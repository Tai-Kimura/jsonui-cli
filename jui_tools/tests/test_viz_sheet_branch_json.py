"""A branch's when / then reach the page as the spec's JSON (ticket 2026-10-20-jui-viz-spec-branch-json-formatted):
an object or an array as written (key order kept), the page formats it; anything else, or one too large, as text."""

import json

from jui_cli.viz import sheet
from jui_cli.viz.sheet import build_doc

IMPL = {"total": 0, "done": 0}


def doc_of(when, then):
    spec = {"branchContracts": {"methods": {"onSave": {"branches": [{"when": when, "then": then}, {"note": "n"}]}}}}
    return build_doc(spec, [], [], IMPL)["branches"]


def test_objects_and_arrays_go_as_they_are_in_their_order():
    when = {"data.noteText": "香りが  開いた", "api.addNote": "default", "z": 1, "a": [True, None]}
    rows = doc_of(when, ["x", {"k": 2.5}])
    assert rows[0] == ["onSave", when, ["x", {"k": 2.5}]]
    assert list(rows[0][1]) == ["data.noteText", "api.addNote", "z", "a"]   # the spec's order
    assert rows[0][1]["data.noteText"] == "香りが  開いた"                  # not squeezed like a line of text
    assert rows[1] == ["onSave", "note", "n"]


def test_text_numbers_and_the_too_large_stay_one_line():
    assert doc_of("empty", 3)[0] == ["onSave", "empty", "3"]
    big = {"k": "x" * (sheet.MAX_JSON + 10)}
    cut = doc_of(big, None)[0]
    assert isinstance(cut[1], str) and len(cut[1]) == sheet.MAX_TEXT and cut[2] == ""
    assert json.loads(json.dumps(doc_of({"a": "<img src=x onerror=alert(1)>"}, {})[0][1])) == {"a": "<img src=x onerror=alert(1)>"}
