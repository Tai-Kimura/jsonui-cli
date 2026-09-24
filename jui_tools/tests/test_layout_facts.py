"""`layout_facts`: one reader of a screen's layout, and a binding grammar held to Ruby's.

Design §6.1 (P2.5). The ids come from the normalizer's L2 tree (styles, includes
with their id prefixes, the platform filter); the binding roots from a Python
port of `shared/core/binding_validator_core.rb`. The port is held by RUNNING
Ruby: one corpus — every conformance fixture layout, plus expressions written to
sit on the grammar's edges — goes through the Ruby validator's own
`extract_variables` (per `@{...}` occurrence, as its canonical rules scan them)
and through the Python port, and the root sets are compared file by file, both
directions. A transcription that agrees is not the proof; the two machines
agreeing on the same inputs is.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from jui_cli.core.layout_facts import expression_roots, layout_facts, value_roots

REPO = Path(__file__).resolve().parents[2]

#: Expressions on the grammar's edges: negation, defaults (with operators
#: inside the default literal), paths, indexes, keywords, numbers, ternaries,
#: comparisons, calls, and the cell item scope.
EDGE_EXPRESSIONS = [
    "isVisible", "!isVisible", "user.name", "items[0].title", "title ?? 'untitled'",
    "count ?? 0", "label ?? \"a ?? b\"", "flag ? 'visible' : 'gone'", "a == b",
    "total > 10 && enabled", "format(price, currency)", "data.name", "data.items[0]",
    "index", "true", "null", "3", "x.y.z", "_private", "$dollar", "a||b",
]


def _edge_layout() -> dict:
    children = [{"type": "Label", "id": f"l{i}", "text": f"@{{{expr}}}"}
                for i, expr in enumerate(EDGE_EXPRESSIONS)]
    children.append({"type": "Label", "id": "mixed",
                     "text": "Hi @{name}, you have @{count} of @{data.limit}"})
    return {"type": "View", "id": "root", "child": children}


_RUBY = r'''
require 'json'
require 'set'
require ARGV[0]
# allocate, not new: the core is abstract (platform profiles define platform_id),
# and extract_variables reads only its constants.
core = JsonUIShared::BindingValidatorCore.allocate
walk = lambda do |value, roots|
  case value
  when String
    value.scan(/@\{([^}]*)\}/).flatten.each do |inner|
      next if inner.strip.start_with?('data.')
      core.send(:extract_variables, inner).each { |v| roots << v }
    end
  when Hash then value.each_value { |v| walk.call(v, roots) }
  when Array then value.each { |v| walk.call(v, roots) }
  end
end
out = {}
ARGV[1..-1].each do |path|
  roots = Set.new
  walk.call(JSON.parse(File.read(path)), roots)
  out[path] = roots.to_a.sort
end
puts JSON.generate(out)
'''


class TheGrammar(unittest.TestCase):
    def test_edges(self):
        self.assertEqual(expression_roots("!isVisible"), {"isVisible"})
        self.assertEqual(expression_roots("items[0].title"), {"items"})
        self.assertEqual(expression_roots("label ?? \"a ?? b\""), {"label"})
        self.assertEqual(expression_roots("flag ? 'visible' : 'gone'"), {"flag"})
        self.assertEqual(expression_roots("total > 10 && enabled"), {"total", "enabled"})
        self.assertEqual(expression_roots("data.name"), set())
        self.assertEqual(expression_roots("index"), set())
        self.assertEqual(value_roots("Hi @{name}, you have @{count} of @{data.limit}"),
                         {"name", "count"})

    def test_not_a_binding_is_not_read(self):
        self.assertEqual(value_roots("plain {text} @ not a binding"), set())


class TheGrammarAgreesWithRuby(unittest.TestCase):
    def setUp(self):
        if shutil.which("ruby") is None:
            if os.environ.get("CI"):
                self.fail("ruby is required in CI to hold the port to the Ruby grammar")
            self.skipTest("ruby not installed")

    def _corpus(self, tmp: Path) -> list:
        # From the tree, not `git ls-files`: a copy of the checkout without its
        # `.git` (a worktree's `.git` is a file) listed nothing and failed the
        # corpus floor below rather than the grammar.
        files = sorted((REPO / "conformance/fixtures").rglob("*.layout.json"))
        edge = tmp / "grammar-edges-probe.json"
        edge.write_text(json.dumps(_edge_layout()), encoding="utf-8")
        return files + [edge]

    def test_every_file_the_same_roots_both_ways(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            files = self._corpus(Path(tmp))
            self.assertGreater(len(files), 100, "the corpus is the conformance fixtures")
            script = Path(tmp) / "roots.rb"
            script.write_text(_RUBY, encoding="utf-8")
            run = subprocess.run(
                ["ruby", str(script), str(REPO / "shared/core/binding_validator_core.rb"),
                 *map(str, files)], capture_output=True, text=True, timeout=300)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            ruby = {k: set(v) for k, v in json.loads(run.stdout).items()}
            python = {str(f): value_roots(json.loads(f.read_text(encoding="utf-8"))) for f in files}
            self.assertEqual(set(ruby), set(python))
            only_ruby = {k: ruby[k] - python[k] for k in ruby if ruby[k] - python[k]}
            only_python = {k: python[k] - ruby[k] for k in ruby if python[k] - ruby[k]}
            self.assertEqual((only_ruby, only_python), ({}, {}))
            # The control: the corpus exercises the grammar at all.
            with_roots = sum(1 for v in python.values() if v)
            self.assertGreater(with_roots, 50, with_roots)
            # By its exact path: conformance has fixtures whose names end the
            # same way, and matching on a suffix read one of them instead.
            edge = str(Path(tmp) / "grammar-edges-probe.json")
            self.assertEqual(ruby[edge], python[edge])
            self.assertIn("enabled", python[edge])


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TheFacts(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.layouts = self.root / "layouts"
        self.styles = self.root / "styles"
        self.styles.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _facts(self, spec, platform="web"):
        return layout_facts(spec, platform, layouts_dir=self.layouts, styles_dir=self.styles)

    def test_not_linked_is_said_not_guessed(self):
        _write(self.layouts / "home.json", {"type": "View", "id": "root"})
        facts = self._facts({"metadata": {"name": "home"}})
        self.assertEqual((facts.evaluated, facts.reason), (False, "layout not linked"))

    def test_a_missing_file_is_said(self):
        facts = self._facts({"metadata": {"layoutFile": "nowhere"}})
        self.assertEqual((facts.evaluated, facts.reason), (False, "layout file missing"))

    def test_ids_and_roots_through_an_include_with_its_prefix(self):
        _write(self.layouts / "home.json", {"type": "View", "id": "root", "child": [
            {"type": "Label", "id": "title", "text": "@{heading}", "hidden": "@{!isReady}"},
            {"include": "banner", "id": "top"}]})
        _write(self.layouts / "banner.json", {"type": "View", "id": "wrap", "child": [
            {"type": "Label", "id": "caption", "text": "@{caption}"}]})
        facts = self._facts({"metadata": {"layoutFile": "home"}})
        self.assertTrue(facts.evaluated, facts.reason)
        self.assertEqual(facts.ids, {"root", "title", "topWrap", "topCaption"})
        self.assertEqual(facts.binding_roots, {"heading", "isReady", "topCaption"})

    def test_a_missing_include_is_returned_not_dropped(self):
        _write(self.layouts / "home.json", {"type": "View", "id": "root", "child": [
            {"include": "gone", "id": "x"}, {"type": "Label", "id": "t", "text": "@{a}"}]})
        facts = self._facts({"metadata": {"layoutFile": "home"}})
        self.assertEqual((facts.evaluated, facts.unresolved_includes), (False, ["gone"]))
        self.assertEqual(facts.reason, "unresolved include: gone")
        self.assertEqual(facts.binding_roots, {"a"})   # what was readable is still read

    def test_the_platform_filter_applies(self):
        _write(self.layouts / "home.json", {"type": "View", "id": "root", "child": [
            {"type": "Label", "id": "web_only", "platform": "web", "text": "@{w}"},
            {"type": "Label", "id": "ios_only", "platform": "ios", "text": "@{i}"}]})
        web = self._facts({"metadata": {"layoutFile": "home"}}, "web")
        ios = self._facts({"metadata": {"layoutFile": "home"}}, "ios")
        self.assertIn("web_only", web.ids)
        self.assertNotIn("ios_only", web.ids)
        self.assertIn("ios_only", ios.ids)
        self.assertEqual((web.binding_roots, ios.binding_roots), ({"w"}, {"i"}))

    def test_cells_are_counted_and_not_read(self):
        _write(self.layouts / "list.json", {"type": "View", "id": "root", "child": [
            # A binding INSIDE the cell reference: a cell is another scope, so
            # reading into it would put `cellOnly` among the screen's roots —
            # the specimen the "cells are read" mutant is judged by.
            {"type": "Collection", "id": "rows",
             "cellClasses": [{"className": "RowCell", "title": "@{cellOnly}"}],
             "items": "@{rows}"},
            {"type": "Collection", "id": "sec", "sections": [
                {"cell": "item_cell", "header": "item_header"}], "items": "@{groups}"}]})
        facts = self._facts({"metadata": {"layoutFile": "list"}})
        self.assertEqual(facts.cells, 3)
        self.assertEqual(facts.binding_roots, {"rows", "groups"})


if __name__ == "__main__":
    unittest.main()
