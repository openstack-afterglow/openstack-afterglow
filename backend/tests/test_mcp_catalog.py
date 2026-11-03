from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest
from openstack.compute.v2.flavor import Flavor
from openstack.compute.v2.keypair import Keypair
from openstack.image.v2.image import Image

from app.services.mcp_control_plane import catalog

PROJECT = "project-a"
USER = "user-a"


def flavor(**changes):
    return {
        "id": "flavor-a",
        "name": "small",
        "vcpus": 2,
        "ram": 4096,
        "disk": 20,
        "is_public": True,
        "extra_specs": {},
        **changes,
    }


def image(**changes):
    return {
        "id": "image-a",
        "name": "Ubuntu",
        "status": "active",
        "visibility": "public",
        "owner": "image-owner",
        "min_disk": 1,
        "min_ram": 512,
        "size": 2048,
        "disk_format": "qcow2",
        "os_distro": "ubuntu",
        "os_version": "24.04",
        "os_admin_user": "ubuntu",
        **changes,
    }


def key(**changes):
    return {
        "name": "work key",
        "user_id": USER,
        "type": "ssh",
        "fingerprint": "aa:bb",
        "private_key": "NEVER-RETURN-PRIVATE",
        "public_key": "NEVER-RETURN-PUBLIC",
        **changes,
    }


class Compute:
    def __init__(self, rows=(), *, grants=()):
        self.rows = list(rows)
        self.grants = list(grants)
        self.calls = []

    def flavors(self, *, details, get_extra_specs, is_public, paginated, limit, marker=None):
        self.calls.append(("flavors", details, get_extra_specs, paginated, limit, marker))
        return iter(self.rows)

    def get_flavor(self, flavor_id):
        self.calls.append(("get_flavor", flavor_id))
        return self.rows[0]

    def get_flavor_access(self, flavor_id):
        self.calls.append(("get_flavor_access", flavor_id))
        return self.grants

    def get(self, path, *, microversion, params, redirect, allow_reauth, connect_retries, status_code_retries):
        self.calls.append(
            (
                "native_keypairs",
                path,
                microversion,
                params,
                redirect,
                allow_reauth,
                connect_retries,
                status_code_retries,
            )
        )
        assert path == "/os-keypairs" and microversion == "2.35"
        assert set(params) <= {"limit", "marker"}
        assert redirect is False and allow_reauth is False
        assert connect_retries == status_code_retries == 0

        def value(row, field):
            return row.get(field) if isinstance(row, dict) else getattr(row, field, None)

        rows = self.rows
        if "marker" in params:
            index = next(index for index, row in enumerate(rows) if value(row, "name") == params["marker"])
            rows = rows[index + 1 :]
        # Nova's actual list view deliberately omits user_id.
        page = [
            {"keypair": {field: value(row, field) for field in ("name", "type", "fingerprint", "public_key")}}
            for row in rows[: params["limit"]]
        ]
        return SimpleNamespace(status_code=200, json=lambda: {"keypairs": page})

    def get_keypair(self, key_name):
        self.calls.append(("get_keypair", key_name))
        return next(
            (row for row in self.rows if (row.get("name") if isinstance(row, dict) else row.name) == key_name),
            self.rows[0],
        )


class Images:
    def __init__(self, rows=(), *, members=()):
        self.rows = list(rows)
        self.member_rows = list(members)
        self.calls = []

    def images(self, *, paginated, limit, marker=None):
        self.calls.append(("images", paginated, limit, marker))
        return iter(self.rows)

    def get_image(self, image_id):
        self.calls.append(("get_image", image_id))
        return self.rows[0]

    def get(self, path, **kwargs):
        self.calls.append(("member_get", path))
        payload = self.member_rows[0] if self.member_rows else {}
        return SimpleNamespace(status_code=200, json=lambda: payload)


def connection(*, compute=None, images=None, admin=False):
    return SimpleNamespace(compute=compute, image=images, _afterglow_compute_admin=admin, _afterglow_user_id=USER)


@pytest.mark.asyncio
async def test_flavors_exact_filters_continue_after_hidden_and_filtered_raw_rows():
    native = Compute(
        [
            flavor(id="foreign", is_public=False),
            flavor(id="other-cpu", vcpus=4),
            flavor(id="other-ram", ram=8192),
            flavor(id="wanted"),
            flavor(id="beyond-page"),
        ]
    )
    result = await catalog.list_project_flavors(
        connection(compute=native, admin=True),
        project_id=PROJECT,
        limit=4,
        marker="previous",
        vcpus=2,
        ram_mb=4096,
    )
    assert [row["id"] for row in result["flavors"]] == ["wanted"]
    assert result["next_marker"] == "wanted"
    assert native.calls == [
        ("flavors", True, False, False, 4, "previous"),
        ("get_flavor_access", "foreign"),
    ]


