"""Explicit-operation reuse and request-fresh domain guards; synthetic native I/O only."""

from collections import Counter
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from keystoneclient.exceptions import NotFound

from app.services import domain_scope, keystone
from app.services.native_operation import NativeOperation
from tests.test_domain_projects import domain_native as domain_native
from tests.test_domain_projects import row


def token_context():
    return {
        "user_id": "creator",
        "domain_id": "tenant-a",
        "identity_domain_id": "home",
        "project_id": "default-a",
    }


def fence(operation=None):
    domain_scope.assert_token_context(
        token_context(),
        user_id="creator",
        domain_id="tenant-a",
        project_id="default-a",
        identity_domain_id="home",
        operation=operation,
    )


def test_nested_context_reuses_identity_domain_project_and_full_graph(domain_native, monkeypatch):
    n = domain_native
    n.raw.append(row(user={"id": "creator"}, role={"id": "admin"}, scope={"system": {"all": True}}))
    n.group_rows["external-managers"] = row(
        id="external-managers", name="External managers", domain_id="home", description=""
    )
    n.members["external-managers"] = {"second"}
    n.raw.append(row(group={"id": "external-managers"}, role={"id": "alias"}, scope={"project": {"id": "default-a"}}))
    roles = Mock(wraps=n.roles.list)
    edges = Mock(wraps=n.inference_rules.list_inference_roles)
    monkeypatch.setattr(n.roles, "list", roles)
    monkeypatch.setattr(n.inference_rules, "list_inference_roles", edges)
    client = Mock(return_value=n)
    monkeypatch.setattr(keystone, "_get_admin_ks_client", client)
    with NativeOperation() as operation:
        for _ in range(2):
            context = domain_scope.domain_context("creator", "tenant-a", operation=operation)
            assert context == {
                "identity_domain_id": "home",
                "identity_domain_name": "home",
                "domain_id": "tenant-a",
                "domain_name": "tenant-a",
                "is_domain_manager": True,
            }
            assert domain_scope.has_scope_authority("creator", domain_id="tenant-a", operation=operation)
            assert domain_scope.has_scope_authority("creator", operation=operation)
            fence(operation)
    counts = Counter(n.read_calls)
    assert counts[("user", "creator")] == 1
    assert counts[("user", "second")] == 1
    assert counts[("group", "external-managers")] == 1
    assert counts[("users.list", "external-managers", None)] == 1
    assert counts[("domain", "tenant-a")] == 1
    assert counts[("domain", "home")] == 1
    assert counts[("project", "default-a")] == 1
    assert counts[("assignments.list", None, None, None, False, None)] == 1
    assert counts[("assignments.list", "default-a", None, None, True, None)] == 1
    roles.assert_called_once_with()
    edges.assert_called_once_with()
    client.assert_called_once_with()
    assert n.calls == []


@pytest.mark.parametrize("resource,status", [("domain", 403), ("identity", 401), ("project", 403)])
def test_standalone_guards_ignore_warm_operation_reads(domain_native, resource, status):
    n = domain_native
    with NativeOperation() as operation:
        domain_scope.domain_context("creator", "tenant-a", operation=operation)
        fence(operation)
        if resource == "domain":
            n.domain_rows["tenant-a"] = row(id="tenant-a", name="tenant-a", enabled=False)
        elif resource == "identity":
            n.user_rows["creator"] = row(id="creator", domain_id="home", enabled=False)
        else:
            n.project_rows["default-a"] = row(id="default-a", domain_id="tenant-a", enabled=False)
        # The explicitly retained snapshot stays local to its owning operation.
        assert domain_scope.domain_context("creator", "tenant-a", operation=operation)["is_domain_manager"]
        fence(operation)
        with pytest.raises(HTTPException) as denied:
            if resource == "domain":
                domain_scope.resolve_domain("tenant-a")
            elif resource == "identity":
                domain_scope.domain_context("creator", "tenant-a")
            else:
                fence()
        assert denied.value.status_code == status


def test_standalone_manager_guard_observes_external_revoke(domain_native):
    n = domain_native
    with NativeOperation() as operation:
        assert domain_scope.has_scope_authority("creator", domain_id="tenant-a", operation=operation)
        n.raw = []
        assert domain_scope.has_scope_authority("creator", domain_id="tenant-a", operation=operation)
        assert not domain_scope.has_scope_authority("creator", domain_id="tenant-a")
        with NativeOperation() as other_operation:
            assert not domain_scope.has_scope_authority("creator", domain_id="tenant-a", operation=other_operation)


