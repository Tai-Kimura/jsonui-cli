"""Tests for `jui lint-strings --usage` — set agreement between
strings.json and its referencing faces.

The check's whole justification is a zero false-positive rate (a naive
scan measured 98% false positives on a real consumer), so most of these
tests are about what must NOT be reported: keys referenced from list
items, from another face than the one being read, through the web
proxy's camel spelling, or through a declared ``*_STRING_KEYS`` map.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.lint_strings_cmd import collect_findings
from jui_cli.commands.lint_strings_usage import (
    DeclaredKeys,
    camelize_flat,
    collect_usage,
    snake_to_camel,
    snake_to_pascal,
)

try:
    from .test_lint_strings import ProjectFixture
except ImportError:  # unittest discover runs tests as top-level modules
    from test_lint_strings import ProjectFixture


class SpellingRoundTripTests(unittest.TestCase):
    def test_ios_generator_spellings(self):
        self.assertEqual(snake_to_pascal("member_list"), "MemberList")
        self.assertEqual(snake_to_camel("leave_button"), "leaveButton")
        self.assertEqual(snake_to_camel("title"), "title")

    def test_web_proxy_spelling(self):
        self.assertEqual(camelize_flat("login_forgot_password"),
                         "loginForgotPassword")
        self.assertEqual(camelize_flat("value_1"), "value1")


class DeclaredKeysTests(unittest.TestCase):
    GROUPS = {
        "login": {"title": "Sign in", "greeting": {"en": "Welcome"}},
        "member_list": {"leave_button": "Leave"},
    }

    def test_every_reference_spelling_is_precomputed(self):
        d = DeclaredKeys(self.GROUPS)
        self.assertIn(("login", "title"), d.by_flat["login_title"])
        self.assertIn(("member_list", "leave_button"),
                      d.by_camel["memberListLeaveButton"])
        self.assertIn(("member_list", "leave_button"),
                      d.by_accessor[("MemberList", "leaveButton")])
        self.assertIn(("login", "greeting"), d.by_value["Welcome"])

    def test_layout_targets_scopes_bare_keys_to_own_sections(self):
        d = DeclaredKeys(self.GROUPS)
        self.assertEqual(d.layout_targets("title", ("login",)),
                         {("login", "title")})
        # foreign bare key: not a reference (the raw-literal lint already
        # flags it) — must not count as usage either
        self.assertEqual(d.layout_targets("title", ("member_list",)), set())
        # the fully-qualified spelling reaches across sections
        self.assertEqual(d.layout_targets("login_title", ("member_list",)),
                         {("login", "title")})


def _usage(groups, trees=None, own=None, roots=None, spec_dir=None):
    return collect_usage(
        strings_groups=groups,
        trees=trees or {},
        own_sections_by_layout=own or {},
        platform_roots=roots or {},
        spec_dir=spec_dir,
    )


class LayoutUsedCollectionTests(unittest.TestCase):
    GROUPS = {"screen": {"title": "The Title", "row_label": "Row"}}

    def test_key_referenced_from_a_list_item_is_used(self):
        # items arrays resolve through the builders' label paths but sit
        # outside the raw-literal scanner's attr walk — the used side must
        # be broader or every such key reads as dead.
        trees = {"screen.json": {
            "type": "SelectBox",
            "items": [{"label": "row_label"}],
            "child": [{"type": "Label", "text": "screen_title"}],
        }}
        report = _usage(self.GROUPS, trees, {"screen.json": ("screen",)})
        self.assertEqual(report.unused, [])

    def test_value_match_counts_as_usage(self):
        trees = {"screen.json": {"type": "Label", "text": "The Title"}}
        report = _usage(
            {"screen": {"title": "The Title"}}, trees, {"screen.json": ("screen",)}
        )
        self.assertEqual(report.unused, [])

    def test_binding_expressions_never_count(self):
        trees = {"screen.json": {"type": "Label", "text": "@{title}"}}
        report = _usage(
            {"screen": {"title": "The Title"}}, trees, {"screen.json": ("screen",)}
        )
        self.assertEqual([f.site for f in report.unused], ["screen.title"])

    def test_unwired_key_is_reported(self):
        # The consumer incident: help text prepared, never referenced.
        trees = {"screen.json": {"type": "Label", "text": "screen_title"}}
        groups = {"screen": {"title": "T", "search_help": "Exact match only"}}
        report = _usage(groups, trees, {"screen.json": ("screen",)})
        self.assertEqual([f.site for f in report.unused],
                         ["screen.search_help"])


class VmFixture:
    """A platform source tree on disk."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def write(self, rel: str, content: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class WebScanTests(unittest.TestCase):
    GROUPS = {"screen": {"title": "T", "help": "H"}}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = VmFixture(Path(self._tmp.name) / "web")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, groups=None):
        return _usage(groups or self.GROUPS, roots={"web": self.fx.root})

    def test_camel_property_access_is_usage(self):
        self.fx.write("src/vm.ts",
                      "const t = StringManager.currentLanguage.screenTitle;\n"
                      "const h = StringManager.currentLanguage.screen_help;\n")
        report = self._run()
        self.assertEqual(report.unused, [])
        self.assertEqual(report.missing, [])

    def test_unknown_property_access_is_a_missing_key(self):
        self.fx.write("src/vm.ts",
                      "const x = StringManager.currentLanguage.screenTypo;\n")
        report = self._run()
        self.assertEqual(len(report.missing), 1)
        self.assertIn("screenTypo", report.missing[0].detail)
        self.assertTrue(report.missing[0].site.endswith("vm.ts:1"))

    def test_getstring_literal_is_usage_and_typo_is_missing(self):
        self.fx.write("src/vm.ts",
                      'a(StringManager.getString("screen_title"));\n'
                      'b(StringManager.getString("screen_helo"));\n')
        report = self._run()
        self.assertEqual([f.site for f in report.unused], ["screen.help"])
        self.assertEqual(len(report.missing), 1)
        self.assertIn("screen_helo", report.missing[0].detail)

    def test_dynamic_reference_without_declared_map_is_a_finding(self):
        self.fx.write("src/vm.ts",
                      "const t = StringManager.getString(kind);\n"
                      "const u = StringManager.currentLanguage[kind];\n")
        report = self._run()
        self.assertEqual(len(report.dynamic), 2)

    def test_declared_map_exempts_the_dynamic_site_and_feeds_used(self):
        self.fx.write(
            "src/vm.ts",
            'const KIND_STRING_KEYS = {\n'
            '  a: "screen_title",\n'
            '  b: "screen_help",\n'
            '};\n'
            "const t = StringManager.getString(KIND_STRING_KEYS[kind]);\n")
        report = self._run()
        self.assertEqual(report.dynamic, [])
        self.assertEqual(report.unused, [])

    def test_map_literal_not_in_strings_json_is_a_missing_key(self):
        self.fx.write("src/vm.ts",
                      'const K_STRING_KEYS = { a: "screen_gone" };\n')
        report = self._run()
        self.assertEqual(len(report.missing), 1)
        self.assertIn("screen_gone", report.missing[0].detail)

    def test_plural_first_argument_is_usage(self):
        # Keys referenced only through the CLDR plural face were all
        # reported unused (11 of 11 on the reporting consumer).
        self.fx.write("src/vm.ts",
                      'const a = StringManager.plural("screen_title", n);\n'
                      'const b = StringManager.plural("screen_help", m);\n')
        report = self._run()
        self.assertEqual(report.unused, [])
        self.assertEqual(report.missing, [])
        self.assertEqual(report.dynamic, [])

    def test_plural_undeclared_literal_is_a_missing_key(self):
        self.fx.write("src/vm.ts",
                      'StringManager.plural("screen_gone", n);\n')
        report = self._run()
        self.assertEqual(len(report.missing), 1)
        self.assertIn("screen_gone", report.missing[0].detail)

    def test_plural_dynamic_key_is_a_finding_unless_declared(self):
        self.fx.write("src/vm.ts",
                      "StringManager.plural(kind, n);\n"
                      'const K_STRING_KEYS = { a: "screen_title" };\n'
                      "StringManager.plural(K_STRING_KEYS[kind], n);\n")
        report = self._run()
        self.assertEqual(len(report.dynamic), 1)
        self.assertTrue(report.dynamic[0].site.endswith(":1"))

    def test_tpl_literal_choice_with_params_is_not_dynamic(self):
        # tpl(expr, {params}) judged the WHOLE argument span, so a
        # literal-choice key with trailing params read as dynamic while
        # the same expression in str() passed. Only the first argument
        # selects the key.
        self.fx.write(
            "src/vm.ts",
            'const t = tpl(late ? "screen_title" : "screen_help", '
            "{ n: count });\n")
        report = self._run()
        self.assertEqual(report.dynamic, [])
        self.assertEqual(report.unused, [])

    def test_tuple_array_string_keys_first_elements_are_not_missing(self):
        # [[prop, key], ...] interleaves non-key strings with keys and
        # nothing structural tells them apart: every literal may feed
        # used, none may be judged missing.
        self.fx.write(
            "src/vm.ts",
            'const ROW_STRING_KEYS = [\n'
            '  ["title", "screen_title"],\n'
            '  ["help", "screen_help"],\n'
            '];\n')
        report = self._run()
        self.assertEqual(report.missing, [])
        self.assertEqual(report.unused, [])

    def test_comment_text_is_not_code(self):
        # The shipped incident: a swagger description mentioning Python's
        # `str(int)` rode a generated DTO's doc comment into a dynamic
        # finding. The prose never selects a key.
        self.fx.write(
            "src/dto.ts",
            "/** backend returns the id in `str(int)` form (_shape). */\n"
            "export interface SeriesDto { id: string }\n"
            "// also prose: getString(anything) here is not a call\n")
        report = self._run()
        self.assertEqual(report.dynamic, [])
        self.assertEqual(report.missing, [])

    def test_commented_out_reference_is_not_usage(self):
        # The quiet direction: a getString("key") in a comment must not
        # mark the key used, or a real dead key hides forever.
        self.fx.write(
            "src/vm.ts",
            '// getString("screen_title") — old call, kept for reference\n'
            '/* StringManager.currentLanguage.screenHelp */\n')
        report = self._run()
        self.assertEqual({f.site for f in report.unused},
                         {"screen.title", "screen.help"})

    def test_a_url_string_does_not_open_a_comment(self):
        # "http://x" must not swallow the rest of the line as a comment —
        # the reference after it is real code.
        self.fx.write(
            "src/vm.ts",
            'const u = "http://example.test"; '
            "const t = StringManager.currentLanguage.screenTitle;\n"
            'a(StringManager.getString("screen_help"));\n')
        report = self._run()
        self.assertEqual(report.unused, [])

    def test_generated_string_manager_stub_is_not_scanned(self):
        # The real stub defines getString(key) — a dynamic-looking call
        # with no *_STRING_KEYS anywhere near it — and embeds the whole
        # table. Scanning it yields a false dynamic finding, and worse.
        self.fx.write("src/StringManager.ts",
                      "class StringManagerClass {\n"
                      "  getString(key) {\n"
                      "    return this.currentLanguage[key] || key;\n"
                      "  }\n"
                      "}\n"
                      'const strings = {"en": {"screen_title": "T", '
                      '"screen_help": "H"}};\n')
        report = self._run()
        self.assertEqual(report.dynamic, [])
        self.assertEqual({f.site for f in report.unused},
                         {"screen.title", "screen.help"})

    def test_node_modules_is_not_scanned(self):
        self.fx.write("node_modules/lib/index.js",
                      "StringManager.currentLanguage.screenTitle;\n")
        report = self._run()
        self.assertEqual({f.site for f in report.unused},
                         {"screen.title", "screen.help"})


