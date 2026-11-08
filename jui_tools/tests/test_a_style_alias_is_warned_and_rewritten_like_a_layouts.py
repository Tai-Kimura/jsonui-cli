"""A Style's aliases are warned and rewritten in its distributed copy, as a
Layout's are.

Until 2.5.13 `_distribute_styles` copied each Style as written: an alias in a
Layout was rewritten with a warning, the same alias in a Style reached the
converters silently (and, before they resolved aliases themselves, drew as
the default). A Style carries no `type` as a rule, so:

- with a `type`, it takes the Layout canonicalizer (attribute, value and
  component aliases);
- without one, only value aliases are rewritten. An attribute alias depends
  on the component: `contentDescription` is `alt` on an Image and
  `accessibilityLabel` elsewhere, and `value` is a real attribute on a Slider.

The source Styles are never rewritten, a Style with nothing to rewrite is
copied byte for byte, and `normalizeLayouts: false` leaves them all as written.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from jui_cli.commands.build_cmd import _distribute_styles
from jui_cli.core.normalizer.alias_table import AliasTable

from test_build_sync_e2e import _build_fixture_project, _load_config, _make_args, _set_normalize

STYLES = {
    # no type: the value alias is rewritten, the attribute alias is not
    "phone_field.json": {"contentType": "phone", "value": "x", "fontSize": 14},
    # typed: as a Layout node
    "email_field.json": {"type": "TextField", "contentType": "emailAddress", "value": "x"},
    # nothing to rewrite: copied as written, formatting and all
    "plain.json": {"fontSize": 12},
}


def _distribute(root: Path) -> str:
    config_mgr, config = _load_config(root)
    out = io.StringIO()
    with redirect_stdout(out):
        _distribute_styles(config_mgr, config["platforms"], _make_args())
    return out.getvalue()


def _project(d: str) -> Path:
    root = Path(d)
    _build_fixture_project(root)
    styles = root / "docs/screens/styles"
    styles.mkdir(parents=True)
    for name, body in STYLES.items():
        # Compact, so a rewritten copy (indent=2) is told from a byte copy.
        (styles / name).write_text(json.dumps(body))
    return root


def _copy(root: Path, name: str) -> str:
    return (root / "ios/Styles" / name).read_text()


class AStyleAliasIsWarnedAndRewritten(unittest.TestCase):
    def test_a_typeless_style_has_its_value_alias_rewritten_and_warned(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(d)
            said = _distribute(root)
            copy = json.loads(_copy(root, "phone_field.json"))
            self.assertEqual(copy["contentType"], "telephoneNumber")
            self.assertIn("Styles/phone_field.json: [style] 'contentType: phone' is an alias spelling of "
                          "'telephoneNumber' — rewrote the value", said)
            # The attribute alias is left: `value` is real on other components.
            self.assertEqual(copy["value"], "x")
            self.assertNotIn("text", copy)
            self.assertNotIn("$jui", copy)

    def test_a_typed_style_takes_the_layout_canonicalizer(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(d)
            said = _distribute(root)
            copy = json.loads(_copy(root, "email_field.json"))
            self.assertEqual(copy["contentType"], "email")
            self.assertEqual(copy["text"], "x")
            self.assertNotIn("value", copy)
            self.assertNotIn("$jui", copy)
            self.assertIn("email_field.json", said)

    def test_every_face_gets_the_rewritten_copy_and_the_source_is_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(d)
            _distribute(root)
            for face in ("ios/Styles", "android/app/src/main/assets/Styles", "web/src/Styles"):
                self.assertEqual(json.loads((root / face / "phone_field.json").read_text())["contentType"],
                                 "telephoneNumber", face)
            self.assertEqual((root / "docs/screens/styles/phone_field.json").read_text(),
                             json.dumps(STYLES["phone_field.json"]))

    def test_a_style_with_nothing_to_rewrite_is_copied_as_written(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(d)
            _distribute(root)
            self.assertEqual(_copy(root, "plain.json"), json.dumps(STYLES["plain.json"]))

    def test_normalize_layouts_false_copies_every_style_as_written(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(d)
            _set_normalize(root, False)
            said = _distribute(root)
            for name, body in STYLES.items():
                self.assertEqual(_copy(root, name), json.dumps(body), name)
            self.assertNotIn("[normalize]", said)


class TheTypelessTableIsTheWholeSsot(unittest.TestCase):
    def test_every_declared_value_alias_is_in_it(self):
        definitions = json.loads((Path(__file__).resolve().parents[2]
                                  / "shared/core/attribute_definitions.json").read_text())
        table = AliasTable(definitions).value_aliases_any_section()
        declared = {(attr, alias) for section in definitions.values() if isinstance(section, dict)
                    for attr, spec in section.items() if isinstance(spec, dict)
                    for alias in (spec.get("valueAliases") or {})}
        self.assertTrue(declared)
        self.assertEqual({(a, k) for a, m in table.items() for k in m}, declared)

    def test_a_pair_two_sections_disagree_on_is_left_out(self):
        table = AliasTable({
            "common": {},
            "A": {"mode": {"enum": ["x", "y"], "valueAliases": {"z": "x"}}},
            "B": {"mode": {"enum": ["x", "y"], "valueAliases": {"z": "y", "w": "y"}}},
        }, type_synonyms={}).value_aliases_any_section()
        self.assertEqual(table, {"mode": {"w": "y"}})


if __name__ == "__main__":
    unittest.main()
