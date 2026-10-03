"""
Manila CephFS 파일 스토리지 관리 서비스.

openstacksdk 는 Manila(Shared File Systems) API 를 manilaclient 로 래핑하지 않으므로
직접 REST 호출로 처리한다.
"""

import logging
import time

import httpx

from app.models.storage import FileStorageDeleteDiagnostic, FileStorageInfo

logger = logging.getLogger(__name__)


class ManilaClient:
    """Keystone 토큰 기반 Manila v2 REST 클라이언트."""

    def __init__(self, endpoint: str, token: str, project_id: str):
        # endpoint 예: http://manila.example.com:8786/v2/{project_id}
        self.base = endpoint.rstrip("/")
        self.headers = {
            "X-Auth-Token": token,
            "X-OpenStack-Manila-API-Version": "2.65",
            "Content-Type": "application/json",
        }
        self.project_id = project_id

    def _url(self, path: str) -> str:
        if self.base.endswith(self.project_id):
            return f"{self.base}/{path.lstrip('/')}"
        return f"{self.base}/{self.project_id}/{path.lstrip('/')}"

    def get(self, path: str, params: dict | None = None) -> dict:
        with httpx.Client() as c:
            r = c.get(self._url(path), headers=self.headers, params=params, timeout=30)
            r.raise_for_status()
            return r.json()

    def post(self, path: str, body: dict, log_errors: bool = True) -> dict:
        with httpx.Client() as c:
            url = self._url(path)
            logger.debug(f"Manila POST {url}")
            r = c.post(url, headers=self.headers, json=body, timeout=30)
            if log_errors and not r.is_success:
                logger.error(f"Manila POST {url} → {r.status_code}: {r.text}")
            r.raise_for_status()
            return r.json() if r.content else {}

    def put(self, path: str, body: dict) -> dict:
        with httpx.Client() as c:
            r = c.put(self._url(path), headers=self.headers, json=body, timeout=30)
            r.raise_for_status()
            return r.json()

    def delete(self, path: str) -> None:
        with httpx.Client() as c:
            r = c.delete(self._url(path), headers=self.headers, timeout=30)
            if r.status_code not in (200, 202, 204):
                r.raise_for_status()


def _normalize_manila_url(url: str) -> str:
    """Manila endpoint 가 /v1 으로 끝나면 /v2 로 치환.

    Manila v1 의 quota-sets 엔드포인트는 'os-quota-sets' 였고 v2 부터 'quota-sets' 로 변경됨.
    클라이언트는 마이크로버전 헤더(2.65)를 보내므로 v2 path 만 사용.
    """
    import re

    return re.sub(r"/v1(?=/|$)", "/v2", url)


def _get_manila_endpoint(conn) -> str:
    """openstacksdk connection 에서 Manila 엔드포인트 추출.
    OS_MANILA_ENDPOINT 환경변수로 오버라이드 가능.
    """
    from app.config import get_settings

    settings = get_settings()
    if getattr(settings, "os_manila_endpoint", ""):
        url = settings.os_manila_endpoint.rstrip("/")
        logger.debug(f"Manila endpoint (override): {url}")
        return _normalize_manila_url(url)

    # v2 우선: sharev2 → shared-file-system → share (v1 fallback)
    # Manila v1 catalog 에서 quota-sets 경로가 os-quota-sets 였으므로 v2 endpoint 우선 선택.
    for service_type in ("sharev2", "shared-file-system", "share"):
        for interface in ("public", "internal", "admin"):
            try:
                url = conn.endpoint_for(service_type, interface=interface)
                if url:
                    normalized = _normalize_manila_url(url.rstrip("/"))
                    logger.debug(f"Manila endpoint [{service_type}/{interface}]: {normalized}")
                    return normalized
            except Exception:
                continue
    raise RuntimeError("Manila 엔드포인트를 서비스 카탈로그에서 찾을 수 없습니다")


def get_client(conn) -> ManilaClient:
    # openstacksdk가 토큰을 재발급할 수 있으므로 원본 토큰/project_id 우선 사용
    token = getattr(conn, "_afterglow_token", None) or conn.auth_token
    project_id = getattr(conn, "_afterglow_project_id", None) or conn.current_project_id
    endpoint = _get_manila_endpoint(conn)
    logger.debug(
        f"Manila client: endpoint={endpoint}, project_id={project_id}, token_src={'original' if hasattr(conn, '_afterglow_token') else 'sdk'}"
    )
    return ManilaClient(endpoint=endpoint, token=token, project_id=project_id)


# ---------------------------------------------------------------------------
# 파일 스토리지 관리
# ---------------------------------------------------------------------------


