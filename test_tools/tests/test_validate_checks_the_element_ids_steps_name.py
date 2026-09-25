"""`jsonui-test validate` checks the element ids a test's steps name (U8 (5)).

Against every layout of the project the run's config names (each on every
platform, includes expanded), through `layout_facts.classify_element`: on no
layout and not declared in `test.appOwnedIds` is INFO below
LAYOUT_ID_GATE_FROM and WARNING from it; what the generated code derives from
a layout id, a project-defined component's parts, web's `A #B`, an id no
layout id could be, one built from a case argument, and an include's other
spellings cannot be checked and are counted apart.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
from pathlib import Path

import pytest

import jsonui_test_cli
from jsonui_test_cli.validation import element_ids
from jsonui_test_cli.validator import TestValidator as Validator
from jsonui_doc_cli.spec_doc import validator as spec_validator


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


LAYOUTS = {
    "detail": {"type": "View", "id": "root", "child": [
        {"type": "Label", "id": "summary"},
        {"type": "Toggle", "id": "sampleToggle"},
        {"include": "panel", "id": "side"},
        {"type": "Collection", "id": "sampleList", "cellClasses": ["sample_cell"]},
        {"type": "Segment", "id": "tabs"},
        {"type": "SamplePicker", "id": "picker"}]},
    # Included only under an include id: its own ids exist only prefixed.
    "panel": {"type": "View", "id": "box", "child": [{"type": "Label", "id": "hint"}]},
    "sample_cell": {"type": "View", "id": "sampleCellTitle"},
    # Included by no layout: the app renders it itself, so its ids exist.
    "shell": {"type": "View", "id": "shellRoot", "child": [{"type": "Button", "id": "navHome"}]},
}


def _face(root: Path, app_owned=None) -> Path:
    """A project; the config is returned — the run's, as `cmd_validate` reads it."""
    config = {"layouts_directory": "layouts"}
    if app_owned is not None:
        config["test"] = {"appOwnedIds": app_owned}
    cfg = _write(root / "app/jui.config.json", config)
    for name, tree in LAYOUTS.items():
        _write(root / f"app/layouts/{name}.json", tree)
    return cfg


def _test(root: Path, steps, name="detail") -> Path:
    # Beside the app, not under it: walking up from here reaches no config.
    return _write(root / f"tests/{name}.test.json", {
        "type": "screen", "source": {"layout": "../app/layouts/detail.json"},
        "metadata": {"name": name},
        "cases": [{"name": "c", "description": "d", "steps": steps,
                   # an id built from a case argument needs the argument defined
                   "args": {"x": "summary", "row": "sampleList"}}]})


@pytest.fixture
def at(monkeypatch):
    """Validate as jsonui-cli *version*, LAYOUT_ID_GATE_FROM and
    INCLUDE_ID_PREFIX_GATE_FROM both at *gate* — synthetic, so an arm about
    the switch does not move when the shipped literal is postponed (three
    arms here did). The shipped literal is pinned in jui_tools."""
    from jui_cli.core import layout_facts

    def go(version, gate="1.8.120"):
        monkeypatch.setattr(jsonui_test_cli, "__version__", version)
        monkeypatch.setattr(spec_validator, "LAYOUT_ID_GATE_FROM", gate)
        monkeypatch.setattr(layout_facts, "INCLUDE_ID_PREFIX_GATE_FROM", gate)
    yield go
    element_ids.set_run_project()


def _validate(root: Path, steps, app_owned=None):
    cfg = _face(root, app_owned)
    element_ids.set_run_project(json.loads(cfg.read_text()), cfg)
    return Validator().validate_file(_test(root, steps))


def _msgs(result):
    return [(m.level, m.message) for m in result.warnings + result.infos
            if "lement id" in m.message or m.message.startswith("Element '")]


def _one(root, element, app_owned=None):
    result = _validate(root, [{"action": "tap", "id": element}], app_owned)
    return result, _msgs(result)


# ------------------------------------------------------------- what is read

EVERY_PLACE = [
    {"action": "tap", "id": "summary"},
    {"action": "waitForAny", "ids": ["summary", "sampleToggle"]},
    {"action": "scrollUntilVisible", "id": "sampleList", "container": "root"},
    {"assert": "screenshot", "name": "shot", "cropId": "summary"},
    {"assert": "visible", "id": "summary", "when": {"visible": "root"}},
    {"assert": "visible", "id": "summary", "when": {"notVisible": "sampleToggle"}},
    {"action": "repeat", "while": {"visible": "summary"}, "steps": [
        {"action": "tap", "id": "sampleToggle"},
        {"action": "retry", "steps": [{"assert": "visible", "id": "root"}]}]},
    {"action": "readText", "id": "summary", "variable": "not_an_element"},
    {"assert": "screen", "name": "detail", "screen": "detail"},
]
EVERY_PLACE_PATHS = [
    "steps[0].id", "steps[1].ids[0]", "steps[1].ids[1]", "steps[2].id",
    "steps[2].container", "steps[3].cropId", "steps[4].id", "steps[4].when.visible",
    "steps[5].id", "steps[5].when.notVisible", "steps[6].while.visible",
    "steps[6].steps[0].id", "steps[6].steps[1].steps[0].id", "steps[7].id",
]