def test_system_group_grants_reuse_reads_but_standalone_rechecks_membership(domain_native, monkeypatch):
    n = domain_native
    n.group_rows["operators"] = row(id="operators", name="Operators", domain_id="home", description="")
    n.members["operators"] = {"creator"}
    n.raw.append(row(group={"id": "operators"}, role={"id": "admin"}, scope={"system": {"all": True}}))
    groups = Mock(wraps=n.groups.list)
    monkeypatch.setattr(n.groups, "list", groups)
    with NativeOperation() as operation:
        for _ in range(2):
            assert domain_scope.has_scope_authority("creator", operation=operation)
        counts = Counter(n.read_calls)
        assert counts[("assignments.list", None, "creator", None, False, "all")] == 1
        assert counts[("assignments.list", None, None, "operators", False, "all")] == 1
        groups.assert_called_once_with(user="creator")
        n.members["operators"] = set()
        assert domain_scope.has_scope_authority("creator", operation=operation)
        assert not domain_scope.has_scope_authority("creator")
        with NativeOperation() as other_operation:
            assert not domain_scope.has_scope_authority("creator", operation=other_operation)


@pytest.mark.parametrize("lookup_by_alias", [False, True])
def test_domain_alias_reuses_canonical_domain_without_weakening_exact_context(
    domain_native, monkeypatch, lookup_by_alias
):
    n = domain_native
    n.domain_rows["tenant-a"].name = "Tenant A"
    native_get = n.domains.get

    def get(domain_id):
        if domain_id == "Tenant A":
            if lookup_by_alias:
                return native_get("tenant-a")
            raise NotFound("No domain with this ID")
        return native_get(domain_id)

    get_call = Mock(side_effect=get)
    list_call = Mock(wraps=n.domains.list)
    monkeypatch.setattr(n.domains, "get", get_call)
    monkeypatch.setattr(n.domains, "list", list_call)
    with NativeOperation() as operation:
        assert domain_scope.resolve_domain("Tenant A", operation=operation)["id"] == "tenant-a"
        assert domain_scope.resolve_domain("Tenant A", operation=operation)["id"] == "tenant-a"
        assert domain_scope.domain_context("creator", "tenant-a", operation=operation)["domain_name"] == "Tenant A"
        assert get_call.call_args_list.count((("Tenant A",), {})) == 1
        assert Counter(n.read_calls)[("domain", "tenant-a")] == int(lookup_by_alias)
        assert list_call.call_count == int(not lookup_by_alias)
        with pytest.raises(HTTPException) as denied:
            domain_scope.domain_context("creator", "Tenant A", operation=operation)
        assert denied.value.status_code == 403


@pytest.mark.parametrize("use_operation", [False, True])
@pytest.mark.parametrize("failure,status", [("ambiguous", 409), ("missing", 404), ("disabled", 403), ("identity", 503)])
def test_domain_resolution_preserves_exactness_and_status(domain_native, monkeypatch, use_operation, failure, status):
    n = domain_native
    lookup = "tenant-a"
    if failure in {"ambiguous", "missing"}:
        lookup = "Alias"
        monkeypatch.setattr(n.domains, "get", Mock(side_effect=NotFound("Domain not found")))
        if failure == "ambiguous":
            n.domain_rows["tenant-a"].name = lookup
            n.domain_rows["tenant-b"].name = lookup
    elif failure == "disabled":
        n.domain_rows[lookup].enabled = False
    else:
        monkeypatch.setattr(n.domains, "get", lambda _: n.domain_rows["tenant-b"])
    with NativeOperation() as operation:
        with pytest.raises(HTTPException) as denied:
            domain_scope.resolve_domain(lookup, operation=operation if use_operation else None)
        assert denied.value.status_code == status


@pytest.mark.asyncio
async def test_invalidation_discards_supplied_operation_authority_reads(domain_native, monkeypatch):
    n = domain_native
    invalidate = AsyncMock()
    monkeypatch.setattr("app.services.cache.invalidate", invalidate)
    with NativeOperation() as operation:
        assert domain_scope.has_scope_authority("creator", domain_id="tenant-a", operation=operation)
        n.raw = []
        await domain_scope.invalidate_authority(operation=operation)
        assert not operation.reads
        assert not domain_scope.has_scope_authority("creator", domain_id="tenant-a", operation=operation)
    assert invalidate.await_count == 3
