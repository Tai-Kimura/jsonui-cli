"""A component spec and the screens that declare it, reconciled — both ways.

Ruled 2026-09-08. Two faces carried four component pages that no screen spec
declared: the pages were generated and nothing linked to them. Two other faces
carried the opposite — `customComponents` naming a `specFile` that does not
exist.

⚠️ The two directions are independent, and that is why both survived. A check
for one is silent on the other. The reporting lane found the first on its own
face; the delivery lane found the second on two different faces, hours later,
while measuring something else.

Ownership here does NOT come from where the declaration sits. A component's
users are the layouts that name it — a fact about the tree, not about the
declaration under test. That is what makes this checkable today, while the
same question for unit contracts is not: `target -> screen` has no
implementation at all (0 occurrences), so unit-contract ownership IS the
declaration position and a check on it would be circular and always green.

Severity follows the evidence, and the third case is the one worth naming:
without a layouts directory, "no layout uses it" and "nobody looked" produce
the same empty list, so the check says which question it could not answer
rather than assigning a severity it has no evidence for.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.cli import (
    _component_declaration_gaps, _component_sibling_dirs)


def _screen(name: str, spec_files: list[str] | None = None) -> dict:
    spec = {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": name, "name": "S", "displayName": "S",
                     "description": "A screen."},
        "structure": {
            "components": [{"type": "View", "id": "root", "description": "r"}],
            "layout": {"root": "root", "children": []},
        },
    }
    if spec_files:
        spec["structure"]["customComponents"] = [
            {"name": f.split(".")[0].title(), "specFile": f,
             "description": "c"} for f in spec_files
        ]
    return spec


def _component(name: str) -> dict:
    return {
        "type": "component_spec", "version": "1.0",
        "metadata": {"name": name, "displayName": name, "description": "c",
                     "category": "input"},
        "props": {},
        "structure": {"components": [{"type": "View", "id": "r",
                                      "description": "r"}],
                      "layout": {"root": "r", "children": []}},
    }


class _Face(unittest.TestCase):
    def face(self, *, components: dict[str, str] | None = None,
             declared: list[str] | None = None,
             layouts: dict[str, list[str]] | None = None,
             with_layouts_dir: bool = True):
        """components: file -> metadata.name. layouts: file -> names it mentions."""
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        specs = root / "docs" / "app" / "screens" / "json"
        specs.mkdir(parents=True)
        (specs / "s.spec.json").write_text(
            json.dumps(_screen("s", declared)), encoding="utf-8")
        comps = root / "docs" / "app" / "components" / "json"
        comps.mkdir(parents=True)
        for file_name, comp_name in (components or {}).items():
            (comps / file_name).write_text(
                json.dumps(_component(comp_name)), encoding="utf-8")
        if with_layouts_dir:
            lay = root / "docs" / "app" / "screens" / "layouts"
            lay.mkdir(parents=True)
            for lname, names in (layouts or {}).items():
                (lay / lname).write_text(
                    json.dumps({"type": "View",
                                "child": [{"type": n} for n in names]}),
                    encoding="utf-8")
        return specs

    def run_check(self, specs: Path):
        return _component_declaration_gaps(sorted(specs.rglob("*.spec.json")), specs)


class BothDirectionsAreChecked(_Face):

    def test_a_declaration_with_no_file_is_an_error(self):
        specs = self.face(components={}, declared=["picker.component.json"])
        errors, warnings = self.run_check(specs)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("does not exist", errors[0])
        self.assertEqual(warnings, [])

    def test_a_file_used_by_a_layout_and_declared_by_nobody_is_an_error(self):
        specs = self.face(
            components={"picker.component.json": "Picker"},
            declared=None,
            layouts={"booking.json": ["Picker"]})
        errors, warnings = self.run_check(specs)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("used by 1 layout", errors[0])
        self.assertIn("unreachable", errors[0])

    def test_a_file_no_layout_names_is_only_a_warning(self):
        # ⚠️ The arm that keeps this from being "always red on any unused
        # component". Nothing uses it, so nothing is broken yet — the page is
        # unreachable, which is worth saying and not worth failing on.
        specs = self.face(
            components={"picker.component.json": "Picker"},
            declared=None,
            layouts={"booking.json": ["SomethingElse"]})
        errors, warnings = self.run_check(specs)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("no layout", warnings[0])

    def test_with_no_layouts_directory_it_says_which_question_it_skipped(self):
        # "no layout uses it" and "nobody looked" produce the same empty list.
        # A severity assigned without the evidence for it is the line that is
        # always wrong — this file already refuses that shape twice over.
        specs = self.face(
            components={"picker.component.json": "Picker"},
            declared=None, with_layouts_dir=False)
        errors, warnings = self.run_check(specs)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("could not be checked", warnings[0])

    def test_a_declared_and_present_component_is_silent(self):
        # The control. The common shape must produce no line at all.
        specs = self.face(
            components={"picker.component.json": "Picker"},
            declared=["picker.component.json"],
            layouts={"booking.json": ["Picker"]})
        self.assertEqual(self.run_check(specs), ([], []))

    def test_one_direction_alone_would_miss_the_other(self):
        # Both defects at once, on one face: a declaration with no file AND a
        # file no one declares. A check written for either direction reports
        # one of these and is silent on the other — which is how both shipped.
        specs = self.face(
            components={"picker.component.json": "Picker"},
            declared=["missing.component.json"],
            layouts={"booking.json": ["Picker"]})
        errors, _ = self.run_check(specs)
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(any("does not exist" in e for e in errors))
        self.assertTrue(any("unreachable" in e for e in errors))


class TheFaceLayoutIsReadInOnePlace(_Face):

    def test_the_expected_shape_resolves_both_siblings(self):
        specs = self.face(components={"picker.component.json": "Picker"},
                          layouts={"booking.json": ["Picker"]})
        comps, layouts = _component_sibling_dirs(specs)
        self.assertIsNotNone(comps)
        self.assertIsNotNone(layouts)

    def test_an_unexpected_shape_gets_no_check_rather_than_a_wrong_one(self):
        # A project laid out differently must not be measured against this
        # tool's layout — the same reasoning that made the component link a
        # defect in the first place.
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        odd = root / "somewhere" / "else"
        odd.mkdir(parents=True)
        self.assertEqual(_component_sibling_dirs(odd), (None, None))


if __name__ == "__main__":
    unittest.main()
