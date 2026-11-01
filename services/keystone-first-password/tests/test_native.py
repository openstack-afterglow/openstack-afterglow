import uuid

import pytest
from keystone.common import password_hashing, sql
from sqlalchemy import text


def password_rows(user_id):
    with sql.session_for_write() as session:
        return session.execute(text(
            "SELECT p.id,p.password_hash FROM password p JOIN local_user l "
            "ON l.id=p.local_user_id WHERE l.user_id=:id FOR UPDATE"
        ), {"id": user_id}).all()


def test_real_capability(native):
    response = native["client"].get("/v3/OS-AFTERGLOW/initial-password/capabilities", headers={"X-Auth-Token": native["token"]})
    assert response.status_code == 200
    assert response.json == {"revision": "first-password-galera-v2", "supported": True}


def test_existing_empty_local_is_eligible_and_preserves_extras(native, subject, post):
    with sql.session_for_write() as session:
        assert session.execute(text("SELECT id FROM local_user WHERE user_id=:id"), {"id": subject["id"]}).one()
    assert password_rows(subject["id"]) == []
    assert post(subject).status_code == 204
    rows = password_rows(subject["id"])
    assert len(rows) == 1
    assert password_hashing.check_password("Synthetic-first-password-482!", rows[0].password_hash)
    fresh = native["providers"].identity_api.get_user(subject["id"])
    assert fresh["afterglow_local_password"] is True
    assert fresh["nested_metadata"] == {"preserve": [1, 2]}
    assert fresh["email"] == "synthetic@example.invalid"
    assert post(subject, "Different-password-519!").status_code == 409
    assert password_rows(subject["id"]) == rows


@pytest.mark.parametrize("kind", ["native", "expired", "null", "old_hash_behind_null"])
def test_any_history_is_never_overwritten(native, subject, post, kind):
    native["providers"].identity_api.update_user(subject["id"], {"password": "Existing-password-681!"})
    if kind in ("expired", "null", "old_hash_behind_null"):
        with sql.session_for_write() as session:
            if kind == "expired":
                session.execute(text("UPDATE password p JOIN local_user l ON l.id=p.local_user_id SET p.expires_at_int=1 WHERE l.user_id=:id"), {"id": subject["id"]})
            elif kind == "null":
                session.execute(text("UPDATE password p JOIN local_user l ON l.id=p.local_user_id SET p.password_hash=NULL WHERE l.user_id=:id"), {"id": subject["id"]})
            else:
                session.execute(text("INSERT INTO password(local_user_id,password_hash,created_at,created_at_int,self_service) SELECT id,NULL,NOW(),1,0 FROM local_user WHERE user_id=:id"), {"id": subject["id"]})
    before = password_rows(subject["id"])
    # A malformed history now also refuses the state snapshot. Supply the
    # actual current SQL revision to exercise creation's own ANY-history guard.
    with sql.session_for_write() as session:
        revision = session.execute(text("SELECT revision FROM afterglow_password_guard WHERE user_id=:id"), {"id": subject["id"]}).scalar_one()
    binding = {"email": subject["email"], "identity_revision": str(revision)}
    assert post(subject, proof=binding).status_code == 409
    assert password_rows(subject["id"]) == before


@pytest.mark.parametrize("disabled,wrong_home", [(True, False), (False, True)])
def test_exact_enabled_subject_home(native, subject, post, disabled, wrong_home):
    if disabled:
        native["providers"].identity_api.update_user(subject["id"], {"enabled": False})
    response = post(subject, domain=uuid.uuid4().hex if wrong_home else None)
    assert response.status_code == 403
    assert password_rows(subject["id"]) == []


def test_no_user_token_self_service_or_other_subject(native, subject, post):
    user = native["providers"].identity_api.create_user({"name": "ordinary-" + uuid.uuid4().hex, "domain_id": native["domain"], "enabled": True, "email": "ordinary@example.invalid", "password": "Ordinary-password-471!"})
    response = native["client"].post("/v3/auth/tokens", json={"auth": {"identity": {"methods": ["password"], "password": {"user": {"id": user["id"], "password": "Ordinary-password-471!"}}}}})
    assert response.status_code == 201
    token = response.headers["X-Subject-Token"]
    assert post(subject, token=token).status_code == 403
    assert post(user, token=token).status_code == 403
    assert post(subject, token="invalid-native-token").status_code == 401
    assert password_rows(subject["id"]) == []


def test_uses_native_password_validation(subject, post):
    assert post(subject, password=None).status_code == 422
    assert post(subject, password="").status_code == 422
    assert password_rows(subject["id"]) == []


def test_federation_rows_preserved(native, subject, post):
    # Use real native shadow/federation managers, not invented extras.
    providers = native["providers"]
    idp = "idp-" + uuid.uuid4().hex
    providers.federation_api.create_idp(idp, {"id": idp, "enabled": True, "remote_ids": []})
    mapping = "map-" + uuid.uuid4().hex
    providers.federation_api.create_mapping(mapping, {"rules": []})
    providers.federation_api.create_protocol(idp, "openid", {"mapping_id": mapping})
    providers.shadow_users_api.create_federated_object({"user_id": subject["id"], "idp_id": idp, "protocol_id": "openid", "unique_id": uuid.uuid4().hex, "display_name": subject["name"]})
    before = providers.shadow_users_api.get_federated_objects(subject["id"])
    assert post(subject).status_code == 204
    assert providers.shadow_users_api.get_federated_objects(subject["id"]) == before
