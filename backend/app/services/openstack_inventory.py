"""OpenStack 리소스 수집 유틸리티 — FastAPI 의존 없음.

app.notion_worker에서 안전하게 import 가능.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

_logger = logging.getLogger(__name__)


def _fetch_hypervisors_raw(conn: openstack.connection.Connection) -> list[dict]:
    """Nova microversion 2.53으로 하이퍼바이저 raw JSON 조회.
    2.88+ 에서 vcpus/memory_mb 등 필드가 deprecated되므로 2.53을 명시적으로 사용."""
    endpoint = conn.compute.get_endpoint()
    resp = conn.session.get(
        f"{endpoint}/os-hypervisors/detail",
        headers={"OpenStack-API-Version": "compute 2.53"},
    )
    return resp.json().get("hypervisors", [])


def list_servers_complete(conn, filters: dict | None = None) -> list[dict]:
    """Consume Nova's native marker pages without trusting next-link destinations."""
    endpoint = conn.compute.get_endpoint().rstrip("/")
    params = {**(filters or {}), "all_tenants": "1", "limit": "1000"}
    params.pop("marker", None)
    rows = []
    seen = set()
    while True:
        response = conn.session.get(
            f"{endpoint}/servers/detail",
            params=dict(params),
            headers={"OpenStack-API-Version": "compute 2.53"},
        )
        response.raise_for_status()
        body = response.json()
        batch = body.get("servers")
        if not isinstance(batch, list):
            raise RuntimeError("Nova inventory response is invalid")
        rows.extend(batch)
        has_next = any(link.get("rel") == "next" for link in body.get("servers_links", []))
        if not has_next and len(batch) < 1000:
            return rows
        marker = batch[-1].get("id") if batch else None
        if not marker or marker in seen:
            raise RuntimeError("Nova inventory pagination did not advance")
        seen.add(marker)
        params["marker"] = marker


