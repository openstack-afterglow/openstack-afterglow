from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

logger = logging.getLogger(__name__)


async def resolve_default_network(
    conn: openstack.connection.Connection,
    settings,
) -> str | None:
    """Apply explicit project-network precedence without selector fallbacks.

    Callers invoke this only after an explicit request network has been checked.
    A persisted project default wins. Automatic provisioning requires the
    administrator-selected external network; when automatic provisioning is
    disabled, the validated shared policy is the final fallback.
    """
    from app.services.default_network import ensure_default_network, get_default_network_id
    from app.services.resource_policy_store import resolve_policies

    project_id = conn._afterglow_project_id
    project_network_id = await get_default_network_id(project_id)
    if project_network_id:
        network = await asyncio.to_thread(conn.network.get_network, project_network_id)
        if network is None:
            raise RuntimeError("project default network is unavailable")
        return project_network_id

    if settings.default_network_enabled:
        policies = await resolve_policies(conn=conn, keys=("nova.default_external_network",))
        default_net = await ensure_default_network(
            conn,
            project_id,
            external_network_id=policies["nova.default_external_network"],
            cidr=settings.default_network_cidr,
        )
        return default_net.id

    policies = await resolve_policies(conn=conn, keys=("nova.default_network",))
    return policies["nova.default_network"]


async def resolve_availability_zones(
    conn: openstack.connection.Connection,
    requested_zone: str | None,
) -> tuple[str, str]:
    """Resolve compute and volume placement independently before side effects."""
    if requested_zone:
        return requested_zone, requested_zone

    from app.services.resource_policy_store import resolve_policies

    policies = await resolve_policies(
        conn=conn,
        keys=("nova.default_compute_availability_zone", "cinder.default_volume_availability_zone"),
    )
    return policies["nova.default_compute_availability_zone"], policies["cinder.default_volume_availability_zone"]


async def compute_effective_security_groups(
    conn: openstack.connection.Connection,
    settings,
    project_id: str,
    resolved_libs: list[str],
    gpu_available: bool,
    base_sgs: list[str],
) -> list[str]:
    """Union egress + node_exporter + dcgm_exporter SG를 결정.
    개별 SG attach 실패는 warning log 후 계속 (기존 동작과 동일).
    """
    from app.services import neutron

    sgs = list(base_sgs)

    if resolved_libs and settings.union_auto_egress_sg_enabled:
        try:
            _sg_name = await asyncio.to_thread(
                neutron.ensure_union_egress_sg,
                conn,
                project_id,
                settings.union_egress_sg_name,
            )
            if _sg_name not in sgs:
                sgs.append(_sg_name)
        except Exception:
            logger.warning("Union egress SG 자동 attach 실패, 계속 진행", exc_info=True)

    if settings.monitoring_auto_sg_enabled and settings.monitoring_scrape_cidr:
        if "default" not in sgs:
            sgs.append("default")
        try:
            _ne = await asyncio.to_thread(
                neutron.ensure_node_exporter_sg,
                conn,
                project_id,
                settings.node_exporter_sg_name,
                settings.monitoring_scrape_cidr,
            )
            if _ne not in sgs:
                sgs.append(_ne)
        except Exception:
            logger.warning("node_exporter SG 자동 attach 실패, 계속 진행", exc_info=True)
        if gpu_available:
            try:
                _dc = await asyncio.to_thread(
                    neutron.ensure_dcgm_exporter_sg,
                    conn,
                    project_id,
                    settings.dcgm_exporter_sg_name,
                    settings.monitoring_scrape_cidr,
                )
                if _dc not in sgs:
                    sgs.append(_dc)
            except Exception:
                logger.warning("dcgm_exporter SG 자동 attach 실패, 계속 진행", exc_info=True)

    return sgs


def build_instance_meta(
    resolved_libs: list[str],
    file_storages: list[dict],
    upper_volume_id: str | None,
    scheduling: str,
    strategy: str,
    health_id: str,
    health_token: str,
) -> dict:
    """Create Nova metadata while keeping retained Union fields layer-owned."""
    meta: dict = {"scheduling": scheduling}
    if scheduling == "ha":
        meta["HA_Enabled"] = "True"
    if not resolved_libs:
        return meta

    meta.update(
        {
            "union_libraries": ",".join(resolved_libs),
            "union_strategy": strategy or "none",
            "union_share_ids": ",".join(s.get("file_storage_id", "") for s in file_storages),
            "union_upper_volume_id": upper_volume_id or "none",
        }
    )
    if health_token and health_id:
        meta["union_health_id"] = health_id
    return meta


async def try_issue_health_token(
    project_id: str,
    settings,
) -> tuple[str, str, str]:
    """Return a best-effort instance-health report token and callback URL."""
    report_url = settings.instance_health_callback_base_url or ""
    if not report_url:
        return "", "", ""
    health_id = str(uuid.uuid4())
    try:
        from app.services import instance_health as _ih

        token = await _ih.issue_report_token(health_id, project_id)
        return health_id, report_url, token
    except Exception:
        logger.warning("헬스 토큰 발급 실패, 헬스체크 없이 계속", exc_info=True)
        return "", "", ""


async def rollback_instance(
    conn: openstack.connection.Connection,
    server_id: str | None,
    boot_volume_id: str | None,
    upper_volume_id: str | None,
    file_storage_ids: list[str],
    access_ids: list[tuple[str, str]],
    floating_ip_id: str | None = None,
) -> None:
    """인스턴스 생성 실패 시 역순 rollback."""
    from app.services import cinder, keystone, manila, neutron, nova

    if floating_ip_id:
        try:
            await asyncio.to_thread(neutron.delete_floating_ip, conn, floating_ip_id)
        except Exception as e:
            logger.error(f"Rollback - Floating IP 삭제 실패: {e}")

    if server_id:
        try:
            await asyncio.to_thread(nova.delete_server, conn, server_id)
        except Exception as e:
            logger.error(f"Rollback - 서버 삭제 실패: {e}")

    for vol_id in [boot_volume_id, upper_volume_id]:
        if vol_id:
            try:
                await asyncio.to_thread(cinder.delete_volume, conn, vol_id)
            except Exception as e:
                logger.error(f"Rollback - 볼륨 삭제 실패 {vol_id}: {e}")

    try:
        svc_conn = await asyncio.to_thread(keystone.get_service_project_connection)
    except RuntimeError:
        svc_conn = conn
    for file_storage_id, access_id in access_ids:
        try:
            await asyncio.to_thread(manila.revoke_access_rule, svc_conn, file_storage_id, access_id)
        except Exception as e:
            logger.error(f"Rollback - access rule 삭제 실패: {e}")

    for file_storage_id in file_storage_ids:
        try:
            await asyncio.to_thread(manila.delete_file_storage, conn, file_storage_id)
        except Exception as e:
            logger.error(f"Rollback - 파일 스토리지 삭제 실패 {file_storage_id}: {e}")
