"""DataMountSpec validation and explicit instance storage-access grant boundaries."""

import copy
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Response

from app.api.compute import instances
from app.api.deps import get_os_conn_write, get_token_info, require_project_write
from app.main import app
from app.models.compute import DataMountSpec, StorageAttachRequest
from tests.conftest import make_token_info

# ────── 모델 검증 ──────


@pytest.mark.parametrize(
    "path",
    [
        "/mnt/mydata",
        "/mnt/data-set_1.2",
        "/data/work",
        "/srv/files",
        "/home/userdir",
        "/mnt",
        "/data",
    ],
)
def test_data_mount_spec_valid_paths(path):
    spec = DataMountSpec(file_storage_id="share-1", mount_point=path, read_only=False)
    assert spec.mount_point == path


@pytest.mark.parametrize(
    "path",
    [
        "mnt/data",  # 상대 경로
        "/tmp/data",  # 허용 외 prefix
        "/opt/layers/merged",  # 차단 prefix
        "/etc/myconf",  # 차단 prefix
        "/usr/local/bin",  # 차단 prefix
        "/opt/layers",  # 차단 prefix 정확 일치
        "/mnt/a/b c",  # 공백 포함
        "/mnt/../etc/passwd",  # path traversal
    ],
)
def test_data_mount_spec_invalid_paths(path):
    with pytest.raises(Exception):
        DataMountSpec(file_storage_id="share-1", mount_point=path, read_only=False)


@pytest.mark.parametrize(
    "payload",
    [
        {"file_storage_id": "s1", "mount_point": "/mnt/x$y"},  # 쉘 메타문자 $
        {"file_storage_id": "s1", "mount_point": "/mnt/x`y"},  # 백틱
        {"file_storage_id": "s1", "mount_point": "/mnt/x;y"},  # 세미콜론
        {"file_storage_id": "s1", "mount_point": "/mnt/x\ny"},  # 개행
    ],
)
def test_data_mount_spec_injection_chars_rejected(payload):
    with pytest.raises(Exception):
        DataMountSpec(**payload)


# ────── Explicit storage-access grants; no guest mount or unmount ──────

INSTANCE_ID = "11111111-2222-4333-8444-555555555555"
OTHER_INSTANCE_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
SHARE_ID = "01234567-89ab-4cde-8fab-0123456789ab"
OTHER_SHARE_ID = "abcdef01-2345-4678-8abc-def012345678"
RULE_ID = "12345678-1234-4234-8234-123456789abc"
BASE_URL = f"/api/v1/instances/{INSTANCE_ID}/storage-attachments"


def _ip(addr, kind="fixed"):
    return SimpleNamespace(addr=addr, type=kind)


def _make_server(project_id="test-project-123", name="vm-1"):
    return SimpleNamespace(
        id=INSTANCE_ID,
        name=name,
        project_id=project_id,
        metadata={},
        ip_addresses=[_ip("10.0.0.5")],
    )


def _make_share(share_id=SHARE_ID, proto="NFS", project_id="test-project-123", status="available"):
    return SimpleNamespace(
        id=share_id,
        name="test-share",
        share_proto=proto,
        project_id=project_id,
        is_public=False,
        status=status,
        nfs_export_location="192.168.1.10:/volumes/share-1",
        export_locations=["192.168.1.10:/volumes/share-1"],
        share_network_id=None,
    )


def _rule(access_to="10.0.0.5", access_type="ip", level="rw", owner=None, rule_id=RULE_ID, state="active"):
    return {
        "id": rule_id,
        "access_to": access_to,
        "access_type": access_type,
        "access_level": level,
        "state": state,
        "access_key": "CEPH_SECRET_MUST_NOT_LEAK==" if access_type == "cephx" else None,
        "metadata": {"afterglow_instance_id": owner} if owner is not None else {},
    }


