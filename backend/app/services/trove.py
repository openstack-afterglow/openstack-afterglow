"""Trove (Database as a Service) 서비스 래퍼.

openstacksdk의 conn.database 프록시를 사용.
서비스가 없거나 오류 시 빈 목록/0을 반환하여 optional 서비스로 동작.
"""

import logging

_logger = logging.getLogger(__name__)


def _addresses_to_map(addresses_raw) -> dict[str, list[str]]:
    """Trove `addresses` 필드를 network_name → [ips] dict 로 변환.

    Trove 응답 형식 두 가지 지원:
    - dict: {"private": [{"addr": "1.2.3.4"}, ...]} (Nova 스타일)
    - list: [{"address": "1.2.3.4", "type": "private"}, ...] (Trove >= Yoga)
    """
    address_map: dict[str, list[str]] = {}
    if isinstance(addresses_raw, dict):
        for net_name, net_addrs in addresses_raw.items():
            nets: list[str] = []
            for addr in net_addrs or []:
                addr_val = addr.get("addr", "") if isinstance(addr, dict) else str(addr)
                if addr_val:
                    nets.append(addr_val)
            if nets:
                address_map[net_name] = nets
    elif isinstance(addresses_raw, list):
        for addr in addresses_raw:
            if not isinstance(addr, dict):
                continue
            addr_val = addr.get("address") or addr.get("addr") or ""
            net_name = addr.get("type") or addr.get("network") or "default"
            if addr_val:
                address_map.setdefault(net_name, []).append(addr_val)
    return address_map


def _dict_from_raw(raw: dict) -> dict:
    """Trove API instance JSON dict → 표준 dict 변환 (raw REST 응답 처리)."""
    flavor = raw.get("flavor") or {}
    volume = raw.get("volume") or {}
    links = raw.get("links") or []

    address_map = _addresses_to_map(raw.get("addresses"))

    # IP 추출: Trove는 'ip' 리스트 또는 'addresses' dict/list 반환
    ip_raw = raw.get("ip")
    if ip_raw:
        ips: list[str] = list(ip_raw) if not isinstance(ip_raw, str) else [ip_raw]
    elif address_map:
        ips = [a for addrs in address_map.values() for a in addrs]
    else:
        ips = []

    return {
        "id": raw.get("id", "") or "",
        "name": raw.get("name", "") or "",
        "status": raw.get("status", "") or "",
        "datastore": raw.get("datastore") or {},
        "flavor_id": str(flavor.get("id", "")) if isinstance(flavor, dict) else "",
        "flavor_ram": flavor.get("ram", 0) if isinstance(flavor, dict) else 0,
        "flavor_vcpus": flavor.get("vcpus", 0) if isinstance(flavor, dict) else 0,
        "size": volume.get("size", 0) if isinstance(volume, dict) else 0,
        "volume_used": round(volume.get("used", 0) or 0, 2) if isinstance(volume, dict) else 0,
        "created_at": str(raw.get("created", "") or raw.get("created_at", "") or ""),
        "updated_at": str(raw.get("updated", "") or raw.get("updated_at", "") or ""),
        "hostname": raw.get("hostname", "") or "",
        "ip": ips[0] if ips else "",
        "ips": ips,
        "address_map": address_map,
        "links": [lk.get("href", "") if isinstance(lk, dict) else str(lk) for lk in links],
    }


