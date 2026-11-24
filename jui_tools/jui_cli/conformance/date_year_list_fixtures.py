"""The date SelectBox's calendar after its year is pressed (Android only).

KotlinJsonUI's DateSelectBox opens a sheet with material3's DatePicker for
``datePickerMode: "date"``. Pressing the month-and-year header swaps the day
grid for the year list, drawn over the grid; the list hides the grid with the
calendar's container colour. KotlinJsonUI 2.64.0 and 2.65.0 made that colour
transparent and the days showed through the years (ticket
2026-11-24-kjui-dateselectbox-year-list-drawn-over-the-days). No fixture
opened the sheet, so nothing saw it.

The fixture opens the sheet, waits for its Done button (``kjui_x7q_done``),
presses the header inside the calendar (``kjui_x7q_calendar``) by its text,
waits for the swap's animation and takes the picture.

- The header and its arrow are material3's own children with no tag and no
  click of their own; the click is on a parent with no name. The step taps the
  named child's centre (jsonui-test-runner Android driver; ticket
  2026-11-24-conformance-android-tap-untagged-material-child-and-pinned-locale).
- Its text is in the device's language; KotlinJsonUI's conformance host pins
  en-US, so the header reads "November 2025" on every device.
- The years run 2020 to 2025 (minimumDate / maximumDate) and the selected date
  is 2025-11-24: material3 rings the current year in the list, and a range
  that ends before the run's year keeps that ring out of the picture whatever
  the day of the run.
- Android only: iOS and the web draw no such sheet.
"""
from __future__ import annotations

from . import rules
from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_PLATFORMS = ["android"]

CASE = "datePickerMode__date_year_list"
SELECTED_DATE = "2025-11-24"
MINIMUM_DATE = "2020-01-01"
MAXIMUM_DATE = "2025-12-31"
#: the header's words in en-US (the host's pinned language) for SELECTED_DATE
HEADER_TEXT = "November 2025"
#: material3's swap to the year list animates; the picture waits it out
SWAP_WAIT_MS = 1000
#: the control: the same sheet, open on the day grid, the year not pressed. A press that reached nothing leaves the
#: fixture's picture the control's, and the control comparison calls it inert.
CONTROL_STEM = "SelectBox__date-sheet-open"
CONTROL_ID = f"__control/{CONTROL_STEM}"


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _layout(source_label: str, mode: bool = True) -> dict:
    """The control leaves datePickerMode out: "date" is the default on both of KotlinJsonUI's paths, so it draws the
    same sheet, and the press is the only difference that shows."""
    box = {
        "type": "SelectBox",
        "id": "target",
        "width": 200,
        "selectItemType": "Date",
        "datePickerMode": "date",
        "selectedDate": "@{pickedDate}",
        "dateStringFormat": "yyyy-MM-dd",
        "minimumDate": MINIMUM_DATE,
        "maximumDate": MAXIMUM_DATE,
    }
    if not mode:
        del box["datePickerMode"]
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": [box],
        "data": [
            {"name": "pickedDate", "class": "String", "defaultValue": SELECTED_DATE},
            {"name": "onPickedDateChange", "class": "(String) -> Void"},
        ],
    }


def _steps(shot: str, press_year: bool) -> list[dict]:
    steps = [
        {"action": "waitFor", "id": "root"},
        {"action": "tap", "id": "target"},
        {"action": "waitFor", "id": "kjui_x7q_done"},
    ]
    if press_year:
        steps.append({"action": "tap", "id": "kjui_x7q_calendar", "text": HEADER_TEXT})
    return steps + [
        {"action": "wait", "ms": SWAP_WAIT_MS},
        {"action": "screenshot", "name": shot},
    ]


def _test(name: str, shot: str, description: str, layout_rel: str, press_year: bool) -> dict:
    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance {name}",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", "SelectBox"],
        },
        "platform": "all",
        "cases": [{
            "name": name,
            "description": description,
            "steps": _steps(shot, press_year),
        }],
    }


def _entry(**fields) -> dict:
    base = {
        "class": rules.CLASS_VISUAL,
        "host": "SelectBox",
        "aliasOf": None,
        "platforms": list(_PLATFORMS),
        "mode": None,
        "deprecated": None,
        "state": None,
        "promotedFrom": None,
    }
    base.update(fields)
    return base


def build_date_year_list_fixtures(source_label: str) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(files, manifest entries)``: the control, then the year-list fixture."""
    control_layout = f"fixtures/__control/{CONTROL_STEM}.layout.json"
    control_test = f"fixtures/__control/{CONTROL_STEM}.test.json"
    layout_rel = f"fixtures/SelectBox/{CASE}.layout.json"
    test_rel = f"fixtures/SelectBox/{CASE}.test.json"
    description = (
        "A date SelectBox's sheet with its year pressed: the year list stands over the "
        "calendar on the sheet's own colour, and no day of the month shows through it."
    )
    control_description = (
        "Control for the year-list fixture: the same date SelectBox's sheet, open on the day "
        "grid, the year not pressed."
    )
    files = [
        (control_layout, _layout(source_label, mode=False)),
        (control_test, _test(CONTROL_STEM, f"control_{CONTROL_STEM}", control_description, control_layout,
                             press_year=False)),
        (layout_rel, _layout(source_label)),
        (test_rel, _test(f"SelectBox {CASE}", f"SelectBox_{CASE}", description, layout_rel, press_year=True)),
    ]
    entries = [
        _entry(id=CONTROL_ID, component="__control", attribute=None, case=CONTROL_STEM, writtenKey=None,
               value=None, layout=control_layout, test=control_test, control=None, isControl=True),
        _entry(id=f"SelectBox/{CASE}", component="SelectBox", attribute="datePickerMode", case=CASE,
               writtenKey="datePickerMode", value="date", layout=layout_rel, test=test_rel, peerGroup=None,
               control=CONTROL_ID),
    ]
    return files, entries
