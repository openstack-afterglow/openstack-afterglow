"""Nova host controls: service identity, safety gates, and per-server requests."""

from unittest.mock import MagicMock, patch

import pytest

BASE = "/api/v1/admin/hypervisors/hyp-uuid"
ENDPOINT = "https://nova.example/v2.1"


def _reply(data):
    response = MagicMock()
    response.json.return_value = data
    return response


def _install_nova(mock_conn, *, state="up", status="disabled", servers=(), pages=None, page_failure=False):
    """Mock Nova HTTP, retaining the URL and query parameter identity contract."""
    mock_conn.compute.get_endpoint.return_value = ENDPOINT
    hyp = {
        "id": "hyp-uuid",
        "hypervisor_hostname": "driver-name",
        "state": state,
        "status": status,
        "service": {"id": "svc-uuid", "host": "compute-host"},
    }
    service = {
        "id": "svc-uuid",
        "host": "compute-host",
        "binary": "nova-compute",
        "status": status,
        "disabled_reason": "maintenance" if status == "disabled" else None,
    }
    calls = []

    def get(url, *, params=None, headers=None):
        calls.append((url, params, headers))
        if url.endswith("/os-hypervisors/hyp-uuid"):
            return _reply({"hypervisor": hyp})
        if url.endswith("/os-services"):
            assert params == {"host": "compute-host", "binary": "nova-compute"}
            return _reply({"services": [service]})
        if url.endswith("/servers/detail"):
            index = len([c for c in calls if c[0].endswith("/servers/detail")]) - 1
            if page_failure and index == 1:
                raise RuntimeError("Nova page failed")
            data = (
                pages[index]
                if pages is not None and index < len(pages)
                else list(servers)
                if index == 0 and pages is None
                else []
            )
            return _reply({"servers": data})
        if "/servers/" in url:
            server_id = url.rsplit("/", 1)[-1]
            server = next(
                s for page in (pages if pages is not None else [servers]) for s in page if s["id"] == server_id
            )
            return _reply(
                {
                    "server": {
                        "id": server_id,
                        "status": server["status"],
                        "OS-EXT-SRV-ATTR:host": server.get("actual_host", "compute-host"),
                    }
                }
            )
        raise AssertionError(url)

    mock_conn.session.get.side_effect = get
    return hyp, service, calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("put", "/service", {"status": "disabled", "reason": "maintenance"}),
        ("post", "/relocate", {"mode": "migrate"}),
    ],
)
async def test_host_controls_require_admin(non_admin_client, mock_conn, method, suffix, body):
    response = await getattr(non_admin_client, method)(BASE + suffix, json=body)
    assert response.status_code == 403
    mock_conn.session.put.assert_not_called()
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
async def test_scheduling_uses_verified_service_uuid_and_exposes_reason(admin_client, mock_conn):
    _, service, calls = _install_nova(mock_conn, status="enabled")
    mock_conn.session.put.return_value = _reply(
        {"service": {**service, "status": "disabled", "disabled_reason": "planned maintenance"}}
    )
    response = await admin_client.put(BASE + "/service", json={"status": "disabled", "reason": " planned maintenance "})
    assert response.status_code == 200, response.text
    assert response.json()["disabled_reason"] == "planned maintenance"
    args, kwargs = mock_conn.session.put.call_args
    assert args == (ENDPOINT + "/os-services/svc-uuid",)
    assert kwargs["json"] == {"status": "disabled", "disabled_reason": "planned maintenance"}
    assert all(call[2] == {"OpenStack-API-Version": "compute 2.53"} for call in calls)


@pytest.mark.asyncio
async def test_scheduling_rejects_missing_reason_and_mismatched_service(admin_client, mock_conn):
    _, service, _ = _install_nova(mock_conn)
    response = await admin_client.put(BASE + "/service", json={"status": "disabled", "reason": "  "})
    assert response.status_code == 422
    service["id"] = "other-svc"
    response = await admin_client.put(BASE + "/service", json={"status": "enabled"})
    assert response.status_code == 409
    mock_conn.session.put.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,state,status,fenced",
    [
        ("migrate", "up", "enabled", False),
        ("migrate", "down", "disabled", False),
        ("evacuate", "up", "disabled", True),
        ("evacuate", "down", "disabled", False),
        ("evacuate", "down", "enabled", False),
    ],
)
async def test_invalid_source_or_missing_fence_requests_nothing(admin_client, mock_conn, mode, state, status, fenced):
    _install_nova(mock_conn, state=state, status=status)
    response = await admin_client.post(BASE + "/relocate", json={"mode": mode, "fenced": fenced})
    assert response.status_code in (400, 409)
    mock_conn.session.post.assert_not_called()
    mock_conn.compute.live_migrate_server.assert_not_called()
    mock_conn.compute.migrate_server.assert_not_called()
    assert not any(c.args[0].endswith("/servers/detail") for c in mock_conn.session.get.call_args_list)