def _instance_to_dict(i) -> dict:
    """SDK Resource → 표준 dict (테스트 호환용 — 현 코드는 raw REST 사용)."""
    flavor = getattr(i, "flavor", {}) or {}
    volume = getattr(i, "volume", {}) or {}
    links = getattr(i, "links", []) or []

    address_map = _addresses_to_map(getattr(i, "addresses", None))

    ip_raw = getattr(i, "ip", None)
    if ip_raw:
        ips: list[str] = list(ip_raw) if not isinstance(ip_raw, str) else [ip_raw]
    elif address_map:
        ips = [a for addrs in address_map.values() for a in addrs]
    else:
        ips = []

    return {
        "id": i.id,
        "name": i.name or "",
        "status": i.status or "",
        "datastore": getattr(i, "datastore", {}) or {},
        "flavor_id": str(flavor.get("id", "")) if isinstance(flavor, dict) else "",
        "flavor_ram": flavor.get("ram", 0) if isinstance(flavor, dict) else 0,
        "flavor_vcpus": flavor.get("vcpus", 0) if isinstance(flavor, dict) else 0,
        "size": volume.get("size", 0) if isinstance(volume, dict) else 0,
        "volume_used": round(volume.get("used", 0) or 0, 2) if isinstance(volume, dict) else 0,
        "created_at": str(getattr(i, "created_at", "") or ""),
        "updated_at": str(getattr(i, "updated_at", "") or ""),
        "hostname": getattr(i, "hostname", None) or "",
        "ip": ips[0] if ips else "",
        "ips": ips,
        "address_map": address_map,
        "links": [lk.get("href", "") if isinstance(lk, dict) else str(lk) for lk in links],
    }


def list_instances(conn) -> list[dict]:
    """현재 프로젝트의 DB 인스턴스 목록 반환 (raw REST: ip/addresses 보장).

    Trove 응답의 deleted=1 행은 이미 삭제된 인스턴스이므로 UI 노출 방지를 위해 제외.
    """
    try:
        resp = conn.database.get("/instances")
        body = resp.json() if hasattr(resp, "json") else {}
        return [_dict_from_raw(raw) for raw in body.get("instances", []) if not raw.get("deleted")]
    except Exception:
        _logger.debug("Trove 인스턴스 목록 조회 실패", exc_info=True)
        return []


def list_instances_admin_all_projects(conn) -> list[dict]:
    """admin 전용: Trove /mgmt/instances 로 모든 프로젝트 DB 인스턴스 반환.

    반환 dict 에 project_id 필드 추가. mgmt API 미지원 환경에서는 빈 목록.
    deleted=1 행은 응답에서 제외 (이미 삭제된 인스턴스).
    """
    try:
        endpoint = conn.database.get_endpoint()
        resp = conn.session.get(f"{endpoint}/mgmt/instances")
        resp.raise_for_status()
        items = resp.json().get("instances", [])
    except Exception:
        _logger.warning("Trove /mgmt/instances 조회 실패", exc_info=True)
        return []

    out: list[dict] = []
    for raw in items:
        if raw.get("deleted"):
            continue
        d = _dict_from_raw(raw)
        d["project_id"] = raw.get("tenant_id", "") or ""
        out.append(d)
    return out


def topology_database_ips(conn, *, all_projects: bool = False) -> set[str]:
    """토폴로지 인스턴스를 DB 인스턴스로 표시하기 위한 Trove IP 집합 반환.

    삭제되지 않은 Trove 인스턴스의 `ips` 를 모두 합집합으로 모은다. 호출자는 이 집합에
    포함된 fixed IP 를 가진 Nova 인스턴스를 `is_database=True` 로 표시한다.

    `all_projects=True` 는 admin 토폴로지용으로 `/mgmt/instances` 전체 프로젝트 목록을 사용한다.

    Trove 는 optional 서비스이므로 카탈로그에 없거나 조회가 실패하는 것은 정상 상황이며
    오류가 아니다. 이 경우 빈 집합을 반환하고 예외를 전파하지 않는다.
    """
    try:
        instances = list_instances_admin_all_projects(conn) if all_projects else list_instances(conn)
    except Exception:
        _logger.debug("Trove 토폴로지 IP 수집 실패 (Trove 미배포는 정상)", exc_info=True)
        return set()

    ips: set[str] = set()
    for inst in instances or []:
        for ip in inst.get("ips") or []:
            # Trove 버전에 따라 `ip` 항목이 문자열이 아니라 {"address": ...} dict 일 수 있다
            # (`_addresses_to_map` 과 같은 이유). str() 로 뭉개면 Nova addr 와 절대 일치하지
            # 않으므로 dict 는 address/addr 키를 꺼내 사용한다.
            addr = ip.get("address") or ip.get("addr") or "" if isinstance(ip, dict) else ip
            if isinstance(addr, str) and addr:
                ips.add(addr)
    return ips


