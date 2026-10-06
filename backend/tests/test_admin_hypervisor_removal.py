"""Consumer-visible approval fencing; Nova/Placement are isolated at the adapter boundary."""

import asyncio
from copy import deepcopy
from threading import Event
from unittest.mock import AsyncMock

import httpx
import pytest

from app.api.deps import get_token_info
from app.api.identity import admin
from app.main import app
from app.services import hypervisor_removal, hypervisor_review
from tests.conftest import make_token_info

BASE = "/api/v1/admin/hypervisors/hyp-uuid"


@pytest.fixture
def cloud(monkeypatch, mock_conn):
    report = {
        "hypervisor_id": "hyp-uuid",
        "hostname": "compute-1",
        "checked_at": "2026-10-05T10:00:00+00:00",
        "service": {
            "id": "svc-uuid",
            "host": "compute-1",
            "binary": "nova-compute",
            "state": "down",
            "status": "disabled",
            "updated_at": "2026-10-04T10:00:00+00:00",
            "forced_down": False,
            "disabled_reason": "retiring",
            "zone": "nova",
        },
        "uptime": {"status": "unavailable", "value": None, "host_time": None},
        "servers": [],
        "history": {"deleted_servers": [], "migrations": [], "note": "Retained records only"},
        "placement": {
            "providers": [
                {
                    "uuid": "hyp-uuid",
                    "name": "compute-1",
                    "parent_provider_uuid": None,
                    "generation": 2,
                    "allocations": {},
                }
            ]
        },
        "checks": [{"code": "empty", "label": "Workloads", "state": "pass", "detail": "No current workloads"}],
        "eligible": True,
    }
    state = {"report": report, "deletions": [], "upstream_error": None, "verified": True}
    mock_conn.compute.get_endpoint.return_value = "https://nova.example/v2.1"

    def inspect(_conn, _id):
        return deepcopy(state["report"])

    def delete(url, **_kwargs):
        if state["upstream_error"]:
            raise state["upstream_error"]
        state["deletions"].append(url)
        return httpx.Response(204, request=httpx.Request("DELETE", url))

    def verify(_conn, evidence):
        verified = state["verified"] and bool(state["deletions"])
        return {
            "status": "removed" if verified else "removal_unverified",
            "verified": verified,
            "hypervisor_id": evidence["hypervisor_id"],
            "hostname": evidence["hostname"],
            "service_id": evidence["service"]["id"],
            "detail": "Removed" if verified else "Placement residue",
            "checks": [
                {
                    "code": "placement_absent",
                    "label": "Placement",
                    "state": "pass" if verified else "blocked",
                    "detail": "Absent" if verified else "Resource provider remains",
                }
            ],
        }

    monkeypatch.setattr(hypervisor_removal, "inspect_host", inspect)
    monkeypatch.setattr(hypervisor_removal, "verify_removal", verify)
    mock_conn.session.delete.side_effect = delete
    monkeypatch.setattr(admin, "rec", AsyncMock())
    return state


async def review(client):
    response = await client.post(BASE + "/removal-check", json={})
    assert response.status_code == 200, response.text
    return response.json()


def approval(result, **changes):
    return {
        "review_token": result["review_token"],
        "confirm_hostname": "compute-1",
        "reason": "retire hardware",
        "reviewed_metadata": True,
        "compute_stopped": True,
        **changes,
    }


@pytest.mark.asyncio
async def test_only_system_admin_can_inspect_or_approve(non_admin_client, cloud):
    check = await non_admin_client.post(BASE + "/removal-check", json={})
    remove = await non_admin_client.post(BASE + "/remove", json=approval({"review_token": "a" * 43}))
    assert check.status_code == remove.status_code == 403
    assert cloud["deletions"] == []


@pytest.mark.asyncio
async def test_unsafe_inspection_cannot_issue_an_approval(admin_client, cloud):
    cloud["report"]["eligible"] = False
    cloud["report"]["checks"][0]["state"] = "unknown"
    checked = await review(admin_client)
    assert checked["report"]["eligible"] is False
    assert checked["review_token"] is None and checked["expires_at"] is None
    response = await admin_client.post(BASE + "/remove", json=approval({"review_token": "a" * 43}))
    assert response.status_code == 409
    assert cloud["deletions"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes", [{"reviewed_metadata": False}, {"compute_stopped": False}, {"reason": "  "}, {"compute_stopped": "true"}]
)
async def test_operator_acknowledgements_are_required(admin_client, cloud, changes):
    checked = await review(admin_client)
    response = await admin_client.post(BASE + "/remove", json=approval(checked, **changes))
    assert response.status_code == 422
    assert cloud["deletions"] == []