@pytest.mark.asyncio
async def test_disagreeing_hypervisor_and_service_state_blocks_requests(admin_client, mock_conn):
    _, service, _ = _install_nova(mock_conn, servers=[{"id": "a", "status": "ACTIVE"}])
    service["state"] = "down"
    response = await admin_client.post(BASE + "/relocate", json={"mode": "migrate"})
    assert response.status_code == 409
    mock_conn.session.post.assert_not_called()
    mock_conn.compute.live_migrate_server.assert_not_called()
    assert not any(c.args[0].endswith("/servers/detail") for c in mock_conn.session.get.call_args_list)


@pytest.mark.asyncio
async def test_up_disabled_dispatches_by_state_and_skips_stale_host_and_unsupported(admin_client, mock_conn):
    servers = [
        {"id": "active", "name": "a", "status": "ACTIVE"},
        {"id": "stopped", "name": "s", "status": "SHUTOFF"},
        {"id": "moving", "name": "m", "status": "ACTIVE", "actual_host": "another-host"},
        {"id": "error", "name": "e", "status": "ERROR"},
    ]
    _, _, calls = _install_nova(mock_conn, servers=servers)
    with (
        patch("app.api.identity.admin.nova.live_migrate_server", side_effect=RuntimeError("private traceback")) as live,
        patch("app.api.identity.admin.nova.cold_migrate_server") as cold,
    ):
        response = await admin_client.post(BASE + "/relocate", json={"mode": "migrate"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(i["id"], i["action"], i["outcome"]) for i in body["items"]] == [
        ("active", "live-migrate", "failed"),
        ("stopped", "cold-migrate", "requested"),
        ("moving", None, "skipped"),
        ("error", None, "skipped"),
    ]
    assert "private traceback" not in response.text
    live.assert_called_once_with(mock_conn, "active")
    cold.assert_called_once_with(mock_conn, "stopped")
    detail_calls = [c for c in calls if c[0].endswith("/servers/detail")]
    assert detail_calls[0][1] == {"all_tenants": "1", "host": "compute-host", "limit": "200"}
    mock_conn.session.put.assert_not_called()
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
async def test_down_fenced_evacuates_eligible_and_records_rejections(admin_client, mock_conn):
    _install_nova(
        mock_conn,
        state="down",
        status="enabled",
        servers=[
            {"id": "one", "name": "a", "status": "ACTIVE"},
            {"id": "two", "name": "b", "status": "SHUTOFF"},
            {"id": "three", "name": "c", "status": "ERROR"},
        ],
    )
    mock_conn.session.post.side_effect = [_reply({}), RuntimeError("secret stack trace")]
    response = await admin_client.post(BASE + "/relocate", json={"mode": "evacuate", "fenced": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(i["id"], i["outcome"]) for i in body["items"]] == [
        ("one", "requested"),
        ("two", "failed"),
        ("three", "skipped"),
    ]
    assert "secret stack trace" not in response.text
    assert mock_conn.session.post.call_count == 2
    assert mock_conn.session.post.call_args_list[0].kwargs["json"] == {"evacuate": {}}
    assert mock_conn.session.post.call_args_list[0].kwargs["headers"] == {"OpenStack-API-Version": "compute 2.53"}
    mock_conn.session.put.assert_not_called()


@pytest.mark.asyncio
async def test_pagination_exhausts_pages_before_dispatch(admin_client, mock_conn, monkeypatch):
    from app.services import nova_hosts

    monkeypatch.setattr(nova_hosts, "HOST_SERVER_PAGE_SIZE", 3)
    pages = [
        [{"id": "a", "name": "a", "status": "SHUTOFF"}, {"id": "b", "name": "b", "status": "SHUTOFF"}],
        [{"id": "c", "name": "c", "status": "SHUTOFF"}],
    ]
    _, _, calls = _install_nova(mock_conn, pages=pages)
    with patch("app.api.identity.admin.nova.cold_migrate_server") as cold:
        response = await admin_client.post(BASE + "/relocate", json={"mode": "migrate"})
    assert response.status_code == 200, response.text
    assert [i["id"] for i in response.json()["items"]] == ["a", "b", "c"]
    assert cold.call_count == 3
    detail_calls = [c[1] for c in calls if c[0].endswith("/servers/detail")]
    assert detail_calls == [
        {"all_tenants": "1", "host": "compute-host", "limit": "3"},
        {"all_tenants": "1", "host": "compute-host", "limit": "3", "marker": "b"},
        {"all_tenants": "1", "host": "compute-host", "limit": "3", "marker": "c"},
    ]


@pytest.mark.asyncio
async def test_service_change_refreshes_cached_list_and_detail(admin_client, mock_conn, monkeypatch):
    from app.api.identity import admin

    hyp, service, _ = _install_nova(mock_conn, status="enabled")
    monkeypatch.setattr(admin, "_fetch_hypervisors_raw", lambda conn: [hyp])
    first = await admin_client.get("/api/v1/admin/hypervisors")
    assert first.status_code == 200
    assert first.json()[0]["status"] == "enabled"

    def update(url, *, json, headers):
        assert url == ENDPOINT + "/os-services/svc-uuid"
        hyp["status"] = service["status"] = json["status"]
        hyp["service"]["disabled_reason"] = service["disabled_reason"] = json["disabled_reason"]
        return _reply({"service": service})

    mock_conn.session.put.side_effect = update
    change = await admin_client.put(BASE + "/service", json={"status": "disabled", "reason": "maintenance"})
    assert change.status_code == 200, change.text
    refreshed = await admin_client.get("/api/v1/admin/hypervisors")
    assert refreshed.status_code == 200
    assert refreshed.json()[0]["status"] == "disabled"
    assert refreshed.json()[0]["disabled_reason"] == "maintenance"
    detail = await admin_client.get(BASE)
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "disabled"
    assert detail.json()["disabled_reason"] == "maintenance"


@pytest.mark.asyncio
async def test_failed_later_page_dispatches_no_actions(admin_client, mock_conn, monkeypatch):
    from app.services import nova_hosts

    monkeypatch.setattr(nova_hosts, "HOST_SERVER_PAGE_SIZE", 1)
    _, _, calls = _install_nova(mock_conn, pages=[[{"id": "a", "name": "a", "status": "ACTIVE"}]], page_failure=True)
    response = await admin_client.post(BASE + "/relocate", json={"mode": "migrate"})
    assert response.status_code == 502
    assert sum(c[0].endswith("/servers/detail") for c in calls) == 2
    mock_conn.compute.live_migrate_server.assert_not_called()
    mock_conn.compute.migrate_server.assert_not_called()
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
async def test_changed_source_during_scan_rejects_whole_batch(admin_client, mock_conn):
    hyp, _, _ = _install_nova(mock_conn, servers=[{"id": "a", "name": "a", "status": "ACTIVE"}])
    get = mock_conn.session.get.side_effect

    def mutate_during_scan(url, **kwargs):
        response = get(url, **kwargs)
        if url.endswith("/servers/detail"):
            hyp["state"] = "down"
        return response

    mock_conn.session.get.side_effect = mutate_during_scan
    response = await admin_client.post(BASE + "/relocate", json={"mode": "migrate"})
    assert response.status_code == 409
    mock_conn.compute.live_migrate_server.assert_not_called()
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
async def test_lease_loss_during_last_server_read_never_dispatches(admin_client, mock_conn, monkeypatch):
    from app.services import hypervisor_review

    _install_nova(mock_conn, servers=[{"id": "vm-last", "status": "ACTIVE"}])
    lease_type = hypervisor_review.HostOperationLease
    leases = []

    def new_lease(*args):
        lease = lease_type(*args)
        leases.append(lease)
        return lease

    monkeypatch.setattr(hypervisor_review, "HostOperationLease", new_lease)
    get = mock_conn.session.get.side_effect

    def lose_during_read(url, **kwargs):
        response = get(url, **kwargs)
        if url.endswith("/servers/vm-last"):
            leases[0].lost = True
        return response

    mock_conn.session.get.side_effect = lose_during_read
    response = await admin_client.post(BASE + "/relocate", json={"mode": "migrate"})
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["outcome"] == "skipped"
    mock_conn.compute.live_migrate_server.assert_not_called()
    mock_conn.session.post.assert_not_called()
