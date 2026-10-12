"""Project-scoped admission and native Nova initial password delivery.

Unwrap credentials only at the Nova call boundary. Keep them out of request
representations, instance metadata, history, progress messages and logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import HTTPException
from pydantic import SecretStr

if TYPE_CHECKING:
    import openstack

    from app.models.compute import CreateInstanceRequest

PASSWORD_PROVISIONING_ERROR = "Instance creation with a password failed. Contact an administrator."
PASSWORD_METADATA_ERROR = "Boot-source password metadata is unavailable."
WINDOWS_PASSWORD_UNSUPPORTED = "This Windows boot source does not support initial password provisioning."
WINDOWS_PASSWORD_CONFLICT = (
    "Windows password provisioning cannot be combined with user-data, GitHub SSH or data mounts."
)


@dataclass(frozen=True)
class PasswordProvisioning:
    windows: bool = False
    config_drive: bool = False

    def nova_admin_pass(self, password: SecretStr | None) -> str | None:
        """Unwrap only at the native Nova call, without altering the password."""
        if password is None:
            return None
        return password.get_secret_value()


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)


def preflight_password(
    conn: openstack.connection.Connection,
    req: CreateInstanceRequest,
) -> PasswordProvisioning:
    """Read the selected boot source before admission or resource mutation.

    No password means no extra lookup or behavior change. An unknown OS for a
    password-bearing request fails closed rather than assuming native Nova can
    provision it. Volume ownership is checked even for a scoped administrator.
    """
    if req.admin_pass is None:
        return PasswordProvisioning()

    try:
        if req.boot_volume_id:
            volume = conn.block_storage.get_volume(req.boot_volume_id)
            project_id = getattr(conn, "_afterglow_project_id", None)
            owner = getattr(volume, "project_id", None)
            if not project_id or owner != project_id:
                raise HTTPException(status_code=400, detail=PASSWORD_METADATA_ERROR)
            raw = volume.to_dict(original_names=True, computed=False)
            metadata = raw.get("volume_image_metadata") or getattr(volume, "volume_image_metadata", None)
        else:
            image = conn.image.get_image(req.image_id)
            metadata = dict(image.properties or {})
            # Glance's flat JSON is split by the SDK: known Body fields live
            # on Image, while the custom password-method marker is a property.
            # Explicit properties retain precedence, matching image projections.
            for key in ("os_type", "os_admin_user", "windows_initial_password_method"):
                if key not in metadata:
                    value = getattr(image, key, None)
                    if value is not None:
                        metadata[key] = value
    except Exception:
        # Provider exceptions can echo request credentials; do not chain them.
        raise HTTPException(status_code=400, detail=PASSWORD_METADATA_ERROR) from None

    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail=PASSWORD_METADATA_ERROR)
    os_type = metadata.get("os_type")
    if not isinstance(os_type, str) or not os_type.strip():
        raise HTTPException(status_code=400, detail=PASSWORD_METADATA_ERROR)
    if os_type.strip().lower() != "windows":
        return PasswordProvisioning()

    account = metadata.get("os_admin_user")
    if (
        metadata.get("windows_initial_password_method") != "nova-adminpass-configdrive"
        or not isinstance(account, str)
        or not account.strip()
        or _has_control(account)
    ):
        raise HTTPException(status_code=400, detail=WINDOWS_PASSWORD_UNSUPPORTED)
    if req.userdata or req.github_username or req.data_mounts:
        raise HTTPException(status_code=400, detail=WINDOWS_PASSWORD_CONFLICT)

    return PasswordProvisioning(windows=True, config_drive=True)