@pytest.mark.asyncio
async def test_flavor_page_can_be_empty_with_continuation_without_refill():
    native = Compute([flavor(id="a", vcpus=8), flavor(id="b", vcpus=8), flavor(id="c")])
    result = await catalog.list_project_flavors(connection(compute=native), project_id=PROJECT, limit=2, vcpus=2)
    assert result == {"flavors": [], "next_marker": "b"}
    assert native.calls == [("flavors", True, False, False, 2, None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "grants,allowed",
    [
        ([{"flavor_id": "flavor-a", "tenant_id": PROJECT}], True),
        ([{"flavor_id": "flavor-a", "tenant_id": "other"}], False),
        ([{"flavor_id": "wrong-flavor", "tenant_id": PROJECT}], False),
        ([{"tenant_id": PROJECT}], False),
        ([], False),
    ],
)
async def test_admin_private_flavor_requires_exact_flavor_and_project_acl(grants, allowed):
    native = Compute([flavor(is_public=False)], grants=grants)
    conn = connection(compute=native, admin=True)
    if allowed:
        result = await catalog.get_project_flavor(conn, project_id=PROJECT, flavor_id="flavor-a")
        assert result["is_public"] is False
    else:
        with pytest.raises(catalog.McpCatalogError, match="access"):
            await catalog.get_project_flavor(conn, project_id=PROJECT, flavor_id="flavor-a")
    assert native.calls == [("get_flavor", "flavor-a"), ("get_flavor_access", "flavor-a")]


@pytest.mark.asyncio
async def test_nonadmin_private_flavor_uses_native_visibility_without_admin_only_acl():
    class NonAdmin(Compute):
        def get_flavor_access(self, flavor_id):
            raise AssertionError("reader must not call Nova admin-only ACL endpoint")

    native = NonAdmin([flavor(is_public=False)])
    conn = connection(compute=native)
    assert (await catalog.list_project_flavors(conn, project_id=PROJECT))["flavors"][0]["is_public"] is False
    assert (await catalog.get_project_flavor(conn, project_id=PROJECT, flavor_id="flavor-a"))["id"] == "flavor-a"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,specs,vcpus,ram,gpu,schedule",
    [
        ("gpu.name-is-not-proof", {}, 2, 4096, False, False),
        ("plain", {"resources:VGPU": "1"}, 2, 4096, True, True),
        ("plain", {"pci_passthrough:alias": "nic:1"}, 2, 4096, False, False),
        ("plain", {}, 12, 4096, False, True),
        ("plain", {}, 2, 65536, False, True),
        ("plain", {"afterglow:usage_schedule_required": "true"}, 2, 4096, False, True),
    ],
)
async def test_flavor_classification_uses_checked_specs_and_canonical_schedule_policy(
    name, specs, vcpus, ram, gpu, schedule
):
    native = Compute([flavor(name=name, extra_specs=specs, vcpus=vcpus, ram=ram, is_gpu=True, password="secret")])
    result = await catalog.get_project_flavor(connection(compute=native), project_id=PROJECT, flavor_id="flavor-a")
    assert result == {
        "id": "flavor-a",
        "name": name,
        "vcpus": vcpus,
        "ram_mb": ram,
        "disk_gb": 20,
        "is_public": True,
        "is_gpu": gpu,
        "requires_usage_schedule": schedule,
    }


@pytest.mark.asyncio
async def test_missing_inline_specs_use_canonical_validated_native_envelope():
    raw = flavor()
    del raw["extra_specs"]

    class Native(Compute):
        def get(self, path, *, redirect, allow_reauth, connect_retries, status_code_retries):
            self.calls.append((path, redirect, allow_reauth, connect_retries, status_code_retries))
            return SimpleNamespace(status_code=200, json=lambda: {"extra_specs": {"resources:VGPU": "1"}})

    native = Native([raw])
    result = await catalog.get_project_flavor(connection(compute=native), project_id=PROJECT, flavor_id="flavor-a")
    assert result["is_gpu"] is True
    assert native.calls[-1] == ("/flavors/flavor-a/os-extra_specs", False, False, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"extra_specs": None}, {"extra_specs": {}, "truncated": True}])
