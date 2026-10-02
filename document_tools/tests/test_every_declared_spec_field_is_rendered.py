"""Every string field a spec schema declares reaches the generated page, or is
named here with the reason it does not.

A conservation law over the schema itself: every declared string leaf
(`$ref` resolved, one array item, the first object / string / array
alternative of a `oneOf`) is filled with a token of its own, the spec is
rendered, and the tokens are searched in the page (HTML unescaped). For the
HTML and for the Markdown, of the component page and of the screen page:

    declared string leaves == rendered + NOT_RENDERED (reasons below)

and nothing in NOT_RENDERED is rendered (a stale exemption fails too). A
field added to a schema is therefore red until a generator draws it or it is
named here. Enum / boolean / number leaves cannot carry a token and are not
counted (an enum's first value, a fixed boolean / number, fills them).

Until jsonui-cli 1.9.6 the component page drew 20 of its 44 string fields
(none of its 11 notes), the screen page 121 (HTML) / 114 (Markdown) of 170
(tickets doc-component-html-drops-every-notes-field and the two filed from it).
"""
from __future__ import annotations

import html
import unittest

from jsonui_doc_cli.spec_doc.component_spec_schema import COMPONENT_SPEC_SCHEMA
from jsonui_doc_cli.spec_doc.html_generator import (
    generate_component_html, generate_component_markdown, generate_spec_html,
)
from jsonui_doc_cli.spec_doc.markdown_generator import generate_spec_markdown
from jsonui_doc_cli.spec_doc.screen_spec_schema import SCREEN_SPEC_SCHEMA

#: Declared and deliberately not drawn on the page, each with its reason.
BOOKKEEPING = "spec-file bookkeeping, not a statement about the screen or component (_SUB_SPEC_BOOKKEEPING)"
COMPONENT_NOT_RENDERED = {
    "$schema": BOOKKEEPING,
    "type": BOOKKEEPING,
    "version": BOOKKEEPING,
}
SCREEN_NOT_RENDERED = {
    "$schema": BOOKKEEPING,
    "type": BOOKKEEPING,
    "version": BOOKKEEPING,
    "metadata.group": "declared as the screen's group on the flow diagram; `jsonui-doc generate mermaid` draws it, not the page",
}


def _probe(schema: dict) -> tuple[dict, dict[str, str]]:
    defs = schema.get("$defs") or schema.get("definitions") or {}
    tokens: dict[str, str] = {}

    def resolve(node):
        while isinstance(node, dict) and "$ref" in node:
            node = defs[node["$ref"].split("/")[-1]]
        return node

    def fill(node, path: str, depth: int):
        node = resolve(node)
        if depth > 12 or not isinstance(node, dict):
            return None
        if "enum" in node:
            return node["enum"][0]
        alternatives = node.get("oneOf") or node.get("anyOf")
        if alternatives and "type" not in node:
            for alt in alternatives:
                if resolve(alt).get("type") in ("object", "string", "array"):
                    return fill(alt, path, depth + 1)
            return fill(alternatives[0], path, depth + 1)
        kind = node.get("type")
        if isinstance(kind, list):
            kind = "string" if "string" in kind else kind[0]
        if kind == "object" or "properties" in node:
            out = {}
            for key, sub in (node.get("properties") or {}).items():
                value = fill(sub, f"{path}.{key}" if path else key, depth + 1)
                if value is not None:
                    out[key] = value
            return out
        if kind == "array":
            item = fill(node.get("items", {"type": "string"}), path + "[]", depth + 1)
            return [] if item is None else [item]
        if kind in ("boolean", "integer", "number"):
            return {"boolean": True, "integer": 1, "number": 1}[kind]
        token = f"zqtok{len(tokens) + 1:04d}zq"
        tokens[token] = path
        return token

    return fill(schema, "", 0), tokens


def _top(path: str) -> str:
    """The exemption key a leaf answers to: its path without array marks."""
    return path.replace("[]", "")


class EveryDeclaredSpecFieldIsRendered(unittest.TestCase):
    def check(self, schema: dict, renderers: dict, exempt: dict[str, str]) -> None:
        spec, tokens = _probe(schema)
        self.assertGreater(len(tokens), 20, "the probe filled the schema")
        declared = {_top(p) for p in tokens.values()}
        self.assertEqual(set(exempt) - declared, set(), "an exemption names no declared field")
        for name, render in renderers.items():
            page = html.unescape(render(spec))
            rendered = {_top(p) for t, p in tokens.items() if t in page}
            missing = {_top(p) for t, p in tokens.items() if t not in page}
            with self.subTest(page=name):
                self.assertEqual(sorted(missing - set(exempt)), [], f"{name}: declared and not drawn")
                self.assertEqual(sorted(rendered & set(exempt)), [], f"{name}: exempt but drawn")
                self.assertEqual(len(tokens), sum(1 for t in tokens if t in page)
                                 + sum(1 for p in tokens.values() if _top(p) in exempt))

    def test_component_page(self):
        self.check(COMPONENT_SPEC_SCHEMA,
                   {"html": generate_component_html, "markdown": generate_component_markdown},
                   COMPONENT_NOT_RENDERED)

    def test_screen_page(self):
        self.check(SCREEN_SPEC_SCHEMA,
                   {"html": generate_spec_html, "markdown": generate_spec_markdown},
                   SCREEN_NOT_RENDERED)


if __name__ == "__main__":
    unittest.main()
