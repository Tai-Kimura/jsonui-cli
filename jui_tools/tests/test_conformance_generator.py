"""Tests for `jui conformance generate` (fixture generator + rules).

Covers the plan-01 acceptance criteria on the generator side:

- classification (assertable / visual / untestable-with-reason)
- alias double-generation (canonical + alias spelling, same expectation)
- enum expansion incl. case-insensitive filename dedup (macOS-safe)
- determinism / idempotency (two runs -> byte-identical tree)
- zero silent drops (every attribute is a fixture or a reasoned skip)
- @generated markers on every emitted file
- generated tests conform to the jsonui-test-runner screen-test shape
- v2: interactive fixtures (binding/callback promotion, conformanceState
  contract in the manifest, case-insensitive path dedup)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import interactive_rules, rules
from jui_cli.conformance.fixture_generator import generate_conformance

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DEFINITIONS = REPO_ROOT / "shared" / "core" / "attribute_definitions.json"

#: Small synthetic definitions exercising every classification branch.
SYNTHETIC_DEFS = {
    "_comment": "synthetic definitions for conformance generator tests",
    "common": {
        "_comment": "common attributes",
        "type": {"type": "string", "required": True, "description": "Component type"},
        "visibility": {
            "type": ["string", "binding"],
            "enum": ["visible", "invisible", "gone"],
            "description": "View visibility state",
        },
        "hidden": {"type": ["boolean", "binding"], "description": "Hidden flag"},
        "opacity": {
            "type": ["number", "binding"],
            "description": "Opacity",
            "aliases": ["alpha"],
        },
        "background": {"type": ["string", "binding"], "description": "Background color"},
        "onclick": {"type": ["string", "array"], "description": "Click handler"},
        "someBinding": {"type": "binding", "description": "Binding-only attribute"},
        "width": {
            "type": ["number", {"enum": ["matchParent", "wrapContent"]}, "binding"],
            "required": True,
            "description": "Width",
        },
    },
    "Label": {
        "text": {"type": ["string", "binding"], "description": "Text content"},
        "textAlign": {
            "type": ["string", "binding"],
            "enum": ["Left", "left"],
            "description": "Alignment with duplicate spellings",
        },
        "onTextChange": {"type": "callback", "description": "Change callback"},
        "highlightAttributes": {
            "type": "object",
            "description": "Composite object without representative value",
        },
    },
    "Embed": {
        "screen": {"type": "string", "required": True, "description": "Embedded screen"},
    },
}


def _write_defs(tmp: Path, defs: dict) -> Path:
    path = tmp / "attribute_definitions.json"
    path.write_text(json.dumps(defs, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _tree_digest(root: Path) -> dict[str, str]:
    """Relative path -> sha256, for byte-level idempotency comparison."""
    digest = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


class ConformanceGeneratorTest(unittest.TestCase):
    """Generator behavior on the synthetic definition set."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.defs_path = _write_defs(tmp, SYNTHETIC_DEFS)
        cls.out_dir = tmp / "conformance"
        cls.summary = generate_conformance(cls.defs_path, cls.out_dir)
        cls.manifest = json.loads((cls.out_dir / "manifest.json").read_text(encoding="utf-8"))
        cls.by_id = {f["id"]: f for f in cls.manifest["fixtures"]}
        cls.skips = {
            (s["component"], s["attribute"]): s["reason"] for s in cls.manifest["skipped"]
        }

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # ---------------- classification ---------------- #

    def test_text_is_assertable_with_text_assertion(self):
        fixture = self.by_id["Label/text__static"]
        self.assertEqual(fixture["class"], "assertable")
        test = json.loads((self.out_dir / fixture["test"]).read_text(encoding="utf-8"))
        steps = test["cases"][0]["steps"]
        self.assertIn(
            {"assert": "text", "id": "target", "equals": rules.CONFORMANCE_TEXT}, steps
        )

    def test_visibility_enum_expands_with_matching_assertions(self):
        expectations = {
            "common/visibility__visible": "visible",
            "common/visibility__invisible": "notVisible",
            "common/visibility__gone": "notVisible",
        }
        for fixture_id, expected_assert in expectations.items():
            fixture = self.by_id[fixture_id]
            self.assertEqual(fixture["class"], "assertable")
            test = json.loads((self.out_dir / fixture["test"]).read_text(encoding="utf-8"))
            asserts = [s.get("assert") for s in test["cases"][0]["steps"] if "assert" in s]
            self.assertEqual(asserts, [expected_assert], fixture_id)

    def test_hidden_boolean_generates_true_and_false_cases(self):
        self.assertIn("common/hidden__true", self.by_id)
        self.assertIn("common/hidden__false", self.by_id)

    def test_visual_attribute_gets_screenshot_only(self):
        fixture = self.by_id["common/background__static"]
        self.assertEqual(fixture["class"], "visual")
        test = json.loads((self.out_dir / fixture["test"]).read_text(encoding="utf-8"))
        steps = test["cases"][0]["steps"]
        self.assertEqual(steps[-1]["action"], "screenshot")
        self.assertNotIn("assert", [k for s in steps for k in s])

    def test_untestable_attributes_are_skipped_with_reasons(self):
        # common/onclick has an interactive rule -> promoted, NOT skipped.
        self.assertNotIn(("common", "onclick"), self.skips)
        # Label/onTextChange has no interactive rule (only TextField/TextView do).
        self.assertEqual(self.skips[("Label", "onTextChange")], rules.REASON_CALLBACK)
        self.assertEqual(self.skips[("common", "someBinding")], rules.REASON_BINDING_ONLY)
        self.assertEqual(self.skips[("common", "type")], rules.REASON_METADATA)
        self.assertEqual(
            self.skips[("Label", "highlightAttributes")], rules.REASON_COMPOSITE
        )
        self.assertIn(("Embed", "screen"), self.skips)
        # $-prefixed harness/normalizer markers (e.g. $jui) are metadata.
        self.assertEqual(
            rules._untestable_reason("common", "$jui", {"type": "object"}),
            rules.REASON_METADATA,
        )

    def test_no_silent_drops(self):
        covered = set(self.by_id and {(f["component"], f["attribute"]) for f in self.manifest["fixtures"]})
        covered |= set(self.skips)
        for section, attrs in SYNTHETIC_DEFS.items():
            if section == "_comment":
                continue
            for attribute in attrs:
                self.assertIn(
                    (section, attribute), covered, f"{section}.{attribute} silently dropped"
                )

    # ---------------- enum / width / alias ---------------- #

    def test_enum_dedup_is_case_insensitive_and_deterministic(self):
        self.assertIn("Label/textAlign__left", self.by_id)
        self.assertIn("Label/textAlign__left_2", self.by_id)
        self.assertEqual(self.by_id["Label/textAlign__left"]["value"], "Left")
        self.assertEqual(self.by_id["Label/textAlign__left_2"]["value"], "left")

    def test_width_generates_number_and_enum_cases(self):
        self.assertIn("common/width__static", self.by_id)
        self.assertIn("common/width__matchparent", self.by_id)
        self.assertIn("common/width__wrapcontent", self.by_id)

    def test_alias_fixture_mirrors_canonical_case(self):
        canonical = self.by_id["common/opacity__static"]
        alias = self.by_id["common/opacity__alias_alpha"]
        self.assertEqual(alias["aliasOf"], "common/opacity__static")
        self.assertEqual(alias["writtenKey"], "alpha")
        self.assertEqual(alias["value"], canonical["value"])
        layout = json.loads((self.out_dir / alias["layout"]).read_text(encoding="utf-8"))
        target = self._find_target(layout)
        self.assertIn("alpha", target)
        self.assertNotIn("opacity", target)

    def _find_target(self, layout: dict) -> dict:
        for child in layout.get("child", []):
            if child.get("id") == "target":
                return child
        self.fail("target node not found")

    # ---------------- markers / determinism ---------------- #

    def test_generated_markers_everywhere(self):
        for fixture in self.manifest["fixtures"]:
            layout = json.loads((self.out_dir / fixture["layout"]).read_text(encoding="utf-8"))
            self.assertEqual(layout["_generated"]["sentinel"], "@generated", fixture["id"])
            test = json.loads((self.out_dir / fixture["test"]).read_text(encoding="utf-8"))
            self.assertIn("@generated", test["metadata"]["generatedBy"], fixture["id"])
        self.assertEqual(self.manifest["_generated"]["sentinel"], "@generated")

    def test_no_timestamps_in_output(self):
        for path in sorted(self.out_dir.rglob("*.json")):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("generatedAt", content, path.name)

    def test_generate_twice_is_byte_identical(self):
        before = _tree_digest(self.out_dir)
        generate_conformance(self.defs_path, self.out_dir)
        self.assertEqual(before, _tree_digest(self.out_dir))

    def test_generate_into_fresh_dir_matches(self):
        with tempfile.TemporaryDirectory() as other:
            other_dir = Path(other) / "conformance"
            generate_conformance(self.defs_path, other_dir)
            self.assertEqual(_tree_digest(self.out_dir), _tree_digest(other_dir))

    def test_stale_fixtures_are_removed_on_regeneration(self):
        stale = self.out_dir / "fixtures" / "Label" / "zzz__stale.layout.json"
        stale.write_text("{}", encoding="utf-8")
        generate_conformance(self.defs_path, self.out_dir)
        self.assertFalse(stale.exists())

    # ---------------- manifest content ---------------- #

    def test_manifest_hash_matches_definitions_file(self):
        expected = hashlib.sha256(self.defs_path.read_bytes()).hexdigest()
        self.assertEqual(self.manifest["generatedFrom"], expected)

    def test_manifest_counts_are_consistent(self):
        counts = self.manifest["counts"]
        fixtures = self.manifest["fixtures"]
        self.assertEqual(counts["fixtures"], len(fixtures))
        self.assertEqual(counts["skipped"], len(self.manifest["skipped"]))
        self.assertEqual(
            counts["assertable"], sum(1 for f in fixtures if f["class"] == "assertable")
        )
        self.assertEqual(
            counts["visual"], sum(1 for f in fixtures if f["class"] == "visual")
        )

    def test_screen_test_shape(self):
        """Structural conformance with the screen-test schema (no jsonschema dep)."""
        for fixture in self.manifest["fixtures"]:
            test = json.loads((self.out_dir / fixture["test"]).read_text(encoding="utf-8"))
            self.assertEqual(test["type"], "screen", fixture["id"])
            self.assertIn("layout", test["source"])
            self.assertIn("name", test["metadata"])
            self.assertGreaterEqual(len(test["cases"]), 1)
            for case in test["cases"]:
                self.assertTrue(case["name"])
                self.assertGreaterEqual(len(case["steps"]), 1)
                for step in case["steps"]:
                    self.assertTrue(
                        ("action" in step) ^ ("assert" in step),
                        f"step must be an action xor assertion: {step}",
                    )


