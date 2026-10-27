"""Behavioral native-state fixtures for Default-project domain authority.

No real Keystone mutation. A separate fake directory expands group and inherited
assignments; the production service must prove its reads and writes against it.
Role mutations exercise real cache invalidation and session-store Lua on fake Redis.
"""

import asyncio
import hashlib
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import cache, domain_projects, domain_scope, identity_roles, keystone, project_service, session_store
from tests.ownership_journal import ownership_journal as ownership_journal

pytestmark = pytest.mark.usefixtures("ownership_journal")


def row(**attrs):
    return SimpleNamespace(**attrs)


def grant(role, *, user=None, group=None, project=None, domain=None, inherited=False):
    scope = {"project" if project else "domain": {"id": project or domain}}
    if inherited:
        scope["OS-INHERIT:inherited_to"] = "projects"
    return row(role={"id": role}, scope=scope, **{"user" if user else "group": {"id": user or group}})


class Directory:
    def __init__(self):
        self.domain_rows = {
            d: row(id=d, name=d, enabled=True, description="") for d in ("home", "tenant-a", "tenant-b")
        }
        self.user_rows = {
            u: row(id=u, name=u, enabled=True, domain_id=d)
            for u, d in (
                ("creator", "home"),
                ("ordinary", "tenant-a"),
                ("other", "tenant-b"),
                ("second", "home"),
                ("operator", "home"),
            )
        }
        self.project_rows = {
            p: row(id=p, name=n, domain_id=d, enabled=True, parent_id=d)
            for p, n, d in (
                ("default-a", "Default", "tenant-a"),
                ("work-a", "Work", "tenant-a"),
                ("default-b", "Default", "tenant-b"),
                ("work-b", "Work", "tenant-b"),
            )
        }
        self.group_rows = {}
        self.members = {}
        self.raw = [grant("manager", user="creator", project="default-a")]
        self.calls = []
        self.read_calls = []
        self.role_rows = [
            row(id=n, name=n, domain_id=None)
            for n in (
                "manager",
                "reader",
                "project_reader",
                "project_member",
                "project_admin",
                "project_owner",
                "member",
                "alias",
                "admin",
            )
        ]
        self.edges = [
            {"prior_role": {"id": "project_reader"}, "implies": [{"id": "reader"}]},
            {"prior_role": {"id": "project_owner"}, "implies": [{"id": "project_admin"}]},
            {"prior_role": {"id": "project_admin"}, "implies": [{"id": "project_member"}]},
            {"prior_role": {"id": "project_member"}, "implies": [{"id": "project_reader"}, {"id": "member"}]},
            {"prior_role": {"id": "alias"}, "implies": [{"id": "manager"}]},
        ]
        self.roles = row(list=lambda: self.role_rows, grant=self.assign, revoke=self.revoke)
        self.inference_rules = row(list_inference_roles=lambda: self.edges)
        self.domains = row(
            get=lambda id: self.get_row("domain", self.domain_rows, id),
            list=lambda: list(self.domain_rows.values()),
            create=self.create_domain,
            update=self.update_domain,
            delete=self.delete_domain,
        )
        self.projects = row(
            get=lambda id: self.get_row("project", self.project_rows, id),
            list=self.projects_list,
            create=self.create_project,
            update=self.update_project,
            delete=self.delete_project,
        )
        self.groups = row(
            get=lambda id: self.get_row("group", self.group_rows, id),
            list=self.groups_list,
            create=self.create_group,
            delete=self.delete_group,
        )
        self.users = row(
            get=lambda id: self.get_row("user", self.user_rows, id),
            list=self.users_list,
            add_to_group=self.add_group,
            remove_from_group=self.remove_group,
        )
        self.role_assignments = row(list=self.assignments)

    def get_row(self, kind, rows, id):
        self.read_calls.append((kind, id))
        return rows[id]

    def projects_list(self, domain=None):
        return [p for p in self.project_rows.values() if domain is None or p.domain_id == domain]

    def groups_list(self, domain=None, user=None):
        return [
            g
            for g in self.group_rows.values()
            if (domain is None or g.domain_id == domain) and (user is None or user in self.members.get(g.id, set()))
        ]

    def users_list(self, group=None, domain=None, name=None):
        self.read_calls.append(("users.list", group, domain))
        if group is not None:
            return [self.user_rows[u] for u in self.members.get(group, set())]
        return [
            u
            for u in self.user_rows.values()
            if (domain is None or u.domain_id == domain) and (name is None or u.name == name)
        ]

    def assignments(self, project=None, user=None, group=None, effective=False, system=None):
        self.read_calls.append(("assignments.list", project, user, group, effective, system))
        if not effective:
            return [
                r
                for r in self.raw
                if (project is None or r.scope.get("project", {}).get("id") == project)
                and (group is None or getattr(r, "group", {}).get("id") == group)
                and (user is None or getattr(r, "user", {}).get("id") == user)
                and (system is None or r.scope.get("system", {}).get("all") is True)
            ]
        result = []
        for source in self.raw:
            source_project = source.scope.get("project", {}).get("id")
            source_domain = source.scope.get("domain", {}).get("id")
            inherited = source.scope.get("OS-INHERIT:inherited_to") == "projects"
            for target in self.project_rows.values():
                if project is not None and project != target.id:
                    continue
                applies = source_project == target.id and not inherited
                if inherited and source_domain == target.domain_id:
                    applies = True
                parent = target.parent_id
                visited = set()
                while inherited and parent in self.project_rows and parent not in visited:
                    visited.add(parent)
                    applies = applies or source_project == parent
                    parent = self.project_rows[parent].parent_id
                if not applies:
                    continue
                gid = getattr(source, "group", {}).get("id")
                subjects = self.members.get(gid, set()) if gid else {source.user["id"]}
                for uid in subjects:
                    if user is not None and user != uid:
                        continue
                    scope = {"project": {"id": target.id}}
                    if inherited:
                        scope["OS-INHERIT:inherited_to"] = "projects"
                    result.append(row(user={"id": uid}, role=source.role, scope=scope))
        return result

    def assign(self, role, *, user=None, group=None, project=None, domain=None, os_inherit_extension_inherited=False):
        self.calls.append(("grant", role, user, group, project, domain, os_inherit_extension_inherited))
        added = grant(
            role, user=user, group=group, project=project, domain=domain, inherited=os_inherit_extension_inherited
        )
        if not any(vars(r) == vars(added) for r in self.raw):
            self.raw.append(added)

    def revoke(self, role, *, user=None, project=None, **_):
        self.calls.append(("revoke", role, user, project))
        self.raw = [
            r
            for r in self.raw
            if not (
                r.role["id"] == role
                and getattr(r, "user", {}).get("id") == user
                and r.scope.get("project", {}).get("id") == project
            )
        ]

    def create_domain(self, *, name, description="", enabled, **extra):
        self.calls.append(("domain.create", enabled))
        d = row(id="created-domain", name=name, description=description, enabled=enabled, **extra)
        self.domain_rows[d.id] = d
        return d

    def update_domain(self, id, *, enabled=None, **attrs):
        if enabled is not None:
            self.calls.append(("domain.enable", enabled))
            attrs["enabled"] = enabled
        for key, value in attrs.items():
            setattr(self.domain_rows[id], key, value)
        return self.domain_rows[id]

    def delete_domain(self, id):
        if self.domain_rows[id].enabled:
            raise HTTPException(409, "Keystone domains must be disabled before deletion")
        self.calls.append(("domain.delete", id))
        del self.domain_rows[id]

    def create_project(self, *, name, domain, enabled, description, **extra):
        if not self.domain_rows[domain].enabled:
            raise HTTPException(409, "Keystone rejects projects beneath a disabled ancestor")
        self.calls.append(("project.create", domain))
        p = row(
            id="created-default" if name == "Default" else f"personal-{len(self.project_rows)}",
            name=name,
            domain_id=domain,
            enabled=enabled,
            parent_id=domain,
            description=description,
            **extra,
        )
        self.project_rows[p.id] = p
        return p

    def update_project(self, id, *, enabled):
        project = self.project_rows[id]
        if enabled and not self.domain_rows[project.domain_id].enabled:
            raise HTTPException(409, "Keystone rejects activation beneath a disabled ancestor")
        self.activation_snapshot = {
            "project_enabled": project.enabled,
            "direct_roles": {r.role["id"] for r in self.assignments(project=id)},
            "projection_members": set(self.members.get("projection-" + project.domain_id, set())),
        }
        self.calls.append(("project.enable", id, enabled))
        project.enabled = enabled
        return project

    def delete_project(self, id):
        self.calls.append(("project.delete", id))
        self.raw = [r for r in self.raw if r.scope.get("project", {}).get("id") != id]
        del self.project_rows[id]

    def create_group(self, *, name, domain, description):
        self.calls.append(("group.create", domain))
        g = row(id="projection-" + domain, name=name, domain_id=domain, description=description)
        self.group_rows[g.id] = g
        self.members[g.id] = set()
        return g

    def delete_group(self, id):
        self.calls.append(("group.delete", id))
        self.raw = [r for r in self.raw if getattr(r, "group", {}).get("id") != id]
        del self.group_rows[id]
        del self.members[id]

    def add_group(self, user, group):
        self.calls.append(("group.add", user, group))
        self.members[group].add(user)

    def remove_group(self, user, group):
        self.calls.append(("group.remove", user, group))
        self.members[group].remove(user)


@pytest.fixture
def domain_native(monkeypatch):
    native = Directory()
    conn = row(close=lambda: None)
    native.conn = conn
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: native)
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: conn)
    monkeypatch.setattr(
        identity_roles, "load_catalog", lambda _: identity_roles._catalog(native.role_rows, native.edges)
    )
    native.lock_depth = 0

    @asynccontextmanager
    async def lock(_):
        assert native.lock_depth == 0, "nested graph lease"
        native.lock_depth += 1

        async def owned():
            assert native.lock_depth == 1

        try:
            yield row(assert_owned=owned)
        finally:
            native.lock_depth -= 1

    monkeypatch.setattr(identity_roles, "_graph_lock", lock)
    monkeypatch.setattr(domain_projects, "apply_default_quotas", AsyncMock())
    return native


