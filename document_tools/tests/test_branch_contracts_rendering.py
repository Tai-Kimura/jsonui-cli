"""Tests for branchContracts decision-table rendering (HTML + Markdown).

P1 value proposition: the declared branch table becomes a machine-validated
document. Note branches must stay visible and counted — never silently
dropped from the rendered doc.
"""
from __future__ import annotations

import unittest

from jsonui_doc_cli.spec_doc.html_generator import generate_spec_html
from jsonui_doc_cli.spec_doc.markdown_generator import generate_spec_markdown


def _spec(branch_contracts=None):
    spec = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {
            "name": "Checkout",
            "displayName": "Checkout",
            "description": "Checkout confirmation screen.",
        },
        "structure": {
            "components": [
                {"type": "View", "id": "root", "description": "root"},
            ],
            "layout": {"root": "root", "children": []},
        },
    }
    if branch_contracts is not None:
        spec["branchContracts"] = branch_contracts
    return spec


_CONTRACT = {
    "conditions": {
        "needsPayment": {
            "meaning": "an amount is due now",
            "witness_true": {"payNowAmount": 1000},
            "witness_false": {"payNowAmount": 0},
        },
    },
    "methods": {
        "onConfirmTap": {
            "baseline": {"isAgreed": True},
            "branches": [
                {"when": {"data.isAgreed": False}, "then": {"api": "none"}},
                {"when": {"api.confirmBooking": "success"},
                 "then": {"transition": "complete"},
                 "notes": "happy path"},
                {"note": "3DS polling is out of v1 scope"},
            ],
        },
    },
    "notes": "vocabulary is closed by design",
}


class HtmlRendering(unittest.TestCase):
    def test_no_section_without_contracts(self):
        html = generate_spec_html(_spec())
        self.assertNotIn('id="branch-contracts"', html)

    def test_section_renders_tables_and_counts(self):
        html = generate_spec_html(_spec(_CONTRACT))
        self.assertIn('id="branch-contracts"', html)
        self.assertIn("Branch Contracts", html)
        # Summary counts: 1 method, 2 declared, 1 note-only.
        self.assertIn("1 method(s)", html)
        self.assertIn("2 declared branch(es)", html)
        self.assertIn("1 note-only branch(es)", html)
        # Named condition with witnesses.
        self.assertIn("needsPayment", html)
        self.assertIn("an amount is due now", html)
        self.assertIn("payNowAmount", html)
        # Method table with baseline and rows.
        self.assertIn("onConfirmTap", html)
        self.assertIn("Baseline:", html)
        self.assertIn("data.isAgreed", html)
        self.assertIn("api.confirmBooking", html)
        self.assertIn("happy path", html)
        # Note branch stays visible and is labeled as not machine-checked.
        self.assertIn("not machine-checked", html)
        self.assertIn("3DS polling is out of v1 scope", html)
        # Section-level notes.
        self.assertIn("vocabulary is closed by design", html)

    def test_values_are_json_rendered_and_escaped(self):
        contract = {
            "methods": {
                "onTap": {
                    "branches": [
                        {"when": {"data.mode": "a<b"},
                         "then": {"data.errorMessage": "@key_one"}},
                    ],
                },
            },
        }
        html = generate_spec_html(_spec(contract))
        self.assertIn("&quot;a&lt;b&quot;", html)
        self.assertIn("@key_one", html)


class MarkdownRendering(unittest.TestCase):
    def test_no_section_without_contracts(self):
        md = generate_spec_markdown(_spec())
        self.assertNotIn("## Branch Contracts", md)

    def test_section_renders_tables_and_counts(self):
        md = generate_spec_markdown(_spec(_CONTRACT))
        self.assertIn("## Branch Contracts", md)
        self.assertIn("2 declared branch(es)", md)
        self.assertIn("1 note-only branch(es)", md)
        self.assertIn("### Named Conditions", md)
        self.assertIn("`needsPayment`", md)
        self.assertIn("### `onConfirmTap`", md)
        self.assertIn("**Baseline:**", md)
        self.assertIn("`data.isAgreed`", md)
        self.assertIn("not machine-checked", md)
        self.assertIn("3DS polling is out of v1 scope", md)


if __name__ == "__main__":
    unittest.main()
