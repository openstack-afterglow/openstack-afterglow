"""Creation password constraints and client-visible validation privacy."""

import json

import pytest
from pydantic import SecretStr, ValidationError

from app.api.identity.admin_instances import AdminCreateInstanceRequest
from app.models.compute import CreateInstanceRequest
from app.services.instance_password import PasswordProvisioning

_SECRET = "  Never-Echo-This-'秘密'  "
_CREATION_PATHS = (
    "/api/v1/instances",
    "/api/v1/instances/async",
    "/api/v1/admin/instances/async",
)
_MODELS = (CreateInstanceRequest, AdminCreateInstanceRequest)
_CONTROLS = tuple(range(32)) + tuple(range(127, 160))


def _payload(**changes):
    payload = {"image_id": "image-1", "flavor_id": "flavor-1", "project_id": "target-project", "admin_pass": _SECRET}
    payload.update(changes)
    return payload


def _assert_private_validation(response, secret):
    assert response.status_code == 422
    assert secret not in response.text
    assert json.dumps(secret, ensure_ascii=True)[1:-1] not in response.text
    assert json.dumps(secret, ensure_ascii=False)[1:-1] not in response.text
    errors = response.json()["detail"]
    assert errors
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)
    return errors


@pytest.mark.parametrize("model", _MODELS)
@pytest.mark.parametrize("password", [" " * 8, " " + "秘密é'" * 30 + " ", "x" * 128])
def test_creation_password_preserves_spaces_unicode_and_boundaries(model, password):
    request = model(**_payload(admin_pass=password))
    assert isinstance(request.admin_pass, SecretStr)
    assert request.admin_pass.get_secret_value() == password
    assert password not in repr(request)
    assert password not in str(request)
    assert password not in request.model_dump_json()


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("password", [" " * 8, _SECRET, "x" * 128])
def test_native_nova_boundary_preserves_password_exactly(windows, password):
    plan = PasswordProvisioning(windows=windows, config_drive=windows)
    assert plan.nova_admin_pass(SecretStr(password)) == password
    assert plan.nova_admin_pass(None) is None


@pytest.mark.parametrize("model", _MODELS)
@pytest.mark.parametrize(
    "password", ["short!", "x" * 129, 12345678, True, ["secret-value"], {"secret": "secret-value"}]
)
def test_creation_password_rejects_invalid_length_and_types_without_validation_string_leaks(model, password):
    with pytest.raises(ValidationError) as caught:
        model(**_payload(admin_pass=password))
    secret = password if isinstance(password, str) else "secret-value"
    assert secret not in str(caught.value)
    assert "input_value" not in str(caught.value)


@pytest.mark.parametrize("model", _MODELS)
@pytest.mark.parametrize("codepoint", _CONTROLS, ids=lambda codepoint: f"U+{codepoint:04X}")
def test_creation_password_rejects_all_c0_del_c1_controls(model, codepoint):
    password = "NeverEcho" + chr(codepoint) + "Password"
    with pytest.raises(ValidationError) as caught:
        model(**_payload(admin_pass=password))
    assert "NeverEcho" not in str(caught.value)


@pytest.mark.parametrize("model", _MODELS)
@pytest.mark.parametrize(
    "changes",
    [
        {"image_id": None},
        {"boot_volume_id": "volume-1"},
        {"github_username": "octocat", "key_name": "key-1"},
        {"flavor_id": {"echo": _SECRET}},
        {"project_id": None},
        {"new_volumes": [{"name": _SECRET, "size_gb": 0}]},
    ],
)
def test_creation_model_validation_string_hides_body_and_unrelated_inputs(model, changes):
    # project_id is an admin-only field; the base model ignores it.
    if model is CreateInstanceRequest and changes == {"project_id": None}:
        changes = {"flavor_id": None}
    with pytest.raises(ValidationError) as caught:
        model(**_payload(**changes))
    assert _SECRET not in str(caught.value)
    assert "input_value" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _CREATION_PATHS)
@pytest.mark.parametrize(
    "password", ["short!", "x" * 129, "NeverEcho\x00Password", "NeverEcho\x7fPassword", "NeverEcho\x85Password"]
)
async def test_creation_http_password_field_errors_never_echo_plaintext(admin_client, path, password):
    response = await admin_client.post(path, json=_payload(admin_pass=password))
    errors = _assert_private_validation(response, password)
    assert any(error["loc"] == ["body", "admin_pass"] for error in errors)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _CREATION_PATHS)
@pytest.mark.parametrize("password", [12345678, True, [_SECRET], {"echo": _SECRET}])
async def test_creation_http_non_string_password_errors_never_echo_input(admin_client, path, password):
    response = await admin_client.post(path, json=_payload(admin_pass=password))
    errors = _assert_private_validation(response, _SECRET)
    assert any(error["loc"] == ["body", "admin_pass"] for error in errors)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _CREATION_PATHS)
@pytest.mark.parametrize(
    "changes, expected_loc",
    [
        ({"image_id": None}, ["body"]),
        ({"boot_volume_id": "volume-1"}, ["body"]),
        ({"github_username": "octocat", "key_name": "key-1"}, ["body"]),
        ({"flavor_id": {"echo": _SECRET}}, ["body", "flavor_id"]),
        ({"boot_volume_size_gb": 0}, ["body", "boot_volume_size_gb"]),
        ({"new_volumes": [{"name": _SECRET, "size_gb": 0}]}, ["body", "new_volumes", 0, "name"]),
        (
            {"data_mounts": [{"file_storage_id": "share-1", "mount_point": _SECRET}]},
            ["body", "data_mounts", 0, "mount_point"],
        ),
    ],
)
async def test_creation_http_model_and_unrelated_field_errors_never_echo_password(
    admin_client, path, changes, expected_loc
):
    response = await admin_client.post(path, json=_payload(**changes))
    errors = _assert_private_validation(response, _SECRET)
    assert any(error["loc"] == expected_loc for error in errors)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _CREATION_PATHS)
async def test_creation_http_missing_flavor_never_echoes_password(admin_client, path):
    payload = _payload()
    del payload["flavor_id"]
    errors = _assert_private_validation(await admin_client.post(path, json=payload), _SECRET)
    assert any(error["loc"] == ["body", "flavor_id"] for error in errors)


@pytest.mark.asyncio
async def test_admin_creation_http_missing_project_never_echoes_password(admin_client):
    payload = _payload()
    del payload["project_id"]
    errors = _assert_private_validation(await admin_client.post("/api/v1/admin/instances/async", json=payload), _SECRET)
    assert any(error["loc"] == ["body", "project_id"] for error in errors)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _CREATION_PATHS)
async def test_creation_http_malformed_json_never_echoes_password(admin_client, path):
    body = json.dumps(_payload())[:-1] + ",}"
    response = await admin_client.post(path, content=body, headers={"Content-Type": "application/json"})
    errors = _assert_private_validation(response, _SECRET)
    assert errors[0]["type"] == "json_invalid"
