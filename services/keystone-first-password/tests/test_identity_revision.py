import json
import os
import uuid

import pytest
from keystone.common import sql
from sqlalchemy import create_engine, text
from test_native import password_rows


def proof(native, subject):
    response = native["client"].get("/v3/users/" + subject["id"] + "/OS-AFTERGLOW/initial-password/identity", headers={"X-Auth-Token": native["token"]})
    assert response.status_code == 200
    value = response.json["user"]
    assert isinstance(value["identity_revision"], str)
    assert value["identity_revision"] == str(int(value["identity_revision"]))
    return value


@pytest.mark.parametrize("changed", ["other@example.invalid", "Synthetic@example.invalid"])
def test_email_aba_on_other_galera_node_is_fenced(native, subject, post, changed):
    original = proof(native, subject)
    engine = create_engine(os.environ["AFTERGLOW_KEYSTONE_TEST_WRITER_B"], hide_parameters=True)
    try:
        for email in (changed, original["email"]):
            with engine.begin() as connection:
                row = connection.execute(text("SELECT extra FROM `user` WHERE id=:id FOR UPDATE"), {"id": subject["id"]}).scalar_one()
                extra = json.loads(row)
                extra["email"] = email
                connection.execute(text("UPDATE `user` SET extra=:extra WHERE id=:id"), {"id": subject["id"], "extra": json.dumps(extra)})
        fresh = proof(native, subject)
        assert fresh["email"] == original["email"]
        assert int(fresh["identity_revision"]) > int(original["identity_revision"])
        response = post(subject, proof=original)
        assert response.status_code == 412 and response.json["error"]["reason"] == "identity_changed"
        assert password_rows(subject["id"]) == []
    finally:
        engine.dispose()


def test_same_uuid_delete_and_recreate_is_not_same_identity_revision(native, subject, post):
    original = proof(native, subject)
    manager = native["providers"].identity_api
    _, driver, entity_id = manager._get_domain_driver_and_entity_id(subject["id"])
    driver.delete_user(entity_id)
    driver.create_user(entity_id, {"id": entity_id, "name": subject["name"], "domain_id": subject["domain_id"], "enabled": True, "email": original["email"]})
    assert int(proof(native, subject)["identity_revision"]) > int(original["identity_revision"])
    assert post(subject, proof=original).status_code == 412
    assert password_rows(subject["id"]) == []


def test_last_active_only_and_same_extra_do_not_invalidate_proof(native, subject, post):
    original = proof(native, subject)
    with sql.session_for_write() as session:
        session.execute(text("UPDATE `user` SET last_active_at=CURRENT_DATE(),extra=extra WHERE id=:id"), {"id": subject["id"]})
    assert proof(native, subject)["identity_revision"] == original["identity_revision"]
    assert post(subject, proof=original).status_code == 204


@pytest.mark.parametrize("revision", ["-1", "01", "", "1.0", "18446744073709551616", "9" * 5000, 1, None])
def test_revision_wire_format_fails_before_password_write(native, subject, post, revision):
    original = proof(native, subject)
    original["identity_revision"] = revision
    assert post(subject, proof=original).status_code == 400
    assert password_rows(subject["id"]) == []


def test_exact_original_email_required_even_with_current_revision(native, subject, post):
    original = proof(native, subject)
    original["email"] = "wrong@example.invalid"
    assert post(subject, proof=original).status_code == 412
    assert password_rows(subject["id"]) == []


@pytest.mark.parametrize("algorithm,maximum,accepted,rejected", [("bcrypt", 4096, "é" * 36, "é" * 37), ("scrypt", 12, "é" * 6, "é" * 7)])
def test_utf8_bytes_never_silently_truncated(native, subject, post, algorithm, maximum, accepted, rejected):
    import afterglow_keystone_first_password as extension
    old_algorithm = extension.CONF.identity.password_hash_algorithm
    old_max = extension.CONF.identity.max_password_length
    extension.CONF.set_override("password_hash_algorithm", algorithm, group="identity")
    extension.CONF.set_override("max_password_length", maximum, group="identity")
    try:
        assert post(subject, password=rejected).status_code == 422
        assert password_rows(subject["id"]) == []
        assert post(subject, password=accepted).status_code == 204
    finally:
        extension.CONF.set_override("password_hash_algorithm", old_algorithm, group="identity")
        extension.CONF.set_override("max_password_length", old_max, group="identity")


@pytest.mark.parametrize("operation", ["binding_delete", "binding_aba", "protocol_update", "protocol_delete", "idp_delete"])
def test_federation_parent_cascade_and_binding_aba_invalidate_proof(native, subject, post, operation):
    providers = native["providers"]
    idp, mapping = "idp-" + uuid.uuid4().hex, "map-" + uuid.uuid4().hex
    providers.federation_api.create_mapping(mapping, {"rules": []})
    providers.federation_api.create_idp(idp, {"id": idp, "domain_id": native["domain"], "enabled": True, "remote_ids": []})
    providers.federation_api.create_protocol(idp, "openid", {"mapping_id": mapping})
    binding = {"user_id": subject["id"], "idp_id": idp, "protocol_id": "openid", "unique_id": uuid.uuid4().hex, "display_name": subject["name"]}
    providers.shadow_users_api.create_federated_object(binding)
    original = proof(native, subject)
    engine = create_engine(os.environ["AFTERGLOW_KEYSTONE_TEST_WRITER_B"], hide_parameters=True)
    try:
        with engine.begin() as connection:
            if operation == "binding_delete":
                connection.execute(text("DELETE FROM federated_user WHERE user_id=:id"), {"id": subject["id"]})
            elif operation == "binding_aba":
                for value in ("different-provider-subject", binding["unique_id"]):
                    connection.execute(text("UPDATE federated_user SET unique_id=:value WHERE user_id=:id"), {"id": subject["id"], "value": value})
            elif operation == "protocol_update":
                connection.execute(text("UPDATE federation_protocol SET remote_id_attribute='changed' WHERE idp_id=:id"), {"id": idp})
            elif operation == "protocol_delete":
                connection.execute(text("DELETE FROM federation_protocol WHERE idp_id=:id"), {"id": idp})
            else:
                connection.execute(text("DELETE FROM identity_provider WHERE id=:id"), {"id": idp})
        assert int(proof(native, subject)["identity_revision"]) > int(original["identity_revision"])
        assert post(subject, proof=original).status_code == 412
        assert password_rows(subject["id"]) == []
    finally:
        engine.dispose()


def test_regex_failure_is_dedicated_prewrite_422(native, subject, post):
    import afterglow_keystone_first_password as extension
    original = extension.CONF.security_compliance.password_regex
    extension.CONF.set_override("password_regex", r"^Only-this-exact-string!$", group="security_compliance")
    try:
        response = post(subject, password="Does-not-match-926!")
        assert response.status_code == 422 and response.json["error"]["reason"] == "invalid_password"
        assert password_rows(subject["id"]) == []
    finally:
        extension.CONF.set_override("password_regex", original, group="security_compliance")
