from __future__ import annotations

import re

_GITHUB_USERNAME_RE = re.compile(r"^(?!-)(?!.*--)[A-Za-z0-9-]{1,39}(?<!-)\Z")

SSH_ACCESS_MODE_METADATA_KEY = "afterglow_ssh_access_mode"
GITHUB_LOGIN_METADATA_KEY = "afterglow_github_login"


def normalize_github_username(value: str | None) -> str | None:
    """Return a validated GitHub username suitable for cloud-init's gh: source."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if not _GITHUB_USERNAME_RE.match(normalized):
        raise ValueError(
            "github_username은 1~39자의 영문자, 숫자, 하이픈만 사용할 수 있으며 하이픈으로 시작·종료하거나 연속 하이픈을 사용할 수 없습니다"
        )
    return normalized


def github_ssh_metadata(verified_login: str | None) -> dict[str, str]:
    """Describe GitHub SSH access after the caller has verified the canonical login.

    This is not verification: API preflight remains authoritative. No keys or
    user-data belong in this metadata, and legacy/keypair VMs remain unmarked.
    """
    if not verified_login:
        return {}
    return {
        SSH_ACCESS_MODE_METADATA_KEY: "github",
        GITHUB_LOGIN_METADATA_KEY: verified_login,
    }
