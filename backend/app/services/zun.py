"""Zun 컨테이너 서비스 — openstacksdk에 Zun 프록시가 없으므로 raw REST 사용."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    import openstack

from app.models.containers import ZunContainerInfo
from app.services.service_proxy import join_version_aware_url


class ZunServiceUnavailable(Exception):
    """Zun 서비스가 배포되지 않았거나 접근할 수 없을 때 발생."""


def _get_zun_endpoint(conn: openstack.connection.Connection) -> str:
    """Resolve a catalog-backed Zun endpoint without guessing a network location."""
    try:
        config = getattr(conn, "config", None)
        interface = config.get_interface("container") if config is not None else "public"
        endpoint = conn.session.get_endpoint(service_type="container", interface=interface or "public")
    except Exception as exc:
        raise ZunServiceUnavailable("Zun service endpoint is unavailable") from exc
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ZunServiceUnavailable("Zun service endpoint is unavailable")
    endpoint = endpoint.strip().rstrip("/")
    try:
        parsed = urlsplit(endpoint)
        _ = parsed.port
    except ValueError as exc:
        raise ZunServiceUnavailable("Zun service endpoint is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ZunServiceUnavailable("Zun service endpoint is invalid")
    return endpoint


def _container_to_info(data: dict) -> ZunContainerInfo:
    return ZunContainerInfo(
        uuid=data.get("uuid", ""),
        name=data.get("name", ""),
        status=data.get("status", ""),
        status_reason=data.get("status_reason"),
        image=data.get("image"),
        command=data.get("command") if isinstance(data.get("command"), str) else " ".join(data.get("command") or []),
        cpu=data.get("cpu"),
        memory=str(data.get("memory", "")) if data.get("memory") else None,
        created_at=data.get("created_at"),
        addresses=data.get("addresses"),
        host=data.get("host"),
    )


def list_containers_admin(conn: openstack.connection.Connection) -> list[ZunContainerInfo]:
    """관리자 전용: 전체 프로젝트의 컨테이너 목록 조회."""
    endpoint = _get_zun_endpoint(conn)
    url = join_version_aware_url(endpoint, "/v1/containers?all_projects=True")
    try:
        resp = conn.session.get(url)
        status_code = getattr(resp, "status_code", None) or getattr(resp, "status", None)
        if status_code == 404:
            raise ZunServiceUnavailable("Zun 서비스 엔드포인트가 404를 반환했습니다")
        data = resp.json() if hasattr(resp, "json") else {}
        containers = data.get("containers", data) if isinstance(data, dict) else data
        if isinstance(containers, list):
            return [_container_to_info(c) for c in containers]
        return []
    except ZunServiceUnavailable:
        raise
    except Exception as e:
        err_str = str(e).lower()
        if "404" in err_str or "not found" in err_str or "connection" in err_str:
            raise ZunServiceUnavailable(f"Zun 서비스에 접근할 수 없습니다: {e}") from e
        raise


def list_containers(conn: openstack.connection.Connection) -> list[ZunContainerInfo]:
    endpoint = _get_zun_endpoint(conn)
    url = join_version_aware_url(endpoint, "/v1/containers")
    try:
        resp = conn.session.get(url)
        status_code = getattr(resp, "status_code", None) or getattr(resp, "status", None)
        if status_code == 404:
            raise ZunServiceUnavailable("Zun 서비스 엔드포인트가 404를 반환했습니다")
        data = resp.json() if hasattr(resp, "json") else {}
        containers = data.get("containers", data) if isinstance(data, dict) else data
        if isinstance(containers, list):
            return [_container_to_info(c) for c in containers]
        return []
    except ZunServiceUnavailable:
        raise
    except Exception as e:
        err_str = str(e).lower()
        if "404" in err_str or "not found" in err_str or "connection" in err_str:
            raise ZunServiceUnavailable(f"Zun 서비스에 접근할 수 없습니다: {e}") from e
        raise


def get_container(conn: openstack.connection.Connection, container_id: str) -> ZunContainerInfo:
    endpoint = _get_zun_endpoint(conn)
    url = join_version_aware_url(endpoint, f"/v1/containers/{container_id}")
    resp = conn.session.get(url)
    return _container_to_info(resp.json())


def create_container(
    conn: openstack.connection.Connection,
    name: str,
    image: str,
    command: str | None = None,
    cpu: float | None = None,
    memory: str | None = None,
    environment: dict | None = None,
    auto_remove: bool = False,
    ports: list[dict] | None = None,
) -> ZunContainerInfo:
    endpoint = _get_zun_endpoint(conn)
    body: dict = {"name": name, "image": image}
    if command:
        body["command"] = command
    if cpu is not None:
        body["cpu"] = cpu
    if memory:
        body["memory"] = memory
    if environment:
        body["environment"] = environment
    if auto_remove:
        body["auto_remove"] = auto_remove
    if ports:
        body["ports"] = ports
    url = join_version_aware_url(endpoint, "/v1/containers")
    resp = conn.session.post(url, json=body)
    return _container_to_info(resp.json())


def delete_container(conn: openstack.connection.Connection, container_id: str) -> None:
    import time

    endpoint = _get_zun_endpoint(conn)
    # Running 상태면 먼저 stop 후 삭제 (force 파라미터는 API v1.7+에서만 지원)
    try:
        info = get_container(conn, container_id)
        if info.status and info.status.upper() == "RUNNING":
            stop_container(conn, container_id)
            # 컨테이너가 실제로 멈출 때까지 대기 (최대 30초)
            for _ in range(15):
                time.sleep(2)
                try:
                    info = get_container(conn, container_id)
                    if info.status and info.status.upper() != "RUNNING":
                        break
                except Exception:
                    break
    except Exception:
        pass  # 상태 조회 실패해도 삭제 시도
    url = join_version_aware_url(endpoint, f"/v1/containers/{container_id}")
    conn.session.delete(url)


def start_container(conn: openstack.connection.Connection, container_id: str) -> None:
    endpoint = _get_zun_endpoint(conn)
    url = join_version_aware_url(endpoint, f"/v1/containers/{container_id}/start")
    conn.session.post(url)


def stop_container(conn: openstack.connection.Connection, container_id: str) -> None:
    endpoint = _get_zun_endpoint(conn)
    url = join_version_aware_url(endpoint, f"/v1/containers/{container_id}/stop")
    conn.session.post(url)


def get_container_logs(conn: openstack.connection.Connection, container_id: str) -> str:
    endpoint = _get_zun_endpoint(conn)
    url = join_version_aware_url(endpoint, f"/v1/containers/{container_id}/logs?stdout=true&stderr=true")
    resp = conn.session.get(url)
    return resp.text if hasattr(resp, "text") else str(resp.content)


def get_exec_websocket_url(conn: openstack.connection.Connection, container_id: str) -> tuple[str, str]:
    """Zun exec attach WebSocket URL과 auth token 반환.
    Returns (ws_url, token)
    """
    raw_endpoint = _get_zun_endpoint(conn)
    # http(s)://host:port → ws(s)://host:port
    ws_endpoint = raw_endpoint.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = join_version_aware_url(ws_endpoint, f"/v1/containers/{container_id}/execute_resize")
    token = getattr(conn, "_afterglow_token", None) or conn.auth_token
    return ws_url, token


class ZunApiError(RuntimeError):
    """Zun returned an unexpected or failed API response."""


class ZunResourceNotFound(ZunApiError):
    """A requested Zun resource no longer exists."""


class ZunResourceConflict(ZunApiError):
    """A Zun resource cannot perform the requested lifecycle transition."""


@dataclass(frozen=True)
class ZunExecSession:
    websocket_url: str
    exec_id: str


def _response_status(response: Any) -> int:
    status = getattr(response, "status_code", None) or getattr(response, "status", None)
    return int(status) if isinstance(status, int) else 0


def _strict_json(response: Any, *, action: str, expected: set[int]) -> Any:
    status = _response_status(response)
    if status == 404:
        raise ZunResourceNotFound(f"Zun {action} target was not found")
    if status == 409:
        raise ZunResourceConflict(f"Zun {action} conflicted with current resource state")
    if status not in expected:
        raise ZunApiError(f"Zun {action} failed with status {status or 'unknown'}")
    if status == 204:
        return None
    if hasattr(response, "content") and not response.content:
        return None
    try:
        return response.json()
    except Exception as exc:
        raise ZunApiError(f"Zun {action} returned malformed JSON") from exc


def list_containers_raw(conn: openstack.connection.Connection) -> list[dict[str, Any]]:
    endpoint = _get_zun_endpoint(conn)
    response = conn.session.get(join_version_aware_url(endpoint, "/v1/containers?limit=1000"), timeout=30)
    body = _strict_json(response, action="container list", expected={200})
    items = body.get("containers", body) if isinstance(body, dict) else body
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ZunApiError("Zun container list returned malformed data")
    return items


def get_container_raw(conn: openstack.connection.Connection, container_id: str) -> dict[str, Any] | None:
    endpoint = _get_zun_endpoint(conn)
    response = conn.session.get(join_version_aware_url(endpoint, f"/v1/containers/{container_id}"), timeout=30)
    if _response_status(response) == 404:
        return None
    body = _strict_json(response, action="container get", expected={200})
    if not isinstance(body, dict):
        raise ZunApiError("Zun container get returned malformed data")
    return body


def create_cloud_shell_container(
    conn: openstack.connection.Connection,
    *,
    name: str,
    image: str,
    cpu: float,
    memory_mib: int,
    network_id: str,
    security_group: str,
    volume_id: str,
    labels: dict[str, str],
) -> dict[str, Any]:
    endpoint = _get_zun_endpoint(conn)
    body = {
        "name": name,
        "image": image,
        "cpu": cpu,
        "memory": memory_mib,
        "command": ["/bin/sh", "-lc", "trap : TERM INT; sleep infinity & wait"],
        "interactive": False,
        "tty": False,
        "privileged": False,
        "auto_remove": False,
        "nets": [{"network": network_id}],
        "security_groups": [security_group],
        "mounts": [{"type": "volume", "source": volume_id, "destination": "/home/cloudshell"}],
        "labels": labels,
    }
    response = conn.session.post(join_version_aware_url(endpoint, "/v1/containers?run=true"), json=body, timeout=30)
    result = _strict_json(response, action="container create", expected={200, 201, 202})
    if not isinstance(result, dict) or not isinstance(result.get("uuid"), str):
        raise ZunApiError("Zun container create returned malformed data")
    return result


def start_container_strict(conn: openstack.connection.Connection, container_id: str) -> None:
    endpoint = _get_zun_endpoint(conn)
    response = conn.session.post(join_version_aware_url(endpoint, f"/v1/containers/{container_id}/start"), timeout=30)
    _strict_json(response, action="container start", expected={200, 202, 204})


def stop_container_strict(conn: openstack.connection.Connection, container_id: str) -> None:
    endpoint = _get_zun_endpoint(conn)
    response = conn.session.post(join_version_aware_url(endpoint, f"/v1/containers/{container_id}/stop"), timeout=30)
    _strict_json(response, action="container stop", expected={200, 202, 204})


def delete_container_strict(conn: openstack.connection.Connection, container_id: str) -> None:
    endpoint = _get_zun_endpoint(conn)
    response = conn.session.delete(
        join_version_aware_url(endpoint, f"/v1/containers/{container_id}?force=true"), timeout=30
    )
    _strict_json(response, action="container delete", expected={200, 202, 204})


def wait_for_container_status(
    conn: openstack.connection.Connection,
    container_id: str,
    *,
    accepted: set[str],
    failed: set[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        container = get_container_raw(conn, container_id)
        if container is None:
            raise ZunResourceNotFound("Zun container disappeared while waiting for status")
        status = str(container.get("status", "")).upper()
        if status in accepted:
            return container
        if status in failed:
            raise ZunResourceConflict(f"Zun container entered terminal status {status}")
        if time.monotonic() >= deadline:
            raise TimeoutError("Zun container did not reach the requested status in time")
        time.sleep(1)


def create_exec_session(
    conn: openstack.connection.Connection,
    container_id: str,
    *,
    trusted_websocket_origin: str,
    command: str | None = None,
) -> ZunExecSession:
    endpoint = _get_zun_endpoint(conn)
    response = conn.session.post(
        join_version_aware_url(endpoint, f"/v1/containers/{container_id}/execute"),
        json={
            "command": command or "/usr/local/bin/afterglow-cloud-shell-bootstrap",
            "run": False,
            "interactive": True,
        },
        timeout=30,
    )
    body = _strict_json(response, action="interactive execute", expected={200, 201, 202})
    if not isinstance(body, dict):
        raise ZunApiError("Zun interactive execute returned malformed data")
    websocket_url = body.get("proxy_url")
    exec_id = body.get("exec_id")
    if not all(isinstance(value, str) and value for value in (websocket_url, exec_id)):
        raise ZunApiError("Zun interactive execute omitted attach credentials")
    parsed = urlsplit(websocket_url)
    trusted = urlsplit(trusted_websocket_origin)
    try:
        parsed_port = parsed.port
        trusted_port = trusted.port
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ZunApiError("Zun interactive execute returned a malformed proxy URL") from exc
    if (
        parsed.scheme != trusted.scheme
        or (parsed.hostname or "").lower() != (trusted.hostname or "").lower()
        or parsed_port != trusted_port
        or not parsed.path
        or parsed.username
        or parsed.password
        or parsed.fragment
        or set(query) != {"token", "uuid", "exec_id"}
        or any(len(values) != 1 or not values[0] for values in query.values())
        or query["uuid"][0] != container_id
        or query["exec_id"][0] != exec_id
    ):
        raise ZunApiError("Zun interactive execute returned an untrusted proxy URL")
    return ZunExecSession(websocket_url=websocket_url, exec_id=exec_id)


def resize_exec_session(
    conn: openstack.connection.Connection,
    container_id: str,
    *,
    exec_id: str,
    cols: int,
    rows: int,
) -> None:
    endpoint = _get_zun_endpoint(conn)
    response = conn.session.post(
        join_version_aware_url(
            endpoint,
            f"/v1/containers/{container_id}/execute_resize?exec_id={exec_id}&w={cols}&h={rows}",
        ),
        timeout=15,
    )
    _strict_json(response, action="interactive resize", expected={200, 202, 204})