class IosAndroidScanTests(unittest.TestCase):
    GROUPS = {"member_list": {"leave_button": "Leave", "title": "Members"}}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ios = VmFixture(Path(self._tmp.name) / "ios")
        self.android = VmFixture(Path(self._tmp.name) / "android")

    def tearDown(self):
        self._tmp.cleanup()

    def test_ios_accessor_and_localized_are_usage(self):
        self.ios.write("App/VM.swift",
                       "let a = StringManager.MemberList.leaveButton()\n"
                       'let b = "member_list_title".localized()\n')
        report = _usage(self.GROUPS, roots={"ios": self.ios.root})
        self.assertEqual(report.unused, [])

    def test_ios_unknown_accessor_is_not_reported(self):
        # A wrong accessor fails the Swift compile; reporting it here
        # would double up on the platform's own gate.
        self.ios.write("App/VM.swift",
                       "let a = StringManager.MemberList.leaveButton()\n"
                       "let x = StringManager.MemberList.typo()\n")
        report = _usage(self.GROUPS, roots={"ios": self.ios.root})
        self.assertEqual(report.missing, [])
        self.assertEqual([f.site for f in report.unused],
                         ["member_list.title"])

    def test_android_r_string_is_usage_and_foreign_symbols_are_ignored(self):
        self.android.write(
            "app/src/main/kotlin/VM.kt",
            "val a = stringResource(R.string.member_list_leave_button)\n"
            "val b = getString(R.string.app_name)\n")  # plain Android res
        report = _usage(self.GROUPS, roots={"android": self.android.root})
        self.assertEqual(report.missing, [])
        self.assertEqual(report.dynamic, [])
        self.assertEqual([f.site for f in report.unused],
                         ["member_list.title"])

    def test_ios_generated_string_manager_is_not_scanned(self):
        # The generated accessor file spells every key as
        # `"flat_key".localized()` — scanning it marks the whole table
        # used and the unused direction goes permanently blind.
        self.ios.write("App/StringManager.swift",
                       "public struct StringManager {\n"
                       "  public struct MemberList {\n"
                       '    public static func leaveButton() -> String { "member_list_leave_button".localized() }\n'
                       '    public static func title() -> String { "member_list_title".localized() }\n'
                       "  }\n"
                       "}\n")
        report = _usage(self.GROUPS, roots={"ios": self.ios.root})
        self.assertEqual({f.site for f in report.unused},
                         {"member_list.leave_button", "member_list.title"})

    def test_spec_branch_contract_string_refs_are_usage_and_checked(self):
        # validate can only check the SHAPE of `@key` — it does not know
        # where the strings table lives. Here it does, so a branch asserting
        # a key nothing declares is caught before the generated test runs.
        spec_dir = Path(self._tmp.name) / "specs"
        (spec_dir).mkdir()
        (spec_dir / "screen.spec.json").write_text(json.dumps({
            "branchContracts": {
                "methods": {
                    "onTap": {
                        "branches": [
                            {"when": {"data.x": True},
                             "then": {"data.msg": "@member_list_title"}},
                            {"when": {"data.x": False},
                             "then": {"data.msg": "@member_list_ghost"}},
                            {"when": {"data.y": True},
                             "then": {"data.msg": "@data.other"}},
                        ],
                    },
                },
            },
        }), encoding="utf-8")
        report = _usage(self.GROUPS, roots={}, spec_dir=spec_dir)
        self.assertEqual(1, len(report.missing))
        self.assertIn("member_list_ghost", report.missing[0].detail)
        # The declared key counts as usage; `@data.<field>` is not a key ref.
        self.assertEqual([f.site for f in report.unused],
                         ["member_list.leave_button"])

    def test_spec_pseudo_key_declared_by_a_harness_map_is_accepted(self):
        # The documented pattern for a formatted string: the branch asserts
        # a pseudo key and the harness formats the real table entry. It is
        # legal precisely because the harness declares it in a closed map.
        spec_dir = Path(self._tmp.name) / "specs"
        spec_dir.mkdir()
        (spec_dir / "screen.spec.json").write_text(json.dumps({
            "branchContracts": {
                "methods": {
                    "onTap": {
                        "branches": [
                            {"when": {"data.x": True},
                             "then": {"data.msg": "@member_list_step_1_of_3"}},
                        ],
                    },
                },
            },
        }), encoding="utf-8")
        self.ios.write(
            "Tests/ScreenBranchHarness.swift",
            "let SCREEN_BRANCH_STRING_KEYS: [String: String] = [\n"
            '    "member_list_step_1_of_3": "member_list_step_x_of_y",\n'
            "]\n")
        report = _usage(self.GROUPS, roots={"ios": self.ios.root},
                        spec_dir=spec_dir)
        self.assertEqual(
            [], [f for f in report.missing if "branchContracts" in f.detail]
        )

    def test_spec_without_branch_contracts_contributes_nothing(self):
        spec_dir = Path(self._tmp.name) / "specs"
        spec_dir.mkdir()
        (spec_dir / "screen.spec.json").write_text(
            json.dumps({"type": "screen_spec", "structure": {}}), encoding="utf-8")
        report = _usage(self.GROUPS, roots={}, spec_dir=spec_dir)
        self.assertEqual([], report.missing)

    def test_ios_raw_foundation_lookup_of_an_absent_key_is_reported(self):
        # NSLocalizedString compiles whatever it is handed and returns the
        # key when nothing resolves, so an absent key ships as a raw key on
        # screen. Reported from a consumer project where an error toast read
        # `subscription_usage_load_error` to real users.
        self.ios.write("App/VM.swift",
                       'showToast(NSLocalizedString("member_list_title", comment: ""))\n'
                       'showToast(NSLocalizedString("member_list_load_error", comment: ""))\n')
        report = _usage(self.GROUPS, roots={"ios": self.ios.root})
        self.assertEqual(1, len(report.missing))
        self.assertIn("member_list_load_error", report.missing[0].detail)
        self.assertIn("VM.swift:2", report.missing[0].site)
        # The declared key it did resolve counts as usage.
        self.assertEqual([f.site for f in report.unused],
                         ["member_list.leave_button"])

    def test_ios_key_carried_by_a_platform_catalog_is_not_missing(self):
        # A key may legitimately live in Localizable.strings rather than in
        # the JsonUI table; that possibility is why these references used to
        # be passed over entirely.
        self.ios.write("App/VM.swift",
                       'let a = NSLocalizedString("Disconnect", comment: "")\n')
        self.ios.write("App/ja.lproj/Localizable.strings",
                       '"Disconnect" = "切断";\n')
        report = _usage(self.GROUPS, roots={"ios": self.ios.root})
        self.assertEqual([], report.missing)

    def test_ios_string_localized_initializer_is_covered(self):
        self.ios.write("App/VM.swift",
                       'let a = String(localized: "member_list_ghost")\n')
        report = _usage(self.GROUPS, roots={"ios": self.ios.root})
        self.assertEqual(1, len(report.missing))
        self.assertIn("String(localized:)", report.missing[0].detail)

    def test_ios_localized_suffix_stays_usage_only(self):
        # The SwiftUI generator emits `"gone".localized()` for a
        # visibility sentinel — reporting unresolved ones here would flag
        # generated code that is not naming a key at all.
        self.ios.write("App/Data.swift",
                       'var visibility: String = "gone".localized()\n')
        report = _usage(self.GROUPS, roots={"ios": self.ios.root})
        self.assertEqual([], report.missing)

    def test_ios_xcstrings_catalog_is_read(self):
        self.ios.write("App/VM.swift",
                       'let a = NSLocalizedString("catalog_only", comment: "")\n')
        self.ios.write(
            "App/Localizable.xcstrings",
            '{"sourceLanguage":"en","strings":{"catalog_only":{}}}\n')
        report = _usage(self.GROUPS, roots={"ios": self.ios.root})
        self.assertEqual([], report.missing)

    def test_kotlin_string_keys_map_feeds_used(self):
        self.android.write(
            "app/src/main/kotlin/VM.kt",
            'val FIELD_STRING_KEYS = mapOf(\n'
            '  "a" to "member_list_title",\n'
            ')\n')
        report = _usage(self.GROUPS, roots={"android": self.android.root})
        self.assertEqual([f.site for f in report.unused],
                         ["member_list.leave_button"])


