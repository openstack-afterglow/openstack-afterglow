"""HTTP coverage for fixed administrator transport and native child boundaries."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openstack.load_balancer.v2.listener import Listener
from openstack.load_balancer.v2.pool import Pool

from app.api.deps import get_token_info
from app.api.identity.admin_resource_details import router
from app.services import keystone, manila

PATHS = [
    "/file-storage/share",
    "/file-storage/share/access-rules",
    "/loadbalancers/lb",
    "/loadbalancers/lb/listeners",
    "/loadbalancers/lb/pools",
    "/loadbalancers/lb/pools/pool/members",
    "/loadbalancers/lb/status",
    "/database-instances",
    "/database-instances/db",
    "/database-instances/db/databases",
    "/database-instances/db/users",
    "/database-instances/db/backups",
]


def response(body):
    result = MagicMock()
    result.json.return_value = body
    return result


def native(rid, **kwargs):
    return SimpleNamespace(id=rid, project_id="foreign", name=rid, **kwargs)


@pytest_asyncio.fixture
async def detail_api(monkeypatch):
    from app.services import domain_scope

    token = {
        "is_system_admin": True,
        "project_id": "personal",
        "connection_project_id": "personal",
        "user_id": "human",
        "domain_id": "domain",
        "domain_name": "Domain",
        "identity_domain_id": "domain",
        "token": "human-member-token",
    }
    conn = MagicMock()
    conn.current_project_id = "configured-admin"
    conn.session.auth.get_access.return_value = SimpleNamespace(
        project_id="configured-admin",
        auth_token="executor-token",
        project_scoped=True,
        system_scoped=False,
        is_admin_project=True,
        role_names=["admin"],
        _data={"token": {}},
    )
    factory = MagicMock(return_value=conn)
    monkeypatch.setattr(keystone, "get_admin_project_connection", factory)
    monkeypatch.setattr(keystone, "validate_token", lambda *args, **kwargs: {"roles": ["member"]})
    monkeypatch.setattr(keystone, "_is_system_admin", lambda uid, **kwargs: True)
    monkeypatch.setattr(domain_scope, "domain_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(domain_scope, "assert_token_context", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin")
    app.dependency_overrides[get_token_info] = lambda: token
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, conn, token, factory


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PATHS)
async def test_nonadmin_rejected_before_executor_or_native_send(detail_api, path):
    client, conn, token, factory = detail_api
    token["is_system_admin"] = False
    result = await client.get("/api/v1/admin" + path)
    assert result.status_code == 403
    factory.assert_not_called()
    conn.database.get.assert_not_called()
    conn.load_balancer.get_load_balancer.assert_not_called()


@pytest.mark.asyncio
async def test_foreign_load_balancer_and_children_use_fixed_executor(detail_api):
    client, conn, token, _ = detail_api
    conn.load_balancer.get_load_balancer.return_value = native("lb", provisioning_status="ERROR")
    listener = Listener(id="listener", name="listener", project_id="foreign", load_balancers=[{"id": "lb"}])
    pool = Pool(id="pool", name="pool", project_id="foreign", loadbalancers=[{"id": "lb"}])
    member = native("member", pool_id="pool")
    conn.load_balancer.listeners.return_value = [listener]
    conn.load_balancer.pools.return_value = [pool]
    conn.load_balancer.get_pool.return_value = pool
    conn.load_balancer.members.return_value = [member]
    tree = {"id": "lb", "listeners": [{"id": "listener", "pools": [{"id": "pool", "members": [{"id": "member"}]}]}]}
    conn.load_balancer.get.return_value = response({"statuses": {"loadbalancer": tree}})
    conn.load_balancer.get_listener.return_value = listener
    conn.load_balancer.get_member.return_value = member
    for suffix in ("", "/listeners", "/pools", "/pools/pool/members", "/status"):
        result = await client.get("/api/v1/admin/loadbalancers/lb" + suffix, headers={"X-Project-Id": "unrelated"})
        assert result.status_code == 200, result.text
    assert conn._afterglow_authenticated_project_id == "configured-admin"
    assert conn._afterglow_project_id == "personal"
    assert conn._afterglow_token == "executor-token"
    assert token["roles"] == ["member"]
    conn.load_balancer.members.assert_called_once_with("pool")
    conn.load_balancer.pools.assert_called_once_with(loadbalancer_id="lb")
    conn.load_balancer.listeners.assert_called_once_with(load_balancer_id="lb")
    assert conn.close.call_count == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["listeners", "pools"])
@pytest.mark.parametrize("bad", ["owner", "relation", "missing-owner", "missing-relation"])
async def test_lb_child_mismatch_fails_closed(detail_api, kind, bad):
    client, conn, _, _ = detail_api
    values = {"id": "child", "project_id": "foreign"}
    relation_key = "loadbalancers" if kind == "pools" else "load_balancers"
    values[relation_key] = [{"id": "lb"}]
    row = Pool(**values) if kind == "pools" else Listener(**values)
    if bad == "owner":
        row.project_id = "other"
    if bad == "relation":
        setattr(row, relation_key, [{"id": "other-lb"}])
    if bad == "missing-owner":
        row.project_id = None
    if bad == "missing-relation":
        setattr(row, relation_key, [])
    # Resource's dict snapshot remains valid; authoritative attributes must win.
    assert row.get("project_id") == "foreign"
    assert row.get(relation_key) == [{"id": "lb"}]
    collection = MagicMock(side_effect=lambda **kwargs: iter([row]))
    conn.load_balancer = SimpleNamespace(
        get_load_balancer=MagicMock(return_value=native("lb")),
        **{kind: collection},
    )
    result = await client.get(f"/api/v1/admin/loadbalancers/lb/{kind}")
    collection.assert_called_once_with(**{"loadbalancer_id" if kind == "pools" else "load_balancer_id": "lb"})
    assert result.status_code == 404
    assert "child" not in result.text


@pytest.mark.asyncio
async def test_foreign_pool_id_rejected_before_members(detail_api):
    client, conn, _, _ = detail_api
    conn.load_balancer.get_load_balancer.return_value = native("lb")
    conn.load_balancer.get_pool.return_value = Pool(id="pool", project_id="foreign", loadbalancers=[{"id": "other"}])
    result = await client.get("/api/v1/admin/loadbalancers/lb/pools/pool/members")
    assert result.status_code == 404
    conn.load_balancer.members.assert_not_called()


@pytest.mark.asyncio
async def test_status_tree_foreign_child_rejected(detail_api):
    client, conn, _, _ = detail_api
    conn.load_balancer.get_load_balancer.return_value = native("lb")
    conn.load_balancer.get.return_value = response(
        {"statuses": {"loadbalancer": {"id": "lb", "listeners": [{"id": "other"}]}}}
    )
    conn.load_balancer.get_listener.return_value = native("other", load_balancers=[{"id": "other-lb"}])
    result = await client.get("/api/v1/admin/loadbalancers/lb/status")
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_foreign_share_rules_require_exact_native_parent(detail_api, monkeypatch):
    client, conn, _, _ = detail_api
    raw = {"id": "share", "project_id": "foreign", "metadata": {}}
    client_factory = MagicMock()
    client_factory.return_value.get.return_value = {"share": raw}
    monkeypatch.setattr(manila, "get_client", client_factory)
    rule_list = MagicMock(return_value=[{"id": "rule"}])
    exact_rule = MagicMock(return_value={"id": "rule", "share_id": "share", "access_key": "secret"})
    monkeypatch.setattr(manila, "list_access_rules", rule_list)
    monkeypatch.setattr(manila, "get_access_rule", exact_rule)
    result = await client.get("/api/v1/admin/file-storage/share/access-rules")
    assert result.status_code == 200
    assert result.json() == [{"id": "rule", "share_id": "share"}]
    assert "access_key" not in result.text and "secret" not in result.text
    rule_list.assert_called_once_with(conn, "share", strict=True)
    exact_rule.assert_called_once_with(conn, "share", "rule")
    raw["project_id"] = None
    rule_list.reset_mock()
    result = await client.get("/api/v1/admin/file-storage/share/access-rules")
    assert result.status_code == 404
    rule_list.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["databases", "users", "backups"])
async def test_foreign_trove_children_use_authenticated_catalog_parent(detail_api, kind):
    client, conn, _, _ = detail_api
    parent = {"id": "db", "tenant_id": "foreign", "name": "db", "status": "ACTIVE"}
    child = {"name": "entry"} if kind != "backups" else {"id": "backup", "instance_id": "db"}
    paths = []

    def get(path):
        paths.append(path)
        if path == "/mgmt/instances/db":
            return response({"instance": parent})
        assert path == f"/instances/db/{kind}"
        assert conn._afterglow_authenticated_project_id == "configured-admin"
        assert conn._afterglow_token == "executor-token"
        return response({kind: [child]})

    conn.database.get.side_effect = get
    result = await client.get(f"/api/v1/admin/database-instances/db/{kind}")
    assert result.status_code == 200, result.text
    assert len(result.json()) == 1
    assert paths == ["/mgmt/instances/db", f"/instances/db/{kind}"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parent",
    [{"id": "other", "tenant_id": "foreign"}, {"id": "db"}, {"id": "db", "tenant_id": "foreign", "deleted": True}],
)
async def test_trove_unproven_parent_blocks_children(detail_api, parent):
    client, conn, _, _ = detail_api
    conn.database.get.return_value = response({"instance": parent})
    result = await client.get("/api/v1/admin/database-instances/db/users")
    assert result.status_code == 404
    conn.database.get.assert_called_once_with("/mgmt/instances/db")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "backup",
    [
        {"id": "backup", "instance_id": "other"},
        {"id": "backup"},
        {"id": "backup", "instance_id": "db", "tenant_id": "other"},
    ],
)
async def test_trove_backup_relation_and_owner_mismatch_rejected(detail_api, backup):
    client, conn, _, _ = detail_api
    conn.database.get.side_effect = [
        response({"instance": {"id": "db", "tenant_id": "foreign"}}),
        response({"backups": [backup]}),
    ]
    result = await client.get("/api/v1/admin/database-instances/db/backups")
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_trove_native_failure_not_empty_success(detail_api):
    client, conn, _, _ = detail_api
    conn.database.get.side_effect = [
        response({"instance": {"id": "db", "tenant_id": "foreign"}}),
        RuntimeError("private native failure"),
    ]
    result = await client.get("/api/v1/admin/database-instances/db/databases")
    assert result.status_code == 502
    assert "private native failure" not in result.text


@pytest.mark.asyncio
async def test_fresh_native_authority_revocation_blocks_inventory(detail_api, monkeypatch):
    client, conn, _, factory = detail_api
    monkeypatch.setattr(keystone, "_is_system_admin", lambda uid, **kwargs: False)
    result = await client.get("/api/v1/admin/database-instances")
    assert result.status_code == 403
    factory.assert_not_called()
    conn.database.get.assert_not_called()


@pytest.mark.asyncio
async def test_foreign_database_detail_has_canonical_owner(detail_api):
    client, conn, _, _ = detail_api
    conn.database.get.return_value = response(
        {"instance": {"id": "db", "tenant_id": "foreign", "name": "DB", "status": "ACTIVE"}}
    )
    result = await client.get("/api/v1/admin/database-instances/db")
    assert result.status_code == 200
    assert result.json()["project_id"] == "foreign"
    assert result.json()["name"] == "DB"
    conn.database.get.assert_called_once_with("/mgmt/instances/db")


@pytest.mark.asyncio
async def test_foreign_share_detail_proves_native_owner_before_enrichment(detail_api, monkeypatch):
    client, conn, _, _ = detail_api
    raw = {"id": "share", "project_id": "foreign", "metadata": {}}
    native_client = MagicMock()
    native_client.get.return_value = {"share": raw}
    monkeypatch.setattr(manila, "get_client", lambda c: native_client)
    detail = MagicMock(return_value=raw)
    monkeypatch.setattr(manila, "get_file_storage", detail)
    result = await client.get("/api/v1/admin/file-storage/share")
    assert result.status_code == 200
    assert result.json()["project_id"] == "foreign"
    detail.assert_called_once_with(conn, "share", resolve_user=True)
    raw["metadata"] = {"union_project_id": "other"}
    detail.reset_mock()
    result = await client.get("/api/v1/admin/file-storage/share")
    assert result.status_code == 404
    detail.assert_not_called()


@pytest.mark.asyncio
async def test_share_mismatched_rule_rejected_without_returning_secret(detail_api, monkeypatch):
    client, _, _, _ = detail_api
    native_client = MagicMock()
    native_client.get.return_value = {"share": {"id": "share", "project_id": "foreign", "metadata": {}}}
    monkeypatch.setattr(manila, "get_client", lambda c: native_client)
    monkeypatch.setattr(manila, "list_access_rules", lambda *a, **kw: [{"id": "rule"}])
    monkeypatch.setattr(
        manila, "get_access_rule", lambda *a: {"id": "rule", "share_id": "other", "access_key": "private-secret"}
    )
    result = await client.get("/api/v1/admin/file-storage/share/access-rules")
    assert result.status_code == 404
    assert "private-secret" not in result.text


@pytest.mark.asyncio
async def test_trove_pagination_never_follows_native_supplied_host(detail_api):
    client, conn, _, _ = detail_api
    conn.database.get.side_effect = [
        response({"instance": {"id": "db", "tenant_id": "foreign"}}),
        response(
            {
                "users": [{"name": "first", "host": "%"}],
                "users_links": [
                    {"rel": "next", "href": "https://untrusted.invalid/other/users?marker=first%40%25&limit=1"}
                ],
            }
        ),
        response(
            {
                "users": [{"name": "first", "host": "localhost"}],
                "users_links": [
                    {"rel": "next", "href": "https://untrusted.invalid/other/users?marker=first%40localhost&limit=1"}
                ],
            }
        ),
        response({"users": [{"name": "second", "host": "%"}]}),
    ]
    result = await client.get("/api/v1/admin/database-instances/db/users")
    assert result.status_code == 200
    assert [(row["name"], row["host"]) for row in result.json()] == [
        ("first", "%"),
        ("first", "localhost"),
        ("second", "%"),
    ]
    assert [call.args[0] for call in conn.database.get.call_args_list] == [
        "/mgmt/instances/db",
        "/instances/db/users",
        "/instances/db/users?marker=first%40%25",
        "/instances/db/users?marker=first%40localhost",
    ]
