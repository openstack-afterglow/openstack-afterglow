import pytest

from app.services import resource_policies


class _NetworkAPI:
    def __init__(self, networks):
        self._networks = {network.id: network for network in networks}

    def get_network(self, resource_id):
        return self._networks.get(resource_id)


class _NetworkConnection:
    def __init__(self, networks):
        self.network = _NetworkAPI(networks)


@pytest.mark.asyncio
async def test_service_scope_discovery_closes_owned_connection(monkeypatch):
    class ServiceConnection:
        closed = False

        def close(self):
            self.closed = True

    service_conn = ServiceConnection()
    admin_conn = object()

    async def service_connection(_admin_conn, spec):
        assert spec.execution_scope == "service"
        return service_conn

    monkeypatch.setattr(resource_policies, "discovery_connection", service_connection)
    monkeypatch.setattr(resource_policies.nova, "list_catalog_flavors", lambda _conn: [])

    assert await resource_policies.discover_options(admin_conn, "builder.flavor") == []
    assert service_conn.closed is True


def test_flavor_discovery_projects_real_catalog_without_afterglow_connection_attributes():
    from types import SimpleNamespace

    public = SimpleNamespace(
        id="public", name="Public", vcpus=2, ram=4096, disk=0, is_public=True, extra_specs={"hw:cpu_policy": "shared"}
    )
    private = SimpleNamespace(
        id="private",
        name="Private",
        vcpus=4,
        ram=8192,
        disk=0,
        is_public=False,
        extra_specs={"hw:cpu_policy": "shared"},
    )
    conn = SimpleNamespace(compute=SimpleNamespace(flavors=lambda **kwargs: [public, private]))
    spec = resource_policies.PolicySpec("test.flavor", "flavor", "Flavor", "Test", "", execution_scope="service")
    assert [option["id"] for option in resource_policies._discover_sync(conn, spec)] == ["public", "private"]
    tenant = resource_policies.PolicySpec("test.flavor", "flavor", "Flavor", "Test", "", execution_scope="tenant")
    assert [option["id"] for option in resource_policies._discover_sync(conn, tenant)] == ["public"]


@pytest.mark.asyncio
async def test_policy_clear_does_not_require_live_resource_lookup(monkeypatch):
    monkeypatch.setattr(
        resource_policies, "validate_existing_selection", lambda *_args: (_ for _ in ()).throw(AssertionError())
    )

    assert await resource_policies.validate_selection(object(), "builder.flavor", None) is None


@pytest.mark.asyncio
async def test_legacy_name_selector_resolves_one_exact_catalog_name(monkeypatch):
    def unavailable(*_args):
        raise resource_policies.ResourcePolicyValidationError("ID not found")

    monkeypatch.setattr(resource_policies, "_validate_existing_sync", unavailable)
    monkeypatch.setattr(
        resource_policies,
        "_discover_sync",
        lambda _conn, _spec: [
            {"id": "type-cephfs", "name": "cephfs"},
            {"id": "type-nfs", "name": "nfs"},
        ],
    )

    assert await resource_policies.validate_legacy_selection(
        object(), "manila.cephfs_share_type", "cephfs", allow_exact_name=True
    ) == {"id": "type-cephfs", "name": "cephfs"}


@pytest.mark.asyncio
async def test_legacy_name_selector_rejects_ambiguous_or_disallowed_names(monkeypatch):
    monkeypatch.setattr(
        resource_policies,
        "_validate_existing_sync",
        lambda *_args: (_ for _ in ()).throw(resource_policies.ResourcePolicyValidationError("ID not found")),
    )
    monkeypatch.setattr(
        resource_policies,
        "_discover_sync",
        lambda _conn, _spec: [{"id": "first", "name": "cephfs"}, {"id": "second", "name": "cephfs"}],
    )

    with pytest.raises(resource_policies.ResourcePolicyValidationError, match="ambiguous"):
        await resource_policies.validate_legacy_selection(
            object(), "manila.cephfs_share_type", "cephfs", allow_exact_name=True
        )
    with pytest.raises(resource_policies.ResourcePolicyValidationError):
        await resource_policies.validate_legacy_selection(
            object(), "manila.cephfs_share_type", "cephfs", allow_exact_name=False
        )