def count_instances(conn) -> int:
    """현재 프로젝트의 DB 인스턴스 수 반환 (deleted 행 제외).

    SDK iterator (`conn.database.instances()`) 가 deleted 행을 포함하는지 불확실하므로
    list_instances 기반으로 산정하여 목록 카운트와 항상 일치.
    """
    try:
        return len(list_instances(conn))
    except Exception:
        return 0


def get_instance(conn, instance_id: str) -> dict:
    """DB 인스턴스 상세 정보 반환 (raw REST: ip/addresses 보장).

    SDK Instance Resource 는 `ip`/`addresses` body 필드가 정의되지 않아
    attribute access 시 None 이 되는 문제 → raw REST 직접 호출.

    `deleted` 필드를 반환 dict 에 포함하여 라우터에서 404 처리 가능하도록 한다.
    """
    resp = conn.database.get(f"/instances/{instance_id}")
    body = resp.json() if hasattr(resp, "json") else {}
    raw = body.get("instance") or {}
    d = _dict_from_raw(raw)
    d["deleted"] = bool(raw.get("deleted"))
    return d


def create_instance(
    conn,
    name: str,
    flavor_id: str,
    volume_size: int,
    datastore_type: str,
    datastore_version: str,
    databases: list | None = None,
    users: list | None = None,
    restore_backup_id: str | None = None,
    availability_zone: str | None = None,
    volume_type: str | None = None,
    nics: list[str] | None = None,
    locality: str | None = None,
    configuration_id: str | None = None,
    replica_of: str | None = None,
    replica_count: int | None = None,
) -> dict:
    """DB 인스턴스 생성 (raw REST 방식으로 안정성 확보)."""
    if locality and not (replica_of or replica_count):
        _logger.warning("locality=%s 무시: replica context 없음 (standalone 인스턴스)", locality)
        locality = None

    instance_body: dict = {
        "name": name,
        "flavorRef": flavor_id,
        "volume": {"size": volume_size},
    }
    if volume_type:
        instance_body["volume"]["type"] = volume_type
    if datastore_type:
        instance_body["datastore"] = {"type": datastore_type, "version": datastore_version}
    if availability_zone:
        instance_body["availability_zone"] = availability_zone
    if nics:
        instance_body["nics"] = [{"net-id": nid} for nid in nics]
    if locality:
        instance_body["locality"] = locality
    if databases:
        instance_body["databases"] = [{"name": db} for db in databases]
    if users:
        instance_body["users"] = users
    if configuration_id:
        instance_body["configuration"] = configuration_id
    if restore_backup_id:
        instance_body["restorePoint"] = {"backupRef": restore_backup_id}
    if replica_of:
        instance_body["replica_of"] = replica_of
        if replica_count:
            instance_body["replica_count"] = replica_count

    payload = {"instance": instance_body}
    if _logger.isEnabledFor(logging.DEBUG):
        import copy

        _log_payload = copy.deepcopy(payload)
        for u in _log_payload.get("instance", {}).get("users", []):
            if "password" in u:
                u["password"] = "***"
        _logger.debug("Trove create_instance payload: %s", _log_payload)

    resp = conn.database.post("/instances", json=payload)
    status = getattr(resp, "status_code", None)
    text = (getattr(resp, "text", "") or "")[:2000]
    _logger.debug("Trove create_instance response: status=%s body=%s", status, text)

    body = resp.json() if hasattr(resp, "json") else {}
    instance_data = body.get("instance")
    if not instance_data or not instance_data.get("id"):
        fault = body.get("instanceFault") or {}
        fault_msg = str(fault.get("message", "") or "")
        import re as _re

        m = _re.search(r"\(([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\)", fault_msg)
        fault_id = m.group(1) if m else ""
        _logger.error(
            "Trove create_instance 실패 status=%s payload_keys=%s fault_id=%s body=%s",
            status,
            list(instance_body.keys()),
            fault_id,
            text,
        )
        raise RuntimeError(
            f"Trove 생성 실패 (HTTP {status})"
            + (f" — Trove fault ID: {fault_id}" if fault_id else "")
            + (f" — {fault_msg[:200]}" if fault_msg else "")
        )

    return {
        "id": instance_data.get("id", ""),
        "name": instance_data.get("name", ""),
        "status": instance_data.get("status", ""),
        "datastore": instance_data.get("datastore", {}),
        "flavor_id": (instance_data.get("flavor") or {}).get("id", flavor_id),
        "flavor_ram": (instance_data.get("flavor") or {}).get("ram", 0),
        "size": (instance_data.get("volume") or {}).get("size", volume_size),
        "created_at": str(instance_data.get("created", "") or ""),
        "hostname": instance_data.get("hostname", "") or "",
        "ip": "",
        "links": [],
    }


