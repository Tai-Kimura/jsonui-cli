"""A `customComponents` entry has to say which file it means.

`customComponentRef` was the one `$defs` in the screen-spec schema with a
`required` list and no `_validate_*` counterpart, so its two required fields
were the only ones in that schema that nothing enforced. Probed 13
requirements across the schema against the hand-rolled validator: 11 were
caught, and both silent ones were here.

What made it worth a ticket rather than a footnote is what happened INSTEAD.
The batch reconciliation is keyed on `specFile`, so an entry carrying only a
`name` matches nothing, and the component spec on disk was then reported as
"declared by no screen spec" — while its declaration sat in that very list.
The advice was to add a declaration the author already had, so following it
exactly changed nothing and never reached the missing field.

The three arms that separate the cases come from the consumer face that hit
it. Arm 3 is the one this check exists for: before it, that case was silent.

    1  specFile present, spec on disk      → nothing (and must stay nothing)
    2  specFile absent, spec on disk       → was the wrong message; now names
                                             the missing field
    3  specFile absent, nothing on disk    → was COMPLETELY SILENT
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.cli import _component_declaration_gaps
from jsonui_doc_cli.spec_doc.validator import SpecValidator

BASE = {
    "type": "screen_spec",
    "version": "1.0",
    "metadata": {"name": "Auth", "displayName": "Auth", "description": "d",
                 "layoutFile": "auth"},
    "structure": {
        "components": [{"type": "Label", "id": "title", "description": "d"}],
        "layout": {"root": "View", "children": [{"id": "title"}]},
        "customComponents": [
            {"name": "HeaderMenu", "specFile": "headermenu.component.json",
             "description": "d"},
        ],
    },
}


def _errors(data):
    return [str(e) for e in SpecValidator().validate_data(copy.deepcopy(data), "s").errors]


class PerFileValidatorTests(unittest.TestCase):
    """Arm 3's home: the per-file check that was missing entirely."""

    def test_a_complete_entry_is_silent(self):
        # Arm 1. 39 entries across five consumer faces; exactly one was
        # incomplete, so a check that fires on the complete shape would be
        # wrong 38 times.
        self.assertEqual([], _errors(BASE))

    def test_a_missing_spec_file_is_named(self):
        d = copy.deepcopy(BASE)
        del d["structure"]["customComponents"][0]["specFile"]
        errs = _errors(d)
        self.assertEqual(1, len(errs), errs)
        self.assertIn("specFile", errs[0])
        self.assertIn("customComponents[0]", errs[0])

    def test_a_missing_name_is_named(self):
        d = copy.deepcopy(BASE)
        del d["structure"]["customComponents"][0]["name"]
        errs = _errors(d)
        self.assertEqual(1, len(errs), errs)
        self.assertIn("name", errs[0])

    def test_a_name_that_is_not_pascal_case_is_rejected(self):
        d = copy.deepcopy(BASE)
        d["structure"]["customComponents"][0]["name"] = "headerMenu"
        errs = _errors(d)
        self.assertTrue(any("PascalCase" in e for e in errs), errs)

    def test_a_spec_file_that_is_not_a_component_spec_is_rejected(self):
        # `.component.json` is what the reconciliation matches on; a value that
        # cannot match there is a declaration that will never link to anything.
        d = copy.deepcopy(BASE)
        d["structure"]["customComponents"][0]["specFile"] = "headermenu.json"
        errs = _errors(d)
        self.assertTrue(any("component.json" in e for e in errs), errs)

    def test_a_non_object_entry_does_not_crash_the_validator(self):
        d = copy.deepcopy(BASE)
        d["structure"]["customComponents"] = ["HeaderMenu"]
        errs = _errors(d)
        self.assertEqual(1, len(errs), errs)
        self.assertIn("must be an object", errs[0])


class ReconciliationMessageTests(unittest.TestCase):
    """Arm 2: the batch check now names the field instead of the wrong fact."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.face = Path(self._tmp.name) / "face"
        self.specs = self.face / "screens" / "json"
        self.comps = self.face / "components" / "json"
        self.layouts = self.face / "screens" / "layouts"
        for d in (self.specs, self.comps, self.layouts):
            d.mkdir(parents=True)
        (self.comps / "headermenu.component.json").write_text(
            json.dumps({"type": "component_spec",
                        "metadata": {"name": "HeaderMenu"}}), encoding="utf-8")
        (self.layouts / "auth.json").write_text(
            json.dumps({"type": "View", "children": [{"type": "HeaderMenu"}]}),
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_spec(self, entry):
        d = copy.deepcopy(BASE)
        d["structure"]["customComponents"] = [entry] if entry else []
        p = self.specs / "auth.spec.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        return [p]

    def test_a_declaration_with_a_spec_file_reconciles(self):
        errors, warnings = _component_declaration_gaps(
            self._write_spec({"name": "HeaderMenu",
                              "specFile": "headermenu.component.json"}),
            self.specs)
        self.assertEqual([], errors)
        self.assertEqual([], warnings)

    def test_a_name_only_declaration_names_the_missing_field(self):
        # ⚠️ This is the message that used to say "declared by no screen spec"
        # — true, and useless, because the fix it implies was already done.
        errors, warnings = _component_declaration_gaps(
            self._write_spec({"name": "HeaderMenu"}), self.specs)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("specFile", errors[0])
        self.assertIn("auth.spec.json", errors[0])
        # The actionable half: it says what to ADD and where. The old phrase
        # still appears in this message, but quoted as history rather than as
        # the finding — the assertion is on the instruction, not on the
        # absence of a string.
        self.assertIn('add "specFile"', errors[0])
        self.assertIn("give no", errors[0])

    def test_a_genuinely_undeclared_component_still_says_so(self):
        # The old message is still right when it IS right: nothing named this
        # component at all. Fixing the wrong case must not silence the case it
        # was originally written for.
        errors, warnings = _component_declaration_gaps(
            self._write_spec(None), self.specs)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("declared by no screen spec", errors[0])


class UnusedWordingTests(unittest.TestCase):
    """A component nothing links to is not a component nothing uses.

    A docs-site face read the earlier wording as "unused" and came close to
    deleting a live component: it was rendered by another COMPONENT, and this
    check only ever searched layouts. The claim's range has to match the
    window that was searched.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.face = Path(self._tmp.name) / "face"
        self.specs = self.face / "screens" / "json"
        self.comps = self.face / "components" / "json"
        self.layouts = self.face / "screens" / "layouts"
        for d in (self.specs, self.comps, self.layouts):
            d.mkdir(parents=True)
        (self.comps / "search.component.json").write_text(
            json.dumps({"type": "component_spec",
                        "metadata": {"name": "Search"}}), encoding="utf-8")
        (self.layouts / "auth.json").write_text(
            json.dumps({"type": "View"}), encoding="utf-8")
        d = copy.deepcopy(BASE)
        d["structure"]["customComponents"] = []
        (self.specs / "auth.spec.json").write_text(json.dumps(d), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_warning_says_only_layouts_were_searched(self):
        errors, warnings = _component_declaration_gaps(
            [self.specs / "auth.spec.json"], self.specs)
        self.assertEqual([], errors)
        self.assertEqual(1, len(warnings), warnings)
        self.assertIn("COMPONENT", warnings[0])
        self.assertIn("not a finding that it is unused", warnings[0])