@pytest.fixture
def login_proofs(domain_native, monkeypatch):
    """Prove stored continuity, not upstream token validity after revocation events."""
    stored = {}
    revoked = []
    monkeypatch.setattr(keystone, "revoke_token", revoked.append)

    async def store(user_id):
        exp = int(time.time()) + 3600
        family, current = f"login-{user_id}", f"refresh-{user_id}"
        home = domain_native.user_rows[user_id].domain_id
        attrs = {
            "domain_id": home,
            "identity_domain_id": home,
            "origin_ip": "192.0.2.10",
            "origin_fp": "original-browser",
        }
        assert await session_store.store_session(family, f"native-{user_id}", "", user_id, exp, **attrs)
        assert await session_store.store_session(
            current,
            f"native-{user_id}",
            "",
            user_id,
            exp,
            previous_jti=family,
            timeout_seconds=3600,
            **attrs,
        )
        stored[user_id] = await session_store.get_session(current)

    async def preserved():
        redis = await session_store._get_redis()
        for uid, before in stored.items():
            family, current = f"login-{uid}", f"refresh-{uid}"
            assert before["family_id"] == family
            assert before["keystone_token"] == f"native-{uid}"
            assert await session_store.get_session(current) == before
            assert await session_store.get_session(family) is None
            assert await redis.get(f"{session_store._FAMILY_PREFIX}{family}") == current
            for jti in (family, current):
                assert await redis.get(f"{session_store._FAMILY_ALIAS_PREFIX}{jti}") == family
            assert await redis.smembers(session_store._user_index_key(uid)) == {current}
            assert await redis.ttl(session_store._key(current)) > 0
        assert not revoked

    def validation_key(user_id, project_id="default-a"):
        token_hash = hashlib.sha256(f"native-{user_id}".encode()).hexdigest()
        return f"afterglow:session:{token_hash}:{project_id}"

    async def roles(user_id, project_id="default-a"):
        """Populate legacy validation entries to exercise eviction, not authentication."""
        return await cache.cached_call(
            validation_key(user_id, project_id),
            60,
            lambda: sorted(
                project_service._expanded_role_ids(
                    domain_native.assignments(project=project_id, effective=True),
                    domain_projects._catalog(domain_native),
                    user_id,
                )
            ),
        )

    async def manager(user_id, domain_id="tenant-a"):
        return await cache.cached_call(
            f"afterglow:identity:domain-context:{user_id}:{domain_id}",
            60,
            lambda: domain_scope.has_scope_authority(user_id, domain_id=domain_id),
        )

    return row(store=store, preserved=preserved, roles=roles, manager=manager, validation_key=validation_key)


def test_read_manager_is_Default_effective_not_home_domain_or_admin(domain_native):
    n = domain_native
    n.raw += [grant("admin", user="ordinary", domain="tenant-a"), grant("admin", user="other", project="work-b")]
    assert domain_projects.has_manager("creator", "tenant-a")
    assert not domain_projects.has_manager("ordinary", "tenant-a")
    assert not domain_projects.has_manager("other", "tenant-b")
    assert not domain_projects.has_manager("creator", "tenant-b")
    assert n.calls == []


@pytest.mark.parametrize("source", ["group", "domain-inherit", "ancestor-inherit", "inference"])
def test_actual_external_manager_sources_work(domain_native, source):
    n = domain_native
    n.raw = []
    if source == "group":
        n.group_rows["external"] = row(id="external", name="external", domain_id="home", description="")
        n.members["external"] = {"creator"}
        n.raw = [grant("manager", group="external", project="default-a")]
    elif source == "domain-inherit":
        n.raw = [grant("manager", user="creator", domain="tenant-a", inherited=True)]
    elif source == "ancestor-inherit":
        n.project_rows["default-a"].parent_id = "work-a"
        n.raw = [grant("manager", user="creator", project="work-a", inherited=True)]
    else:
        n.raw = [grant("alias", user="creator", project="default-a")]
    assert domain_projects.has_manager("creator", "tenant-a")
    assert not domain_projects.has_manager("creator", "tenant-b")
    assert n.calls == []


@pytest.mark.asyncio
async def test_creation_anchors_exact_cross_identity_creator_and_reader(domain_native):
    n = domain_native
    result = await domain_projects.create_domain(
        name="Created", description="tenant", enabled=True, creator_id="creator"
    )
    assert result["default_project_id"] == "created-default"
    assert n.project_rows["created-default"].domain_id == "created-domain"
    assert n.user_rows["creator"].domain_id == "home"
    assert domain_projects.has_manager("creator", "created-domain")
    direct = n.assignments(project="created-default")
    assert {r.role["id"] for r in direct if getattr(r, "user", {}).get("id") == "creator"} == {
        "manager",
        "project_reader",
        "project_owner",
    }
    projection = n.members["projection-created-domain"]
    assert projection == {"creator"}
    assert n.calls.index(("domain.create", True)) < n.calls.index(("project.create", "created-domain"))
    assert n.calls[-1] == ("project.enable", "created-default", True)
    assert n.activation_snapshot == {
        "project_enabled": False,
        "direct_roles": {"manager", "project_owner", "project_reader"},
        "projection_members": {"creator"},
    }
    assert not any(r.scope.get("domain", {}).get("id") == "created-domain" and r.role["id"] == "manager" for r in n.raw)


@pytest.mark.asyncio
async def test_requested_disabled_domain_is_provisioned_but_not_activated(domain_native):
    result = await domain_projects.create_domain(name="Disabled", description="", enabled=False, creator_id="creator")
    assert result["enabled"] is False
    assert "created-default" in domain_native.project_rows
    assert not domain_projects.has_manager("creator", "created-domain")
    assert ("domain.enable", True) not in domain_native.calls
    assert domain_native.calls[-1] == ("domain.enable", False)
    assert domain_native.project_rows["created-default"].enabled is True


@pytest.mark.asyncio
async def test_login_grants_only_reader_then_projection_covers_existing_and_future_projects(domain_native):
    n = domain_native
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    own = [r.role["id"] for r in n.raw if getattr(r, "user", {}).get("id") == "ordinary"]
    assert own == ["project_reader"]
    assert not domain_projects.has_manager("ordinary", "tenant-a")
    for target in ("work-a", "default-a"):
        assert any(
            r.user["id"] == "creator" and r.role["id"] == "project_reader"
            for r in n.assignments(project=target, effective=True)
        )
    n.project_rows["future"] = row(id="future", name="Future", enabled=True, domain_id="tenant-a", parent_id="tenant-a")
    assert [r.role["id"] for r in n.assignments(project="future", user="creator", effective=True)] == ["project_reader"]
    assert not n.assignments(project="work-b", user="creator", effective=True)
    assert not any(r.role["id"] == "manager" and r.scope.get("project", {}).get("id") != "default-a" for r in n.raw)


@pytest.mark.asyncio
async def test_first_login_creates_owner_reader_without_manager_and_later_user_only_reader(domain_native):
    n = domain_native
    del n.project_rows["default-b"]
    n.user_rows["second"].domain_id = "tenant-b"
    assert domain_projects.default_project("tenant-b") is None
    assert n.calls == []  # Directory lookup never provisions.
    await domain_projects.ensure_login_access("other", "tenant-b")
    project = domain_projects.default_project("tenant-b")
    assert project["id"] == "created-default"
    assert n.activation_snapshot == {
        "project_enabled": False,
        "direct_roles": {"project_owner", "project_reader"},
        "projection_members": set(),
    }
    await domain_projects.ensure_login_access("second", "tenant-b")
    await domain_projects.ensure_login_access("other", "tenant-b")
    assert n.calls.count(("project.create", "tenant-b")) == 1
    assert {r.role["id"] for r in n.assignments(project=project["id"], user="other")} == {
        "project_owner",
        "project_reader",
    }
    assert {r.role["id"] for r in n.assignments(project=project["id"], user="second")} == {"project_reader"}
    state = await project_service._ownership_state(n, domain_projects._catalog(n), project["id"])
    assert state["status"] == "unique" and state["owner_user_id"] == "other"
    assert not domain_projects.has_manager("other", "tenant-b")
    assert not domain_projects.has_manager("second", "tenant-b")
    assert n.members["projection-tenant-b"] == set()
    domain_projects.apply_default_quotas.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_bootstrap_retains_manager_and_unique_creator_owner(domain_native, login_proofs):
    n = domain_native
    await login_proofs.store("creator")
    assert not await login_proofs.manager("creator", "tenant-b")
    del n.project_rows["default-b"]
    result = await domain_projects.bootstrap_default("tenant-b", creator_id="creator")
    assert result["creator_id"] == "creator"
    assert domain_projects.has_manager("creator", "tenant-b")
    assert not domain_projects.has_manager("other", "tenant-b")
    assert {r.role["id"] for r in n.assignments(project=result["default_project_id"], user="creator")} == {
        "manager",
        "project_owner",
        "project_reader",
    }
    assert await login_proofs.manager("creator", "tenant-b")
    await login_proofs.preserved()
    with pytest.raises(HTTPException) as error:
        await domain_projects.bootstrap_default("tenant-b", creator_id="other")
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_projection_resync_removes_revoked_managers_and_live_project_fence_rejects_stale(
    domain_native,
    login_proofs,
):
    n = domain_native
    await domain_projects.ensure_login_access("creator", "tenant-a")
    await login_proofs.store("creator")
    assert "reader" in await login_proofs.roles("creator", "work-a")
    assert await login_proofs.manager("creator")
    n.raw = [r for r in n.raw if r.role["id"] != "manager"]
    assert n.members["projection-tenant-a"] == {"creator"}
    assert not domain_projects.has_manager("creator", "tenant-a")
    domain_projects.assert_membership("creator", "tenant-a")  # Durable Default reader.
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_project_membership("creator", "work-a")
    assert error.value.status_code == 403
    await domain_projects.sync_manager_access("tenant-a")
    assert n.members["projection-tenant-a"] == set()
    assert not n.assignments(project="work-a", user="creator", effective=True)
    assert await login_proofs.roles("creator", "work-a") == []
    assert not await login_proofs.manager("creator")
    domain_projects.assert_membership("creator", "tenant-a")
    await login_proofs.preserved()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["group", "domain-inherit", "ancestor-inherit", "inference"])