async def collect_instance_data(
    email_to_page_id: dict[str, str] | None = None,
    host_to_page_id: dict[str, str] | None = None,
    gpu_name_to_page_id: dict[str, str] | None = None,
) -> list[dict]:
    """OpenStack에서 전체 인스턴스 + 플레이버 + 사용자 + 프로젝트 정보를 수집한다.

    email_to_page_id: People DB의 {이메일 → page_id} 맵 (user relation 설정용)
    host_to_page_id: Hypervisor DB의 {호스트명 → page_id} 맵 (openstack resource relation 설정용)
    gpu_name_to_page_id: GPU Spec DB의 {GPU정식이름 → page_id} 맵 (GPU spec relation 설정용)
    """
    from app.config import get_settings
    from app.services import native_transport, notion_sync
    from app.services.gpu_inventory import build_alias_to_device_name_map, resolve_alias_to_device_name

    settings = get_settings()
    alias_to_device_name = build_alias_to_device_name_map()
    conn = native_transport.connect(
        auth_url=settings.os_auth_url,
        username=settings.os_username,
        password=settings.os_password,
        project_name=settings.os_project_name,
        user_domain_name=settings.os_user_domain_name,
        project_domain_name=settings.os_project_domain_name,
        verify=settings.ssl_verify,
    )

    try:

        def _collect():
            from app.services.nova import list_catalog_flavors

            flavor_infos = list_catalog_flavors(conn)
            flavors_by_id = {flavor.id: flavor for flavor in flavor_infos}
            flavors_by_name = {flavor.name: flavor for flavor in flavor_infos}

            # 프로젝트 맵
            projects = {}
            try:
                for p in conn.identity.projects():
                    projects[p.id] = p.name
            except Exception:
                _logger.warning("프로젝트 목록 조회 실패", exc_info=True)

            # 사용자 맵 (id → name, id → email)
            users = {}
            user_emails: dict[str, str] = {}
            try:
                for u in conn.identity.users():
                    users[u.id] = u.name
                    if getattr(u, "email", None):
                        user_emails[u.id] = u.email
            except Exception:
                _logger.warning("사용자 목록 조회 실패", exc_info=True)

            # 인스턴스 수집
            result = []
            for s in conn.compute.servers(all_projects=True, details=True):
                # 서버 응답의 embedded flavor snapshot을 우선 사용하고, UUID 또는 이름으로
                # 상세 flavor를 보충한다. Nova 2.47+에서는 id에 original_name이 올 수 있다.
                server_flavor = s.flavor if hasattr(s.flavor, "get") else {}
                fl_id = server_flavor.get("id", "")
                fl_name = server_flavor.get("original_name", "") or server_flavor.get("name", "")
                fl = flavors_by_id.get(fl_id) or flavors_by_name.get(fl_name) or flavors_by_name.get(fl_id)
                embedded_vcpus = server_flavor.get("vcpus")
                embedded_ram = server_flavor.get("ram")
                embedded_extra_specs = server_flavor.get("extra_specs") or {}
                vcpus = embedded_vcpus if embedded_vcpus is not None else (fl.vcpus if fl else 0)
                ram_mb = embedded_ram if embedded_ram is not None else (fl.ram if fl else 0)
                extra_specs = embedded_extra_specs or (fl.extra_specs if fl else {})

                status = (s.status or "").upper()
                resource_allocated = notion_sync.is_resource_allocated_status(status)

                # GPU (alias 이름 추출)
                gpu_alias, flavor_gpu_count = notion_sync._gpu_info_from_flavor(
                    fl_name or (fl.name if fl else ""),
                    extra_specs or {},
                )

                # GPU alias → 정식 이름 변환 및 GPU map 검증
                gpu_spec_page_id = ""
                gpu_display_name = gpu_alias  # Notion GPU 필드에 표시할 이름
                gpu_count = flavor_gpu_count if resource_allocated else 0
                if gpu_alias:
                    canonical_name = resolve_alias_to_device_name(gpu_alias, alias_to_device_name)
                    if canonical_name:
                        gpu_display_name = canonical_name
                        if resource_allocated:
                            gpu_spec_page_id = (gpu_name_to_page_id or {}).get(canonical_name, "")
                            if not gpu_spec_page_id:
                                _logger.debug(
                                    "GPU spec 페이지 미발견 (GPU=%s, alias=%s) — GPU spec DB 동기화 후 재시도 예정",
                                    canonical_name,
                                    gpu_alias,
                                )
                    elif resource_allocated:
                        _logger.warning(
                            "GPU alias '%s'가 PCI_DEVICE_MAP에 없음 — GPU spec relation 미설정 (flavor=%s)",
                            gpu_alias,
                            fl_name,
                        )
                # IP 주소
                fixed_ips = []
                floating_ips = []
                addresses = s.addresses or {}
                for _net_name, addrs in addresses.items():
                    for addr in addrs:
                        if addr.get("OS-EXT-IPS:type") == "floating":
                            floating_ips.append(addr["addr"])
                        else:
                            fixed_ips.append(addr["addr"])

                # created_at → ISO 8601
                created_at_iso = ""
                if s.created_at:
                    created_at_iso = str(s.created_at).replace(" ", "T")
                    if not created_at_iso.endswith("Z") and "+" not in created_at_iso:
                        created_at_iso += "Z"

                # 호스트 정보 (openstack resource relation 연결용)
                compute_host = getattr(s, "compute_host", "") or ""

                # 사용자 page_id (People DB relation)
                user_email = user_emails.get(s.user_id, "")
                user_page_id = (email_to_page_id or {}).get(user_email.lower(), "")

                hypervisor_page_id = ""
                if compute_host and resource_allocated:
                    hypervisor_page_id = (host_to_page_id or {}).get(compute_host, "")

                result.append(
                    {
                        "name": s.name or "",
                        "instance_id": s.id or "",
                        "status": status,
                        "project_name": projects.get(s.project_id, ""),
                        "flavor_name": fl_name or (fl.name if fl else ""),
                        "vcpus": vcpus,
                        "ram_gb": round(ram_mb / 1024) if ram_mb else 0,
                        "gpu_name": gpu_display_name,
                        "gpu_count": gpu_count,
                        "gpu_spec_page_id": gpu_spec_page_id,
                        "fixed_ip": ", ".join(fixed_ips),
                        "floating_ip": ", ".join(floating_ips),
                        "created_at": created_at_iso,
                        "compute_host": compute_host,
                        "user_page_id": user_page_id,
                        "hypervisor_page_id": hypervisor_page_id,
                    }
                )

            return result

        return await asyncio.to_thread(_collect)
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def collect_hypervisor_data(gpu_name_to_page_id: dict[str, str] | None = None) -> list[dict]:
    """OpenStack에서 하이퍼바이저 리소스 + GPU 정보를 수집한다.

    gpu_name_to_page_id: GPU Spec DB의 {GPU정식이름 → page_id} 맵.
                         제공 시 각 하이퍼바이저의 GPU relation page_id 목록을 설정한다.
    """
    from app.config import get_settings
    from app.services import native_transport
    from app.services.gpu_inventory import _collect_gpu_hosts
    from app.services.openstack_inventory import _fetch_hypervisors_raw

    settings = get_settings()
    conn = native_transport.connect(
        auth_url=settings.os_auth_url,
        username=settings.os_username,
        password=settings.os_password,
        project_name=settings.os_project_name,
        user_domain_name=settings.os_user_domain_name,
        project_domain_name=settings.os_project_domain_name,
        verify=settings.ssl_verify,
    )

    try:

        def _collect():
            raw = _fetch_hypervisors_raw(conn)

            # Placement API로 호스트별 GPU 그룹 수집
            host_gpu_map: dict[str, list[dict]] = {}
            try:
                gpu_data = _collect_gpu_hosts(conn)
                for h in gpu_data.get("aggregated_hosts", []):
                    host_gpu_map[h["name"]] = h.get("gpu_groups", [])
            except Exception:
                _logger.warning("하이퍼바이저 GPU 데이터 수집 실패 — GPU 정보 없이 진행", exc_info=True)

            result = []
            for h in raw:
                hostname = h.get("hypervisor_hostname", "")
                mem_mb = h.get("memory_mb", 0) or 0
                mem_used_mb = h.get("memory_mb_used", 0) or 0

                gpu_groups = host_gpu_map.get(hostname, [])
                gpu_total = sum(g.get("total", 0) for g in gpu_groups)

                # GPU spec page_id 목록 (여러 종류 GPU 가능)
                gpu_spec_page_ids: list[str] = []
                for g in gpu_groups:
                    device_name = g.get("device_name", "")
                    page_id = (gpu_name_to_page_id or {}).get(device_name, "")
                    if page_id and page_id not in gpu_spec_page_ids:
                        gpu_spec_page_ids.append(page_id)

                result.append(
                    {
                        "name": hostname,
                        "status": f"{h.get('state', '')}/{h.get('status', '')}",
                        "running_vms": h.get("running_vms", 0) or 0,
                        "vcpus_used": h.get("vcpus_used", 0) or 0,
                        "vcpus": h.get("vcpus", 0) or 0,
                        "memory_used_gb": round(mem_used_mb / 1024),
                        "memory_size_gb": round(mem_mb / 1024),
                        "gpu_spec_page_ids": gpu_spec_page_ids,
                        "gpu_total": gpu_total,
                        "gpu_groups": gpu_groups,  # 집계 계산용
                    }
                )
            return result

        return await asyncio.to_thread(_collect)
    finally:
        try:
            conn.close()
        except Exception:
            pass
