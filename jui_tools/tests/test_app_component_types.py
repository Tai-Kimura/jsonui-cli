"""A project component named as a type synonym or an alias section is left as written by the layout normalizer.

A project component (``jui g converter``) is drawn by its own converter
whatever its spelling, and reads its attributes as the layout spells them.
Through 2.5.20 `jui build`'s normalizer read such a node as the synonym's or
the alias's section: an extension ``SeekBar``'s ``minValue`` was distributed
as ``minimum`` (Slider's) and the generated ``SeekBar()`` lost the binding on
all three platforms without a word; an extension ``EditText`` was distributed
as a ``TextField`` (ticket
jui-extension-component-named-as-type-synonym-validated-against-canonical).
The Ruby validators' half is pinned in each tool's
spec/core/project_component_named_as_a_type_synonym_spec.rb.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.build_cmd import _distribute_layouts
from jui_cli.core.app_component_types import (
    EXTENSION_DEFINITION_DIRS,
    app_component_types,
    project_app_component_types,
)
from jui_cli.core.config_manager import ConfigManager
from jui_cli.core.normalizer import AliasTable, Canonicalizer
from jui_cli.core.normalizer.alias_table import default_definitions_path, load_type_synonyms

_REPO = Path(__file__).resolve().parents[2]
_TOOL = {"ios": "sjui", "android": "kjui", "web": "rjui"}
_CONTROL = "ZzProjectControl"


def _ruby_extension_dirs(tool: str) -> set[str]:
    """The `File.join(Dir.pwd, ...)` paths of the tool's extension_definition_paths."""
    source = (_REPO / f"{tool}_tools" / "lib" / "core" / "attribute_validator.rb").read_text(encoding="utf-8")
    body = source[source.index("def extension_definition_paths"):]
    body = body[: body.index("\n      end\n")]
    found = set()
    for args in re.findall(r"File\.join\(Dir\.pwd,\s*([^)]*)\)", body):
        found.add("/".join(re.findall(r"'([^']+)'", args)))
    return found


def _spellings_and_definitions():
    definitions = json.loads(default_definitions_path().read_text(encoding="utf-8"))
    synonyms = load_type_synonyms()
    aliases = {k: v["_alias_of"] for k, v in definitions.items()
               if isinstance(v, dict) and isinstance(v.get("_alias_of"), str)}
    sections = {**{s: e["canonical"] for s, e in synonyms.items()}, **aliases}
    return sections, definitions


def _node(type_: str, section: dict) -> dict:
    """A node naming every alias spelling the section declares, and `bind`."""
    node = {"type": type_, "id": "x", "bind": "@{b}"}
    for spec in section.values():
        if isinstance(spec, dict) and isinstance(spec.get("aliases"), list):
            for alias in spec["aliases"]:
                node[alias] = "@{a}"
    return node


class ExtensionDirectoriesAreTheToolsTests(unittest.TestCase):
    def test_each_platform_reads_the_directories_its_tool_validator_reads(self):
        for platform, tool in _TOOL.items():
            with self.subTest(platform=platform):
                self.assertEqual(set(EXTENSION_DEFINITION_DIRS[platform]), _ruby_extension_dirs(tool))
                self.assertTrue(EXTENSION_DEFINITION_DIRS[platform])


