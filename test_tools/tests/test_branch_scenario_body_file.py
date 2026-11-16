"""A scenario's body on the generated web and iOS runtimes — RUN, not read (ticket
2026-10-25-jsonui-test-mock-bodyfile-is-never-read).

The web runtime JSON-encoded a string body (an NDJSON stream arrived as one quoted line) and sent a null as the
text `null`, where `mock serve` sends both as written. A `bodyFile`'s text is embedded as the literal `_swift_str`
writes; the iOS probe serves it and prints the bytes the app's client receives, which must be the file's — a BOM,
CRLFs and non-ASCII kept. Needs node and swiftc: run with the compilers (ci.yml's branch-runtime step,
run-suites.sh), not in python-suite. Android is test_branch_scenario_body_file_android.py.
"""
from __future__ import annotations

import json
import subprocess

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc
from tests.test_mock_scenario_body_file import CSV

_SWIFT_MAIN = """import Foundation
let routes = [
  RouteSpec(op: "a", method: "GET", pattern: "^/a$", defaultScenario: "csv",
            scenarios: ["csv": (200, %s, "text/csv")]),
]
let dummy = NSObject()
runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: dummy) }) { h, _ in
  let session = URLSession(configuration: .default)
  let done = DispatchSemaphore(value: 0)
  session.dataTask(with: URL(string: "https://example.test/a")!) { data, _, _ in
    print("BODY " + (data ?? Data()).map { String(format: "%%02x", $0) }.joined())
    done.signal()
  }.resume()
  while done.wait(timeout: .now()) == .timedOut { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
  h.settle()
  session.invalidateAndCancel()
}
"""


def test_ios_runtime_sends_the_files_bytes(tmp_path):
    from tests.test_branch_scenario_delay import _SWIFT_SHIM
    tc.tool("swiftc")
    runtime = bt.SWIFT_RUNTIME
    assert runtime.count("\nimport XCTest\n") == 1
    (tmp_path / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (tmp_path / "runtime.swift").write_text(runtime.replace("\nimport XCTest\n", "\n", 1), encoding="utf-8")
    (tmp_path / "main.swift").write_text(_SWIFT_MAIN % bt._swift_str(CSV.decode("utf-8")), encoding="utf-8")
    build = subprocess.run(["swiftc", "-Onone", "-o", str(tmp_path / "prog"), str(tmp_path / "shim.swift"),
                            str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
                           capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, build.stderr[:4000]
    run = subprocess.run([str(tmp_path / "prog")], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[:3000]
    body = [line[5:] for line in run.stdout.splitlines() if line.startswith("BODY ")]
    assert body == [CSV.hex()], run.stdout


_TS_PROBE = '''import { installFetchMock } from "./runtime.ts";
const SC: any = {
  stream: { status: 200, contentType: "application/x-ndjson", body: "{\\"n\\":1}\\n{\\"n\\":2}\\n" },
  drained: { status: 200, body: null }, obj: { status: 200, body: { a: 1 } }, none: { status: 200 } };
for (const name of Object.keys(SC)) {
  const rec = installFetchMock([{ op: "a", method: "GET", pattern: "^/a$", scenario: name, scenarios: SC } as any]);
  const res = await fetch("https://x.test/a");
  console.log(`${name} ${JSON.stringify(await res.text())}`);
  rec.restore();
}
process.exit(0);
'''


def test_web_runtime_sends_a_body_the_way_mock_serve_does(tmp_path):
    tc.tool("node")
    (tmp_path / "runtime.ts").write_text(bt.RUNTIME_TS, encoding="utf-8")
    (tmp_path / "probe.ts").write_text(_TS_PROBE, encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[:3000]
    got = dict(line.split(" ", 1) for line in run.stdout.strip().splitlines())
    assert {k: json.loads(v) for k, v in got.items()} == {
        "stream": '{"n":1}\n{"n":2}\n',  # as written, two records
        "drained": "",
        "obj": '{"a":1}',
        "none": "",
    }, got
