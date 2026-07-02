"""Tests for the L1 canonicalizer (alias rewrite, conflicts, deprecation,
``$jui`` marker, idempotency)."""
from __future__ import annotations

import unittest
from pathlib import Path

from jui_cli.core.normalizer import (
    MARKER_KEY,
    SCHEMA_VERSION,
    AliasTable,
    Canonicalizer,
    default_definitions_path,
    normalize,
)

# Synthetic definitions with the same structural features as the real
# shared/core/attribute_definitions.json (common + component overrides,
# aliases, scoped deprecation).
SYNTH_DEFS = {
    "common": {
        "opacity": {"type": "number", "aliases": ["alpha"]},
        "alpha": {"type": "number"},
        "width": {"type": ["string", "number"]},
    },
    "Slider": {
        "minimum": {"type": "number", "aliases": ["minimumValue", "minValue"]},
        "minValue": {"type": "number"},
    },
    "TextField": {
        "hintColor": {
            "type": "string",
            "deprecated": "swiftui",
            "deprecation_note": "use hintAttributes instead.",
        },
    },
}


def _table() -> AliasTable:
    return AliasTable(SYNTH_DEFS)


class AliasTableTest(unittest.TestCase):
    def test_common_aliases_apply_to_all_types(self):
        table = _table()
        self.assertEqual(table.aliases_for("View").get("alpha"), "opacity")
        self.assertEqual(table.aliases_for(None).get("alpha"), "opacity")

    def test_component_aliases_are_scoped(self):
        table = _table()
        self.assertEqual(table.aliases_for("Slider").get("minValue"), "minimum")
        self.assertNotIn("minValue", table.aliases_for("View"))

    def test_type_synonyms_resolve_to_definition_key(self):
        table = _table()
        # SeekBar is the Android spelling of Slider
        self.assertEqual(table.aliases_for("SeekBar").get("minValue"), "minimum")

    def test_deprecated_lookup(self):
        table = _table()
        dep = table.deprecated_for("TextField").get("hintColor")
        self.assertIsNotNone(dep)
        self.assertEqual(dep.scope, "swiftui")
        self.assertIn("hintAttributes", dep.note)

    def test_real_definitions_contain_known_aliases(self):
        path = default_definitions_path()
        self.assertIsNotNone(path, "shared/core/attribute_definitions.json not found")
        table = AliasTable.from_file(path)
        self.assertEqual(table.aliases_for("View").get("alpha"), "opacity")
        # alignTopView is NOT an alias of alignTopOfView: they are distinct
        # attributes (align top edges vs position relative to the target
        # view) on every platform renderer, so the definitions must not
        # alias them (rewriting would silently change layout semantics).
        self.assertNotIn("alignTopView", table.aliases_for("View"))
        self.assertEqual(table.aliases_for("Button").get("hilightColor"), "highlightColor")
        self.assertEqual(
            table.aliases_for("Button").get("highlightBackground"), "tapBackground"
        )
        self.assertEqual(table.aliases_for("Slider").get("maxValue"), "maximum")
        self.assertEqual(
            table.aliases_for("Collection").get("onPageChanged"), "onValueChange"
        )
        self.assertEqual(
            table.aliases_for("TabView").get("selectedTabIndex"), "selectedIndex"
        )

    def test_missing_file_degrades_to_empty_table(self):
        table = AliasTable.from_file("/nonexistent/attribute_definitions.json")
        self.assertEqual(table.aliases_for("View"), {})
        self.assertTrue(table.is_empty())

    def test_loaded_table_is_not_empty(self):
        self.assertFalse(AliasTable(SYNTH_DEFS).is_empty())

    def test_default_path_falls_back_to_tool_copies(self):
        # Simulate a project-local install: jui_tools synced next to
        # kjui_tools, no shared/ tree.
        import shutil
        import tempfile
        real = default_definitions_path()
        self.assertIsNotNone(real)
        with tempfile.TemporaryDirectory() as tmp:
            tool_copy = (
                Path(tmp) / "kjui_tools" / "lib" / "core" / "attribute_definitions.json"
            )
            tool_copy.parent.mkdir(parents=True)
            shutil.copy(real, tool_copy)
            # Resolution is anchored on jui_cli's __file__, so exercise the
            # relpath list directly against the simulated root.
            from jui_cli.core.normalizer.alias_table import _DEFINITIONS_RELPATHS

            found = None
            for rel in _DEFINITIONS_RELPATHS:
                candidate = Path(tmp) / rel
                if candidate.exists():
                    found = candidate
                    break
            self.assertEqual(found, tool_copy)


