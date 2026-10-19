"""sheet.py hands each transition's type / method to the page as its third element (2.3.5: the page colours a
transition's tag by its kind, and the kind comes first from what the spec says the transition is)."""
from __future__ import annotations

from jui_cli.viz.sheet import build_doc


def test_each_transition_carries_its_type_or_method_or_nothing():
    spec = {"transitions": [
        {"condition": "保存", "destination": "StoreEditSheetView", "type": "navigationDestination"},
        {"trigger": "戻る", "destination": "前の画面", "method": "dismiss"},
        {"condition": "両方", "destination": "X", "type": "sheet", "method": "present"},   # type wins
        {"condition": "何も無い", "destination": "Home"},
    ]}
    doc = build_doc(spec, [], [], {"total": 0, "done": 0})
    assert [t[2] for t in doc["transitions"]] == ["navigationDestination", "dismiss", "sheet", ""]
    assert [t[:2] for t in doc["transitions"]] == [["保存", "StoreEditSheetView"], ["戻る", "前の画面"], ["両方", "X"], ["何も無い", "Home"]]
