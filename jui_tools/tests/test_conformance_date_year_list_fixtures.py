"""The date SelectBox year-list fixture: what it presses, what its control leaves out, and why its years stop early."""
from __future__ import annotations

import datetime

from jui_cli.conformance import date_year_list_fixtures as Y


def _built():
    files, entries = Y.build_date_year_list_fixtures("test")
    return dict(files), {e["id"]: e for e in entries}


def test_the_fixture_presses_the_header_by_its_text_and_the_control_does_not():
    files, entries = _built()
    fixture = entries[f"SelectBox/{Y.CASE}"]
    control = entries[Y.CONTROL_ID]
    assert fixture["control"] == Y.CONTROL_ID and control["isControl"] and fixture["platforms"] == ["android"]
    press = {"action": "tap", "id": "kjui_x7q_calendar", "text": Y.HEADER_TEXT}
    fixture_steps = files[fixture["test"]]["cases"][0]["steps"]
    control_steps = files[control["test"]]["cases"][0]["steps"]
    assert press in fixture_steps and press not in control_steps
    # the rest is the same: open the sheet, wait for Done, wait, shoot
    assert [s for s in fixture_steps if s != press][:-1] == control_steps[:-1]


def test_the_header_text_is_the_selected_month_in_en_us():
    picked = datetime.date.fromisoformat(Y.SELECTED_DATE)
    assert Y.HEADER_TEXT == f"{picked:%B} {picked.year}"   # the C locale's month name: en-US's


def test_the_years_end_before_any_run_so_no_current_year_is_ringed():
    files, entries = _built()
    box = files[entries[f"SelectBox/{Y.CASE}"]["layout"]]["child"][0]
    last = datetime.date.fromisoformat(box["maximumDate"]).year
    assert last < datetime.date.today().year
    assert box["minimumDate"] <= Y.SELECTED_DATE <= box["maximumDate"]


def test_the_control_leaves_out_only_the_mode_whose_default_is_date():
    files, entries = _built()
    fixture = files[entries[f"SelectBox/{Y.CASE}"]["layout"]]["child"][0]
    control = files[entries[Y.CONTROL_ID]["layout"]]["child"][0]
    assert fixture["datePickerMode"] == "date" and "datePickerMode" not in control
    assert {k: v for k, v in fixture.items() if k != "datePickerMode"} == control
