#!/usr/bin/env python3
"""Regression tests for immutable Kolla role tag selection."""

from __future__ import annotations
import sys
import importlib.util
import unittest
from pathlib import Path


_SCRIPT = Path(__file__).with_name("promote_kolla_role_tags.py")
_SPEC = importlib.util.spec_from_file_location("promote_kolla_role_tags", _SCRIPT)
assert _SPEC and _SPEC.loader
_PROMOTER = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _PROMOTER
_SPEC.loader.exec_module(_PROMOTER)


class SelectTagTests(unittest.TestCase):
    def test_adopts_matching_release_tag_over_commit_pin(self) -> None:
        self.assertEqual(_PROMOTER.select_tag("0.2.22", None, ["v0.2.21", "v0.2.22"]), "v0.2.22")

    def test_selects_newest_non_downgrade_tag(self) -> None:
        self.assertEqual(_PROMOTER.select_tag("0.2.22", "v0.2.22", ["v0.2.22", "v0.2.23"]), "v0.2.23")

    def test_never_downgrades_to_an_older_tag(self) -> None:
        self.assertIsNone(_PROMOTER.select_tag("0.2.22", None, ["v0.2.20", "v0.2.21"]))

    def test_rejects_non_stable_release_tags(self) -> None:
        with self.assertRaises(_PROMOTER.PromotionError):
            _PROMOTER.tag_version("v0.2.22-rc1")


if __name__ == "__main__":
    unittest.main()