def get_file_storage_quota(conn, *, strict: bool = False) -> dict:
    """프로젝트의 Manila 할당량 (limit + in_use) 조회."""
    try:
        client = get_client(conn)
        project_id = getattr(conn, "_afterglow_project_id", None) or conn.current_project_id
        quota_path = f"quota-sets/{project_id}/detail" if strict else f"quota-sets/{project_id}"
        data = client.get(quota_path, params={"usage": "true"})
        quota = data.get("quota_set", {})

        def _q(key):
            value = quota.get(key, {})
            if isinstance(value, dict):
                return {"limit": value.get("limit", -1), "in_use": value.get("in_use", 0)}
            return {"limit": int(value) if value is not None else -1, "in_use": 0}

        def _strict_entry(key: str) -> dict:
            value = quota.get(key)
            if not isinstance(value, dict) or "limit" not in value or "in_use" not in value:
                raise ValueError(f"Manila quota usage is missing for {key}")
            limit, in_use = value["limit"], value["in_use"]
            if (
                not isinstance(limit, (int, float))
                or isinstance(limit, bool)
                or not isinstance(in_use, (int, float))
                or isinstance(in_use, bool)
            ):
                raise ValueError(f"Manila quota data is malformed for {key}")
            return {"limit": limit, "in_use": in_use}

        if strict:
            result = {
                "shares": _strict_entry("shares"),
                "gigabytes": _strict_entry("gigabytes"),
            }
        else:
            result = {
                "shares": _q("shares"),
                "gigabytes": _q("gigabytes"),
                "share_networks": _q("share_networks"),
                "share_groups": _q("share_groups"),
                "snapshot_gigabytes": _q("snapshot_gigabytes"),
            }

        # The supplemental share-count probe remains soft in strict mode:
        # only failure of the primary quota response is authoritative.
        if result["shares"]["in_use"] == 0:
            try:
                shares_data = client.get("shares/detail")
                actual_shares = shares_data.get("shares", [])
                if actual_shares:
                    result["shares"]["in_use"] = len(actual_shares)
                    total_gb = sum(int(share.get("size", 0)) for share in actual_shares)
                    if total_gb > 0 and result["gigabytes"]["in_use"] == 0:
                        result["gigabytes"]["in_use"] = total_gb
                    logger.debug(
                        "Manila quota fallback: %d shares, %d GB",
                        result["shares"]["in_use"],
                        result["gigabytes"]["in_use"],
                    )
            except Exception:
                logger.debug("Manila quota fallback 조회 실패", exc_info=True)

        return result
    except Exception:
        if strict:
            raise
        import logging as _logging

        _logging.getLogger(__name__).warning("Manila 파일 스토리지 quota 조회 실패", exc_info=True)
        return {
            key: {"limit": -1, "in_use": 0}
            for key in ["shares", "gigabytes", "share_networks", "share_groups", "snapshot_gigabytes"]
        }


def _infer_supported_protocols(name: str, extra_specs: dict) -> list[str]:
    """share_type 의 extra_specs / 이름으로 지원 프로토콜을 추정.

    1순위: extra_specs.storage_protocol (Manila 가 명시)
    2순위: vendor_name / share_backend_name 패턴 매칭
    추정 실패 시 빈 리스트 → 프론트는 fallback 으로 모든 옵션 노출.
    """
    proto = extra_specs.get("storage_protocol") or extra_specs.get("share_backend_name") or ""
    proto = str(proto).upper()
    if proto in {"CEPHFS", "NFS", "CIFS", "GLUSTERFS"}:
        return [proto]

    # vendor / backend / 타입 이름으로 패턴 매칭
    haystack = " ".join(
        str(v)
        for v in (
            extra_specs.get("vendor_name", ""),
            extra_specs.get("share_backend_name", ""),
            name,
        )
    ).lower()
    if "ceph" in haystack:
        return ["CEPHFS"]
    if any(k in haystack for k in ("nfs", "generic", "netapp", "glusterfs")):
        return ["NFS"]
    return []


def list_share_types(conn) -> list[dict]:
    """Manila에서 사용 가능한 share type 목록 조회.

    각 type 의 extra_specs 와 추정된 supported_protocols 를 함께 반환해
    프론트엔드가 share_type 선택 시 호환되는 share_proto 만 노출할 수 있게 한다.
    """
    client = get_client(conn)
    data = client.get("types")
    result: list[dict] = []
    for t in data.get("share_types", []):
        extra_specs = t.get("extra_specs") or {}
        result.append(
            {
                "id": t["id"],
                "name": t["name"],
                "is_default": t.get("share_type_access:is_public", True),
                "extra_specs": extra_specs,
                "supported_protocols": _infer_supported_protocols(t["name"], extra_specs),
            }
        )
    return result


def extract_manila_error(e: httpx.HTTPStatusError) -> tuple[int, str]:
    """Manila API 의 HTTPStatusError 에서 (status_code, message) 추출.

    Manila 응답 본문 예: {"badRequest": {"code": 400, "message": "..."}}
    JSON 파싱 실패 시 plain text 또는 Exception str 로 fallback.
    """
    status = e.response.status_code
    try:
        body = e.response.json()
        if isinstance(body, dict) and body:
            first = next(iter(body.values()))
            if isinstance(first, dict) and isinstance(first.get("message"), str):
                return status, first["message"]
    except Exception:
        pass
    text = (e.response.text or "").strip()
    return status, text or str(e)


def format_error_message(exc: httpx.HTTPStatusError) -> str:
    """HTTPStatusError에서 사람이 읽을 수 있는 메시지 반환.

    create_file_storage()가 "share type not found" 404를 enrichment한 경우
    exc.args[0]에 가용 type 목록이 포함됨 → 그 쪽을 우선 반환.
    그 외에는 extract_manila_error()로 응답 본문 메시지를 반환.
    """
    if exc.args and str(exc.args[0]).startswith("Manila API"):
        return str(exc.args[0])
    status, message = extract_manila_error(exc)
    return f"Manila API {status}: {message}"


