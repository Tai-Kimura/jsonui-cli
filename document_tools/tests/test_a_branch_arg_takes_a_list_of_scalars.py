"""`when arg.<name>` takes a list of plain scalars for a parameter that takes a
list — as branch-tests generation already did on every face.

Until 2.5.17 the gate (doc_validate_spec, and `generate spec` / `generate
html`, which refuse on its errors) took a scalar only, while generation passed
a list through and the test it wrote passed: a method whose input IS a list
(`types: [String]?`) had a working contract and no HTML. `when data.*` stays
scalar on purpose — a list pre-state goes in the branch's `baseline`, whole —
and its error now says so.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.spec_doc.html_generator import generate_spec_html
from jsonui_doc_cli.spec_doc.validator import SpecValidator


def _spec(when: dict) -> dict:
    return {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Inbox", "displayName": "Inbox", "description": "d", "layoutFile": "inbox"},
        "structure": {"components": [], "layout": {}},
        "dataFlow": {"viewModel": {
            "methods": [{"name": "applyFilter", "params": [{"name": "types", "type": "[String]?"}]}],
            "vars": [{"name": "tags", "type": "[String]"}],
        }},
        "stateManagement": {"uiVariables": []},
        "branchContracts": {"methods": {"applyFilter": {"branches": [{"when": when, "then": {"api": "none"}}]}}},
    }


def _errors(when: dict) -> list:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "inbox.spec.json"
        path.write_text(json.dumps(_spec(when)))
        result = SpecValidator().validate_file(path)
    return [(m.path, m.message) for m in result.errors if "branchContracts" in m.path]


class ABranchArgTakesAListOfScalars(unittest.TestCase):
    def test_a_list_of_scalars_is_accepted(self):
        self.assertEqual(_errors({"arg.types": ["notice", "promo"]}), [])

    def test_an_empty_list_is_accepted(self):
        self.assertEqual(_errors({"arg.types": []}), [])

    def test_control_a_scalar_is_accepted(self):
        self.assertEqual(_errors({"arg.types": "notice"}), [])

    def test_a_reference_inside_the_list_is_refused_by_position(self):
        errors = _errors({"arg.types": ["notice", "@data.tags"]})
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0][0].endswith("when.arg.types[1]"))
        self.assertIn("literal string", errors[0][1])

    def test_a_list_of_lists_and_a_list_of_objects_are_refused(self):
        for value in ([["notice"]], [{"kind": "notice"}]):
            errors = _errors({"arg.types": value})
            self.assertEqual(len(errors), 1, value)
            self.assertIn("list elements must be scalar literals", errors[0][1])

    def test_an_object_is_refused_with_the_reason(self):
        errors = _errors({"arg.types": {"kind": "notice"}})
        self.assertEqual(len(errors), 1)
        self.assertIn("or a list of them", errors[0][1])
        self.assertIn("iOS harness casts", errors[0][1])

    def test_a_data_list_stays_refused_and_names_the_baseline(self):
        errors = _errors({"data.tags": ["notice"]})
        self.assertEqual(len(errors), 1)
        self.assertIn("'baseline'", errors[0][1])

    def test_the_html_shows_the_list_as_written(self):
        html = generate_spec_html(_spec({"arg.types": ["notice"]}))
        self.assertIn("<code>arg.types</code> = <code>[&quot;notice&quot;]</code>", html)


if __name__ == "__main__":
    unittest.main()