async def test_projection_sync_external_manager_changes_preserve_stored_login(domain_native, login_proofs, source):
    n = domain_native
    await domain_projects.sync_manager_access("tenant-a")
    for uid in ("creator", "second", "ordinary"):
        await login_proofs.store(uid)
    assert not await login_proofs.manager("second")
    assert await login_proofs.roles("second", "work-a") == []
    if source == "group":
        n.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
        n.members["external"] = {"second"}
        added = grant("manager", group="external", project="default-a")
    elif source == "domain-inherit":
        added = grant("manager", user="second", domain="tenant-a", inherited=True)
    elif source == "ancestor-inherit":
        n.project_rows["default-a"].parent_id = "work-a"
        added = grant("manager", user="second", project="work-a", inherited=True)
    else:
        added = grant("alias", user="second", project="default-a")
    n.raw.append(added)
    assert domain_scope.has_scope_authority("second", domain_id="tenant-a")
    await domain_projects.sync_manager_access("tenant-a")
    assert n.members["projection-tenant-a"] == {"creator", "second"}
    assert await login_proofs.manager("second")
    assert "reader" in await login_proofs.roles("second", "work-a")
    domain_projects.assert_project_membership("second", "work-a")
    await login_proofs.preserved()

    n.raw.remove(added)
    assert not domain_scope.has_scope_authority("second", domain_id="tenant-a")
    with pytest.raises(HTTPException) as denied:
        domain_projects.assert_project_membership("second", "work-a")
    assert denied.value.status_code == 403  # Stale projection cannot restore authority.
    await domain_projects.sync_manager_access("tenant-a")
    assert n.members["projection-tenant-a"] == {"creator"}
    assert not await login_proofs.manager("second")
    assert await login_proofs.roles("second", "work-a") == []
    await login_proofs.preserved()


def test_multidomain_membership_excludes_stale_projection_and_disabled_resources(domain_native):
    n = domain_native
    n.raw += [grant("reader", user="creator", project="work-b")]
    assert {d["id"] for d in domain_projects.accessible_domains("creator")} == {"home", "tenant-a", "tenant-b"}
    n.project_rows["work-b"].enabled = False
    assert {d["id"] for d in domain_projects.accessible_domains("creator")} == {"home", "tenant-a"}
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_membership("ordinary", "tenant-b")
    assert error.value.status_code == 403
    n.domain_rows["home"].enabled = False
    with pytest.raises(HTTPException):
        domain_projects.accessible_domains("creator")


@pytest.mark.parametrize(
    "change",
    [
        {"user_id": "creator", "project_id": "default-a", "role_id": "manager", "remove_assignment": True},
        {"disabled_user_ids": ("creator",)},
        {"disabled_domain_id": "home"},
    ],
)
def test_last_active_manager_cannot_be_removed(domain_native, change):
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_managers_remain(**change)
    assert error.value.status_code == 409 and error.value.detail == "last_domain_manager"
    assert domain_native.calls == []


def test_last_manager_simulation_preserves_independent_group_and_inference_sources(domain_native):
    n = domain_native
    n.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
    n.members["external"] = {"creator", "second"}
    n.raw = [grant("alias", group="external", project="default-a")]
    assert domain_projects.assert_managers_remain(group_id="external", remove_group_user_id="creator") == {"tenant-a"}
    with pytest.raises(HTTPException):
        domain_projects.assert_managers_remain(group_id="external", delete_group=True)
    with pytest.raises(HTTPException):
        domain_projects.assert_managers_remain(prior_id="alias", implied_id="manager", remove_edge=True)
    n.raw.append(grant("manager", user="second", project="default-a"))
    assert "tenant-a" in domain_projects.assert_managers_remain(
        prior_id="alias", implied_id="manager", remove_edge=True
    )
    n.user_rows["second"].enabled = False
    with pytest.raises(HTTPException):
        domain_projects.assert_managers_remain(disabled_user_ids=("creator",))


@pytest.mark.parametrize("source", ["domain", "ancestor"])
def test_inherited_last_manager_simulation_and_unknown_provider_fail_closed(domain_native, source):
    n = domain_native
    if source == "domain":
        n.raw = [grant("alias", user="creator", domain="tenant-a", inherited=True)]
    else:
        n.project_rows["default-a"].parent_id = "work-a"
        n.raw = [grant("alias", user="creator", project="work-a", inherited=True)]
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_managers_remain(disabled_user_ids=("creator",))
    assert error.value.detail == "last_domain_manager"
    original = n.role_assignments.list
    n.role_assignments.list = lambda **kw: [] if not kw else original(**kw)
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_managers_remain(disabled_user_ids=("creator",))
    assert error.value.status_code == 503


def test_manager_assignment_and_inference_addition_are_Default_only(domain_native):
    n = domain_native
    domain_projects.assert_manager_assignment("default-a", "alias")
    with pytest.raises(HTTPException):
        domain_projects.assert_manager_assignment("work-a", "alias")
    n.raw.append(grant("reader", user="other", project="work-b"))
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_managers_remain(prior_id="reader", implied_id="manager")
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_canonical_role_and_native_reader_hierarchy_validated_before_any_write(domain_native):
    n = domain_native
    n.edges = [e for e in n.edges if e["prior_role"]["id"] != "project_reader"]
    with pytest.raises(HTTPException):
        await domain_projects.create_domain(name="No", description="", enabled=True, creator_id="creator")
    assert n.calls == []
    n.role_rows.append(row(id="duplicate", name="Manager", domain_id=None))
    with pytest.raises(HTTPException) as error:
        domain_projects.has_manager("creator", "tenant-a")
    assert error.value.status_code == 503


@pytest.fixture
def creator_native(domain_native):
    domain_native.role_rows.append(row(id="project_creator", name="project_creator", domain_id=None))
    domain_native.raw.append(grant("project_creator", user="ordinary", project="default-a"))
    return domain_native


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["direct", "group", "implication", "domain-inherited", "ancestor-inherited"])
async def test_creator_capability_proves_current_effective_default_sources(creator_native, source):
    n = creator_native
    n.raw = [r for r in n.raw if r.role["id"] != "project_creator"]
    if source == "group":
        n.group_rows["creators"] = row(id="creators", name="Creators", domain_id="tenant-a")
        n.members["creators"] = {"ordinary"}
        n.raw.append(grant("project_creator", group="creators", project="default-a"))
    elif source == "implication":
        n.role_rows.append(row(id="creator-alias", name="creator-alias", domain_id=None))
        n.edges.append({"prior_role": {"id": "creator-alias"}, "implies": [{"id": "project_creator"}]})
        n.raw.append(grant("creator-alias", user="ordinary", project="default-a"))
    elif source == "domain-inherited":
        n.raw.append(grant("project_creator", user="ordinary", domain="tenant-a", inherited=True))
    elif source == "ancestor-inherited":
        n.project_rows["default-a"].parent_id = "work-a"
        n.raw.append(grant("project_creator", user="ordinary", project="work-a", inherited=True))
    else:
        n.raw.append(grant("project_creator", user="ordinary", project="default-a"))
    assert await project_service.can_create_project("ordinary", "tenant-a")
    assert not domain_projects.has_manager("ordinary", "tenant-a")
    n.raw = [r for r in n.raw if r.role["id"] not in {"project_creator", "creator-alias"}]
    assert not await project_service.can_create_project("ordinary", "tenant-a")
    assert n.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["legacy-domain", "ordinary-project", "other-default", "missing-default"])
async def test_creator_wrong_scope_never_authorizes_creation(creator_native, scope):
    n = creator_native
    n.raw = []
    if scope == "legacy-domain":
        n.raw.append(grant("project_creator", user="ordinary", domain="tenant-a"))
    elif scope == "ordinary-project":
        n.raw.append(grant("project_creator", user="ordinary", project="work-a"))
    elif scope == "other-default":
        n.raw.append(grant("project_creator", user="ordinary", project="default-b"))
    else:
        del n.project_rows["default-a"]
    assert not await project_service.can_create_project("ordinary", "tenant-a")
    assert n.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "disabled-default",
        "duplicate-default",
        "lookalike-default",
        "duplicate-role",
        "lookalike-role",
        "disabled-user",
        "disabled-home",
        "missing-provenance",
        "wrong-effective-scope",
    ],
)
async def test_creator_native_authority_faults_fail_closed(creator_native, fault):
    n = creator_native
    if fault == "disabled-default":
        n.project_rows["default-a"].enabled = False
    elif fault == "duplicate-default":
        n.project_rows["duplicate"] = row(id="duplicate", name="Default", domain_id="tenant-a", enabled=True)
    elif fault == "lookalike-default":
        n.project_rows["default-a"].name = "default"
    elif fault == "duplicate-role":
        n.role_rows.append(row(id="duplicate-role", name="Project_Creator", domain_id=None))
    elif fault == "lookalike-role":
        n.role_rows[-1].name = "Project_Creator"
    elif fault == "disabled-user":
        n.user_rows["ordinary"].enabled = False
    elif fault == "disabled-home":
        n.domain_rows["tenant-a"].enabled = False
    else:
        original = n.role_assignments.list

        def broken(**kwargs):
            if fault == "missing-provenance" and not kwargs:
                return [r for r in n.raw if r.role["id"] != "project_creator"]
            rows = original(**kwargs)
            if fault == "wrong-effective-scope" and kwargs.get("project") == "default-a" and kwargs.get("effective"):
                rows.append(grant("project_creator", user="ordinary", project="work-a"))
            return rows

        n.role_assignments.list = broken
    with pytest.raises(HTTPException) as denied:
        await project_service.can_create_project("ordinary", "tenant-a")
    assert denied.value.status_code in {401, 403, 503}
    assert n.calls == []


def test_creator_project_assignment_targets_only_canonical_default(creator_native):
    n = creator_native
    domain_projects.assert_creator_assignment("default-a", "project_creator")
    with pytest.raises(HTTPException) as denied:
        domain_projects.assert_creator_assignment("work-a", "project_creator")
    assert denied.value.detail == "project_creator_requires_default_project"
    n.role_rows.append(row(id="creator-alias", name="creator-alias", domain_id=None))
    n.edges.append({"prior_role": {"id": "creator-alias"}, "implies": [{"id": "project_creator"}]})
    with pytest.raises(HTTPException) as denied:
        domain_projects.assert_creator_assignment("work-a", "creator-alias")
    assert denied.value.status_code == 422
    assert n.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["group", "implication", "domain-inherited"])
async def test_creator_delegation_preserves_non_direct_effective_grants(creator_native, source):
    n = creator_native
    n.raw = [r for r in n.raw if r.role["id"] != "project_creator"]
    if source == "group":
        n.group_rows["creators"] = row(id="creators", name="Creators", domain_id="tenant-a")
        n.members["creators"] = {"ordinary"}
        n.raw.append(grant("project_creator", group="creators", project="default-a"))
    elif source == "implication":
        n.role_rows.append(row(id="creator-alias", name="creator-alias", domain_id=None))
        n.edges.append({"prior_role": {"id": "creator-alias"}, "implies": [{"id": "project_creator"}]})
        n.raw.append(grant("creator-alias", user="ordinary", project="default-a"))
    else:
        n.raw.append(grant("project_creator", user="ordinary", domain="tenant-a", inherited=True))
    listed = await project_service.project_creators("tenant-a", "creator")
    assert listed["users"][0]["id"] == "ordinary"
    assert listed["users"][0]["direct"] is False and listed["users"][0]["source"] == "inherited"
    unchanged = await project_service.change_project_creator("tenant-a", "ordinary", False, "creator")
    assert unchanged["users"] == listed["users"]
    assert await project_service.can_create_project("ordinary", "tenant-a")
    assert n.calls == []