def list_share_networks(conn) -> list[dict]:
    """Manila에서 사용 가능한 share network 목록 조회."""
    client = get_client(conn)
    data = client.get("share-networks/detail")
    return [
        {
            "id": net["id"],
            "name": net.get("name", ""),
            "neutron_net_id": net.get("neutron_net_id"),
            "neutron_subnet_id": net.get("neutron_subnet_id"),
            "network_type": net.get("network_type"),
            "status": net.get("status", ""),
            "created_at": net.get("created_at"),
        }
        for net in data.get("share_networks", [])
    ]


def get_share_network(conn, share_network_id: str) -> dict:
    """Share network 상세 조회."""
    client = get_client(conn)
    data = client.get(f"share-networks/{share_network_id}")
    net = data.get("share_network", data)
    return {
        "id": net["id"],
        "name": net.get("name", ""),
        "description": net.get("description", ""),
        "neutron_net_id": net.get("neutron_net_id"),
        "neutron_subnet_id": net.get("neutron_subnet_id"),
        "network_type": net.get("network_type"),
        "status": net.get("status", ""),
        "created_at": net.get("created_at"),
        "security_service_ids": [ss.get("id", "") for ss in net.get("security_services", [])]
        if net.get("security_services")
        else [],
    }


def create_share_network(
    conn,
    name: str,
    neutron_net_id: str,
    neutron_subnet_id: str,
    description: str = "",
) -> dict:
    """Share network 생성."""
    client = get_client(conn)
    body = {
        "share_network": {
            "name": name,
            "description": description,
            "neutron_net_id": neutron_net_id,
            "neutron_subnet_id": neutron_subnet_id,
        }
    }
    return client.post("share-networks", body)["share_network"]


def delete_share_network(conn, share_network_id: str) -> None:
    """Share network 삭제."""
    client = get_client(conn)
    client.delete(f"share-networks/{share_network_id}")


def add_security_service_to_network(conn, share_network_id: str, security_service_id: str) -> dict:
    """Share network에 보안 서비스 연결."""
    client = get_client(conn)
    body = {"add_security_service": {"security_service_id": security_service_id}}
    return client.post(f"share-networks/{share_network_id}/action", body)


def remove_security_service_from_network(conn, share_network_id: str, security_service_id: str) -> dict:
    """Share network에서 보안 서비스 제거."""
    client = get_client(conn)
    body = {"remove_security_service": {"security_service_id": security_service_id}}
    return client.post(f"share-networks/{share_network_id}/action", body)


# ---------------------------------------------------------------------------
# Security Services
# ---------------------------------------------------------------------------


def list_security_services(conn) -> list[dict]:
    """Manila security service 목록 조회."""
    client = get_client(conn)
    data = client.get("security-services/detail")
    return [
        {
            "id": ss["id"],
            "name": ss.get("name", ""),
            "description": ss.get("description", ""),
            "type": ss.get("type", ""),
            "dns_ip": ss.get("dns_ip"),
            "server": ss.get("server"),
            "domain": ss.get("domain"),
            "status": ss.get("status", ""),
            "created_at": ss.get("created_at"),
        }
        for ss in data.get("security_services", [])
    ]


def create_security_service(
    conn,
    type: str,
    name: str,
    description: str = "",
    dns_ip: str = "",
    server: str = "",
    domain: str = "",
    user: str = "",
    password: str = "",
) -> dict:
    """Manila security service 생성."""
    client = get_client(conn)
    body: dict = {
        "type": type,
        "name": name,
    }
    if description:
        body["description"] = description
    if dns_ip:
        body["dns_ip"] = dns_ip
    if server:
        body["server"] = server
    if domain:
        body["domain"] = domain
    if user:
        body["user"] = user
    if password:
        body["password"] = password
    return client.post("security-services", {"security_service": body})["security_service"]


def delete_security_service(conn, security_service_id: str) -> None:
    """Manila security service 삭제."""
    client = get_client(conn)
    client.delete(f"security-services/{security_service_id}")


