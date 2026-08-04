"""Tests for `jui lint-strings` — SSoT-derived visible attributes,
strings.json resolution, the layout scanner, the two-way allowlist
ratchet, and the opt-in build gate.

The SSoT inputs (attribute definitions + STRING_PROPS vocabulary) are
synthetic fixtures written to a temp dir — the suite must not depend on
the live shared/core files, which other work streams edit.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.lint_strings_cmd import (
    ALLOWLIST_FILENAME,
    Allowlist,
    Finding,
    LayoutScanner,
    LintStringsSetupError,
    StringsTable,
    _update_allowlist,
    collect_findings,
    is_lintable_literal,
    load_string_props,
    visible_attrs_by_component,
)
from jui_cli.commands.build_cmd import _lint_strings_enabled
from jui_cli.core.config_manager import ConfigManager
from jui_cli.core.normalizer import AliasTable

VOCABULARY = frozenset({"text", "hint", "placeholder", "label", "prompt"})

SYNTH_DEFS = {
    "common": {
        "visibility": {"type": "string"},
    },
    "Label": {
        "text": {"type": ["string", "binding"]},
        "hint": {"type": "string"},
        "fontColor": {"type": "string"},
    },
    "TextField": {
        "text": {"type": ["string", "binding"]},
        "hint": {"type": "string", "aliases": ["placeholder"]},
    },
    "Button": {
        "text": {"type": ["string", "binding"]},
    },
    "Image": {
        "src": {"type": "string"},
    },
    # Vocabulary names used for image resources — no binding-typed text
    # attr, so the whole component is out of the lint's scope.
    "NetworkImage": {
        "src": {"type": ["string", "binding"]},
        "hint": {"type": "string"},
        "placeholder": {"type": "string"},
    },
}

STRINGS = {
    "login": {
        "title": "Sign in",
        "greeting": {"en": "Welcome", "ja": "ようこそ"},
        "items_count": {"en": {"plural": {"one": "{count} item", "other": "{count} items"}}},
    },
}

PLURAL_VALIDATOR_SNIPPET = """
module Shared
  class PluralValidator
    STRING_PROPS = %w[text hint placeholder label prompt].freeze
  end
