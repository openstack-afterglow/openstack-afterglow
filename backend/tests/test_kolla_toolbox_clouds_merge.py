"""Toolbox clouds.yaml merge: only the Afterglow cloud entry changes; siblings and failures are preserved."""

import importlib.util
from pathlib import Path

import pytest
import yaml

_HELPER_PATH = (
    Path(__file__).resolve().parents[2] / "deploy/kolla/ansible/roles/afterglow/files/merge_toolbox_clouds.py"
)
_ENTRY = {
    "auth": {"auth_url": "https://keystone.test/v3"},
    "auth_type": "password",
    "region_name": "R1",
    "interface": "internal",
}


@pytest.fixture
def merge_helper():
    spec = importlib.util.spec_from_file_location("merge_toolbox_clouds", _HELPER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_kolla_entry_is_replaced_and_kolla_admin_siblings_are_kept(merge_helper):
    existing = yaml.safe_dump(
        {"clouds": {"kolla-admin-internal": {"auth_type": "password"}, "kolla": {"auth_type": "old"}}}
    )
    document, changed = merge_helper.merge_clouds(existing, "kolla", _ENTRY)
    assert changed is True
    assert document["clouds"]["kolla-admin-internal"] == {"auth_type": "password"}
    assert document["clouds"]["kolla"] == _ENTRY


def test_missing_file_starts_with_only_the_kolla_cloud(merge_helper):
    document, changed = merge_helper.merge_clouds("", "kolla", _ENTRY)
    assert changed is True
    assert document == {"clouds": {"kolla": _ENTRY}}


def test_identical_content_is_reported_unchanged(merge_helper):
    existing = yaml.safe_dump({"clouds": {"kolla-admin": {"auth_type": "password"}, "kolla": _ENTRY}})
    _, changed = merge_helper.merge_clouds(existing, "kolla", _ENTRY)
    assert changed is False


@pytest.mark.parametrize(
    "existing",
    ["clouds: [unterminated", "- just-a-list", "clouds: [1, 2]"],
    ids=["malformed-yaml", "non-mapping-root", "non-mapping-clouds"],
)
def test_unreadable_or_malformed_existing_file_fails_closed(merge_helper, existing):
    with pytest.raises((ValueError, yaml.YAMLError)):
        merge_helper.merge_clouds(existing, "kolla", _ENTRY)


@pytest.mark.parametrize("name, entry", [("", _ENTRY), ("kolla", "not-a-mapping")], ids=["empty-name", "bad-entry"])
def test_invalid_request_is_rejected(merge_helper, name, entry):
    with pytest.raises(ValueError):
        merge_helper.merge_clouds("", name, entry)