class CanonicalizerLeavesTheProjectsOwnTypesTests(unittest.TestCase):
    def test_every_synonym_and_alias_section_is_left_as_the_control_is(self):
        sections, definitions = _spellings_and_definitions()
        self.assertGreater(len(sections), 50)
        table = AliasTable.from_file()
        own = Canonicalizer(table.with_app_types(list(sections) + [_CONTROL]))
        differ = []
        for spelling, canonical in sections.items():
            node = _node(spelling, definitions.get(canonical) or {})
            out, warnings = own.canonicalize(node, add_marker=False)
            control, control_warnings = own.canonicalize({**node, "type": _CONTROL}, add_marker=False)
            if out["type"] != spelling or {**out, "type": _CONTROL} != control \
                    or len(warnings) != len(control_warnings):
                differ.append(spelling)
        self.assertEqual(differ, [])

    def test_without_them_the_synonyms_and_aliases_are_read_as_before(self):
        """The control: a spelling no project registers is its section's."""
        table = AliasTable.from_file()
        plain = Canonicalizer(table)
        out, _ = plain.canonicalize({"type": "SeekBar", "id": "s", "minValue": 0}, add_marker=False)
        self.assertEqual(out, {"type": "SeekBar", "id": "s", "minimum": 0})
        out, _ = plain.canonicalize({"type": "EditText", "id": "e"}, add_marker=False)
        self.assertEqual(out["type"], "TextField")
        self.assertEqual(table.definition_key_for("ProgressBar"), "Progress")
        # the same table, asked with the project's types, leaves the original alone
        self.assertIsNot(table.with_app_types(["SeekBar"]), table)
        self.assertEqual(table.definition_key_for("SeekBar"), "Slider")
        self.assertIsNone(table.with_app_types(["SeekBar"]).definition_key_for("SeekBar"))


def _project(root: Path) -> ConfigManager:
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens/json",
        "layouts_directory": "docs/screens/layouts",
        "platforms": {
            "ios": {"root": "ios", "layoutsDir": "Layouts"},
            "android": {"root": "android", "layoutsDir": "app/src/main/assets/Layouts"},
            "web": {"root": "web", "layoutsDir": "src/Layouts"},
        },
    }), encoding="utf-8")
    layouts = root / "docs/screens/layouts"
    layouts.mkdir(parents=True)
    (layouts / "probe.json").write_text(json.dumps({
        "type": "View", "id": "root",
        "child": [{"type": "SeekBar", "id": "seek", "minValue": "@{seekMin}"},
                  {"type": "EditText", "id": "edit"}],
    }), encoding="utf-8")
    # SeekBar and EditText are the project's own on iOS only
    ext = root / "ios" / EXTENSION_DEFINITION_DIRS["ios"][1]
    ext.mkdir(parents=True)
    (ext / "SeekBar.json").write_text(json.dumps({"SeekBar": {"minValue": {"type": "number"}}}), encoding="utf-8")
    (ext / "EditText.json").write_text(json.dumps({"EditText": {}}), encoding="utf-8")
    (ext / "Broken.json").write_text("{", encoding="utf-8")  # skipped, as the validator skips it
    old = os.getcwd()
    os.chdir(root)
    try:
        return ConfigManager()
    finally:
        os.chdir(old)


class BuildDistributionTests(unittest.TestCase):
    def test_a_platform_that_has_the_component_gets_it_as_written(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            config_mgr = _project(root)
            platforms = config_mgr.load()["platforms"]
            args = argparse.Namespace(clean=False, ios_only=False, android_only=False, web_only=False)
            _distribute_layouts(config_mgr, platforms, args)

            ios = json.loads((root / "ios/Layouts/probe.json").read_text(encoding="utf-8"))
            self.assertEqual(ios["child"][0], {"type": "SeekBar", "id": "seek", "minValue": "@{seekMin}"})
            self.assertEqual(ios["child"][1]["type"], "EditText")
            # the control: a platform without the component reads the synonym as before
            android = json.loads((root / "android/app/src/main/assets/Layouts/probe.json").read_text(encoding="utf-8"))
            self.assertEqual(android["child"][0], {"type": "SeekBar", "id": "seek", "minimum": "@{seekMin}"})
            self.assertEqual(android["child"][1]["type"], "TextField")

            self.assertEqual(app_component_types("ios", root / "ios"), frozenset({"SeekBar", "EditText"}))
            self.assertEqual(app_component_types("web", root / "web"), frozenset())
            self.assertEqual(app_component_types("ios", None), frozenset())
            self.assertEqual(project_app_component_types(config_mgr), frozenset({"SeekBar", "EditText"}))


if __name__ == "__main__":
    unittest.main()