@pytest.mark.asyncio
async def test_creator_listing_reuses_one_effective_default_assignment_read_for_500_users(creator_native):
    n = creator_native
    n.raw = [source for source in n.raw if source.role["id"] != "project_creator"]
    expected = {f"scale-creator-{index:03d}" for index in range(500)}
    for uid in sorted(expected):
        n.user_rows[uid] = row(id=uid, name=uid, enabled=True, domain_id="tenant-a")
        n.raw.append(grant("project_creator", user=uid, project="default-a"))
    n.read_calls.clear()
    listed = await project_service.project_creators("tenant-a", "creator")
    assert {user["id"] for user in listed["users"]} == expected
    assignment_reads = [call for call in n.read_calls if call[0] == "assignments.list"]
    assert sum(call[1] == "default-a" and call[4] is True for call in assignment_reads) == 1
    assert sum(call[1] == "default-a" and call[4] is False for call in assignment_reads) == 1
    assert not any(call[2] in expected for call in assignment_reads)
    assert all(user["direct"] is True and user["source"] == "direct" for user in listed["users"])
    assert n.calls == []


@pytest.mark.parametrize("kind", ["ambiguous", "disabled", "case", "foreign"])
def test_Default_lookup_fails_closed_on_provider_or_identity_uncertainty(domain_native, kind):
    n = domain_native
    if kind == "ambiguous":
        n.project_rows["duplicate"] = row(id="duplicate", name="Default", domain_id="tenant-a", enabled=True)
    elif kind == "disabled":
        n.project_rows["default-a"].enabled = False
    elif kind == "case":
        n.project_rows["default-a"].name = "default"
    else:
        n.projects.list = lambda **_: list(n.project_rows.values())
    with pytest.raises(HTTPException) as error:
        domain_projects.default_project("tenant-a")
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_tampered_projection_foreign_assignment_never_becomes_domain_authority(domain_native):
    n = domain_native
    await domain_projects.sync_manager_access("tenant-a")
    gid = "projection-tenant-a"
    n.raw.append(grant("manager", group=gid, project="work-b"))
    assert {d["id"] for d in domain_projects.accessible_domains("creator")} == {"home", "tenant-a"}
    with pytest.raises(HTTPException):
        domain_projects.assert_project_membership("creator", "work-b")
    with pytest.raises(HTTPException) as error:
        await domain_projects.sync_manager_access("tenant-a")
    assert error.value.status_code == 503
    with pytest.raises(HTTPException):
        domain_projects.assert_not_projection_group(gid)


@pytest.mark.asyncio
async def test_manager_change_native_readback_and_last_manager_are_protected(domain_native, login_proofs):
    n = domain_native
    n.raw.append(grant("reader", user="second", project="default-a"))
    for uid in ("creator", "second", "ordinary"):
        await login_proofs.store(uid)
    await domain_projects.ensure_login_access("creator", "tenant-a")
    assert await login_proofs.manager("creator")
    assert not await login_proofs.manager("second")
    assert "reader" in await login_proofs.roles("second")
    assert "manager" in await login_proofs.roles("creator")
    with pytest.raises(HTTPException) as error:
        await domain_projects.change_manager("tenant-a", "creator", "manager", remove=True, actor={})
    assert error.value.detail == "last_domain_manager"
    await login_proofs.preserved()
    await domain_projects.change_manager("tenant-a", "second", "manager", remove=False, actor={})
    assert await login_proofs.manager("second")
    assert "manager" in await login_proofs.roles("second")
    domain_projects.assert_project_membership("second", "work-a")
    await login_proofs.preserved()
    await domain_projects.change_manager("tenant-a", "creator", "manager", remove=True, actor={})
    assert not domain_projects.has_manager("creator", "tenant-a")
    assert n.members["projection-tenant-a"] == {"second"}
    assert domain_projects.has_manager("second", "tenant-a")
    assert not await login_proofs.manager("creator")
    assert "manager" not in await login_proofs.roles("creator")
    assert "reader" in await login_proofs.roles("creator")
    domain_projects.assert_project_membership("creator", "default-a")
    with pytest.raises(HTTPException) as denied:
        domain_projects.assert_project_membership("creator", "work-a")
    assert denied.value.status_code == 403
    await login_proofs.preserved()
    assert n.lock_depth == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("remove", [False, True])
@pytest.mark.parametrize("outcome", ["readback-mismatch", "lost-response", "cancelled"])
async def test_manager_change_uncertainty_and_cancellation_preserve_login_and_current_authority(
    domain_native,
    login_proofs,
    monkeypatch,
    remove,
    outcome,
):
    n = domain_native
    n.raw.append(grant("reader", user="second", project="default-a"))
    if remove:
        n.raw.append(grant("manager", user="second", project="default-a"))
    await domain_projects.sync_manager_access("tenant-a")
    await login_proofs.store("second")
    assert await login_proofs.manager("second") is remove
    assert ("manager" in await login_proofs.roles("second")) is remove
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    method = "revoke" if remove else "grant"
    original = getattr(n.roles, method)

    def write(*args, **kwargs):
        if outcome == "readback-mismatch":
            return None
        original(*args, **kwargs)
        if outcome == "lost-response":
            raise HTTPException(503, "synthetic_lost_response")
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5), "provider write was not released"

    monkeypatch.setattr(n.roles, method, write)
    request = asyncio.create_task(
        domain_projects.change_manager("tenant-a", "second", "manager", remove=remove, actor={})
    )
    try:
        if outcome == "cancelled":
            await asyncio.wait_for(entered.wait(), 5)
            request.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await request
        else:
            with pytest.raises(HTTPException) as error:
                await request
            assert error.value.status_code == 503
    finally:
        release.set()
        if not request.done():
            await request

    # Even a missing readback or cancelled/lost response must evict old snapshots.
    redis = await session_store._get_redis()
    assert await redis.get(login_proofs.validation_key("second")) is None
    expected = remove if outcome == "readback-mismatch" else not remove
    assert domain_scope.has_scope_authority("second", domain_id="tenant-a") is expected
    assert await login_proofs.manager("second") is expected
    assert ("second" in n.members["projection-tenant-a"]) is expected
    assert ("manager" in await login_proofs.roles("second")) is expected
    if expected:
        domain_projects.assert_project_membership("second", "work-a")
    else:
        with pytest.raises(HTTPException) as denied:
            domain_projects.assert_project_membership("second", "work-a")
        assert denied.value.status_code == 403
    assert n.lock_depth == 0
    await login_proofs.preserved()


@pytest.mark.asyncio
async def test_shared_mutation_projection_does_not_reacquire_lease(domain_native):
    n = domain_native
    async with domain_projects._mutation() as context:
        await domain_projects.sync_manager_access("tenant-a", mutation=context)
    assert n.members["projection-tenant-a"] == {"creator"}


def test_Default_delete_rename_disable_are_immutable(domain_native):
    for change in ({"delete": True}, {"attrs": {"name": "Moved"}}, {"attrs": {"is_enabled": False}}):
        with pytest.raises(HTTPException) as error:
            domain_projects.assert_default_immutable("default-a", **change)
        assert error.value.status_code == 422
    domain_projects.assert_default_immutable("default-a", attrs={"description": "okay"})
    domain_projects.assert_default_immutable("work-a", delete=True)


@pytest.mark.asyncio
async def test_failed_initial_owner_retains_disabled_exact_objects_and_unknown_intent(domain_native):
    from app.services import project_ownership_journal as journal

    n = domain_native

    def failed_grant(*_, **__):
        raise HTTPException(503, "synthetic_provider_failure")

    n.roles.grant = failed_grant
    with pytest.raises(HTTPException) as error:
        await domain_projects.create_domain(name="Failure", description="", enabled=True, creator_id="creator")
    assert error.value.status_code == 503
    assert n.project_rows["created-default"].enabled is False
    assert n.domain_rows["created-domain"].enabled is False
    assert not any(c[0] in {"project.delete", "domain.delete"} for c in n.calls)
    operation = await journal.get("created-default")
    assert operation["status"] == "unknown"
    assert not any(call == ("domain.enable", True) for call in n.calls)


@pytest.mark.asyncio
async def test_unknown_domain_creation_response_never_retries_or_deletes_by_name(domain_native):
    n = domain_native
    create = n.domains.create

    def lost_response(**kwargs):
        create(**kwargs)
        raise HTTPException(503, "synthetic_lost_response")

    n.domains.create = lost_response
    with pytest.raises(HTTPException):
        await domain_projects.create_domain(name="Unknown", description="", enabled=True, creator_id="creator")
    assert n.calls == [("domain.create", True)]
    assert n.domain_rows["created-domain"].enabled is True
    assert not n.projects_list(domain="created-domain")
    assert not n.groups_list(domain="created-domain")
    assert "created-domain" not in {d["id"] for d in domain_projects.accessible_domains("creator")}


@pytest.mark.asyncio
async def test_projection_native_write_readback_failure_evicts_validation_and_preserves_login(
    domain_native,
    login_proofs,
):
    n = domain_native
    await login_proofs.store("creator")
    assert await login_proofs.roles("creator", "work-a") == []
    n.users.add_to_group = lambda *args: None
    with pytest.raises(HTTPException) as error:
        await domain_projects.sync_manager_access("tenant-a")
    assert error.value.status_code == 503
    assert domain_projects.has_manager("creator", "tenant-a")
    assert n.members["projection-tenant-a"] == set()
    redis = await session_store._get_redis()
    assert await redis.get(login_proofs.validation_key("creator", "work-a")) is None
    assert await login_proofs.roles("creator", "work-a") == []
    with pytest.raises(HTTPException) as denied:
        domain_projects.assert_project_membership("creator", "work-a")
    assert denied.value.status_code == 403
    await login_proofs.preserved()


def test_exact_system_boolean_and_mapping_Default_shapes(domain_native):
    n = domain_native
    n.project_rows["default-a"] = vars(n.project_rows["default-a"])
    n.projects.list = lambda **kw: [n.project_rows["default-a"]]
    assert domain_projects.default_project("tenant-a")["id"] == "default-a"
    catalog = domain_projects._catalog(n)
    malformed = row(user={"id": "creator"}, role={"id": "admin"}, scope={"system": {"all": 1}})
    with pytest.raises(HTTPException) as error:
        domain_projects._assignment(malformed, catalog, effective=True)
    assert error.value.status_code == 503