def create_file_storage(
    conn,
    name: str,
    size_gb: int,
    share_network_id: str,
    share_type: str = "cephfstype",
    share_proto: str = "CEPHFS",
    metadata: dict | None = None,
) -> FileStorageInfo:
    client = get_client(conn)
    proto_upper = share_proto.upper()
    share_body: dict = {
        "name": name,
        "share_proto": proto_upper,
        "size": size_gb,
        "share_type": share_type,
        "metadata": metadata or {},
    }
    # CephFS native forbids a network; NFS requires the selected type's DHSS
    # setting. Never guess on a failed lookup: DHSS=False rejects a network.
    _include_share_network = bool(share_network_id) and proto_upper != "CEPHFS"
    if _include_share_network:
        if not share_type:
            raise RuntimeError("Cannot determine share type DHSS mode without a share type")
        try:
            types = list_share_types(conn)
        except Exception as exc:
            raise RuntimeError(f"Cannot determine share type DHSS mode: {share_type}") from exc
        matched = next((item for item in types if item["name"] == share_type), None)
        dhss = str((matched or {}).get("extra_specs", {}).get("driver_handles_share_servers", "")).lower()
        if dhss not in {"true", "false"}:
            raise RuntimeError(f"Cannot determine share type DHSS mode: {share_type}")
        if dhss == "false":
            logger.warning(
                "create_file_storage: share type '%s' 는 DHSS=False 이므로 share_network_id '%s' 를 무시합니다.",
                share_type,
                share_network_id,
            )
            _include_share_network = False
    if _include_share_network:
        share_body["share_network_id"] = share_network_id
    body = {"share": share_body}
    try:
        data = client.post("shares", body)["share"]
    except httpx.HTTPStatusError as e:
        status, message = extract_manila_error(e)
        if status == 404 and "share type" in message.lower():
            # 가용 share type 목록을 조회해 에러 메시지에 첨부 (진단 지원)
            try:
                available = [t["name"] for t in list_share_types(conn)]
            except Exception:
                available = []
            hint = f" 가용 share type: {available}" if available else ""
            raise httpx.HTTPStatusError(
                f"Manila API {status}: {message}{hint}",
                request=e.request,
                response=e.response,
            ) from e
        raise
    file_storage_id = data["id"]

    # available 상태까지 폴링
    for _ in range(60):
        time.sleep(5)
        info = client.get(f"shares/{file_storage_id}")["share"]
        if info["status"] == "available":
            break
        if info["status"] == "error":
            # 실패 원인 조회 (Manila Messages API, best-effort)
            failure_reason = ""
            try:
                msgs = client.get("messages", params={"resource_id": file_storage_id}).get("messages", [])
                if msgs:
                    failure_reason = ": " + msgs[0].get("user_message", "")
            except Exception:
                pass
            # error 상태 share 정리 (잔류 방지, best-effort)
            try:
                client.delete(f"shares/{file_storage_id}")
            except Exception:
                pass
            raise RuntimeError(f"파일 스토리지 생성 실패 (error 상태){failure_reason} [{file_storage_id}]")

    return _parse_file_storage(client.get(f"shares/{file_storage_id}")["share"])


def delete_file_storage(conn, file_storage_id: str) -> None:
    client = get_client(conn)
    client.delete(f"shares/{file_storage_id}")


def _list_share_messages(client: ManilaClient, file_storage_id: str) -> list[dict]:
    try:
        return client.get("messages", params={"resource_id": file_storage_id}).get("messages", [])
    except Exception:
        return []


def _list_share_instances(client: ManilaClient, file_storage_id: str) -> list[dict]:
    try:
        return client.get(f"shares/{file_storage_id}/instances").get("share_instances", [])
    except Exception:
        pass

    try:
        instances = client.get("share_instances").get("share_instances", [])
    except Exception:
        return []
    return [inst for inst in instances if inst.get("share_id") == file_storage_id]


def _get_share_type_extra_specs(conn, share_type_name: str | None) -> dict:
    if not share_type_name:
        return {}
    try:
        share_type = next((t for t in list_share_types(conn) if t.get("name") == share_type_name), None)
    except Exception:
        return {}
    return (share_type or {}).get("extra_specs") or {}


def _message_text(message: dict) -> str:
    parts: list[str] = []
    for value in message.values():
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _matched_backend_missing_message(messages: list[dict]) -> str | None:
    needles = ("enoent", "no such file or directory", "not found")
    for message in messages:
        text = _message_text(message)
        lower = text.lower()
        if any(needle in lower for needle in needles):
            return text
    return None


