"""Emitter tests: golden output, determinism, smoke checks, walkthrough.

Golden files live in ``tests/golden/attr_codegen/{swift,kotlin,ruby}`` and
were generated from ``mini_definitions.json`` (a fixture that exercises
every classification shape found in the real definitions file).

Smoke checks (``ruby -c`` / ``swiftc``) skip automatically when the tool
is not on PATH so the suite stays green on minimal machines.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from jui_cli.commands.generate_cmd import _cmd_generate_attr_bindings
from jui_cli.generators.attr_codegen import (
    kotlin_emitter,
    ruby_emitter,
    swift_emitter,
)
from jui_cli.generators.attr_codegen.model import (
    default_definitions_path,
    load_model,
)

GOLDEN_DIR = Path(__file__).parent / "golden" / "attr_codegen"
EMITTERS = {
    "swift": swift_emitter,
    "kotlin": kotlin_emitter,
    "ruby": ruby_emitter,
}


def _mini_model():
    return load_model(GOLDEN_DIR / "mini_definitions.json")


class GoldenTests(unittest.TestCase):
    """Small definitions input → expected code output, per emitter."""

    def _check_lang(self, lang: str):
        emitted = EMITTERS[lang].emit(_mini_model())
        golden_files = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted((GOLDEN_DIR / lang).iterdir())
        }
        self.assertEqual(sorted(emitted), sorted(golden_files))
        for name, content in emitted.items():
            self.assertEqual(
                content, golden_files[name], f"golden mismatch: {lang}/{name}"
            )

    def test_swift_golden(self):
        self._check_lang("swift")

    def test_kotlin_golden(self):
        self._check_lang("kotlin")

    def test_ruby_golden(self):
        self._check_lang("ruby")

    def test_every_emitted_file_has_generated_marker(self):
        for lang, emitter in EMITTERS.items():
            for name, content in emitter.emit(_mini_model()).items():
                self.assertIn("@generated", content, f"{lang}/{name}")


class ValueAliasFoldingTests(unittest.TestCase):
    """Declared value aliases fold into the canonical enum case."""

    VALUES = ("vertical", "horizontal", "flow", "Flow", "LeftAligned", "leftAligned")
    ALIASES = {"Flow": "flow", "LeftAligned": "flow", "leftAligned": "flow"}

    def test_enum_cases_fold_aliases_into_canonical_case(self):
        from jui_cli.generators.attr_codegen.swift_emitter import enum_cases

        cases = enum_cases(self.VALUES, lambda v: v.upper(), self.ALIASES)
        names = [name for name, _, _ in cases]
        self.assertEqual(names, ["VERTICAL", "HORIZONTAL", "FLOW"])
        flow = next(c for c in cases if c[0] == "FLOW")
        self.assertEqual(flow[1], "flow")  # canonical value
        self.assertEqual(set(flow[2]), {"flow", "Flow", "LeftAligned", "leftAligned"})

    def test_enum_ci_cases_route_alias_spellings_to_canonical(self):
        from jui_cli.generators.attr_codegen.swift_emitter import enum_ci_cases

        table = dict(enum_ci_cases(self.VALUES, lambda v: v.upper(), self.ALIASES))
        self.assertIn("leftaligned", table["FLOW"])
        self.assertIn("flow", table["FLOW"])

    def test_kotlin_collection_layout_has_no_leftaligned_member(self):
        # Against the real SSoT: the generated Layout enum folds the alias
        # spellings — LEFT_ALIGNED disappears as a member, the spelling is
        # still accepted and routes to FLOW.
        model = load_model()
        emitted = EMITTERS["kotlin"].emit(model)
        content = emitted["CollectionAttributes.kt"]
        self.assertNotIn("LEFT_ALIGNED", content)
        self.assertIn('"leftaligned" -> FLOW', content)

    def test_swift_collection_layout_routes_leftaligned_to_flow(self):
        model = load_model()
        emitted = EMITTERS["swift"].emit(model)
        content = emitted["CollectionAttributes.swift"]
        self.assertNotIn("leftAligned = ", content)
        self.assertIn('"leftaligned"', content)


class DeterminismTests(unittest.TestCase):
    def test_emitters_deterministic_on_real_definitions(self):
        model_a = load_model()
        model_b = load_model()
        for lang, emitter in EMITTERS.items():
            self.assertEqual(
                emitter.emit(model_a), emitter.emit(model_b), f"lang={lang}"
            )

    def test_cli_generates_identical_trees_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            outs = []
            for run in ("a", "b"):
                out = Path(tmp) / run
                rc = _cmd_generate_attr_bindings(
                    Namespace(lang="all", out=str(out), definitions=None)
                )
                self.assertEqual(rc, 0)
                outs.append(out)
            files_a = sorted(
                p.relative_to(outs[0]) for p in outs[0].rglob("*") if p.is_file()
            )
            files_b = sorted(
                p.relative_to(outs[1]) for p in outs[1].rglob("*") if p.is_file()
            )
            self.assertEqual(files_a, files_b)
            self.assertTrue(files_a)
            for rel in files_a:
                self.assertEqual(
                    (outs[0] / rel).read_bytes(),
                    (outs[1] / rel).read_bytes(),
                    f"non-deterministic: {rel}",
                )

    def test_cli_emits_skip_list_per_lang(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = _cmd_generate_attr_bindings(
                Namespace(lang="ruby", out=tmp, definitions=None)
            )
            self.assertEqual(rc, 0)
            payload = json.loads(
                (Path(tmp) / "skipped_attributes.json").read_text(encoding="utf-8")
            )
            skipped = {
                (e["component"], e["attribute"]) for e in payload["skipped"]
            }
            self.assertIn(("Collection", "onItemAppear"), skipped)
            self.assertIn(("common", "generatedBy"), skipped)


class SmokeCheckTests(unittest.TestCase):
    """Generated code parses/loads with the real toolchains when present."""

    @unittest.skipUnless(shutil.which("ruby"), "ruby not installed")
    def test_ruby_syntax_full_output(self):
        model = load_model()
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in ruby_emitter.emit(model).items():
                (Path(tmp) / name).write_text(content, encoding="utf-8")
            for rb in sorted(Path(tmp).glob("*.rb")):
                proc = subprocess.run(
                    ["ruby", "-c", str(rb)], capture_output=True, text=True
                )
                self.assertEqual(proc.returncode, 0, f"{rb.name}: {proc.stderr}")

    @unittest.skipUnless(shutil.which("ruby"), "ruby not installed")
    def test_ruby_runtime_extraction_semantics(self):
        """Load the generated modules and assert alias resolution,
        AttrValue wrapping (including :binding raw preservation), lenient
        enum matching, canonical_only, dimension, and the metadata API."""
        model = load_model()
        script = r"""
