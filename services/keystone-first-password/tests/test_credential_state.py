"""Authoritative state is native SQL history, never a federation/extra marker."""
import json
import uuid

import afterglow_keystone_first_password as extension
import pytest
from keystone.common import sql
from sqlalchemy import text
from test_identity_revision import proof
from test_native import password_rows


def snapshot(native, subject):
    return native["client"].get(
        "/v3/users/" + subject["id"] + "/OS-AFTERGLOW/initial-password/identity",
        headers={"X-Auth-Token": native["token"]},
    )


def current_binding(subject):
    # Fixture-only current revision for exercising mutations against deliberately
    # malformed history, whose real HTTP state endpoint must refuse disclosure.
    with sql.session_for_write() as session:
        revision = session.execute(text(
            "SELECT revision FROM afterglow_password_guard WHERE user_id=:id FOR UPDATE"
        ), {"id": subject["id"]}).scalar_one()
    return {"email": subject["email"], "identity_revision": str(revision)}


def federate(native, subject):
    providers = native["providers"]
    idp, mapping = "state-idp-" + uuid.uuid4().hex, "state-map-" + uuid.uuid4().hex
    providers.federation_api.create_mapping(mapping, {"rules": []})
    providers.federation_api.create_idp(idp, {
        "id": idp, "domain_id": native["domain"], "enabled": True, "remote_ids": [],
    })
    providers.federation_api.create_protocol(idp, "openid", {"mapping_id": mapping})
    providers.shadow_users_api.create_federated_object({
        "user_id": subject["id"], "idp_id": idp, "protocol_id": "openid",
        "unique_id": uuid.uuid4().hex, "display_name": subject["name"],
    })
    return providers.shadow_users_api.get_federated_objects(subject["id"])


def test_snapshot_absent_is_current_empty_history_not_metadata(native, subject):
    native["providers"].identity_api.update_user(subject["id"], {"afterglow_local_password": True})
    value = proof(native, subject)
    assert value["password_state"] == "absent"
    assert set(value) == {"id", "domain_id", "email", "identity_revision", "password_state"}
    assert password_rows(subject["id"]) == []


def test_snapshot_existing_ignores_stale_false_metadata_and_federation(native, subject):
    before = federate(native, subject)
    native["providers"].identity_api.update_user(subject["id"], {
        "password": "Synthetic-existing-825!", "afterglow_local_password": False,
    })
    rows = password_rows(subject["id"])
    response = snapshot(native, subject)
    assert response.status_code == 200
    assert response.json["user"]["password_state"] == "existing"
    encoded = json.dumps(response.json)
    assert "Synthetic-existing-825!" not in encoded
    assert "password_hash" not in encoded
    assert all(row.password_hash not in encoded for row in rows)
    assert password_rows(subject["id"]) == rows
    assert native["providers"].shadow_users_api.get_federated_objects(subject["id"]) == before
    assert native["providers"].identity_api.get_user(subject["id"])["afterglow_local_password"] is False


def test_snapshot_expired_valid_password_is_still_existing(native, subject):
    native["providers"].identity_api.update_user(subject["id"], {"password": "Synthetic-expired-689!"})
    with sql.session_for_write() as session:
        session.execute(text(
            "UPDATE password p JOIN local_user l ON l.id=p.local_user_id "
            "SET p.expires_at_int=1 WHERE l.user_id=:id"
        ), {"id": subject["id"]})
    assert proof(native, subject)["password_state"] == "existing"


@pytest.mark.parametrize("algorithm", ["bcrypt", "bcrypt_sha256", "pbkdf2_sha512", "scrypt"])
def test_snapshot_accepts_actual_native_supported_hashes_without_kdf(native, subject, monkeypatch, algorithm):
    previous = extension.CONF.identity.password_hash_algorithm
    extension.CONF.set_override("password_hash_algorithm", algorithm, group="identity")
    try:
        native["providers"].identity_api.update_user(subject["id"], {"password": "Synthetic-format-284!"})
    finally:
        extension.CONF.set_override("password_hash_algorithm", previous, group="identity")
    def no_kdf(*args, **kwargs):
        raise AssertionError("State snapshots must not compute password KDFs")
    # Actual persisted native hash and the installed HTTP route remain real.
    for hasher in extension.password_hashing.SUPPORTED_HASHERS:
        monkeypatch.setattr(hasher, "verify", no_kdf)
        monkeypatch.setattr(hasher, "hash", no_kdf)
    assert proof(native, subject)["password_state"] == "existing"