def diagnose_file_storage_delete_issue(conn, file_storage_id: str) -> FileStorageDeleteDiagnostic:
    fs = get_file_storage(conn, file_storage_id)
    client = get_client(conn)
    messages = _list_share_messages(client, file_storage_id)
    instances = _list_share_instances(client, file_storage_id)
    share_instance_ids = [str(inst["id"]) for inst in instances if inst.get("id")]
    if not share_instance_ids:
        share_instance_ids = [
            detail.share_instance_id for detail in fs.export_location_details if detail.share_instance_id
        ]

    base = {
        "file_storage_id": file_storage_id,
        "status": fs.status,
        "share_proto": fs.share_proto,
        "share_type_name": fs.share_type_name,
        "share_network_id": fs.share_network_id,
        "share_instance_ids": share_instance_ids,
    }

    extra_specs = _get_share_type_extra_specs(conn, fs.share_type_name)
    dhss = str(extra_specs.get("driver_handles_share_servers", "")).lower()
    if fs.share_network_id and dhss == "false":
        return FileStorageDeleteDiagnostic(
            **base,
            root_cause_code="dhss_false_share_network_mismatch",
            confidence="high",
            summary="DHSS=False share type에 share_network_id가 포함되어 Manila 드라이버가 작업을 거부한 것으로 판단됩니다.",
            evidence=[
                f"share_type_name={fs.share_type_name}",
                "driver_handles_share_servers=False",
                f"share_network_id={fs.share_network_id}",
            ],
            recommended_action="backend export/subvolume이 없는 것을 확인한 뒤 관리자 강제 삭제로 Manila share/instance DB 레코드를 제거하고, 동일 share type으로 재생성할 때 share_network_id를 제거하세요.",
            force_delete_available=True,
        )

    matched_message = _matched_backend_missing_message(messages)
    if fs.status in {"error_deleting", "deleting"} and matched_message:
        return FileStorageDeleteDiagnostic(
            **base,
            root_cause_code="backend_missing_after_failed_create_or_delete",
            confidence="high",
            summary="Manila DB 레코드는 남아 있지만 backend export/subvolume이 이미 없어서 삭제가 실패한 것으로 판단됩니다.",
            evidence=[f"status={fs.status}", f"manila_message={matched_message}"],
            recommended_action="관리자 강제 삭제로 Manila share/instance DB 레코드를 제거하세요.",
            force_delete_available=True,
        )

    if fs.status == "error":
        return FileStorageDeleteDiagnostic(
            **base,
            root_cause_code="unknown",
            confidence="medium",
            summary="Share가 error 상태입니다. 일반 삭제를 먼저 시도할 수 있지만 실패하면 관리자 강제 삭제가 필요할 수 있습니다.",
            evidence=[f"status={fs.status}"],
            recommended_action="일반 삭제가 실패했거나 backend 리소스 부재가 확인되었다면 관리자 강제 삭제로 Manila 레코드를 제거하세요.",
            force_delete_available=True,
        )

    if fs.status in {"available", "inactive"}:
        return FileStorageDeleteDiagnostic(
            **base,
            root_cause_code="normal_delete_possible",
            confidence="medium",
            summary="현재 상태에서는 일반 삭제 경로를 먼저 사용하세요.",
            evidence=[f"status={fs.status}"],
            recommended_action="상단의 파일 스토리지 삭제 버튼으로 일반 삭제를 먼저 실행하세요.",
            force_delete_available=False,
        )

    return FileStorageDeleteDiagnostic(
        **base,
        root_cause_code="unknown",
        confidence="low",
        summary="자동 진단으로 정확한 원인을 특정하지 못했습니다.",
        evidence=[],
        recommended_action="Manila messages/logs와 backend export 존재 여부를 확인한 뒤, backend 리소스가 이미 없거나 일반 삭제가 실패한 경우에만 관리자 강제 삭제를 사용하세요.",
        force_delete_available=fs.status in {"error", "error_deleting", "deleting"},
    )


def force_delete_file_storage(conn, file_storage_id: str) -> str:
    client = get_client(conn)
    try:
        # Manila API force-delete action: https://docs.openstack.org/api-ref/shared-file-system/
        client.post(f"shares/{file_storage_id}/action", {"force_delete": None})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return "already_deleted"
        raise
    return "force_delete_submitted"


def list_file_storages(
    conn,
    metadata_filter: dict | None = None,
    all_tenants: bool = False,
    caller_project_id: str | None = None,
    include_public: bool = False,
) -> list[FileStorageInfo]:
    client = get_client(conn)

    shares_by_id: dict[str, FileStorageInfo] = {}

    def _fetch(params: dict) -> None:
        try:
            data = client.get("shares/detail", params=params or None)["shares"]
            for s in data:
                fs = _parse_file_storage(s)
                shares_by_id[fs.id] = fs
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                logger.warning(f"Manila shares/detail 400 (파일 스토리지 없음으로 추정): {e}")
            else:
                raise

    params: dict = {}
    if all_tenants:
        params["all_tenants"] = "1"
    _fetch(params)

    # prebuilt share는 다른 프로젝트 소유일 수 있으므로 public share를 별도 조회하여 합침
    if include_public and not all_tenants:
        _fetch({"is_public": "true"})

    file_storages = list(shares_by_id.values())
    if metadata_filter:
        file_storages = [s for s in file_storages if all(s.metadata.get(k) == v for k, v in metadata_filter.items())]
    if caller_project_id is not None:
        # 다른 프로젝트 소유 share는 is_public=True인 경우만 노출
        file_storages = [
            s
            for s in file_storages
            if s.is_public or s.metadata.get("union_project_id") in (caller_project_id, None, "")
        ]
    return file_storages


def get_file_storage(conn, file_storage_id: str, resolve_user: bool = False) -> FileStorageInfo:
    """share 상세 조회.

    resolve_user=True 시 Keystone에서 user_id → user_name 해석을 시도한다(best-effort).
    export_locations는 별도 서브리소스를 통해 병합한다(Manila 2.9+ 인라인 제거 대응).
    """
    client = get_client(conn)
    data = client.get(f"shares/{file_storage_id}")["share"]

    # export_locations 별도 조회 (Manila 2.9+에서 인라인 없음)
    try:
        export_details = get_export_location_details(conn, file_storage_id)
    except Exception:
        export_details = []

    fs = _parse_file_storage(data, export_detail_list=export_details)

    # 생성자 이름 해석 (best-effort)
    if resolve_user and fs.user_id:
        try:
            from app.services import keystone

            user_info = keystone.get_user(conn, fs.user_id)
            resolved_name = user_info.get("name") or None
            if resolved_name:
                fs = fs.model_copy(update={"user_name": resolved_name})
        except Exception:
            pass  # user_name은 None 유지 — 프론트가 user_id로 fallback

    return fs


# ---------------------------------------------------------------------------
# Access Rule (CephX)
# ---------------------------------------------------------------------------