require_relative 'label_attributes'
require_relative 'slider_attributes'
include JsonUI::Generated

warnings = []
AttrWarnings.handler = ->(msg) { warnings << msg }

# NOTE: braces are required — a braceless trailing hash is interpreted as
# keyword arguments on Ruby >= 3.0 (extract takes the hash positionally).
out = LabelAttributes.extract({
  'text' => '@{title}',
  'alpha' => 0.5,
  'width' => 'matchParent',
  'height' => 120,
  'visibility' => 'bogus',
  'onClick' => '@{save}',
  'fontColor' => '#FF0000'
})

raise 'alias failed' unless out['opacity'].is_a?(AttrValue) && out['opacity'].value == 0.5
raise 'binding failed' unless out['text'].binding? && out['text'].binding_expression == 'title'
raise 'binding raw recover failed' unless out['text'].raw == '@{title}'
raise 'dimension keyword failed' unless out['width'].value == 'matchParent'
raise 'dimension number failed' unless out['height'].value == 120
# Lenient enums: unknown values warn but PASS THROUGH raw (never dropped).
raise 'enum unknown should pass through' unless out['visibility'].value == 'bogus'
raise 'warning hook not called' unless warnings.any? { |w| w.include?('common.visibility') }
# Binding-only: AttrValue with the @{} wrapper information preserved.
raise 'binding-only failed' unless out['onClick'].is_a?(AttrValue)
raise 'binding-only expr failed' unless out['onClick'].binding_expression == 'save'
raise 'binding-only raw failed' unless out['onClick'].raw == '@{save}'
raise 'color failed' unless out['fontColor'].is_a?(AttrValue) && out['fontColor'].value == '#FF0000'

