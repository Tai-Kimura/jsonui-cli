"""One vocabulary for glass shapes, across the repository boundary.

THE DEFECT THIS EXISTS FOR

The Swift library accepted ``rectangle``. No declaration ever defined it — it is
SwiftUI's type name, written into the library from the implementation's vocabulary
rather than from the SSoT. It survived three separate removals in one file because
each was found on its own, and nothing compared the library with the declaration.

Today the two agree, and nothing holds them in agreement: the generator's enum was
written by reading the library's list once, by hand. A property that is true by
coincidence has no defence, so it is pinned while it is still true.

WHY THIS IS A PYTHON TEST AND NOT AN RSPEC ONE

It was written first as rspec, under sjui_tools. Measured afterwards, that arm could
never run in CI, for three independent reasons: the ruby job checks out one
repository (no sibling at all), the env var the spec read was spelled without the
JSONUI_ prefix CI uses, and the sparse checkout stopped one directory short of the
file. A gate that always skips gates nothing, so the arm moved to the job that
already has the sibling — this one.

When the sibling is absent this SKIPS and says what was not compared. A cross-repo
arm that passes without the sibling reports agreement between one list and nothing.
"""

from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SSOT = REPO_ROOT / "shared" / "core" / "attribute_definitions.json"
CONVERTER = REPO_ROOT / "sjui_tools" / "lib" / "swiftui" / "views" / "base_view_converter.rb"


def _sibling_repo(env_var: str, name: str) -> Path | None:
    override = os.environ.get(env_var)
    if override:
        path = Path(override)
        return path if path.exists() else None
    path = REPO_ROOT.parent / name
    return path if path.exists() else None


_swift_repo = _sibling_repo("JSONUI_SWIFTJSONUI_PATH", "SwiftJsonUI")
GLASS_SWIFT = None
if _swift_repo:
    _candidate = (
        _swift_repo / "Sources" / "SwiftJsonUI" / "Classes" / "SwiftUI" / "SJUIGlass.swift"
    )
    GLASS_SWIFT = _candidate if _candidate.exists() else None


def _glass_declaration() -> dict:
    def walk(node):
        if isinstance(node, dict):
            if "glass" in node:
                return node["glass"]
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = walk(value)
                if found is not None:
                    return found
        return None

    return walk(json.loads(SSOT.read_text(encoding="utf-8"))) or {}


class GlassShapeVocabularyIsOneList(unittest.TestCase):
    """The declaration and the Swift library name the same shape spellings."""

    @unittest.skipUnless(
        GLASS_SWIFT is not None,
        "SwiftJsonUI checkout (or SJUIGlass.swift within it) not found — the "
        "library/declaration vocabulary comparison did NOT run",
    )
    def test_the_fixed_spellings_match(self) -> None:
        enum = _glass_declaration().get("properties", {}).get("shape", {}).get("enum")
        self.assertIsNotNone(enum, "the declaration carries no shape enum to compare against")

        source = GLASS_SWIFT.read_text(encoding="utf-8")
        listed = re.search(r"knownShapeSpellings\s*=\s*\[(.*?)\]", source, re.S)
        self.assertIsNotNone(listed, "knownShapeSpellings not found in SJUIGlass.swift")

        library = sorted(re.findall(r'"([^"]+)"', listed.group(1)))
        self.assertEqual(library, sorted(v.lower() for v in enum))

    @unittest.skipUnless(GLASS_SWIFT is not None, "SwiftJsonUI checkout not found")
    def test_both_sides_carry_the_parameterised_rounded_form(self) -> None:
        # `rounded(N)` carries a number, so it cannot be an enum member. It is declared
        # in prose and both sides read it from there.
        self.assertIn("rounded(n)", str(_glass_declaration().get("description", "")).lower())

        source = GLASS_SWIFT.read_text(encoding="utf-8")
        # ⚠️ The window is the isKnown FUNCTION, not the file: the same spelling also
        # appears in roundedRadius, so a file-wide search passes while isKnown uses a
        # different prefix. Measured — it did.
        is_known = re.search(r"static func isKnown\(shape:.*?\n    \}", source, re.S)
        self.assertIsNotNone(is_known, "isKnown not found in SJUIGlass.swift")
        self.assertIn('hasPrefix("rounded")', is_known.group(0))

    def test_the_derivation_reads_the_enum_and_the_glass_description_only(self) -> None:
        """WHERE the derivation reads, not only what it finds.

        The declaration's ``properties.shape.description`` carries the word
        ``rectangle`` in a historical note. That is harmless only because the
        derivation reads the enum and the ``glass`` description, never the
        per-property prose. Widening the scan turns the note back into vocabulary.

        No skip: this reads two files in THIS repository.
        """
        converter = CONVERTER.read_text(encoding="utf-8")
        # ⚠️ Every method in the chain, not just the entry point: a change one call
        # deeper passed an arm that inspected only declared_glass_shapes.
        for name in ("declared_glass_shapes", "from_enum", r"declares_rounded_form\?"):
            body = re.search(rf"def self\.{name}[^\w?].*?\n        end", converter, re.S)
            self.assertIsNotNone(body, f"{name} not found — the derivation chain changed shape")
            without_comments = "\n".join(
                line for line in body.group(0).splitlines() if not line.strip().startswith("#")
            )
            self.assertIsNone(
                re.search(r"properties.*description|description.*properties", without_comments, re.S),
                f"{name} reads per-property prose — the historical note becomes vocabulary",
            )

    def test_the_historical_note_the_guard_protects_against_is_still_there(self) -> None:
        note = str(
            _glass_declaration().get("properties", {}).get("shape", {}).get("description", "")
        )
        if not note:
            self.skipTest("the declaration carries no per-property shape description")
        self.assertIn(
            "rectangle",
            note.lower(),
            "the note lost the word, so the arm above lost its subject — check whether "
            "the derivation still needs guarding",
        )


if __name__ == "__main__":
    unittest.main()