async def test_missing_or_incomplete_native_specs_never_become_empty_policy(payload):
    raw = flavor()
    del raw["extra_specs"]

    class Native(Compute):
        def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=200, json=lambda: payload)

    with pytest.raises(catalog.McpCatalogError, match="unavailable"):
        await catalog.get_project_flavor(connection(compute=Native([raw])), project_id=PROJECT, flavor_id="flavor-a")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("vcpus", True),
        ("vcpus", "2"),
        ("vcpus", 0),
        ("ram", -1),
        ("disk", -1),
        ("disk", 2**63),
        ("is_public", "true"),
        ("extra_specs", []),
        ("extra_specs", {"resources:VGPU": 1}),
    ],
)
async def test_flavor_malformed_provider_values_fail_closed(field, value):
    with pytest.raises(catalog.McpCatalogError):
        await catalog.get_project_flavor(
            connection(compute=Compute([flavor(**{field: value})])),
            project_id=PROJECT,
            flavor_id="flavor-a",
        )


@pytest.mark.asyncio
async def test_sdk_flavor_defaults_do_not_prove_missing_native_visibility_or_capacity():
    for field in ("is_public", "vcpus", "ram", "disk"):
        raw = flavor()
        del raw[field]
        resource = Flavor.existing(**raw)
        with pytest.raises(catalog.McpCatalogError):
            await catalog.get_project_flavor(
                connection(compute=Compute([resource])),
                project_id=PROJECT,
                flavor_id="flavor-a",
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "visibility,owner,allowed",
    [
        ("private", PROJECT, True),
        ("shared", PROJECT, True),
        ("public", "other", True),
        ("community", "other", True),
        ("private", "other", False),
        ("shared", "other", False),
    ],
)
async def test_image_visibility_is_owned_public_community_or_explicit_accepted_share(visibility, owner, allowed):
    native = Images([image(visibility=visibility, owner=owner)])
    if allowed:
        result = await catalog.get_project_image(connection(images=native), project_id=PROJECT, image_id="image-a")
        assert result["id"] == "image-a"
    else:
        with pytest.raises(catalog.McpCatalogError, match="visibility"):
            await catalog.get_project_image(connection(images=native), project_id=PROJECT, image_id="image-a")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "member,allowed",
    [
        ({"member_id": PROJECT, "status": "accepted", "image_id": "image-a"}, True),
        ({"member_id": PROJECT, "status": "pending", "image_id": "image-a"}, False),
        ({"member_id": PROJECT, "status": "rejected", "image_id": "image-a"}, False),
        ({"member_id": "other", "status": "accepted", "image_id": "image-a"}, False),
        ({"status": "accepted", "image_id": "image-a"}, False),
        ({"member_id": PROJECT, "status": "accepted", "image_id": "wrong"}, False),
    ],
)
async def test_shared_image_membership_requires_exact_returned_project_accepted_status_and_image(member, allowed):
    native = Images([image(visibility="shared")], members=[member])
    conn = connection(images=native)
    if allowed:
        assert (await catalog.get_project_image(conn, project_id=PROJECT, image_id="image-a"))["visibility"] == "shared"
    else:
        with pytest.raises(catalog.McpCatalogError):
            await catalog.get_project_image(conn, project_id=PROJECT, image_id="image-a")


@pytest.mark.asyncio
async def test_image_page_filters_exact_name_and_active_visibility_without_refilling():
    native = Images(
        [
            image(id="inactive", status="queued"),
            image(id="prefix", name="Ubuntu server"),
            image(id="hidden", visibility="private"),
            image(id="wanted"),
            image(id="outside"),
        ]
    )
    result = await catalog.list_project_images(
        connection(images=native),
        project_id=PROJECT,
        limit=4,
        marker="previous",
        name="Ubuntu",
    )
    assert [row["id"] for row in result["images"]] == ["wanted"]
    assert result["next_marker"] == "wanted"
    assert native.calls == [("images", False, 4, "previous")]


