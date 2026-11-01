"""Real Keystone SQL tests; no in-memory substitute is accepted.

Run only in the isolated Keystone 28.1.0 test container after db_sync, the
exact-source installer and offline guard migration. Set:
AFTERGLOW_KEYSTONE_TEST_CONFIG = absolute native keystone.conf path;
AFTERGLOW_KEYSTONE_TEST_AUDITS = JSON audit DSNs for both loopback Galera nodes;
AFTERGLOW_KEYSTONE_TEST_MEMBERS = JSON exact wsrep_node_name values;
AFTERGLOW_KEYSTONE_TEST_WRITER_B = restricted SQL writer DSN for node B.
The native config must have a real restricted writer URL, SQL identity,
fernet token keys, and no external cache/auth/provider network dependencies.
All test users/domains are unique disposable fixture records.
"""
import json
import os
import sys
import uuid
from pathlib import Path

import afterglow_keystone_first_password as extension
import pytest


@pytest.fixture(scope="session")
def native():
    from keystone import server
    from keystone.common import provider_api
    from keystone.server.flask.application import application_factory
    from keystone.server.flask.core import setup_app_middleware
    config = os.environ["AFTERGLOW_KEYSTONE_TEST_CONFIG"]
    if not Path(config).is_file():
        raise RuntimeError("A real isolated Keystone configuration is required")
    # oslo.config otherwise parses pytest's own command-line arguments.
    argv = sys.argv
    try:
        sys.argv = argv[:1]
        server.configure(config_files=[config])
    finally:
        sys.argv = argv
    server.setup_backends()
    conf = extension.CONF
    conf.set_override("enabled", True, group=extension.GROUP)
    conf.set_override("peer_connections", json.loads(os.environ["AFTERGLOW_KEYSTONE_TEST_AUDITS"]), group=extension.GROUP)
    conf.set_override("cluster_members", json.loads(os.environ["AFTERGLOW_KEYSTONE_TEST_MEMBERS"]), group=extension.GROUP)
    providers = provider_api.ProviderAPIs
    domain_id = uuid.uuid4().hex
    providers.resource_api.create_domain(domain_id, {"id": domain_id, "name": "initial-password-test-" + domain_id, "enabled": True})
    service = providers.identity_api.create_user({"name": "service-" + uuid.uuid4().hex, "domain_id": domain_id, "enabled": True, "password": "Synthetic-service-password-729!"})
    conf.set_override("service_user_id", service["id"], group=extension.GROUP)
    roles = [r for r in providers.role_api.list_roles() if r["name"] == "admin"]
    role = roles[0] if roles else providers.role_api.create_role(uuid.uuid4().hex, {"name": "admin"})
    providers.assignment_api.create_system_grant_for_user(service["id"], role["id"])
    client = setup_app_middleware(application_factory()).test_client()
    response = client.post("/v3/auth/tokens", json={"auth": {"identity": {"methods": ["password"], "password": {"user": {"id": service["id"], "password": "Synthetic-service-password-729!"}}}, "scope": {"system": {"all": True}}}})
    assert response.status_code == 201, response.status_code
    token = response.headers["X-Subject-Token"]
    yield {"providers": providers, "domain": domain_id, "service": service, "client": client, "token": token}
    # Fixture database is disposable; destructive global cleanup is deliberately
    # not performed against an externally supplied database.


@pytest.fixture
def subject(native):
    return native["providers"].identity_api.create_user({
        "name": "federated-enrollment-" + uuid.uuid4().hex,
        "domain_id": native["domain"], "enabled": True,
        "email": "synthetic@example.invalid",
        "nested_metadata": {"preserve": [1, 2]},
    })


@pytest.fixture
def post(native):
    def call(subject, password="Synthetic-first-password-482!", domain=None, token=None, proof=None):
        if proof is None:
            response = native["client"].get("/v3/users/" + subject["id"] + "/OS-AFTERGLOW/initial-password/identity", headers={"X-Auth-Token": native["token"]})
            if response.status_code != 200:
                return response
            proof = response.json["user"]
        return native["client"].post(
            "/v3/users/" + subject["id"] + "/OS-AFTERGLOW/initial-password",
            headers={"X-Auth-Token": native["token"] if token is None else token},
            json={"user": {"password": password, "domain_id": domain or subject["domain_id"], "email": proof["email"], "identity_revision": proof["identity_revision"]}},
        )
    return call
