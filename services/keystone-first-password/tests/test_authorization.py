import uuid

import afterglow_keystone_first_password as extension
from test_identity_revision import proof
from test_native import password_rows


def test_configured_service_identity_still_requires_native_policy(native, subject, post):
    providers = native["providers"]
    user = providers.identity_api.create_user({"name": "unprivileged-service-" + uuid.uuid4().hex, "domain_id": native["domain"], "enabled": True, "password": "Synthetic-no-admin-password-975!"})
    response = native["client"].post("/v3/auth/tokens", json={"auth": {"identity": {"methods": ["password"], "password": {"user": {"id": user["id"], "password": "Synthetic-no-admin-password-975!"}}}}})
    assert response.status_code == 201
    previous = extension.CONF[extension.GROUP].service_user_id
    binding = proof(native, subject)
    extension.CONF.set_override("service_user_id", user["id"], group=extension.GROUP)
    try:
        assert post(subject, token=response.headers["X-Subject-Token"], proof=binding).status_code == 403
        assert password_rows(subject["id"]) == []
    finally:
        extension.CONF.set_override("service_user_id", previous, group=extension.GROUP)


def test_real_federated_only_subject_creates_local_user_atomically(native, post):
    providers = native["providers"]
    idp = "shadow-idp-" + uuid.uuid4().hex
    providers.federation_api.create_idp(idp, {"id": idp, "domain_id": native["domain"], "enabled": True, "remote_ids": []})
    mapping = "map-" + uuid.uuid4().hex
    providers.federation_api.create_mapping(mapping, {"rules": []})
    providers.federation_api.create_protocol(idp, "openid", {"mapping_id": mapping})
    subject = providers.shadow_users_api.create_federated_user(native["domain"], {"idp_id": idp, "protocol_id": "openid", "unique_id": uuid.uuid4().hex, "display_name": "shadow-name-" + uuid.uuid4().hex}, email="synthetic@example.invalid")
    before = providers.shadow_users_api.get_federated_objects(subject["id"])
    assert password_rows(subject["id"]) == []
    assert post(subject).status_code == 204
    assert len(password_rows(subject["id"])) == 1
    assert providers.shadow_users_api.get_federated_objects(subject["id"]) == before


def test_valid_service_admin_cannot_bypass_native_update_user_policy(native, subject, post):
    from keystone.common import rbac_enforcer
    from oslo_policy import policy
    binding = proof(native, subject)
    enforcer = rbac_enforcer.RBACEnforcer()._enforcer
    original = policy.Rules(dict(enforcer.rules))
    enforcer.set_rules(policy.Rules.from_dict({"identity:update_user": "!"}), overwrite=False)
    try:
        assert post(subject, proof=binding).status_code == 403
        assert password_rows(subject["id"]) == []
    finally:
        enforcer.set_rules(original, overwrite=True)