end
"""


def _scanner(strings=None) -> LayoutScanner:
    table = AliasTable(SYNTH_DEFS)
    return LayoutScanner(
        table,
        visible_attrs_by_component(SYNTH_DEFS, VOCABULARY),
        VOCABULARY,
        StringsTable(strings if strings is not None else STRINGS),
    )


class StringPropsTest(unittest.TestCase):
    def test_parses_vocabulary_from_ruby(self):
        with tempfile.TemporaryDirectory() as tmp:
            rb = Path(tmp) / "plural_validator.rb"
            rb.write_text(PLURAL_VALIDATOR_SNIPPET, encoding="utf-8")
            self.assertEqual(load_string_props(rb), VOCABULARY)

    def test_missing_file_is_a_setup_error(self):
        with self.assertRaises(LintStringsSetupError):
            load_string_props(Path("/nonexistent/plural_validator.rb"))

    def test_missing_constant_is_a_setup_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            rb = Path(tmp) / "plural_validator.rb"
            rb.write_text("module Empty; end\n", encoding="utf-8")
            with self.assertRaises(LintStringsSetupError):
                load_string_props(rb)


class VisibleAttrsTest(unittest.TestCase):
    def test_intersection_with_declared_attributes(self):
        vm = visible_attrs_by_component(SYNTH_DEFS, VOCABULARY)
        self.assertEqual(vm["Label"], frozenset({"text", "hint"}))
        self.assertEqual(vm["TextField"], frozenset({"text", "hint"}))
        self.assertEqual(vm["Image"], frozenset())
        # fontColor is string-typed but not in the vocabulary
        self.assertNotIn("fontColor", vm["Label"])

    def test_component_without_bindable_text_attr_is_excluded(self):
        # NetworkImage's hint/placeholder are image names, not copy —
        # no vocabulary attr declares "binding", so the set is empty.
        vm = visible_attrs_by_component(SYNTH_DEFS, VOCABULARY)
        self.assertEqual(vm["NetworkImage"], frozenset())


class LintableLiteralTest(unittest.TestCase):
    def test_judged(self):
        self.assertTrue(is_lintable_literal("Hello"))
        self.assertTrue(is_lintable_literal("ログイン"))

    def test_skipped(self):
        self.assertFalse(is_lintable_literal(None))
        self.assertFalse(is_lintable_literal(12))
        self.assertFalse(is_lintable_literal(""))
        self.assertFalse(is_lintable_literal("   "))
        self.assertFalse(is_lintable_literal("@{userName}"))
        self.assertFalse(is_lintable_literal("Hello @{userName}"))
        self.assertFalse(is_lintable_literal("${count}"))
        self.assertFalse(is_lintable_literal("100%"))
        self.assertFalse(is_lintable_literal("12:34"))
        self.assertFalse(is_lintable_literal("→"))


class StringsTableTest(unittest.TestCase):
    def test_resolution_forms(self):
        table = StringsTable(STRINGS)
        self.assertTrue(table.resolves("title"))          # bare key
        self.assertTrue(table.resolves("login_title"))    # {group}_{key}
        self.assertTrue(table.resolves("Sign in"))        # value match
        self.assertTrue(table.resolves("ようこそ"))        # language value match
        self.assertTrue(table.resolves("items_count"))    # key of a plural entry

    def test_plural_forms_do_not_value_match(self):
        table = StringsTable(STRINGS)
        self.assertFalse(table.resolves("{count} items"))

    def test_unknown_literal(self):
        table = StringsTable(STRINGS)
        self.assertFalse(table.resolves("Sign out"))

    def test_empty_table_resolves_nothing(self):
        self.assertFalse(StringsTable({}).resolves("title"))
        self.assertFalse(StringsTable(None).resolves("title"))


class DuplicateDeclarationTest(unittest.TestCase):
    """One text under two sections: the builders take the first section
    that matches and name sections differently per platform, so the
    generated key forks and section order picks the winner."""

    def test_same_text_in_two_sections_is_reported(self):
        table = StringsTable(
            {
                "hero_section_cell": {"rating": "RATING"},
                "item_detail_hero_section_cell": {"rating": "RATING"},
            }
        )
        dups = table.duplicate_declarations()
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0].value, "RATING")
        self.assertEqual(
            dups[0].sections(),
            ["hero_section_cell", "item_detail_hero_section_cell"],
        )
        self.assertEqual(
            dups[0].sites,
            (("hero_section_cell", "rating"), ("item_detail_hero_section_cell", "rating")),
        )

    def test_two_keys_in_one_section_are_not_a_fork(self):
        # Same text twice inside ONE section still resolves to one
        # section on every platform — no cross-platform divergence.
        table = StringsTable({"login": {"submit": "OK", "confirm": "OK"}})
        self.assertEqual(table.duplicate_declarations(), [])

    def test_distinct_texts_are_clean(self):
        table = StringsTable(
            {"a": {"k": "One"}, "b": {"k": "Two"}}
        )
        self.assertEqual(table.duplicate_declarations(), [])


class ScannerTest(unittest.TestCase):
    def test_raw_literal_is_a_finding_with_path(self):
        tree = {
            "type": "View",
            "child": [
                {"type": "Label", "text": "login_title"},
                {"type": "Label", "text": "Sign out"},
            ],
        }
        findings = _scanner().scan(tree, "login.json")
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual((f.layout, f.path, f.value), ("login.json", "child[1].text", "Sign out"))

    def test_non_visible_attributes_are_ignored(self):
        tree = {"type": "Image", "src": "hero_banner"}
        self.assertEqual(_scanner().scan(tree, "a.json"), [])

    def test_image_placeholder_names_are_not_findings(self):
        tree = {"type": "NetworkImage", "src": "@{url}", "placeholder": "downstream_placeholder"}
        self.assertEqual(_scanner().scan(tree, "a.json"), [])

    def test_unknown_component_falls_back_to_vocabulary(self):
        tree = {"type": "FancyBadge", "label": "New!", "iconName": "star.fill"}
        findings = _scanner().scan(tree, "a.json")
        self.assertEqual([f.path for f in findings], ["label"])

    def test_platform_patch_values_are_judged(self):
        tree = {
            "type": "Label",
            "text": "login_title",
            "platform": {"ios": {"text": "iOS only raw"}},
        }
        findings = _scanner().scan(tree, "a.json")
        self.assertEqual([f.path for f in findings], ["platform.ios.text"])

    def test_responsive_patch_values_are_judged(self):
        tree = {
            "type": "Label",
            "text": "login_title",
            "responsive": {"regular": {"text": "Tablet raw"}},
        }
        findings = _scanner().scan(tree, "a.json")
        self.assertEqual([f.path for f in findings], ["responsive.regular.text"])

    def test_bindings_and_glyphs_pass(self):
        tree = {
            "type": "View",
            "child": [
                {"type": "Label", "text": "@{userName}"},
                {"type": "Label", "text": "100%"},
                {"type": "Label", "text": ""},
            ],
        }
        self.assertEqual(_scanner().scan(tree, "a.json"), [])


class ProjectFixture:
    """A minimal consumer project on disk."""

    def __init__(self, root: Path):
        self.root = root
        (root / "docs/screens/layouts/Resources").mkdir(parents=True)
        (root / "docs/screens/styles").mkdir(parents=True)
        (root / "jui.config.json").write_text(
            json.dumps(
                {
                    "project_name": "fixture",
                    "layouts_directory": "docs/screens/layouts",
                    "styles_directory": "docs/screens/styles",
                    "platforms": {},
                }
            ),
            encoding="utf-8",
        )
        self.defs_path = root / "attribute_definitions.json"
        self.defs_path.write_text(json.dumps(SYNTH_DEFS), encoding="utf-8")
        self.props_path = root / "plural_validator.rb"
        self.props_path.write_text(PLURAL_VALIDATOR_SNIPPET, encoding="utf-8")
        self.write_strings(STRINGS)

    def write_strings(self, data) -> None:
        (self.root / "docs/screens/layouts/Resources/strings.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def write_layout(self, name: str, tree) -> None:
        (self.root / "docs/screens/layouts" / name).write_text(
            json.dumps(tree, ensure_ascii=False), encoding="utf-8"
        )

    def write_style(self, name: str, attrs) -> None:
        (self.root / "docs/screens/styles" / f"{name}.json").write_text(
            json.dumps(attrs, ensure_ascii=False), encoding="utf-8"
        )

    def write_allowlist(self, entries) -> None:
        (self.root / ALLOWLIST_FILENAME).write_text(
            json.dumps({"entries": entries}, ensure_ascii=False), encoding="utf-8"
        )

    def config_mgr(self) -> ConfigManager:
        return ConfigManager(config_path=self.root / "jui.config.json")

    def collect(self, **kwargs):
        return collect_findings(
            self.config_mgr(),
            definitions_path=self.defs_path,
            string_props_path=self.props_path,
            **kwargs,
        )


class CollectFindingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = ProjectFixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_forked_declaration_fails_the_run_and_is_not_allowlistable(self):
        self.fx.write_strings(
            {
                "hero_section_cell": {"rating": "RATING"},
                "item_detail_hero_section_cell": {"rating": "RATING"},
            }
        )
        self.fx.write_layout("home.json", {"type": "Label", "text": "RATING"})
        report = self.fx.collect()

        # The literal itself resolves, so it is not a raw-literal finding
        self.assertEqual(report.findings, [])
        self.assertEqual(len(report.duplicates), 1)
        self.assertFalse(report.clean)
        self.assertTrue(
            any("declares 'RATING' in 2 sections" in line for line in report.warning_lines())
        )

        # The allowlist ledger covers raw literals; it cannot silence a fork
        self.fx.write_allowlist(
            [{"layout": "home.json", "path": "text", "value": "RATING", "reason": "no"}]
        )
        report = self.fx.collect()
        self.assertFalse(report.clean)
        self.assertEqual(len(report.duplicates), 1)

    def test_single_declaration_stays_clean(self):
        self.fx.write_strings({"home": {"rating": "RATING"}})
        self.fx.write_layout("home.json", {"type": "Label", "text": "RATING"})
        report = self.fx.collect()
        self.assertTrue(report.clean)

    def test_style_merged_value_is_judged(self):
        self.fx.write_style("warn", {"text": "Raw from style"})
        self.fx.write_layout("home.json", {"type": "Label", "style": "warn"})
        report = self.fx.collect()
        self.assertEqual([f.value for f in report.findings], ["Raw from style"])

    def test_alias_spelling_is_canonicalized_before_judgment(self):
        # placeholder is an alias of TextField.hint in the synthetic SSoT
        self.fx.write_layout(
            "form.json", {"type": "TextField", "placeholder": "Type here"}
        )
        report = self.fx.collect()
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].attribute, "hint")

    def test_resources_and_styles_trees_are_not_scanned(self):
        self.fx.write_layout("home.json", {"type": "Label", "text": "login_title"})
        # a stray json under Resources must not be linted
        (self.fx.root / "docs/screens/layouts/Resources/junk.json").write_text(
            json.dumps({"type": "Label", "text": "Raw"}), encoding="utf-8"
        )
        report = self.fx.collect()
        self.assertEqual(report.findings, [])
        self.assertEqual(report.scanned_layouts, 1)

    def test_allowlisted_literal_with_reason_is_clean(self):
        self.fx.write_layout("home.json", {"type": "Label", "text": "ACMECORP"})
        self.fx.write_allowlist(
            [
                {
                    "layout": "home.json",
                    "path": "text",
                    "value": "ACMECORP",
                    "reason": "brand name, never localized",
                }
            ]
        )
        report = self.fx.collect()
        self.assertTrue(report.clean)
        self.assertEqual(len(report.allowed), 1)

    def test_allowlist_entry_without_reason_fails(self):
        self.fx.write_layout("home.json", {"type": "Label", "text": "ACMECORP"})
        self.fx.write_allowlist(
            [{"layout": "home.json", "path": "text", "value": "ACMECORP", "reason": ""}]
        )
        report = self.fx.collect()
        self.assertFalse(report.clean)
        self.assertEqual(len(report.missing_reason), 1)

    def test_stale_allowlist_entry_fails(self):
        self.fx.write_layout("home.json", {"type": "Label", "text": "login_title"})
        self.fx.write_allowlist(
            [
                {
                    "layout": "home.json",
                    "path": "text",
                    "value": "Gone literal",
                    "reason": "was here once",
                }
            ]
        )
        report = self.fx.collect()
        self.assertFalse(report.clean)
        self.assertEqual(len(report.stale_entries), 1)

    def test_missing_strings_json_flags_everything(self):
        (self.fx.root / "docs/screens/layouts/Resources/strings.json").unlink()
        self.fx.write_layout("home.json", {"type": "Label", "text": "Hello"})
        report = self.fx.collect()
        self.assertEqual(len(report.findings), 1)

    def test_update_allowlist_preserves_reasons(self):
        self.fx.write_layout(
            "home.json",
            {
                "type": "View",
                "child": [
                    {"type": "Label", "text": "ACMECORP"},
                    {"type": "Label", "text": "New raw"},
                ],
            },
        )
        self.fx.write_allowlist(
            [
                {
                    "layout": "home.json",
                    "path": "child[0].text",
                    "value": "ACMECORP",
                    "reason": "brand name",
                },
                {
                    "layout": "home.json",
                    "path": "child[9].text",
                    "value": "Stale",
                    "reason": "obsolete",
                },
            ]
        )
        report = self.fx.collect()
        args = argparse.Namespace(allowlist=None)
        exit_code = _update_allowlist(self.fx.config_mgr(), args, report)
        # New raw has no reason yet — the update itself reports non-clean
        self.assertNotEqual(exit_code, 0)

        written = Allowlist.load(self.fx.root / ALLOWLIST_FILENAME)
        by_key = {written.key_of(e): e for e in written.entries}
        self.assertEqual(len(written.entries), 2)  # stale entry dropped
        self.assertEqual(
            by_key[("home.json", "child[0].text", "ACMECORP")]["reason"], "brand name"
        )
        self.assertEqual(
            by_key[("home.json", "child[1].text", "New raw")]["reason"], ""
        )


class BuildGateTest(unittest.TestCase):
    def test_default_is_off(self):
        args = argparse.Namespace(lint_strings=False)
        self.assertFalse(_lint_strings_enabled({}, args))
        self.assertFalse(_lint_strings_enabled({"lint": {}}, args))
        # args without the attribute at all (defensive getattr default)
        self.assertFalse(_lint_strings_enabled({}, argparse.Namespace()))

    def test_flag_enables(self):
        args = argparse.Namespace(lint_strings=True)
        self.assertTrue(_lint_strings_enabled({}, args))

    def test_config_enables(self):
        args = argparse.Namespace(lint_strings=False)
        self.assertTrue(_lint_strings_enabled({"lint": {"strings": True}}, args))


if __name__ == "__main__":
    unittest.main()