def delete_instance(conn, instance_id: str) -> None:
    """DB 인스턴스 삭제."""
    conn.database.delete_instance(instance_id, ignore_missing=False)


def restart_instance(conn, instance_id: str) -> None:
    """DB 인스턴스 재시작."""
    i = conn.database.get_instance(instance_id)
    i.restart(conn.database)


def enable_root(conn, instance_id: str) -> dict:
    """root 유저 활성화. {name, password} 반환."""
    i = conn.database.get_instance(instance_id)
    result = i.enable_root_user(conn.database)
    if isinstance(result, dict):
        return result
    # result 가 Resource 객체일 수 있음
    return {
        "name": getattr(result, "name", "root"),
        "password": getattr(result, "password", ""),
    }


# ---------------------------------------------------------------------------
# 데이터베이스 (인스턴스 내부) 관리
# ---------------------------------------------------------------------------


def list_databases(conn, instance_id: str) -> list[dict]:
    """인스턴스 내 데이터베이스 목록."""
    try:
        return [
            {
                "name": db.name or "",
                "character_set": getattr(db, "character_set", "utf8") or "utf8",
                "collate": getattr(db, "collate", "") or "",
            }
            for db in conn.database.databases(instance_id)
        ]
    except Exception:
        _logger.debug("Trove DB 목록 조회 실패 instance=%s", instance_id, exc_info=True)
        return []


def create_database(
    conn,
    instance_id: str,
    name: str,
    character_set: str | None = None,
    collate: str | None = None,
) -> None:
    """인스턴스 내 데이터베이스 생성 (raw REST: Trove POST /instances/{id}/databases).

    SDK Database 리소스는 _prepare_request 오버라이드가 없어 {"database": {...}} 단수
    키로 직렬화하지만, Trove API는 {"databases": [{...}]} 복수 배열을 요구한다.

    주의: openstack proxy.post 는 raise_exc=False 기본이라 4xx/5xx 도 silent 통과.
    반드시 resp.ok 를 직접 검증해야 한다.

    PostgreSQL datastore 는 MySQL 형식의 character_set/collate 를 LC_COLLATE 로 그대로
    전달해 실패하므로, 호출자가 None 을 주면 페이로드에서 제외한다 (PG 기본 locale 사용).
    """
    db: dict = {"name": name}
    if character_set:
        db["character_set"] = character_set
    if collate:
        db["collate"] = collate
    resp = conn.database.post(f"/instances/{instance_id}/databases", json={"databases": [db]})
    if not resp.ok:
        body = (getattr(resp, "text", "") or "")[:500]
        raise RuntimeError(f"Trove POST /databases status={resp.status_code} body={body}")


def delete_database(conn, instance_id: str, db_name: str) -> None:
    """인스턴스 내 데이터베이스 삭제."""
    conn.database.delete_database(db_name, instance=instance_id, ignore_missing=False)


# ---------------------------------------------------------------------------
# 유저 (인스턴스 내부) 관리
# ---------------------------------------------------------------------------