class CanonicalizerTest(unittest.TestCase):
    def setUp(self):
        self.canon = Canonicalizer(_table())

    def test_alias_rewritten_without_warning(self):
        tree, warnings = self.canon.canonicalize({"type": "View", "alpha": 0.5})
        self.assertEqual(tree["opacity"], 0.5)
        self.assertNotIn("alpha", tree)
        self.assertEqual(warnings, [])

    def test_key_order_preserved_on_rewrite(self):
        tree, _ = self.canon.canonicalize(
            {"type": "View", "width": 10, "alpha": 0.5, "id": "x"}
        )
        self.assertEqual(
            list(tree.keys()), [MARKER_KEY, "type", "width", "opacity", "id"]
        )

    def test_canonical_wins_over_alias_with_warning(self):
        tree, warnings = self.canon.canonicalize(
            {"type": "View", "alpha": 0.2, "opacity": 0.9}
        )
        self.assertEqual(tree["opacity"], 0.9)
        self.assertNotIn("alpha", tree)
        self.assertEqual(len(warnings), 1)
        self.assertIn("alias of 'opacity'", warnings[0])
        self.assertIn("keeping 'opacity'", warnings[0])

    def test_two_aliases_first_wins_with_warning(self):
        tree, warnings = self.canon.canonicalize(
            {"type": "Slider", "minimumValue": 1, "minValue": 2}
        )
        self.assertEqual(tree["minimum"], 1)
        self.assertEqual(len(warnings), 1)
        self.assertIn("minValue", warnings[0])

    def test_component_alias_not_applied_to_other_types(self):
        tree, _ = self.canon.canonicalize({"type": "View", "minValue": 3})
        self.assertEqual(tree["minValue"], 3)

    def test_deprecated_warns_without_rewrite(self):
        tree, warnings = self.canon.canonicalize(
            {"type": "TextField", "hintColor": "#888888"}
        )
        self.assertEqual(tree["hintColor"], "#888888")
        self.assertEqual(len(warnings), 1)
        self.assertIn("deprecated (swiftui)", warnings[0])
        self.assertIn("hintAttributes", warnings[0])

    def test_marker_added_first(self):
        tree, _ = self.canon.canonicalize({"type": "View"})
        self.assertEqual(next(iter(tree)), MARKER_KEY)
        self.assertEqual(
            tree[MARKER_KEY], {"normalized": "L1", "schemaVersion": SCHEMA_VERSION}
        )

    def test_children_recursed(self):
        tree, _ = self.canon.canonicalize(
            {
                "type": "View",
                "child": [
                    {"type": "Slider", "minValue": 1},
                    {"type": "View", "children": [{"type": "View", "alpha": 1}]},
                ],
            }
        )
        self.assertEqual(tree["child"][0]["minimum"], 1)
        self.assertEqual(tree["child"][1]["children"][0]["opacity"], 1)
        # Marker stays top-level only
        self.assertNotIn(MARKER_KEY, tree["child"][0])

    def test_sections_nodes_recursed(self):
        tree, _ = self.canon.canonicalize(
            {
                "type": "Collection",
                "sections": [
                    {
                        "header": {"type": "View", "alpha": 0.5},
                        "cell": {"type": "Slider", "minimumValue": 2},
                        "footer": {"type": "View"},
                    }
                ],
            }
        )
        self.assertEqual(tree["sections"][0]["header"]["opacity"], 0.5)
        self.assertEqual(tree["sections"][0]["cell"]["minimum"], 2)

    def test_style_include_platform_untouched(self):
        src = {
            "type": "View",
            "style": "card",
            "platform": {"ios": {"alpha": 1}},
            "child": [{"include": "shared_header", "id": "header"}],
        }
        tree, _ = self.canon.canonicalize(src)
        self.assertEqual(tree["style"], "card")
        self.assertEqual(tree["child"][0]["include"], "shared_header")
        # platform override blocks are attribute *values* — not rewritten at L1
        self.assertEqual(tree["platform"], {"ios": {"alpha": 1}})

    def test_unknown_attributes_pass_through(self):
        tree, warnings = self.canon.canonicalize(
            {"type": "View", "totallyCustomAttr": True}
        )
        self.assertTrue(tree["totallyCustomAttr"])
        self.assertEqual(warnings, [])

    def test_data_only_dicts_not_rewritten(self):
        src = {
            "type": "View",
            "data": [{"name": "alpha", "class": "Double", "defaultValue": 1}],
        }
        tree, _ = self.canon.canonicalize(src)
        self.assertEqual(tree["data"][0]["name"], "alpha")

    def test_input_not_mutated(self):
        src = {"type": "View", "alpha": 0.5}
        self.canon.canonicalize(src)
        self.assertEqual(src, {"type": "View", "alpha": 0.5})

    def test_idempotent(self):
        src = {
            "type": "View",
            "alpha": 0.5,
            "child": [{"type": "Slider", "minimumValue": 0, "maxValue": 10}],
        }
        once, w1 = self.canon.canonicalize(src)
        twice, w2 = self.canon.canonicalize(once)
        self.assertEqual(once, twice)
        self.assertEqual(w2, [])
        self.assertEqual(len(w1), 0)