def _build_nfs_access_metadata(root_squash: bool = True, sec_flavor: str = "sys") -> dict:
    """NFS access rule에 첨부할 보안 메타데이터 빌드.

    root_squash: True 시 Manila가 NFS 서버에 root→nobody 매핑을 적용하도록 요청.
    sec_flavor: NFS 인증 방식 — "sys"(기본, UNIX UID/GID) 또는 "krb5"(Kerberos).
    Manila API 2.65+를 사용하므로 메타데이터 필드는 표준으로 지원된다.
    """
    meta: dict = {}
    if root_squash:
        meta["root_squash"] = "True"
    if sec_flavor:
        meta["auth_flavor_list"] = [sec_flavor]
    return meta


def create_access_rule(
    conn,
    file_storage_id: str,
    access_to: str,
    access_level: str = "ro",  # "ro" | "rw"
    access_type: str = "cephx",  # "cephx" | "ip"
    metadata: dict | None = None,  # NFS access rule 보안 메타데이터 (IP 타입에만 유효)
) -> dict:
    """
    접근 규칙 생성.
    - CephFS: access_type="cephx", access_to=cephx_id
    - NFS: access_type="ip", access_to=IP/CIDR, metadata={root_squash, auth_flavor_list}
    반환: { access_id, access_key, access_to, access_level }
    """
    client = get_client(conn)
    allow_access: dict = {
        "access_type": access_type,
        "access_to": access_to,
        "access_level": access_level,
    }
    if metadata and access_type == "ip":
        allow_access["metadata"] = metadata
    body = {"allow_access": allow_access}
    data = client.post(f"shares/{file_storage_id}/action", body)["access"]

    # access_key 조회 (CephX만 해당, IP 규칙은 없음)
    access_key = ""
    if access_type == "cephx":
        try:
            from app.config import get_settings as _get_settings

            _timeout = _get_settings().manila_cephx_key_timeout_seconds
        except Exception:
            _timeout = 300
        try:
            access_key = _get_access_key(client, file_storage_id, data["id"], _timeout)
        except RuntimeError:
            # key 발급 타임아웃 → 생성된 고아 rule 자동 정리 후 예외 재발생
            try:
                _revoke_access_rule_raw(client, file_storage_id, data["id"])
            except Exception:
                pass
            raise
    return {
        "id": data["id"],
        "access_type": access_type,
        "access_to": access_to,
        "access_level": data["access_level"],
        "access_key": access_key or None,
        "state": data.get("state", "new"),
    }


def revoke_access_rule(conn, file_storage_id: str, access_id: str) -> None:
    client = get_client(conn)
    body = {"deny_access": {"access_id": access_id}}
    client.post(f"shares/{file_storage_id}/action", body)


def rotate_cephx_access_rule(conn, file_storage_id: str, access_id: str) -> dict:
    """CephX access rule 교체 (revoke 후 동일 access_to/level로 재생성).

    Manila update-access API는 backend별 비호환이므로 revoke+create 방식을 사용한다.
    반환: { access_id, access_key, access_to, access_level }
    """
    # 기존 rule 조회
    rules = list_access_rules(conn, file_storage_id)
    target = next((r for r in rules if r.get("id") == access_id), None)
    if target is None:
        raise KeyError(f"access_id {access_id}를 찾을 수 없습니다")
    access_to = target["access_to"]
    access_level = target["access_level"]

    # revoke 후 재생성
    revoke_access_rule(conn, file_storage_id, access_id)
    return create_access_rule(conn, file_storage_id, access_to, access_level, "cephx")


def list_access_rules(conn, file_storage_id: str) -> list[dict]:
    client = get_client(conn)
    # API v2.45+: use share-access-rules endpoint instead of action
    data = client.get(f"share-access-rules?share_id={file_storage_id}")
    rules = data.get("access_rules", [])
    if rules:
        return rules
    # 일부 Manila 구성에서 share-access-rules가 빈 결과를 반환하는 경우 legacy action API fallback
    try:
        data2 = client.post(f"shares/{file_storage_id}/action", {"os-list-access": {}}, log_errors=False)
        legacy = data2.get("access_list", [])
        if legacy:
            logger.warning(
                "share-access-rules returned empty; os-list-access fallback returned %d rules",
                len(legacy),
            )
        return legacy
    except Exception as e:
        logger.debug("os-list-access fallback failed: %s", e)
        return rules


def get_export_locations(conn, file_storage_id: str) -> list[str]:
    """CephFS export path 목록 반환 (예: '192.168.1.10:6789,... :/')."""
    client = get_client(conn)
    data = client.get(f"shares/{file_storage_id}/export_locations")
    locations = data.get("export_locations", [])
    return [loc["path"] for loc in locations if loc.get("is_admin_only") is False]


def get_export_location_details(conn, file_storage_id: str) -> list[dict]:
    """export_locations 서브리소스에서 상세 정보 반환 (path, preferred, share_instance_id).

    Manila 2.9+에서 share 인라인 뷰에 export_locations가 포함되지 않으므로
    상세 조회 시 이 함수로 별도 취득한다.
    is_admin_only=True인 항목은 제외한다.
    """
    client = get_client(conn)
    data = client.get(f"shares/{file_storage_id}/export_locations")
    return [
        {
            "path": loc["path"],
            "preferred": bool(loc.get("preferred", False)),
            "share_instance_id": loc.get("share_instance_id"),
        }
        for loc in data.get("export_locations", [])
        if loc.get("is_admin_only") is False
    ]


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------


