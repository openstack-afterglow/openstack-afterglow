from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.compute import CreateInstanceRequest
from app.services.ssh_access import normalize_github_username


def test_create_request_accepts_github_ssh_source() -> None:
    request = CreateInstanceRequest(
        image_id="image-1",
        name="example-vm",
        flavor_id="flavor-1",
        github_username=" octocat ",
    )
    assert request.github_username == "octocat"
    assert request.key_name is None


@pytest.mark.parametrize("username", ["octo cat", "octo--cat", "octocat\nruncmd:\n- id"])
def test_create_request_rejects_invalid_github_ssh_source(username: str) -> None:
    with pytest.raises(ValidationError):
        CreateInstanceRequest(
            image_id="image-1",
            name="example-vm",
            flavor_id="flavor-1",
            github_username=username,
        )


def test_create_request_rejects_mixed_ssh_sources() -> None:
    with pytest.raises(ValidationError, match="함께 사용할 수 없습니다"):
        CreateInstanceRequest(
            image_id="image-1",
            name="example-vm",
            flavor_id="flavor-1",
            github_username="octocat",
            key_name="existing-keypair",
        )


def test_empty_github_username_is_absent() -> None:
    assert normalize_github_username("  ") is None