@pytest.mark.asyncio
async def test_wrong_host_name_consumes_the_review_and_never_deletes(admin_client, cloud):
    checked = await review(admin_client)
    response = await admin_client.post(BASE + "/remove", json=approval(checked, confirm_hostname="compute-2"))
    assert response.status_code == 409
    correct = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert correct.status_code == 409
    assert cloud["deletions"] == []


@pytest.mark.asyncio
async def test_expired_review_requires_a_new_inspection(admin_client, cloud, _fake_redis_global):
    checked = await review(admin_client)
    await _fake_redis_global.expire(f"afterglow:ws-ticket:{checked['review_token']}", 0)
    response = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert response.status_code == 409
    assert cloud["deletions"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("context", ["user", "project", "cloud", "hypervisor"])
async def test_review_is_bound_to_identity_project_cloud_and_host(admin_client, cloud, mock_conn, context):
    checked = await review(admin_client)
    path = BASE
    if context in {"user", "project"}:
        token = make_token_info(roles=["admin"], is_system_admin=True)
        token["user_id" if context == "user" else "project_id"] = "someone-else"

        async def identity():
            return token

        app.dependency_overrides[get_token_info] = identity
    elif context == "cloud":
        mock_conn.compute.get_endpoint.return_value = "https://other-nova.example/v2.1"
    else:
        path = "/api/v1/admin/hypervisors/another-node"
    response = await admin_client.post(path + "/remove", json=approval(checked))
    assert response.status_code == 409
    assert cloud["deletions"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["heartbeat", "service", "history", "provider", "unsafe"])
async def test_changed_metadata_or_new_workload_invalidates_review(admin_client, cloud, change):
    checked = await review(admin_client)
    report = cloud["report"]
    if change == "heartbeat":
        report["service"]["updated_at"] = "2026-10-05T10:00:01Z"
    elif change == "service":
        report["service"]["id"] = "replacement-service"
    elif change == "history":
        report["history"]["deleted_servers"] = [
            {"id": "old-vm", "name": "old workload", "status": "DELETED", "project_id": "p1", "created_at": None}
        ]
    elif change == "provider":
        report["placement"]["providers"][0]["generation"] += 1
    else:
        report["eligible"] = False
        report["servers"] = [
            {"id": "new-vm", "name": "new workload", "status": "BUILD", "project_id": "p1", "created_at": None}
        ]
    response = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert response.status_code == 409
    retry = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert retry.status_code == 409
    assert cloud["deletions"] == []


@pytest.mark.asyncio
async def test_verified_removal_is_one_use_and_samples_do_not_change_approval(admin_client, cloud):
    checked = await review(admin_client)
    cloud["report"]["checked_at"] = "2026-10-05T10:00:30Z"
    cloud["report"]["uptime"] = {"status": "unavailable", "value": None, "host_time": "later sampling"}
    response = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "removed" and response.json()["verified"] is True
    retry = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert retry.status_code == 409
    assert len(cloud["deletions"]) == 1
    assert "no-store" in response.headers["cache-control"]
    assert checked["review_token"] not in repr(admin.rec.call_args_list)


@pytest.mark.asyncio
async def test_nova_acceptance_is_not_success_when_residue_remains(admin_client, cloud):
    cloud["verified"] = False
    checked = await review(admin_client)
    response = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert response.status_code == 200
    assert response.json()["status"] == "removal_unverified" and response.json()["verified"] is False
    assert response.json()["checks"][0]["state"] == "blocked"
    retry = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert retry.status_code == 409
    assert len(cloud["deletions"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [409, 500])
async def test_nova_rejection_is_public_and_review_cannot_be_replayed(admin_client, cloud, status):
    checked = await review(admin_client)
    request = httpx.Request("DELETE", "https://nova.example/v2.1/os-services/svc-uuid")
    cloud["upstream_error"] = httpx.HTTPStatusError(
        "password=private secret traceback", request=request, response=httpx.Response(status, request=request)
    )
    response = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert response.status_code == (409 if status == 409 else 502)
    assert "private" not in response.text and "traceback" not in response.text
    cloud["upstream_error"] = None
    retry = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert retry.status_code == 409
    assert cloud["deletions"] == []


@pytest.mark.asyncio
async def test_simultaneous_host_mutation_is_excluded(admin_client, cloud, monkeypatch):
    checked = await review(admin_client)
    entered, release = Event(), Event()

    def slow_inspection(_conn, _id):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("test barrier timed out")
        return deepcopy(cloud["report"])

    monkeypatch.setattr(hypervisor_removal, "inspect_host", slow_inspection)
    pending = asyncio.create_task(admin_client.post(BASE + "/remove", json=approval(checked)))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        conflict = await admin_client.put(BASE + "/service", json={"status": "enabled"})
        assert conflict.status_code == 409
        second = await admin_client.post(BASE + "/remove", json=approval(checked))
        assert second.status_code == 409
    finally:
        release.set()
        result = await pending
    assert result.status_code == 200 and result.json()["verified"] is True
    assert len(cloud["deletions"]) == 1


@pytest.mark.asyncio
async def test_cancelled_request_keeps_lock_until_nova_delete_finishes(admin_client, cloud, mock_conn):
    checked = await review(admin_client)
    entered, release = Event(), Event()
    delete = mock_conn.session.delete.side_effect

    def slow_delete(*args, **kwargs):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("test barrier timed out")
        return delete(*args, **kwargs)

    mock_conn.session.delete.side_effect = slow_delete
    pending = asyncio.create_task(admin_client.post(BASE + "/remove", json=approval(checked)))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        pending.cancel()
        await asyncio.sleep(0)
        conflict = await admin_client.put(BASE + "/service", json={"status": "enabled"})
        assert conflict.status_code == 409
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert len(cloud["deletions"]) == 1
    replay = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert replay.status_code == 409


@pytest.mark.asyncio
async def test_coordination_outage_never_falls_back_to_unlocked_deletion(admin_client, cloud, monkeypatch):
    checked = await review(admin_client)

    async def unavailable():
        raise RuntimeError("private Redis URL unavailable")

    monkeypatch.setattr(hypervisor_review, "_get_redis", unavailable)
    response = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert response.status_code == 503
    assert "private" not in response.text
    assert cloud["deletions"] == []


@pytest.mark.asyncio
async def test_down_host_retains_observed_uptime_without_claiming_live_status(admin_client, cloud):
    cloud["report"]["uptime"] = {"status": "available", "value": "up 8 days, 3:41", "host_time": "12:34:56"}
    observed = await review(admin_client)
    assert observed["report"]["uptime"]["source"] == "live"
    cloud["report"]["uptime"] = {"status": "unavailable", "value": None, "host_time": None}
    cloud["report"]["eligible"] = False
    down = await review(admin_client)
    uptime = down["report"]["uptime"]
    assert uptime["source"] == "last_observed" and uptime["status"] == "unavailable"
    assert uptime["value"] == "up 8 days, 3:41"
    assert uptime["observed_at"] == observed["report"]["uptime"]["observed_at"]
    assert down["review_token"] is None


@pytest.mark.asyncio
async def test_replacement_compute_service_does_not_inherit_old_uptime(admin_client, cloud):
    cloud["report"]["uptime"] = {"status": "available", "value": "up 99 days", "host_time": "12:34:56"}
    await review(admin_client)
    cloud["report"]["uptime"] = {"status": "unavailable", "value": None, "host_time": None}
    cloud["report"]["service"]["id"] = "replacement-service"
    checked = await review(admin_client)
    assert checked["report"]["uptime"]["source"] == "unavailable"
    assert checked["report"]["uptime"]["value"] is None


@pytest.mark.asyncio
async def test_review_expiring_during_revalidation_never_reaches_nova_delete(admin_client, cloud, monkeypatch):
    from datetime import UTC, datetime, timedelta

    clock = [datetime(2026, 10, 5, 10, 0, tzinfo=UTC)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(hypervisor_review, "datetime", Clock)
    checked = await review(admin_client)

    def delayed_inspection(_conn, _id):
        clock[0] += timedelta(seconds=hypervisor_review.REVIEW_TTL_SECONDS + 1)
        return deepcopy(cloud["report"])

    monkeypatch.setattr(hypervisor_removal, "inspect_host", delayed_inspection)
    response = await admin_client.post(BASE + "/remove", json=approval(checked))
    assert response.status_code == 409
    assert cloud["deletions"] == []