def _revoke_access_rule_raw(client: ManilaClient, file_storage_id: str, access_id: str) -> None:
    """client 객체만 있을 때 access rule을 직접 revoke (create_access_rule 내부 rollback 전용)."""
    client.post(f"shares/{file_storage_id}/action", {"deny_access": {"access_id": access_id}})


def _get_access_key(client: ManilaClient, file_storage_id: str, access_id: str, timeout_seconds: int = 300) -> str:
    """access rule 에서 CephX secret key 추출 (Manila API v2.45+).

    Manila는 access rule 생성 직후 key가 빈 문자열일 수 있으므로 timeout_seconds 동안 재시도.
    모두 실패하면 RuntimeError 발생 — 빈 key로 cloud-init에 주입되면 CephFS 마운트가
    반드시 실패하므로 호출부에서 인지할 수 있도록 예외를 선호한다.
    """
    import logging as _logging

    _log = _logging.getLogger(__name__)
    max_attempts = max(1, timeout_seconds // 3)
    # ~30초 간격으로 INFO 진행 로그를 찍어 hang 위치를 가시화한다.
    info_interval = max(1, max_attempts // 10)
    last_state = "?"
    for attempt in range(max_attempts):
        data = client.get(f"share-access-rules?share_id={file_storage_id}")
        rules = data.get("access_rules", [])
        for rule in rules:
            if rule["id"] == access_id:
                last_state = rule.get("state", "?")
                if rule.get("access_key"):
                    if attempt > 0:
                        _log.info(
                            "[manila] CephX key 획득 — %ds 경과, rule state=%s, access_id=%s",
                            attempt * 3,
                            last_state,
                            access_id,
                        )
                    return rule["access_key"]
                break
        if attempt > 0 and attempt % info_interval == 0:
            _log.info(
                "[manila] CephX key 폴링 진행 %d/%d (~%ds 경과, rule state=%s, access_id=%s)",
                attempt,
                max_attempts,
                attempt * 3,
                last_state,
                access_id,
            )
        else:
            _log.debug(
                "[manila] CephX key 미할당 %d/%d, rule state=%s",
                attempt + 1,
                max_attempts,
                last_state,
            )
        time.sleep(3)
    raise RuntimeError(
        f"CephX access key 발급 타임아웃 (access_id={access_id}, share={file_storage_id}, "
        f"last_state={last_state}). Manila가 {timeout_seconds}초 내에 key를 할당하지 못했습니다."
    )


def _parse_file_storage(data: dict, export_detail_list: list[dict] | None = None) -> FileStorageInfo:
    """share dict를 FileStorageInfo로 변환.

    export_detail_list: get_export_location_details()로 별도 취득한 상세 목록.
                        None이면 인라인 data["export_locations"]에서 경로만 추출한다
                        (목록 뷰용 — Manila 2.9+에서는 항상 빈 리스트가 된다).
    """
    meta = data.get("metadata", {}) or {}

    if export_detail_list is not None:
        # 상세 조회 경로: 별도 취득한 dict 목록 사용
        locations = [loc["path"] for loc in export_detail_list]
        from app.models.storage import ExportLocation

        export_location_details = [
            ExportLocation(
                path=loc["path"],
                preferred=bool(loc.get("preferred", False)),
                share_instance_id=loc.get("share_instance_id"),
            )
            for loc in export_detail_list
        ]
    else:
        # 목록 조회 경로: 인라인 export (Manila 2.9+에서는 항상 비어 있음)
        locations = []
        for loc in data.get("export_locations", []):
            if isinstance(loc, dict):
                locations.append(loc.get("path", ""))
            elif isinstance(loc, str):
                locations.append(loc)
        export_location_details = []

    share_proto = data.get("share_proto", "CEPHFS")

    # NFS export location: NFS 프로토콜인 경우 첫 번째 export 경로 사용
    nfs_export_location = None
    if share_proto == "NFS":
        nfs_export_location = locations[0] if locations else None

    return FileStorageInfo(
        id=data["id"],
        name=data.get("name", ""),
        status=data["status"],
        size=data["size"],
        share_proto=share_proto,
        export_locations=locations,
        metadata=meta,
        project_id=data.get("project_id"),
        created_at=str(data["created_at"]) if data.get("created_at") else None,
        nfs_export_location=nfs_export_location,
        is_public=bool(data.get("is_public", False)),
        library_name=meta.get("union_library"),
        library_version=meta.get("union_version"),
        built_at=meta.get("union_built_at"),
        # 확장 필드
        progress=data.get("progress"),
        user_id=data.get("user_id"),
        access_rules_status=data.get("access_rules_status"),
        host=data.get("host"),
        availability_zone=data.get("availability_zone"),
        share_type_name=data.get("share_type_name"),
        share_network_id=data.get("share_network_id"),
        export_location_details=export_location_details,
    )


# ---------------------------------------------------------------------------
# NFS access rule 관리
# ---------------------------------------------------------------------------


def ensure_nfs_access_rule(
    conn,
    file_storage_id: str,
    access_to: str,
    access_level: str = "rw",
    root_squash: bool = True,
    sec_flavor: str = "sys",
    extra_metadata: dict | None = None,
) -> dict:
    """
    NFS access rule이 없으면 생성하고, 이미 있으면 기존 rule을 반환.
    access_to: IP 주소 또는 CIDR (예: "192.168.1.100" 또는 "10.0.0.0/24")
    root_squash: NFS root → nobody 매핑 강제 여부 (보안 권장: True)
    sec_flavor: NFS 인증 flavor — "sys" 또는 "krb5"
    extra_metadata: root_squash/sec_flavor 외에 추가로 붙일 Manila metadata (예: union_grant_project)
    """
    # 기존 access rule 조회
    existing_rules = list_access_rules(conn, file_storage_id)
    for rule in existing_rules:
        if (
            rule.get("access_type") == "ip"
            and rule.get("access_to") == access_to
            and rule.get("access_level") == access_level
            and rule.get("state") in ("active", "new")
        ):
            logger.info(f"NFS access rule 이미 존재: {access_to} ({rule.get('id')})")
            return {
                "access_id": rule["id"],
                "access_key": "",
                "access_to": access_to,
                "access_level": access_level,
            }

    # 새로 생성 (보안 메타데이터 포함)
    meta = _build_nfs_access_metadata(root_squash=root_squash, sec_flavor=sec_flavor)
    if extra_metadata:
        meta.update(extra_metadata)
    result = create_access_rule(
        conn,
        file_storage_id=file_storage_id,
        access_to=access_to,
        access_level=access_level,
        access_type="ip",
        metadata=meta or None,
    )
    # create_access_rule 반환은 access_id 형식이 기본이다. 구형 호출자/테스트 호환을 위해 id도 허용.
    access_id = result.get("access_id") or result.get("id")
    if not access_id:
        raise KeyError("access_id")
    return {
        "access_id": access_id,
        "access_key": result.get("access_key"),
        "access_to": access_to,
        "access_level": result["access_level"],
    }


def set_share_public(conn, file_storage_id: str, is_public: bool = True) -> dict:
    """Manila share의 공개 범위 설정 (다른 프로젝트 접근 허용)."""
    client = get_client(conn)
    body = {"share": {"is_public": is_public}}
    return client.put(f"shares/{file_storage_id}", body)


def get_nfs_export_location(conn, file_storage_id: str) -> str | None:
    """NFS share의 export location을 반환. CephFS share이면 None."""
    info = get_file_storage(conn, file_storage_id)
    if info.share_proto != "NFS":
        return None
    locations = get_export_locations(conn, file_storage_id)
    return locations[0] if locations else None


# ---------------------------------------------------------------------------
# Manila share 메타데이터 관리
# ---------------------------------------------------------------------------


def update_share_metadata(conn, file_storage_id: str, metadata: dict) -> dict:
    """Manila share 메타데이터 업데이트 (POST /shares/{id}/metadata)."""
    client = get_client(conn)
    body = {"metadata": metadata}
    return client.post(f"shares/{file_storage_id}/metadata", body)


# ---------------------------------------------------------------------------
# Manila share snapshot 관리
# ---------------------------------------------------------------------------


def create_share_snapshot(
    conn,
    file_storage_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict:
    """Manila share 스냅샷 생성."""
    client = get_client(conn)
    body: dict = {"snapshot": {"share_id": file_storage_id}}
    if name:
        body["snapshot"]["name"] = name
    if description:
        body["snapshot"]["description"] = description
    return client.post("snapshots", body)["snapshot"]


def list_share_snapshots(
    conn,
    file_storage_id: str | None = None,
    all_tenants: bool = False,
) -> list[dict]:
    """Manila share 스냅샷 목록 조회.

    `all_tenants=True`는 admin scope에서 전(全) 프로젝트 스냅샷 합산용.
    """
    client = get_client(conn)
    params: dict = {}
    if file_storage_id:
        params["share_id"] = file_storage_id
    if all_tenants:
        params["all_tenants"] = "1"
    data = client.get("snapshots/detail", params=params or None)
    return data.get("snapshots", [])


def delete_share_snapshot(conn, snapshot_id: str) -> None:
    """Manila share 스냅샷 삭제."""
    client = get_client(conn)
    client.delete(f"snapshots/{snapshot_id}")


def get_share_snapshot(conn, snapshot_id: str) -> dict:
    """Manila share 스냅샷 단건 조회."""
    client = get_client(conn)
    return client.get(f"snapshots/{snapshot_id}")["snapshot"]


def revert_to_snapshot(conn, share_id: str, snapshot_id: str) -> None:
    """share를 특정 스냅샷 시점으로 복원 (Manila microversion 2.27+)."""
    client = get_client(conn)
    client.post(f"shares/{share_id}/action", {"revert": {"snapshot_id": snapshot_id}})


# ---------------------------------------------------------------------------
# 하위 호환 alias (기존 코드와 호환 유지)
# ---------------------------------------------------------------------------
get_share_quota = get_file_storage_quota
create_share = create_file_storage
delete_share = delete_file_storage
list_shares = list_file_storages
get_share = get_file_storage
