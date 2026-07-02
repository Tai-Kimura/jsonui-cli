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
        AttrValue wrapping, enum unknown → nil + warning, dimension."""
        model = load_model()
        script = r"""
require_relative 'label_attributes'
include JsonUI::Generated

warnings = []
AttrWarnings.handler = ->(msg) { warnings << msg }

out = LabelAttributes.extract(
  'text' => '@{title}',
  'alpha' => 0.5,
  'width' => 'matchParent',
  'height' => 120,
  'visibility' => 'bogus',
  'onClick' => '@{save}',
  'fontColor' => '#FF0000'
)

raise 'alias failed' unless out['opacity'].is_a?(AttrValue) && out['opacity'].value == 0.5
raise 'binding failed' unless out['text'].binding? && out['text'].binding_expression == 'title'
raise 'dimension keyword failed' unless out['width'].value == 'matchParent'
raise 'dimension number failed' unless out['height'].value == 120
raise 'enum unknown should be dropped' if out.key?('visibility')
raise 'warning hook not called' unless warnings.any? { |w| w.include?('common.visibility') }
raise 'binding-only failed' unless out['onClick'] == 'save'
raise 'color failed' unless out['fontColor'].is_a?(AttrValue) && out['fontColor'].value == '#FF0000'
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