@pytest.fixture
def grants(mock_conn, monkeypatch):
    """Keep provider rules and Nova metadata separate so ownership/state changes are observable."""
    env = SimpleNamespace(
        server=_make_server(),
        share=_make_share(),
        rules=[],
        create_state="new",
        create_key="CEPH_SECRET_MUST_NOT_LEAK==",
        pending_revoke=False,
    )

    def create(conn, file_storage_id, access_to, access_level="ro", access_type="cephx", metadata=None, **kwargs):
        rule = _rule(access_to, access_type, access_level, state=env.create_state)
        rule["metadata"] = dict(metadata or {})
        if access_type == "cephx":
            rule["access_key"] = env.create_key
        env.rules.append(rule)
        return dict(rule)

    def revoke(conn, file_storage_id, access_id):
        if env.pending_revoke:
            for rule in env.rules:
                if rule["id"] == access_id:
                    rule["state"] = "denying"
        else:
            env.rules[:] = [rule for rule in env.rules if rule["id"] != access_id]

    def set_metadata(instance_id, **metadata):
        env.server.metadata.update(metadata)

    def delete_metadata(instance_id, keys):
        for key in keys:
            env.server.metadata.pop(key, None)

    env.get_server = MagicMock(side_effect=lambda conn, instance_id: env.server)
    env.get_share = MagicMock(side_effect=lambda conn, share_id: env.share)
    env.list_rules = MagicMock(side_effect=lambda conn, share_id, *, strict=False: copy.deepcopy(env.rules))
    env.get_rule = MagicMock(
        side_effect=lambda conn, share_id, access_id: next(
            (copy.deepcopy(rule) for rule in env.rules if rule["id"] == access_id),
            None,
        )
    )
    env.create = MagicMock(side_effect=create)
    env.revoke = MagicMock(side_effect=revoke)
    monkeypatch.setattr(instances.nova, "get_server", env.get_server)
    monkeypatch.setattr(instances.manila, "get_file_storage", env.get_share)
    monkeypatch.setattr(instances.manila, "list_access_rules", env.list_rules)
    monkeypatch.setattr(instances.manila, "get_access_rule", env.get_rule)
    monkeypatch.setattr(instances.manila, "create_access_rule", env.create)
    monkeypatch.setattr(instances.manila, "revoke_access_rule", env.revoke)
    monkeypatch.setattr(instances, "invalidate", AsyncMock())
    monkeypatch.setattr(instances.cache_invalidation, "invalidate_mutation_count", AsyncMock())
    mock_conn.compute.set_server_metadata.side_effect = set_metadata
    mock_conn.compute.delete_server_metadata.side_effect = delete_metadata
    return env


def _assert_no_mutation(grants, mock_conn):
    grants.create.assert_not_called()
    grants.revoke.assert_not_called()
    mock_conn.compute.set_server_metadata.assert_not_called()
    mock_conn.compute.delete_server_metadata.assert_not_called()


def test_storage_grant_request_has_no_mount_point():
    request = StorageAttachRequest(file_storage_id=SHARE_ID, read_only=True, fixed_ip="10.0.0.5")
    assert request.model_dump() == {"file_storage_id": SHARE_ID, "read_only": True, "fixed_ip": "10.0.0.5"}
    assert StorageAttachRequest(file_storage_id=SHARE_ID).fixed_ip is None


@pytest.mark.asyncio
@pytest.mark.parametrize("selected", [None, "10.0.0.5"])
async def test_nfs_single_fixed_ip_default_or_explicit_grants_exact_host(client, mock_conn, grants, selected):
    payload = {"file_storage_id": SHARE_ID}
    grants.server.ip_addresses.append(_ip("203.0.113.5", "floating"))
    if selected is not None:
        payload["fixed_ip"] = selected
    response = await client.post(BASE_URL, json=payload)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    rule = grants.rules[0]
    assert rule["access_type"] == "ip"
    assert rule["access_to"] == "10.0.0.5"
    assert rule["access_level"] == "rw"
    assert rule["metadata"]["afterglow_instance_id"] == INSTANCE_ID
    grants.get_server.assert_called_once_with(mock_conn, INSTANCE_ID)
    grants.create.assert_called_once()
    grants.revoke.assert_not_called()
    assert "mount_command" not in response.json()
    assert "keyring_file" not in response.json()


@pytest.mark.asyncio
async def test_nfs_selected_ip_is_from_fresh_instance_and_not_first_ip(client, mock_conn, grants):
    grants.server.ip_addresses = [_ip("10.0.0.5"), _ip("10.0.1.9"), _ip("203.0.113.5", "floating")]
    response = await client.post(
        BASE_URL, json={"file_storage_id": SHARE_ID, "fixed_ip": "10.0.1.9", "read_only": True}
    )

    assert response.status_code == 200
    assert grants.rules[0]["access_to"] == "10.0.1.9"
    assert grants.rules[0]["access_level"] == "ro"
    grants.get_server.assert_called_once_with(mock_conn, INSTANCE_ID)
    grants.create.assert_called_once()
    grants.revoke.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("addresses", [[], [_ip("203.0.113.5", "floating")], [_ip("10.0.0.5"), _ip("10.0.1.9")]])
