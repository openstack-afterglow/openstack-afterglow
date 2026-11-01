"""Database policy/runtime-setting authority regression tests."""

import pytest

from app.services import resource_policy_store


def test_runtime_settings_are_strictly_allowlisted_and_typed():
    assert resource_policy_store._validate_runtime_value("notion.sync_enabled", False) is False

    with pytest.raises(resource_policy_store.RuntimeSettingValidationError):
        resource_policy_store._validate_runtime_value("notion.sync_enabled", 1)
    with pytest.raises(resource_policy_store.RuntimeSettingValidationError):
        resource_policy_store._validate_runtime_value("unknown", True)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["compute.managed_flavors", "compute.flavor_automation_policy"])
async def test_generic_runtime_write_cannot_bypass_automation_policy(key, monkeypatch):
    def forbidden_storage():
        pytest.fail("dedicated automation policy must be rejected before storage access")

    monkeypatch.setattr(resource_policy_store, "_require_db", forbidden_storage)
    with pytest.raises(resource_policy_store.RuntimeSettingValidationError):
        await resource_policy_store.set_runtime_setting(
            key=key, value={"revision": 999, "hosts": [], "gpu_profiles": []}, updated_by_user_id="admin"
        )