class ConformanceInteractiveTest(unittest.TestCase):
    """v2 interactive fixtures on the synthetic definition set."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.defs_path = _write_defs(tmp, SYNTHETIC_DEFS)
        cls.out_dir = tmp / "conformance"
        cls.summary = generate_conformance(cls.defs_path, cls.out_dir)
        cls.manifest = json.loads((cls.out_dir / "manifest.json").read_text(encoding="utf-8"))
        cls.by_id = {f["id"]: f for f in cls.manifest["fixtures"]}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _load(self, fixture: dict, kind: str) -> dict:
        return json.loads((self.out_dir / fixture[kind]).read_text(encoding="utf-8"))

    # ---------------- promotion out of the skip list ---------------- #

    def test_callback_attribute_is_promoted_to_interactive(self):
        fixture = self.by_id["common/onclick__callback_fire"]
        self.assertEqual(fixture["class"], "interactive")
        self.assertEqual(fixture["promotedFrom"], rules.REASON_CALLBACK)
        self.assertEqual(self.manifest["counts"]["promoted"], {"callback": 1})
        self.assertEqual(
            self.manifest["counts"]["interactive"], self.summary.interactive_count
        )

    def test_static_fixture_entries_carry_null_state(self):
        fixture = self.by_id["Label/text__static"]
        self.assertIsNone(fixture["state"])
        self.assertIsNone(fixture["promotedFrom"])

    # ---------------- conformanceState contract in the manifest ---------------- #

    def test_callback_fire_state_contract(self):
        fixture = self.by_id["common/onclick__callback_fire"]
        self.assertEqual(
            fixture["state"],
            {
                "vars": [
                    {
                        "name": interactive_rules.RESULT_VAR,
                        "class": "String",
                        "defaultValue": interactive_rules.RESULT_BEFORE,
                    }
                ],
                "handlers": [
                    {
                        "name": interactive_rules.FIRE_HANDLER,
                        "set": {
                            "var": interactive_rules.RESULT_VAR,
                            "value": interactive_rules.RESULT_AFTER,
                        },
                    }
                ],
            },
        )

    def test_interactive_layout_declares_data_section_and_mirror(self):
        fixture = self.by_id["common/onclick__callback_fire"]
        layout = self._load(fixture, "layout")
        self.assertEqual(layout["orientation"], "vertical")
        self.assertEqual(
            layout["data"],
            [
                {
                    "name": interactive_rules.RESULT_VAR,
                    "class": "String",
                    "defaultValue": interactive_rules.RESULT_BEFORE,
                }
            ],
        )
        by_node_id = {c["id"]: c for c in layout["child"]}
        self.assertEqual(
            by_node_id["target"]["onclick"], interactive_rules.FIRE_HANDLER
        )
        self.assertEqual(
            by_node_id["mirror"]["text"], f"@{{{interactive_rules.RESULT_VAR}}}"
        )

    def test_callback_fire_test_steps(self):
        fixture = self.by_id["common/onclick__callback_fire"]
        steps = self._load(fixture, "test")["cases"][0]["steps"]
        self.assertEqual(
            steps,
            [
                {"action": "waitFor", "id": "root"},
                {"assert": "text", "id": "mirror", "equals": interactive_rules.RESULT_BEFORE},
                {"action": "tap", "id": "target"},
                {"assert": "text", "id": "mirror", "equals": interactive_rules.RESULT_AFTER},
            ],
        )

    # ---------------- binding fixture types ---------------- #

    def test_binding_initial_asserts_data_default_on_target(self):
        fixture = self.by_id["Label/text__binding_initial"]
        self.assertEqual(fixture["class"], "interactive")
        self.assertIsNone(fixture["promotedFrom"])  # text was already testable
        steps = self._load(fixture, "test")["cases"][0]["steps"]
        self.assertIn(
            {"assert": "text", "id": "target", "equals": interactive_rules.BOUND_INITIAL},
            steps,
        )
        layout = self._load(fixture, "layout")
        target = next(c for c in layout["child"] if c["id"] == "target")
        self.assertEqual(target["text"], f"@{{{interactive_rules.TEXT_VAR}}}")

    def test_visibility_binding_sweep_covers_all_enum_values(self):
        expectations = {
            "common/visibility__binding_visible": "visible",
            "common/visibility__binding_invisible": "notVisible",
            "common/visibility__binding_gone": "notVisible",
        }
        for fixture_id, expected_assert in expectations.items():
            fixture = self.by_id[fixture_id]
            self.assertEqual(fixture["class"], "interactive", fixture_id)
            steps = self._load(fixture, "test")["cases"][0]["steps"]
            asserts = [s["assert"] for s in steps if "assert" in s]
            self.assertEqual(asserts, [expected_assert], fixture_id)
            # the swept enum value is the data default
            layout = self._load(fixture, "layout")
            self.assertEqual(
                layout["data"][0]["defaultValue"], fixture_id.rsplit("_", 1)[-1]
            )

    # ---------------- case-insensitive path dedup ---------------- #

    def test_case_colliding_attributes_get_distinct_file_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            defs = {
                "common": {
                    "onclick": {"type": ["string", "array"], "description": "selector"},
                    "onClick": {"type": "binding", "description": "binding"},
                }
            }
            defs_path = _write_defs(Path(tmp), defs)
            out_dir = Path(tmp) / "out"
            generate_conformance(defs_path, out_dir)
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            layouts = [f["layout"].lower() for f in manifest["fixtures"]]
            self.assertEqual(len(layouts), len(set(layouts)))
            for fixture in manifest["fixtures"]:
                self.assertTrue((out_dir / fixture["layout"]).is_file(), fixture["id"])
                self.assertTrue((out_dir / fixture["test"]).is_file(), fixture["id"])

    # ---------------- rule table hygiene ---------------- #

    def test_interactive_rule_table_matches_real_definitions(self):
        """Every rule-table key must exist in the real SSoT (no dead rules)."""
        defs = json.loads(REAL_DEFINITIONS.read_text(encoding="utf-8"))
        for section, attribute in interactive_rules.INTERACTIVE_SPECS:
            self.assertIn(attribute, defs.get(section, {}), f"{section}.{attribute}")

    def test_interactive_steps_stay_inside_runner_vocabulary(self):
        allowed_actions = {"waitFor", "tap", "input", "longPress", "selectOption"}
        allowed_asserts = {"text", "visible", "notVisible"}
        for specs in interactive_rules.INTERACTIVE_SPECS.values():
            for spec in specs:
                for step in spec.steps:
                    if "action" in step:
                        self.assertIn(step["action"], allowed_actions, step)
                    else:
                        self.assertIn(step["assert"], allowed_asserts, step)


class ConformanceGeneratorRealDefinitionsTest(unittest.TestCase):
    """Smoke tests against the repo's real attribute_definitions.json."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls._tmp.name) / "conformance"
        cls.summary = generate_conformance(REAL_DEFINITIONS, cls.out_dir)
        cls.manifest = json.loads((cls.out_dir / "manifest.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_full_coverage_no_silent_drops(self):
        defs = json.loads(REAL_DEFINITIONS.read_text(encoding="utf-8"))
        covered = {(f["component"], f["attribute"]) for f in self.manifest["fixtures"]}
        covered |= {(s["component"], s["attribute"]) for s in self.manifest["skipped"]}
        for section, attrs in defs.items():
            if section == "_comment" or not isinstance(attrs, dict):
                continue
            for attribute in attrs:
                self.assertIn((section, attribute), covered)

    def test_reasonable_volume(self):
        self.assertGreater(self.summary.fixture_count, 500)
        self.assertGreater(self.summary.assertable_count, 20)
        self.assertGreater(self.summary.skipped_count, 100)

    def test_interactive_volume_and_promotions(self):
        # 12 attributes promoted out of `callback` (v1 had 50); every
        # interactive fixture carries a state contract.
        self.assertEqual(self.summary.promoted, {"callback": 12})
        self.assertGreaterEqual(self.summary.interactive_count, 19)
        for fixture in self.manifest["fixtures"]:
            if fixture["class"] == "interactive":
                self.assertIsInstance(fixture["state"], dict, fixture["id"])
                self.assertIn("vars", fixture["state"], fixture["id"])
                self.assertIn("handlers", fixture["state"], fixture["id"])

    def test_unique_ids_and_case_insensitive_paths(self):
        ids = [f["id"] for f in self.manifest["fixtures"]]
        self.assertEqual(len(ids), len(set(ids)))
        lowered = [f["layout"].lower() for f in self.manifest["fixtures"]]
        self.assertEqual(len(lowered), len(set(lowered)), "macOS filename collision")

    @unittest.skipIf(shutil.which("jsonui-test") is None, "jsonui-test CLI not installed")
    def test_jsonui_test_validate_passes(self):
        proc = subprocess.run(
            ["jsonui-test", "validate", str(self.out_dir / "fixtures")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Errors: 0, Warnings: 0", proc.stdout)


class ConformanceCommandTest(unittest.TestCase):
    """`jui conformance` argparse dispatch."""

    def test_generate_subcommand_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            defs_path = _write_defs(Path(tmp), SYNTHETIC_DEFS)
            from jui_cli.commands.conformance_cmd import cmd_conformance

            args = argparse.Namespace(
                conformance_target="generate",
                definitions=str(defs_path),
                out=str(Path(tmp) / "out"),
            )
            self.assertEqual(cmd_conformance(args), 0)
            self.assertTrue((Path(tmp) / "out" / "manifest.json").is_file())

    def test_missing_subcommand_prints_usage(self):
        from jui_cli.commands.conformance_cmd import cmd_conformance

        self.assertEqual(cmd_conformance(argparse.Namespace(conformance_target=None)), 1)


if __name__ == "__main__":
    unittest.main()