async def test_nfs_missing_or_ambiguous_default_is_rejected_before_mutation(client, mock_conn, grants, addresses):
    grants.server.ip_addresses = addresses
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 409
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selected,status",
    [("10.0.0.0/24", 422), ("10.0.0.5/32", 422), ("203.0.113.5", 409), ("10.0.0.99", 409), ("not-an-ip", 422)],
)
async def test_nfs_cidr_floating_nonmember_or_invalid_target_rejected(client, mock_conn, grants, selected, status):
    grants.server.ip_addresses.append(_ip("203.0.113.5", "floating"))
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID, "fixed_ip": selected})

    assert response.status_code == status
    _assert_no_mutation(grants, mock_conn)


def _record(grants, share_id=SHARE_ID):
    records = (
        json.loads(value) for key, value in grants.server.metadata.items() if key.startswith("afterglow_share_grant_")
    )
    return next(record for record in records if record["s"] == share_id)


def _reset_mutations(grants, mock_conn):
    grants.create.reset_mock()
    grants.revoke.reset_mock()
    mock_conn.compute.set_server_metadata.reset_mock()
    mock_conn.compute.delete_server_metadata.reset_mock()


@pytest.mark.asyncio
async def test_ceph_identity_uses_instance_uuid_not_mutable_or_unsafe_name(client, mock_conn, grants):
    grants.share.share_proto = "CEPHFS"
    grants.create_state = "active"
    grants.server.name = "same name';$(touch /tmp/unsafe)\n"
    first = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID, "read_only": True})

    assert first.status_code == 200
    identity = first.json()["access_to"]
    assert identity == "afterglow-" + INSTANCE_ID.replace("-", "")
    assert re.fullmatch(r"[a-z0-9-]+", identity)
    assert grants.rules[0]["access_type"] == "cephx"
    assert grants.rules[0]["access_level"] == "ro"
    assert grants.rules[0]["metadata"] == {"afterglow_instance_id": INSTANCE_ID}
    assert grants.create.call_args.kwargs["wait_for_key"] is False
    assert first.json()["secret"] == {"type": "cephx_key", "value": "CEPH_SECRET_MUST_NOT_LEAK=="}
    assert not {"mount_command", "keyring_file", "keyring_path"} & first.json().keys()

    grants.server.name = "renamed-after-grant"
    metadata = dict(grants.server.metadata)
    _reset_mutations(grants, mock_conn)
    repeat = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID, "read_only": True})

    assert repeat.status_code == 200
    assert repeat.json()["access_to"] == identity
    assert repeat.json()["access_id"] == first.json()["access_id"]
    assert repeat.json()["managed"] is True
    assert "secret" not in repeat.json()
    assert grants.server.metadata == metadata
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("fixed_ip,instance_id", [("10.0.0.5", INSTANCE_ID), (None, "not-a-uuid")])
async def test_ceph_rejects_ip_or_non_uuid_identity_before_mutation(client, mock_conn, grants, fixed_ip, instance_id):
    grants.share.share_proto = "CEPHFS"
    grants.server.id = instance_id
    response = await client.post(
        f"/api/v1/instances/{instance_id}/storage-attachments",
        json={"file_storage_id": SHARE_ID, "fixed_ip": fixed_ip},
    )

    assert response.status_code == 422
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("proto", ["CIFS", "GLUSTERFS", "HDFS", "UNKNOWN"])
async def test_unsupported_protocol_never_falls_back_to_ceph(client, mock_conn, grants, proto):
    grants.share.share_proto = proto
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 422
    grants.list_rules.assert_not_called()
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("method", ["POST", "DELETE"])
async def test_foreign_share_even_public_is_not_management_authority(client, mock_conn, grants, public, method):
    if method == "DELETE":
        assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
        _reset_mutations(grants, mock_conn)
    grants.share.project_id = "foreign-project"
    grants.share.is_public = public
    response = await client.request(
        method,
        BASE_URL if method == "POST" else f"{BASE_URL}/{SHARE_ID}",
        json={"file_storage_id": SHARE_ID},
    )

    assert response.status_code == 404
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "GET", "DELETE"])
async def test_foreign_instance_is_hidden_before_storage_lookup(client, mock_conn, grants, method):
    grants.server.project_id = "foreign-project"
    response = await client.request(
        method,
        BASE_URL if method != "DELETE" else f"{BASE_URL}/{SHARE_ID}",
        json={"file_storage_id": SHARE_ID},
    )

    assert response.status_code == 404
    grants.get_share.assert_not_called()
    grants.list_rules.assert_not_called()
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
async def test_unavailable_share_rejects_grant_before_mutation(client, mock_conn, grants):
    grants.share.status = "creating"
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 409
    grants.list_rules.assert_not_called()
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.parametrize(
    "endpoint", [instances.attach_storage, instances.detach_storage, instances.storage_connection_info]
)
def test_storage_mutations_declare_project_write_dependency(endpoint):
    route = next(route for route in instances.router.routes if getattr(route, "endpoint", None) is endpoint)
    connection = next(dep for dep in route.dependant.dependencies if dep.call is get_os_conn_write)
    assert any(dep.call is require_project_write for dep in connection.dependencies)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "DELETE"])
