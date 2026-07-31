"""Tests for the attribute-coverage ratchet (`jui conformance coverage`).

The hole this closes: conformance compares each platform's screenshot against
that same platform's previous screenshot, so an attribute that no converter
reads renders blank, matches its blank baseline, and passes. `Button.image`
and `View.flexWrap` both survived every gate that way.

Covers:

- read detection across the forms converters actually use (bracket, alias
  helpers, dig/fetch/key?)
- platform / mode scoping, including UIKit's deliberate exclusion
- non-renderer attributes (metadata, structural) staying out of scope
- the ratchet in both directions: a new gap fails, a closed gap left in the
  ledger fails
- ledger determinism and reason preservation across regeneration
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import coverage


def _defs(**components) -> dict:
    return {"_comment": "test", **components}


class ScanReadsTests(unittest.TestCase):
    def _scan(self, source: str, filename: str = "converter.rb", defs: dict | None = None) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "lib"
            (root / "nested").mkdir(parents=True)
            (root / "nested" / filename).write_text(source, encoding="utf-8")
            return coverage.scan_reads(root, defs)

    def test_finds_bracket_reads_for_every_receiver(self):
        keys = self._scan(
            "attributes['a']\n@component['b']\njson_data['c']\njson['d']\nattrs['e']\n"
        )
        self.assertEqual({coverage.SHARED: {"a", "b", "c", "d", "e"}}, keys)

    def test_finds_both_names_of_an_alias_helper(self):
        # highlightColor/hilightColor is read through one call, not two lookups.
        keys = self._scan("attr_with_alias('highlightColor', 'hilightColor')")
        self.assertEqual({coverage.SHARED: {"highlightColor", "hilightColor"}}, keys)
        keys = self._scan("Core::Normalization.attr_lookup(json_data, 'a', 'b')")
        self.assertEqual({coverage.SHARED: {"a", "b"}}, keys)

    def test_finds_dig_fetch_and_key_predicate(self):
        keys = self._scan(
            "json_data.dig('x')\nattributes.fetch('y')\n@component.key?('z')\n"
        )
        self.assertEqual({coverage.SHARED: {"x", "y", "z"}}, keys)

    def test_ignores_non_ruby_files_and_missing_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "lib"
            root.mkdir()
            (root / "notes.md").write_text("attributes['ignored']", encoding="utf-8")
            self.assertEqual({}, coverage.scan_reads(root))
        self.assertEqual({}, coverage.scan_reads(Path(tmp) / "gone"))

    def test_component_files_own_their_reads(self):
        # A read in button_converter.rb credits Button, and ONLY Button —
        # the false-green this closes: Label.highlightColor reported
        # implemented on web because button_converter.rb read the name.
        defs = _defs(Button={"image": {"type": "string"}})
        keys = self._scan("attributes['image']", filename="button_converter.rb", defs=defs)
        self.assertEqual({"Button": {"image"}}, keys)

    def test_file_naming_quirks_normalize_to_the_component(self):
        defs = _defs(TextField={"text": {"type": "string"}})
        for name in ("text_field_converter.rb", "textfield_converter.rb", "textfield_component.rb"):
            keys = self._scan("attributes['text']", filename=name, defs=defs)
            self.assertEqual({"TextField": {"text"}}, keys, name)

    def test_unmapped_component_like_files_stay_shared(self):
        # SHARED satisfies every pair, so a mapping miss can only hide a gap
        # (the pre-pair-scan behaviour), never invent a false one.
        keys = self._scan("attributes['x']", filename="collection_stack_component.rb", defs=_defs())
        self.assertEqual({coverage.SHARED: {"x"}}, keys)


class ScopingTests(unittest.TestCase):
    def test_no_platform_field_means_every_platform(self):
        self.assertEqual(coverage.PLATFORMS, coverage.applicable_platforms({}))

    def test_platform_tag_narrows_and_keeps_canonical_order(self):
        self.assertEqual(("web",), coverage.applicable_platforms({"platform": "react"}))
        self.assertEqual(
            ("ios", "android"),
            coverage.applicable_platforms({"platform": ["kotlin", "swift"]}),
        )

    def test_uikit_mode_is_out_of_scope(self):
        # UIKit applies attributes in the SwiftJsonUI Swift runtime straight
        # off the layout JSON — no Ruby converter is expected to read them.
        self.assertEqual((), coverage.applicable_platforms({"mode": "uikit"}))
        self.assertEqual(
            (), coverage.applicable_platforms({"platform": "swift", "mode": "uikit"})
        )

    def test_unknown_platform_tokens_fail_loudly(self):
        # Silently dropping a token either shrinks the declared surface or
        # (all tokens unknown -> scope None) widens it to every platform.
        with self.assertRaises(ValueError):
            coverage.applicable_platforms({"platform": "web"})
        with self.assertRaises(ValueError):
            coverage.applicable_platforms({"platform": ["swift", "webb"]})

    def test_swiftui_and_compose_modes_narrow_to_their_platform(self):
        self.assertEqual(("ios",), coverage.applicable_platforms({"mode": "swiftui"}))
        self.assertEqual(("android",), coverage.applicable_platforms({"mode": "compose"}))

    def test_metadata_and_structural_attributes_are_not_renderer_attributes(self):
        self.assertFalse(coverage.in_scope("common", "type", {"type": "string"}))
        self.assertFalse(coverage.in_scope("common", "child", {"type": "array"}))
        self.assertFalse(coverage.in_scope("common", "$jui", {"type": "string"}))
        self.assertFalse(coverage.in_scope("View", "style", {"type": "string"}))

    def test_deprecated_attributes_are_not_gaps(self):
        self.assertFalse(
            coverage.in_scope("View", "old", {"type": "string", "deprecated": True})
        )

    def test_callbacks_stay_in_scope(self):
        # Hard to *fixture*, but a converter absolutely does read them.
        self.assertTrue(coverage.in_scope("View", "onClick", {"type": "string"}))


class FindGapsTests(unittest.TestCase):
    def test_reports_only_the_platforms_that_miss_the_attribute(self):
        defs = _defs(Button={"image": {"type": "string"}})
        gaps = coverage.find_gaps(
            defs,
            {
                "ios": {"Button": {"image"}},
                "android": {},
                "web": {coverage.SHARED: {"image"}},
            },
        )
        self.assertEqual(["Button.image [android]"], [str(g) for g in gaps])

    def test_platform_scoped_attribute_is_only_checked_there(self):
        defs = _defs(Button={"buttonType": {"type": "string", "platform": "react"}})
        gaps = coverage.find_gaps(defs, {"ios": {}, "android": {}, "web": {}})
        self.assertEqual(["Button.buttonType [web]"], [str(g) for g in gaps])

    def test_a_sibling_components_read_no_longer_satisfies_the_pair(self):
        # The filed bug: Label.highlightColor [web] closed because
        # button_converter.rb read the name.
        defs = _defs(
            Button={"highlightColor": {"type": "string"}},
            Label={"highlightColor": {"type": "string"}},
        )
        reads = {"ios": {"Button": {"highlightColor"}},
                 "android": {"Button": {"highlightColor"}},
                 "web": {"Button": {"highlightColor"}}}
        gaps = {str(g) for g in coverage.find_gaps(defs, reads)}
        self.assertEqual(
            {"Label.highlightColor [ios]", "Label.highlightColor [android]",
             "Label.highlightColor [web]"},
            gaps,
        )

    def test_alias_closure_lets_the_alias_named_file_serve_the_canonical(self):
        # sjui routes `Switch, Toggle` to toggle_converter.rb: the CANONICAL
        # component's reads live in the alias-named file.
        defs = _defs(
            Switch={"isOn": {"type": "boolean"}},
            Toggle={"_alias_of": "Switch", "isOn": {"type": "boolean"}},
        )
        reads = {"ios": {"Toggle": {"isOn"}},
                 "android": {"Toggle": {"isOn"}},
                 "web": {"Toggle": {"isOn"}}}
        self.assertEqual([], coverage.find_gaps(defs, reads))

    def test_common_attributes_are_satisfied_tree_wide(self):
        defs = _defs(common={"padding": {"type": "number"}})
        reads = {"ios": {"Button": {"padding"}},
                 "android": {coverage.SHARED: {"padding"}},
                 "web": {"Label": {"padding"}}}
        self.assertEqual([], coverage.find_gaps(defs, reads))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.defs = _defs(
            Button={
                "image": {"type": "string"},
                "hilightColor": {"type": "string"},
                "highlightColor": {"type": "string", "aliases": ["hilightColor"]},
            }
        )
        self.reads = {
            "ios": {coverage.SHARED: {"highlightColor"}},
            "android": {},
            "web": {},
        }

    def test_ledger_is_deterministic_and_sorted(self):
        gaps = coverage.find_gaps(self.defs, self.reads)
        first = coverage.render_ledger(gaps, definitions=self.defs)
        second = coverage.render_ledger(gaps, definitions=self.defs)
        self.assertEqual(first, second)
        doc = json.loads(first)
        names = [f"{e['component']}.{e['attribute']}" for e in doc["entries"]]
        self.assertEqual(sorted(names), names)
        self.assertEqual(coverage.SCHEMA_VERSION, doc["schemaVersion"])

    def test_platforms_are_merged_into_one_entry_in_canonical_order(self):
        gaps = coverage.find_gaps(self.defs, self.reads)
        doc = json.loads(coverage.render_ledger(gaps, definitions=self.defs))
        image = next(e for e in doc["entries"] if e["attribute"] == "image")
        self.assertEqual(["ios", "android", "web"], image["platforms"])

    def test_an_alias_is_classified_as_legacy_not_unimplemented(self):
        # L1 normalization rewrites an alias to its canonical spelling, so no
        # converter is ever expected to read one.
        gaps = coverage.find_gaps(self.defs, self.reads)
        doc = json.loads(coverage.render_ledger(gaps, definitions=self.defs))
        alias = next(e for e in doc["entries"] if e["attribute"] == "hilightColor")
        self.assertEqual("legacy", alias["reason"])
        image = next(e for e in doc["entries"] if e["attribute"] == "image")
        self.assertEqual("unimplemented", image["reason"])

    def test_regenerating_preserves_a_hand_set_reason_and_note(self):
        gaps = coverage.find_gaps(self.defs, self.reads)
        with tempfile.TemporaryDirectory() as tmp:
            path = coverage.coverage_path(tmp)
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "entries": [
                            {
                                "component": "Button",
                                "attribute": "image",
                                "platforms": ["ios", "android", "web"],
                                "reason": "platform-na",
                                "note": "decided in review",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            existing = coverage.load_ledger(path)
            doc = json.loads(
                coverage.render_ledger(gaps, existing=existing, definitions=self.defs)
            )
        image = next(e for e in doc["entries"] if e["attribute"] == "image")
        self.assertEqual("platform-na", image["reason"])
        self.assertEqual("decided in review", image["note"])

    def test_every_default_reason_is_a_known_reason(self):
        gaps = coverage.find_gaps(self.defs, self.reads)
        doc = json.loads(coverage.render_ledger(gaps, definitions=self.defs))
        for entry in doc["entries"]:
            self.assertIn(entry["reason"], coverage.REASONS)


class RatchetTests(unittest.TestCase):
    """`check()` must fail in both directions, never silently pass."""

    def _run(self, defs, sources, ledger_entries):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for platform, src in sources.items():
                d = root / coverage.SOURCE_ROOTS[platform]
                d.mkdir(parents=True)
                (d / "conv.rb").write_text(src, encoding="utf-8")
            conf = root / "conformance"
            conf.mkdir()
            coverage.coverage_path(conf).write_text(
                json.dumps({"schemaVersion": 1, "entries": ledger_entries}),
                encoding="utf-8",
            )
            return coverage.check(defs, root, conf)

    def test_a_recorded_gap_passes(self):
        result = self._run(
            _defs(Button={"image": {"type": "string"}}),
            {"ios": "", "android": "", "web": ""},
            [
                {
                    "component": "Button",
                    "attribute": "image",
                    "platforms": ["ios", "android", "web"],
                    "reason": "unimplemented",
                }
            ],
        )
        self.assertTrue(result.ok)
        self.assertEqual({"unimplemented": 3}, result.by_reason)

    def test_a_newly_declared_attribute_nobody_wired_up_fails(self):
        result = self._run(
            _defs(Button={"image": {"type": "string"}}),
            {"ios": "", "android": "", "web": ""},
            [],
        )
        self.assertFalse(result.ok)
        self.assertEqual(3, len(result.unrecorded))
        self.assertIn("Button.image [ios]", [str(g) for g in result.unrecorded])

    def test_closing_a_gap_without_dropping_its_entry_fails(self):
        # Otherwise the ledger rots into a list of things that used to be
        # broken, and stops meaning anything.
        result = self._run(
            _defs(Button={"image": {"type": "string"}}),
            {"ios": "attributes['image']", "android": "attributes['image']",
             "web": "attributes['image']"},
            [
                {
                    "component": "Button",
                    "attribute": "image",
                    "platforms": ["ios", "android", "web"],
                    "reason": "unimplemented",
                }
            ],
        )
        self.assertFalse(result.ok)
        self.assertEqual(3, len(result.stale))

    def test_an_entry_for_a_deleted_attribute_is_stale(self):
        result = self._run(
            _defs(Button={"text": {"type": "string"}}),
            {"ios": "attributes['text']", "android": "attributes['text']",
             "web": "attributes['text']"},
            [
                {
                    "component": "Button",
                    "attribute": "gone",
                    "platforms": ["web"],
                    "reason": "unimplemented",
                }
            ],
        )
        self.assertFalse(result.ok)
        self.assertEqual(["Button.gone [web]"], result.stale)

    def test_platform_filter_ignores_other_platforms_entirely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for platform in coverage.PLATFORMS:
                d = root / coverage.SOURCE_ROOTS[platform]
                d.mkdir(parents=True)
                (d / "conv.rb").write_text("", encoding="utf-8")
            (root / coverage.SOURCE_ROOTS["web"] / "conv.rb").write_text(
                "attributes['image']", encoding="utf-8"
            )
            conf = root / "conformance"
            conf.mkdir()
            coverage.coverage_path(conf).write_text(
                json.dumps({"schemaVersion": 1, "entries": []}), encoding="utf-8"
            )
            result = coverage.check(
                _defs(Button={"image": {"type": "string"}}), root, conf,
                platforms=("web",),
            )
        self.assertTrue(result.ok)


class RealRepositoryTests(unittest.TestCase):
    """The committed ledger must match the committed converters."""

    def test_repository_ledger_is_current(self):
        repo_root = Path(__file__).resolve().parents[2]
        definitions = json.loads(
            (repo_root / "shared" / "core" / "attribute_definitions.json").read_text(
                encoding="utf-8"
            )
        )
        result = coverage.check(definitions, repo_root, repo_root / "conformance")
        self.assertEqual(
            [], [str(g) for g in result.unrecorded],
            "unrecorded attribute gaps — run `jui conformance coverage --update`",
        )
        self.assertEqual(
            [], result.stale,
            "stale ledger entries — run `jui conformance coverage --update`",
        )

    def test_button_image_is_no_longer_a_gap(self):
        # The regression that motivated this check.
        repo_root = Path(__file__).resolve().parents[2]
        defs = json.loads(
            (repo_root / "shared" / "core" / "attribute_definitions.json").read_text(
                encoding="utf-8"
            )
        )
        reads = {
            p: coverage.scan_reads(repo_root / coverage.SOURCE_ROOTS[p], defs)
            for p in coverage.PLATFORMS
        }
        sources = coverage._readers_for("Button", defs)
        for platform in coverage.PLATFORMS:
            self.assertTrue(
                coverage._is_read("image", sources, reads[platform]), platform
            )
        self.assertTrue(
            coverage._is_read(
                "flexWrap", coverage._readers_for("View", defs), reads["web"]
            )
        )


if __name__ == "__main__":
    unittest.main()
