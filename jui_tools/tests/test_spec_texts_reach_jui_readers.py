"""`{"md": ...}` prose references, as `jui` reads specs.

Resolved once, where each spec FILE is read (`shared/core/spec_texts.py`),
because a reference means "the paired texts file of the file I am written
in". Pinned here:

* `jui g converter` reads component specs through the same resolver, so a
  prop's texts-file description reaches the converter doc comment instead of
  being dropped for not being a string — and a spec with no reference still
  works with no PyYAML;
* the parent-spec merger keeps a `MarkdownText` note a `MarkdownText`
  (`str(v)` turned it back into a plain string, and the page stopped
  rendering it as Markdown);
* a sub-spec's reference is resolved against the SUB-SPEC's file only. The
  merged dict is handed to `extract_screen_spec` with the PARENT's path, and
  re-resolving it there let an unresolved sub-spec reference borrow a
  same-named key from the parent's texts file — silently, and wrong;
* the merger reports what it could not resolve, per file, so a reader of
  the merged view (test_tools) can refuse it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jui_cli.commands.generate_cmd import _cmd_generate_converter
from jui_cli.core import shared_core
from jui_cli.core.parent_spec_merger import ParentSpecMerger
from jui_cli.core.spec_extractor import extract_screen_spec

texts = shared_core.load("spec_texts")


class _Done:
    returncode = 0


class _NoModule:
    def __init__(self, *names):
        self.names = names

    def __enter__(self):
        self.saved = {n: sys.modules.get(n, _NoModule) for n in self.names}
        for n in self.names:
            sys.modules[n] = None

    def __exit__(self, *exc):
        for n, v in self.saved.items():
            if v is _NoModule:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = v


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str)
                        else json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path


class ConverterReadsThroughTheResolver(_Tmp):
    def _project(self, description, yaml_text=None):
        self.write("jui.config.json", {
            "component_spec_directory": "docs/components/json",
            "platforms": {"web": {"root": "web"}}})
        self.write("docs/components/json/meter.component.json", {
            "metadata": {"name": "Meter"},
            "props": {"items": [
                {"name": "scale", "type": "Int", "description": description}]},
        })
        if yaml_text is not None:
            self.write("docs/components/json/meter.texts.yaml", yaml_text)

    def _descriptions(self):
        args = argparse.Namespace(name=None, from_spec=None, all_specs=True,
                                  attributes=None, container=False,
                                  skip_existing=False, force=False)
        calls = []

        def fake_run(cmd, cwd=None, env=None):
            calls.append(cmd)
            return _Done()

        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with patch("subprocess.run", side_effect=fake_run):
                rc = _cmd_generate_converter(args)
        finally:
            os.chdir(cwd)
        self.assertEqual(0, rc)
        (cmd,) = calls
        opt = "--attribute-descriptions"
        return json.loads(cmd[cmd.index(opt) + 1]) if opt in cmd else {}

    def test_a_texts_file_description_reaches_the_converter(self):
        self._project({"md": "props.scale"},
                      "props:\n  scale: |\n    目盛りの数\n\n    - 0〜10\n")
        self.assertEqual({"scale": "目盛りの数\n\n- 0〜10\n"}, self._descriptions())

    def test_a_spec_without_references_needs_no_pyyaml(self):
        self._project("inline text")
        with _NoModule("yaml"):
            self.assertEqual({"scale": "inline text"}, self._descriptions())


class MergerKeepsMarkdown(_Tmp):
    def _merge(self, sub_notes, parent_notes=None):
        self.write("p/0.spec.json", {"type": "screen_spec",
                                     "metadata": {"name": "S0", "description": "s"},
                                     "notes": sub_notes})
        self.write("p/0.texts.yaml", "n: from the sub-spec\n")
        parent = {"type": "screen_parent_spec", "version": "1.0",
                  "metadata": {"name": "P", "description": "P."},
                  "subSpecs": [{"file": "p/0.spec.json", "name": "S0"}]}
        if parent_notes is not None:
            parent["notes"] = parent_notes
            self.write("p.texts.yaml", "pn: from the parent\n")
        path = self.write("p.spec.json", parent)
        return ParentSpecMerger().merge_from_file(path)

    def test_a_sub_spec_note_stays_markdown(self):
        notes = self._merge({"md": "n"}).spec["notes"]
        self.assertTrue(any(texts.is_markdown(n) for n in notes), notes)

    def test_a_parent_note_stays_markdown(self):
        notes = self._merge("plain", {"md": "pn"}).spec["notes"]
        self.assertTrue(texts.is_markdown(notes[0]), notes)


class SubSpecReferencesResolveAgainstTheirOwnFile(_Tmp):
    def _parent(self, sub_yaml=None):
        self.write("p/0.spec.json", {
            "type": "screen_spec", "metadata": {"name": "S0", "description": "s"},
            "dataFlow": {"repositories": [
                {"name": "Repo", "description": {"md": "repo"}, "methods": []}]}})
        if sub_yaml is not None:
            self.write("p/0.texts.yaml", sub_yaml)
        # The parent's own texts file happens to define the same key.
        self.write("p.texts.yaml", "repo: THE PARENT'S TEXT\n")
        return self.write("p.spec.json", {
            "type": "screen_parent_spec", "version": "1.0",
            "metadata": {"name": "P", "description": {"md": "repo"}},
            "subSpecs": [{"file": "p/0.spec.json", "name": "S0"}]})

    def _screen(self, parent_path):
        merged = ParentSpecMerger().merge_from_file(parent_path)
        return merged, extract_screen_spec(merged.spec, parent_path)

    def test_an_unresolved_sub_spec_reference_does_not_borrow_the_parents_key(self):
        _merged, screen = self._screen(self._parent())
        (repo,) = screen.repositories
        self.assertNotEqual("THE PARENT'S TEXT", repo.description)
        # The parent's own reference still resolves against the parent's file.
        self.assertEqual("THE PARENT'S TEXT", screen.description)

    def test_a_resolved_sub_spec_reference_keeps_the_sub_specs_text(self):
        _merged, screen = self._screen(self._parent("repo: the sub-spec's text\n"))
        (repo,) = screen.repositories
        self.assertEqual("the sub-spec's text", repo.description)

    def test_the_merger_names_what_it_could_not_resolve(self):
        merged, _screen = self._screen(self._parent())
        (error,) = merged.texts_errors
        self.assertIn("0.spec.json", error)
        self.assertIn("dataFlow.repositories[0].description", error)


if __name__ == "__main__":
    unittest.main()