MALFORMED_HASHES = [
    None, "", "not-a-native-hash", "$scrypt$ln=16,r=8,p=1$c2FsdA$AA",
    "$scrypt$ln=16,r=8,p=1$c2FsdA$", "$pbkdf2-sha512$25000$c2FsdA$AA",
    "$pbkdf2-sha512$0$c2FsdA$AA", "$2b$12$truncated",
    "$bcrypt-sha256$v=2,t=2b,r=12$bad$bad",
    "$2b$12$" + "A" * 53,
    "$2b$12$" + "A" * 21 + "." + "A" * 31,
    "$2$12$" + "A" * 21 + "." + "A" * 30 + ".",
    "$bcrypt-sha256$v=2,t=2b,r=12$" + "A" * 22 + "$" + "A" * 31,
    "$bcrypt-sha256$v=2,t=2b,r=12$" + "A" * 21 + ".$" + "A" * 31,
]


@pytest.mark.parametrize("hashed", MALFORMED_HASHES)
def test_malformed_history_never_reports_absence_or_existing(native, subject, hashed):
    native["providers"].identity_api.update_user(subject["id"], {"password": "Synthetic-corrupt-492!"})
    with sql.session_for_write() as session:
        session.execute(text(
            "UPDATE password p JOIN local_user l ON l.id=p.local_user_id "
            "SET p.password_hash=:hashed WHERE l.user_id=:id"
        ), {"id": subject["id"], "hashed": hashed})
    before = password_rows(subject["id"])
    response = snapshot(native, subject)
    assert response.status_code == 503
    assert "password_state" not in json.dumps(response.json)
    assert "Synthetic-corrupt-492!" not in json.dumps(response.json)
    if hashed:
        assert hashed not in json.dumps(response.json)
    assert password_rows(subject["id"]) == before


def test_valid_old_hash_behind_null_is_ambiguous(native, subject):
    native["providers"].identity_api.update_user(subject["id"], {"password": "Synthetic-prior-619!"})
    with sql.session_for_write() as session:
        session.execute(text(
            "INSERT INTO password(local_user_id,password_hash,created_at,created_at_int,self_service) "
            "SELECT id,NULL,NOW(),1,0 FROM local_user WHERE user_id=:id"
        ), {"id": subject["id"]})
    before = password_rows(subject["id"])
    assert snapshot(native, subject).status_code == 503
    assert password_rows(subject["id"]) == before


def test_native_guard_prevents_local_home_rebinding(native, subject):
    from sqlalchemy.exc import DBAPIError

    native["providers"].identity_api.update_user(subject["id"], {"password": "Synthetic-home-628!"})
    other = uuid.uuid4().hex
    native["providers"].resource_api.create_domain(other, {"id": other, "name": other, "enabled": True})
    before = proof(native, subject)
    with pytest.raises(DBAPIError) as blocked:
        with sql.session_for_write() as session:
            session.execute(text("UPDATE local_user SET domain_id=:domain WHERE user_id=:id"), {
                "id": subject["id"], "domain": other,
            })
    assert blocked.value.orig.args[0] == 1644
    assert proof(native, subject) == before

def test_snapshot_unavailable_guard_never_leaks_history(native, subject):
    native["providers"].identity_api.update_user(subject["id"], {"password": "Synthetic-unavailable-619!"})
    previous = extension.CONF[extension.GROUP].enabled
    extension.CONF.set_override("enabled", False, group=extension.GROUP)
    try:
        response = snapshot(native, subject)
        assert response.status_code == 503
        assert "Synthetic-unavailable-619!" not in json.dumps(response.json)
        assert "password_state" not in json.dumps(response.json)
    finally:
        extension.CONF.set_override("enabled", previous, group=extension.GROUP)