def list_users(conn, instance_id: str) -> list[dict]:
    """인스턴스 내 유저 목록 (raw REST 우선, name@host 기준 dedup)."""
    try:
        # raw REST: SDK 래핑이 host 를 누락하거나 중복 entry 를 만드는 경우 회피
        try:
            resp = conn.database.get(f"/instances/{instance_id}/users")
            body = resp.json() if hasattr(resp, "json") else {}
            raw_users = body.get("users", []) or []
            entries = [
                {
                    "name": u.get("name", "") or "",
                    "host": u.get("host", "%") or "%",
                    "databases": u.get("databases", []) or [],
                }
                for u in raw_users
                if u.get("name")
            ]
        except Exception:
            entries = [
                {
                    "name": u.name or "",
                    "host": getattr(u, "host", "%") or "%",
                    "databases": getattr(u, "databases", []) or [],
                }
                for u in conn.database.users(instance_id)
            ]

        # dedup: (name, host) 동일 entry 는 1개로 (Trove 가 동일 user 중복 반환하는 경우 방어)
        seen: dict[tuple[str, str], dict] = {}
        for e in entries:
            key = (e["name"], e["host"])
            if key not in seen:
                seen[key] = e
        return list(seen.values())
    except Exception:
        _logger.debug("Trove 유저 목록 조회 실패 instance=%s", instance_id, exc_info=True)
        return []


def create_user(
    conn,
    instance_id: str,
    name: str,
    password: str,
    host: str = "%",
    databases: list[str] | None = None,
) -> None:
    """인스턴스 내 유저 생성 (raw REST: Trove POST /instances/{id}/users)."""
    user: dict = {"name": name, "password": password, "host": host}
    if databases:
        user["databases"] = [{"name": db} for db in databases]
    conn.database.post(f"/instances/{instance_id}/users", json={"users": [user]})


def delete_user(conn, instance_id: str, username: str, host: str = "%") -> None:
    """인스턴스 내 유저 삭제 (raw REST: name@host 식별).

    Trove user identity 는 name@host 조합이므로 host 가 다르면 다른 유저.
    SDK delete_user 는 host 파라미터를 받지 않아 동명 다른 host 유저 구분 불가 → raw REST.
    """
    from urllib.parse import quote

    user_id = quote(f"{username}@{host}", safe="")
    conn.database.delete(f"/instances/{instance_id}/users/{user_id}")


# ---------------------------------------------------------------------------
# 플레이버 / 데이터스토어
# ---------------------------------------------------------------------------


_ALLOWED_DB_FLAVORS = {"cpu.2c_2g", "cpu.4c_8g", "cpu.8c_16g", "cpu.8c_32g"}


def list_flavors(conn) -> list[dict]:
    """DB 플레이버 목록 (허용된 flavor만 반환).

    openstacksdk Flavor ORM 이 일부 환경에서 id 를 None 으로 반환해
    flavorRef 에 name 이 전송되는 문제 → raw REST 로 숫자 id 를 직접 파싱.
    """
    try:
        resp = conn.database.get("/flavors")
        body = resp.json() if hasattr(resp, "json") else {}
        result: list[dict] = []
        for f in body.get("flavors", []):
            name = f.get("name", "") or ""
            if name not in _ALLOWED_DB_FLAVORS:
                continue
            raw_id = f.get("id") or f.get("str_id")
            if raw_id in (None, ""):
                continue
            result.append(
                {
                    "id": str(raw_id),
                    "name": name,
                    "ram": f.get("ram", 0) or 0,
                    "vcpus": f.get("vcpus", 0) or 0,
                    "disk": f.get("disk", 0) or 0,
                }
            )
        return result
    except Exception:
        _logger.debug("Trove 플레이버 목록 조회 실패", exc_info=True)
        return []