def test_every_place_a_step_names_an_element_id_is_read():
    # ... and nothing else: a screen name, a variable, a screenshot's name.
    refs = element_ids.test_element_ids(
        {"type": "screen", "setup": [EVERY_PLACE[0]], "teardown": [EVERY_PLACE[0]],
         "cases": [{"name": "c", "steps": EVERY_PLACE}]}, "$")
    assert [p for p, _ in refs] == (["$.setup[0].id"]
                                    + [f"$.cases[0].{p}" for p in EVERY_PLACE_PATHS]
                                    + ["$.teardown[0].id"])


def _misspell(steps, place):
    """*steps* with the id at *place* ("steps[6].steps[0].id") set to `nowhere`."""
    root = {"steps": json.loads(json.dumps(steps))}
    *keys, last = re.findall(r"(\w+)(?:\[(\d+)\])?", place)
    target = root
    for key, index in keys:
        target = target[key][int(index)] if index else target[key]
    key, index = last
    if index:
        target[key][int(index)] = "nowhere"
    else:
        target[key] = "nowhere"
    return root["steps"]


@pytest.mark.parametrize("place", EVERY_PLACE_PATHS)
def test_each_place_misspelled_alone_is_the_one_reported(tmp_path, at, place):
    # Conservation with the reader: a place read and then dropped fails here.
    at("1.8.119")
    result = _validate(tmp_path, _misspell(EVERY_PLACE, place))
    missing = [m.path for m in result.infos if m.message.startswith("Element '")]
    assert [p.split(".test.json.", 1)[1] for p in missing] == [f"cases[0].{place}"]
    assert dict(result.element_ids) == {"named": 14, "on_layout": 13, "missing": 1}


def test_ids_on_a_layout_pass_silently_wherever_the_layout_is(tmp_path, at):
    # Prefixed include ids, a cell's id, and a layout no screen includes.
    at("1.8.121")
    result = _validate(tmp_path, [{"action": "tap", "id": i} for i in (
        "summary", "sideHint", "sideBox", "sampleCellTitle", "navHome", "shellRoot")])
    assert _msgs(result) == []
    assert dict(result.element_ids) == {"named": 6, "on_layout": 6}


def test_validate_data_checks_no_element_ids(tmp_path, at):
    at("1.8.119")
    _face(tmp_path)
    result = Validator().validate_data({"type": "screen", "cases": [
        {"name": "c", "description": "d", "steps": [{"action": "tap", "id": "nowhere"}]}]})
    assert _msgs(result) == [] and not result.element_ids


# ------------------------------------------------------------- the level

NOWHERE = ("Element 'sample_toggle' is on no layout of this project (includes expanded, "
           "every platform); the layouts have 'sampleToggle' — the runtime id is the "
           "layout's spelling")


@pytest.mark.parametrize("version, level", [("1.8.119", "info"), ("1.8.120", "warning"),
                                            ("1.8.121", "warning")])   # 1.8.120: the equal point
def test_on_no_layout_is_info_below_the_release_and_a_warning_from_it(tmp_path, at,
                                                                      version, level):
    at(version)
    result, msgs = _one(tmp_path, "sample_toggle")
    assert msgs == [(level, NOWHERE)]
    assert result.is_valid        # never an error


@pytest.mark.parametrize("gate", ["withdrawn", "1.8", None])
def test_a_withdrawn_or_unreadable_gate_never_warns_or_announces(tmp_path, at, gate):
    at("9.9.9", gate=gate)
    _, msgs = _one(tmp_path, "sample_toggle")
    assert [lv for lv, _ in msgs] == ["info"]
    assert element_ids.gate_notice("9.9.9") is None


def test_the_notice_is_announced_below_the_release_only(at):
    at("1.8.119")
    assert element_ids.gate_notice("1.8.119") == (
        "from jsonui-cli 1.8.120, test element ids on no layout of the project become WARNING "
        "(declare the ones the app draws itself in test.appOwnedIds)")
    assert element_ids.gate_notice("1.8.120") is None


# ------------------------------------------------------------- cannot check