def test_graph_cannot_promote_Default_readers_or_remove_native_reader(domain_native):
    n = domain_native
    n.raw.append(grant("project_reader", user="ordinary", project="default-a"))
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_managers_remain(prior_id="project_reader", implied_id="manager")
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_managers_remain(prior_id="project_reader", implied_id="reader", remove_edge=True)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_domain_creation_preserves_existing_creator_session_for_domain_switch(domain_native, login_proofs):
    await login_proofs.store("creator")
    result = await domain_projects.create_domain(name="Switchable", description="", enabled=True, creator_id="creator")
    await login_proofs.preserved()
    domain_projects.assert_membership("creator", result["id"])
    await domain_projects.ensure_login_access("creator", result["id"])
    domain_projects.assert_project_membership("creator", result["default_project_id"])
    await login_proofs.preserved()


@pytest.mark.asyncio
async def test_existing_Default_login_never_adopts_or_replaces_native_owner(domain_native):
    n = domain_native
    n.raw.append(grant("project_owner", user="creator", project="default-a"))
    before = [vars(r) for r in n.assignments(project="default-a", user="creator")]
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    assert [vars(r) for r in n.assignments(project="default-a", user="creator")] == before
    assert not any(c[0] == "grant" and c[1] == "project_owner" for c in n.calls)
    assert {r.role["id"] for r in n.assignments(project="default-a", user="ordinary")} == {"project_reader"}


@pytest.mark.asyncio
async def test_reenabled_external_manager_discovery_and_projection_preserve_login(domain_native, login_proofs):
    n = domain_native
    await login_proofs.store("creator")
    n.raw.append(grant("manager", user="second", project="default-a"))
    await domain_projects.sync_manager_access("tenant-a")
    assert await login_proofs.manager("creator")
    assert domain_projects.assert_managers_remain(user_id="creator", disabled_user_ids={"creator"}) == {"tenant-a"}
    n.user_rows["creator"].enabled = False
    await domain_projects.sync_manager_access("tenant-a")
    assert n.members["projection-tenant-a"] == {"second"}
    assert not await login_proofs.manager("creator")
    with pytest.raises(HTTPException) as denied:
        domain_projects.assert_project_membership("creator", "work-a")
    assert denied.value.status_code == 401
    await login_proofs.preserved()
    assert domain_projects.assert_managers_remain(user_id="creator") == {"tenant-a"}
    assert domain_projects.assert_managers_remain(changed_domain_id="home") == {"tenant-a"}
    n.user_rows["creator"].enabled = True
    await domain_projects.sync_manager_access("tenant-a")
    assert n.members["projection-tenant-a"] == {"creator", "second"}
    assert await login_proofs.manager("creator")
    domain_projects.assert_project_membership("creator", "work-a")
    await login_proofs.preserved()


def test_harmless_graph_edit_avoids_native_recipient_reads(domain_native):
    n = domain_native
    n.role_rows.append(row(id="audit", name="audit", domain_id=None))
    catalog = domain_projects._catalog(n)

    def no_native_reads(*_, **__):
        raise AssertionError("unchanged manager role expansion must avoid recipient reads")

    n.role_assignments.list = no_native_reads
    n.domains.list = no_native_reads
    assert (
        domain_projects.assert_managers_remain(catalog=catalog, prior_id="project_reader", implied_id="audit") == set()
    )


def test_native_fixture_rejects_project_creation_beneath_disabled_domain(domain_native):
    n = domain_native
    n.domain_rows["tenant-b"].enabled = False
    for project_enabled in (False, True):
        with pytest.raises(HTTPException) as error:
            n.projects.create(name="Invalid", domain="tenant-b", enabled=project_enabled, description="")
        assert error.value.status_code == 409
    assert "created-default" not in n.project_rows


@pytest.mark.parametrize("check", ["domain", "project"])
def test_disabled_authenticated_subject_is_401_not_scope_denial(domain_native, check):
    domain_native.user_rows["creator"].enabled = False
    with pytest.raises(HTTPException) as error:
        if check == "domain":
            domain_projects.assert_membership("creator", "tenant-a")
        else:
            domain_projects.assert_project_membership("creator", "default-a")
    assert error.value.status_code == 401


@pytest.mark.parametrize("kind", ["home-domain", "working-domain", "project"])
def test_disabled_scope_still_returns_403_for_enabled_subject(domain_native, kind):
    if kind == "home-domain":
        domain_native.domain_rows["home"].enabled = False
    elif kind == "working-domain":
        domain_native.domain_rows["tenant-a"].enabled = False
    else:
        domain_native.project_rows["default-a"].enabled = False
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_project_membership("creator", "default-a")
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_id,working_domain,organization_enabled,open_signup,system_admin,client_admin_claim,expected",
    [
        ("creator", "tenant-a", True, False, False, False, 201),
        ("new-user", "home", True, True, False, False, 201),
        ("new-user", "home", True, False, False, False, 201),
        ("new-user", "home", False, True, False, True, 403),
        ("operator", "home", False, False, True, False, 201),
    ],
)
async def test_auth_domain_creation_uses_live_native_authority_and_independent_organization_policy(
    domain_native,
    monkeypatch,
    login_proofs,
    user_id,
    working_domain,
    organization_enabled,
    open_signup,
    system_admin,
    client_admin_claim,
    expected,
):
    import httpx
    from fastapi import FastAPI

    from app.api.deps import get_token_info
    from app.api.identity import auth as auth_api
    from app.services import activity

    n = domain_native
    n.user_rows["new-user"] = row(id="new-user", name="New", enabled=True, domain_id="home", email="new@example.com")
    if system_admin:
        n.raw.append(row(user={"id": user_id}, role={"id": "admin"}, scope={"system": {"all": True}}))
    settings = auth_api.get_settings()
    monkeypatch.setattr(settings.auth, "organization_creation_enabled", organization_enabled)
    monkeypatch.setattr(settings.auth, "public_signup_enabled", open_signup)
    monkeypatch.setattr(activity, "record", AsyncMock())
    await login_proofs.store(user_id)
    info = {
        "user_id": user_id,
        "username": user_id,
        "identity_domain_id": "home",
        "domain_id": working_domain,
        "project_id": "",
        "token": "existing-native-token",
        "is_system_admin": client_admin_claim,
    }
    application = FastAPI()
    application.include_router(auth_api.router, prefix="/api/v1/auth")
    application.dependency_overrides[get_token_info] = lambda: info
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as http:
        response = await http.post("/api/v1/auth/domains", json={"name": "Created", "description": "real-service-path"})
        assert response.status_code == expected
        assert response.headers["cache-control"] == "no-store, private"
        if expected == 201:
            result = response.json()
            assert result["default_project_id"] == "created-default"
            assert domain_projects.has_manager(user_id, result["id"])
            assert n.user_rows[user_id].domain_id == "home"
            direct = n.assignments(project=result["default_project_id"])
            assert {r.role["id"] for r in direct if getattr(r, "user", {}).get("id") == user_id} == {
                "manager",
                "project_owner",
                "project_reader",
            }
            domains = await http.get("/api/v1/auth/domains")
            assert domains.status_code == 200
            assert result["id"] in {d["id"] for d in domains.json()}
            await domain_projects.ensure_login_access(user_id, result["id"])
            domain_projects.assert_project_membership(user_id, result["default_project_id"])
        else:
            assert n.calls == []
    await login_proofs.preserved()
    assert info["identity_domain_id"] == "home" and info["domain_id"] == working_domain


@pytest.mark.asyncio
async def test_failed_projection_never_activates_staged_Default(domain_native):
    n = domain_native
    n.users.add_to_group = lambda *args: None
    with pytest.raises(HTTPException) as error:
        await domain_projects.create_domain(
            name="Failed projection", description="", enabled=True, creator_id="creator"
        )
    assert error.value.status_code == 503
    assert ("project.enable", "created-default", True) not in n.calls
    assert "created-default" not in n.project_rows and "created-domain" not in n.domain_rows
    assert "projection-created-domain" not in n.group_rows
    assert ("domain.enable", False) in n.calls


@pytest.mark.asyncio
async def test_unknown_group_creation_retains_known_domain_disabled_without_name_cleanup(domain_native):
    n = domain_native
    create_group = n.groups.create

    def lost_group_response(**kwargs):
        create_group(**kwargs)
        raise HTTPException(503, "synthetic_lost_group_response")

    n.groups.create = lost_group_response
    with pytest.raises(HTTPException):
        await domain_projects.create_domain(name="Unknown group", description="", enabled=True, creator_id="creator")
    assert n.domain_rows["created-domain"].enabled is False
    assert "created-default" not in n.project_rows
    assert "projection-created-domain" in n.group_rows
    assert n.calls.count(("group.create", "created-domain")) == 1
    assert not any(call[0] == "group.delete" for call in n.calls)
    assert ("project.enable", "created-default", True) not in n.calls


@pytest.mark.parametrize(
    "attrs",
    [
        {"name": "afterglow-default-managers-tenant-a"},
        {"description": "afterglow:default-manager-reader:v1:tenant-a"},
        {"name": "ordinary", "description": "afterglow:default-manager-reader:v1:tenant-b"},
    ],
)
def test_projection_identity_attributes_are_reserved_without_native_reads(attrs, monkeypatch):
    def no_native_reads():
        raise AssertionError("attribute guard must be pure")

    monkeypatch.setattr(keystone, "_get_admin_ks_client", no_native_reads)
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_projection_attributes(attrs)
    assert error.value.status_code == 403
    domain_projects.assert_projection_attributes({"name": "ordinary", "description": "team"})
    domain_projects.assert_projection_attributes({"description": None})


