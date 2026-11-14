"""onReorderStart / onReorderEnd on iOS (rule.callbacks; ticket jui-collection-reorder-start-callback-missing, the
orchestrator's ruling 2026-11-14).

A Collection iOS draws as a List reorders with onMove, which has no pick-up: SwiftJsonUI calls start and end together
when the row lands, and a release where it began or a cancelled drag calls neither. jui build says so on an iOS build
as one INFO line ([ios-reorder-callbacks]), on every minimum iOS, never as a warning. A stack that declares either
keeps the library's drag on every iOS, so the [ios-reorder] line (two drags by OS version) does not name it.
"""
from __future__ import annotations

import re

from jui_cli.core import reorder_info as info

LIST = {"type": "Collection", "id": "stops", "reorderable": True, "onReorder": "@{onMove}", "lazy": "lazy"}
STACK = {"type": "Collection", "id": "stops", "reorderable": True, "onReorder": "@{onMove}", "lazy": "none"}


def _lines(node, minimum=17.0):
    return info.tree_lines({"type": "View", "child": [node]}, "a.json", minimum, "x")


def test_a_list_that_declares_a_callback_is_named_once():
    for extra in ({"onReorderStart": "@{began}"}, {"onReorderEnd": "@{ended}"},
                  {"onReorderStart": "@{began}", "onReorderEnd": "@{ended}"}):
        lines = _lines(dict(LIST, **extra))
        assert len(lines) == 1, extra
        assert lines[0].startswith("INFO [ios-reorder-callbacks]: a.json: 'stops' (Collection) declares")
        assert "start and end come together when the row lands" in lines[0]
        assert "calls neither" in lines[0]


def test_the_list_line_is_said_on_every_minimum_ios():
    assert len(_lines(dict(LIST, onReorderStart="@{began}"), minimum=27.0)) == 1
    assert len(_lines(dict(LIST, onReorderStart="@{began}"), minimum=None)) == 1


def test_sections_with_a_list_style_are_the_list_path_too():
    node = dict(LIST, sections=[{"cell": "StopCell"}], listStyle="plain", onReorderEnd="@{ended}")
    assert [l for l in _lines(node) if "[ios-reorder-callbacks]" in l]


def test_control_a_list_without_callbacks_is_not_named():
    assert _lines(dict(LIST)) == []


def test_a_stack_that_declares_a_callback_keeps_the_librarys_drag_and_is_named_by_neither():
    # Control: without them the stack is the [ios-reorder] line (two drags by OS version).
    assert _lines(dict(STACK))[0].startswith("INFO [ios-reorder]:")
    assert _lines(dict(STACK, onReorderStart="@{began}")) == []
    assert _lines(dict(STACK, onReorderEnd="@{ended}")) == []


def test_the_line_is_not_a_warning_to_the_gates_that_count_them():
    line = _lines(dict(LIST, onReorderStart="@{began}"))[0]
    assert not re.search(r"warning \[|warning:|\[warn|⚠|error", line, re.IGNORECASE)