# Binding-only Hash action objects are preserved, not dropped.
handler = { 'action' => 'link', 'url' => 'https://example.com' }
out = LabelAttributes.extract({ 'onClick' => handler })
raise 'action object dropped' unless out['onClick'].value == handler

# Lenient enums match case-insensitively without warning.
warnings.clear
out = LabelAttributes.extract({ 'textAlign' => 'left' })
raise 'ci enum failed' unless out['textAlign'].value == 'left'
raise 'ci enum warned' unless warnings.empty?

# canonical_only disables alias fallback (L1-normalized input).
out = SliderAttributes.extract({ 'minimumValue' => 5 }, canonical_only: true)
raise 'canonical_only failed' if out.key?('minimum')
out = SliderAttributes.extract({ 'minimumValue' => 5 })
raise 'alias fallback failed' unless out['minimum'].value == 5

# Metadata API: rows / declared? / alias_map.
raise 'declared? canonical failed' unless SliderAttributes.declared?('minimum')
raise 'declared? alias failed' unless SliderAttributes.declared?('minimumValue')
raise 'declared? common failed' unless SliderAttributes.declared?('opacity')
raise 'declared? undeclared failed' if SliderAttributes.declared?('customProp')
raise 'alias_map failed' unless SliderAttributes.alias_map['minimumValue'] == 'minimum'
raise 'rows failed' unless SliderAttributes.rows['minimum'][:kind] == :number
# `alpha` redirects to `opacity`. It used to be declared as its own row as
# well, which cancelled the redirect (alias_map skips a spelling that is
# also a declared attribute) — plan 49-E removed seven such self-cancelling
# declarations and added a guard test, so the redirect must now be live.
raise 'alias redirect failed' unless SliderAttributes.alias_map['alpha'] == 'opacity'
puts 'RUBY_RUNTIME_OK'
"""
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in ruby_emitter.emit(model).items():
                (Path(tmp) / name).write_text(content, encoding="utf-8")
            check = Path(tmp) / "runtime_check.rb"
            check.write_text(script, encoding="utf-8")
            proc = subprocess.run(
                ["ruby", str(check)], capture_output=True, text=True, cwd=tmp
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("RUBY_RUNTIME_OK", proc.stdout)

    @unittest.skipUnless(shutil.which("swiftc"), "swiftc not installed")
    def test_swift_parses(self):
        model = _mini_model()
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, content in swift_emitter.emit(model).items():
                p = Path(tmp) / name
                p.write_text(content, encoding="utf-8")
                paths.append(str(p))
            proc = subprocess.run(
                ["swiftc", "-parse", *paths], capture_output=True, text=True
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)


class WalkthroughTests(unittest.TestCase):
    """README walkthrough, automated: add one attribute to a temp copy of
    the real definitions → regenerate → it appears in all 3 languages."""

    def test_new_attribute_propagates_to_all_languages(self):
        with open(default_definitions_path(), "r", encoding="utf-8") as f:
            defs = json.load(f)
        defs["Label"]["walkthroughDemo"] = {
            "type": ["string", "binding"],
            "description": "Walkthrough demo attribute",
        }
        with tempfile.TemporaryDirectory() as tmp:
            defs_path = Path(tmp) / "attribute_definitions.json"
            with open(defs_path, "w", encoding="utf-8") as f:
                json.dump(defs, f, ensure_ascii=False)
            model = load_model(defs_path)

            swift = swift_emitter.emit(model)["LabelAttributes.swift"]
            self.assertIn(
                "public let walkthroughDemo: AttrValue<String>?", swift
            )

            kotlin = kotlin_emitter.emit(model)["LabelAttributes.kt"]
            self.assertIn("val walkthroughDemo: AttrValue<String>? = null", kotlin)

            ruby = ruby_emitter.emit(model)["label_attributes.rb"]
            self.assertIn(
                "{ name: 'walkthroughDemo', kind: :string, bindable: true }", ruby
            )


if __name__ == "__main__":
    unittest.main()
