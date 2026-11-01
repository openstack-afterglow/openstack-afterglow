"""Use the actual pinned upstream wheel, not a fabricated source fixture.

AFTERGLOW_KEYSTONE_TEST_WHEEL names keystone-28.1.0-py3-none-any.whl.
"""
import hashlib
import importlib.util
import os
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def installer():
    spec = importlib.util.spec_from_file_location("first_password_installer", Path(__file__).parents[1] / "install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wheel_root(tmp_path, installer):
    wheel = Path(os.environ["AFTERGLOW_KEYSTONE_TEST_WHEEL"])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == installer.WHEEL_SHA256
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(tmp_path)
    return wheel, tmp_path



@pytest.mark.parametrize("relative", ["keystone/identity/backends/sql_model.py", "keystone/common/password_hashers/bcrypt.py"])
def test_tamper_rejects_before_any_hook_write(installer, wheel_root, relative):
    wheel, root = wheel_root
    target = root / relative
    target.write_bytes(target.read_bytes() + b"\n# changed native input\n")
    before = {name: (root / name).read_bytes() for name in installer.INPUTS}
    with pytest.raises(SystemExit):
        installer.install(root, wheel)
    assert {name: (root / name).read_bytes() for name in installer.INPUTS} == before
    assert not (root / "keystone/afterglow_initial_password_build.json").exists()


def test_api_revision_does_not_require_schema_migration(installer, wheel_root):
    wheel, root = wheel_root
    manifest = installer.install(root, wheel)
    assert manifest["revision"] == "first-password-galera-v1"
    assert manifest["api_revision"] == "first-password-galera-v2"
    assert set(manifest["files"]) == set(installer.INPUTS)
    assert set(manifest["extension_files"]) == {"__init__.py", "api.py", "schema.py", "migrate.py", "schema.sql"}
    for relative, digest in manifest["files"].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
