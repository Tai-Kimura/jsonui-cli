"""`jsonui-test validate` checks initialState (jsonui-test-runner spec §10).

Two vectors drive it, both vendored byte for byte from jsonui-test-runner
(dev-guide/ci/check-canonical-sync.py compares them):

- shared/core/initial_state_payload_vectors.json — which test files are
  validate errors and warnings, by code;
- shared/core/initial_state_coercion_vectors.json — which values a Data class
  accepts, and the reason for each it rejects. The three generators and the
  two libraries run the same file; validate answering it is what lets an
  error here mean "the app will reject this".

The rest builds a project (a config, layouts) and checks keys and values
against the Data each layout declares, per platform.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
from pathlib import Path

import pytest

from jsonui_test_cli import shared_core
from jsonui_test_cli.validation import initial_state as ist
from jsonui_test_cli.validation import screen_ids
from jsonui_test_cli.validation.step import set_project_platforms
from jsonui_test_cli.validator import TestValidator as Validator

CORE = shared_core.shared_core_dir()
PAYLOAD = json.loads((CORE / "initial_state_payload_vectors.json").read_text(encoding="utf-8"))
COERCION = json.loads((CORE / "initial_state_coercion_vectors.json").read_text(encoding="utf-8"))
CODES = {ist.CODE_CASE_NEEDS_REOPEN, ist.CODE_REFERENCED_IGNORED, ist.CODE_FLOW_SCREEN_REMOVED}


@pytest.fixture(autouse=True)
def _clean():
    screen_ids.clear_cache()
    set_project_platforms(None)
    yield
    screen_ids.clear_cache()
    set_project_platforms(None)


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ------------------------------------------------------------- the coercion vector


@pytest.mark.parametrize("case", COERCION["cases"], ids=[c["name"] for c in COERCION["cases"]])
def test_the_value_rules_answer_the_coercion_vector(case):
    fields = [(d["name"], d["class"]) for d in case["data"]]
    applied, rejected = ist.judge(fields, case["input"])
    assert sorted(applied) == sorted(case["expect"]["applied"])
    key = lambda r: (r["key"], r["reason"])  # noqa: E731
    assert sorted(rejected, key=key) == sorted(case["expect"]["rejected"], key=key)


def test_the_coercion_vector_reaches_every_reason():
    # A vector that never rejected for one reason could not catch a rule
    # that never gives it.
    reasons = {r["reason"].split(" ")[0] for c in COERCION["cases"] for r in c["expect"]["rejected"]}
    assert reasons == {"not", "type", "null", "unsupported"}


# ------------------------------------------------------------- the payload vector


def _materialise_payload_case(tmp_path: Path, case: dict) -> Path:
    for ref, body in (case.get("files") or {}).items():
        _write(tmp_path / f"{ref}.test.json", body)
    return _write(tmp_path / "t.test.json", case["test"])


def _coded(messages):
    return [m for m in messages if m.kind in CODES]


@pytest.mark.parametrize("case", PAYLOAD["cases"], ids=[c["name"] for c in PAYLOAD["cases"]])
def test_validate_answers_the_payload_vector(tmp_path, case):
    """validateErrors and warnings, by code — and the case or file each names."""
    result = Validator().validate_file(_materialise_payload_case(tmp_path, case))
    expect = case["expect"]
    for got, want in ((_coded(result.errors), expect["validateErrors"]),
                      (_coded(result.warnings), expect["warnings"])):
        assert sorted(m.kind for m in got) == sorted(w["code"] for w in want), \
            [str(m) for m in got]
        for w in want:
            named = [m for m in got if m.kind == w["code"]
                     and ("file" not in w or f"'{w['file']}'" in m.message)
                     and ("case" not in w or f"case '{w['case']}'" in m.message)]
            assert len(named) == 1, (w, [str(m) for m in got])
    # Nothing else in the vector's files is an error: they are valid tests
    # but for the one coded finding.
    assert [str(m) for m in result.errors if m.kind not in CODES] == []


def test_the_payload_vector_reaches_every_code():
    seen = {e["code"] for c in PAYLOAD["cases"]
            for e in c["expect"]["validateErrors"] + c["expect"]["warnings"]}
    assert seen == CODES


@pytest.mark.parametrize("case", [c for c in PAYLOAD["cases"]
                                  if c["test"]["type"] == "screen" and c["expect"]["launches"]
                                  and c["expect"]["launches"][0]["screens"]],
                         ids=lambda c: c["name"])
def test_the_screen_under_test_is_the_vectors_screen_id(case):
    # The id the values are checked for is the id the driver delivers them to.
    ids = {k for launch in case["expect"]["launches"] if launch["screens"]
           for k in launch["screens"]}
    assert ids == {ist.screen_id_for_layout(case["test"]["source"]["layout"])}


# ------------------------------------------------------------- against a project

LOGIN = {
    "type": "View", "id": "root",
    "data": [
        {"name": "email", "class": "String"},
        {"name": "count", "class": "Int"},
        {"name": "agreed", "class": "Bool"},
        {"name": "note", "class": "String?"},
        {"name": "onTap", "class": "() -> Void"},
        {"name": "perFace", "class": {"swift": "Int", "kotlin": "Int", "typescript": "number"}},
        # DataItemPlatform: declared for the mobile platforms only — a Data
        # name on two platforms of three.
        {"name": "mobileOnly", "class": "String", "platform": "ios,android"},
    ],
    "child": [
        {"type": "View", "id": "box", "data": [{"name": "boxed", "class": "String"}]},
        {"include": "header", "id": "header"},
    ],
}
HEADER = {"type": "View", "id": "headerRoot", "data": [{"name": "title", "class": "String"}]}
HOME = {"type": "View", "id": "homeRoot", "data": [{"name": "tab", "class": "Int"}]}


def _project(root: Path, platforms=None) -> Path:
    config = {"layouts_directory": "layouts"}
    if platforms is not None:
        config["platforms"] = platforms
    cfg = _write(root / "app/jui.config.json", config)
    _write(root / "app/layouts/login.json", LOGIN)
    _write(root / "app/layouts/header.json", HEADER)
    _write(root / "app/layouts/home.json", HOME)
    screen_ids.set_run_config(json.loads(cfg.read_text()), cfg)
    return cfg


def _screen(view_model=None, cases=None, **extra) -> dict:
    data = {"type": "screen", "source": {"layout": "../app/layouts/login.json"},
            "metadata": {"name": "login"},
            "cases": cases or [{"name": "a", "description": "d",
                                "steps": [{"assert": "visible", "id": "root"}]}],
            **extra}
    if view_model is not None:
        data["initialState"] = {"viewModel": view_model}
    return data


def _validate(tmp_path: Path, data: dict, name="screens/login.test.json"):
    return Validator().validate_file(_write(tmp_path / "tests" / name, data))


def _state_errors(result):
    return [m.message for m in result.errors if m.message.startswith("initialState '")]


def test_fitting_values_are_clean(tmp_path):
    _project(tmp_path)
    result = _validate(tmp_path, _screen({
        "email": "a@example.com", "count": 2.0, "agreed": False, "note": None,
        "perFace": 3, "mobileOnly": "m", "boxed": "x", "headerTitle": "t"},
        platform=["ios", "android"]))
    assert _state_errors(result) == []
    assert [m for m in result.infos if "initialState" in m.message] == []


@pytest.mark.parametrize("key,value,reason", [
    ("nickname", "x", "not a data field"),
    ("Email", "x", "not a data field"),
    ("email", 1, "type mismatch: expected String"),
    ("count", 1.5, "type mismatch: expected Int"),
    ("count", 2147483648, "type mismatch: expected Int"),
    ("agreed", 1, "type mismatch: expected Bool"),
    ("agreed", None, "null for non-optional Bool"),
    ("onTap", None, "unsupported type () -> Void"),
])
def test_a_value_the_app_would_reject_is_an_error(tmp_path, key, value, reason):
    _project(tmp_path)
    errors = _state_errors(_validate(tmp_path, _screen({key: value})))
    assert len(errors) == 1 and f"initialState '{key}' for screen 'login': {reason}." in errors[0]


def test_a_data_name_on_some_platforms_names_the_others(tmp_path):
    _project(tmp_path)
    errors = _state_errors(_validate(tmp_path, _screen({"mobileOnly": "x"})))
    assert len(errors) == 1 and "not a data field on web." in errors[0]


def test_the_files_platform_bounds_the_check(tmp_path):
    _project(tmp_path)
    assert _state_errors(_validate(tmp_path, _screen({"mobileOnly": "x"}, platform="ios"))) == []


def test_the_projects_platforms_bound_the_check(tmp_path):
    _project(tmp_path)
    set_project_platforms(["ios", "android"])
    assert _state_errors(_validate(tmp_path, _screen({"mobileOnly": "x"}))) == []


def test_a_per_platform_class_is_read_per_platform(tmp_path):
    _project(tmp_path)
    errors = _state_errors(_validate(tmp_path, _screen({"perFace": "x"})))
    # Int on ios / android, `number` (Number's lower-case spelling) on web:
    # each platform judged, and named, by its own class.
    assert sorted(e.split(": ", 1)[1].split(". The")[0] for e in errors) == [
        "type mismatch: expected Int on ios, android", "type mismatch: expected number on web"]


def test_a_case_level_value_is_checked(tmp_path):
    _project(tmp_path)
    data = _screen(caseIsolation="reopen", cases=[
        {"name": "a", "description": "d", "steps": [{"assert": "visible", "id": "root"}],
         "initialState": {"viewModel": {"count": "1"}}}])
    errors = [m for m in _validate(tmp_path, data).errors if m.message.startswith("initialState '")]
    assert len(errors) == 1 and errors[0].path.endswith(".cases[0].initialState.viewModel.count")


def test_a_case_under_shared_is_an_error_and_reopen_is_not(tmp_path):
    case = {"name": "b", "description": "d", "steps": [{"assert": "visible", "id": "root"}],
            "initialState": {"viewModel": {"email": "b"}}}
    shared = Validator().validate_data(_screen(cases=[case]))
    assert [m.kind for m in shared.errors] == [ist.CODE_CASE_NEEDS_REOPEN]
    reopen = Validator().validate_data(_screen(cases=[case], caseIsolation="reopen"))
    assert reopen.errors == []


def test_an_empty_case_initial_state_under_shared_is_none(tmp_path):
    case = {"name": "b", "description": "d", "steps": [{"assert": "visible", "id": "root"}],
            "initialState": {"viewModel": {}}}
    assert Validator().validate_data(_screen(cases=[case])).errors == []


@pytest.mark.parametrize("state,fragment", [
    ("x", "'initialState' must be an object, got: string"),
    ({"viewModel": []}, "'initialState.viewModel' must be an object, got: array"),
    ({"viewModels": {}}, "Unknown initialState key: viewModels"),
])
def test_the_screen_shape_is_checked(state, fragment):
    data = _screen()
    data["initialState"] = state
    assert any(fragment in m.message for m in Validator().validate_data(data).errors)


def test_without_a_project_the_values_are_said_to_be_unchecked(tmp_path):
    result = _validate(tmp_path, _screen({"nickname": "x"}))
    assert _state_errors(result) == []
    infos = [m.message for m in result.infos if "initialState" in m.message]
    assert len(infos) == 1 and "not checked" in infos[0]


def test_a_screen_with_no_layout_is_said_to_be_unchecked(tmp_path):
    _project(tmp_path)
    data = _screen({"nickname": "x"})
    data["source"]["layout"] = "../app/layouts/ghost.json"
    infos = [m.message for m in _validate(tmp_path, data).infos if "initialState" in m.message]
    assert len(infos) == 1 and "screen 'ghost' has no layout in this project" in infos[0]


# ------------------------------------------------------------- flows


def _flow(view_models=None, steps=None, **extra) -> dict:
    data = {"type": "flow", "metadata": {"name": "f"},
            "steps": steps or [{"screen": "login", "action": "tap", "id": "root"}], **extra}
    if view_models is not None:
        data["initialState"] = {"viewModels": view_models}
    return data


def test_flow_values_are_checked_per_screen(tmp_path):
    _project(tmp_path)
    errors = _state_errors(_validate(tmp_path, _flow({"login": {"email": "a"},
                                                      "home": {"tab": "1"}}), "flows/f.test.json"))
    assert len(errors) == 1 and "initialState 'tab' for screen 'home': type mismatch" in errors[0]


def test_a_flow_view_models_key_is_a_screen_id(tmp_path):
    _project(tmp_path)
    result = _validate(tmp_path, _flow({"Login": {"email": "a"}}), "flows/f.test.json")
    assert any("viewModels keys are screen ids" in m.message and "Unknown screen 'Login'" in m.message
               for m in result.errors)


def test_a_flow_view_models_entry_must_be_an_object():
    result = Validator().validate_data(_flow({"login": "x"}))
    assert any("initialState.viewModels['login'] must be an object" in m.message
               for m in result.errors)


def test_a_flow_initial_state_screen_is_removed():
    result = Validator().validate_data(_flow({"login": {}}, ))
    assert result.errors == []
    data = _flow({"login": {"email": "a"}})
    data["initialState"]["screen"] = "login"
    assert [m.kind for m in Validator().validate_data(data).errors] == [ist.CODE_FLOW_SCREEN_REMOVED]


def test_a_referenced_case_not_run_by_the_step_is_not_warned(tmp_path):
    _write(tmp_path / "screens/home.test.json", {
        "type": "screen", "source": {"layout": "home"}, "metadata": {"name": "h"},
        "cases": [{"name": "a", "steps": []},
                  {"name": "b", "steps": [], "initialState": {"viewModel": {"tab": 2}}}]})
    flow = _write(tmp_path / "f.test.json", _flow(steps=[{"file": "home", "case": "a"}]))
    result = Validator().validate_file(flow)
    assert _coded(result.warnings) == []
    flow = _write(tmp_path / "f.test.json", _flow(steps=[{"file": "home"}]))
    assert [m.kind for m in _coded(Validator().validate_file(flow).warnings)] == \
        [ist.CODE_REFERENCED_IGNORED]


# ------------------------------------------------------------- the printed run


def test_the_cli_fails_on_a_rejected_value_and_names_it(tmp_path):
    cfg = _project(tmp_path)
    screen_ids.clear_cache()   # the run sets its own config
    _validate(tmp_path, _screen({"count": "2"}))
    from jsonui_test_cli.cli import main
    argv, cwd = sys.argv, os.getcwd()
    out = io.StringIO()
    try:
        os.chdir(cfg.parent)
        sys.argv = ["jsonui-test", "validate", "../tests", "--no-install", "--no-mock-check",
                    "--no-coverage-check"]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                rc = main()
            except SystemExit as exc:
                rc = exc.code
    finally:
        sys.argv = argv
        os.chdir(cwd)
    assert rc != 0
    assert re.search(r"\[ERROR\] .*initialState 'count' for screen 'login': "
                     r"type mismatch: expected Int\.", out.getvalue()), out.getvalue()


def test_an_app_owned_screen_is_said_to_be_unchecked(tmp_path):
    # Declared in test.appOwnedScreens: a real screen id with no layout, so
    # there is no Data to read — not an error, and not silence either.
    cfg = _write(tmp_path / "app/jui.config.json",
                 {"layouts_directory": "layouts", "test": {"appOwnedScreens": ["native_settings"]}})
    _write(tmp_path / "app/layouts/login.json", LOGIN)
    _write(tmp_path / "app/layouts/header.json", HEADER)
    screen_ids.set_run_config(json.loads(cfg.read_text()), cfg)
    result = _validate(tmp_path, _flow({"native_settings": {"x": 1}}), "flows/f.test.json")
    assert result.errors == []
    infos = [m.message for m in result.infos if "initialState" in m.message]
    assert len(infos) == 1 and "screen 'native_settings' has no layout in this project " \
        "(declared app-owned)" in infos[0]
