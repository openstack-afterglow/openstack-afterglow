"""Native mapping pin derived from the Kolla mapping source must equal the backend guard's digest."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import native_oidc

_HELPER = Path(__file__).resolve().parents[2] / "deploy/kolla/ansible/roles/afterglow/files/render_effective_config.py"

RULES = [
    {
        "local": [{"user": {"name": "alice", "domain": {"id": "acct"}, "type": "local"}}],
        "remote": [
            {"type": "OIDC-email", "any_one_of": ["alice@example.test"]},
            {"type": "OIDC-email_verified", "any_one_of": ["1", "true"]},
        ],
    },
    {
        "local": [{"groups": "{0}", "domain": {"id": "dmslab"}}],
        "remote": [{"type": "OIDC-groups_direct"}, {"type": "OIDC-email_verified", "any_one_of": ["true"]}],
    },
]


@pytest.fixture
def renderer():
    spec = importlib.util.spec_from_file_location("kolla_native_pin_renderer", _HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source(tmp_path: Path, rules) -> Path:
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    return path


def _config(pin: str | None = None) -> dict:
    native = {
        "mode": "ephemeral",
        "mapping_id": "sso_oidc_mapping",
        "account_domain_id": "acct",
        "personal_domain_id": "personal",
    }
    if pin is not None:
        native["sha256"] = pin
    return {"auth": {"providers": {"dmslab_gitlab_domain": {"native_mapping": native}}}}


def _mappings(path: Path) -> list[dict]:
    return [{"name": "sso_oidc_mapping", "file": str(path)}]


def _pin(config: dict) -> str:
    return config["auth"]["providers"]["dmslab_gitlab_domain"]["native_mapping"]["sha256"]


def test_derived_pin_is_accepted_by_backend_guard(renderer, tmp_path: Path) -> None:
    pin = _pin(renderer.pin_native_mappings(_config(), _mappings(_source(tmp_path, RULES))))
    live = {"id": "sso_oidc_mapping", "schema_version": "2.0", "rules": RULES}
    assert native_oidc.mapping_matches(live, SimpleNamespace(mapping_id="sso_oidc_mapping", sha256=pin))


def test_changed_source_rules_move_the_derived_pin_and_reject_the_old_one(renderer, tmp_path: Path) -> None:
    old = _pin(renderer.pin_native_mappings(_config(), _mappings(_source(tmp_path, RULES))))
    changed = RULES + [{"local": [], "remote": []}]
    new = _pin(renderer.pin_native_mappings(_config(), _mappings(_source(tmp_path, changed))))
    assert new != old
    live = {"id": "sso_oidc_mapping", "schema_version": "2.0", "rules": changed}
    assert not native_oidc.mapping_matches(live, SimpleNamespace(mapping_id="sso_oidc_mapping", sha256=old))


def test_operator_declared_pin_must_equal_the_derived_value(renderer, tmp_path: Path) -> None:
    source = _source(tmp_path, RULES)
    derived = _pin(renderer.pin_native_mappings(_config(), _mappings(source)))
    assert _pin(renderer.pin_native_mappings(_config(derived), _mappings(source))) == derived
    with pytest.raises(ValueError, match="differs"):
        renderer.pin_native_mappings(_config("f" * 64), _mappings(source))


def test_missing_or_ambiguous_source_fails_closed(renderer, tmp_path: Path) -> None:
    source = _source(tmp_path, RULES)
    with pytest.raises(ValueError, match="missing or ambiguous"):
        renderer.pin_native_mappings(_config(), [])
    with pytest.raises(ValueError, match="missing or ambiguous"):
        renderer.pin_native_mappings(_config(), _mappings(source) + _mappings(source))


def test_non_native_config_needs_no_mapping_source(renderer) -> None:
    config = {"auth": {"providers": {"plain": {"kind": "oidc"}}}}
    assert renderer.pin_native_mappings(config, []) == config


def test_invalid_schema_or_empty_rules_are_rejected(renderer) -> None:
    with pytest.raises(ValueError):
        renderer.native_mapping_digest("1.0", RULES)
    with pytest.raises(ValueError):
        renderer.native_mapping_digest("2.0", [])


def test_live_digest_cli_matches_the_derived_pin(renderer, tmp_path: Path) -> None:
    derived = _pin(renderer.pin_native_mappings(_config(), _mappings(_source(tmp_path, RULES))))
    live = json.dumps({"id": "sso_oidc_mapping", "schema_version": "2.0", "rules": RULES})
    completed = subprocess.run(
        [sys.executable, str(_HELPER), "--mapping-digest"],
        input=live,
        text=True,
        capture_output=True,
        check=True,
    )
    assert completed.stdout.strip() == derived
