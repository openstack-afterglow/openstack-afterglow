"""Toolbox clouds.yaml authentication combines Kolla's cloud profile and password override."""

import importlib.util
import io
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

_HELPER_PATH = (
    Path(__file__).resolve().parents[2] / "deploy/kolla/ansible/roles/afterglow/files/merge_toolbox_clouds.py"
)
_SOURCE = {
    "auth": {
        "auth_url": "https://keystone.test/v3",
        "username": "admin",
        "project_name": "admin",
        "user_domain_name": "Default",
        "project_domain_name": "Default",
    },
    "region_name": "R1",
    "interface": "internal",
}
_AUTH_OVERRIDES = {"password": "test-password"}


@pytest.fixture
def merge_helper():
    spec = importlib.util.spec_from_file_location("merge_toolbox_clouds", _HELPER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _merge(merge_helper, existing_text):
    return merge_helper.merge_clouds(
        existing_text,
        "kolla",
        "kolla-admin-internal",
        _AUTH_OVERRIDES,
        "R1",
        "internal",
    )


def test_kolla_cli_cloud_uses_kolla_profile_and_password_override(merge_helper):
    existing = yaml.safe_dump(
        {
            "clouds": {
                "kolla-admin-internal": _SOURCE,
                "kolla": {"auth": {"password": "old"}, "region_name": "old"},
            }
        }
    )
    document, changed = _merge(merge_helper, existing)

    assert changed is True
    assert document["clouds"]["kolla-admin-internal"] == _SOURCE
    assert document["clouds"]["kolla"] == {
        "auth": {**_SOURCE["auth"], **_AUTH_OVERRIDES},
        "auth_type": "password",
        "region_name": "R1",
        "interface": "internal",
    }


def test_identical_merged_content_is_reported_unchanged(merge_helper):
    entry = {
        **_SOURCE,
        "auth": {**_SOURCE["auth"], **_AUTH_OVERRIDES},
        "auth_type": "password",
        "region_name": "R1",
        "interface": "internal",
    }
    existing = yaml.safe_dump({"clouds": {"kolla-admin-internal": _SOURCE, "kolla": entry}})

    _, changed = _merge(merge_helper, existing)

    assert changed is False


@pytest.mark.parametrize(
    "existing",
    ["clouds: [unterminated", "- just-a-list", "clouds: [1, 2]"],
    ids=["malformed-yaml", "non-mapping-root", "non-mapping-clouds"],
)
def test_malformed_existing_file_fails_closed(merge_helper, existing):
    with pytest.raises((ValueError, yaml.YAMLError)):
        _merge(merge_helper, existing)


def test_missing_source_cloud_fails_closed(merge_helper):
    with pytest.raises(ValueError, match="source cloud entry"):
        _merge(merge_helper, "")


@pytest.mark.parametrize(
    ("source", "auth_overrides", "message"),
    [
        ({"auth": []}, _AUTH_OVERRIDES, "source cloud auth"),
        ({}, _AUTH_OVERRIDES, "source cloud auth"),
        (_SOURCE, {}, "authentication overrides"),
        (_SOURCE, {"password": ""}, "require password"),
    ],
    ids=["invalid-auth", "missing-auth", "empty-overrides", "empty-password"],
)
def test_invalid_auth_input_fails_closed(merge_helper, source, auth_overrides, message):
    existing = yaml.safe_dump({"clouds": {"kolla-admin-internal": source}})
    with pytest.raises(ValueError, match=message):
        merge_helper.merge_clouds(
            existing,
            "kolla",
            "kolla-admin-internal",
            auth_overrides,
            "R1",
            "internal",
        )


def test_source_cloud_without_auth_url_fails_closed(merge_helper):
    existing = yaml.safe_dump({"clouds": {"kolla-admin-internal": {"auth": {"username": "admin"}}}})
    with pytest.raises(ValueError, match="auth_url"):
        _merge(merge_helper, existing)


def test_main_writes_secure_cloud_file_and_is_idempotent(merge_helper, tmp_path, monkeypatch, capsys):
    path = tmp_path / "clouds.yaml"
    path.write_text(yaml.safe_dump({"clouds": {"kolla-admin-internal": _SOURCE}}), encoding="utf-8")
    monkeypatch.setattr(merge_helper, "CLOUDS_PATH", str(path))
    monkeypatch.setattr(
        merge_helper.pwd,
        "getpwnam",
        lambda _name: SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()),
    )
    request = json.dumps(
        {
            "name": "kolla",
            "source_cloud": "kolla-admin-internal",
            "auth_overrides": _AUTH_OVERRIDES,
            "region_name": "R1",
            "interface": "internal",
        }
    )
    monkeypatch.setattr(merge_helper.sys, "stdin", io.StringIO(request))

    merge_helper.main()

    first_output = capsys.readouterr().out
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert first_output.strip() == "changed"
    assert content["clouds"]["kolla"]["auth"]["auth_url"] == _SOURCE["auth"]["auth_url"]
    assert content["clouds"]["kolla"]["auth"]["password"] == _AUTH_OVERRIDES["password"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    monkeypatch.setattr(merge_helper.sys, "stdin", io.StringIO(request))
    merge_helper.main()
    second_output = capsys.readouterr().out
    assert second_output.strip() == "unchanged"
    assert _AUTH_OVERRIDES["password"] not in first_output + second_output