@pytest.mark.parametrize("element, kind", [
    # derived by the generated code — boundary: the base must be the right type
    ("sampleList_item_0", "derived"), ("sampleList_item_12", "derived"), ("tabs_tab_1", "derived"),
    ("summary_item_0", "missing"), ("summary_tab_1", "missing"), ("nowhere_item_0", "missing"),
    ("sampleList_tab_0", "missing"), ("sampleList_item_x", "missing"),
    # a project-defined component's parts — boundary: a built-in type has none
    ("picker_today", "part"), ("picker_range_start", "part"), ("summary_today", "missing"),
    # web's CSS descendant form, each part checked
    ("sampleList_item_0 #sampleCellTitle", "css"), ("root #summary", "css"),
    ("sampleList_item_0 #nowhere", "missing"), ("nowhere #summary", "missing"),
    # no layout id is spelled so
    ("com.example:id/icon", "not_an_id"), ("sample_2000-01-01", "not_an_id"),
    ("Grid-Info", "not_an_id"), ("summary2", "missing"),
    # built from a case argument
    ("@{row}_label", "argument"),
])
def test_what_cannot_be_checked_is_counted_apart(tmp_path, at, element, kind):
    at("1.8.121")                                   # where a miss would be a WARNING
    result, msgs = _one(tmp_path, element)
    if kind == "missing":
        assert [lv for lv, _ in msgs] == ["warning"], msgs
        assert result.element_ids["missing"] == 1
    else:
        assert [lv for lv, _ in msgs] == ["info"], msgs
        assert msgs[0][1].startswith(f"cannot check: 1 element id(s) ({element}) — ")
        assert msgs[0][1].endswith(element_ids.CANNOT[kind])
        assert result.element_ids["cannot_check"] == 1


def test_a_css_part_on_no_layout_is_named(tmp_path, at):
    at("1.8.121")
    _, msgs = _one(tmp_path, "sampleList_item_0 #nowhere")
    assert msgs[0][1].startswith(
        "Element 'sampleList_item_0 #nowhere': its part 'nowhere' is on no layout of this project")


# ------------------------------------------------------------- include spellings

def test_web_s_old_spelling_cannot_be_checked_and_names_the_release_s(tmp_path, at):
    at("1.8.119")
    _, msgs = _one(tmp_path, "hint")
    assert msgs == [("info",
        "cannot check: 1 element id(s) inside includes (hint) — web spells an id inside an "
        "include with an id as the included layout has it (its root: the include's id), "
        "native prefixes it with the include's; from jsonui-cli 1.8.120 web spells it as "
        "native: 'hint' -> 'sideHint'")]


@pytest.mark.parametrize("element, now", [("hint", "sideHint"), ("side", "sideBox")])
def test_from_the_include_release_web_s_old_spelling_is_a_warning(tmp_path, at, element, now):
    at("1.8.120")
    _, msgs = _one(tmp_path, element)
    assert msgs == [("warning",
        f"Element '{element}' is on no layout of this project (includes expanded, every "
        f"platform); the layouts have '{now}' — the runtime id is the layout's spelling")]


@pytest.mark.parametrize("version", ["1.8.119", "1.8.121"])
def test_uikit_s_spelling_stays_cannot_check(tmp_path, at, version):
    at(version)
    _, msgs = _one(tmp_path, "side_hint")
    assert [lv for lv, _ in msgs] == ["info"]
    assert "UIKit / XML spell it '<include id>_<id>' (side_hint)" in msgs[0][1]


def test_a_partial_included_only_under_an_id_lends_no_raw_id(tmp_path, at):
    # `box` is the partial's root: on no platform is it spelled `box` (web
    # gives the root the include's id, native prefixes it).
    at("1.8.121")
    result, msgs = _one(tmp_path, "box")
    assert [lv for lv, _ in msgs] == ["warning"]


def test_control_a_partial_also_included_without_an_id_lends_its_ids(tmp_path, at):
    at("1.8.121")
    LAYOUTS["detail"]["child"].append({"include": "panel"})
    try:
        result, msgs = _one(tmp_path, "box")
    finally:
        LAYOUTS["detail"]["child"].pop()
    assert msgs == [] and result.element_ids["on_layout"] == 1


# ------------------------------------------------------------- test.appOwnedIds

@pytest.mark.parametrize("element, entry", [("toastLabel", "toastLabel"),
                                            ("sample_day_12", "sample_day_*")])
def test_an_id_the_app_draws_itself_is_declared(tmp_path, at, element, entry):
    at("1.8.121")
    result, msgs = _one(tmp_path, element, app_owned=["toastLabel", "sample_day_*", "stale"])
    assert msgs == [] and result.element_ids["app_owned"] == 1
    assert entry not in element_ids.unnamed_app_owned()
    assert "stale" in element_ids.unnamed_app_owned()


@pytest.mark.parametrize("element", ["toastLabelX", "sample_da", "xsample_day_1"])
def test_boundary_a_declaration_covers_only_what_it_says(tmp_path, at, element):
    at("1.8.121")
    _, msgs = _one(tmp_path, element, app_owned=["toastLabel", "sample_day_*"])
    assert [lv for lv, _ in msgs] == ["warning"]


