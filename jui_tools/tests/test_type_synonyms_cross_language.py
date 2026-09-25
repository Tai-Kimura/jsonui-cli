"""Cross-language agreement guard for component-type → definition-key mapping.

Attribute validation runs in Ruby (``shared/core/attribute_validator_core.rb``,
mirrored into ``{s,k,r}jui_tools/lib/core/``) while L1 normalization and
deprecation warnings run in Python (``jui_cli/core/normalizer/alias_table.py``).
Both answer the same question — "which ``attribute_definitions.json`` section
validates a node of type X?" — from the same two files:

* ``shared/core/attribute_definitions.json``: each section is its own key, and
  a section that is an ``_alias_of`` pointer (EditText, Check, ...) resolves to
  its target;
* ``shared/core/type_synonyms.json``: every other accepted spelling, with its
  ``canonical`` section.

The expected mapping is derived from those files here, not written out: the
readers held hand-written copies until 2026-09-26, and this test held a fifth.
Each Ruby mirror is executed (subprocess) and compared entry by entry, as is
``AliasTable.definition_key_for``. Because every reader now reads the file, a
reader that stopped reading it — a hard-coded list that happens to agree
today — is caught by swapping the file for an edited copy and checking that
each reader's answers follow (``AuthoritySwapTests``).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.normalizer.alias_table import AliasTable, load_type_synonyms

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO_ROOT / "shared" / "core" / "attribute_definitions.json"
TYPE_SYNONYMS = REPO_ROOT / "shared" / "core" / "type_synonyms.json"

RUBY_IMPLEMENTATIONS = {
    "sjui_tools": "SjuiTools::Core::AttributeValidator",
    "kjui_tools": "KjuiTools::Core::AttributeValidator",
    "rjui_tools": "RjuiTools::Core::AttributeValidator",
}

def _definitions() -> dict:
    with open(DEFINITIONS, encoding="utf-8") as f:
        return json.load(f)


def expected_mapping(synonyms: dict[str, dict[str, str]]) -> dict[str, str]:
    """Every accepted spelling → the section that validates it, from the two
    files: sections to themselves (an ``_alias_of`` section to its target),
    synonyms to their ``canonical``."""
    table: dict[str, str] = {}
    for name, section in _definitions().items():
        if name in ("common", "_comment") or not isinstance(section, dict):
            continue
        table[name] = section.get("_alias_of", name)
    for spelling, entry in synonyms.items():
        table[spelling] = entry["canonical"]
    return table


#: A spelling no implementation knows: both sides must degrade it to
#: common-only validation (Ruby via identity + failed section lookup,
#: Python via ``None``).
UNKNOWN_TYPE = "DefinitelyNotAComponent"

RUBY_DRIVER = r"""
require 'json'
require ARGV[0]
validator = Object.const_get(ARGV[1]).allocate
# map_type_to_definition's component-alias hop (`_alias_of`) reads
# @definitions — allocate skips initialize, so inject the SSoT directly.
validator.instance_variable_set(:@definitions, JSON.parse(File.read(ARGV[3])))
validator.instance_variable_set(:@type_synonyms_path, ARGV[4]) if ARGV[4]
types = JSON.parse(ARGV[2])
puts JSON.generate(types.to_h { |t| [t, validator.send(:map_type_to_definition, t)] })
"""


def _ruby_available() -> bool:
    return shutil.which("ruby") is not None


def _ruby_mapping(tool_dir: str, const_name: str, types: list[str], synonyms: Path | None = None) -> dict[str, str]:
    source = REPO_ROOT / tool_dir / "lib" / "core" / "attribute_validator.rb"
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / "driver.rb"
        driver.write_text(RUBY_DRIVER, encoding="utf-8")
        proc = subprocess.run(
            [
                "ruby",
                str(driver),
                str(source),
                const_name,
                json.dumps(types),
                str(DEFINITIONS),
            ] + ([str(synonyms)] if synonyms else []),
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0:
        raise AssertionError(f"{tool_dir} driver failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


def _ssot_keys() -> set[str]:
    with open(DEFINITIONS, encoding="utf-8") as f:
        definitions = json.load(f)
    return {k for k in definitions if k not in ("common", "_comment")}


class TargetExistenceTests(unittest.TestCase):
    """Every mapping target must be a real SSoT section."""

    def test_synonym_targets_exist(self):
        missing = sorted({e["canonical"] for e in load_type_synonyms(TYPE_SYNONYMS).values()} - _ssot_keys())
        self.assertEqual(missing, [], "type_synonyms.json maps to nonexistent sections")

    def test_component_alias_sections_are_pure_pointers(self):
        """B1 invariant: an `_alias_of` section carries no attribute copies
        (that is the copy-paste drift the collapse removed), points at a
        real section, and the target is not itself an alias (one hop)."""
        with open(DEFINITIONS, encoding="utf-8") as f:
            definitions = json.load(f)
        alias_sections = {
            name: section
            for name, section in definitions.items()
            if isinstance(section, dict) and "_alias_of" in section
        }
        self.assertEqual(
            sorted(alias_sections),
            ["Check", "EditText", "Input", "Toggle"],
            "unexpected set of component-alias sections",
        )
        for name, section in alias_sections.items():
            with self.subTest(section=name):
                stray = sorted(k for k in section if not k.startswith("_"))
                self.assertEqual(
                    stray, [], f"{name} is an alias yet carries attribute copies"
                )
                target = section["_alias_of"]
                target_section = definitions.get(target)
                self.assertIsInstance(
                    target_section, dict, f"{name} points at missing '{target}'"
                )
                self.assertNotIn(
                    "_alias_of", target_section, f"{name} -> {target} chains aliases"
                )

    def test_synonym_keys_are_not_sections(self):
        """A synonym whose key is itself an SSoT section is dead code —
        ``definition_key_for`` exact-matches first, so the entry never fires
        and silently misrepresents the effective behavior."""
        shadowed = sorted(set(load_type_synonyms(TYPE_SYNONYMS)) & _ssot_keys())
        self.assertEqual(shadowed, [], "type_synonyms.json entries shadowed by exact match")

    def test_render_as_names_a_type(self):
        """``render_as`` is the type a renderer draws instead of the
        canonical one — a non-empty type name, never a section's own
        spelling (that is what the absence of ``render_as`` means)."""
        for spelling, entry in load_type_synonyms(TYPE_SYNONYMS).items():
            if "render_as" not in entry:
                continue
            with self.subTest(spelling=spelling):
                self.assertIsInstance(entry["render_as"], str)
                self.assertTrue(entry["render_as"])
                self.assertNotEqual(entry["render_as"], entry["canonical"])


    def test_implied_attributes_are_declared_on_the_canonical_section(self):
        """An entry's keys other than ``canonical`` / ``render_as`` are
        attributes the spelling means (HStack: ``orientation: horizontal``).
        Each must be declared on the canonical section, with a value its
        ``enum`` allows — a renderer adds it to the node as if written."""
        definitions = _definitions()
        implied = 0
        for spelling, entry in load_type_synonyms(TYPE_SYNONYMS).items():
            section = definitions[entry["canonical"]]
            for key, value in entry.items():
                if key in ("canonical", "render_as"):
                    continue
                implied += 1
                with self.subTest(spelling=spelling, attribute=key):
                    self.assertIn(key, section, f"{entry['canonical']} declares no `{key}`")
                    allowed = section[key].get("enum") if isinstance(section[key], dict) else None
                    if allowed is not None:
                        self.assertIn(value, allowed)
        self.assertGreater(implied, 0, "no implied attribute was checked")


class RubyAgreementTests(unittest.TestCase):
    """Each Ruby mirror answers what the two files say."""

    @classmethod
    def setUpClass(cls):
        if not _ruby_available():
            if os.environ.get("CI"):
                raise AssertionError(
                    "ruby is required in CI to run the cross-language guard"
                )
            raise unittest.SkipTest("ruby not installed")
        cls.expected = expected_mapping(load_type_synonyms(TYPE_SYNONYMS))
        types = sorted(cls.expected) + [UNKNOWN_TYPE]
        cls.actual = {
            tool: _ruby_mapping(tool, const, types)
            for tool, const in RUBY_IMPLEMENTATIONS.items()
        }

    def test_each_ruby_implementation_matches_the_canon(self):
        for tool, mapping in self.actual.items():
            diverging = {
                spelling: (mapping.get(spelling), expected_key)
                for spelling, expected_key in self.expected.items()
                if mapping.get(spelling) != expected_key
            }
            with self.subTest(tool=tool):
                self.assertEqual(
                    diverging,
                    {},
                    f"{tool} disagrees with the files (actual, expected)",
                )

    def test_unknown_type_degrades_to_common_only(self):
        ssot = _ssot_keys()
        for tool, mapping in self.actual.items():
            with self.subTest(tool=tool):
                self.assertNotIn(
                    mapping[UNKNOWN_TYPE],
                    ssot,
                    f"{tool} resolved an unknown type to a real section",
                )


class PythonAgreementTests(unittest.TestCase):
    """``definition_key_for`` answers what the two files say."""

    @classmethod
    def setUpClass(cls):
        cls.table = AliasTable.from_file(DEFINITIONS)
        assert not cls.table.is_empty(), "SSoT definitions failed to load"

    def test_python_matches_the_files(self):
        expected = expected_mapping(load_type_synonyms(TYPE_SYNONYMS))
        diverging = {
            spelling: (self.table.definition_key_for(spelling), expected_key)
            for spelling, expected_key in expected.items()
            if self.table.definition_key_for(spelling) != expected_key
        }
        self.assertEqual(
            diverging, {}, "alias_table disagrees with the files (actual, expected)"
        )

    def test_unknown_type_degrades_to_common_only(self):
        self.assertIsNone(self.table.definition_key_for(UNKNOWN_TYPE))

class AuthoritySwapTests(unittest.TestCase):
    """Every reader follows the file: with one entry changed and one added
    in a copy of it, each reader's answers change with them. Agreement with
    today's file cannot tell reading it from a hard-coded list that matches
    it; following an edit can."""

    PROBE = "ProbeSpellingOfLabel"

    @classmethod
    def setUpClass(cls):
        entries = load_type_synonyms(TYPE_SYNONYMS)
        cls.edited = dict(entries)
        cls.edited["Text"] = {"canonical": "TextView"}      # was Label
        cls.edited[cls.PROBE] = {"canonical": "Label"}      # new
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "type_synonyms.json"
        cls.path.write_text(json.dumps({"synonyms": cls.edited}), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_python_follows_the_file(self):
        table = AliasTable(_definitions(), load_type_synonyms(self.path))
        self.assertEqual(table.definition_key_for("Text"), "TextView")
        self.assertEqual(table.definition_key_for(self.PROBE), "Label")

    def test_ruby_follows_the_file(self):
        if not _ruby_available():
            if os.environ.get("CI"):
                raise AssertionError("ruby is required in CI to run the cross-language guard")
            raise unittest.SkipTest("ruby not installed")
        for tool, const in RUBY_IMPLEMENTATIONS.items():
            with self.subTest(tool=tool):
                mapping = _ruby_mapping(tool, const, ["Text", self.PROBE], self.path)
                self.assertEqual(mapping, {"Text": "TextView", self.PROBE: "Label"})


if __name__ == "__main__":
    unittest.main()