def test_registry_has_no_service_owned_drover_policies():
    keys = {spec.key for spec in resource_policies.list_specs()}

    assert not any(key.startswith("k3s.") for key in keys)
    assert {"openstack.service_project", "cinder.default_volume_availability_zone", "manila.nfs_share_type"} <= keys


def test_unknown_resource_policy_is_rejected():
    with pytest.raises(resource_policies.ResourcePolicyValidationError):
        resource_policies.get_spec("not-a-policy")


@pytest.mark.asyncio
async def test_missing_sdk_network_is_admission_validation_not_provider_error():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from openstack.exceptions import ResourceNotFound

    provider_error = ResourceNotFound("private provider response")
    conn = SimpleNamespace(network=SimpleNamespace(get_network=MagicMock(side_effect=provider_error)))
    with pytest.raises(
        resource_policies.ResourcePolicyValidationError, match="selected network is unavailable"
    ) as failure:
        await resource_policies.validate_existing_selection(conn, "nova.default_network", "missing-network")
    assert failure.value.__cause__ is provider_error
    assert "private provider response" not in str(failure.value)
    conn.network.get_network.assert_called_once_with("missing-network")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["auth", "outage"])
async def test_network_auth_and_outage_errors_are_not_reclassified_as_missing(kind):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from openstack.exceptions import ForbiddenException, HttpException

    error = (
        ForbiddenException("authorization denied")
        if kind == "auth"
        else HttpException("provider unavailable", http_status=503)
    )
    conn = SimpleNamespace(network=SimpleNamespace(get_network=MagicMock(side_effect=error)))
    with pytest.raises(type(error)) as failure:
        await resource_policies.validate_existing_selection(conn, "nova.default_network", "network-a")
    assert failure.value is error


@pytest.mark.asyncio
async def test_consume_missing_sdk_network_returns_400_before_provider_mutation(admin_client, mock_conn):
    from unittest.mock import AsyncMock, patch

    from openstack.exceptions import ResourceNotFound

    mock_conn.network.get_network.side_effect = ResourceNotFound("private provider response")
    with (
        patch("app.services.layer_build.run_layer_consume", AsyncMock()) as run,
        patch("app.services.layer_build.resolve_import_consume_artifacts", AsyncMock()) as artifacts,
        patch("app.services.keystone.get_admin_connection_for_project") as connect,
    ):
        response = await admin_client.post(
            "/api/v1/admin/libraries/consume",
            json={"transport": "block", "import_id": 9, "flavor_id": "flavor-a", "network_id": "missing-network"},
        )
    assert response.status_code == 400
    assert "selected network is unavailable" in response.json()["detail"]
    assert "private provider response" not in response.text
    run.assert_not_awaited()
    artifacts.assert_not_awaited()
    connect.assert_not_called()
    mock_conn.compute.create_server.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["auth", "outage"])
async def test_consume_network_auth_and_outage_do_not_become_missing_400(admin_client, mock_conn, kind):
    from unittest.mock import AsyncMock, patch

    from openstack.exceptions import ForbiddenException, HttpException

    error = (
        ForbiddenException("authorization denied")
        if kind == "auth"
        else HttpException("provider unavailable", http_status=503)
    )
    mock_conn.network.get_network.side_effect = error
    with patch("app.services.layer_build.run_layer_consume", AsyncMock()) as run:
        with pytest.raises(type(error)) as failure:
            await admin_client.post(
                "/api/v1/admin/libraries/consume",
                json={"transport": "block", "import_id": 9, "flavor_id": "flavor-a", "network_id": "network-a"},
            )
    assert failure.value is error
    run.assert_not_awaited()
