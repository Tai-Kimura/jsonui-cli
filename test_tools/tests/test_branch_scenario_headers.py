"""A scenario's `headers` on the generated branch tests' runtimes — measured by RUNNING them (ticket
2026-10-24-jsonui-test-mock-scenario-cannot-set-response-headers).

`mock serve` sends a scenario's headers; the runtimes put only Content-Type on their responses, so a row could not
pick the scenario a header-reading branch needs. Each probe serves a 429 with `Retry-After` and `X-Request-ID` and
reads them off the response the way the app's client would, a delayed delivery too (iOS holds it apart). Needs node
and swiftc: run with the compilers (ci.yml's branch-runtime step, run-suites.sh), not in python-suite. Android is
test_branch_scenario_headers_android.py, in run-suites.sh's Android leg.
"""
from __future__ import annotations

import subprocess

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc


_TS_PROBE = '''import { installFetchMock } from "./runtime.ts";
const ROUTES: any[] = [{ op: "a", method: "GET", pattern: "^/a$", scenario: "limited",
  scenarios: { limited: { status: 429, body: {}, headers: { "Retry-After": "30", "X-Request-ID": "r-1" } } } }];
const rec = installFetchMock(ROUTES);
const res = await fetch("https://x.test/a");
console.log(`STATUS ${res.status}`);
console.log(`RETRY ${res.headers.get("Retry-After")}`);
console.log(`REQ ${res.headers.get("X-Request-ID")}`);
console.log(`TYPE ${res.headers.get("Content-Type")}`);
rec.restore();
process.exit(0);
'''


def test_web_runtime_puts_the_headers_on_the_response(tmp_path):
    tc.tool("node")
    (tmp_path / "runtime.ts").write_text(bt.RUNTIME_TS, encoding="utf-8")
    (tmp_path / "probe.ts").write_text(_TS_PROBE, encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[:3000]
    got = dict(line.split(" ", 1) for line in run.stdout.strip().splitlines())
    assert got == {"STATUS": "429", "RETRY": "30", "REQ": "r-1", "TYPE": "application/json"}, got


_SWIFT_MAIN = """import Foundation
let routes = [
  RouteSpec(op: "a", method: "GET", pattern: "^/a$", defaultScenario: "limited",
            scenarios: ["limited": (429, "{}", "application/json")],
            headers: ["limited": ["Retry-After": "30", "X-Request-ID": "r-1"]]),
  RouteSpec(op: "b", method: "GET", pattern: "^/b$", defaultScenario: "limited",
            scenarios: ["limited": (429, "{}", "application/json")], delays: ["limited": 50],
            headers: ["limited": ["Retry-After": "5"]]),
]
let dummy = NSObject()
runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: dummy) }) { h, _ in
  let session = URLSession(configuration: .default)
  for name in ["a", "b"] {
    let done = DispatchSemaphore(value: 0)
    session.dataTask(with: URL(string: "https://example.test/" + name)!) { _, response, _ in
      let r = response as! HTTPURLResponse
      print("\\(name.uppercased()) \\(r.statusCode) \\(r.value(forHTTPHeaderField: "Retry-After") ?? "-") \\(r.value(forHTTPHeaderField: "X-Request-ID") ?? "-") \\(r.value(forHTTPHeaderField: "Content-Type") ?? "-")")
      done.signal()
    }.resume()
    while done.wait(timeout: .now()) == .timedOut { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
  }
  h.settle()
  session.invalidateAndCancel()
}
"""


def test_ios_runtime_puts_the_headers_on_the_response(tmp_path):
    from tests.test_branch_scenario_delay import _SWIFT_SHIM
    tc.tool("swiftc")
    runtime = bt.SWIFT_RUNTIME
    assert runtime.count("\nimport XCTest\n") == 1
    (tmp_path / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (tmp_path / "runtime.swift").write_text(runtime.replace("\nimport XCTest\n", "\n", 1), encoding="utf-8")
    (tmp_path / "main.swift").write_text(_SWIFT_MAIN, encoding="utf-8")
    build = subprocess.run(["swiftc", "-Onone", "-o", str(tmp_path / "prog"), str(tmp_path / "shim.swift"),
                            str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
                           capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, build.stderr[:4000]
    run = subprocess.run([str(tmp_path / "prog")], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[:3000]
    got = dict(line.split(" ", 1) for line in run.stdout.strip().splitlines() if line[:2] in ("A ", "B "))
    # a delayed delivery carries its headers too
    assert got == {"A": "429 30 r-1 application/json", "B": "429 5 - application/json"}, run.stdout
