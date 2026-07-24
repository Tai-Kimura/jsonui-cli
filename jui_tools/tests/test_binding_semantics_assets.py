"""Schema guard for the binding-resolution SSoT assets.

``shared/core/binding_semantics.json`` (canonical semantics) and
``shared/core/binding_vectors.json`` (shared test vectors) are hand-authored
canonical sources consumed by platform unit tests and codegen validator
specs (renderer SSoT track 15). This guard keeps them parseable, internally
consistent, and cross-linked so a malformed edit fails in jsonui-cli CI
before any platform vendors a broken copy.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

SHARED_CORE = Path(__file__).resolve().parents[2] / "shared" / "core"
SEMANTICS_PATH = SHARED_CORE / "binding_semantics.json"
VECTORS_PATH = SHARED_CORE / "binding_vectors.json"

WHOLE_BINDING_RE = re.compile(r"^@\{.+\}$", re.DOTALL)
RUNTIME_EXPECT_KEYS = ("text", "value", "outcome", "params")


def _load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class BindingSemanticsAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.semantics = _load(SEMANTICS_PATH)
        cls.vectors = _load(VECTORS_PATH)

    # --- semantics -------------------------------------------------------

    def test_semantics_version_and_sections(self):
        self.assertIsInstance(self.semantics["version"], int)
        for section in (
            "contexts",
            "pathResolution",
            "defaultOperator",
            "unresolved",
            "fallbackPrecedence",
            "negation",
            "coercion",
            "validatorRules",
        ):
            self.assertIn(section, self.semantics, f"missing section: {section}")

    def test_semantics_context_shape(self):
        for name, ctx in self.semantics["contexts"].items():
            self.assertIn("description", ctx, name)
            self.assertIn("features", ctx, name)
            self.assertIn("unresolved", ctx, name)

    def test_validator_rule_ids_unique_and_shaped(self):
        rules = self.semantics["validatorRules"]
        ids = [r["id"] for r in rules]
        self.assertEqual(len(ids), len(set(ids)), "duplicate validator rule ids")
        for rule in rules:
            self.assertIn(rule["severity"], ("error", "warning"), rule["id"])
            self.assertTrue(rule["rule"], rule["id"])

    # --- vectors ---------------------------------------------------------

    def test_vectors_link_to_semantics_version(self):
        self.assertIsInstance(self.vectors["version"], int)
        self.assertEqual(
            self.vectors["semanticsVersion"],
            self.semantics["version"],
            "binding_vectors.json semanticsVersion must match "
            "binding_semantics.json version — bump them together",
        )

    def test_case_ids_unique(self):
        ids = [c["id"] for c in self.vectors["cases"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate vector case ids")

    def test_runtime_case_shapes(self):
        contexts = set(self.semantics["contexts"].keys())
        for case in self.vectors["cases"]:
            if case.get("kind") == "validation":
                continue
            cid = case["id"]
            self.assertIn(case["context"], contexts, cid)
            expect = case["expect"]
            present = [k for k in RUNTIME_EXPECT_KEYS if k in expect]
            self.assertEqual(len(present), 1, f"{cid}: expect must have exactly one of {RUNTIME_EXPECT_KEYS}")
            if "outcome" in expect:
                self.assertEqual(expect["outcome"], "unresolved", cid)
            if case["context"] == "text":
                self.assertIn("template", case, cid)
                self.assertIsInstance(case["data"], dict, cid)
                self.assertIn("text", expect, cid)
            elif case["context"] == "value":
                self.assertIn(case["valueType"], ("string", "number", "bool"), cid)
                self.assertRegex(case["expr"], WHOLE_BINDING_RE, cid)
                self.assertIsInstance(case["data"], dict, cid)
                self.assertTrue("value" in expect or "outcome" in expect, cid)
            elif case["context"] == "embedParams":
                self.assertIsInstance(case["params"], dict, cid)
                self.assertIsInstance(case["parentData"], dict, cid)
                self.assertIn("params", expect, cid)
            else:
                self.fail(f"{cid}: runtime case in non-runtime context {case['context']}")
            if "dataDefaults" in case:
                self.assertIsInstance(case["dataDefaults"], dict, cid)

    def test_validation_cases_reference_declared_rules(self):
        rule_ids = {r["id"] for r in self.semantics["validatorRules"]}
        for case in self.vectors["cases"]:
            if case.get("kind") != "validation":
                continue
            self.assertIn(case["expectError"], rule_ids, case["id"])
            self.assertTrue(
                any(k in case for k in ("template", "expr", "params")),
                f"{case['id']}: validation case needs template/expr/params input",
            )

    def test_runtime_coverage_per_context(self):
        counts: dict[str, int] = {}
        for case in self.vectors["cases"]:
            if case.get("kind") == "validation":
                continue
            counts[case["context"]] = counts.get(case["context"], 0) + 1
        for ctx in ("text", "value", "embedParams"):
            self.assertGreaterEqual(
                counts.get(ctx, 0), 5, f"context '{ctx}' needs runtime vector coverage"
            )

    def test_every_error_rule_has_a_validation_vector(self):
        referenced = {
            c["expectError"] for c in self.vectors["cases"] if c.get("kind") == "validation"
        }
        for rule in self.semantics["validatorRules"]:
            if rule["severity"] != "error":
                continue
            self.assertIn(
                rule["id"],
                referenced,
                f"error rule '{rule['id']}' has no validation vector — "
                "add one or downgrade the rule",
            )


if __name__ == "__main__":
    unittest.main()
