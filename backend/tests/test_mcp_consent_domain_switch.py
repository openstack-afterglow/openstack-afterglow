"""Consent tickets follow a same-user domain switch only while pending; approval stays exact-owner."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.models.mcp_authority import McpOAuthAuthorizationRequest, McpOAuthClient
from app.services.mcp_control_plane import oauth_authority as oa

METADATA = {
    "client_id": "client-1",
    "client_name": "Codex",
    "redirect_uris": ["http://localhost:53796/callback"],
    "grant_types": ["authorization_code", "refresh_token"],
    "token_endpoint_auth_method": "none",
}


class _Begin:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_args):
        return False


class FakeSession:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def begin(self):
        return _Begin()

    async def scalar(self, stmt):
        return self.store[stmt.column_descriptions[0]["entity"].__name__]


def _store(*, status="pending", owner_user="user-a", owner_project="project-a"):
    request = SimpleNamespace(
        ticket_hash=None,
        client_id="client-1",
        client_fingerprint=oa._fingerprint(METADATA),
        redirect_uri="http://localhost:53796/callback",
        resource="https://cloud.example.test/mcp",
        scopes=["mcp:read"],
        code_challenge="c" * 43,
        state=None,
        status=status,
        expires_at=oa._now() + timedelta(minutes=10),
        owner_user_id=owner_user,
        owner_project_id=owner_project,
        grant_deadline=oa._now() + timedelta(days=1),
        used_at=None,
    )
    client = SimpleNamespace(client_id="client-1", metadata_json=METADATA, revoked_at=None)
    return {
        McpOAuthAuthorizationRequest.__name__: request,
        McpOAuthClient.__name__: client,
    }, request


@pytest.fixture
def no_owner_locks(monkeypatch):
    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(oa, "lock_owner", noop)


def _factory(store):
    return lambda: FakeSession(store)


@pytest.mark.asyncio
async def test_same_user_switching_domain_rebinds_pending_ticket(no_owner_locks):
    store, request = _store(owner_project="project-a")
    ticket = _ticket_for(request)
    consent = await oa.load_consent_ticket(
        _factory(store), ticket=ticket, owner_user_id="user-a", owner_project_id="project-b", rebind_project=True
    )
    assert consent.client_id == "client-1"
    assert request.owner_project_id == "project-b"
    assert request.owner_user_id == "user-a"


@pytest.mark.asyncio
async def test_project_change_without_rebind_is_still_refused(no_owner_locks):
    store, request = _store(owner_project="project-a")
    with pytest.raises(oa.McpOAuthAuthorityError, match="different project"):
        await oa.load_consent_ticket(
            _factory(store), ticket=_ticket_for(request), owner_user_id="user-a", owner_project_id="project-b"
        )
    assert request.owner_project_id == "project-a"


@pytest.mark.asyncio
async def test_other_user_cannot_rebind_a_pending_ticket(no_owner_locks):
    store, request = _store(owner_project="project-a")
    with pytest.raises(oa.McpOAuthAuthorityError, match="different user"):
        await oa.load_consent_ticket(
            _factory(store),
            ticket=_ticket_for(request),
            owner_user_id="user-b",
            owner_project_id="project-b",
            rebind_project=True,
        )
    assert request.owner_user_id == "user-a" and request.owner_project_id == "project-a"


@pytest.mark.asyncio
async def test_non_pending_ticket_is_not_rebound(no_owner_locks):
    store, request = _store(status="approved", owner_project="project-a")
    with pytest.raises(oa.McpOAuthAuthorityError, match="expired"):
        await oa.load_consent_ticket(
            _factory(store),
            ticket=_ticket_for(request),
            owner_user_id="user-a",
            owner_project_id="project-b",
            rebind_project=True,
        )
    assert request.owner_project_id == "project-a"


@pytest.mark.asyncio
async def test_approval_from_the_stale_project_is_refused_after_rebind(monkeypatch, no_owner_locks):
    async def no_orphans(*_args, **_kwargs):
        return None

    monkeypatch.setattr(oa, "recover_stale_pending_orphans", no_orphans)
    store, request = _store(owner_project="project-b")
    conn = SimpleNamespace(_afterglow_user_id="user-a", _afterglow_project_id="project-a")
    with pytest.raises(oa.McpOAuthAuthorityError, match="not available"):
        await oa.approve_consent_ticket(
            _factory(store),
            ticket=_ticket_for(request),
            owner_user_id="user-a",
            owner_project_id="project-a",
            username="user-a",
            roles=[],
            conn=conn,
        )


def _ticket_for(request) -> str:
    """Bind the stored hash to a known ticket value for the fake store."""
    ticket = "ticket-" + str(id(request))
    request.ticket_hash = oa.hash_oauth_value(ticket)
    return ticket


@pytest.mark.asyncio
async def test_project_list_labels_every_candidate_with_the_session_domain(monkeypatch):
    import json

    from app.api.identity import mcp_access

    monkeypatch.setattr(mcp_access, "_require_mcp_enabled", lambda: None)

    async def memberships(_conn, _user_id):
        return [{"id": "project-a", "name": "A"}]

    monkeypatch.setattr(mcp_access, "caller_membership_projects", memberships)
    response = await mcp_access.get_mcp_projects(
        request=None,
        preview=False,
        token_info={"user_id": "user-a", "domain_id": "domain-a", "domain_name": "DMS Lab"},
        conn=object(),
    )
    assert json.loads(response.body) == [
        {"id": "project-a", "name": "A", "domain_id": "domain-a", "domain_name": "DMS Lab"}
    ]
