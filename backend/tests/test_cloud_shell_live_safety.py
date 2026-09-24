import pytest

from tests.integration.test_cloud_shell import (
    LIVE_CONFIRM_ENV,
    LIVE_CONFIRM_VALUE,
    LIVE_IDENTITY_ENV,
    require_disposable_live_identity,
    require_empty_live_workspace,
)

CREDENTIALS = {
    "username": "cloud-shell-disposable",
    "password": "redacted",
    "project_name": "cloud-shell-integration",
    "domain_name": "Default",
}


def test_destructive_live_smoke_requires_explicit_identity_and_confirmation() -> None:
    with pytest.raises(pytest.skip.Exception):
        require_disposable_live_identity(CREDENTIALS, {})

    with pytest.raises(pytest.skip.Exception):
        require_disposable_live_identity(
            CREDENTIALS,
            {LIVE_IDENTITY_ENV: CREDENTIALS["username"]},
        )

    require_disposable_live_identity(
        CREDENTIALS,
        {
            LIVE_IDENTITY_ENV: CREDENTIALS["username"],
            LIVE_CONFIRM_ENV: LIVE_CONFIRM_VALUE,
        },
    )


def test_destructive_live_smoke_rejects_a_different_selected_user() -> None:
    with pytest.raises(pytest.fail.Exception, match="does not match"):
        require_disposable_live_identity(
            CREDENTIALS,
            {
                LIVE_IDENTITY_ENV: "some-other-user",
                LIVE_CONFIRM_ENV: LIVE_CONFIRM_VALUE,
            },
        )


def test_destructive_live_smoke_requires_an_empty_inactive_workspace() -> None:
    require_empty_live_workspace({"workspace": "absent", "session_active": False})

    with pytest.raises(pytest.fail.Exception, match="active session"):
        require_empty_live_workspace({"workspace": "absent", "session_active": True})

    with pytest.raises(pytest.fail.Exception, match="without a persistent workspace"):
        require_empty_live_workspace({"workspace": "available", "session_active": False})