async def test_reader_cannot_mutate_storage_even_with_owned_resources(client, mock_conn, grants, monkeypatch, method):
    monkeypatch.setitem(app.dependency_overrides, get_token_info, lambda: make_token_info(roles=["reader"]))
    response = await client.request(
        method,
        BASE_URL if method == "POST" else f"{BASE_URL}/{SHARE_ID}",
        json={"file_storage_id": SHARE_ID},
    )

    assert response.status_code == 403
    grants.get_server.assert_not_called()
    grants.get_share.assert_not_called()
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "revoke", "connection-info"])
async def test_storage_mutations_guard_function_token_without_dependency_resolution(mock_conn, grants, operation):
    token = make_token_info(roles=["reader"])
    with pytest.raises(HTTPException) as error:
        if operation == "grant":
            await instances.attach_storage(
                INSTANCE_ID,
                StorageAttachRequest(file_storage_id=SHARE_ID),
                response=Response(),
                conn=mock_conn,
                token_info=token,
            )
        elif operation == "revoke":
            await instances.detach_storage(INSTANCE_ID, SHARE_ID, conn=mock_conn, token_info=token)
        else:
            await instances.storage_connection_info(
                INSTANCE_ID,
                SHARE_ID,
                response=Response(),
                conn=mock_conn,
                token_info=token,
            )

    assert error.value.status_code == 403
    grants.get_server.assert_not_called()
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state", ["new", "queued_to_apply", "applying", "active", "error", "denying", "queued_to_deny", "unknown"]
)
async def test_get_reports_provider_rule_state_not_guest_mount_state_and_no_secret(
    client,
    mock_conn,
    grants,
    monkeypatch,
    state,
):
    grants.share.share_proto = "CEPHFS"
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    grants.rules[0]["state"] = state
    grants.rules[0]["provider_secret"] = "DO_NOT_SERIALIZE_PROVIDER_DICT"
    _reset_mutations(grants, mock_conn)
    monkeypatch.setitem(app.dependency_overrides, get_token_info, lambda: make_token_info(roles=["reader"]))
    response = await client.get(BASE_URL)

    assert response.status_code == 200
    item = response.json()[0]
    assert item["state"] == state
    assert item["association_state"] == "tracked"
    assert item["access_id"] == RULE_ID
    assert item["managed"] is True
    assert item["access_type"] == "cephx"
    assert item["exports"] == grants.share.export_locations
    assert item["share_network_id"] is None
    assert item["share_network"] is None
    assert not {"secret", "access_key", "keyring_file", "mount_command", "mounted"} & item.keys()
    assert "CEPH_SECRET_MUST_NOT_LEAK" not in response.text
    assert "DO_NOT_SERIALIZE_PROVIDER_DICT" not in response.text
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["new", "active", "error"])
async def test_post_reports_accepted_rule_state_without_claiming_active_or_mounted(client, grants, state):
    grants.create_state = state
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 200
    assert response.json()["state"] == state
    assert response.json()["managed"] is True
    assert not {"mounted", "mount_command", "active"} & response.json().keys()