@pytest.mark.asyncio
async def test_image_output_is_exact_allowlist_with_optional_nulls_and_no_locations_or_properties():
    native = Images(
        [
            image(
                size=None,
                disk_format=None,
                os_distro=None,
                os_version=None,
                os_admin_user=None,
                locations=[{"url": "https://secret.invalid/token"}],
                direct_url="secret",
                properties={"password": "secret"},
            )
        ]
    )
    result = await catalog.get_project_image(connection(images=native), project_id=PROJECT, image_id="image-a")
    assert result == {
        "id": "image-a",
        "name": "Ubuntu",
        "status": "active",
        "visibility": "public",
        "min_disk_gb": 1,
        "min_ram_mb": 512,
        "size_bytes": None,
        "disk_format": None,
        "os_distro": None,
        "os_version": None,
        "os_admin_user": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"status": "deactivated"},
        {"owner": None},
        {"visibility": "unknown"},
        {"min_disk": -1},
        {"min_ram": True},
        {"size": "2048"},
        {"size": 2**63},
        {"os_admin_user": {"secret": "bad"}},
    ],
)
async def test_image_malformed_or_inactive_provider_rows_fail_closed(changes):
    with pytest.raises(catalog.McpCatalogError):
        await catalog.get_project_image(
            connection(images=Images([image(**changes)])),
            project_id=PROJECT,
            image_id="image-a",
        )


@pytest.mark.asyncio
async def test_sdk_image_raw_values_are_checked_before_descriptor_coercion():
    resource = Image.existing(**image(size="2048"))
    with pytest.raises(catalog.McpCatalogError, match="size"):
        await catalog.get_project_image(connection(images=Images([resource])), project_id=PROJECT, image_id="image-a")


@pytest.mark.asyncio
async def test_keypair_list_filters_foreign_owner_preserves_raw_marker_and_never_returns_key_material():
    native = Compute(
        [key(name="previous key"), key(name="own"), key(name="foreign", user_id="other"), key(name="outside")]
    )
    result = await catalog.list_user_keypairs(connection(compute=native), user_id=USER, limit=2, marker="previous key")
    assert result == {"keypairs": [{"name": "own", "type": "ssh", "fingerprint": "aa:bb"}], "next_marker": "foreign"}
    assert native.calls == [
        ("native_keypairs", "/os-keypairs", "2.35", {"limit": 2, "marker": "previous key"}, False, False, 0, 0),
        ("get_keypair", "own"),
        ("get_keypair", "foreign"),
    ]


@pytest.mark.asyncio
async def test_keypair_native_ownerless_list_paginates_at_235_and_proves_each_show_owner():
    native = Compute([key(name="a"), key(name="b"), key(name="c")])
    conn = connection(compute=native)
    first = await catalog.list_user_keypairs(conn, user_id=USER, limit=2)
    second = await catalog.list_user_keypairs(conn, user_id=USER, limit=2, marker=first["next_marker"])
    assert [row["name"] for row in first["keypairs"]] == ["a", "b"]
    assert first["next_marker"] == "b"
    assert second == {"keypairs": [{"name": "c", "type": "ssh", "fingerprint": "aa:bb"}], "next_marker": None}
    assert [call for call in native.calls if call[0] == "get_keypair"] == [
        ("get_keypair", "a"),
        ("get_keypair", "b"),
        ("get_keypair", "c"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("caller", [None, "other"])
async def test_keypair_list_requires_validated_exact_connection_caller(caller):
    native = Compute([key()])
    conn = connection(compute=native)
    conn._afterglow_user_id = caller
    with pytest.raises(catalog.McpCatalogError, match="caller identity"):
        await catalog.list_user_keypairs(conn, user_id=USER)
    assert native.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,payload",
    [
        (406, {"keypairs": []}),
        (200, {}),
        (200, {"keypairs": {}}),
        (200, {"keypairs": [{"name": "not-the-native-envelope"}]}),
        (200, {"keypairs": [{"keypair": key(name="a")}, {"keypair": key(name="b")}]}),
    ],
)
async def test_keypair_native_page_rejects_unsupported_version_malformed_or_oversized_pages(status, payload):
    class Malformed(Compute):
        def get(self, *args, **kwargs):
            self.calls.append(("native_get", args, kwargs))
            return SimpleNamespace(status_code=status, json=lambda: payload)

    native = Malformed([key()])
    with pytest.raises(catalog.McpCatalogError):
        await catalog.list_user_keypairs(connection(compute=native), user_id=USER, limit=1)
    assert len(native.calls) == 1
    assert native.calls[0][2]["microversion"] == "2.35"


@pytest.mark.asyncio
async def test_keypair_get_has_no_owner_seed_argument_and_returns_only_safe_metadata():
    native = Compute([key()])
    result = await catalog.get_user_keypair(connection(compute=native), user_id=USER, key_name="work key")
    assert result == {"name": "work key", "type": "ssh", "fingerprint": "aa:bb"}
    assert native.calls == [("get_keypair", "work key")]


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [None, "", "other"])
@pytest.mark.parametrize("sdk_resource", [False, True])
async def test_keypair_get_requires_provider_owner_even_with_real_sdk_resources(owner, sdk_resource):
    raw = key(user_id=owner)
    if owner is None:
        del raw["user_id"]
    resource = Keypair.existing(**raw) if sdk_resource else raw
    with pytest.raises(catalog.McpCatalogError):
        await catalog.get_user_keypair(connection(compute=Compute([resource])), user_id=USER, key_name="work key")