def test_a_declaration_is_not_looked_up_in_the_layouts(tmp_path, at):
    # The app draws it; that no layout has it is the point.
    at("1.8.121")
    _, msgs = _one(tmp_path, "toastLabel", app_owned=["toastLabel"])
    assert msgs == []


# ------------------------------------------------------------- the run's project

def test_the_project_is_the_config_the_run_read_not_one_above_the_test(tmp_path, at):
    # A config above the tests that declares no layouts: walking up from the
    # test file finds it, and every id went unchecked on the face measured.
    at("1.8.119")
    _write(tmp_path / "jui.config.json", {})
    result, msgs = _one(tmp_path, "sample_toggle")
    assert result.element_ids["missing"] == 1


def test_without_a_project_nothing_is_checked_and_why_is_kept(tmp_path, at):
    at("1.8.119")
    _face(tmp_path)
    element_ids.set_run_project()
    result = Validator().validate_file(_test(tmp_path, [{"action": "tap", "id": "nowhere"}]))
    assert _msgs(result) == []
    assert dict(result.element_ids) == {"named": 1, "not_checked": 1}
    assert result.element_ids_unchecked_why == "validate was not given a project config"


# ------------------------------------------------------------- the printed run

def _cli(tmp_path, steps, app_owned=None):
    cfg = _face(tmp_path, app_owned)
    _test(tmp_path, steps)
    from jsonui_test_cli.cli import main
    import sys
    argv, cwd = sys.argv, os.getcwd()
    out = io.StringIO()
    try:
        os.chdir(cfg.parent)
        sys.argv = ["jsonui-test", "validate", "../tests", "--no-install", "--no-mock-check",
                    "--no-coverage-check"]
        with contextlib.redirect_stdout(out):
            rc = main()
    finally:
        sys.argv = argv
        os.chdir(cwd)
    return rc, out.getvalue()


def test_the_run_prints_the_count_its_denominator_and_the_notice(tmp_path, at):
    at("1.8.119")
    rc, out = _cli(tmp_path, [{"action": "tap", "id": i} for i in (
        "summary", "sample_toggle", "sampleList_item_0", "toastLabel", "@{x}")],
        app_owned=["toastLabel", "stale"])
    assert rc == 0
    assert ("[INFO] element ids: 5 named in the steps — 1 on a layout, 1 declared in "
            "test.appOwnedIds, 1 on no layout, 2 cannot check, 0 not checked") in out
    assert "[INFO] test.appOwnedIds: 1 entry no step in this run names (stale)" in out
    assert "[INFO] from jsonui-cli 1.8.120, test element ids on no layout" in out
    assert re.search(r"^Files: \d+, Errors: 0, Warnings: 0, Info: 3 \(not counted\)$", out, re.M)
    # The agents' rulebook counts warnings with this expression; no INFO matches it.
    rule = re.compile(r"warning \[|warning:|\[warn|⚠", re.I)
    assert [line for line in out.splitlines() if "INFO" in line and rule.search(line)] == []


def test_from_the_release_it_counts_as_a_warning_and_announces_nothing(tmp_path, at):
    at("1.8.120")
    rc, out = _cli(tmp_path, [{"action": "tap", "id": "sample_toggle"}])
    assert rc == 0
    assert re.search(r"^Files: \d+, Errors: 0, Warnings: 1$", out, re.M), out
    assert "become WARNING" not in out


def test_without_gate_versions_they_stay_info_and_the_run_says_why(tmp_path, at, monkeypatch):
    # A tool tree without shared/core/gate_versions.py: nothing may become a
    # WARNING that was never announced, and the run says why.
    at("1.8.121")
    monkeypatch.setattr(element_ids, "_gates", lambda: None)
    rc, out = _cli(tmp_path, [{"action": "tap", "id": "sample_toggle"}])
    assert rc == 0
    assert re.search(r"^Files: \d+, Errors: 0, Warnings: 0, Info: 1 \(not counted\)$", out, re.M)
    assert ("[INFO] the level of 1 element id(s) on no layout cannot be decided — "
            "shared/core/gate_versions.py is not in this tool tree; they are listed as INFO") in out


@pytest.mark.parametrize("element, hint", [("sample_toggle", False), ("zz_unrelated", True)])
def test_the_declaration_hint_only_where_no_layout_id_is_near(tmp_path, at, element, hint):
    # Beside a near spelling the fix is the spelling; the hint would offer a
    # way to declare the typo instead (ee, pack review).
    at("1.8.121")
    _, msgs = _one(tmp_path, element)
    assert ("test.appOwnedIds" in msgs[0][1]) is hint, msgs
