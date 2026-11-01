"""Installed-native conditional reset; no mock password/SQL implementation."""
import json
import os
import uuid

import afterglow_keystone_first_password as extension
import pytest
from keystone import exception, notifications
from keystone.common import password_hashing, sql
from oslo_policy import policy
from sqlalchemy import create_engine, event, text
from test_credential_state import MALFORMED_HASHES, current_binding, federate, snapshot
from test_identity_revision import proof as identity_proof
from test_native import password_rows

OLD = "Synthetic-old-password-529!"
NEW = "Synthetic-new-password-826!"


def reset(native, subject, password=NEW, proof=None, token=None, domain=None, body=None):
    if proof is None:
        response = snapshot(native, subject)
        if response.status_code != 200:
            return response
        proof = response.json["user"]
    if body is None:
        body = {"user": {
            "password": password, "domain_id": domain or subject["domain_id"],
            "email": proof["email"], "identity_revision": proof["identity_revision"],
        }}
    return native["client"].post(
        "/v3/users/" + subject["id"] + "/OS-AFTERGLOW/password-reset",
        headers={"X-Auth-Token": native["token"] if token is None else token}, json=body,
    )


def set_existing(native, subject):
    native["providers"].identity_api.update_user(subject["id"], {
        "password": OLD, "afterglow_local_password": False,
    })
    return identity_proof(native, subject)


def authenticate(native, subject, password):
    return native["client"].post("/v3/auth/tokens", json={"auth": {
        "identity": {"methods": ["password"], "password": {"user": {
            "id": subject["id"], "password": password,
        }}},
    }})


def test_existing_mapped_reset_uses_native_setter_preserves_identity_revokes_and_audits(native, monkeypatch):
    providers = native["providers"]
    # Create the existing credential natively, without a preceding reset event.
    # Fernet timestamps truncate to seconds; issuing immediately after a setup
    # password UPDATE can otherwise start with an already-revoked token.
    subject = providers.identity_api.create_user({
        "name": "existing-reset-" + uuid.uuid4().hex, "domain_id": native["domain"],
        "enabled": True, "email": "synthetic-reset@example.invalid", "password": OLD,
        "afterglow_local_password": False, "nested_metadata": {"preserve": [1, 2]},
    })
    federation = federate(native, subject)
    binding = identity_proof(native, subject)
    before = providers.identity_api.get_user(subject["id"])
    token = providers.token_provider_api.issue_token(subject["id"], ["password"])
    providers.token_provider_api.validate_token(token.id)
    audited = []
    original = notifications.Audit.updated
    def record(resource, resource_id, initiator=None, *args, **kwargs):
        audited.append((resource, resource_id, initiator))
        return original(resource, resource_id, initiator, *args, **kwargs)
    monkeypatch.setattr(notifications.Audit, "updated", record)
    response = reset(native, subject, proof=binding)
    assert response.status_code == 204
    assert response.data == b""
    after = providers.identity_api.get_user(subject["id"])
    for field in ("id", "domain_id", "name", "email", "enabled", "nested_metadata"):
        assert after[field] == before[field]
    assert after["afterglow_local_password"] is True
    assert providers.shadow_users_api.get_federated_objects(subject["id"]) == federation
    rows = password_rows(subject["id"])
    assert sum(password_hashing.check_password(NEW, row.password_hash) for row in rows) == 1
    assert authenticate(native, subject, OLD).status_code == 401
    assert authenticate(native, subject, NEW).status_code == 201
    with pytest.raises(exception.TokenNotFound):
        providers.token_provider_api.validate_token(token.id)
    assert any(resource_id == subject["id"] for _, resource_id, _ in audited)
    assert OLD not in repr(audited) and NEW not in repr(audited)
    fresh = identity_proof(native, subject)
    assert fresh["password_state"] == "existing"
    assert int(fresh["identity_revision"]) > int(binding["identity_revision"])
    encoded = json.dumps(fresh)
    assert NEW not in encoded and OLD not in encoded and "password_hash" not in encoded
    assert all(row.password_hash not in encoded for row in rows)