@pytest.mark.asyncio
async def test_keypair_list_missing_owner_fails_closed_instead_of_trusting_query():
    raw = key()
    del raw["user_id"]
    with pytest.raises(catalog.McpCatalogError, match="user_id"):
        await catalog.list_user_keypairs(connection(compute=Compute([Keypair.existing(**raw)])), user_id=USER)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["flavor", "image", "keypair"])
async def test_get_requires_exact_returned_identity(kind):
    if kind == "flavor":
        operation = catalog.get_project_flavor(
            connection(compute=Compute([flavor(id="other")])), project_id=PROJECT, flavor_id="flavor-a"
        )
    elif kind == "image":
        operation = catalog.get_project_image(
            connection(images=Images([image(id="other")])), project_id=PROJECT, image_id="image-a"
        )
    else:
        operation = catalog.get_user_keypair(
            connection(compute=Compute([key(name="other")])), user_id=USER, key_name="work key"
        )
    with pytest.raises(catalog.McpCatalogError, match="identity"):
        await operation


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101, -1, True, "50", 1.5])
@pytest.mark.parametrize("kind", ["flavor", "image", "keypair"])
async def test_invalid_page_bounds_are_rejected_before_provider_calls(limit, kind):
    conn = connection()
    with pytest.raises(catalog.McpCatalogError, match="limit"):
        if kind == "flavor":
            await catalog.list_project_flavors(conn, project_id=PROJECT, limit=limit)
        elif kind == "image":
            await catalog.list_project_images(conn, project_id=PROJECT, limit=limit)
        else:
            await catalog.list_user_keypairs(conn, user_id=USER, limit=limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", ["", " ", "x" * 256, "bad\nmarker", 123])
async def test_invalid_marker_is_rejected_before_provider_calls(marker):
    with pytest.raises(catalog.McpCatalogError, match="marker"):
        await catalog.list_project_images(connection(), project_id=PROJECT, marker=marker)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, -1, True, 2.5, "2"])
@pytest.mark.parametrize("field", ["vcpus", "ram_mb"])
async def test_exact_flavor_filters_require_positive_real_integers(field, value):
    with pytest.raises(catalog.McpCatalogError, match=field):
        await catalog.list_project_flavors(connection(), project_id=PROJECT, **{field: value})


@pytest.mark.asyncio
async def test_opaque_markers_and_exact_names_are_not_rewritten():
    native = Images([image(name=" Ubuntu ")])
    result = await catalog.list_project_images(
        connection(images=native),
        project_id=PROJECT,
        marker="opaque:/?#% value",
        name=" Ubuntu ",
    )
    assert result["images"][0]["name"] == " Ubuntu "
    assert native.calls == [("images", False, 50, "opaque:/?#% value")]


@pytest.mark.asyncio
async def test_explicit_community_visibility_uses_one_native_page_and_checks_returned_visibility():
    class Community(Images):
        def images(self, *, paginated, limit, marker, visibility):
            self.calls.append((paginated, limit, marker, visibility))
            return iter(
                [
                    image(id="community", visibility="community"),
                    image(id="wrong-visibility", visibility="public"),
                ]
            )

    native = Community()
    result = await catalog.list_project_images(
        connection(images=native),
        project_id=PROJECT,
        limit=2,
        marker="previous",
        visibility="community",
    )
    assert native.calls == [(False, 2, "previous", "community")]
    assert result["next_marker"] == "wrong-visibility"
    assert [row["id"] for row in result["images"]] == ["community"]
    assert result["images"][0]["visibility"] == "community"


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["", "all", "PUBLIC", [], True])
async def test_invalid_visibility_filter_is_rejected_before_native_calls(visibility):
    with pytest.raises(catalog.McpCatalogError, match="visibility filter"):
        await catalog.list_project_images(connection(), project_id=PROJECT, visibility=visibility)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["flavor", "image", "keypair"])
