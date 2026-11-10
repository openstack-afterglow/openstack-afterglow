"""Native policy read failures keep a closed reason set at the raise site, not from the masked HTTP status."""

import httpx
import pytest
from fastapi import HTTPException

from app.services import service_authorization, service_proxy


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (service_proxy.NativePolicyError(401, "policy_unauthorized"), "policy_unauthorized"),
        (service_proxy.NativePolicyError(403, "policy_forbidden"), "policy_forbidden"),
        (service_proxy.NativePolicyError(503, "policy_not_found"), "policy_not_found"),
        (service_proxy.NativePolicyError(503, "policy_upstream_error"), "policy_upstream_error"),
        (service_proxy.NativePolicyError(503, "policy_unreachable"), "policy_unreachable"),
        (service_proxy.NativePolicyError(502, "policy_invalid_response"), "policy_invalid_response"),
        (service_proxy.NativePolicyError(403, "policy_local_guard"), "policy_local_guard"),
        (TimeoutError(), "policy_timeout"),
        (HTTPException(status_code=503, detail="not a native policy error"), "permission_check_unavailable"),
        (RuntimeError("upstream text must not leak"), "permission_check_unavailable"),
    ],
)
def test_policy_failures_map_to_closed_reason_codes(exc, code):
    assert service_authorization.policy_error_code(exc) == code


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _patch_native(monkeypatch, *, response=None, error=None):
    monkeypatch.setattr(service_proxy, "_get_internal_endpoint", lambda *_a, **_k: "https://drover.internal")

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _url, headers=None):
            if error is not None:
                raise error
            return response

    monkeypatch.setattr(service_proxy.httpx, "AsyncClient", FakeClient)


TOKEN = {"token": "subject-token", "project_id": "project-a"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "reason", "http_status"),
    [
        (401, "policy_unauthorized", 401),
        (403, "policy_forbidden", 403),
        (404, "policy_not_found", 503),
        (500, "policy_upstream_error", 503),
    ],
)
async def test_native_status_is_classified_at_the_raise_site(monkeypatch, status, reason, http_status):
    _patch_native(monkeypatch, response=_Response(status))
    with pytest.raises(service_proxy.NativePolicyError) as info:
        await service_proxy.get_policy_capabilities("drover", dict(TOKEN))
    assert info.value.reason == reason
    assert info.value.status_code == http_status


@pytest.mark.asyncio
async def test_transport_failure_is_unreachable_not_a_generic_status(monkeypatch):
    _patch_native(monkeypatch, error=httpx.ConnectError("refused"))
    with pytest.raises(service_proxy.NativePolicyError) as info:
        await service_proxy.get_policy_capabilities("drover", dict(TOKEN))
    assert info.value.reason == "policy_unreachable"


@pytest.mark.asyncio
async def test_local_subject_guard_is_not_reported_as_native_denial(monkeypatch):
    _patch_native(monkeypatch, response=_Response(200, {}))
    with pytest.raises(service_proxy.NativePolicyError) as info:
        await service_proxy.get_policy_capabilities("drover", {"token": "", "project_id": "project-a"})
    assert info.value.reason == "policy_local_guard"
    assert info.value.status_code == 401


@pytest.mark.asyncio
async def test_snapshot_reports_native_denial_as_reason_not_generic(monkeypatch):
    monkeypatch.setattr(service_authorization, "service_policy_availability", lambda: {"drover": True})

    async def deny(service, token_info, **_kwargs):
        raise service_proxy.NativePolicyError(403, "policy_forbidden")

    monkeypatch.setattr(service_proxy, "get_policy_capabilities", deny)

    permissions, errors = await service_authorization.service_permission_snapshot({"token": "t"})

    assert permissions == {"drover": []}
    assert errors == {"drover": "policy_forbidden"}