@pytest.mark.asyncio
async def test_get_empty_has_no_provider_rule_lookup(client, mock_conn, grants):
    response = await client.get(BASE_URL)

    assert response.status_code == 200
    assert response.json() == []
    grants.list_rules.assert_not_called()
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_key", ["union_data_share_ids", "afterglow_data_share_ids"])
async def test_legacy_share_id_is_untracked_not_inferred_authorization(client, mock_conn, grants, legacy_key):
    grants.server.metadata = {legacy_key: SHARE_ID}
    grants.rules = [_rule(owner=INSTANCE_ID)]
    response = await client.get(BASE_URL)

    assert response.status_code == 200
    item = response.json()[0]
    assert item["file_storage_id"] == SHARE_ID
    assert item["state"] == "untracked"
    assert item["association_state"] == "untracked"
    assert item["managed"] is False
    assert item["access_id"] is None
    assert item["access_to"] is None
    grants.list_rules.assert_not_called()

    rejected = await client.delete(f"{BASE_URL}/{SHARE_ID}")
    assert rejected.status_code == 409
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,state,association",
    [
        ("absent", "missing", "tracked"),
        ("owner", "new", "mismatch"),
        ("target", "new", "mismatch"),
        ("level", "new", "mismatch"),
        ("lookup", "unknown", "unknown"),
    ],
)
async def test_get_missing_changed_or_unreadable_rule_keeps_states_separate(
    client,
    mock_conn,
    grants,
    change,
    state,
    association,
):
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    if change == "absent":
        grants.rules.clear()
    elif change == "owner":
        grants.rules[0]["metadata"]["afterglow_instance_id"] = OTHER_INSTANCE_ID
    elif change == "target":
        grants.rules[0]["access_to"] = "10.0.0.99"
    elif change == "level":
        grants.rules[0]["access_level"] = "ro"
    else:
        grants.list_rules.side_effect = RuntimeError("provider failed with private credentials")
    _reset_mutations(grants, mock_conn)
    response = await client.get(BASE_URL)

    assert response.status_code == 200
    assert response.json()[0]["state"] == state
    assert response.json()[0]["association_state"] == association
    assert "private credentials" not in response.text
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
async def test_repeat_exact_managed_grant_preserves_rule_and_association(client, mock_conn, grants):
    first = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})
    assert first.status_code == 200
    metadata = dict(grants.server.metadata)
    rules = copy.deepcopy(grants.rules)
    _reset_mutations(grants, mock_conn)
    repeat = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert repeat.status_code == 200
    assert repeat.json()["access_id"] == first.json()["access_id"]
    assert repeat.json()["managed"] is True
    assert grants.server.metadata == metadata
    assert grants.rules == rules
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"fixed_ip": "10.0.1.9"}, {"read_only": True}])
async def test_repeat_grant_rejects_target_or_level_change_without_replacement(client, mock_conn, grants, change):
    grants.server.ip_addresses.append(_ip("10.0.1.9"))
    payload = {"file_storage_id": SHARE_ID, "fixed_ip": "10.0.0.5"}
    assert (await client.post(BASE_URL, json=payload)).status_code == 200
    metadata = dict(grants.server.metadata)
    rules = copy.deepcopy(grants.rules)
    _reset_mutations(grants, mock_conn)
    response = await client.post(BASE_URL, json={**payload, **change})

    assert response.status_code == 409
    assert grants.server.metadata == metadata
    assert grants.rules == rules
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("proto", ["NFS", "CEPHFS"])
async def test_preexisting_exact_unmarked_rule_reused_unmanaged_never_revoked(client, mock_conn, grants, proto):
    grants.share.share_proto = proto
    access_type = "ip" if proto == "NFS" else "cephx"
    target = "10.0.0.5" if proto == "NFS" else "afterglow-" + INSTANCE_ID.replace("-", "")
    grants.rules = [_rule(target, access_type)]
    original = copy.deepcopy(grants.rules)
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 200
    assert response.json()["access_id"] == RULE_ID
    assert response.json()["managed"] is False
    assert "secret" not in response.json()
    assert _record(grants)["m"] is False
    grants.create.assert_not_called()
    _reset_mutations(grants, mock_conn)
    repeat = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})
    rejected = await client.delete(f"{BASE_URL}/{SHARE_ID}")

    assert repeat.status_code == 200
    assert repeat.json()["managed"] is False
    assert rejected.status_code == 409
    assert grants.rules == original
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [INSTANCE_ID, OTHER_INSTANCE_ID])
@pytest.mark.parametrize("proto", ["NFS", "CEPHFS"])
async def test_marked_but_unassociated_rule_cannot_be_adopted(client, mock_conn, grants, owner, proto):
    grants.share.share_proto = proto
    target = "10.0.0.5" if proto == "NFS" else "afterglow-" + INSTANCE_ID.replace("-", "")
    grants.rules = [_rule(target, "ip" if proto == "NFS" else "cephx", owner=owner)]
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 409
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("rules", [[_rule(level="ro")], [_rule(), _rule(rule_id="duplicate-rule")]])
async def test_preexisting_level_conflict_or_ambiguous_rules_not_replaced(client, mock_conn, grants, rules):
    grants.rules = copy.deepcopy(rules)
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 409
    assert grants.rules == rules
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("proto", ["NFS", "CEPHFS"])
async def test_exact_revoke_protects_unrelated_and_other_vm_rules(client, mock_conn, grants, proto):
    grants.share.share_proto = proto
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    target = grants.rules[0]["access_to"]
    access_type = grants.rules[0]["access_type"]
    unrelated = [
        _rule(target, access_type, owner=OTHER_INSTANCE_ID, rule_id="other-vm-rule"),
        _rule(target, access_type, rule_id="unassociated-rule"),
        _rule("10.0.0.99", "ip", owner=INSTANCE_ID, rule_id="unrelated-target-rule"),
        _rule("data-rw-vm-1-01234567", "cephx", rule_id="legacy-name-prefix-rule"),
    ]
    grants.rules.extend(copy.deepcopy(unrelated))
    grants.server.name = "renamed-after-grant"
    grants.server.metadata["unrelated_metadata"] = "keep"
    _reset_mutations(grants, mock_conn)
    response = await client.delete(f"{BASE_URL}/{SHARE_ID}")

    assert response.status_code == 204
    grants.revoke.assert_called_once_with(mock_conn, SHARE_ID, RULE_ID)
    grants.create.assert_not_called()
    assert grants.rules == unrelated
    assert grants.server.metadata == {"unrelated_metadata": "keep"}
    mock_conn.compute.set_server_metadata.assert_not_called()
    mock_conn.compute.delete_server_metadata.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["owner", "unmarked", "target", "level", "type"])
