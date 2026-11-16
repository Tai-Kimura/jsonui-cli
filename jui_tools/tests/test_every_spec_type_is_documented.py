"""Every spec type this repo knows is reachable from the dev guide.

1.8.52 shipped a DETECTION — `unit-stubs --check` telling authors to move a
declaration "to the app contracts spec" — and shipped no rule to go with it.
The author it spoke to had nowhere to look up the correct fix, and because the
type name existed only in code they could not even guess the spelling: earlier
names for the same idea appear in the history.

So the pairing is a gate rather than a habit. A detection that names a word has
to leave that word somewhere a person can find it, and the only way that stays
true is if adding a type without documenting it fails.

⚠️ This checks reachability, not correctness. A line that merely contains the
type name passes. That is deliberate — the alternative is pinning prose, which
goes stale in the direction of being edited around. What it prevents is the
case that actually happened: the word existing nowhere but in a Python literal.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_GUIDE = REPO_ROOT / "dev-guide"


def _spec_types() -> set[str]:
    from jui_cli.core import shared_core
    core = shared_core.load("spec_types")
    if core is None:
        raise AssertionError(
            "shared/core/spec_types.py did not load. This test cannot say "
            "anything about documentation without it, and a silent skip here "
            "would look exactly like a pass."
        )
    return set(core.SCREEN_TYPES) | set(core.NON_SCREEN_TYPES)


class SpecTypeDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(DEV_GUIDE.is_dir(), f"no dev-guide at {DEV_GUIDE}")
        self.text = "\n".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(DEV_GUIDE.rglob("*.md"))
        )
        self.assertTrue(self.text, "dev-guide has no markdown to search")

    def test_the_search_finds_something_it_should(self):
        # Positive control. Without it, a broken path or an empty read makes
        # every type look undocumented — or, if the assertion were inverted,
        # makes every type look fine.
        self.assertIn("screen_spec", self.text)

    def test_every_spec_type_appears_in_the_dev_guide(self):
        missing = sorted(t for t in _spec_types() if t not in self.text)
        self.assertEqual(
            [], missing,
            f"spec type(s) known to shared/core/spec_types.py but absent from "
            f"dev-guide/: {missing}. A detection that names one of these sends "
            f"its reader somewhere that does not exist — which is what "
            f"happened with app_contracts_spec in 1.8.52. Document the type "
            f"(dev-guide/02-ssot-shared-core.md §6) in the same change that "
            f"adds it."
        )

    def test_app_contracts_spec_reaches_the_rule_not_just_the_name(self):
        # The specific failure that produced this file: the reader arrives from
        # a finding that says "move it to the app contracts spec" and needs to
        # learn where that file goes and what shape it has.
        self.assertIn("app_contracts_spec", self.text)
        self.assertIn("unitContracts", self.text)