@pytest.mark.asyncio
async def test_domain_listing_many_effective_roles_reads_each_native_subject_once(domain_native):
    import httpx
    from fastapi import FastAPI

    from app.api.deps import get_token_info
    from app.api.identity import auth as auth_api

    n = domain_native
    n.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
    n.members["external"] = {"creator", "second"}
    n.project_rows["default-a"].parent_id = "work-a"
    for index in range(8):
        pid = f"child-{index}"
        n.project_rows[pid] = row(id=pid, name=pid, domain_id="tenant-a", enabled=True, parent_id="work-a")
    role_ids = [f"external-role-{index}" for index in range(20)]
    n.role_rows.extend(row(id=rid, name=rid, domain_id=None) for rid in role_ids)
    n.raw = [grant(rid, group="external", project="work-a", inherited=True) for rid in role_ids]

    application = FastAPI()
    application.include_router(auth_api.router, prefix="/api/v1/auth")
    application.dependency_overrides[get_token_info] = lambda: {"user_id": "creator"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as http:
        response = await http.get("/api/v1/auth/domains")
    assert response.status_code == 200
    assert {d["id"] for d in response.json()} == {"home", "tenant-a"}
    counts = Counter(n.read_calls)
    # 180 effective role rows share nine projects, one ancestor and one group.
    for pid in ["default-a", "work-a", *(f"child-{index}" for index in range(8))]:
        assert counts[("project", pid)] == 1
    assert counts[("group", "external")] == 1
    assert counts[("users.list", "external", None)] == 1
    assert counts[("domain", "tenant-a")] == 1
    assert counts[("domain", "home")] == 1
    assert counts[("user", "creator")] == 1
    assert n.calls == []


def test_manager_group_role_expansion_reads_each_active_subject_once(domain_native):
    n = domain_native
    n.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
    n.members["external"] = {"creator", "second"}
    n.project_rows["default-a"].parent_id = "work-a"
    n.raw = [grant(rid, group="external", project="work-a", inherited=True) for rid in ("alias", "reader", "manager")]
    assert domain_projects.has_manager("creator", "tenant-a")
    counts = Counter(n.read_calls)
    assert counts[("group", "external")] == 1
    assert counts[("users.list", "external", None)] == 1
    assert counts[("user", "creator")] == 1
    assert counts[("user", "second")] == 1
    assert counts[("domain", "home")] == 1


@pytest.mark.parametrize("revoke", ["membership", "assignment"])
def test_second_authority_call_observes_group_revoke_despite_stale_projection(domain_native, revoke):
    n = domain_native
    n.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
    n.members["external"] = {"creator", "second"}
    n.group_rows["private"] = row(
        id="private",
        name="afterglow-default-managers-tenant-a",
        description="afterglow:default-manager-reader:v1:tenant-a",
        domain_id="tenant-a",
    )
    n.members["private"] = {"creator"}
    n.raw = [
        grant("alias", group="external", domain="tenant-a", inherited=True),
        grant("project_reader", group="private", domain="tenant-a", inherited=True),
    ]
    domain_projects.assert_membership("creator", "tenant-a")
    domain_projects.assert_project_membership("creator", "work-a")
    assert domain_projects.has_manager("creator", "tenant-a")
    if revoke == "membership":
        n.members["external"].remove("creator")
    else:
        n.raw = [r for r in n.raw if getattr(r, "group", {}).get("id") != "external"]
    assert {d["id"] for d in domain_projects.accessible_domains("creator")} == {"home"}
    for check, target in (
        (domain_projects.assert_membership, "tenant-a"),
        (domain_projects.assert_project_membership, "work-a"),
    ):
        with pytest.raises(HTTPException) as error:
            check("creator", target)
        assert error.value.status_code == 403
    assert not domain_projects.has_manager("creator", "tenant-a")
    assert n.members["private"] == {"creator"}
    assert n.calls == []


def test_home_membership_does_not_depend_on_irrelevant_foreign_inventory(domain_native):
    n = domain_native

    def unavailable(*args, **kwargs):
        raise HTTPException(503, "unrelated_foreign_inventory_unavailable")

    n.role_assignments.list = unavailable
    n.roles.list = unavailable
    n.inference_rules.list_inference_roles = unavailable
    n.projects.get = n.projects.list = unavailable
    n.groups.get = n.groups.list = unavailable
    domain_projects.assert_membership("creator", "home")
    assert Counter(n.read_calls) == Counter({("user", "creator"): 1, ("domain", "home"): 1})
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_membership("creator", "tenant-a")
    assert error.value.status_code == 503
    n.domain_rows["home"].enabled = False
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_membership("creator", "home")
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    "subject,attribute,value,status",
    [
        ("user", "id", "wrong-user", 503),
        ("user", "domain_id", "", 503),
        ("user", "enabled", "true", 503),
        ("user", "enabled", False, 401),
        ("domain", "id", "wrong-domain", 503),
        ("domain", "enabled", "true", 503),
        ("domain", "name", None, 503),
    ],
)
def test_home_membership_short_circuit_requires_exact_active_metadata(domain_native, subject, attribute, value, status):
    n = domain_native
    target = n.user_rows["creator"] if subject == "user" else n.domain_rows["home"]
    setattr(target, attribute, value)
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_membership("creator", "home")
    assert error.value.status_code == status


@pytest.mark.parametrize(
    "malformed",
    ["group-id", "group-marker", "member-id", "ancestor-domain", "project-domain", "effective-role"],
)
def test_deduplicated_foreign_authority_fails_closed_on_relevant_metadata(domain_native, malformed):
    n = domain_native
    n.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
    n.members["external"] = {"creator", "second"}
    n.project_rows["default-a"].parent_id = "work-a"
    n.raw = [grant(rid, group="external", project="work-a", inherited=True) for rid in ("manager", "reader")]
    if malformed == "group-id":
        n.group_rows["external"].id = "different-group"
    elif malformed == "group-marker":
        n.group_rows["external"].description = None
    elif malformed == "member-id":
        n.user_rows["second"].id = ""
    elif malformed == "ancestor-domain":
        n.project_rows["work-a"].domain_id = "tenant-b"
    elif malformed == "project-domain":
        n.project_rows["default-a"].domain_id = None
    else:
        original = n.role_assignments.list

        def corrupt_effective(**kwargs):
            result = original(**kwargs)
            if kwargs.get("effective"):
                result.append(grant("unknown-role", user="creator", project="default-a"))
            return result

        n.role_assignments.list = corrupt_effective
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_membership("creator", "tenant-a")
    assert error.value.status_code == 503
    assert n.calls == []


@pytest.mark.parametrize("parent_id", [False, 0, ""])
def test_inherited_authority_rejects_malformed_falsy_parent(domain_native, parent_id):
    n = domain_native
    n.project_rows["default-a"].parent_id = "work-a"
    n.project_rows["work-a"].parent_id = parent_id
    n.raw = [grant("manager", user="creator", project="work-a", inherited=True)]
    with pytest.raises(HTTPException) as error:
        domain_projects.assert_membership("creator", "tenant-a")
    assert error.value.status_code == 503


def test_operation_reuses_complete_provenance_across_scope_reads(domain_native, monkeypatch):
    from app.services.native_operation import NativeOperation

    n = domain_native
    calls = Counter()
    for manager, method, label in (
        (n.roles, "list", "roles"),
        (n.inference_rules, "list_inference_roles", "inferences"),
        (n.projects, "list", "projects"),
    ):
        original = getattr(manager, method)

        def counted(*args, _original=original, _label=label, **kwargs):
            calls[_label] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(manager, method, counted)
    n.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
    n.members["external"] = {"creator", "second"}
    n.raw = [grant("alias", group="external", domain="tenant-a", inherited=True)]
    with NativeOperation() as operation:
        for _ in range(2):
            domain_projects.assert_membership("creator", "tenant-a", operation=operation)
            assert domain_projects.has_manager("creator", "tenant-a", operation=operation)
            domain_projects.assert_project_membership("creator", "work-a", operation=operation)
            assert domain_projects.default_project("tenant-a", operation=operation)["id"] == "default-a"
            assert {d["id"] for d in domain_projects.accessible_domains("creator", operation=operation)} == {
                "home",
                "tenant-a",
            }
    counts = Counter(n.read_calls)
    assert counts[("assignments.list", None, None, None, False, None)] == 1
    assert counts[("assignments.list", "default-a", None, None, True, None)] == 1
    assert counts[("assignments.list", "work-a", None, None, True, None)] == 1
    assert counts[("assignments.list", None, "creator", None, True, None)] == 1
    assert counts[("users.list", "external", None)] == 1
    assert counts[("user", "creator")] == counts[("user", "second")] == 1
    assert calls == Counter(roles=1, inferences=1, projects=1)
    assert n.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", ["creator", "ordinary"])
async def test_current_login_avoids_write_connection_lease_and_writes(domain_native, monkeypatch, user_id):
    n = domain_native
    await domain_projects.ensure_login_access(user_id, "tenant-a")
    n.calls.clear()
    n.read_calls.clear()

    def forbidden(*args, **kwargs):
        pytest.fail("current login must not open a mutation connection or graph lease")

    monkeypatch.setattr(keystone, "get_admin_project_connection", forbidden)
    monkeypatch.setattr(identity_roles, "_graph_lock", forbidden)
    await domain_projects.ensure_login_access(user_id, "tenant-a")
    assert n.calls == []
    counts = Counter(n.read_calls)
    assert counts[("assignments.list", None, None, None, False, None)] == 1
    assert counts[("assignments.list", "default-a", None, None, True, None)] == 1
    assert counts[("users.list", "projection-tenant-a", None)] == 1
    assert counts[("user", "creator")] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["native-reader", "group", "inherited", "inference"])
