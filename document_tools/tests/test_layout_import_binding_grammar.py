"""The spec-doc layout import reads bindings with the one grammar.

Ticket spec-doc-layout-import-reads-bindings-by-whole-value-only (ee,
2026-09-25): `_node_to_component` treated a value as a binding only when it was
wholly `@{...}` and took the text inside the braces as the variable's name —
`@{!isOn}` imported a variable `!isOn`, `@{a ?? 'x'}` one named `a ?? 'x'`,
`"Hi @{name}"` none at all (it went into `style`), and only seven event keys
were events. Now every occurrence is read by `jui_cli.core.layout_facts`
(the Ruby grammar's port, held to Ruby by `jui_tools/tests/test_layout_facts.py`):
the ROOTS it names become variables, and any `on` + capital key is an event.
"""
from __future__ import annotations

from jsonui_doc_cli.spec_doc.layout_importer import _extract_from_layout


def _imported(*children):
    result = _extract_from_layout({"type": "View", "id": "root", "child": list(children)})
    return ([v["name"] for v in result["uiVariables"]],
            [h["name"] for h in result["eventHandlers"]], result["components"])


def test_negation_and_defaults_import_the_root():
    variables, _, _ = _imported({"type": "Switch", "id": "s", "isOn": "@{!isEnabled}"},
                                {"type": "Label", "id": "t", "text": "@{title ?? 'untitled'}"})
    assert variables == ["isEnabled", "title"]


def test_paths_import_their_root():
    variables, _, _ = _imported({"type": "Label", "id": "t", "text": "@{user.profile.name}"},
                                {"type": "Label", "id": "u", "text": "@{items[0].title}"})
    assert variables == ["user", "items"]


def test_interpolation_imports_every_root_and_leaves_style():
    variables, _, components = _imported(
        {"type": "Label", "id": "t", "text": "Hi @{name}, you have @{count} of @{data.limit}",
         "fontSize": 12})
    assert variables == ["count", "name"]
    label = components[0]["children"][0]
    # Before: the whole text sat in `style` as a literal, and nothing was a binding.
    assert label["binding"] == {"text": "Hi @{name}, you have @{count} of @{data.limit}"}
    assert label["style"] == {"fontSize": 12}


def test_any_on_key_is_an_event():
    variables, events, _ = _imported(
        {"type": "Button", "id": "b", "onClick": "@{onTap}", "onDoubleTap": "@{onTwice}"})
    assert (variables, events) == ([], ["onTap", "onTwice"])


def test_control_a_plain_value_is_still_style():
    variables, events, _ = _imported({"type": "Label", "id": "t", "text": "no bindings @ here"})
    assert (variables, events) == ([], [])