def list_datastores(conn) -> list[dict]:
    """데이터스토어 목록 (raw REST).

    name/version 이 빈 문자열이면 select value 가 비어 form validation 실패 →
    이름 없는 datastore/version 은 응답에서 제외.
    """
    try:
        resp = conn.database.get("/datastores")
        body = resp.json() if hasattr(resp, "json") else {}
        datastores_raw = body.get("datastores", [])
        result = []
        for ds in datastores_raw:
            ds_name = ds.get("name", "") or ""
            if not ds_name:
                continue
            versions = []
            for v in ds.get("versions", []):
                v_name = v.get("name", "") or v.get("version", "") or ""
                if not v_name:
                    continue
                versions.append({"id": str(v.get("id", "") or v_name), "name": v_name})
            result.append(
                {
                    "id": str(ds.get("id", "") or ds_name),
                    "name": ds_name,
                    "versions": versions,
                }
            )
        return result
    except Exception:
        _logger.debug("Trove 데이터스토어 목록 조회 실패", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# 백업 (SDK 미지원 → raw REST)
# ---------------------------------------------------------------------------


def _backup_to_dict(b: dict) -> dict:
    return {
        "id": b.get("id", ""),
        "name": b.get("name", ""),
        "description": b.get("description", ""),
        "status": b.get("status", ""),
        "instance_id": b.get("instance_id", ""),
        "size": b.get("size", 0),
        "created_at": b.get("created", "") or b.get("created_at", ""),
        "updated_at": b.get("updated", "") or b.get("updated_at", ""),
        "datastore": {
            "type": (b.get("datastore") or {}).get("type", "")
            if isinstance(b.get("datastore"), dict)
            else str(b.get("datastore", "")),
            "version": (b.get("datastore_version") or {}).get("name", "")
            if isinstance(b.get("datastore_version"), dict)
            else str(b.get("datastore_version", "")),
        },
    }


def list_backups(conn, instance_id: str | None = None) -> list[dict]:
    """백업 목록. instance_id 지정 시 해당 인스턴스 백업만 반환."""
    try:
        url = f"/instances/{instance_id}/backups" if instance_id else "/backups"
        resp = conn.database.get(url)
        body = resp.json() if hasattr(resp, "json") else {}
        return [_backup_to_dict(b) for b in body.get("backups", [])]
    except Exception:
        _logger.debug("Trove 백업 목록 조회 실패", exc_info=True)
        return []


def create_backup(conn, instance_id: str, name: str, description: str = "") -> dict:
    """백업 생성."""
    payload: dict = {"backup": {"instance": instance_id, "name": name}}
    if description:
        payload["backup"]["description"] = description
    resp = conn.database.post("/backups", json=payload)
    status = getattr(resp, "status_code", None)
    text = (getattr(resp, "text", "") or "")[:2000]
    body = resp.json() if hasattr(resp, "json") else {}
    backup_data = body.get("backup", {})
    if not backup_data or not backup_data.get("id"):
        _logger.error(
            "Trove create_backup 실패 status=%s body=%s",
            status,
            text,
        )
        raise RuntimeError(f"Trove 백업 생성 실패 (HTTP {status})")
    return _backup_to_dict(backup_data)


def delete_backup(conn, backup_id: str) -> None:
    """백업 삭제."""
    conn.database.delete(f"/backups/{backup_id}")


def get_backup(conn, backup_id: str) -> dict:
    """백업 상세 조회."""
    resp = conn.database.get(f"/backups/{backup_id}")
    body = resp.json() if hasattr(resp, "json") else {}
    return _backup_to_dict(body.get("backup", {}))


# ---------------------------------------------------------------------------
# 접근 제어 (is_public / allowed_cidrs)
# ---------------------------------------------------------------------------


def set_instance_access(conn, instance_id: str, is_public: bool, allowed_cidrs: list[str]) -> None:
    """인스턴스 접근 정책 설정 (is_public, allowed_cidrs)."""
    payload = {"access": {"is_public": is_public, "allowed_cidrs": allowed_cidrs}}
    conn.database.put(f"/instances/{instance_id}/access", json=payload)


# ---------------------------------------------------------------------------
# Configuration groups
# ---------------------------------------------------------------------------


def list_configurations(conn) -> list[dict]:
    """DB Configuration group 목록 (raw REST)."""
    try:
        resp = conn.database.get("/configurations")
        body = resp.json() if hasattr(resp, "json") else {}
        result = []
        for c in body.get("configurations", []):
            cfg_name = c.get("name", "") or ""
            cfg_id = str(c.get("id", "") or "")
            if not cfg_id:
                continue
            result.append(
                {
                    "id": cfg_id,
                    "name": cfg_name,
                    "datastore_name": c.get("datastore_name", "") or "",
                    "datastore_version_name": c.get("datastore_version_name", "") or "",
                }
            )
        return result
    except Exception:
        _logger.debug("Trove configuration group 목록 조회 실패", exc_info=True)
        return []
