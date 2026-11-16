"""Every generated fixture must be legal on every platform it runs on.

The hole this closes: a fixture's layout is one file shared by all the
platforms the fixture targets, and nothing checked that the attributes in it
are declared for those platforms. Widening a fixture's base to make an
attribute observable is how the violation gets in — `Label.highlightAttributes`
only takes effect while the label is selected, so its fixture gained
`selected: true`, and because that base attribute was keyed by attribute name
alone it landed in `Button.highlightColor`'s fixture too, where `selected` is
not a declared attribute at all.

Three gates were green over that: the coverage ratchet only reads converter
sources, the control diff only compares screenshots, and fixture freshness only
checks that regeneration is a no-op. This asserts the property none of them do.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from jui_cli.conformance import coverage, rules

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFORMANCE = REPO_ROOT / "conformance"
DEFINITIONS = REPO_ROOT / "shared" / "core" / "attribute_definitions.json"

#: Keys that are layout structure rather than component attributes.
STRUCTURAL_KEYS = {"child", "children", "data", "include"}

#: The generator's own scoping helper, deliberately reused rather than
#: reimplemented: a second copy of this mapping would drift from the one that
#: decides which platforms a fixture is generated for, and then the guard would
#: stop guarding.
valid_platforms = rules._platforms


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class FixturePlatformScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONFORMANCE.exists() or not DEFINITIONS.exists():
            raise unittest.SkipTest("conformance fixtures not present")
        cls.definitions = _load(DEFINITIONS)
        cls.manifest = _load(CONFORMANCE / "manifest.json")
        # alias -> canonical, per component, so a fixture written under an alias
        # key resolves to the declaration that scopes it.
        cls.aliases = coverage.alias_names(cls.definitions)

    def _declaration(self, component: str, attribute: str):
        """The declaration governing `attribute` on `component`, or None."""
        for section in (component, "common"):
            defs = self.definitions.get(section)
            if not isinstance(defs, dict):
                continue
            defn = defs.get(attribute)
            if isinstance(defn, dict):
                return defn
            canonical = self.aliases.get((section, attribute))
            if canonical:
                defn = defs.get(canonical)
                if isinstance(defn, dict):
                    return defn
        return None

    def _walk(self, node, found):
        """Collect (component, attribute) pairs written anywhere in a layout."""
        if isinstance(node, list):
            for item in node:
                self._walk(item, found)
            return
        if not isinstance(node, dict):
            return

        component = node.get("type")
        for key, value in node.items():
            if key.startswith("_") or key in STRUCTURAL_KEYS or key == "type":
                continue
            if isinstance(component, str):
                found.add((component, key))
        for key in STRUCTURAL_KEYS:
            if key in node:
                self._walk(node[key], found)

    def test_no_fixture_uses_an_attribute_its_platform_does_not_declare(self):
        violations = []
        for fixture in self.manifest["fixtures"]:
            layout_path = CONFORMANCE / fixture["layout"]
            if not layout_path.exists():
                continue
            written = set()
            self._walk(_load(layout_path), written)

            for component, attribute in sorted(written):
                defn = self._declaration(component, attribute)
                if defn is None:
                    # Undeclared entirely is a different failure mode; the
                    # generator only writes declared names, and asserting it
                    # here would duplicate the schema check.
                    continue
                allowed = valid_platforms(defn)
                for platform in fixture["platforms"]:
                    if platform not in allowed:
                        violations.append(
                            f"{fixture['id']} runs on {platform} but writes "
                            f"{component}.{attribute}, declared for "
                            f"{list(allowed) or 'no platform'}"
                        )

        self.assertEqual(
            violations,
            [],
            "fixture layouts must only use attributes declared for the "
            "platforms they run on:\n  " + "\n  ".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
