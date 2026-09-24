"""`jsonui-test contracts coverage`, measured against the red-checks it must pass.

One synthetic project, and each red-check a mutation of it with an expected
DIFFERENCE from the baseline counts — so an arm that stopped counting would
not pass by reporting the same zeros twice. The baseline itself is pinned
first, with the arithmetic spelled out, because every mutation is read
against it.

The project (web and ios): a detail screen whose `approve` method

  1. serves setApproval=default          -> then: getItem called, status
  2. serves setApproval=default, getItem=error_404 -> then: transition
  3. serves setApproval=error_500, alsoStatuses 429 -> then: banner
  4. serves setApproval=error_409        -> then: banner "conflict"

and excludes getItem's 500 as unreachable. getOther is declared in the
dataFlow and reached by no row (unattributed).

  approve × setApproval  200 401 403 404 409 429 500
                         row 200, 409, 500, 429(also) · uncovered 401 403 404 (partial)
  approve × getItem      200 404 500 default
                         row 404 · unreachable 500 · uncovered 200 (partial) · default n/a
  getOther (unattributed) 200 500 -> uncovered 2
  required 12 = row 5 (alsoStatuses 1) + unreachable 1 + uncovered 6; outside 1
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from jsonui_test_cli import contracts_coverage as cc
from jsonui_test_cli.contracts_coverage import CannotStart, run_coverage


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


_OPENAPI = {
    "openapi": "3.0.0",
    "paths": {
        "/api/items/{id}": {"get": {"operationId": "getItem", "responses": {
            "200": {}, "404": {}, "500": {}, "default": {}}}},
        "/api/items/{id}/approval": {"put": {"operationId": "setApproval", "responses": {
            "200": {}, "401": {}, "403": {}, "404": {}, "409": {}, "429": {}, "500": {}}}},
        "/api/other": {"get": {"operationId": "getOther", "responses": {"200": {}, "500": {}}}},
        "/api/logout": {"post": {"operationId": "postLogout", "responses": {"204": {}}}},
    },
}

_MOCKS = {
    "getItem": ("GET", "/api/items/{id}", {
        "default": {"status": 200, "body": {"id": 1}},
        "error_404": {"status": 404, "body": {"message": "gone"}},
        "error_500": {"status": 500, "body": {"message": "boom"}}}),
    "setApproval": ("PUT", "/api/items/{id}/approval", {
        "default": {"status": 200, "body": {}},
        **{f"error_{s}": {"status": s, "body": {"message": f"e{s}"}}
           for s in (401, 403, 404, 409, 429, 500)}}),
    "getOther": ("GET", "/api/other", {
        "default": {"status": 200, "body": {}}, "error_500": {"status": 500, "body": {}}}),
    "postLogout": ("POST", "/api/logout", {"default": {"status": 204}}),
}


def _screen() -> dict:
    return {
        "type": "screen_spec",
        "metadata": {"name": "detail"},
        "dataFlow": {
            "viewModel": {"methods": [{"name": "approve"}, {"name": "load"}]},
            "repositories": [{"name": "DetailRepository", "methods": [
                {"name": "setApproval", "endpoint": "PUT /api/items/{id}/approval"},
                {"name": "getItem", "endpoint": "GET /api/items/{id}"},
                {"name": "getOther", "endpoint": "GET /api/other"},
                {"name": "localOnly"},
            ]}],
        },
        "branchContracts": {"methods": {"approve": {
            "branches": [
                {"when": {"api.setApproval": "default"},
                 "then": {"api.getItem": "called", "data.status": "approved"}},
                {"when": {"api.setApproval": "default", "api.getItem": "error_404"},
                 "then": {"transition": "back"}},
                {"when": {"api.setApproval": "error_500"},
                 "alsoStatuses": {"api.setApproval": ["429"]},
                 "then": {"data.banner": "visible"}},
                {"when": {"api.setApproval": "error_409"},
                 "then": {"data.banner": "conflict"}},
            ],
            "excludedOutcomes": {"api.getItem": {"500": {
                "by": "unreachable", "reason": "the item is read before approval"}}},
        }}},
    }


def _project(root: Path, screen=None, *, platforms=("web", "ios"), mocks=None,
             openapi=None, app=None, extra_screens=()) -> Path:
    config = {"spec_directory": "docs/screens/json", "api_directory": "docs/api",
              "mock": {"swagger": ["docs/api/api.json"], "mockDir": "tests/mocks"}}
    if platforms is not None:
        config["platforms"] = list(platforms)
    _write(root / "jui.config.json", config)
    _write(root / "docs/api/api.json", openapi or _OPENAPI)
    for op_id, (method, path, scenarios) in (mocks or _MOCKS).items():
        _write(root / f"tests/mocks/generated/{op_id}.mock.json", {
            "source": {"method": method, "path": path, "operationId": op_id},
            "activeScenario": "default", "scenarios": scenarios})
    _write(root / "docs/screens/json/detail.spec.json", screen or _screen())
    for name, spec in extra_screens:
        _write(root / f"docs/screens/json/{name}.spec.json", spec)
    if app is not None:
        _write(root / "docs/screens/json/app_contracts.spec.json", app)
    return root


def _block(report, platform="web"):
    return next(b for b in report.platforms if b.platform == platform)


def _screen_result(report, platform="web", name="detail"):
    return next(s for s in _block(report, platform).screens if s.spec == name)


def _counts(s) -> dict:
    return {"units": s.units, "required": s.statuses_required, **s.breakdown,
            "also": s.row_also_statuses, **{f"u_{k}": v for k, v in s.uncovered_breakdown.items()},
            "outside": sum(s.outside_required.values()), "declared": s.declared}


BASELINE = {"units": 2, "required": 12, "row": 5, "unit": 0, "unreachable": 1,
            "unexpressible": 0, "not_evaluated": 0, "uncovered": 6, "also": 1,
            "u_partial": 4, "u_default_only": 0, "u_unattributed": 2,
            "outside": 1, "declared": 13}


def _run(root: Path, **kw):
    return run_coverage(root, **kw)


def _diff(before: dict, after: dict) -> dict:
    return {k: after[k] - before[k] for k in before if after[k] != before[k]}


# ------------------------------------------------------------------ baseline ---

def test_the_baseline_counts(tmp_path):
    report = _run(_project(tmp_path))
    s = _screen_result(report)
    assert _counts(s) == BASELINE
    assert s.contracted_methods == 1 and s.vm_methods == 2
    assert s.methods_without_endpoint == 1
    kinds = {(u["method"], u["op"]): (u["kind"], u["statuses"]) for u in s.uncovered}
    assert kinds == {
        ("approve", "setApproval"): ("partial", ["401", "403", "404"]),
        ("approve", "getItem"): ("partial", ["200"]),
        (None, "getOther"): ("unattributed", ["200", "500"]),
    }
    assert _block(report).exit == cc.EXIT_UNCOVERED and _block(report).verdict == "uncovered"
    assert report.exit == cc.EXIT_UNCOVERED


def test_the_text_and_json_carry_the_same_numbers(tmp_path):
    report = _run(_project(tmp_path))
    text = "\n".join(cc.format_text(report))
    assert ("statuses required 12 = row 5 (alsoStatuses 1) + unit 0 + unreachable 1 + "
            "unexpressible 0 + not-evaluated 0 + uncovered 6") in text
    assert "units 2  contracted methods 1 of 2" in text
    data = cc.to_json(report)
    web = next(p for p in data["platforms"] if p["platform"] == "web")
    assert web["screens"][0]["breakdown"]["uncovered"] == 6
    assert web["verdict"] == "uncovered" and data["exit"] == 1


# ---------------------------------------------------------------- red-checks ---

def _mutated(tmp_path, mutate) -> dict:
    spec = _screen()
    mutate(spec)
    return _counts(_screen_result(_run(_project(tmp_path, spec))))


def test_overlapping_routes_are_info_not_an_error(tmp_path):
    openapi = copy.deepcopy(_OPENAPI)
    openapi["paths"]["/api/items/export"] = {"get": {"operationId": "exportItems",
                                                     "responses": {"200": {}}}}
    mocks = copy.deepcopy(_MOCKS)
    mocks["exportItems"] = ("GET", "/api/items/export", {"default": {"status": 200}})
    spec = _screen()
    spec["dataFlow"]["repositories"][0]["methods"].append(
        {"name": "exportItems", "endpoint": "GET /api/items/export"})
    s = _screen_result(_run(_project(tmp_path, spec, openapi=openapi, mocks=mocks)))
    assert s.info["route_overlaps"] == 1
    assert not s.declaration_errors
    assert any("recorded as 'exportItems'" in note for note in s.notes)


def test_i_deleting_the_only_row_for_a_status_uncovers_it(tmp_path):
    after = _mutated(tmp_path, lambda s: s["branchContracts"]["methods"]["approve"]["branches"].pop(3))
    assert _diff(BASELINE, after) == {"row": -1, "uncovered": 1, "u_partial": 1}


def test_ii_deleting_every_row_that_reaches_an_op_moves_it_to_unattributed(tmp_path):
    """The (M,E) unit leaves the audit; the bound (generated tests) is the
    other half of this red-check and is run in test_branch_act_window_and_bound."""
    def drop(spec):
        branches = spec["branchContracts"]["methods"]["approve"]["branches"]
        del branches[0:2]
        del spec["branchContracts"]["methods"]["approve"]["excludedOutcomes"]
    after = _mutated(tmp_path, drop)
    assert after["units"] == 1
    assert after["u_unattributed"] == BASELINE["u_unattributed"] + 3   # getItem 200 404 500


def test_iii_renaming_a_scenario_changes_nothing(tmp_path):
    mocks = copy.deepcopy(_MOCKS)
    scenarios = mocks["setApproval"][2]
    scenarios["conflict"] = scenarios.pop("error_409")
    spec = _screen()
    spec["branchContracts"]["methods"]["approve"]["branches"][3]["when"]["api.setApproval"] = "conflict"
    s = _screen_result(_run(_project(tmp_path, spec, mocks=mocks)))
    assert _counts(s) == BASELINE


def test_iv_a_second_row_for_the_same_status_is_not_counted_twice(tmp_path):
    mocks = copy.deepcopy(_MOCKS)
    mocks["setApproval"][2]["conflict"] = {"status": 409, "body": {}}
    spec = _screen()
    spec["branchContracts"]["methods"]["approve"]["branches"].append(
        {"when": {"api.setApproval": "conflict"}, "then": {"data.banner": "conflict"}})
    with_two = _counts(_screen_result(_run(_project(tmp_path / "two", spec, mocks=mocks))))
    assert with_two == BASELINE
    spec["branchContracts"]["methods"]["approve"]["branches"].pop(3)
    with_one = _counts(_screen_result(_run(_project(tmp_path / "one", spec, mocks=mocks))))
    assert with_one == BASELINE


def test_v_without_branch_contracts_everything_is_unattributed(tmp_path):
    after = _mutated(tmp_path, lambda s: s.pop("branchContracts"))
    assert after["units"] == 0 and after["row"] == 0
    assert after["uncovered"] == after["required"] == after["u_unattributed"]
    # Each op's statuses once: setApproval 7 + getItem 3 (default outside) + getOther 2.
    assert after["required"] == 12 and after["outside"] == 1


def test_vi_the_route_default_scenario_is_not_a_row(tmp_path):
    mocks = copy.deepcopy(_MOCKS)
    method, path, scenarios = mocks["setApproval"]
    root = _project(tmp_path, mocks=mocks)
    mock_file = root / "tests/mocks/generated/setApproval.mock.json"
    data = json.loads(mock_file.read_text())
    data["activeScenario"] = "error_500"
    mock_file.write_text(json.dumps(data))
    assert _counts(_screen_result(_run(root))) == BASELINE


def test_vii_not_called_on_the_covering_row_uncovers_its_status(tmp_path):
    def mute(spec):
        spec["branchContracts"]["methods"]["approve"]["branches"][3]["then"][
            "api.setApproval"] = "not-called"
    after = _mutated(tmp_path, mute)
    assert _diff(BASELINE, after) == {"row": -1, "uncovered": 1, "u_partial": 1}


def test_a_row_that_only_says_the_op_was_reached_answers_nothing(tmp_path):
    """A `then` with nothing beyond the op's own reach is not an answer: the
    status would be "covered" by a row that asserts no outcome at all."""
    def empty(spec):
        spec["branchContracts"]["methods"]["approve"]["branches"].append(
            {"when": {"api.setApproval": "error_401"}, "then": {"api.setApproval": "called"}})
    after = _mutated(tmp_path, empty)
    assert after == BASELINE


def test_ix_a_row_and_an_exclusion_for_one_status_is_an_error(tmp_path):
    def both(spec):
        spec["branchContracts"]["methods"]["approve"]["excludedOutcomes"]["api.setApproval"] = {
            "409": {"by": "unit", "reason": "tested in the view model's unit tests"}}
    spec = _screen()
    both(spec)
    report = _run(_project(tmp_path / "same", spec))
    s = _screen_result(report)
    assert any("both a row and an excludedOutcomes" in e["message"] for e in s.declaration_errors)
    assert _block(report).exit == cc.EXIT_UNCOVERED

    # The pair: the row on ios only, the exclusion on web only -> no conflict.
    spec = _screen()
    spec["branchContracts"]["methods"]["approve"]["branches"][3]["platforms"] = ["ios"]
    spec["branchContracts"]["methods"]["approve"]["excludedOutcomes"]["api.setApproval"] = {
        "409": {"by": "unit", "reason": "r", "platforms": ["web"]}}
    report = _run(_project(tmp_path / "split", spec))
    for platform in ("web", "ios"):
        assert not _screen_result(report, platform).declaration_errors, platform
    assert _screen_result(report, "web").breakdown["unit"] == 1
    assert _screen_result(report, "ios").breakdown["unit"] == 0


def test_x_a_use_case_call_names_the_caller_and_changes_no_count(tmp_path):
    def calls(spec):
        spec["dataFlow"]["useCases"] = [{"name": "OtherUseCase", "methods": [
            {"name": "refresh", "calls": ["DetailRepository.getOther"]}]}]
    spec = _screen()
    calls(spec)
    s = _screen_result(_run(_project(tmp_path, spec)))
    assert _counts(s) == BASELINE
    other = next(u for u in s.uncovered if u["op"] == "getOther")
    assert other["callers"] == ["OtherUseCase.refresh"]


def test_xi_a_range_key_answers_only_what_the_numbers_leave(tmp_path):
    openapi = copy.deepcopy(_OPENAPI)
    openapi["paths"]["/api/items/{id}"]["get"]["responses"]["4XX"] = {}
    mocks_a = copy.deepcopy(_MOCKS)
    mocks_a["getItem"][2]["error_418"] = {"status": 418, "body": {}}
    a = _screen_result(_run(_project(tmp_path / "a", openapi=openapi, mocks=mocks_a)))
    item_a = next(u for u in a.uncovered if u["op"] == "getItem")
    assert "4XX" in item_a["statuses"]                      # (A) a 418 scenario exists
    b = _screen_result(_run(_project(tmp_path / "b", openapi=openapi)))
    item_b = next(u for u in b.uncovered if u["op"] == "getItem")
    assert "4XX" not in item_b["statuses"]                  # (B) only the numbers
    assert b.outside_required["na_no_scenario"] == 1
    assert a.breakdown["row"] == b.breakdown["row"] == BASELINE["row"]   # 404 stays a row


def test_xii_adding_a_status_to_also_statuses_answers_it(tmp_path):
    def more(spec):
        spec["branchContracts"]["methods"]["approve"]["branches"][2]["alsoStatuses"][
            "api.setApproval"].append("403")
    after = _mutated(tmp_path, more)
    assert _diff(BASELINE, after) == {"row": 1, "also": 1, "uncovered": -1, "u_partial": -1}


def test_xiii_a_response_path_the_status_body_lacks_is_not_evaluated(tmp_path):
    mocks = copy.deepcopy(_MOCKS)
    mocks["setApproval"][2]["error_429"] = {"status": 429, "body": {}}   # no `message`

    def ref(spec):
        spec["branchContracts"]["methods"]["approve"]["branches"][2]["then"][
            "data.bannerText"] = "@response.message"
    spec = _screen()
    ref(spec)
    report = _run(_project(tmp_path, spec, mocks=mocks))
    s = _screen_result(report)
    assert _diff(BASELINE, _counts(s)) == {"row": -1, "also": -1, "not_evaluated": 1}
    assert any("[+429 via error_429]" in e["message"] for e in s.not_evaluated)


def test_xvi_arrangement_decides_whether_two_answers_conflict(tmp_path):
    def with_explicit_429(same_arrangement: bool):
        spec = _screen()
        branches = spec["branchContracts"]["methods"]["approve"]["branches"]
        row = {"when": {"api.setApproval": "error_429"}, "then": {"data.banner": "slow"}}
        if not same_arrangement:
            row["when"]["data.retrying"] = True
        branches.append(row)
        return spec
    same = _screen_result(_run(_project(tmp_path / "same", with_explicit_429(True))))
    assert any("two answers to one question" in e["message"] for e in same.declaration_errors)
    differs = _screen_result(_run(_project(tmp_path / "differs", with_explicit_429(False))))
    assert not differs.declaration_errors
    assert differs.info["also_statuses_arrange_differs"] == 1


def test_xix_unreached_ops_need_a_row_on_the_platform(tmp_path):
    spec = _screen()
    spec["branchContracts"]["unreachedOps"] = {"api.getOther": {"reason": "the parent calls it"}}
    # Without a row on web the exclusion would be stale there — another error.
    del spec["branchContracts"]["methods"]["approve"]["excludedOutcomes"]
    for branch in spec["branchContracts"]["methods"]["approve"]["branches"]:
        branch["platforms"] = ["ios"]
    report = _run(_project(tmp_path / "a", spec))
    web = _screen_result(report, "web")
    assert any("no row of this screen is active on web" in e["message"]
               for e in web.declaration_errors)
    ios = _screen_result(report, "ios")
    assert not ios.declaration_errors
    assert ios.outside_required["unreached_op"] == 2
    # The pair: limited to ios, the declaration is not read on web at all.
    spec["branchContracts"]["unreachedOps"]["api.getOther"]["platforms"] = ["ios"]
    web = _screen_result(_run(_project(tmp_path / "b", spec)), "web")
    assert not web.declaration_errors


def test_xx_a_platform_no_screen_exists_on_is_empty(tmp_path):
    spec = _screen()
    spec["metadata"]["platforms"] = ["ios"]
    report = _run(_project(tmp_path, spec))
    web = _block(report, "web")
    assert web.exit == cc.EXIT_PASS and web.verdict == "empty"
    s = _screen_result(report, "web")
    # setApproval 7 + getItem 4 (default included) + getOther 2.
    assert s.platform_excluded and s.outside_required["na_platform_excluded"] == 13


# ------------------------------------------------------------ app, and exits ---

_APP = {"type": "app_contracts_spec", "metadata": {"name": "app", "description": "d"},
        "unitContracts": [{"target": "ApiClient", "cases": [{"name": "request_on401_logsOut"}]}],
        "apiOutcomeRules": [{"id": "logout", "statuses": ["401"], "sideCalls": ["postLogout"],
                             "verifiedBy": ["request_on401_logsOut"], "reason": "r"}]}


def test_a_resolvable_side_call_is_no_error(tmp_path):
    report = _run(_project(tmp_path, app=_APP))
    assert report.app_errors == [] and report.rules == 1


def test_an_unknown_or_synthesized_side_call_is_an_error(tmp_path):
    app = copy.deepcopy(_APP)
    app["apiOutcomeRules"][0]["sideCalls"] = ["noSuchOperation"]
    report = _run(_project(tmp_path / "unknown", app=app))
    assert "no operation in mock.swagger" in report.app_errors[0]["message"]
    assert report.exit == cc.EXIT_UNCOVERED

    openapi = copy.deepcopy(_OPENAPI)
    del openapi["paths"]["/api/logout"]["post"]["operationId"]
    from jsonui_test_cli.mock.openapi import _fallback_operation_id
    app["apiOutcomeRules"][0]["sideCalls"] = [_fallback_operation_id("post", "/api/logout")]
    report = _run(_project(tmp_path / "synth", app=app, openapi=openapi))
    assert "synthesized" in report.app_errors[0]["message"]


@pytest.mark.parametrize("breakage, reason", [
    (lambda root: (root / "jui.config.json").write_text(json.dumps(
        {"spec_directory": "docs/screens/json",
         "mock": {"swagger": ["docs/api/api.json"], "mockDir": "tests/mocks"}})), "platforms"),
    (lambda root: (root / "docs/api/api.json").unlink(), "does not resolve"),
    (lambda root: (root / "tests/mocks").rename(root / "tests/elsewhere"), "mockDir"),
])
def test_what_stops_it_from_starting(tmp_path, breakage, reason):
    root = _project(tmp_path)
    breakage(root)
    with pytest.raises(CannotStart, match=reason):
        _run(root)


def test_the_same_route_in_two_documents_stops_it(tmp_path):
    root = _project(tmp_path)
    _write(root / "docs/api/second.json", _OPENAPI)
    config = json.loads((root / "jui.config.json").read_text())
    config["mock"]["swagger"].append("docs/api/second.json")
    (root / "jui.config.json").write_text(json.dumps(config))
    with pytest.raises(CannotStart, match="declared by both"):
        _run(root)


def test_a_clean_screen_passes(tmp_path):
    openapi = {"openapi": "3.0.0", "paths": {"/api/items/{id}": {"get": {
        "operationId": "getItem", "responses": {"200": {}, "404": {}}}}}}
    spec = _screen()
    spec["dataFlow"]["repositories"][0]["methods"] = [
        {"name": "getItem", "endpoint": "GET /api/items/{id}"}]
    spec["branchContracts"]["methods"] = {"approve": {"branches": [
        {"when": {"api.getItem": "default"}, "then": {"data.status": "ok"}},
        {"when": {"api.getItem": "error_404"}, "then": {"transition": "back"}}]}}
    report = _run(_project(tmp_path, spec, openapi=openapi))
    assert _block(report).exit == cc.EXIT_PASS and _block(report).verdict == "pass"
    assert _counts(_screen_result(report))["required"] == 2


def _clean(extra_api_endpoints=(), extra_methods=()):
    """The clean screen (exit 0), with endpoints added to its dataFlow."""
    openapi = {"openapi": "3.0.0", "paths": {
        "/api/items/{id}": {"get": {"operationId": "getItem", "responses": {"200": {}, "404": {}}}},
        "/api/tags": {"get": {"operationId": "getTags", "responses": {"200": {}, "403": {}}}}}}
    mocks = {"getItem": _MOCKS["getItem"],
             "getTags": ("GET", "/api/tags", {"default": {"status": 200, "body": {}},
                                                  "error_403": {"status": 403, "body": {}}})}
    spec = _screen()
    spec["dataFlow"]["repositories"][0]["methods"] = [
        {"name": "getItem", "endpoint": "GET /api/items/{id}"}, *extra_methods]
    spec["dataFlow"]["apiEndpoints"] = [{"method": "GET", "path": "/api/items/{id}"},
                                        *extra_api_endpoints]
    spec["branchContracts"]["methods"] = {"approve": {"branches": [
        {"when": {"api.getItem": "default"}, "then": {"data.status": "ok"}},
        {"when": {"api.getItem": "error_404"}, "then": {"transition": "back"}}]}}
    return spec, openapi, mocks


def test_xxiii_c_an_endpoint_only_in_api_endpoints_is_named_and_unmeasured(tmp_path):
    """Design v4.8 §2.2 / §4 #34: `apiEndpoints` alone routes nothing, so a call
    to the endpoint is `(unmatched)` in every generated test. Coverage names it
    as an E and keeps the verdict off `pass` — the "0 uncovered" it would print
    otherwise is a count that never looked at this endpoint."""
    spec, openapi, mocks = _clean([{"method": "GET", "path": "/api/tags"}])
    report = _run(_project(tmp_path, spec, openapi=openapi, mocks=mocks))
    s = _screen_result(report)
    assert s.na_endpoints["unbound"] == 1
    assert s.unbound_endpoints == ["GET /api/tags"]
    assert any("GET /api/tags is in dataFlow.apiEndpoints" in n for n in s.notes)
    assert _counts(s)["required"] == 2 and s.breakdown["uncovered"] == 0
    assert _block(report).exit == cc.EXIT_UNMEASURED and _block(report).verdict == "unmeasured"
    assert "unbound endpoint 1" in "\n".join(cc.format_text(report))
    web = next(p for p in cc.to_json(report)["platforms"] if p["platform"] == "web")
    assert web["screens"][0]["na_endpoints"]["unbound"] == 1
    assert web["screens"][0]["unbound_endpoints"] == ["GET /api/tags"]


def test_xxiii_c_control_binding_the_endpoint_brings_it_into_the_count(tmp_path):
    """The pair: the same endpoint as a repository method's endpoint is an
    operation like any other — no longer unbound, its statuses are required,
    and with no row reaching it they are unattributed."""
    spec, openapi, mocks = _clean([{"method": "GET", "path": "/api/tags"}],
                                  [{"name": "getTags", "endpoint": "GET /api/tags"}])
    report = _run(_project(tmp_path, spec, openapi=openapi, mocks=mocks))
    s = _screen_result(report)
    assert s.na_endpoints["unbound"] == 0 and s.unbound_endpoints == []
    assert _counts(s)["required"] == 4
    assert s.uncovered_breakdown["unattributed"] == 2
    assert _block(report).exit == cc.EXIT_UNCOVERED


def test_xxiii_c_boundary_a_renamed_path_variable_is_the_same_endpoint(tmp_path):
    """Matched by route: `{item_id}` in apiEndpoints and `{id}` in the
    method's endpoint name one route, so nothing is unbound and the screen
    passes as it did without the extra line."""
    spec, openapi, mocks = _clean([{"method": "GET", "path": "/api/items/{item_id}"}])
    report = _run(_project(tmp_path, spec, openapi=openapi, mocks=mocks))
    assert _screen_result(report).na_endpoints["unbound"] == 0
    assert _block(report).exit == cc.EXIT_PASS


def test_the_command_line_exits_with_the_composed_code(tmp_path):
    root = _project(tmp_path)
    done = subprocess.run(
        [sys.executable, "-m", "jsonui_test_cli.cli", "contracts", "coverage", "--json"],
        cwd=root, capture_output=True, text=True,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1]), "PATH": "/usr/bin:/bin"})
    assert done.returncode == 1, done.stderr
    assert json.loads(done.stdout)["exit"] == 1
    broken = subprocess.run(
        [sys.executable, "-m", "jsonui_test_cli.cli", "contracts", "coverage"],
        cwd=tmp_path / "docs", capture_output=True, text=True,
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1]), "PATH": "/usr/bin:/bin"})
    assert broken.returncode == 2 and "cannot start" in broken.stderr
