"""The profile change contract uses stock Keystone self-service, not admin PATCH."""
import uuid


def test_ordinary_user_can_change_only_with_existing_password(native):
    client = native["client"]
    user = native["providers"].identity_api.create_user({
        "name": "profile-self-" + uuid.uuid4().hex,
        "domain_id": native["domain"],
        "enabled": True,
        "password": "Synthetic-original-437!",
    })
    user_id = user["id"]

    def authenticate(password):
        return client.post("/v3/auth/tokens", json={
            "auth": {"identity": {"methods": ["password"], "password": {
                "user": {"id": user_id, "password": password},
            }}}
        })

    original = authenticate("Synthetic-original-437!")
    assert original.status_code == 201
    headers = {"X-Auth-Token": original.headers["X-Subject-Token"]}
    assert client.patch("/v3/users/" + user_id, headers=headers, json={
        "user": {"password": "Synthetic-replacement-592!"},
    }).status_code == 403
    wrong = client.post("/v3/users/" + user_id + "/password", headers=headers, json={
        "user": {"original_password": "incorrect", "password": "Synthetic-replacement-592!"},
    })
    assert wrong.status_code in (401, 403)
    changed = client.post("/v3/users/" + user_id + "/password", headers=headers, json={
        "user": {"original_password": "Synthetic-original-437!", "password": "Synthetic-replacement-592!"},
    })
    assert changed.status_code == 204
    assert authenticate("Synthetic-original-437!").status_code == 401
    assert authenticate("Synthetic-replacement-592!").status_code == 201