@pytest.mark.parametrize("mapped", [False, True])
def test_reset_never_creates_first_password(native, subject, mapped):
    if mapped:
        federate(native, subject)
    binding = identity_proof(native, subject)
    assert binding["password_state"] == "absent"
    assert reset(native, subject, proof=binding).status_code == 409
    assert password_rows(subject["id"]) == []
    assert identity_proof(native, subject)["identity_revision"] == binding["identity_revision"]


@pytest.mark.parametrize("hashed", MALFORMED_HASHES)
def test_reset_refuses_invalid_actual_history_inside_guard(native, subject, hashed):
    set_existing(native, subject)
    with sql.session_for_write() as session:
        session.execute(text(
            "UPDATE password p JOIN local_user l ON l.id=p.local_user_id "
            "SET p.password_hash=:hashed WHERE l.user_id=:id"
        ), {"id": subject["id"], "hashed": hashed})
    binding = current_binding(subject)
    before = password_rows(subject["id"])
    response = reset(native, subject, proof=binding)
    assert response.status_code == 503
    assert NEW not in json.dumps(response.json)
    assert "password_hash" not in json.dumps(response.json)
    if hashed:
        assert hashed not in json.dumps(response.json)
    assert password_rows(subject["id"]) == before
    assert current_binding(subject) == binding


def test_reset_refuses_valid_history_behind_null(native, subject):
    set_existing(native, subject)
    with sql.session_for_write() as session:
        session.execute(text(
            "INSERT INTO password(local_user_id,password_hash,created_at,created_at_int,self_service) "
            "SELECT id,NULL,NOW(),1,0 FROM local_user WHERE user_id=:id"
        ), {"id": subject["id"]})
    before = password_rows(subject["id"])
    assert reset(native, subject, proof=current_binding(subject)).status_code == 503
    assert password_rows(subject["id"]) == before


@pytest.mark.parametrize("field", ["email", "enabled", "password"])
def test_concurrent_native_identity_change_refuses_stale_reset(native, subject, field):
    binding = set_existing(native, subject)
    update = {"email": "different@example.invalid", "enabled": False, "password": "Concurrent-password-992!"}
    native["providers"].identity_api.update_user(subject["id"], {field: update[field]})
    before = password_rows(subject["id"])
    response = reset(native, subject, proof=binding)
    assert response.status_code == 412
    assert response.json["error"]["reason"] == "identity_changed"
    assert password_rows(subject["id"]) == before


@pytest.mark.parametrize("kind", ["email", "password", "federation"])
def test_other_galera_node_aba_is_fenced_for_reset(native, subject, kind):
    if kind == "federation":
        federate(native, subject)
    binding = set_existing(native, subject)
    engine = create_engine(os.environ["AFTERGLOW_KEYSTONE_TEST_WRITER_B"], hide_parameters=True)
    try:
        with engine.begin() as connection:
            if kind == "email":
                extra = json.loads(connection.execute(text("SELECT extra FROM `user` WHERE id=:id FOR UPDATE"), {"id": subject["id"]}).scalar_one())
                for email in ("changed@example.invalid", binding["email"]):
                    extra["email"] = email
                    connection.execute(text("UPDATE `user` SET extra=:extra WHERE id=:id"), {"id": subject["id"], "extra": json.dumps(extra)})
            elif kind == "password":
                hashed = connection.execute(text("SELECT p.password_hash FROM password p JOIN local_user l ON l.id=p.local_user_id WHERE l.user_id=:id FOR UPDATE"), {"id": subject["id"]}).scalar_one()
                for value in (None, hashed):
                    connection.execute(text("UPDATE password p JOIN local_user l ON l.id=p.local_user_id SET p.password_hash=:hashed WHERE l.user_id=:id"), {"id": subject["id"], "hashed": value})
            else:
                unique_id = connection.execute(text("SELECT unique_id FROM federated_user WHERE user_id=:id FOR UPDATE"), {"id": subject["id"]}).scalar_one()
                for value in ("changed-subject", unique_id):
                    connection.execute(text("UPDATE federated_user SET unique_id=:value WHERE user_id=:id"), {"id": subject["id"], "value": value})
        fresh = identity_proof(native, subject)
        assert fresh["email"] == binding["email"]
        assert fresh["password_state"] == "existing"
        assert int(fresh["identity_revision"]) > int(binding["identity_revision"])
        before = password_rows(subject["id"])
        assert reset(native, subject, proof=binding).status_code == 412
        assert password_rows(subject["id"]) == before
    finally:
        engine.dispose()


