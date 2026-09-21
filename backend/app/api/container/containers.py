from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack
import asyncio
import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from app.api.common.activity_recorder import rec
from app.api.deps import CacheMode, cache_mode, get_os_conn, get_token_info
from app.models.containers import (
    ContainerListResponse,
    CreateZunContainerRequest,
    ZunContainerInfo,
)
from app.rate_limit import limiter
from app.services import cache, zun
from app.services.cache import invalidation, keys
from app.services.service_proxy import join_version_aware_url
from app.services.ws_ticket import WebSocketTicketError, consume_ticket, issue_ticket
from app.services.zun import ZunServiceUnavailable

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=ContainerListResponse)
async def list_containers(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    pid = conn._afterglow_project_id

    async def _load():
        try:
            items = await asyncio.to_thread(zun.list_containers, conn)
            return ContainerListResponse(items=items)
        except ZunServiceUnavailable:
            return ContainerListResponse(
                items=[],
                service_available=False,
                message="컨테이너 서비스에 연결할 수 없습니다",
            )
        except Exception:
            raise HTTPException(status_code=500, detail="컨테이너 목록 조회 실패")

    return await cache.cached_call(
        keys.project_key("zun", pid, "containers"),
        cache.ttl_normal(),
        _load,
        enabled=cm.enabled,
        refresh=cm.refresh,
    )


@router.get("/{container_id}", response_model=ZunContainerInfo)
async def get_container(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    cm: CacheMode = Depends(cache_mode),
):
    pid = conn._afterglow_project_id
    try:
        return await cache.cached_call(
            keys.project_key("zun", pid, "containers", sub=container_id),
            cache.ttl_normal(),
            lambda: zun.get_container(conn, container_id),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
    except Exception:
        raise HTTPException(status_code=404, detail="컨테이너를 찾을 수 없습니다")


@router.post("", response_model=ZunContainerInfo, status_code=201)
@limiter.limit("5/minute")
async def create_container(
    request: Request,
    req: CreateZunContainerRequest,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        ports = [p.model_dump(exclude_none=True) for p in req.ports] if req.ports else None
        result = await asyncio.to_thread(
            zun.create_container,
            conn,
            req.name,
            req.image,
            req.command,
            req.cpu,
            req.memory,
            req.environment,
            req.auto_remove,
            ports,
        )
        pid = conn._afterglow_project_id
        await cache.invalidate(f"afterglow:zun:{pid}:*")
        await invalidation.invalidate_mutation_count("zun", pid)
        await rec(token_info, conn, resource_type="container", action="create", resource_name=req.name)
        return result
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="container",
            action="create",
            status="failed",
            resource_name=req.name,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="컨테이너 생성 실패")


@router.delete("/{container_id}", status_code=204)
async def delete_container(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    try:
        await asyncio.to_thread(zun.delete_container, conn, container_id)
        pid = conn._afterglow_project_id
        await cache.invalidate(f"afterglow:zun:{pid}:*")
        await invalidation.invalidate_mutation_count("zun", pid)
        await rec(token_info, conn, resource_type="container", action="delete", resource_id=container_id)
    except Exception as e:
        await rec(
            token_info,
            conn,
            resource_type="container",
            action="delete",
            status="failed",
            resource_id=container_id,
            error_message=str(e)[:500],
        )
        raise HTTPException(status_code=500, detail="컨테이너 삭제 실패")


@router.post("/{container_id}/start", status_code=204)
async def start_container(container_id: str, conn: openstack.connection.Connection = Depends(get_os_conn)):
    try:
        await asyncio.to_thread(zun.start_container, conn, container_id)
        pid = conn._afterglow_project_id
        await cache.invalidate(f"afterglow:zun:{pid}:containers:{container_id}")
        await invalidation.invalidate_mutation_count("zun", pid)
    except Exception:
        raise HTTPException(status_code=500, detail="컨테이너 시작 실패")


@router.post("/{container_id}/stop", status_code=204)
async def stop_container(container_id: str, conn: openstack.connection.Connection = Depends(get_os_conn)):
    try:
        await asyncio.to_thread(zun.stop_container, conn, container_id)
        pid = conn._afterglow_project_id
        await cache.invalidate(f"afterglow:zun:{pid}:containers:{container_id}")
        await invalidation.invalidate_mutation_count("zun", pid)
    except Exception:
        raise HTTPException(status_code=500, detail="컨테이너 중지 실패")


@router.get("/{container_id}/logs")
async def get_container_logs(container_id: str, conn: openstack.connection.Connection = Depends(get_os_conn)):
    try:
        logs = await asyncio.to_thread(zun.get_container_logs, conn, container_id)
        return {"logs": logs}
    except Exception:
        raise HTTPException(status_code=500, detail="로그 조회 실패")


class ExecRequest(BaseModel):
    command: str = "/bin/bash"


@router.post("/{container_id}/exec-ticket", status_code=201)
async def create_exec_ticket(
    container_id: str,
    conn: openstack.connection.Connection = Depends(get_os_conn),
):
    """WebSocket exec 연결에 사용할 일회용 티켓 발급 (30초 유효)."""
    try:
        ticket = await issue_ticket(
            "container-exec",
            {
                "container_id": container_id,
                "user_id": conn._afterglow_user_id,
                "project_id": conn._afterglow_project_id,
                "token": conn._afterglow_token,
            },
            ttl_seconds=30,
        )
    except WebSocketTicketError:
        raise HTTPException(status_code=503, detail="WebSocket 티켓 저장소를 사용할 수 없습니다") from None
    return {"ticket": ticket}


@router.websocket("/{container_id}/exec")
async def container_exec_ws(
    container_id: str,
    websocket: WebSocket,
    ticket: str = Query(...),
):
    """컨테이너 exec 인터랙티브 WebSocket 프록시.
    Zun execute API를 통해 명령을 실행하고 결과를 반환하는 간단한 셸 에뮬레이터.
    인증은 일회용 티켓으로 처리 (POST /{id}/exec-ticket 으로 발급).
    """
    await websocket.accept()
    conn = None
    try:
        from app.services import keystone

        try:
            payload = await consume_ticket(ticket, expected_kind="container-exec")
        except WebSocketTicketError:
            await websocket.close(code=4001)
            return
        if payload is None:
            await websocket.close(code=4001)
            return
        if payload.get("container_id") != container_id:
            await websocket.close(code=4001)
            return

        scoped_token = payload["token"]
        pid = payload["project_id"]
        conn = await asyncio.to_thread(keystone.get_openstack_connection, scoped_token, pid)
        conn._afterglow_token = scoped_token
        conn._afterglow_project_id = pid

        endpoint = zun._get_zun_endpoint(conn)
        await websocket.send_text(
            "\r\n\x1b[32mZun 컨테이너 콘솔에 연결됨\x1b[0m\r\n\x1b[33m명령어를 입력하세요 (exit 로 종료)\x1b[0m\r\n$ "
        )

        while True:
            data = await websocket.receive_text()
            cmd = data.strip()
            if cmd in ("exit", "quit", "logout"):
                await websocket.send_text("\r\n연결 종료\r\n")
                break
            if not cmd:
                await websocket.send_text("$ ")
                continue
            try:
                body = {"command": ["/bin/sh", "-c", cmd]}
                exec_url = join_version_aware_url(endpoint, f"/v1/containers/{container_id}/execute")
                resp = await asyncio.to_thread(lambda _url=exec_url, _body=body: conn.session.post(_url, json=_body))
                result = resp.json() if hasattr(resp, "json") else {}
                output = result.get("output", "")
                exit_code = result.get("exit_code", 0)
                if output:
                    await websocket.send_text(output.replace("\n", "\r\n"))
                if exit_code != 0:
                    await websocket.send_text(f"\r\n\x1b[31m[exit {exit_code}]\x1b[0m")
                await websocket.send_text("\r\n$ ")
            except Exception as e:
                logger.warning("Container exec command error: %s", e)
                await websocket.send_text("\r\n\x1b[31m명령 실행에 실패했습니다\x1b[0m\r\n$ ")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("Container exec WS error: %s", e)
        try:
            await websocket.send_text("\r\n\x1b[31m연결 오류가 발생했습니다\x1b[0m\r\n")
            await websocket.close()
        except Exception:
            pass
    finally:
        if conn:
            try:
                await asyncio.to_thread(conn.close)
            except Exception:
                pass
