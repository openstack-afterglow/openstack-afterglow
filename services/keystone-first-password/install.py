#!/usr/bin/env python3
"""Offline, exact-input installer. Never modifies a running Keystone service."""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

SOURCE = "c0f8139167179f4ffe7749516105958a2ecdc2b0"
WHEEL_SHA256 = "4477a975a341faea86c7888a3f08c16f882af7fd3323444c42c3e89e16e5a1b0"
INPUTS = {
    "keystone/api/users.py": "fe8c44b9a425587341d659ad6f0db94698606b603076da5f2469934af422e011",
    "keystone/identity/backends/sql.py": "88392fe8ee7e81118e8512052ede0700947427d19ecb12902ddd33bee8252b81",
    "keystone/identity/core.py": "40396c6b2726d79b73e6375cc6069f8b824f9134f1d242b77d0a5fe29da29a2b",
    "keystone/identity/backends/sql_model.py": "ffc8aa3c0a4ae92d817de03d67005003f939b2137d76fbdd01eaead3335a91b5",
    "keystone/common/validation/validators.py": "ec4bede52360b55cdcb52d96cb0d307e0d30f636d08b64d559ac34e06169474b",
    "keystone/common/sql/core.py": "ca35324c6d657bb20a913a938e61ae1441a850bcba5f2dd4e481b90c1517b1ad",
    "keystone/common/password_hashing.py": "a305a8ae818bff7a48e9389603c9843ac9ca3d478ff9777f92d5e05bdd6e1c8b",
    "keystone/common/password_hashers/__init__.py": "bee087a86babd27325c4844fe195c5c2352f1572a71761b2d435db9d6dd91a66",
    "keystone/common/password_hashers/bcrypt.py": "5b353c60c44521fc549878c2f0d1267401f63ec9f872519a3b80e00b798fcf5c",
    "keystone/common/password_hashers/pbkdf2.py": "da8fb68c9d21fb46933c75a28d35c49ae423edefecfb2e65e2344ab035cb013e",
    "keystone/common/password_hashers/scrypt.py": "45dfa45c4b9da212af6b4953a08ac89814f714f76605411c3a382fe0172d2fa0",
    "keystone/federation/backends/sql.py": "522b8b46f021b6e85d40271d07ab99e3ba5e29eafb88a2dad393a498652e8ca4",
}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise SystemExit("Native source hook anchor mismatch")
    return text.replace(old, new, 1)


def install(root, wheel=None):
    if wheel is not None:
        raw = wheel.read_bytes()
        if hashlib.sha256(raw).hexdigest() != WHEEL_SHA256:
            raise SystemExit("Keystone wheel checksum mismatch")
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.startswith("keystone/") and not name.endswith("/") and (root / name).read_bytes() != archive.read(name):
                    raise SystemExit("Extracted native wheel differs: " + name)
    else:
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if actual != SOURCE:
            raise SystemExit("Keystone commitment mismatch")
        if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True).strip():
            raise SystemExit("Keystone source checkout must be clean")
    prepared = {}
    for path, digest in INPUTS.items():
        raw = (root / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise SystemExit("Keystone source differs from pinned input: " + path)
        prepared[path] = raw.decode()
    path = "keystone/identity/backends/sql.py"
    anchor = "    @sql.handle_conflicts(conflict_type='user')\n    # Explicitly retry on StaleDataErrors"
    prepared[path] = replace_once(prepared[path], anchor,
        "    def update_user(self, user_id, user):\n"
        "        from afterglow_keystone_first_password import pending, update_user\n"
        "        if pending():\n"
        "            return update_user(self, user_id, user)\n"
        "        return self._update_user_without_initial_password(user_id, user)\n\n" + anchor)
    # Rename ONLY the existing decorated implementation. Both conditional
    # operations dispatch outside the conflict wrapper and DB retry wrapper.
    prepared[path] = replace_once(prepared[path],
        "    @oslo_db_api.wrap_db_retry(exception_checker=_stale_data_exception_checker)\n    def update_user(self, user_id, user):\n",
        "    @oslo_db_api.wrap_db_retry(exception_checker=_stale_data_exception_checker)\n    def _update_user_without_initial_password(self, user_id, user):\n")
    path = "keystone/api/users.py"
    prepared[path] = replace_once(prepared[path], "class UserAPI(ks_flask.APIBase):\n",
        "from afterglow_keystone_first_password.api import InitialPassword, InitialPasswordCapability, InitialPasswordIdentity, PasswordReset\n\n\n"
        "class UserAPI(ks_flask.APIBase):\n")
    prepared[path] = replace_once(prepared[path], "    resource_mapping = [\n",
        "    resource_mapping = [\n"
        "        ks_flask.construct_resource_map(\n"
        "            resource=InitialPasswordCapability,\n"
        "            url='/OS-AFTERGLOW/initial-password/capabilities',\n"
        "            resource_kwargs={}, rel='afterglow_initial_password_capabilities', path_vars={},\n"
        "        ),\n"
        "        ks_flask.construct_resource_map(\n"
        "            resource=InitialPasswordIdentity,\n"
        "            url='/users/<string:user_id>/OS-AFTERGLOW/initial-password/identity',\n"
        "            resource_kwargs={}, rel='afterglow_initial_password_identity',\n"
        "            path_vars={'user_id': json_home.Parameters.USER_ID},\n"
        "        ),\n"
        "        ks_flask.construct_resource_map(\n"
        "            resource=InitialPassword,\n"
        "            url='/users/<string:user_id>/OS-AFTERGLOW/initial-password',\n"
        "            resource_kwargs={}, rel='afterglow_initial_password',\n"
        "            path_vars={'user_id': json_home.Parameters.USER_ID},\n"
        "        ),\n"
        "        ks_flask.construct_resource_map(\n"
        "            resource=PasswordReset,\n"
        "            url='/users/<string:user_id>/OS-AFTERGLOW/password-reset',\n"
        "            resource_kwargs={}, rel='afterglow_password_reset',\n"
        "            path_vars={'user_id': json_home.Parameters.USER_ID},\n"
        "        ),\n")
    package = Path(__file__).resolve().parent / "afterglow_keystone_first_password"
    extension_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(package.iterdir()) if p.suffix in (".py", ".sql")}
    manifest = {"revision": "first-password-galera-v1", "api_revision": "first-password-galera-v2", "keystone_version": "28.1.0",
                "source_commit": SOURCE, "upstream_wheel_sha256": WHEEL_SHA256,
                "files": {p: hashlib.sha256(s.encode()).hexdigest() for p, s in prepared.items()},
                "extension_files": extension_files}
    # Validate every input and anchor before writing any file. A failed output
    # write is an offline failed build, never permission to start native APIs.
    for path, source in prepared.items():
        (root / path).write_text(source)
    (root / "keystone/afterglow_initial_password_build.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    if wheel is None:
        with (root / "MANIFEST.in").open("a") as stream:
            stream.write("\ninclude keystone/afterglow_initial_password_build.json\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keystone_root", type=Path)
    parser.add_argument("--upstream-wheel", type=Path)
    args = parser.parse_args()
    print(json.dumps(install(args.keystone_root.resolve(), args.upstream_wheel), sort_keys=True))