@pytest.mark.parametrize("operation", ["repeat", "revoke"])
async def test_mutation_rejects_changed_exact_rule_instead_of_inferred_match(
    client,
    mock_conn,
    grants,
    change,
    operation,
):
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    metadata = dict(grants.server.metadata)
    if change == "owner":
        grants.rules[0]["metadata"]["afterglow_instance_id"] = OTHER_INSTANCE_ID
    elif change == "unmarked":
        grants.rules[0]["metadata"] = {}
    elif change == "target":
        grants.rules[0]["access_to"] = "10.0.0.99"
    elif change == "level":
        grants.rules[0]["access_level"] = "ro"
    else:
        grants.rules[0]["access_type"] = "cephx"
    _reset_mutations(grants, mock_conn)
    if operation == "repeat":
        response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})
    else:
        response = await client.delete(f"{BASE_URL}/{SHARE_ID}")

    assert response.status_code == 409
    assert grants.server.metadata == metadata
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
async def test_unassociated_revoke_cannot_use_same_ip_or_name_prefix(client, mock_conn, grants):
    grants.rules = [_rule(owner=INSTANCE_ID), _rule("data-rw-vm-1-01234567", "cephx", rule_id="name-match")]
    response = await client.delete(f"{BASE_URL}/{SHARE_ID}")

    assert response.status_code == 409
    grants.list_rules.assert_not_called()
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
async def test_pending_provider_revoke_keeps_association_until_rule_absent(client, mock_conn, grants):
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    metadata = dict(grants.server.metadata)
    grants.pending_revoke = True
    _reset_mutations(grants, mock_conn)
    pending = await client.delete(f"{BASE_URL}/{SHARE_ID}")

    assert pending.status_code == 409
    assert grants.server.metadata == metadata
    grants.revoke.assert_called_once_with(mock_conn, SHARE_ID, RULE_ID)
    mock_conn.compute.delete_server_metadata.assert_not_called()
    _reset_mutations(grants, mock_conn)
    again = await client.delete(f"{BASE_URL}/{SHARE_ID}")
    assert again.status_code == 409
    _assert_no_mutation(grants, mock_conn)

    grants.rules.clear()
    complete = await client.delete(f"{BASE_URL}/{SHARE_ID}")
    assert complete.status_code == 204
    assert grants.server.metadata == {}
    grants.revoke.assert_not_called()
    mock_conn.compute.delete_server_metadata.assert_called_once()


@pytest.mark.asyncio
async def test_provider_revoke_failure_is_not_success_and_preserves_metadata(client, mock_conn, grants):
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    metadata = dict(grants.server.metadata)
    grants.revoke.side_effect = RuntimeError("private provider response")
    _reset_mutations(grants, mock_conn)
    response = await client.delete(f"{BASE_URL}/{SHARE_ID}")

    assert response.status_code == 502
    assert grants.server.metadata == metadata
    assert "private provider" not in response.text
    mock_conn.compute.delete_server_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_grant_metadata_failure_never_reports_success_or_compensating_revoke(client, mock_conn, grants):
    mock_conn.compute.set_server_metadata.side_effect = RuntimeError("private metadata failure")
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 502
    grants.create.assert_called_once()
    grants.revoke.assert_not_called()
    assert grants.server.metadata == {}
    assert len(grants.rules) == 1
    assert "private metadata" not in response.text


@pytest.mark.asyncio
async def test_revoke_metadata_failure_is_not_success_and_absent_rule_retry_finishes(client, mock_conn, grants):
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    metadata = dict(grants.server.metadata)
    delete_metadata = mock_conn.compute.delete_server_metadata.side_effect
    mock_conn.compute.delete_server_metadata.side_effect = RuntimeError("private metadata failure")
    _reset_mutations(grants, mock_conn)
    failed = await client.delete(f"{BASE_URL}/{SHARE_ID}")

    assert failed.status_code == 502
    assert grants.rules == []
    assert grants.server.metadata == metadata
    assert "private metadata" not in failed.text
    grants.revoke.assert_called_once_with(mock_conn, SHARE_ID, RULE_ID)

    mock_conn.compute.delete_server_metadata.side_effect = delete_metadata
    _reset_mutations(grants, mock_conn)
    complete = await client.delete(f"{BASE_URL}/{SHARE_ID}")
    assert complete.status_code == 204
    assert grants.server.metadata == {}
    grants.revoke.assert_not_called()


