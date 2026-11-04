"""Static source templates are restored only with the exact recorded catalog identity."""

import json
from pathlib import Path

from app.services.experience_catalog import catalog_entry, is_known_message_key


def test_exact_revision_key_and_actual_locale_only():
    path = Path(__file__).resolve().parents[1] / "app" / "data" / "experience_catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    revision = catalog["revision"]
    entry = catalog_entry(revision, "common:actions.confirm", "en")
    assert entry == {
        "revision": revision,
        "key": "common:actions.confirm",
        "locale": "en",
        "template": "Confirm",
    }
    assert catalog_entry("0" * 64, "common:actions.confirm", "en") is None
    assert catalog_entry(revision, "common:actions.confirm", "unknown") is None
    assert catalog_entry(revision, "user supplied error or resource name", "en") is None
    assert catalog_entry(revision, "common:actions.confirm", "en-US") is None


def test_static_parameter_template_never_interpolates_event_values():
    path = Path(__file__).resolve().parents[1] / "app" / "data" / "experience_catalog.json"
    revision = json.loads(path.read_text(encoding="utf-8"))["revision"]
    entry = catalog_entry(revision, "common:state.loadingNamed", "en")
    assert entry["template"] == "Loading {name}…"
    entry["template"] = "arbitrary runtime value"
    assert catalog_entry(revision, "common:state.loadingNamed", "en")["template"] == "Loading {name}…"
    assert is_known_message_key("common:state.loadingNamed")
    assert not is_known_message_key("common:unregistered")
    assert not is_known_message_key("arbitrary runtime value")
