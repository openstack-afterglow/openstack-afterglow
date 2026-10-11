"""Ordinary creation and instance responses expose no library/HA selectors."""

from app.api.identity.admin_instances import AdminCreateInstanceRequest
from app.models.compute import CreateInstanceRequest, InstanceInfo


def test_create_instance_request_has_no_library_or_ha_selectors():
    removed = {"libraries", "strategy", "scheduling", "existing_upper_volume_id"}
    assert not removed & CreateInstanceRequest.model_fields.keys()
    assert not removed & AdminCreateInstanceRequest.model_fields.keys()


def test_instance_info_has_no_scheduling_projection():
    assert "scheduling" not in InstanceInfo.model_fields
