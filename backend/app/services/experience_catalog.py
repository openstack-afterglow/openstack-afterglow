"""Resolve only exact source-owned static templates, never user-formatted event strings.

Historical templates are retained by the experience store alongside their revision. This
module deliberately does not substitute the current catalog for an unknown old revision.
"""

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "experience_catalog.json"


@lru_cache(maxsize=1)
def _catalog() -> tuple[str, Mapping[str, Mapping[str, str]]]:
    document = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    messages = {key: MappingProxyType(dict(locales)) for key, locales in document["messages"].items()}
    return document["revision"], MappingProxyType(messages)


def catalog_entry(revision: str, key: str, locale: str) -> dict | None:
    """Return a fresh safe template receipt only for the exact registered revision/key/locale."""
    current_revision, messages = _catalog()
    if revision != current_revision:
        return None
    template = messages.get(key, {}).get(locale)
    if template is None:
        return None
    return {"revision": revision, "key": key, "locale": locale, "template": template}


def is_known_message_key(key: str) -> bool:
    """A key is source-registered, not arbitrary text or a caller-supplied namespace."""
    return key in _catalog()[1]