class AggregationTests(unittest.TestCase):
    """Memo ③: judge only after the union over every declared face."""

    GROUPS = {"screen": {"ios_only": "A", "web_only": "B"}}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ios = VmFixture(Path(self._tmp.name) / "ios")
        self.web = VmFixture(Path(self._tmp.name) / "web")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_key_used_by_any_face_is_not_unused(self):
        self.ios.write("A.swift",
                       "let a = StringManager.Screen.iosOnly()\n")
        self.web.write("b.ts",
                       "StringManager.currentLanguage.screenWebOnly;\n")
        report = _usage(
            self.GROUPS,
            roots={"ios": self.ios.root, "web": self.web.root},
        )
        self.assertEqual(report.unused, [])
        self.assertEqual(report.faces, ["layout", "ios", "web"])

    def test_judging_one_face_alone_would_have_killed_the_other_key(self):
        # The false positive the aggregation rule exists to prevent.
        self.ios.write("A.swift",
                       "let a = StringManager.Screen.iosOnly()\n")
        report = _usage(self.GROUPS, roots={"ios": self.ios.root})
        self.assertEqual([f.site for f in report.unused],
                         ["screen.web_only"])


class CollectFindingsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = ProjectFixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _enable_web(self):
        config = json.loads((self.fx.root / "jui.config.json").read_text())
        config["platforms"] = {"web": {"root": "web"}}
        (self.fx.root / "jui.config.json").write_text(json.dumps(config))
        (self.fx.root / "web").mkdir()

    def test_usage_is_off_by_default(self):
        self.fx.write_layout("login.json", {"type": "Label", "text": "title"})
        report = self.fx.collect()
        self.assertIsNone(report.usage)

    def test_usage_flag_reports_unwired_keys(self):
        # STRINGS declares login.title/greeting/items_count; the layout
        # references only title.
        self.fx.write_layout("login.json", {"type": "Label", "text": "title"})
        report = self.fx.collect(usage=True)
        self.assertIsNotNone(report.usage)
        self.assertEqual(
            {f.site for f in report.usage.unused},
            {"login.greeting", "login.items_count"},
        )
        self.assertFalse(report.clean)

    def test_config_key_opts_in_without_the_flag(self):
        config = json.loads((self.fx.root / "jui.config.json").read_text())
        config["lint"] = {"stringsUsage": True}
        (self.fx.root / "jui.config.json").write_text(json.dumps(config))
        self.fx.write_layout("login.json", {"type": "Label", "text": "title"})
        report = self.fx.collect()
        self.assertIsNotNone(report.usage)

    def test_clean_when_every_key_is_wired(self):
        self.fx.write_layout("login.json", {
            "type": "View",
            "child": [
                {"type": "Label", "text": "title"},
                {"type": "Label", "text": "greeting"},
                {"type": "Label", "text": "items_count"},
            ],
        })
        report = self.fx.collect(usage=True)
        self.assertEqual(report.usage.unused, [])
        self.assertTrue(report.clean)

    def test_declared_face_with_missing_root_is_a_setup_error(self):
        # A face that silently cannot be scanned shrinks the used set and
        # invents unused keys — refuse to run instead.
        config = json.loads((self.fx.root / "jui.config.json").read_text())
        config["platforms"] = {"web": {"root": "does-not-exist"}}
        (self.fx.root / "jui.config.json").write_text(json.dumps(config))
        self.fx.write_layout("login.json", {"type": "Label", "text": "title"})
        from jui_cli.commands.lint_strings_cmd import LintStringsSetupError
        with self.assertRaises(LintStringsSetupError):
            self.fx.collect(usage=True)

    def test_web_vm_usage_joins_the_union(self):
        self._enable_web()
        (self.fx.root / "web" / "vm.ts").write_text(
            "StringManager.currentLanguage.loginGreeting;\n"
            'StringManager.getString("login_items_count");\n',
            encoding="utf-8",
        )
        self.fx.write_layout("login.json", {"type": "Label", "text": "title"})
        report = self.fx.collect(usage=True)
        self.assertEqual(report.usage.unused, [])
        self.assertTrue(report.clean)


if __name__ == "__main__":
    unittest.main()