async def test_login_requires_direct_canonical_reader_not_equivalent_access(domain_native, source):
    n = domain_native
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    n.raw = [r for r in n.raw if getattr(r, "user", {}).get("id") != "ordinary"]
    if source == "native-reader":
        n.raw.append(grant("reader", user="ordinary", project="default-a"))
    elif source == "inherited":
        n.raw.append(grant("project_reader", user="ordinary", domain="tenant-a", inherited=True))
    elif source == "inference":
        n.role_rows.append(row(id="custom-reader", name="custom-reader", domain_id=None))
        n.edges.append({"prior_role": {"id": "custom-reader"}, "implies": [{"id": "project_reader"}]})
        n.raw.append(grant("custom-reader", user="ordinary", project="default-a"))
    else:
        n.group_rows["external"] = row(id="external", name="Team", domain_id="tenant-a", description="")
        n.members["external"] = {"ordinary"}
        n.raw.append(grant("project_reader", group="external", project="default-a"))
    n.calls.clear()
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    assert n.calls == [("grant", "project_reader", "ordinary", None, "default-a", None, False)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stale",
    [
        "group",
        "grant",
        "missing-member",
        "foreign-member",
        "manager-added",
        "manager-revoked",
        "disabled",
        "home-disabled",
    ],
)
async def test_login_repairs_entire_stale_projection_not_only_login_user(
    domain_native, monkeypatch, login_proofs, stale
):
    n = domain_native
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    for uid in ("creator", "second", "other", "ordinary"):
        await login_proofs.store(uid)
    gid = "projection-tenant-a"
    expected = {"creator"}
    if stale == "group":
        del n.group_rows[gid]
        del n.members[gid]
        n.raw = [r for r in n.raw if getattr(r, "group", {}).get("id") != gid]
    elif stale == "grant":
        n.raw = [r for r in n.raw if getattr(r, "group", {}).get("id") != gid]
    elif stale == "missing-member":
        n.members[gid].clear()
    elif stale == "foreign-member":
        n.members[gid].add("other")
    elif stale == "manager-added":
        n.raw.append(grant("alias", user="second", project="default-a"))
        expected.add("second")
    elif stale == "manager-revoked":
        n.raw = [r for r in n.raw if r.role["id"] != "manager"]
        expected.clear()
    elif stale == "disabled":
        n.user_rows["creator"].enabled = False
        expected.clear()
    else:
        n.domain_rows["home"].enabled = False
        expected.clear()
    connections = []
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: connections.append(n.conn) or n.conn)
    n.calls.clear()
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    assert connections == [n.conn]
    assert n.calls
    assert n.members[gid] == expected
    assert [vars(r) for r in n.assignments(group=gid)] == [
        vars(grant("project_reader", group=gid, domain="tenant-a", inherited=True))
    ]
    for uid in ("creator", "second", "other"):
        assert domain_projects.has_manager(uid, "tenant-a") is (uid in expected)
    if stale == "manager-revoked":
        with pytest.raises(HTTPException) as denied:
            domain_projects.assert_project_membership("creator", "work-a")
        assert denied.value.status_code == 403
    await login_proofs.preserved()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tamper", ["attributes", "duplicate-group", "foreign-grant", "duplicate-grant", "malformed-member"]
)
async def test_current_reader_cannot_bypass_tampered_projection(domain_native, tamper):
    n = domain_native
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    gid = "projection-tenant-a"
    if tamper == "attributes":
        n.group_rows[gid].description = "tampered"
    elif tamper == "duplicate-group":
        n.group_rows["duplicate"] = row(**{**vars(n.group_rows[gid]), "id": "duplicate"})
        n.members["duplicate"] = {"creator"}
    elif tamper == "foreign-grant":
        n.raw.append(grant("admin", group=gid, project="work-b"))
    elif tamper == "duplicate-grant":
        n.raw.append(grant("project_reader", group=gid, domain="tenant-a", inherited=True))
    else:
        n.members[gid].add("second")
        n.user_rows["second"].id = ""
    n.calls.clear()
    with pytest.raises(HTTPException) as error:
        await domain_projects.ensure_login_access("ordinary", "tenant-a")
    assert error.value.status_code == 503
    assert n.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["effective-only", "raw-only", "unrelated-malformed"])
async def test_login_fast_path_proves_full_graph_and_all_managers(domain_native, mismatch):
    n = domain_native
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    original = n.role_assignments.list

    def mismatched(**kwargs):
        result = original(**kwargs)
        if mismatch == "effective-only" and kwargs.get("effective") and kwargs.get("project") == "default-a":
            result.append(grant("manager", user="second", project="default-a"))
        elif mismatch == "raw-only" and not kwargs:
            result.append(grant("manager", user="second", project="default-a"))
        elif mismatch == "unrelated-malformed" and not kwargs:
            result.append(grant("unknown-role", user="other", project="work-b"))
        return result

    n.role_assignments.list = mismatched
    n.calls.clear()
    with pytest.raises(HTTPException) as error:
        await domain_projects.ensure_login_access("ordinary", "tenant-a")
    assert error.value.status_code == 503
    assert n.calls == []


@pytest.mark.asyncio
async def test_login_repair_discards_operation_cache_before_fresh_leased_guard(domain_native, monkeypatch):
    from app.services.native_operation import NativeOperation

    n = domain_native
    original = identity_roles._graph_lock

    @asynccontextmanager
    async def revoke_before_guard(conn):
        n.raw.clear()
        async with original(conn) as lease:
            yield lease

    monkeypatch.setattr(identity_roles, "_graph_lock", revoke_before_guard)
    with NativeOperation() as operation:
        assert domain_projects.has_manager("creator", "tenant-a", operation=operation)
        with pytest.raises(HTTPException) as error:
            await domain_projects.ensure_login_access("creator", "tenant-a", operation=operation)
        assert error.value.status_code == 403
        assert operation.reads == {}
        assert not domain_projects.has_manager("creator", "tenant-a", operation=operation)
    assert n.calls == []


@pytest.mark.asyncio
async def test_login_repair_reuses_client_but_invalidates_observations_after_write(domain_native, monkeypatch):
    from app.services.native_operation import NativeOperation

    n = domain_native
    clients = []
    closed = []
    n.session = row(session=row(close=lambda: closed.append("service")))
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: clients.append(n) or n)
    with NativeOperation() as operation:
        domain_projects.assert_membership("ordinary", "tenant-a", operation=operation)
        assert operation.reads
        await domain_projects.ensure_login_access("ordinary", "tenant-a", operation=operation)
        assert operation.reads == {}
        assert closed == []
        n.calls.clear()
        await domain_projects.ensure_login_access("ordinary", "tenant-a", operation=operation)
        assert n.calls == []
    assert clients == [n]
    assert closed == ["service"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["repair", "current", "legacy", "denied"])
async def test_standalone_login_closes_owned_service_session(domain_native, case):
    n = domain_native
    if case == "current":
        await domain_projects.ensure_login_access("ordinary", "tenant-a")
    if case == "legacy":
        del n.project_rows["default-a"]
    closed = []
    n.session = row(session=row(close=lambda: closed.append("service")))
    if case == "denied":
        with pytest.raises(HTTPException) as error:
            await domain_projects.ensure_login_access("other", "tenant-a")
        assert error.value.status_code == 403
    else:
        await domain_projects.ensure_login_access("ordinary", "tenant-a")
    assert closed == ["service"]


@pytest.mark.asyncio
async def test_standalone_mutation_closes_owned_service_session_on_failure(domain_native):
    closed = []
    domain_native.session = row(session=row(close=lambda: closed.append("service")))
    with pytest.raises(RuntimeError, match="mutation failed"):
        async with domain_projects._mutation():
            raise RuntimeError("mutation failed")
    assert closed == ["service"]


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["group", "domain-inherit", "ancestor-inherit", "inference"])
async def test_current_login_proves_external_manager_sources_without_lease(domain_native, monkeypatch, source):
    n = domain_native
    if source == "group":
        n.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
        n.members["external"] = {"creator", "second"}
        n.raw = [grant("alias", group="external", project="default-a")]
    elif source == "domain-inherit":
        n.raw = [grant("manager", user="creator", domain="tenant-a", inherited=True)]
    elif source == "ancestor-inherit":
        n.project_rows["default-a"].parent_id = "work-a"
        n.raw = [grant("manager", user="creator", project="work-a", inherited=True)]
    else:
        n.raw = [grant("alias", user="creator", project="default-a")]
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    n.calls.clear()

    def forbidden(*args, **kwargs):
        pytest.fail("proven current external provenance must not enter mutation")

    monkeypatch.setattr(keystone, "get_admin_project_connection", forbidden)
    await domain_projects.ensure_login_access("ordinary", "tenant-a")
    assert n.calls == []
    assert n.members["projection-tenant-a"] == ({"creator", "second"} if source == "group" else {"creator"})


@pytest.mark.parametrize("revoke", ["membership", "assignment"])
def test_new_operation_observes_external_revoke_without_projection_authority(domain_native, revoke):
    from app.services.native_operation import NativeOperation

    n = domain_native
    n.group_rows["external"] = row(id="external", name="Team", domain_id="home", description="")
    n.members["external"] = {"creator", "second"}
    n.group_rows["private"] = row(
        id="private",
        name="afterglow-default-managers-tenant-a",
        description="afterglow:default-manager-reader:v1:tenant-a",
        domain_id="tenant-a",
    )
    n.members["private"] = {"creator"}
    n.raw = [
        grant("alias", group="external", domain="tenant-a", inherited=True),
        grant("project_reader", group="private", domain="tenant-a", inherited=True),
    ]
    with NativeOperation() as operation:
        assert domain_projects.has_manager("creator", "tenant-a", operation=operation)
        domain_projects.assert_membership("creator", "tenant-a", operation=operation)
        domain_projects.assert_project_membership("creator", "work-a", operation=operation)
    if revoke == "membership":
        n.members["external"].remove("creator")
    else:
        n.raw = [r for r in n.raw if getattr(r, "group", {}).get("id") != "external"]
    with NativeOperation() as operation:
        assert not domain_projects.has_manager("creator", "tenant-a", operation=operation)
        assert {d["id"] for d in domain_projects.accessible_domains("creator", operation=operation)} == {"home"}
        for check, target in (
            (domain_projects.assert_membership, "tenant-a"),
            (domain_projects.assert_project_membership, "work-a"),
        ):
            with pytest.raises(HTTPException) as error:
                check("creator", target, operation=operation)
            assert error.value.status_code == 403
    assert n.members["private"] == {"creator"}
    assert n.calls == []


@pytest.mark.asyncio
async def test_simultaneous_first_logins_serialize_one_owner_and_one_reader(domain_native, monkeypatch):
    n = domain_native
    del n.project_rows["default-b"]
    n.user_rows["second"].domain_id = "tenant-b"
    original = identity_roles._graph_lock
    mutex = asyncio.Lock()
    both_waiting = asyncio.Event()
    arrivals = 0

    @asynccontextmanager
    async def serialized(conn):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            both_waiting.set()
        await asyncio.wait_for(both_waiting.wait(), timeout=5)
        async with mutex:
            async with original(conn) as lease:
                yield lease

    monkeypatch.setattr(identity_roles, "_graph_lock", serialized)
    await asyncio.gather(
        domain_projects.ensure_login_access("other", "tenant-b"),
        domain_projects.ensure_login_access("second", "tenant-b"),
    )
    assert n.calls.count(("project.create", "tenant-b")) == 1
    assert arrivals == 2 and n.lock_depth == 0
    direct = n.assignments(project="created-default")
    owners = [r.user["id"] for r in direct if r.role["id"] == "project_owner"]
    assert len(owners) == 1 and owners[0] in {"other", "second"}
    assert {r.user["id"] for r in direct if r.role["id"] == "project_reader"} == {"other", "second"}
    assert not any(r.role["id"] == "manager" for r in direct)


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["foreign", "revoked", "user-disabled", "home-disabled", "target-disabled"])
async def test_absent_Default_never_bootstraps_without_fresh_membership(domain_native, monkeypatch, denial):
    from app.services.native_operation import NativeOperation

    n = domain_native
    del n.project_rows["default-b"]
    user_id = "other"
    if denial in {"foreign", "revoked"}:
        user_id = "second"
    if denial == "revoked":
        n.raw.append(grant("reader", user=user_id, project="work-b"))
    original = identity_roles._graph_lock

    @asynccontextmanager
    async def revoke_before_guard(conn):
        if denial == "revoked":
            n.raw = [r for r in n.raw if getattr(r, "user", {}).get("id") != user_id]
        elif denial == "user-disabled":
            n.user_rows[user_id].enabled = False
        elif denial == "home-disabled":
            n.domain_rows[n.user_rows[user_id].domain_id].enabled = False
        elif denial == "target-disabled":
            n.domain_rows["tenant-b"].enabled = False
        async with original(conn) as lease:
            yield lease

    monkeypatch.setattr(identity_roles, "_graph_lock", revoke_before_guard)
    with NativeOperation() as operation:
        with pytest.raises(HTTPException) as error:
            await domain_projects.ensure_login_access(user_id, "tenant-b", operation=operation)
        assert error.value.status_code == (401 if denial == "user-disabled" else 403)
        if denial != "foreign":
            assert operation.reads == {}
    assert n.calls == []
    assert "created-default" not in n.project_rows