async def test_empty_terminal_page_has_no_marker(kind):
    conn = connection(compute=Compute([key(name="previous")]) if kind == "keypair" else Compute(), images=Images())
    if kind == "flavor":
        result = await catalog.list_project_flavors(conn, project_id=PROJECT, marker="previous")
        assert result == {"flavors": [], "next_marker": None}
    elif kind == "image":
        result = await catalog.list_project_images(conn, project_id=PROJECT, marker="previous")
        assert result == {"images": [], "next_marker": None}
    else:
        result = await catalog.list_user_keypairs(conn, user_id=USER, marker="previous")
        assert result == {"keypairs": [], "next_marker": None}


@pytest.mark.asyncio
async def test_provider_cannot_force_unbounded_raw_scan_or_auto_refill():
    class Infinite(Images):
        def images(self, *, paginated, limit, marker=None):
            assert paginated is False
            for index in range(limit):
                yield image(id=f"image-{index}", status="queued")
            raise AssertionError("adapter consumed beyond its raw page bound")

    result = await catalog.list_project_images(connection(images=Infinite()), project_id=PROJECT, limit=3)
    assert result == {"images": [], "next_marker": "image-2"}


@pytest.mark.asyncio
@pytest.mark.parametrize("ids,marker", [(["same", "same"], None), (["previous"], "previous")])
async def test_duplicate_or_nonadvancing_provider_identity_is_rejected(ids, marker):
    native = Images([image(id=identity) for identity in ids])
    with pytest.raises(catalog.McpCatalogError, match="identity"):
        await catalog.list_project_images(connection(images=native), project_id=PROJECT, marker=marker)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 503])
async def test_shared_membership_unavailable_is_not_downgraded_to_empty_catalog(status):
    class Unavailable(Images):
        def get(self, path, **kwargs):
            return SimpleNamespace(status_code=status, json=lambda: {"error": "native-secret"})

    with pytest.raises(catalog.McpCatalogError, match="membership is unavailable"):
        await catalog.list_project_images(
            connection(images=Unavailable([image(visibility="shared")])),
            project_id=PROJECT,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 404])
async def test_nonmember_shared_image_is_skipped_without_hiding_healthy_catalog(status):
    class Denied(Images):
        def get(self, path, **kwargs):
            return SimpleNamespace(status_code=status, json=lambda: {"error": "native-secret"})

    native = Denied([image(id="unshared", visibility="shared"), image(id="public")])
    conn = connection(images=native)
    page = await catalog.list_project_images(conn, project_id=PROJECT)
    assert [row["id"] for row in page["images"]] == ["public"]
    with pytest.raises(catalog.McpCatalogError, match="visibility"):
        await catalog.get_project_image(conn, project_id=PROJECT, image_id="unshared")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["a/b", "a\\b", "a?user_id=other", "a#fragment", "a%2fsecret"])
async def test_key_names_cannot_retarget_native_path_or_query(name):
    native = Compute()
    with pytest.raises(catalog.McpCatalogError, match="reserved path"):
        await catalog.get_user_keypair(connection(compute=native), user_id=USER, key_name=name)
    assert native.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["flavor", "image", "keypair"])
async def test_provider_error_is_redacted(kind):
    class Broken:
        def flavors(self, **kwargs):
            raise RuntimeError("Bearer SECRET https://provider.invalid/private")

        images = flavors

        def get(self, *args, **kwargs):
            raise RuntimeError("Bearer SECRET https://provider.invalid/private")

    native = Broken()
    conn = connection(compute=native, images=native)
    with pytest.raises(catalog.McpCatalogError, match="unavailable") as caught:
        if kind == "flavor":
            await catalog.list_project_flavors(conn, project_id=PROJECT)
        elif kind == "image":
            await catalog.list_project_images(conn, project_id=PROJECT)
        else:
            await catalog.list_user_keypairs(conn, user_id=USER)
    assert "SECRET" not in str(caught.value)
    assert "provider.invalid" not in str(caught.value)


@pytest.mark.asyncio
async def test_cancelled_catalog_read_drains_owned_sdk_thread_before_returning():
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    class Slow(Compute):
        def get_keypair(self, key_name):
            started.set()
            release.wait(5)
            completed.set()
            return key()

    task = asyncio.create_task(catalog.get_user_keypair(connection(compute=Slow()), user_id=USER, key_name="work key"))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert completed.is_set()
    finally:
        release.set()
        if not task.done():
            await asyncio.gather(task, return_exceptions=True)
