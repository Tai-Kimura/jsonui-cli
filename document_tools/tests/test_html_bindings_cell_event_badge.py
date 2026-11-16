"""The spec HTML's binding cell tells events from data with the importer's rule.

Ticket doc-html-generator-event-badge-uses-a-closed-hand-list:
`_render_bindings_cell` decided "event" by membership in a hand list of eleven
keys, so every other event — onLoadFailed, onPan, onPinch, onItemAppear — was
drawn with the two-way ``bind ↔`` badge. The layout importer that fills
`comp["binding"]` already reads any `on` + capital key as an event; the cell
now asks the same pattern.
"""
from __future__ import annotations

import re

import pytest

from jsonui_doc_cli.spec_doc import html_generator, layout_importer
from jsonui_doc_cli.spec_doc.html_generator import _render_bindings_cell
from jsonui_doc_cli.spec_doc.layout_importer import _extract_from_layout


def _badges(binding: dict) -> dict[str, str]:
    """key -> 'event' | 'bind', read back from the rendered HTML."""
    cell = _render_bindings_cell({"binding": binding})
    found = re.findall(r'bind-(event|data)">(?:event|bind)</span> <code>([^<]+)</code>', cell)
    assert len(found) == len(binding), cell
    return {key: ("event" if kind == "event" else "bind") for kind, key in found}


@pytest.mark.parametrize("key", ["onLoadFailed", "onPan", "onPinch", "onItemAppear"])
def test_an_event_the_old_list_did_not_name_is_an_event(key):
    assert _badges({key: "handler"}) == {key: "event"}


@pytest.mark.parametrize("key", ["one", "onx", "on", "online", "on_click"])
def test_a_key_that_is_not_on_plus_capital_stays_a_data_binding(key):
    # The boundary: `on` alone, `on` + lower case, and a word that merely
    # starts with the letters.
    assert _badges({key: "value"}) == {key: "bind"}


def test_the_eleven_keys_of_the_old_list_are_still_events():
    old = ["onClick", "onLongPress", "onValueChange", "onTextChange", "onSelect",
           "onTabChange", "onSubmit", "onSignIn", "onAppear", "onDisappear", "onRefresh"]
    assert set(_badges({k: "h" for k in old}).values()) == {"event"}


def test_events_are_listed_before_data_bindings():
    cell = _render_bindings_cell({"binding": {"text": "title", "onLoadFailed": "failed"}})
    assert cell.index("onLoadFailed") < cell.index("title")


def test_the_cell_uses_the_importers_pattern_itself():
    # One rule, not a second copy of it: the object the importer classifies
    # with is the object the cell classifies with.
    assert html_generator._EVENT_BINDING_KEY is layout_importer._EVENT_KEY


def test_what_the_import_calls_a_handler_the_cell_draws_as_an_event():
    # End to end through the importer that fills comp["binding"].
    result = _extract_from_layout({"type": "View", "id": "root", "child": [
        {"type": "Web", "id": "web", "url": "@{pageUrl}",
         "onLoadFailed": "@{loadFailed}", "reloadToken": "@{reloadToken}"},
    ]})
    handlers = {h["name"] for h in result["eventHandlers"]}
    web = result["components"][0]["children"][0] if result["components"][0].get("children") else None
    assert "loadFailed" in handlers
    assert web is not None, result["components"]
    assert _badges(web["binding"]) == {
        "url": "bind", "onLoadFailed": "event", "reloadToken": "bind",
    }
