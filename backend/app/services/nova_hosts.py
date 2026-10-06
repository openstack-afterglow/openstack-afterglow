"""Raw Nova host identity and exhaustive admin-scoped server reads.

Host filtering is Nova's responsibility here: legacy host-control fixtures and
callers do not necessarily include OS-EXT-SRV-ATTR:host. Removal inspection adds
its own strict host/metadata validation before treating a scan as evidence.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException

NOVA_HOST_HEADERS = {"OpenStack-API-Version": "compute 2.53"}
HOST_SERVER_PAGE_SIZE = 200
MAX_HOST_PAGES = 10000


def _object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid {label}")
    return value


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or invalid {label}")
    return value


def _items(body: dict, key: str) -> list[dict]:
    items = body.get(key)
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError(f"Invalid {key} page")
    return items


def _get_json(conn, endpoint: str, path: str, *, params=None, headers=None) -> dict:
    response = conn.session.get(f"{endpoint.rstrip('/')}{path}", params=params, headers=headers)
    response.raise_for_status()
    return _object(response.json(), "response")


def get_hypervisor(conn, hypervisor_id: str) -> dict:
    hypervisor_id = _text(hypervisor_id, "hypervisor ID")
    body = _get_json(
        conn,
        conn.compute.get_endpoint(),
        f"/os-hypervisors/{quote(hypervisor_id, safe='')}",
        headers=NOVA_HOST_HEADERS,
    )
    hypervisor = _object(body.get("hypervisor"), "hypervisor")
    if hypervisor.get("id") != hypervisor_id:
        raise HTTPException(status_code=409, detail="하이퍼바이저 ID가 일치하지 않습니다")
    return hypervisor


def get_compute_service(conn, hypervisor: dict) -> dict:
    """Resolve both the hypervisor mapping and the exact service host/binary."""
    try:
        mapping = _object(hypervisor.get("service"), "hypervisor service")
        service_id = _text(mapping.get("id"), "service ID")
        host = _text(mapping.get("host"), "service host")
    except ValueError:
        raise HTTPException(status_code=409, detail="컴퓨트 서비스를 확인할 수 없습니다") from None
    body = _get_json(
        conn,
        conn.compute.get_endpoint(),
        "/os-services",
        params={"host": host, "binary": "nova-compute"},
        headers=NOVA_HOST_HEADERS,
    )
    services = _items(body, "services")
    for service in services:
        for field in ("id", "host", "binary"):
            _text(service.get(field), f"service {field}")
    matches = [
        item
        for item in services
        if item["id"] == service_id and item["host"] == host and item["binary"] == "nova-compute"
    ]
    if len(matches) != 1 or any(
        item["host"] == host and item["binary"] == "nova-compute" and item["id"] != service_id for item in services
    ):
        raise HTTPException(status_code=409, detail="컴퓨트 서비스 매핑을 확인할 수 없습니다")
    return matches[0]


def host_servers(conn, host: str, *, deleted: bool = False):
    """Yield all pages, including when Nova caps a page below our requested limit.

    deleted=True includes Nova-retained deleted *and soft-deleted* instances.
    No extra host-field requirement is imposed on ordinary callers.
    """
    host = _text(host, "host")
    endpoint = conn.compute.get_endpoint()
    marker = None
    seen: set[str] = set()
    for _ in range(MAX_HOST_PAGES):
        params = {"all_tenants": "1", "host": host, "limit": str(HOST_SERVER_PAGE_SIZE)}
        if deleted:
            params["deleted"] = "true"
        if marker is not None:
            params["marker"] = marker
        body = _get_json(conn, endpoint, "/servers/detail", params=params, headers=NOVA_HOST_HEADERS)
        page = _items(body, "servers")
        for server in page:
            server_id = _text(server.get("id"), "server ID")
            if server_id in seen:
                raise ValueError("Invalid server pagination")
            seen.add(server_id)
            yield server
        if not page:
            if body.get("servers_links"):
                raise ValueError("Invalid empty server page with continuation")
            return
        marker = page[-1]["id"]
    raise ValueError("Server pagination did not terminate")