class NormalizeApiTest(unittest.TestCase):
    def test_l1_via_public_api(self):
        result = normalize(
            {"type": "View", "alpha": 0.4}, "L1", alias_table=_table()
        )
        self.assertEqual(result.level, "L1")
        self.assertEqual(result.tree["opacity"], 0.4)
        self.assertEqual(result.tree[MARKER_KEY]["normalized"], "L1")

    def test_l1_idempotent_via_public_api(self):
        table = _table()
        first = normalize({"type": "View", "alpha": 0.4}, "L1", alias_table=table)
        second = normalize(first.tree, "L1", alias_table=table)
        self.assertEqual(first.tree, second.tree)

    def test_invalid_level_rejected(self):
        with self.assertRaises(ValueError):
            normalize({}, "L3")

    def test_l2_requires_dirs(self):
        with self.assertRaises(ValueError):
            normalize({"type": "View"}, "L2")

    def test_non_dict_passthrough(self):
        result = normalize([1, 2], "L1")
        self.assertEqual(result.tree, [1, 2])

    def test_source_prefix_in_warnings(self):
        result = normalize(
            {"type": "View", "alpha": 1, "opacity": 2},
            "L1",
            alias_table=_table(),
            source="home.json",
        )
        self.assertTrue(result.warnings[0].startswith("home.json: "))


class VerifyNormalizationTest(unittest.TestCase):
    """`jui verify` applies the same canonicalization to both sides —
    an L1-distributed layout must never register as drift against the
    L0 spec-generated tree."""

    def test_view_diff_checker_no_false_drift_between_l0_and_l1(self):
        from jui_cli.core.view_diff_checker import ViewDiffChecker

        canon = Canonicalizer(_table())

        def normalizer(tree):
            return canon.canonicalize(tree)[0]

        generated_l0 = {
            "type": "View",
            "id": "root",
            "alpha": 1,
            "child": [{"type": "Slider", "id": "volume", "minValue": 0}],
        }
        # Simulate the distributed platform-side copy (L1 + $jui marker).
        actual_l1, _ = canon.canonicalize(generated_l0)

        checker = ViewDiffChecker(normalizer=normalizer)
        diff = checker.compare(generated_l0, actual_l1, screen="home")
        self.assertFalse(diff.has_diff)
        self.assertEqual(diff.total_match_pct, 100)


if __name__ == "__main__":
    unittest.main()