@pytest.mark.asyncio
async def test_metadata_is_compact_per_share_and_removal_preserves_other_association(client, mock_conn, grants):
    grants.server.metadata["user_tag"] = "preserve"
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    first_metadata = dict(grants.server.metadata)
    first_record = _record(grants)
    assert first_record == {"s": SHARE_ID, "i": RULE_ID, "t": "ip", "a": "10.0.0.5", "l": "rw", "m": True}
    grants.share = _make_share(OTHER_SHARE_ID)
    grants.rules.clear()
    _reset_mutations(grants, mock_conn)
    assert (await client.post(BASE_URL, json={"file_storage_id": OTHER_SHARE_ID})).status_code == 200

    metadata = grants.server.metadata
    grant_keys = [key for key in metadata if key.startswith("afterglow_share_grant_")]
    assert len(grant_keys) == 2
    for key in grant_keys:
        assert len(key) <= 255
        assert len(metadata[key].encode()) <= 256
        assert metadata[key] == json.dumps(json.loads(metadata[key]), separators=(",", ":"))
        assert "CEPH_SECRET" not in metadata[key]
    for key, value in first_metadata.items():
        assert metadata[key] == value

    grants.share = _make_share()
    grants.rules.clear()
    response = await client.delete(f"{BASE_URL}/{SHARE_ID}")
    assert response.status_code == 204
    assert _record(grants, OTHER_SHARE_ID)["s"] == OTHER_SHARE_ID
    assert grants.server.metadata["user_tag"] == "preserve"
    assert len(grants.server.metadata) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("state,secret", [("new", False), ("applying", False), ("error", False), ("active", True)])
async def test_ceph_secret_retrieval_requires_explicit_post_and_active_managed_rule(
    client,
    mock_conn,
    grants,
    state,
    secret,
):
    grants.share.share_proto = "CEPHFS"
    grants.create_key = None
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    grants.rules[0]["state"] = state
    grants.rules[0]["access_key"] = "CEPH_SECRET_MUST_NOT_LEAK=="
    metadata = dict(grants.server.metadata)
    _reset_mutations(grants, mock_conn)
    grants.get_server.reset_mock()
    grants.get_share.reset_mock()
    response = await client.post(f"{BASE_URL}/{SHARE_ID}/connection-info")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["state"] == state
    assert ("secret" in response.json()) is secret
    if secret:
        assert response.json()["secret"] == {"type": "cephx_key", "value": "CEPH_SECRET_MUST_NOT_LEAK=="}
    grants.get_server.assert_called_once_with(mock_conn, INSTANCE_ID)
    grants.get_share.assert_called_once_with(mock_conn, SHARE_ID)
    assert grants.server.metadata == metadata
    _assert_no_mutation(grants, mock_conn)

    listed = await client.get(BASE_URL)
    assert listed.status_code == 200
    assert "CEPH_SECRET_MUST_NOT_LEAK" not in listed.text
    assert "secret" not in listed.json()[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["untracked", "unmanaged", "missing", "other-owner", "target-changed"])
