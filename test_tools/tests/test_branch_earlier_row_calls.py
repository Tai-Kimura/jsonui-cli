"""A call an earlier row's view model makes after its row ended does not count
in a later row — measured by RUNNING generated web tests in the pinned vitest.

Measured before this (2026-09-26, the 1.8.121 runtime): row 1's view model
posting 1 s after its act turned the next row red on "api.createOrder: this
row says not-called … called 1 time(s)", and satisfied another row's wait for
createOrder — a row that should have failed by name passed. The web runtime
now binds each request to the row whose async context started it (Node's
AsyncLocalStorage): a timer or a task carries its row, and a call it makes in
a later row is answered 599, not counted, and named there
(earlier_row_call).

What it cannot tell apart, and says so: a call an earlier row's view model
makes from an event the LATER row posts (a subscription) runs in the later
row's context and counts there.

The specimens' times are far from the windows they straddle: row 1 posts
2000 ms after its act, its settle returns ~QUIET_MS (400) after it; the next
row's act takes 4000 ms, so the call lands inside it whatever the machine.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc
from tests import test_branch_notices_reach_agent_runs as n

LATE_MS = 2000
NEXT_ACT_MS = 4000


def test_the_specimens_straddle_the_windows_by_a_margin():
    assert LATE_MS >= 5 * bt.QUIET_MS          # after row 1 settled
    assert NEXT_ACT_MS >= 2 * LATE_MS         # inside the next row's act


def _spec(methods: dict[str, list[dict]]) -> dict:
    return {
        "type": "screen_spec", "metadata": {"name": "orders"},
        "dataFlow": {"viewModel": {"methods": [{"name": m} for m in methods]},
                     "repositories": [{"name": "OrderRepository", "methods": [
                         {"name": "createOrder", "endpoint": "POST /api/orders"}]}]},
        "branchContracts": {"methods": {m: {"branches": rows} for m, rows in methods.items()}},
    }


# The view model: `start` leaves a call behind (a timer, a task, or a
# subscription to an app-wide event); the other methods call nothing, and
# `idle` / `waits` take NEXT_ACT_MS, so the late call lands inside them.
_HARNESS = '''import { applyDeclaredKeys } from "../generated/jsonui-branch-runtime";
export const apiOrigins = ["https://api.test"];
const post = () => void fetch("https://api.test/api/orders", { method: "POST" });
const bus: EventTarget = ((globalThis as any).__appBus ??= new EventTarget());
const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));
class OrdersViewModel {
  status = "idle";
  async start() {
    this.status = "started";
    if (CARRIER === "timer") setTimeout(post, LATE_MS);
    if (CARRIER === "task") void (async () => { await pause(LATE_MS); post(); })();
    if (CARRIER === "subscription") bus.addEventListener("changed", post);
  }
  async idle() {
    if (CARRIER === "subscription") bus.dispatchEvent(new Event("changed"));
    await pause(NEXT_ACT_MS);
  }
  async waits() { await pause(NEXT_ACT_MS); }
}
export function createHarness() {
  const vm = new OrdersViewModel();
  return {
    vm,
    setState(state: Record<string, unknown>) { applyDeclaredKeys(vm, state); },
    readField(name: string) { return (vm as any)[name]; },
    expectTransition(_d: string) {},
    resolveString(key: string) { return key; },
  };
}
'''

START = {"start": [{"when": {"data.status": "idle"}, "then": {"data.status": "started"}}]}
#: The red direction: a row that says the call is not made.
NOT_CALLED = {**START, "idle": [{"when": {"data.status": "idle"},
                                 "then": {"api.createOrder": "not-called", "data.status": "idle"}}]}
#: The silent-green direction: a row that waits for the call its view model never makes.
WAITS = {**START, "waits": [{"when": {"api.createOrder": "default", "data.status": "idle"},
                             "then": {"data.status": "idle"}}]}


def _project(root: Path, methods: dict, carrier: str, *, without_row_context: bool = False) -> Path:
    n._write(root / "jui.config.json", json.dumps({"spec_directory": "docs/screens/json", "platforms": ["web"]}))
    n._write(root / "docs/screens/json/orders.spec.json", json.dumps(_spec(methods)))
    n._write(root / "tests/mocks/generated/orders.mock.json", json.dumps({
        "source": {"method": "POST", "path": "/api/orders", "operationId": "createOrder"},
        "activeScenario": "default", "scenarios": {"default": {"status": 200, "body": {}}}}))
    report = bt.generate_branch_tests("orders", root, platform="web", config_platforms=["web"])
    n._write(root / "tests/unit/branch-harness/orders.ts",
             _HARNESS.replace("CARRIER", json.dumps(carrier)).replace("NEXT_ACT_MS", str(NEXT_ACT_MS))
             .replace("LATE_MS", str(LATE_MS)))
    if without_row_context:
        # The control: the runtime without its row context — every request
        # counts where it lands, as before.
        text = report.runtime_file.read_text(encoding="utf-8")
        old = "    return Storage ? new Storage() : null;\n"
        assert text.count(old) == 1
        report.runtime_file.write_text(text.replace(old, "    return null;\n"), encoding="utf-8")
    n._runner_files(root)
    return root


def _run(root: Path) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """Each test's (outcome, failure message) by name, from the junit file,
    and the earlier_row_call notices on stderr."""
    tc.tool("node")
    n._vitest()
    out = root / "junit.xml"
    run = n._vitest_run(root, {}, "--reporter=junit", f"--outputFile={out}")
    assert out.is_file(), (run.stdout + run.stderr)[-4000:]
    tests = {}
    for case in ET.parse(out).getroot().iter("testcase"):
        failure = case.find("failure")
        tests[case.get("name", "")] = ("failed" if failure is not None else "passed",
                                       "" if failure is None else failure.get("message", ""))
    said = [line for line in run.stderr.splitlines() if " earlier_row_call: " in line]
    return tests, said


def _one(tests: dict, method: str) -> tuple[str, str]:
    rows = [v for k, v in tests.items() if k.startswith(f"orders.{method} > ")]
    assert len(rows) == 1, tests
    return rows[0]


@pytest.mark.parametrize("carrier", ["timer", "task"])
def test_a_late_call_does_not_fail_a_later_rows_not_called(tmp_path, carrier):
    tests, said = _run(_project(tmp_path / "p", NOT_CALLED, carrier))
    assert _one(tests, "start")[0] == "passed", tests
    assert _one(tests, "idle")[0] == "passed", tests
    assert len(said) == 1 and "POST /api/orders from " in said[0] and '"orders.start' in said[0], said


@pytest.mark.parametrize("carrier", ["timer", "task"])
def test_control_without_the_row_context_the_later_row_is_red(tmp_path, carrier):
    tests, said = _run(_project(tmp_path / "p", NOT_CALLED, carrier, without_row_context=True))
    outcome, message = _one(tests, "idle")
    assert outcome == "failed" and "api.createOrder: this row says not-called" in message, tests
    assert any("rows cannot be told apart here" in line for line in said), said


def test_a_late_call_does_not_satisfy_a_later_rows_wait(tmp_path):
    tests, said = _run(_project(tmp_path / "p", WAITS, "timer"))
    outcome, message = _one(tests, "waits")
    assert outcome == "failed" and "the row expects createOrder, never called within EXPECT_MS" in message, tests
    # The row fails before its notice line; its own red names the call.
    assert "not counted here, 1 call(s) an earlier row's view model started: POST /api/orders from " in message, message


def test_control_without_the_row_context_the_wait_is_satisfied_by_the_earlier_row(tmp_path):
    tests, _ = _run(_project(tmp_path / "p", WAITS, "timer", without_row_context=True))
    assert _one(tests, "waits")[0] == "passed", tests       # the silent green


def test_a_subscription_the_later_row_triggers_is_not_told_apart(tmp_path):
    """The limit, printed: the call runs in the later row's context."""
    tests, said = _run(_project(tmp_path / "p", NOT_CALLED, "subscription"))
    outcome, message = _one(tests, "idle")
    assert outcome == "failed" and "api.createOrder: this row says not-called" in message, tests
    assert said == [], said