@pytest.mark.asyncio
async def test_Default_created_before_lease_is_reused_without_owner_takeover(domain_native, monkeypatch):
    n = domain_native
    existing = n.project_rows.pop("default-b")
    original = identity_roles._graph_lock

    @asynccontextmanager
    async def created_before_guard(conn):
        n.project_rows[existing.id] = existing
        n.raw.append(grant("project_owner", user="second", project=existing.id))
        async with original(conn) as lease:
            yield lease

    monkeypatch.setattr(identity_roles, "_graph_lock", created_before_guard)
    await domain_projects.ensure_login_access("other", "tenant-b")
    assert domain_projects.default_project("tenant-b")["id"] == "default-b"
    assert not any(c[0] == "project.create" or c[:2] == ("grant", "project_owner") for c in n.calls)
    assert [r.user["id"] for r in n.assignments(project="default-b") if r.role["id"] == "project_owner"] == ["second"]


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe", ["missing", "ambiguous", "incomplete", "manager-inference"])
async def test_first_login_requires_safe_canonical_owner_graph_without_seeding(domain_native, unsafe):
    n = domain_native
    del n.project_rows["default-b"]
    if unsafe == "missing":
        n.role_rows = [r for r in n.role_rows if r.name != "project_owner"]
        n.edges = [e for e in n.edges if e["prior_role"]["id"] != "project_owner"]
    elif unsafe == "ambiguous":
        n.role_rows.append(row(id="other-owner", name="Project_Owner", domain_id=None))
    elif unsafe == "incomplete":
        n.edges = [e for e in n.edges if e["prior_role"]["id"] != "project_owner"]
    else:
        n.edges.append({"prior_role": {"id": "project_owner"}, "implies": [{"id": "manager"}]})
    roles, edges = list(n.role_rows), list(n.edges)
    with pytest.raises(HTTPException):
        await domain_projects.ensure_login_access("other", "tenant-b")
    assert n.calls == []
    assert n.role_rows == roles and n.edges == edges


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["owner-noop", "reader-noop", "quota"])
async def test_first_login_failed_setup_never_activates_and_cleans_only_settled_owner(
    domain_native, monkeypatch, failure
):
    n = domain_native
    del n.project_rows["default-b"]
    before = set(n.project_rows)
    assign = n.roles.grant

    def missing_grant(role, **kwargs):
        if role == ("project_owner" if failure == "owner-noop" else "project_reader"):
            return
        return assign(role, **kwargs)

    if failure == "quota":
        monkeypatch.setattr(domain_projects, "apply_default_quotas", AsyncMock(side_effect=HTTPException(503, "quota")))
    else:
        n.roles.grant = missing_grant
    with pytest.raises(HTTPException) as error:
        await domain_projects.ensure_login_access("other", "tenant-b")
    assert error.value.status_code == 503
    if failure == "owner-noop":
        from app.services import project_ownership_journal as journal

        assert n.project_rows["created-default"].enabled is False
        assert (await journal.get("created-default"))["status"] == "unknown"
        assert ("project.delete", "created-default") not in n.calls
    else:
        assert set(n.project_rows) == before
        assert ("project.delete", "created-default") in n.calls
    assert ("project.enable", "created-default", True) not in n.calls
    assert not any(c[0] == "domain.delete" for c in n.calls)


@pytest.mark.asyncio
async def test_foreign_owner_on_new_Default_blocks_initial_grant_and_destructive_cleanup(domain_native):
    n = domain_native
    del n.project_rows["default-b"]
    create = n.projects.create

    def owned_externally(**kwargs):
        created = create(**kwargs)
        n.raw.append(grant("project_owner", user="second", project=created.id))
        return created

    n.projects.create = owned_externally
    with pytest.raises(HTTPException) as error:
        await domain_projects.ensure_login_access("other", "tenant-b")
    assert error.value.detail == "domain_default_setup_cleanup_unavailable"
    assert n.project_rows["created-default"].enabled is False
    assert not any(c[:2] == ("grant", "project_owner") or c[0] == "project.delete" for c in n.calls)
    assert [r.user["id"] for r in n.assignments(project="created-default")] == ["second"]


@pytest.mark.asyncio
@pytest.mark.parametrize("participant_role", ["project_member", "project_admin"])
async def test_new_Default_owner_delegates_safe_roles_but_reader_cannot(domain_native, monkeypatch, participant_role):
    n = domain_native
    del n.project_rows["default-b"]
    n.user_rows["second"].domain_id = "tenant-b"
    await domain_projects.ensure_login_access("other", "tenant-b")
    await domain_projects.ensure_login_access("second", "tenant-b")
    pid = domain_projects.default_project("tenant-b")["id"]
    owner = {"user_id": "other", "domain_id": "tenant-b", "project_id": pid}
    reader = {**owner, "user_id": "second"}
    monkeypatch.setattr(identity_roles, "_applied", AsyncMock())
    monkeypatch.setattr(project_service, "invalidate_project_lists", AsyncMock())
    before = list(n.calls)
    with pytest.raises(HTTPException) as error:
        await project_service.replace_member_roles(pid, "other", ["project_member"], reader)
    assert error.value.status_code == 403
    assert n.calls == before
    result = await project_service.replace_member_roles(pid, "second", [participant_role], owner)
    assert set(result["direct_role_ids"]) == {participant_role, "project_reader"}
    result = await project_service.replace_member_roles(pid, "second", [], owner)
    assert result["direct_role_ids"] == ["project_reader"]
    for selected in (["project_reader"], ["project_owner", "project_reader"]):
        target = "other" if selected == ["project_reader"] else "second"
        with pytest.raises(HTTPException) as error:
            await project_service.replace_member_roles(pid, target, selected, owner)
        assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await project_service.transfer_project_ownership(pid, "second", owner)
    assert error.value.status_code == 422  # Default remains immutable.
    await project_service._verify_unique_owner(n, domain_projects._catalog(n), pid, "other")
    assert not domain_projects.has_manager("other", "tenant-b")


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["lost-reply", "foreign-existing-id"])
async def test_first_login_unknown_create_never_replays_or_deletes_by_name(domain_native, outcome):
    n = domain_native
    del n.project_rows["default-b"]
    create = n.projects.create

    def uncertain_create(**kwargs):
        if outcome == "foreign-existing-id":
            return n.project_rows["work-b"]
        create(**kwargs)
        raise HTTPException(503, "lost_create_reply")

    n.projects.create = uncertain_create
    with pytest.raises(HTTPException) as error:
        await domain_projects.ensure_login_access("other", "tenant-b")
    assert error.value.status_code == 503
    assert not any(c[0] in {"project.delete", "project.enable"} for c in n.calls)
    assert n.project_rows["work-b"].enabled is True
    if outcome == "lost-reply":
        assert n.calls == [("project.create", "tenant-b")]
        assert n.project_rows["created-default"].enabled is False
    else:
        assert n.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("revoked_role", [None, "project_owner", "project_reader"])
async def test_bootstrap_checks_authority_and_quotas_before_activation(domain_native, monkeypatch, revoked_role):
    n = domain_native
    del n.project_rows["default-b"]

    async def apply(domain_id, project_id, lease):
        await lease.assert_owned()
        assert (domain_id, project_id) == ("tenant-b", "created-default")
        assert n.project_rows[project_id].enabled is False
        await project_service._verify_unique_owner(n, domain_projects._catalog(n), project_id, "other")
        assert {r.role["id"] for r in n.assignments(project=project_id, user="other")} == {
            "project_owner",
            "project_reader",
        }
        assert n.members["projection-tenant-b"] == set()
        if revoked_role is not None:
            n.revoke(revoked_role, user="other", project=project_id)

    monkeypatch.setattr(domain_projects, "apply_default_quotas", apply)
    if revoked_role is None:
        await domain_projects.ensure_login_access("other", "tenant-b")
        assert n.project_rows["created-default"].enabled is True
    else:
        with pytest.raises(HTTPException) as error:
            await domain_projects.ensure_login_access("other", "tenant-b")
        assert error.value.status_code == 503
        assert ("project.enable", "created-default", True) not in n.calls
        assert "created-default" not in n.project_rows


@pytest.mark.asyncio
@pytest.mark.parametrize("committed", [False, True])
async def test_unknown_initial_owner_grant_is_never_cleaned_or_replayed(domain_native, committed):
    from app.services import project_ownership_journal as journal

    n = domain_native
    del n.project_rows["default-b"]
    assign = n.roles.grant
    attempts = []

    def lost_owner_reply(role, **kwargs):
        assert role == "project_owner"
        attempts.append((role, kwargs))
        if committed:
            assign(role, **kwargs)
        raise HTTPException(503, "owner_grant_reply_lost")

    n.roles.grant = lost_owner_reply
    with pytest.raises(HTTPException) as error:
        await domain_projects.ensure_login_access("other", "tenant-b")
    assert error.value.status_code == 503
    assert len(attempts) == 1
    assert n.project_rows["created-default"].enabled is False
    operation = await journal.get("created-default")
    assert operation["status"] == "unknown" and operation["to_user_id"] == "other"
    assert not any(c[0] in {"project.delete", "project.enable"} for c in n.calls)
    with pytest.raises(HTTPException) as error:
        await domain_projects.ensure_login_access("other", "tenant-b")
    assert error.value.status_code == 503
    assert len(attempts) == 1
    assert n.calls.count(("project.create", "tenant-b")) == 1


@pytest.mark.asyncio
async def test_organization_creation_fails_closed_on_truncated_native_domain_inventory(domain_native, monkeypatch):
    class LimitedDomains(list):
        limited = True

    before = set(domain_native.domain_rows)
    monkeypatch.setattr(domain_native.domains, "list", lambda: LimitedDomains(domain_native.domain_rows.values()))
    with pytest.raises(HTTPException) as denied:
        await domain_projects.create_domain(name="New organization", description="", enabled=True, creator_id="creator")
    assert denied.value.status_code == 503
    assert set(domain_native.domain_rows) == before and domain_native.calls == []
