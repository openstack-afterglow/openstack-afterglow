"""보안그룹 API 단위 테스트."""

from types import SimpleNamespace
from unittest.mock import call, patch

import pytest


def make_sg(sg_id: str = "sg-1", name: str = "test-sg") -> dict:
    return {
        "id": sg_id,
        "name": name,
        "description": "test security group",
        "project_id": "test-project-123",
        "security_group_rules": [],
    }


@pytest.mark.asyncio
async def test_list_security_groups(client, mock_conn):
    async def mock_cached_call(key, ttl, fn, **kw):
        return fn()

    with (
        patch("app.api.network.security_groups.neutron.list_security_groups", return_value=[make_sg()]),
        patch("app.api.network.security_groups.cached_call", new=mock_cached_call),
    ):
        resp = await client.get("/api/v1/security-groups")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert resp.json()[0]["id"] == "sg-1"


@pytest.mark.asyncio
async def test_create_security_group(client, mock_conn):
    with patch("app.api.network.security_groups.neutron.create_security_group", return_value=make_sg("sg-new")):
        resp = await client.post("/api/v1/security-groups", json={"name": "test-sg", "description": "test"})
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_delete_security_group(client, mock_conn):
    with patch("app.api.network.security_groups.neutron.delete_security_group", return_value=None):
        resp = await client.delete("/api/v1/security-groups/sg-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_create_security_group_rule(client, mock_conn):
    rule = {"id": "rule-1", "direction": "ingress", "protocol": "tcp", "port_range_min": 22, "port_range_max": 22}
    with patch("app.api.network.security_groups.neutron.create_security_group_rule", return_value=rule):
        resp = await client.post(
            "/api/v1/security-groups/sg-1/rules",
            json={
                "direction": "ingress",
                "protocol": "tcp",
                "port_range_min": 22,
                "port_range_max": 22,
            },
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_security_group_rule_rejects_port_in_remote_cidr_field(client, mock_conn):
    with patch("app.api.network.security_groups.neutron.create_security_group_rule") as create_rule:
        resp = await client.post(
            "/api/v1/security-groups/sg-1/rules",
            json={
                "direction": "ingress",
                "protocol": "tcp",
                "port_range_min": 9000,
                "port_range_max": 9000,
                "remote_ip_prefix": "9000",
            },
        )

    assert resp.status_code == 422
    assert "CIDR" in resp.text
    create_rule.assert_not_called()


@pytest.mark.asyncio
async def test_delete_security_group_rule(client, mock_conn):
    mock_conn.network.get_security_group_rule.return_value = SimpleNamespace(
        project_id="test-project-123", security_group_id="sg-1"
    )
    with patch("app.api.network.security_groups.neutron.delete_security_group_rule", return_value=None):
        resp = await client.delete("/api/v1/security-groups/sg-1/rules/rule-1")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_rule_target_defaults_and_rule_shapes(client, mock_conn):
    from app.services.neutron import _sg_to_dict, create_security_group_rule

    mock_conn.network.create_security_group_rule.return_value = SimpleNamespace(
        id="rule-2",
        direction="ingress",
        protocol="tcp",
        port_range_min=443,
        port_range_max=443,
        remote_ip_prefix=None,
        remote_group_id="sg-target",
        ether_type="IPv4",
    )
    mock_conn.network.get_security_group.side_effect = lambda sg_id: SimpleNamespace(
        project_id="test-project-123",
        id=sg_id,
    )
    with patch(
        "app.api.network.security_groups.neutron.create_security_group_rule", side_effect=create_security_group_rule
    ):
        resp = await client.post(
            "/api/v1/security-groups/sg-1/rules",
            json={
                "direction": "ingress",
                "protocol": "tcp",
                "port_range_min": 443,
                "remote_group_id": "sg-target",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["remote_group_id"] == "sg-target"
    assert resp.json()["remote_ip_prefix"] is None
    assert mock_conn.network.create_security_group_rule.call_args.kwargs == {
        "security_group_id": "sg-1",
        "direction": "ingress",
        "ether_type": "IPv4",
        "protocol": "tcp",
        "port_range_min": 443,
        "port_range_max": 443,
        "remote_group_id": "sg-target",
    }
    assert mock_conn.network.get_security_group.call_args_list == [call("sg-1"), call("sg-target")]
    sg = SimpleNamespace(
        id="sg-1",
        name="group",
        description="",
        security_group_rules=[
            {
                "id": "rule-2",
                "direction": "ingress",
                "remote_group_id": "sg-target",
                "ethertype": "IPv4",
            }
        ],
    )
    assert _sg_to_dict(sg)["rules"][0]["remote_group_id"] == "sg-target"


@pytest.mark.asyncio
async def test_rule_preserves_selected_network_cidr(client, mock_conn):
    with patch(
        "app.api.network.security_groups.neutron.create_security_group_rule", return_value={"id": "rule-net"}
    ) as create:
        resp = await client.post(
            "/api/v1/security-groups/sg-1/rules",
            json={
                "direction": "ingress",
                "ethertype": "IPv4",
                "remote_ip_prefix": "192.0.2.0/24",
                "protocol": "tcp",
                "port_range_min": 443,
            },
        )
    assert resp.status_code == 201
    assert create.call_args.kwargs["remote_ip_prefix"] == "192.0.2.0/24"
    assert create.call_args.kwargs["remote_group_id"] is None
    assert create.call_args.kwargs["port_range_max"] == 443


@pytest.mark.asyncio
async def test_rule_ipv6_open_target_and_port_default(client, mock_conn):
    with patch(
        "app.api.network.security_groups.neutron.create_security_group_rule", return_value={"id": "rule-2"}
    ) as create:
        resp = await client.post(
            "/api/v1/security-groups/sg-1/rules",
            json={
                "direction": "ingress",
                "ethertype": "IPv6",
                "protocol": "tcp",
                "port_range_min": 8080,
            },
        )
    assert resp.status_code == 201
    assert create.call_args.kwargs["remote_ip_prefix"] == "::/0"
    assert create.call_args.kwargs["port_range_max"] == 8080
    assert create.call_args.kwargs["remote_group_id"] is None


@pytest.mark.asyncio
async def test_rule_rejects_conflicting_or_wrong_family_target(client, mock_conn):
    with patch("app.api.network.security_groups.neutron.create_security_group_rule") as create:
        conflicting = await client.post(
            "/api/v1/security-groups/sg-1/rules",
            json={
                "direction": "ingress",
                "remote_group_id": "sg-2",
                "remote_ip_prefix": "0.0.0.0/0",
            },
        )
        wrong_family = await client.post(
            "/api/v1/security-groups/sg-1/rules",
            json={
                "direction": "ingress",
                "ethertype": "IPv6",
                "remote_ip_prefix": "0.0.0.0/0",
            },
        )
    assert conflicting.status_code == wrong_family.status_code == 422
    create.assert_not_called()


@pytest.mark.asyncio
async def test_rule_target_must_belong_to_project(client, mock_conn):
    mock_conn.network.get_security_group.side_effect = lambda sg_id: SimpleNamespace(
        project_id="another-project" if sg_id == "sg-target" else "test-project-123"
    )
    with patch("app.api.network.security_groups.neutron.create_security_group_rule") as create:
        resp = await client.post(
            "/api/v1/security-groups/sg-1/rules",
            json={
                "direction": "ingress",
                "remote_group_id": "sg-target",
            },
        )
    assert resp.status_code == 404
    create.assert_not_called()


@pytest.mark.asyncio
async def test_group_deletion_rejects_foreign_or_unknown_owner(client, mock_conn):
    with patch("app.api.network.security_groups.neutron.delete_security_group") as delete:
        for project_id in ("other-project", None):
            mock_conn.network.get_security_group.return_value = SimpleNamespace(project_id=project_id)
            resp = await client.delete("/api/v1/security-groups/sg-1")
            assert resp.status_code == 404
    delete.assert_not_called()


@pytest.mark.asyncio
async def test_rule_deletion_rejects_other_group_or_project(client, mock_conn):
    with patch("app.api.network.security_groups.neutron.delete_security_group_rule") as delete:
        for group_id, project_id in (("sg-2", "test-project-123"), ("sg-1", "other-project"), ("sg-1", None)):
            mock_conn.network.get_security_group_rule.return_value = SimpleNamespace(
                security_group_id=group_id,
                project_id=project_id,
            )
            resp = await client.delete("/api/v1/security-groups/sg-1/rules/rule-1")
            assert resp.status_code == 404
    delete.assert_not_called()


@pytest.mark.asyncio
async def test_quota_reads_detailed_neutron_usage(client, mock_conn):
    from openstack.network.v2.quota import QuotaDetails

    mock_conn.network.get_quota.return_value = QuotaDetails.new(
        security_group={"limit": 10, "used": 4},
        security_group_rule={"limit": 50, "used": 23},
    )
    resp = await client.get("/api/v1/security-groups/quota")
    assert resp.status_code == 200
    assert resp.json() == {
        "security_group": {"limit": 10, "in_use": 4},
        "security_group_rule": {"limit": 50, "in_use": 23},
    }
    mock_conn.network.get_quota.assert_called_once_with("test-project-123", details=True)


@pytest.mark.asyncio
async def test_quota_missing_usage_and_neutron_failure_are_visible(client, mock_conn):
    from openstack.network.v2.quota import QuotaDetails

    mock_conn.network.get_quota.return_value = QuotaDetails.new(
        security_group={"limit": 10, "used": 4},
        security_group_rule={"limit": 50},
    )
    assert (await client.get("/api/v1/security-groups/quota")).status_code == 503
    mock_conn.network.get_quota.side_effect = RuntimeError("Neutron unavailable")
    assert (await client.get("/api/v1/security-groups/quota")).status_code == 503
    assert mock_conn.network.get_quota.call_args_list == [
        call("test-project-123", details=True),
        call("test-project-123", details=True),
    ]


@pytest.mark.asyncio
async def test_group_instances_only_distinct_owned_compute_port_members(client, mock_conn):
    def port(device_id, group_ids, owner="compute:nova", project_id="test-project-123"):
        return SimpleNamespace(
            device_id=device_id, security_group_ids=group_ids, device_owner=owner, project_id=project_id
        )

    mock_conn.network.ports.return_value = [
        port("vm-a", ["sg-1"]),
        port("vm-a", ["sg-1", "sg-2"]),
        port("vm-b", ["sg-1"], "network:router_interface"),
        port("vm-c", ["sg-1"], project_id="other-project"),
        port("vm-d", ["sg-2"]),
        port("", ["sg-1"]),
        port("vm-e", ["sg-1"]),
    ]
    mock_conn.compute.get_server.side_effect = lambda instance_id: SimpleNamespace(
        project_id="test-project-123",
        name=f"Name {instance_id}",
        status="ACTIVE",
    )
    resp = await client.get("/api/v1/security-groups/sg-1/instances")
    assert resp.status_code == 200
    assert resp.json() == [
        {"id": "vm-a", "name": "Name vm-a", "status": "ACTIVE"},
        {"id": "vm-e", "name": "Name vm-e", "status": "ACTIVE"},
    ]
    mock_conn.network.ports.assert_called_once_with(project_id="test-project-123")
    assert mock_conn.compute.get_server.call_args_list == [call("vm-a"), call("vm-e")]


@pytest.mark.asyncio
async def test_group_instances_reject_foreign_group_before_listing_ports(client, mock_conn):
    mock_conn.network.get_security_group.return_value = SimpleNamespace(project_id="other-project")
    resp = await client.get("/api/v1/security-groups/sg-1/instances")
    assert resp.status_code == 404
    mock_conn.network.ports.assert_not_called()


@pytest.mark.asyncio
async def test_group_instances_do_not_leak_foreign_nova_server(client, mock_conn):
    mock_conn.network.ports.return_value = [
        SimpleNamespace(
            device_id="vm-x",
            security_group_ids=["sg-1"],
            device_owner="compute:nova",
            project_id="test-project-123",
        )
    ]
    mock_conn.compute.get_server.return_value = SimpleNamespace(
        project_id="other-project",
        name="secret",
        status="ACTIVE",
    )
    resp = await client.get("/api/v1/security-groups/sg-1/instances")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_group_instances_nova_failure_is_not_silent_empty(client, mock_conn):
    mock_conn.network.ports.return_value = [
        SimpleNamespace(
            device_id="vm-a",
            security_group_ids=["sg-1"],
            device_owner="compute:nova",
            project_id="test-project-123",
        )
    ]
    mock_conn.compute.get_server.side_effect = RuntimeError("Nova unavailable")
    resp = await client.get("/api/v1/security-groups/sg-1/instances")
    assert resp.status_code == 500
