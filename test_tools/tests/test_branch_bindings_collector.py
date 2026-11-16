"""What a generated branch test is made of, decided before anything is emitted.

The generator now binds a screen through one collector: routes, then the
`alsoStatuses` copies, then argument bindings, then `@response.*`, then a
trial arrangement of every row. `contracts coverage` needs every row that CAN
be judged, so the collector collects instead of stopping at the first error;
the generator raises what was collected. Around it:

- **Effective platforms.** `jui.config.json` platforms ∩ the screen's
  `metadata.platforms`, one function for the generator and the coverage
  command. A platform outside it generates nothing and expects nothing, and
  a binding error it would never have used does not stop it.
- **Overlapping routes are refused.** Recorded calls go to the first route
  whose pattern matches, so `/items/export` beside `/items/{id}` makes every
  count on one op describe the other.
- **`alsoStatuses` copies.** Chosen by the status a scenario RETURNS, never
  inserted into the branches (numbers stay put), and refused when they
  cannot mean anything: the row's own status, a status no scenario returns,
  a `@response.*` the status's body cannot answer.
- **App rules.** Read from the project's config; two app specs declaring
  rules, or a malformed rule, stop generation rather than silently admit
  nothing.

These arms read generated text and the collector's result; the web test
file is executed end to end in `test_branch_act_window_and_bound.py`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli.branch_tests import BranchTestGenerationError


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _mock(root: Path, name: str, method: str, path: str, scenarios: dict,
          operation_id: str | None = None, generated: bool = True) -> None:
    source = {"method": method, "path": path}
    if operation_id:
        source["operationId"] = operation_id
    where = "tests/mocks/generated" if generated else "tests/mocks"
    _write(root / where / f"{name}.mock.json",
           {"source": source, "activeScenario": next(iter(scenarios)),
            "scenarios": scenarios})


def _project(root: Path, branches: list, *, endpoints=None, metadata=None,
             config_platforms=("web", "android", "ios"), app_specs=()) -> Path:
    endpoints = endpoints or [("submitOrder", "POST /api/orders")]
    config = {"spec_directory": "docs/screens/json"}
    if config_platforms is not None:
        config["platforms"] = list(config_platforms)
    _write(root / "jui.config.json", config)
    spec = {
        "type": "screen_spec",
        "metadata": {"name": "checkout", **(metadata or {})},
        "dataFlow": {
            "viewModel": {"methods": [{"name": "submit"}]},
            "repositories": [{"name": "OrderRepository", "methods": [
                {"name": name, "endpoint": endpoint} for name, endpoint in endpoints]}],
        },
        "branchContracts": {"methods": {"submit": {"branches": branches}}},
    }
    _write(root / "docs/screens/json/checkout.spec.json", spec)
    for i, app in enumerate(app_specs):
        _write(root / f"docs/screens/json/app{i}.spec.json", app)
    return root


_ORDERS = {
    "default": {"status": 200, "body": {}},
    "error_500": {"status": 500, "body": {"message": "server"}},
    "error_429": {"status": 503, "body": {"message": "misnamed"}},   # returns 503
    "too_many": {"status": 429, "body": {"message": "slow down"}},
    "error_401": {"status": 401, "body": {}},
}


def _orders_mock(root: Path, scenarios=None) -> None:
    _mock(root, "orders", "POST", "/api/orders", scenarios or _ORDERS, "submitOrder")


def _generate(root: Path, platform="web", **kw):
    extra = {}
    if platform == "android":
        extra = {"package": "com.example.app", "out_dir": "app/src/test/java",
                 "harness_dir": "app/src/test/java"}
    elif platform == "ios":
        extra = {"module": "app", "out_dir": "Tests/Generated",
                 "harness_dir": "Tests/Generated"}
    config = json.loads((root / "jui.config.json").read_text())
    return bt.generate_branch_tests(
        "checkout", root, platform=platform,
        config_platforms=config.get("platforms"), **extra, **kw)


# ---------------------------------------------------------------- platforms ---

@pytest.mark.parametrize("config, metadata, expected", [
    (None, None, ("web", "android", "ios")),
    (["ios", "web"], None, ("web", "ios")),
    (None, ["android"], ("android",)),
    (["ios", "web"], ["web", "android"], ("web",)),
    (["web"], [], ()),
])
def test_effective_platforms(config, metadata, expected):
    assert bt.effective_platforms(config, metadata) == expected


def test_an_excluded_platform_generates_nothing_and_retires_what_it_made(tmp_path):
    root = _project(tmp_path, [{"when": {"api.submitOrder": "default"},
                                "then": {"data.status": "done"}}])
    _orders_mock(root)
    first = _generate(root)
    assert first.test_file.exists()
    # The screen stops existing on web.
    spec_path = root / "docs/screens/json/checkout.spec.json"
    spec = json.loads(spec_path.read_text())
    spec["metadata"]["platforms"] = ["ios"]
    spec_path.write_text(json.dumps(spec))

    checked = _generate(root, check=True)
    assert checked.platform_excluded and not checked.platform_applicable
    assert checked.stale == [first.test_file] and first.test_file.exists()

    done = _generate(root)
    assert done.platform_excluded and done.stale == [first.test_file]
    assert not first.test_file.exists()


def test_the_config_alone_can_exclude(tmp_path):
    root = _project(tmp_path, [{"when": {"api.submitOrder": "default"},
                                "then": {"data.status": "done"}}],
                    config_platforms=["ios"])
    _orders_mock(root)
    report = _generate(root)
    assert report.platform_excluded
    assert not (root / "tests/unit/generated").exists()


def test_a_binding_error_on_an_excluded_platform_does_not_stop_it(tmp_path):
    root = _project(tmp_path, [{"when": {"api.submitOrder": "no_such_scenario"},
                                "then": {"data.status": "done"}}],
                    metadata={"platforms": ["ios"]})
    _orders_mock(root)
    assert _generate(root).platform_excluded       # web: nothing to bind
    with pytest.raises(BranchTestGenerationError, match="no_such_scenario"):
        _generate(root, platform="ios")


# -------------------------------------------------------------- overlapping ---

def _overlap_project(root: Path) -> Path:
    root = _project(root, [{"when": {"api.getItem": "default"},
                            "then": {"data.status": "done"}}],
                    endpoints=[("getItem", "GET /api/items/{item_id}"),
                               ("exportItems", "GET /api/items/export")])
    _mock(root, "item", "GET", "/api/items/{item_id}", {"default": {"status": 200}})
    _mock(root, "export", "GET", "/api/items/export", {"default": {"status": 200}})
    return root


def test_overlapping_routes_are_ordered_the_way_mock_serve_orders_them(tmp_path):
    """red-check xxi (design v4.2): `/items/{id}` beside `/items/export` in one
    spec generates; the static path is tried first, as `mock serve` tries it,
    and the pair and the side that wins are printed rather than refused."""
    report = _generate(_overlap_project(tmp_path))
    text = report.test_file.read_text()
    assert text.index('op: "exportItems"') < text.index('op: "getItem"')
    assert report.route_overlaps == [
        "route overlap: GET /api/items/export ('exportItems') and "
        "/api/items/{item_id} ('getItem') — a call both match is recorded as "
        "'exportItems' (the order mock serve uses)"]


def test_the_generator_and_mock_serve_share_one_order():
    from jsonui_test_cli.mock import generate
    paths = ["/a/{id}", "/a/export", "/b", "/a/{id}/x", "/a/list"]
    assert sorted(paths, key=generate.route_match_order) == [
        "/a/export", "/a/list", "/b", "/a/{id}", "/a/{id}/x"]


def test_both_follow_a_changed_order(tmp_path, monkeypatch):
    """The order is ONE function: replace it, and mock serve and the generated
    ROUTES both follow. A copy of the rule that happens to agree today (a
    lambda in the server, a sort of its own in the generator) keeps the old
    order here and fails — agreement by value cannot show that."""
    from jsonui_test_cli.mock import generate, server
    reverse = lambda path: (not ("{" in path), path)   # params first
    monkeypatch.setattr(generate, "route_match_order", reverse)
    monkeypatch.setattr(server, "route_match_order", reverse)

    root = _overlap_project(tmp_path)
    store = server.MockStore.load(root / "tests/mocks")
    served = [e.path for e in store.endpoints]
    assert served.index("/api/items/{item_id}") < served.index("/api/items/export")
    text = _generate(root).test_file.read_text()
    assert text.index('op: "getItem"') < text.index('op: "exportItems"')


def test_a_call_both_routes_match_is_recorded_as_the_winner(tmp_path):
    """Executed: the generated ROUTES in the runtime record `/export` as the
    export op and `/7` as the item — the attribution `mock serve` gives."""
    from tests import _toolchain as tc
    import subprocess
    tc.tool("node")
    report = _generate(_overlap_project(tmp_path / "p"))
    text = report.test_file.read_text()
    routes = text[text.index("const ROUTES: RouteSpec[] = ["):text.index("];") + 2]
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / "runtime.ts").write_text(bt.RUNTIME_TS, encoding="utf-8")
    (probe / "probe.ts").write_text(
        'import { installFetchMock, type RouteSpec } from "./runtime.ts";\n'
        + routes + "\n"
        + 'const rec = installFetchMock(ROUTES);\n'
        + 'await fetch("https://x.test/api/items/export");\n'
        + 'await fetch("https://x.test/api/items/7");\n'
        + 'console.log(JSON.stringify(rec.calls.map((c) => [c.path, c.op])));\n'
        + 'rec.restore();\n', encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts"],
                         cwd=probe, capture_output=True, text=True, timeout=120)
    assert json.loads(run.stdout.strip().splitlines()[-1]) == [
        ["/api/items/export", "exportItems"], ["/api/items/7", "getItem"]], run.stderr


def test_routes_that_do_not_overlap_are_accepted(tmp_path):
    """The control: a different method, and a different segment count."""
    root = _project(tmp_path, [{"when": {"api.getItem": "default"},
                                "then": {"data.status": "done"}}],
                    endpoints=[("getItem", "GET /api/items/{item_id}"),
                               ("postExport", "POST /api/items/export"),
                               ("getAll", "GET /api/items")])
    _mock(root, "item", "GET", "/api/items/{item_id}", {"default": {"status": 200}})
    _mock(root, "export", "POST", "/api/items/export", {"default": {"status": 200}})
    _mock(root, "all", "GET", "/api/items", {"default": {"status": 200}})
    assert _generate(root).test_file.exists()


def test_two_spellings_of_one_path_template_are_one_endpoint(tmp_path):
    root = _project(tmp_path, [
        {"when": {"api.getItem": "default"}, "then": {"data.status": "done"}},
        {"when": {"api.fetchItem": "default"}, "then": {"data.status": "done"}}],
        endpoints=[("getItem", "GET /api/items/{item_id}"),
                   ("fetchItem", "GET /api/items/{id}")])
    _mock(root, "item", "GET", "/api/items/{item_id}", {"default": {"status": 200}})
    _mock(root, "item2", "GET", "/api/items/{id}", {"default": {"status": 200}},
          generated=False)
    with pytest.raises(BranchTestGenerationError, match="both name"):
        _generate(root)


# ------------------------------------------------------------ alsoStatuses ---

def _also_rows(root: Path, branches: list, platform="web"):
    spec = json.loads((root / "docs/screens/json/checkout.spec.json").read_text())
    methods = spec["branchContracts"]["methods"]
    mocks = bt.index_mock_files(root / "tests/mocks")
    return bt.collect_bindings(spec, methods, mocks, root / "tests/mocks", platform)


def test_the_copy_is_served_the_scenario_that_returns_the_status(tmp_path):
    branches = [{"when": {"api.submitOrder": "error_500"},
                 "alsoStatuses": {"api.submitOrder": ["429"]},
                 "then": {"data.status": "failed"}}]
    root = _project(tmp_path, branches)
    _orders_mock(root)
    found = _also_rows(root, branches)
    assert not found.errors, found.errors
    copies = [r for r in found.rows if r.also]
    # `error_429` returns 503, so it is not a 429 scenario; `too_many` is.
    assert [(r.number, r.also) for r in copies] == [(1, ("429", "too_many"))]
    assert copies[0].branch["when"]["api.submitOrder"] == "too_many"


def test_error_name_is_preferred_when_it_returns_the_status(tmp_path):
    scenarios = dict(_ORDERS, error_429={"status": 429, "body": {}})
    branches = [{"when": {"api.submitOrder": "error_500"},
                 "alsoStatuses": {"api.submitOrder": ["429"]},
                 "then": {"data.status": "failed"}}]
    root = _project(tmp_path, branches)
    _orders_mock(root, scenarios)
    copies = [r for r in _also_rows(root, branches).rows if r.also]
    assert copies[0].also == ("429", "error_429")


def test_copies_keep_the_numbers_of_the_rows_after_them(tmp_path):
    branches = [
        {"when": {"api.submitOrder": "error_500"},
         "alsoStatuses": {"api.submitOrder": ["429", "401"]},
         "then": {"data.status": "failed"}},
        {"when": {"api.submitOrder": "default"}, "then": {"data.status": "done"}},
    ]
    root = _project(tmp_path, branches)
    _orders_mock(root)
    text = _generate(root).test_file.read_text()
    titles = [json.loads(t) for t in re.findall(r'^  it\((".*"), async', text, re.M)]
    assert titles == [
        'branch 1: api.submitOrder="error_500"',
        'branch 1: api.submitOrder="error_500" [+429 via too_many]',
        'branch 1: api.submitOrder="error_500" [+401 via error_401]',
        'branch 2: api.submitOrder="default"',
    ], titles
    report = _generate(root)
    assert report.declared_branches == 2 and report.also_statuses_rows == 2
    kotlin = _generate(root, platform="android").test_file.read_text()
    assert "fun `submit branch 1 also 429`()" in kotlin
    assert "fun `submit branch 2`()" in kotlin


def test_the_expansion_does_not_depend_on_row_order(tmp_path):
    """red-check xv: reordering rows keeps the same set of copies."""
    a = {"when": {"api.submitOrder": "error_500"},
         "alsoStatuses": {"api.submitOrder": ["429"]}, "then": {"data.status": "failed"}}
    b = {"when": {"api.submitOrder": "default"}, "then": {"data.status": "done"}}
    c = {"when": {"api.submitOrder": "error_401"},
         "alsoStatuses": {"api.submitOrder": ["503"]}, "then": {"data.status": "gone"}}

    def copies(branches, where):
        root = _project(where, branches)
        _orders_mock(root)
        rows = _also_rows(root, branches).rows
        return {(json.dumps(r.branch["then"]), r.also) for r in rows if r.also}

    assert copies([a, b, c], tmp_path / "one") == copies([c, a, b], tmp_path / "two")


def test_the_rows_own_status_is_refused(tmp_path):
    branches = [{"when": {"api.submitOrder": "error_500"},
                 "alsoStatuses": {"api.submitOrder": ["500"]},
                 "then": {"data.status": "failed"}}]
    root = _project(tmp_path, branches)
    _orders_mock(root)
    errors = _also_rows(root, branches).errors
    assert [(e.kind, e.status) for e in errors] == [("self", "500")]
    with pytest.raises(BranchTestGenerationError, match="already serves"):
        _generate(root)


def test_a_status_no_scenario_returns_is_the_mocks_to_fix(tmp_path):
    branches = [{"when": {"api.submitOrder": "error_500"},
                 "alsoStatuses": {"api.submitOrder": ["418"]},
                 "then": {"data.status": "failed"}}]
    root = _project(tmp_path, branches)
    _orders_mock(root)
    errors = _also_rows(root, branches).errors
    assert [(e.kind, e.status, e.op) for e in errors] == [("no-scenario", "418", "submitOrder")]
    assert "add a scenario to the mock" in errors[0].message


def test_a_response_path_the_status_body_lacks_names_the_row_and_status(tmp_path):
    """red-check xiii: the 500 body has `message`, the 401 body does not."""
    branches = [{"when": {"api.submitOrder": "error_500"},
                 "alsoStatuses": {"api.submitOrder": ["401"]},
                 "then": {"data.errorText": "@response.message"}}]
    root = _project(tmp_path, branches)
    _orders_mock(root)
    found = _also_rows(root, branches)
    assert [(e.kind, e.status, e.op, e.branch_index) for e in found.errors] == [
        ("response", "401", "submitOrder", 0)]
    assert "[+401 via error_401]" in found.errors[0].message
    # The original row still binds — only the copy is refused.
    assert [r.also for r in found.rows] == [None]
    assert found.rows[0].branch["then"]["data.errorText"] == "server"
    with pytest.raises(BranchTestGenerationError, match=r"\[\+401 via error_401\]"):
        _generate(root)


def test_a_malformed_declaration_stops_generation(tmp_path):
    branches = [{"when": {"api.submitOrder": "error_500"},
                 "alsoStatuses": {"api.submitOrder": ["4XX"]},
                 "then": {"data.status": "failed"}}]
    root = _project(tmp_path, branches)
    _orders_mock(root)
    with pytest.raises(BranchTestGenerationError, match="alsoStatuses"):
        _generate(root)


# ----------------------------------------------------------------- collector ---

def test_errors_are_collected_across_rows(tmp_path):
    branches = [
        {"when": {"api.submitOrder": "missing_one"}, "then": {"data.status": "a"}},
        {"when": {"api.submitOrder": "missing_two"}, "then": {"data.status": "b"}},
        {"when": {"api.submitOrder": "default"}, "then": {"data.status": "ok"}},
    ]
    root = _project(tmp_path, branches)
    _orders_mock(root)
    found = _also_rows(root, branches)
    assert [e.branch_index for e in found.errors] == [0, 1]
    assert [r.number for r in found.rows] == [3]      # the good row still binds
    with pytest.raises(BranchTestGenerationError) as e:
        _generate(root)
    assert "2 binding error(s)" in str(e.value)
    assert "missing_one" in str(e.value) and "missing_two" in str(e.value)


def test_one_error_keeps_the_message_it_always_had(tmp_path):
    branches = [{"when": {"api.submitOrder": "missing_one"}, "then": {"data.status": "a"}}]
    root = _project(tmp_path, branches)
    _orders_mock(root)
    with pytest.raises(BranchTestGenerationError) as e:
        _generate(root)
    assert str(e.value).startswith("branches[0].when.api.submitOrder: scenario 'missing_one'")


# ----------------------------------------------------------------- app rules ---

def _app(rules, cases=("request_onTerminal401_postsLogout",)):
    return {"type": "app_contracts_spec", "metadata": {"name": "app", "description": "d"},
            "unitContracts": [{"target": "ApiClient",
                               "cases": [{"name": c} for c in cases]}],
            "apiOutcomeRules": rules}


_RULE = {"id": "session-end", "statuses": ["401"], "sideCalls": ["postLogout"],
         "verifiedBy": ["request_onTerminal401_postsLogout"], "reason": "r"}


def _rule_project(root: Path, app_specs, logout_id="postLogout"):
    branches = [
        {"when": {"api.submitOrder": "error_401"}, "then": {"data.status": "failed"}},
        {"when": {"api.submitOrder": "error_500"}, "then": {"data.status": "failed"}},
    ]
    root = _project(root, branches, app_specs=app_specs,
                    endpoints=[("submitOrder", "POST /api/orders"),
                               ("logout", "POST /api/logout")])
    _orders_mock(root)
    _mock(root, "logout", "POST", "/api/logout", {"default": {"status": 204}}, logout_id)
    return root


def _allowed(text: str) -> list:
    return [json.loads(a) for a in re.findall(r"rec\.unexpectedOps\((\[.*?\])\)", text)]


def test_a_rule_admits_its_side_call_only_for_its_statuses(tmp_path):
    root = _rule_project(tmp_path, [_app([_RULE])])
    assert _allowed(_generate(root).test_file.read_text()) == [
        ["logout", "submitOrder"], ["submitOrder"]]


def test_an_unresolvable_side_call_admits_nothing_and_raises_nothing(tmp_path):
    root = _rule_project(tmp_path, [_app([_RULE])], logout_id="someOtherId")
    assert _allowed(_generate(root).test_file.read_text()) == [
        ["submitOrder"], ["submitOrder"]]


def test_a_hand_written_mock_does_not_carry_the_operation_id(tmp_path):
    """Only a GENERATED file names the operation a side call refers to."""
    root = _rule_project(tmp_path, [_app([_RULE])], logout_id="unused")
    (root / "tests/mocks/generated/logout.mock.json").unlink()
    _mock(root, "logout", "POST", "/api/logout", {"default": {"status": 204}},
          "postLogout", generated=False)
    assert _allowed(_generate(root).test_file.read_text()) == [
        ["submitOrder"], ["submitOrder"]]


def test_two_app_specs_with_rules_stop_generation(tmp_path):
    root = _rule_project(tmp_path, [_app([_RULE]), _app([_RULE])])
    with pytest.raises(BranchTestGenerationError, match="more than one app contracts spec"):
        _generate(root)


def test_a_malformed_rule_stops_generation(tmp_path):
    root = _rule_project(tmp_path, [_app([dict(_RULE, statuses=["4XX"])])])
    with pytest.raises(BranchTestGenerationError, match="could not be read"):
        _generate(root)


def test_no_app_spec_means_no_rules_and_says_so(tmp_path):
    root = _rule_project(tmp_path, [])
    found = bt.find_app_contract_spec(root)
    assert found.rules == [] and "none" in found.note()
    assert _allowed(_generate(root).test_file.read_text()) == [
        ["submitOrder"], ["submitOrder"]]


# --------------------------------------------------- side routes (P2e(d)) ---
#
# A rule's sideCalls name operations the app's network layer makes around any
# call (a logout after a 401). A screen that does not declare the endpoint used
# to leave the call unmatched — a 599 no server returns — so admitting it meant
# every screen declaring the app's logout. The generator now serves such an
# operation as a SIDE route, under its operationId, with its mock's default
# scenario; admission is still by the rule's statuses.

def _side_project(root: Path, app_specs, *, declare_logout=False, logout_id="postLogout"):
    branches = [
        {"when": {"api.submitOrder": "error_401"}, "then": {"data.status": "failed"}},
        {"when": {"api.submitOrder": "error_500"}, "then": {"data.status": "failed"}},
    ]
    endpoints = [("submitOrder", "POST /api/orders")]
    if declare_logout:
        endpoints.append(("logout", "POST /api/logout"))
    root = _project(root, branches, app_specs=app_specs, endpoints=endpoints)
    _orders_mock(root)
    _mock(root, "logout", "POST", "/api/logout", {"default": {"status": 204}}, logout_id)
    return root


def _route_ops(text: str) -> list:
    return re.findall(r'\{ op: "([^"]+)", method: "\w+", pattern: "([^"]+)"', text)


def test_an_undeclared_side_call_becomes_a_side_route_admitted_by_status(tmp_path):
    root = _side_project(tmp_path, [_app([_RULE])])
    report = _generate(root)
    text = report.test_file.read_text()
    assert ("postLogout", "^/api/logout$") in _route_ops(text)
    assert report.side_routes == ["postLogout"]
    # The 401 row may call it; the 500 row may not (the ⊆ bound would name it).
    assert _allowed(text) == [["postLogout", "submitOrder"], ["submitOrder"]]


def test_a_declared_side_call_is_the_screens_own_route(tmp_path):
    root = _side_project(tmp_path, [_app([_RULE])], declare_logout=True)
    report = _generate(root)
    assert report.side_routes == []
    assert _allowed(report.test_file.read_text()) == [["logout", "submitOrder"], ["submitOrder"]]


def test_no_rule_no_side_route_and_the_same_file(tmp_path):
    """An app without apiOutcomeRules generates what it generated before."""
    with_rule = _side_project(tmp_path / "a", [_app([_RULE])])
    without = _side_project(tmp_path / "b", [])
    report = _generate(without)
    text = report.test_file.read_text()
    assert report.side_routes == [] and "postLogout" not in text
    # Control: the rule is what added it.
    assert "postLogout" in _generate(with_rule).test_file.read_text()


def test_an_unresolvable_side_call_adds_no_route(tmp_path):
    root = _side_project(tmp_path, [_app([_RULE])], logout_id="someOtherId")
    report = _generate(root)
    assert report.side_routes == []
    assert _allowed(report.test_file.read_text()) == [["submitOrder"], ["submitOrder"]]


def test_a_side_call_named_like_another_endpoint_stops_generation(tmp_path):
    """One op naming two endpoints would make every count on it describe both."""
    rule = dict(_RULE, sideCalls=["submitOrder"])
    root = _side_project(tmp_path, [_app([rule])], logout_id="submitOrder")
    # The orders mock also carries operationId submitOrder: two generated files
    # carry it, so it does not resolve — make only the logout one carry it.
    (root / "tests/mocks/generated/orders.mock.json").write_text(json.dumps({
        "source": {"method": "POST", "path": "/api/orders"},
        "activeScenario": "default", "scenarios": _ORDERS}), encoding="utf-8")
    with pytest.raises(BranchTestGenerationError, match="also this screen's name"):
        _generate(root)


@pytest.mark.parametrize("platform, needle", [
    ("android", 'RouteSpec("postLogout"'),
    ("ios", 'RouteSpec(op: "postLogout"'),
])
def test_the_side_route_reaches_every_platform(tmp_path, platform, needle):
    root = _side_project(tmp_path, [_app([_RULE])])
    report = _generate(root, platform=platform)
    assert report.side_routes == ["postLogout"]
    assert needle in report.test_file.read_text()
