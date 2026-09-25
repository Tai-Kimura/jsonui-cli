"""A request no declared route answers, and the app's side calls — RUN end to end.

Design v4.14–v4.15, P2e:

- **(a)** A request in the act window that no declared route answered got the
  runtime's 599, a response no server returns, so whatever the view model did
  next is made up. From the release `UNMATCHED_GATE_FROM` names, the generated
  test fails on it and names the request; before that release it prints a
  warning naming the request (and the release, when one is set). Unset, the
  warning promises no release.
- **(d)** An `apiOutcomeRules.sideCalls` operation the screen does not declare
  is served as a side route with its mock's default scenario, admitted only in
  the tests whose served statuses the rule names.

The shipping conditions these arms carry (design §6.1):

- xxxii: a row whose act hits an undeclared route is red and names it; the
  control declares the route in dataFlow and a mock, and it is green.
- xxxiv: an authenticated call's 401 row whose network layer posts logout,
  {rule, no rule} × {the 401 row, a non-401 row that also posts logout}: rule ×
  401 green (the side route answers), no rule × 401 red naming the request (a),
  rule × non-401 red naming the op (the ⊆ bound).

The web face is run the way test_branch_act_window_and_bound.py runs it: the
generated file as written, a hand-written harness, node, and a minimal
stand-in for vitest.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc
from tests.test_branch_act_window_and_bound import _HOOKS, _REGISTER, _VITEST

_RULE = {"id": "session-end-logout", "statuses": ["401"], "sideCalls": ["postLogout"],
         "verifiedBy": ["request_onTerminal401_postsLogout"],
         "reason": "the network layer posts logout on a terminal 401"}


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def _mock(root: Path, name: str, method: str, path: str, operation_id: str,
          scenarios: dict) -> None:
    _write(root / "tests/mocks/generated" / f"{name}.mock.json", {
        "source": {"method": method, "path": path, "operationId": operation_id},
        "activeScenario": "default", "scenarios": scenarios})


def _project(root: Path, *, rule: bool, declare_unknown: bool = False) -> Path:
    endpoints = [{"name": "submitOrder", "endpoint": "POST /api/orders"},
                 {"name": "getHistory", "endpoint": "GET /api/history"}]
    if declare_unknown:
        endpoints.append({"name": "getUnknown", "endpoint": "GET /api/unknown"})
    _write(root / "jui.config.json",
           {"spec_directory": "docs/screens/json", "platforms": ["web"]})
    _write(root / "docs/screens/json/checkout.spec.json", {
        "type": "screen_spec",
        "metadata": {"name": "checkout"},
        "dataFlow": {
            "viewModel": {"methods": [{"name": "submit"}, {"name": "refresh"}]},
            "repositories": [{"name": "OrderRepository", "methods": endpoints}],
        },
        "branchContracts": {"methods": {
            "submit": {"branches": [
                {"when": {"api.submitOrder": "error_401"}, "then": {"data.status": "failed"}},
                {"when": {"api.submitOrder": "error_500"}, "then": {"data.status": "failed"}},
            ]},
            "refresh": {"branches": [
                {"when": {"api.getHistory": "default"},
                 "then": {"data.status": "idle"}
                 | ({"api.getUnknown": "called"} if declare_unknown else {})},
            ]},
        }},
    })
    if rule:
        _write(root / "docs/screens/json/app_contracts.spec.json", {
            "type": "app_contracts_spec",
            "metadata": {"name": "app", "description": "d"},
            "unitContracts": [{"target": "ApiClient", "cases": [
                {"name": "request_onTerminal401_postsLogout"}]}],
            "apiOutcomeRules": [_RULE]})
    _mock(root, "orders", "POST", "/api/orders", "submitOrder", {
        "default": {"status": 200, "body": {}},
        "error_500": {"status": 500, "body": {}},
        "error_401": {"status": 401, "body": {}}})
    _mock(root, "logout", "POST", "/api/logout", "postLogout", {"default": {"status": 204}})
    _mock(root, "history", "GET", "/api/history", "getHistory",
          {"default": {"status": 200, "body": []}})
    _mock(root, "unknown", "GET", "/api/unknown", "getUnknown",
          {"default": {"status": 200, "body": {}}})
    return root


_HARNESS = '''import { applyDeclaredKeys } from "../generated/jsonui-branch-runtime";

class CheckoutViewModel {
  status = "idle";
  async submit() {
    const r = await fetch("https://api.test/api/orders", { method: "POST", body: "{}" });
    if (r.status === 401 || (LOGOUT_ON_500 && r.status === 500)) {
      // What an app's network layer does around a failed call.
      await fetch("https://api.test/api/logout", { method: "POST" });
    }
    this.status = r.ok ? "done" : "failed";
  }
  async refresh() {
    await fetch("https://api.test/api/history");
    await fetch("https://api.test/api/unknown");
  }
}

export function createHarness() {
  const vm = new CheckoutViewModel();
  return {
    vm,
    setState(state: Record<string, unknown>) { applyDeclaredKeys(vm, state); },
    readField(name: string) { return (vm as any)[name]; },
    expectTransition(_d: string) {},
    resolveString(key: string) { return key; },
  };
}
'''

_RUNNER = '''import { run } from "vitest";
await import("./tests/unit/generated/checkout.branches.test.ts");
await run();
'''


def _generate_and_run(root: Path, *, logout_on_500: bool = False):
    report = bt.generate_branch_tests("checkout", root, platform="web", config_platforms=["web"])
    _write(root / "tests/unit/branch-harness/checkout.ts",
           _HARNESS.replace("LOGOUT_ON_500", "true" if logout_on_500 else "false"))
    _write(root / "node_modules/vitest/package.json",
           '{"name": "vitest", "type": "module", "main": "index.js"}')
    _write(root / "node_modules/vitest/index.js", _VITEST)
    _write(root / "package.json", '{"type": "module"}')
    _write(root / "hooks.mjs", _HOOKS)
    _write(root / "register.mjs", _REGISTER)
    _write(root / "runner.mjs", _RUNNER)
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--import", "./register.mjs", "runner.mjs"],
        cwd=root, capture_output=True, text=True, timeout=120)
    rows = {}
    for line in run.stdout.splitlines():
        m = re.match(r"^(PASS|FAIL) (.+?)(?: :: (.*))?$", line)
        if m:
            rows[m.group(2)] = (m.group(1) == "PASS", m.group(3) or "")
    assert rows, f"no rows:\n{run.stdout}\n{run.stderr[:4000]}"
    return report, rows, run.stderr


def _row(rows: dict, method: str, number: int) -> tuple[bool, str]:
    hits = [v for name, v in rows.items() if f"checkout.{method} > branch {number}:" in name]
    assert len(hits) == 1, sorted(rows)
    return hits[0]


@pytest.fixture
def red(monkeypatch):
    """The gate at or below the running version: unmatched requests fail."""
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", "0.0.1")


# ------------------------------------------------------------------ xxxii ---

def test_xxxii_an_undeclared_route_in_the_act_window_is_red_and_named(tmp_path, red):
    tc.tool("node")
    _, rows, _ = _generate_and_run(_project(tmp_path, rule=True))
    passed, why = _row(rows, "refresh", 1)
    assert not passed and "GET https://api.test/api/unknown" in why, rows
    assert "reached no declared route" in why and "apiOrigins" in why, rows


def test_xxxii_control_declaring_the_route_makes_it_green(tmp_path, red):
    tc.tool("node")
    _, rows, _ = _generate_and_run(_project(tmp_path, rule=True, declare_unknown=True))
    assert _row(rows, "refresh", 1)[0], rows


def test_before_the_gate_the_request_is_a_warning_naming_the_release(tmp_path, monkeypatch):
    tc.tool("node")
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", "999.0.0")
    _, rows, stderr = _generate_and_run(_project(tmp_path, rule=True))
    assert _row(rows, "refresh", 1)[0], rows
    assert "GET https://api.test/api/unknown reached no declared route" in stderr, stderr
    assert "from jsonui-cli 999.0.0 this fails the test" in stderr, stderr


def test_unset_the_warning_promises_no_release(tmp_path, monkeypatch):
    tc.tool("node")
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", None)
    _, rows, stderr = _generate_and_run(_project(tmp_path, rule=True))
    assert _row(rows, "refresh", 1)[0], rows
    assert "GET https://api.test/api/unknown reached no declared route" in stderr, stderr
    assert "this fails the test" not in stderr, stderr


def test_a_test_with_nothing_unmatched_warns_nothing(tmp_path, monkeypatch):
    tc.tool("node")
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", None)
    _, rows, stderr = _generate_and_run(_project(tmp_path, rule=True, declare_unknown=True))
    assert all(v[0] for v in rows.values()), rows
    assert "reached no declared route" not in stderr, stderr


# ------------------------------------------------------------------ xxxiv ---

def test_xxxiv_rule_and_401_the_side_route_answers(tmp_path, red):
    tc.tool("node")
    report, rows, _ = _generate_and_run(_project(tmp_path, rule=True, declare_unknown=True))
    assert report.side_routes == ["postLogout"]
    assert _row(rows, "submit", 1)[0], rows      # 401: logout served and admitted
    assert _row(rows, "submit", 2)[0], rows      # 500: no logout, nothing to admit


def test_xxxiv_no_rule_and_401_is_red_naming_the_request(tmp_path, red):
    tc.tool("node")
    report, rows, _ = _generate_and_run(_project(tmp_path, rule=False, declare_unknown=True))
    assert report.side_routes == []
    passed, why = _row(rows, "submit", 1)
    assert not passed and "POST https://api.test/api/logout" in why, rows
    assert _row(rows, "submit", 2)[0], rows


def test_xxxiv_rule_and_a_non_401_row_that_posts_logout_is_the_bounds_red(tmp_path, red):
    tc.tool("node")
    _, rows, _ = _generate_and_run(
        _project(tmp_path, rule=True, declare_unknown=True), logout_on_500=True)
    assert _row(rows, "submit", 1)[0], rows
    passed, why = _row(rows, "submit", 2)
    assert not passed and "postLogout" in why and "outside what this method's rows reach" in why, rows


# ------------------------------------------------------------------ gate ---

@pytest.mark.parametrize("gate, running, red_", [
    (None, "1.8.118", False),
    ("1.8.119", "1.8.118", False),
    ("1.8.119", "1.8.119", True),
    ("1.8.100", "1.8.99", False),     # numeric, not string, comparison
    ("1.8.99", "1.8.100", True),
])
def test_the_gate_compares_versions_as_numbers(monkeypatch, gate, running, red_):
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", gate)
    monkeypatch.setattr(bt, "_running_version", lambda: running)
    assert bt.unmatched_gate() == (red_, gate)


def test_an_unreadable_gate_stops_generation(monkeypatch):
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", "next")
    with pytest.raises(bt.BranchTestGenerationError, match="UNMATCHED_GATE_FROM"):
        bt.unmatched_gate()


def test_the_released_tool_announces_no_red_yet():
    """Guard for the release: the literal ships unset until the release that
    announces the red is cut (it is set then, not derived)."""
    assert bt.UNMATCHED_GATE_FROM is None


# ------------------------------------------------------------- withdrawn ---

@pytest.mark.parametrize("running", ["1.8.118", "1.8.119", "1.8.120"])
def test_a_withdrawn_gate_is_never_red_and_does_not_stop_generation(monkeypatch, running):
    """Design v4.18 makes "withdrawn" a lawful literal, and the tag gate passes
    it; reading it as a version would stop every face's generation."""
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", "withdrawn")
    monkeypatch.setattr(bt, "_running_version", lambda: running)
    assert bt.unmatched_gate() == (False, "withdrawn")


def test_a_withdrawn_gate_warns_that_it_was_withdrawn(tmp_path, monkeypatch):
    tc.tool("node")
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", "withdrawn")
    _, rows, stderr = _generate_and_run(_project(tmp_path, rule=True))
    assert all(v[0] for v in rows.values()), rows
    assert "GET https://api.test/api/unknown reached no declared route" in stderr, stderr
    assert "was withdrawn — it does not fail" in stderr, stderr
    assert "from jsonui-cli withdrawn" not in stderr, stderr
