"""인스턴스 OverlayFS/NFS 헬스체크 API."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_token_info
from app.config import get_settings
from app.models.instance_health import InstanceHealth, InstanceHealthReport
from app.rate_limit import limiter
from app.services import instance_health as health_svc

router = APIRouter()
_logger = logging.getLogger(__name__)


def _callback_error(status_code: int, reason: str, detail: str) -> HTTPException:
    _logger.warning("Instance callback rejected", extra={"diagnostic_reason": reason})
    return HTTPException(status_code=status_code, detail=detail)


async def _callback_identity(request: Request, instance_id: str) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not auth[len("Bearer ") :].strip():
        raise _callback_error(401, "health_credential_missing", "Bearer 토큰 필요")
    try:
        token_data = await health_svc.verify_report_token(auth[len("Bearer ") :])
    except health_svc.HealthStoreUnavailable as exc:
        raise _callback_error(503, exc.reason, "헬스 인증 저장소를 사용할 수 없습니다") from None
    if token_data is None:
        raise _callback_error(401, "health_credential_expired_or_unknown", "유효하지 않은 토큰")
    if token_data.get("instance_id") != instance_id:
        raise _callback_error(403, "health_credential_instance_mismatch", "토큰이 해당 인스턴스에 귀속되지 않음")
    return token_data


@router.post("/{instance_id}/health/report", status_code=204)
@limiter.limit("30/minute")
async def report_health(
    request: Request,
    instance_id: str,
    body: InstanceHealthReport,
):
    """VM 내부 헬스체크 스크립트에서 주기적으로 POST. Bearer 토큰으로 인증."""
    await _callback_identity(request, instance_id)
    try:
        await health_svc.store_health_result(instance_id, body)
    except health_svc.HealthStoreUnavailable as exc:
        raise _callback_error(503, exc.reason, "헬스 보고 저장소를 사용할 수 없습니다") from None


@router.get("/{instance_id}/health", response_model=InstanceHealth)
async def get_instance_health(
    request: Request,
    instance_id: str,
    token_info: dict = Depends(get_token_info),
):
    """인스턴스 헬스 결과 조회. Nova 메타데이터의 union_health_id로 Redis 조회."""
    import asyncio

    from app.api.deps import get_os_conn
    from app.services import nova

    health_id = instance_id  # fallback: health_id = instance_id
    try:
        conn = await get_os_conn(request, token_info)
        server = await asyncio.to_thread(nova.get_server, conn, instance_id)
        health_id = (server.metadata or {}).get("union_health_id", instance_id)
    except Exception:
        pass

    result = await health_svc.get_health_result(health_id)
    if result is None:
        raise HTTPException(status_code=404, detail="헬스 데이터 없음 (아직 보고되지 않았거나 만료)")
    return result


@router.post("/{instance_id}/credentials/rotate-cephx")
@limiter.limit("10/minute")
async def rotate_cephx_credentials(
    request: Request,
    instance_id: str,
):
    """VM CephX 키 회전 (Bearer 토큰 인증). 새 access_key를 반환한다.

    VM 내 `union-rotate-key.timer`가 주기적으로 호출한다.
    """
    from app.services import manila

    token_data = await _callback_identity(request, instance_id)

    settings = get_settings()
    if settings.union_cephx_rotate_hours == 0:
        raise HTTPException(status_code=503, detail="CephX 키 회전이 비활성화되어 있습니다")

    access_id: str = token_data.get("cephx_access_id", "")
    share_id: str = token_data.get("cephx_share_id", "")
    if not access_id or not share_id:
        raise HTTPException(status_code=422, detail="토큰에 cephx_access_id 또는 cephx_share_id 누락")

    try:
        from app.api.deps import get_os_conn

        conn = await get_os_conn(request, {})
        import asyncio

        new_rule = await asyncio.to_thread(manila.rotate_cephx_access_rule, conn, share_id, access_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        _logger.warning("instance_health failure reason=health_cephx_rotation_unavailable")
        raise HTTPException(status_code=502, detail="Manila CephX 키 회전 실패")

    return {
        "cephx_user": new_rule["access_to"],
        "cephx_key": new_rule["access_key"],
        "new_access_id": new_rule["access_id"],
        "monitors": settings.os_ceph_monitors if hasattr(settings, "os_ceph_monitors") else "",
    }


@router.get("/health", response_model=list[InstanceHealth])
async def list_instances_health(
    token_info: dict = Depends(get_token_info),
):
    """프로젝트 내 인스턴스 헬스 일괄 조회 (Redis 보고 데이터 기반)."""
    try:
        from app.services.cache import _get_client

        r = await _get_client()
        results = []
        async for key in r.scan_iter("afterglow:health:result:*"):
            key_str = key if isinstance(key, str) else key.decode()
            health_id = key_str.split(":")[-1]
            h = await health_svc.get_health_result(health_id)
            if h:
                results.append(h)
        return results
    except Exception:
        return []
