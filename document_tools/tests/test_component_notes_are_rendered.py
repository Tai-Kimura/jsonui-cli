"""A component spec's notes reach its HTML and Markdown pages.

The component schema (component_spec_schema.py) declares `notes` at 11 places:
the top level (a list), each section (props, slots, structure,
stateManagement, usage) and each row of props / slots / structure components /
internal states / exposed events. Until jsonui-cli 1.9.6 the component page
rendered none of them — a consumer's 146 note sentences, 0 on the page — while
the screen page renders its own (ticket
doc-component-html-drops-every-notes-field).

The arm is a conservation law: every note sentence of a spec with a note at
every declared place appears in the HTML and in the Markdown, once each — the
number written equals the number rendered.
"""
from __future__ import annotations

import html
import unittest

from jsonui_doc_cli.spec_doc.component_spec_schema import COMPONENT_SPEC_SCHEMA
from jsonui_doc_cli.spec_doc.html_generator import generate_component_html, generate_component_markdown


def _spec() -> tuple[dict, list[str]]:
    sentences: list[str] = []

    def note(where: str) -> str:
        text = f"Note sentence {len(sentences) + 1:02d} about the {where}."
        sentences.append(text)
        return text

    spec = {
        "type": "component_spec",
        "metadata": {"name": "NoteCard", "displayName": "Note card", "description": "A card with notes everywhere."},
        "props": {"items": [{"name": "title", "type": "String", "description": "The title.", "notes": note("title prop")}],
                  "notes": note("props section")},
        "slots": {"items": [{"name": "footer", "description": "The footer slot.", "notes": note("footer slot")}],
                  "notes": note("slots section")},
        "structure": {"components": [{"type": "Label", "id": "title_label", "description": "The title label.",
                                      "notes": note("title label")}],
                      "notes": note("structure section")},
        "stateManagement": {
            "internalStates": [{"name": "isOpen", "type": "Bool", "initialValue": False, "description": "Open or not.",
                                "notes": note("isOpen state")}],
            "exposedEvents": [{"name": "onTap", "parameters": [], "description": "Tapped.", "notes": note("onTap event")}],
            "notes": note("state section"),
        },
        "usage": {"example": "{}", "usedInScreens": ["home"], "notes": note("usage section")},
        "notes": [note("component, first"), note("component, second")],
    }
    return spec, sentences


def _declared_notes(schema: dict) -> int:
    """How many places the schema declares `notes` (the spec above must fill every one)."""
    count = 0

    def walk(node):
        nonlocal count
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict) and "notes" in props:
                count += 1
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return count


class ComponentNotesAreRendered(unittest.TestCase):
    def test_the_spec_fills_every_place_the_schema_declares_notes(self):
        spec, sentences = _spec()
        self.assertEqual(_declared_notes(COMPONENT_SPEC_SCHEMA), 11)
        # 11 places, the top-level list holding two
        self.assertEqual(len(sentences), 12)

    def test_every_note_reaches_the_html_once(self):
        spec, sentences = _spec()
        page = html.unescape(generate_component_html(spec))
        rendered = [s for s in sentences if page.count(s) == 1]
        self.assertEqual(len(rendered), len(sentences), [s for s in sentences if s not in rendered])

    def test_every_note_reaches_the_markdown_once(self):
        spec, sentences = _spec()
        page = generate_component_markdown(spec)
        rendered = [s for s in sentences if page.count(s) == 1]
        self.assertEqual(len(rendered), len(sentences), [s for s in sentences if s not in rendered])

    def test_control_the_description_was_already_rendered(self):
        spec, _ = _spec()
        self.assertIn("A card with notes everywhere.", html.unescape(generate_component_html(spec)))
        self.assertIn("A card with notes everywhere.", generate_component_markdown(spec))

    def test_a_section_with_only_notes_is_still_drawn(self):
        spec = {"metadata": {"name": "Bare", "displayName": "Bare", "description": "d"},
                "props": {"notes": "Only a props note."}, "structure": {"notes": "Only a structure note."}}
        for page in (html.unescape(generate_component_html(spec)), generate_component_markdown(spec)):
            self.assertIn("Only a props note.", page)
            self.assertIn("Only a structure note.", page)


if __name__ == "__main__":
    unittest.main()
