"""The test bridge: an initialState the host delivers at launch, and `state`.

jsonui-test-runner spec section 10. A screen applies a UI test's initialState
once, the first time it appears after launch, and publishes its Data (and a
receipt of what it applied) for the driver. These four fixtures hold the
library side of that on every face:

- ``initialState__applied``     String / Int / Bool / an optional's null go in;
                                the label shows the string, ``state`` reads all
                                four, the receipt lists the four as applied.
- ``initialState__rejected``    an undeclared key and 1.5 for an Int are
                                rejected with the fixed reasons; the string
                                that fits still goes in, the Int keeps its
                                default.
- ``initialState__not_reapplied`` the host remounts the fixture (store and
                                all) after checking the receipt: the new
                                instance shows the defaults — the payload is
                                consumed once per launch and screen.
- ``initialState__bridge_follows`` the host's afterFirstDraw changes a value;
                                ``state`` reads the new one through the bridge.

No step drives input, so the codegen faces host them too. What the host does
is the ``testBridge`` section of conformance/INTERACTIVE_HOST_CONTRACT.md:
deliver the payload at launch keyed by its own screen id for the fixture,
check the receipt against ``testBridge.receipt``, point ``state`` at that
screen, and remount when ``testBridge.remount`` is set.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"
SECTION = "TestBridge"
_PLATFORMS = ["ios", "android", "web"]

EMAIL = "tbEmail"
COUNT = "tbCount"
AGREED = "tbAgreed"
NICKNAME = "tbNickname"
RESULT = "conformanceResult"

EMAIL_DEFAULT = "unset"
NICKNAME_DEFAULT = "nick"

#: The Data every initialState fixture declares — one of each class kind the
#: spec's table names that all three faces hold natively.
_DATA = [
    {"name": EMAIL, "class": "String", "defaultValue": EMAIL_DEFAULT},
    {"name": COUNT, "class": "Int", "defaultValue": 0},
    {"name": AGREED, "class": "Bool", "defaultValue": False},
    {"name": NICKNAME, "class": "String?", "defaultValue": NICKNAME_DEFAULT},
]


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _label(element_id: str, var: str) -> dict:
    return {"type": "Label", "id": element_id, "width": "wrapContent", "height": "wrapContent",
            "text": f"@{{{var}}}", "fontColor": "#000000"}


def _layout(source_label: str, data: list[dict], labels: list[dict]) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "orientation": "vertical",
        "data": data,
        "child": labels,
    }


def _test(case: str, description: str, layout_rel: str, steps: list[dict]) -> dict:
    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance {SECTION}.{case}",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", "interactive", SECTION],
        },
        "platform": "all",
        "cases": [{
            "name": case,
            "description": description,
            "steps": [{"action": "waitFor", "id": "root"}, *steps],
        }],
    }


def _state(path: str, equals) -> dict:
    return {"assert": "state", "path": path, "equals": equals}


def _text(element_id: str, equals: str) -> dict:
    return {"assert": "text", "id": element_id, "equals": equals}


def _entry(case: str, layout_rel: str, test_rel: str, state, test_bridge: dict) -> dict:
    return {
        "id": f"{SECTION}/{case}",
        "component": SECTION,
        "attribute": "initialState",
        "case": case,
        "class": "interactive",
        "host": "View",
        "writtenKey": None,
        "aliasOf": None,
        "value": None,
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "layout": layout_rel,
        "test": test_rel,
        "state": state,
        "promotedFrom": None,
        "companions": list(rules.BASE_COMPANIONS.get("View", [])),
        "testBridge": test_bridge,
    }


def _cases() -> list[tuple[str, str, list[dict], list[dict], dict | None, dict, list[dict]]]:
    """(case, description, data, labels, state, testBridge, steps)."""
    email_label = [_label("label_email", EMAIL)]
    # Interactive fixtures carry a state object; these deliver no vars and
    # no handlers of their own — their values come from the initialState.
    no_state = {"vars": [], "handlers": []}
    applied = {EMAIL: "a@example.com", COUNT: 3, AGREED: True, NICKNAME: None}
    rejected_input = {EMAIL: "x", "tbTypo": "y", COUNT: 1.5}
    return [
        (
            "initialState__applied",
            "The host delivers String / Int / Bool / null-for-an-optional at launch; the screen "
            "applies all four once and says so in its receipt, the label shows the string and "
            "`state` reads every value back.",
            _DATA, email_label, no_state,
            {"data": _DATA, "initialState": applied,
             "receipt": {"applied": sorted(applied), "rejected": []}},
            [
                _text("label_email", "a@example.com"),
                _state(EMAIL, "a@example.com"),
                _state(COUNT, 3),
                _state(AGREED, True),
                _state(NICKNAME, None),
            ],
        ),
        (
            "initialState__rejected",
            "An undeclared key and 1.5 for an Int are rejected with the spec's reasons; the string "
            "that fits is applied, the Int keeps its default.",
            _DATA, email_label, no_state,
            {"data": _DATA, "initialState": rejected_input,
             "receipt": {"applied": [EMAIL], "rejected": [
                 {"key": COUNT, "reason": "type mismatch: expected Int"},
                 {"key": "tbTypo", "reason": "not a data field"},
             ]}},
            [
                _text("label_email", "x"),
                _state(COUNT, 0),
            ],
        ),
        (
            "initialState__not_reapplied",
            "After the receipt is checked the host remounts the fixture, store and all. The new "
            "instance is the same screen in the same launch, so the payload is not applied again: "
            "it shows the defaults.",
            _DATA, email_label, no_state,
            {"data": _DATA, "initialState": {EMAIL: "a@example.com"},
             "receipt": {"applied": [EMAIL], "rejected": []}, "remount": True},
            [
                _text("label_email", EMAIL_DEFAULT),
                _state(EMAIL, EMAIL_DEFAULT),
            ],
        ),
        (
            "initialState__bridge_follows",
            "No initialState: the host's afterFirstDraw sets a value after the first draw, and "
            "`state` reads the new value — the bridge is published again on every change.",
            [{"name": RESULT, "class": "String", "defaultValue": "ready"}],
            [_label("mirror", RESULT)],
            {"vars": [{"name": RESULT, "class": "String", "defaultValue": "ready"}],
             "handlers": [],
             "afterFirstDraw": {"name": "conformanceAfterFirstDraw", "set": {"var": RESULT, "value": "fired"}}},
            {"data": [{"name": RESULT, "class": "String", "defaultValue": "ready"}]},
            [
                _state(RESULT, "fired"),
                _text("mirror", "fired"),
            ],
        ),
    ]


def build_test_bridge_fixtures(source_label: str) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)`` for the test-bridge family."""
    files: list[tuple[str, dict]] = []
    entries: list[dict] = []
    for case, description, data, labels, state, test_bridge, steps in _cases():
        layout_rel = f"fixtures/{SECTION}/{case}.layout.json"
        test_rel = f"fixtures/{SECTION}/{case}.test.json"
        files.append((layout_rel, _layout(source_label, data, labels)))
        files.append((test_rel, _test(case, description, layout_rel, steps)))
        entries.append(_entry(case, layout_rel, test_rel, state, test_bridge))
    return files, entries
