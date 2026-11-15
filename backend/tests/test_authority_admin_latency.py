"""Administrator chat keeps its independent fresh native guard.

Use AUTHORITY_BENCHMARK=1 to measure these same tests against baseline source.
The upstream forwarding boundary is synthetic; authentication and guards are real.
"""

import json
import os
import time
from collections import Counter

import pytest
from fastapi.responses import JSONResponse

from app.api import deps
from app.api.lumen import proxy as lumen_proxy
from app.services import domain_scope, keystone, service_authorization
from tests.test_auth_domain_boundaries import domain_client as domain_client
from tests.test_authority_resolution_latency import delayed_browser as delayed_browser


def configure_admin(browser, monkeypatch, source):
    _, _, state, members, recorder = browser
    if source == "direct":
        subject = {"user": {"id": "user"}}
    else:
        subject = {"group": {"id": "team-0"}}
        ks = keystone._get_admin_ks_client()

        def groups(domain=None, user=None):
            if user is not None:
                return (
                    [{"id": "team-0", "name": "team-0", "domain_id": "tenant-a", "description": ""}]
                    if user in members["team-0"]
                    else []
                )
            return [{"id": gid, "name": gid, "domain_id": "tenant-a", "description": ""} for gid in members]

        monkeypatch.setattr(ks.groups, "list", recorder.wrap("groups.list", groups))
    state.assignments.append({**subject, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}})
    recorder.reset()


async def authorized_upstream(service, request, upstream_path, **kwargs):
    await service_authorization.authorize_service_request(service, request, upstream_path)
    return JSONResponse([])


@pytest.mark.asyncio
@pytest.mark.parametrize("admin_source", ["direct", "group"])
async def test_admin_chat_round_trip_benchmark(delayed_browser, monkeypatch, admin_source):
    configure_admin(delayed_browser, monkeypatch, admin_source)
    client, tokens, _, _, recorder = delayed_browser
    monkeypatch.setattr(lumen_proxy, "proxy", authorized_upstream)
    started = time.perf_counter()
    response = await client.get("/api/v1/chat/conversations", headers={"Authorization": "Bearer " + tokens["token"]})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    report = recorder.report("/api/v1/chat/conversations", elapsed)
    report["admin_source"] = admin_source
    print("AUTHORITY_ADMIN_BENCHMARK=" + json.dumps(report, sort_keys=True))
    if os.environ.get("AUTHORITY_BENCHMARK"):
        return
    counts = Counter((label, args, query) for label, args, query, _ in recorder.calls)
    assert len(recorder.calls) == (82 if admin_source == "direct" else 84)
    assert counts[("users.get", ("user",), ())] == 2
    assert counts[("domains.get", ("tenant-a",), ())] == 2
    assert counts[("role_assignments.list", (), (("system", "all"), ("user", "user")))] == 2
    assert 2 <= recorder.peak <= 4


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["system_role", "system_group_membership", "selected_project_membership"])
async def test_admin_chat_fresh_guard_observes_same_request_revocation(delayed_browser, monkeypatch, revocation):
    configure_admin(delayed_browser, monkeypatch, "group" if revocation == "system_group_membership" else "direct")
    client, tokens, state, members, recorder = delayed_browser
    monkeypatch.setattr(lumen_proxy, "proxy", authorized_upstream)
    fresh_guard = deps.require_admin
    operations = []
    context = domain_scope.domain_context

    def observe_context(*args, operation=None, **kwargs):
        if operation is not None and all(item is not operation for item in operations):
            operations.append(operation)
        return context(*args, operation=operation, **kwargs)

    monkeypatch.setattr(domain_scope, "domain_context", observe_context)
    entered = []

    async def revoke_before_guard(principal):
        assert principal["is_system_admin"] is True
        assert principal.get("_live_system_admin") is not True
        entered.append(len(recorder.calls))
        if revocation == "system_role":
            state.assignments = [item for item in state.assignments if "system" not in item["scope"]]
        elif revocation == "system_group_membership":
            members["team-0"].clear()
        else:
            state.grants["user"].remove("own")
        return await fresh_guard(principal)

    monkeypatch.setattr(deps, "require_admin", revoke_before_guard)
    response = await client.get("/api/v1/chat/conversations", headers={"Authorization": "Bearer " + tokens["token"]})
    assert response.status_code == (401 if revocation == "selected_project_membership" else 403), response.text
    assert entered and len(recorder.calls) > entered[0]
    assert len(operations) == 2, "fresh guard must not reuse authentication's NativeOperation"
    counts = Counter((label, args) for label, args, _, _ in recorder.calls)
    assert counts[("users.get", ("user",))] == 2
    assert counts[("domains.get", ("tenant-a",))] == 2