def test_same_uuid_recreation_cannot_use_prior_reset_proof(native, subject):
    binding = set_existing(native, subject)
    manager = native["providers"].identity_api
    _, driver, entity_id = manager._get_domain_driver_and_entity_id(subject["id"])
    driver.delete_user(entity_id)
    driver.create_user(entity_id, {
        "id": entity_id, "name": subject["name"], "domain_id": subject["domain_id"],
        "enabled": True, "email": subject["email"], "password": OLD,
    })
    before = password_rows(subject["id"])
    assert reset(native, subject, proof=binding).status_code == 412
    assert password_rows(subject["id"]) == before


@pytest.mark.parametrize("field", ["email", "domain_id"])
def test_exact_email_and_home_required_with_current_revision(native, subject, field):
    binding = set_existing(native, subject)
    before = password_rows(subject["id"])
    if field == "email":
        binding["email"] = "different@example.invalid"
        response = reset(native, subject, proof=binding)
        assert response.status_code == 412
    else:
        response = reset(native, subject, proof=binding, domain=uuid.uuid4().hex)
        assert response.status_code == 403
    assert password_rows(subject["id"]) == before


@pytest.mark.parametrize("password", [None, "", "x" * 4097])
def test_reset_invalid_native_password_is_prewrite_422(native, subject, password):
    binding = set_existing(native, subject)
    before = password_rows(subject["id"])
    response = reset(native, subject, proof=binding, password=password)
    assert response.status_code == 422
    assert response.json["error"]["reason"] == "invalid_password"
    assert password_rows(subject["id"]) == before
    assert current_binding(subject)["identity_revision"] == binding["identity_revision"]


@pytest.mark.parametrize("body", [{}, {"user": {}}, {"user": {"password": NEW}}, {"user": {}, "other": {}}])
def test_reset_requires_exact_body(native, subject, body):
    binding = set_existing(native, subject)
    before = password_rows(subject["id"])
    assert reset(native, subject, proof=binding, body=body).status_code == 400
    assert password_rows(subject["id"]) == before


def test_reset_service_identity_and_native_admin_policy_are_both_required(native, subject):
    binding = set_existing(native, subject)
    ordinary = native["providers"].identity_api.create_user({
        "name": "reset-ordinary-" + uuid.uuid4().hex, "domain_id": native["domain"],
        "enabled": True, "password": "Ordinary-password-712!",
    })
    token = authenticate(native, ordinary, "Ordinary-password-712!")
    assert token.status_code == 201
    before = password_rows(subject["id"])
    assert reset(native, subject, proof=binding, token=token.headers["X-Subject-Token"]).status_code == 403
    assert reset(native, subject, proof=binding, token="invalid-native-token").status_code == 401
    previous = extension.CONF[extension.GROUP].service_user_id
    extension.CONF.set_override("service_user_id", ordinary["id"], group=extension.GROUP)
    try:
        assert reset(native, subject, proof=binding, token=token.headers["X-Subject-Token"]).status_code == 403
    finally:
        extension.CONF.set_override("service_user_id", previous, group=extension.GROUP)
    from keystone.common import rbac_enforcer
    enforcer = rbac_enforcer.RBACEnforcer()._enforcer
    original = policy.Rules(dict(enforcer.rules))
    enforcer.set_rules(policy.Rules.from_dict({"identity:update_user": "!"}), overwrite=False)
    try:
        assert reset(native, subject, proof=binding).status_code == 403
    finally:
        enforcer.set_rules(original, overwrite=True)
    assert password_rows(subject["id"]) == before


