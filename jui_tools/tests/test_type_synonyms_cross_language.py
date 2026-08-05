"""Cross-language agreement guard for component-type → definition-key mapping.

Attribute validation runs in Ruby three times over (``{s,k,r}jui_tools/lib/
core/attribute_validator.rb`` — a deliberate three-way fork awaiting the
shared-gem consolidation) while L1 normalization and deprecation warnings
run in Python (``jui_cli/core/normalizer/alias_table.py``). All four readers
answer the same question — "which ``attribute_definitions.json`` section
validates a node of type X?" — and each source file carries a "keep in sync
manually" comment. This module is the machinery that comment wished for:

* ``UNIFIED_TABLE`` below is the agreed canon, spelled out once.
* Each Ruby implementation is executed (subprocess, same pattern as
  ``test_screen_index_cross_language.py``) and compared entry by entry.
* The Python ``AliasTable.definition_key_for`` is compared to the same canon.
* Every mapping target is checked against the SSoT definitions file, so a
  mapping to a nonexistent section (which silently degrades that type to
  common-only validation) can never reappear.

Touching any of the four type maps without updating the others — or this
table — fails the ``python-suite`` CI job.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.normalizer.alias_table import AliasTable, _TYPE_SYNONYMS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO_ROOT / "shared" / "core" / "attribute_definitions.json"

RUBY_IMPLEMENTATIONS = {
    "sjui_tools": "SjuiTools::Core::AttributeValidator",
    "kjui_tools": "KjuiTools::Core::AttributeValidator",
    "rjui_tools": "RjuiTools::Core::AttributeValidator",
}

#: The agreed spelling → definition-key canon. Keys cover every spelling any
#: of the four implementations recognises; values must all be real sections
#: of ``attribute_definitions.json``. Canonical names map to themselves so
#: the table doubles as the full accepted-spelling inventory.
UNIFIED_TABLE: dict[str, str] = {
    # text
    "Label": "Label", "Text": "Label",
    "TextField": "TextField",
    "TextView": "TextView", "MultiLineEditText": "TextView", "Textarea": "TextView",
    "Button": "Button",
    "IconLabel": "IconLabel",
    # images
    "Image": "Image", "ImageView": "Image", "Img": "Image",
    "NetworkImage": "NetworkImage", "NetworkImageView": "NetworkImage",
    # CircleImage is an Image with a circular clip, not a URL loader —
    # component_metadata.json Image.platformSpecific.swift.circleImage, and all
    # three factories route it to the Image converter (49-E, 2026-08-05).
    "CircleImage": "Image", "CircleImageView": "Image",
    "AsyncImage": "NetworkImage",
    # selection / input controls
    "SelectBox": "SelectBox", "Spinner": "SelectBox", "DatePicker": "SelectBox",
    "Select": "SelectBox", "Picker": "SelectBox",
    # component aliases (`_alias_of` pointer sections): resolved to the
    # canonical section by the alias hop in every implementation
    "Switch": "Switch", "Toggle": "Switch",
    "CheckBox": "CheckBox", "Checkbox": "CheckBox",
    "Check": "CheckBox",
    "EditText": "TextField", "Input": "TextField",
    "Radio": "Radio", "RadioButton": "Radio", "RadioGroup": "Radio",
    "Segment": "Segment", "SegmentedControl": "Segment",
    "TabLayout": "Segment", "TabGroup": "Segment",
    "Slider": "Slider", "SeekBar": "Slider", "Range": "Slider",
    "Progress": "Progress", "ProgressBar": "Progress",
    "Indicator": "Indicator", "ActivityIndicator": "Indicator", "Loading": "Indicator",
    # containers
    "View": "View", "LinearLayout": "View", "RelativeLayout": "View",
    "FrameLayout": "View", "HStack": "View", "VStack": "View", "ZStack": "View",
    "Div": "View", "Box": "View", "Container": "View", "Column": "View",
    "Row": "View", "ConstraintLayout": "View",
    "SafeAreaView": "SafeAreaView",
    "ScrollView": "ScrollView", "Scroll": "ScrollView",
    "Collection": "Collection", "CollectionView": "Collection",
    "RecyclerView": "Collection", "Table": "Collection", "TableView": "Collection",
    "List": "Collection", "Grid": "Collection", "LazyGrid": "Collection",
    "ListView": "Collection", "LazyColumn": "Collection",
    "TabView": "TabView",
    # decorations / misc
    "GradientView": "GradientView", "Gradient": "GradientView",
    "Blur": "Blur", "BlurView": "Blur",
    "Web": "Web", "WebView": "Web", "Iframe": "Web",
    "Embed": "Embed",
}

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
types = JSON.parse(ARGV[2])
puts JSON.generate(types.to_h { |t| [t, validator.send(:map_type_to_definition, t)] })
"""


def _ruby_available() -> bool:
    return shutil.which("ruby") is not None


def _ruby_mapping(tool_dir: str, const_name: str, types: list[str]) -> dict[str, str]:
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
            ],
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

    def test_unified_table_targets_exist(self):
        missing = sorted(set(UNIFIED_TABLE.values()) - _ssot_keys())
        self.assertEqual(missing, [], "UNIFIED_TABLE maps to nonexistent sections")

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

    def test_python_synonym_targets_exist(self):
        missing = sorted(set(_TYPE_SYNONYMS.values()) - _ssot_keys())
        self.assertEqual(missing, [], "_TYPE_SYNONYMS maps to nonexistent sections")

    def test_python_synonym_keys_are_not_sections(self):
        """A synonym whose key is itself an SSoT section is dead code —
        ``definition_key_for`` exact-matches first, so the entry never fires
        and silently misrepresents the effective behavior."""
        shadowed = sorted(set(_TYPE_SYNONYMS) & _ssot_keys())
        self.assertEqual(shadowed, [], "_TYPE_SYNONYMS entries shadowed by exact match")


class RubyAgreementTests(unittest.TestCase):
    """The three Ruby forks must implement the canon exactly."""

    @classmethod
    def setUpClass(cls):
        if not _ruby_available():
            if os.environ.get("CI"):
                raise AssertionError(
                    "ruby is required in CI to run the cross-language guard"
                )
            raise unittest.SkipTest("ruby not installed")
        cls.expected = dict(UNIFIED_TABLE)
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
                    f"{tool} disagrees with the canon (actual, expected)",
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
    """``definition_key_for`` must agree with the Ruby canon."""

    @classmethod
    def setUpClass(cls):
        cls.table = AliasTable.from_file(DEFINITIONS)
        assert not cls.table.is_empty(), "SSoT definitions failed to load"

    def test_python_matches_the_unified_table(self):
        diverging = {
            spelling: (self.table.definition_key_for(spelling), expected_key)
            for spelling, expected_key in UNIFIED_TABLE.items()
            if self.table.definition_key_for(spelling) != expected_key
        }
        self.assertEqual(
            diverging, {}, "alias_table disagrees with the canon (actual, expected)"
        )

    def test_unknown_type_degrades_to_common_only(self):
        self.assertIsNone(self.table.definition_key_for(UNKNOWN_TYPE))

if __name__ == "__main__":
    unittest.main()