async def test_connection_secret_rejects_unassociated_or_nonexact_rule(client, mock_conn, grants, condition):
    grants.share.share_proto = "CEPHFS"
    if condition == "unmanaged":
        grants.rules = [_rule("afterglow-" + INSTANCE_ID.replace("-", ""), "cephx")]
    if condition != "untracked":
        assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    if condition == "missing":
        grants.rules.clear()
    elif condition == "other-owner":
        grants.rules[0]["metadata"]["afterglow_instance_id"] = OTHER_INSTANCE_ID
    elif condition == "target-changed":
        grants.rules[0]["access_to"] = "another-ceph-identity"
    _reset_mutations(grants, mock_conn)
    response = await client.post(f"{BASE_URL}/{SHARE_ID}/connection-info")

    assert response.status_code == 409
    assert "CEPH_SECRET_MUST_NOT_LEAK" not in response.text
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["reader", "foreign-instance", "foreign-public-share"])
async def test_connection_secret_rechecks_project_write_and_owners(client, mock_conn, grants, monkeypatch, condition):
    grants.share.share_proto = "CEPHFS"
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    grants.rules[0]["state"] = "active"
    if condition == "reader":
        monkeypatch.setitem(app.dependency_overrides, get_token_info, lambda: make_token_info(roles=["reader"]))
    elif condition == "foreign-instance":
        grants.server.project_id = "foreign-project"
    else:
        grants.share.project_id = "foreign-project"
        grants.share.is_public = True
    _reset_mutations(grants, mock_conn)
    response = await client.post(f"{BASE_URL}/{SHARE_ID}/connection-info")

    assert response.status_code == (403 if condition == "reader" else 404)
    assert "CEPH_SECRET_MUST_NOT_LEAK" not in response.text
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["share-unavailable", "key-pending"])
async def test_connection_secret_not_returned_until_share_and_key_ready(client, mock_conn, grants, condition):
    grants.share.share_proto = "CEPHFS"
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    grants.rules[0]["state"] = "active"
    if condition == "share-unavailable":
        grants.share.status = "error"
    else:
        grants.rules[0]["access_key"] = None
    _reset_mutations(grants, mock_conn)
    response = await client.post(f"{BASE_URL}/{SHARE_ID}/connection-info")

    assert response.status_code == 200
    assert "secret" not in response.json()
    assert "CEPH_SECRET_MUST_NOT_LEAK" not in response.text
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
async def test_oversized_association_rejected_before_provider_allow(client, mock_conn, grants):
    grants.share.id = "share-" + "a" * 256
    response = await client.post(BASE_URL, json={"file_storage_id": grants.share.id})

    assert response.status_code == 422
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["instance", "share"])
async def test_missing_project_ownership_is_not_write_authority(client, mock_conn, grants, resource):
    target = grants.server if resource == "instance" else grants.share
    target.project_id = None
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 404
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [None, "CEPH_SECRET_MUST_NOT_LEAK=="])
async def test_pending_ceph_grant_is_truthful_and_never_exposes_key_or_polls(client, mock_conn, grants, key):
    grants.share.share_proto = "CEPHFS"
    grants.create_key = key
    response = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert response.status_code == 200
    assert response.json()["state"] == "new"
    assert response.json()["managed"] is True
    assert "secret" not in response.json()
    assert grants.create.call_args.kwargs["wait_for_key"] is False
    grants.revoke.assert_not_called()
    assert _record(grants)["i"] == RULE_ID


@pytest.mark.asyncio
async def test_missing_exact_rule_never_recreated_or_replaced_by_matching_unassociated_rule(client, mock_conn, grants):
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    grants.rules = [_rule(rule_id="different-rule-same-target", owner=OTHER_INSTANCE_ID)]
    unrelated = copy.deepcopy(grants.rules)
    _reset_mutations(grants, mock_conn)
    repeat = await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})

    assert repeat.status_code == 409
    _assert_no_mutation(grants, mock_conn)
    revoked = await client.delete(f"{BASE_URL}/{SHARE_ID}")

    assert revoked.status_code == 204
    assert grants.rules == unrelated
    assert grants.server.metadata == {}
    grants.revoke.assert_not_called()
    grants.create.assert_not_called()


@pytest.mark.asyncio
async def test_unreadable_rule_state_blocks_revoke_before_mutation(client, mock_conn, grants):
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    metadata = dict(grants.server.metadata)
    grants.get_rule.side_effect = RuntimeError("private provider failure")
    _reset_mutations(grants, mock_conn)
    response = await client.delete(f"{BASE_URL}/{SHARE_ID}")

    assert response.status_code == 502
    assert grants.server.metadata == metadata
    assert "private provider" not in response.text
    _assert_no_mutation(grants, mock_conn)


@pytest.mark.asyncio
async def test_revoke_empty_list_does_not_hide_live_exact_rule(client, mock_conn, grants):
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    metadata = dict(grants.server.metadata)
    grants.list_rules.side_effect = lambda conn, share_id, *, strict=False: []
    grants.pending_revoke = True
    response = await client.delete(f"{BASE_URL}/{SHARE_ID}")
    assert response.status_code == 409
    assert grants.server.metadata == metadata
    assert grants.rules[0]["state"] == "denying"
    mock_conn.compute.delete_server_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_exact_confirmation_error_retains_tracking(client, mock_conn, grants):
    assert (await client.post(BASE_URL, json={"file_storage_id": SHARE_ID})).status_code == 200
    metadata = dict(grants.server.metadata)
    grants.get_rule.side_effect = [copy.deepcopy(grants.rules[0]), RuntimeError("provider timeout")]
    response = await client.delete(f"{BASE_URL}/{SHARE_ID}")
    assert response.status_code == 502
    assert grants.server.metadata == metadata
    grants.revoke.assert_called_once()
    mock_conn.compute.delete_server_metadata.assert_not_called()