def test_reset_does_not_retry_native_database_failure(native, subject):
    binding = set_existing(native, subject)
    before = password_rows(subject["id"])
    with sql.session_for_write() as session:
        engine = session.get_bind()
    attempts = []
    def fail_dispatch(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO PASSWORD"):
            attempts.append(True)
            raise RuntimeError("Synthetic native failure, not a secret")
    event.listen(engine, "before_cursor_execute", fail_dispatch)
    try:
        response = reset(native, subject, proof=binding)
    finally:
        event.remove(engine, "before_cursor_execute", fail_dispatch)
    assert response.status_code == 503
    assert len(attempts) == 1
    assert NEW not in json.dumps(response.json) and OLD not in json.dumps(response.json)
    assert password_rows(subject["id"]) == before
    assert current_binding(subject)["identity_revision"] == binding["identity_revision"]


@pytest.mark.parametrize("kind", ["email_aba", "history_delete"])
def test_other_node_change_during_actual_reset_dispatch_cannot_be_overwritten(native, subject, kind):
    binding = set_existing(native, subject)
    with sql.session_for_write() as session:
        local_engine = session.get_bind()
    remote = create_engine(os.environ["AFTERGLOW_KEYSTONE_TEST_WRITER_B"], hide_parameters=True)
    attempts = []
    def change_before_guard(connection, cursor, statement, parameters, context, many):
        if not statement.lstrip().upper().startswith("UPDATE AFTERGLOW_PASSWORD_GUARD"):
            return
        attempts.append(True)
        if len(attempts) != 1:
            raise AssertionError("Conditional dispatch retried")
        with remote.begin() as writer:
            if kind == "email_aba":
                extra = json.loads(writer.execute(text("SELECT extra FROM `user` WHERE id=:id FOR UPDATE"), {"id": subject["id"]}).scalar_one())
                for email in ("changed-mid-reset@example.invalid", binding["email"]):
                    extra["email"] = email
                    writer.execute(text("UPDATE `user` SET extra=:extra WHERE id=:id"), {"id": subject["id"], "extra": json.dumps(extra)})
            else:
                writer.execute(text("DELETE p FROM password p JOIN local_user l ON l.id=p.local_user_id WHERE l.user_id=:id"), {"id": subject["id"]})
    event.listen(local_engine, "before_cursor_execute", change_before_guard)
    try:
        response = reset(native, subject, proof=binding)
    finally:
        event.remove(local_engine, "before_cursor_execute", change_before_guard)
        remote.dispose()
    assert attempts == [True]
    assert response.status_code == 412
    rows = password_rows(subject["id"])
    if kind == "history_delete":
        assert rows == []
        assert reset(native, subject, proof=identity_proof(native, subject)).status_code == 409
        assert password_rows(subject["id"]) == []
    else:
        assert len(rows) == 1
        assert password_hashing.check_password(OLD, rows[0].password_hash)


def test_shadow_only_never_password_reset_does_not_create_local_mapping(native):
    providers = native["providers"]
    idp, mapping = "reset-shadow-" + uuid.uuid4().hex, "reset-map-" + uuid.uuid4().hex
    providers.federation_api.create_mapping(mapping, {"rules": []})
    providers.federation_api.create_idp(idp, {"id": idp, "domain_id": native["domain"], "enabled": True, "remote_ids": []})
    providers.federation_api.create_protocol(idp, "openid", {"mapping_id": mapping})
    subject = providers.shadow_users_api.create_federated_user(native["domain"], {
        "idp_id": idp, "protocol_id": "openid", "unique_id": uuid.uuid4().hex,
        "display_name": "reset-shadow-name-" + uuid.uuid4().hex,
    }, email="synthetic@example.invalid")
    before = providers.shadow_users_api.get_federated_objects(subject["id"])
    assert identity_proof(native, subject)["password_state"] == "absent"
    assert reset(native, subject).status_code == 409
    with sql.session_for_write() as session:
        assert session.execute(text("SELECT id FROM local_user WHERE user_id=:id"), {"id": subject["id"]}).all() == []
    assert password_rows(subject["id"]) == []
    assert providers.shadow_users_api.get_federated_objects(subject["id"]) == before
