"""Actual HTTP/SQL credential-state behavior; native directory/SMTP are synthetic."""

import pytest

from app.services import account_recovery as recovery
from tests.test_account_recovery import REPLACEMENT, persisted, seed_sessions, token_from
from tests.test_account_recovery import directory as directory
from tests.test_profile_password_creation import BASE
from tests.test_profile_password_creation import creation as creation
from tests.test_profile_password_creation import creation_client as creation_client
from tests.test_profile_password_creation import recoveries as recoveries

pytestmark = pytest.mark.asyncio


async def test_password_login_change_is_independent_of_admin_directory(creation, creation_client, monkeypatch):
    creation.actor["auth_method"] = "password"
    creation.settings.smtp_enabled = False
    creation.support = False

    def unavailable(*args, **kwargs):
        raise ConnectionError("admin directory offline")

    monkeypatch.setattr(recovery.keystone, "_get_admin_ks_client", unavailable)
    response = await creation_client.get(BASE + "/capability")
    assert response.status_code == 200
    assert response.json() == {"mode": "change"}
    assert not creation.sent and not creation.posts


@pytest.mark.parametrize("marker", [False, True, None, "false"])
async def test_external_existing_password_ignores_stale_marker(creation, creation_client, marker):
    creation.users["external"].afterglow_local_password = marker
    creation.password_states["external"] = "existing"
    response = await creation_client.get(BASE + "/capability")
    assert response.json() == {"mode": "change"}
    rejected = await creation_client.post(BASE + "/create/request", json={})
    assert rejected.status_code == 409
    assert not creation.sent and not creation.posts


async def test_external_unknown_state_keeps_current_password_path_not_first_creation(creation, creation_client):
    creation.support = False
    response = await creation_client.get(BASE + "/capability")
    assert response.json() == {"mode": "change", "reason": "password_state_unknown"}
    response = await creation_client.post(BASE + "/create/request", json={})
    assert response.status_code == 503
    assert not creation.sent and not creation.posts


async def test_profile_recovery_uses_only_current_registered_mailbox(creation, creation_client, recoveries):
    creation.password_states["external"] = "existing"
    response = await creation_client.post(BASE + "/recovery/request", json={})
    assert response.status_code == 202 and response.json() == {"accepted": True}
    assert response.headers["cache-control"] == "no-store, private"
    token = token_from(creation.sent[-1])
    row = await persisted(recoveries, token)
    assert row.kind == "password" and row.email == "external@test.invalid"
    assert row.native_identity_revision == "5"
    seed_sessions(creation, "external")
    response = await creation_client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert response.status_code == 200
    assert creation.posts[0][0] == "users/external/OS-AFTERGLOW/password-reset"
    assert creation.revoked == ["native-one", "native-two"]
    assert (await persisted(recoveries, token)).status == "changed"
    replay = await creation_client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert replay.status_code == 410


async def test_forgotten_password_cannot_create_first_external_password(creation, creation_client):
    response = await creation_client.post(BASE + "/recovery/request", json={})
    assert response.status_code == 202 and response.json() == {"accepted": True}
    assert not creation.sent and not creation.posts


@pytest.mark.parametrize(
    "body", [{"email": "victim@test.invalid"}, {"user_id": "local"}, {"identity_domain_id": "other"}]
)
async def test_profile_recovery_rejects_target_substitution(creation, creation_client, body):
    response = await creation_client.post(BASE + "/recovery/request", json=body)
    assert response.status_code == 422
    assert not creation.sent and not creation.posts


async def test_email_reset_rejects_native_identity_aba_before_dispatch(creation, creation_client, recoveries):
    creation.password_states["external"] = "existing"
    response = await creation_client.post(BASE + "/recovery/request", json={})
    assert response.status_code == 202
    token = token_from(creation.sent[-1])
    creation.identity_revision = "7"
    response = await creation_client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert response.status_code == 410
    assert not creation.posts
    assert (await persisted(recoveries, token)).status == "pending"


@pytest.mark.parametrize(
    "status,expected,state",
    [
        (409, 410, "rejected"),
        (412, 410, "rejected"),
        (422, 422, "rejected"),
        (503, 502, "outcome_unknown"),
        (307, 502, "outcome_unknown"),
    ],
)
async def test_external_reset_native_refusal_or_unknown_never_replays(
    creation, creation_client, recoveries, status, expected, state
):
    creation.password_states["external"] = "existing"
    assert (await creation_client.post(BASE + "/recovery/request", json={})).status_code == 202
    token = token_from(creation.sent[-1])
    seed_sessions(creation, "external")
    creation.post_status = status
    response = await creation_client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert response.status_code == expected
    assert (await persisted(recoveries, token)).status == state
    assert len(creation.posts) == 1
    assert creation.revoked == ([] if state == "rejected" else ["native-one", "native-two"])
    replay = await creation_client.post(
        "/api/v1/auth/recovery/password/complete", json={"token": token, "new_password": REPLACEMENT}
    )
    assert replay.status_code == 410 and len(creation.posts) == 1


@pytest.mark.parametrize("state", ["existing", "absent"])
async def test_mapped_session_without_native_federation_marker_uses_observed_state(
    creation, creation_client, recoveries, state
):
    user = creation.users["external"]
    user.federated = []
    del user.afterglow_local_password
    creation.password_states["external"] = state
    capability = await creation_client.get(BASE + "/capability")
    assert capability.json() == {"mode": "change" if state == "existing" else "create"}
    if state == "existing":
        assert (await creation_client.post(BASE + "/recovery/request", json={})).status_code == 202
        row = await persisted(recoveries, token_from(creation.sent[-1]))
        assert row.native_identity_revision == "5"
        completed = await creation_client.post(
            "/api/v1/auth/recovery/password/complete",
            json={"token": token_from(creation.sent[-1]), "new_password": REPLACEMENT},
        )
        assert completed.status_code == 200
        assert creation.posts[-1][0] == "users/external/OS-AFTERGLOW/password-reset"


async def test_stable_external_metadata_cannot_use_local_recovery_to_create_password(creation, creation_client):
    user = creation.users["external"]
    user.federated = []
    del user.afterglow_local_password
    user.afterglow_external_identities = [{"issuer": "https://provider.test.invalid", "subject": "subject"}]
    assert (await creation_client.post("/api/v1/auth/recovery/password", json={"email": user.email})).status_code == 202
    assert not creation.sent and not creation.posts
