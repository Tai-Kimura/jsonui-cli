"""Red-check xxxvi: only the app's own API origin makes an unmatched request red.

Design v4.19, P2e(a). The iOS runtime intercepts every URLSession in the
process, so a third-party SDK's request during act was an unmatched request no
declaration could clear. Now a request to a host that is not the app's API is
the info `unmatched_foreign`; one whose host cannot be told apart (no
`apiOrigins` / `apiOrigin` declared) counts as the app's, and the message says
how to tell them apart. Routes, side routes included, answer only the app's
requests: another host's POST to the same path is not served.

Per face:
- web: the harness module may export `apiOrigins`; a relative URL is the app's.
- iOS: the harness may give `apiOrigin` (BaseBranchHarness has an overridable
  nil); the protocol classifies by scheme, host and port.
- Android: MockWebServer records only its own host:port, so every recorded
  request is the app's — no change, pinned here.

Arms: the matrix {own, foreign, undetermined} × {declared, not} on the web
runtime (run in node) and on the iOS runtime (compiled, requests through a
real URLSession); the generated web test run with and without `apiOrigins`;
the Android runtime and emission unchanged.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc
from tests.test_branch_act_window_and_bound import _HOOKS, _REGISTER, _VITEST
from tests.test_recorder_keeps_every_concurrent_call import _SWIFT_SHIM

# ------------------------------------------------------------------- web ---

_TS_PROBE = '''import { apiOriginsOf, installFetchMock } from "./runtime.ts";
const ROUTES: any[] = [
  { op: "a", method: "POST", pattern: "^/api/a$", scenario: "default",
    scenarios: { default: { status: 200, body: {} } } },
];
function check(name: string, got: boolean) { console.log(`${got ? "PASS" : "FAIL"} ${name}`); }

async function run(label: string, origins: string[] | null) {
  const rec = installFetchMock(ROUTES, {}, origins);
  rec.mark();
  await fetch("/api/rel");                                       // relative: the app's
  await fetch("https://api.test/api/abs");                       // absolute, the API host
  await fetch("https://sdk.example/api/track");                  // absolute, another host
  const sameAsRoute = await fetch("https://sdk.example/api/a", { method: "POST" });
  const onRoute = await fetch("https://api.test/api/a", { method: "POST" });
  const own = rec.unmatchedCalls(), foreign = rec.unmatchedForeign();
  rec.restore();
  return { label, own, foreign, sameAsRoute: sameAsRoute.status, onRoute: onRoute.status,
           served: rec.countFor("a") };
}

const declared = await run("declared", apiOriginsOf({ apiOrigins: ["https://api.test"] }));
check("declared-relative-is-own", declared.own.includes("GET /api/rel"));
check("declared-api-host-is-own", declared.own.includes("GET https://api.test/api/abs"));
check("declared-other-host-is-foreign",
      declared.foreign.includes("GET https://sdk.example/api/track")
      && !declared.own.some((c) => c.includes("sdk.example")));
check("declared-other-host-post-on-a-route-path-is-not-served",
      declared.sameAsRoute === 599 && declared.foreign.includes("POST https://sdk.example/api/a"));
check("declared-own-post-on-the-route-is-served", declared.onRoute === 200 && declared.served === 1);

const none = await run("none", apiOriginsOf({}));
check("undeclared-relative-is-own", none.own.includes("GET /api/rel"));
check("undeclared-other-host-counts-as-own", none.own.includes("GET https://sdk.example/api/track"));
check("undeclared-nothing-is-foreign", none.foreign.length === 0);
check("undeclared-other-host-post-on-a-route-path-is-served", none.sameAsRoute === 200 && none.served === 2);
check("apiOrigins-must-be-strings", apiOriginsOf({ apiOrigins: [1] }) === null);
'''

_TS_EXPECTED = {
    "declared-relative-is-own", "declared-api-host-is-own", "declared-other-host-is-foreign",
    "declared-other-host-post-on-a-route-path-is-not-served",
    "declared-own-post-on-the-route-is-served", "undeclared-relative-is-own",
    "undeclared-other-host-counts-as-own", "undeclared-nothing-is-foreign",
    "undeclared-other-host-post-on-a-route-path-is-served", "apiOrigins-must-be-strings",
}


def _results(stdout: str) -> dict:
    return {m.group(2): m.group(1) == "PASS"
            for m in re.finditer(r"^(PASS|FAIL) (\S+)", stdout, re.M)}


def test_xxxvi_web_runtime_matrix(tmp_path):
    tc.tool("node")
    (tmp_path / "runtime.ts").write_text(bt.RUNTIME_TS, encoding="utf-8")
    (tmp_path / "probe.ts").write_text(_TS_PROBE, encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts"],
                         cwd=tmp_path, capture_output=True, text=True, timeout=120)
    got = _results(run.stdout)
    assert set(got) == _TS_EXPECTED, run.stdout + run.stderr[:3000]
    assert all(got.values()), run.stdout


def test_xxxvi_web_control_without_the_origin_check_the_foreign_post_is_served(tmp_path):
    """The route loop consults `foreign`; with that removed the other host's
    POST to a route path is served — the row the check exists for flips."""
    tc.tool("node")
    runtime = bt.RUNTIME_TS
    assert runtime.count("for (const r of foreign ? [] : compiled) {") == 1
    (tmp_path / "runtime.ts").write_text(
        runtime.replace("for (const r of foreign ? [] : compiled) {", "for (const r of compiled) {"),
        encoding="utf-8")
    (tmp_path / "probe.ts").write_text(_TS_PROBE, encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts"],
                         cwd=tmp_path, capture_output=True, text=True, timeout=120)
    got = _results(run.stdout)
    assert got["declared-other-host-post-on-a-route-path-is-not-served"] is False, run.stdout


# --------------------------------------- web: the generated test, run ---

def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def _project(root: Path) -> Path:
    _write(root / "jui.config.json", {"spec_directory": "docs/screens/json", "platforms": ["web"]})
    _write(root / "docs/screens/json/feed.spec.json", {
        "type": "screen_spec", "metadata": {"name": "feed"},
        "dataFlow": {"viewModel": {"methods": [{"name": "load"}]},
                     "repositories": [{"name": "FeedRepository", "methods": [
                         {"name": "getFeed", "endpoint": "GET /api/feed"}]}]},
        "branchContracts": {"methods": {"load": {"branches": [
            {"when": {"api.getFeed": "default"}, "then": {"data.status": "ready"}}]}}},
    })
    _write(root / "tests/mocks/generated/feed.mock.json", {
        "source": {"method": "GET", "path": "/api/feed", "operationId": "getFeed"},
        "activeScenario": "default", "scenarios": {"default": {"status": 200, "body": []}}})
    return root


_FEED_HARNESS = '''import { applyDeclaredKeys } from "../generated/jsonui-branch-runtime";
APIORIGINS
class FeedViewModel {
  status = "idle";
  async load() {
    await fetch("https://api.test/api/feed");
    await fetch("https://sdk.example/collect", { method: "POST" });   // an analytics SDK
    this.status = "ready";
  }
}
export function createHarness() {
  const vm = new FeedViewModel();
  return {
    vm,
    setState(state: Record<string, unknown>) { applyDeclaredKeys(vm, state); },
    readField(name: string) { return (vm as any)[name]; },
    expectTransition(_d: string) {},
    resolveString(key: string) { return key; },
  };
}
'''


def _run_feed(root: Path, declare: bool, monkeypatch) -> tuple[bool, str, str]:
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", "0.0.1")      # the gate on: red is red
    bt.generate_branch_tests("feed", root, platform="web", config_platforms=["web"])
    origins = 'export const apiOrigins = ["https://api.test"];' if declare else ""
    _write(root / "tests/unit/branch-harness/feed.ts", _FEED_HARNESS.replace("APIORIGINS", origins))
    _write(root / "node_modules/vitest/package.json",
           '{"name": "vitest", "type": "module", "main": "index.js"}')
    _write(root / "node_modules/vitest/index.js", _VITEST)
    _write(root / "package.json", '{"type": "module"}')
    _write(root / "hooks.mjs", _HOOKS)
    _write(root / "register.mjs", _REGISTER)
    _write(root / "runner.mjs", 'import { run } from "vitest";\n'
           'await import("./tests/unit/generated/feed.branches.test.ts");\nawait run();\n')
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--import", "./register.mjs", "runner.mjs"],
        cwd=root, capture_output=True, text=True, timeout=120)
    m = re.search(r"^(PASS|FAIL) .*branch 1:.*?(?: :: (.*))?$", run.stdout, re.M)
    assert m, run.stdout + run.stderr[:3000]
    return m.group(1) == "PASS", m.group(2) or "", run.stdout + run.stderr


def test_xxxvi_web_generated_foreign_with_apiorigins_is_info_not_red(tmp_path, monkeypatch):
    tc.tool("node")
    passed, why, out = _run_feed(_project(tmp_path), True, monkeypatch)
    assert passed, why
    assert "unmatched_foreign: 1 — POST https://sdk.example/collect" in out, out


def test_xxxvi_web_generated_undeclared_is_red_and_says_how_to_split(tmp_path, monkeypatch):
    tc.tool("node")
    passed, why, _ = _run_feed(_project(tmp_path), False, monkeypatch)
    assert not passed and "POST https://sdk.example/collect" in why and "apiOrigins" in why, why


# ------------------------------------------------------------------- iOS ---

_SWIFT_MAIN = '''import Foundation
final class DeclaredHarness: BaseBranchHarness {
  override var apiOrigin: URL? { URL(string: "https://api.test") }
}
let routes = [RouteSpec(op: "a", method: "POST", pattern: "^/api/a$", defaultScenario: "ok",
                        scenarios: ["ok": (200, "{}", "application/json")])]
let dummy = NSObject()

func status(_ session: URLSession, _ url: String, _ method: String) -> Int {
  var request = URLRequest(url: URL(string: url)!)
  request.httpMethod = method
  let done = DispatchSemaphore(value: 0)
  var code = -1
  session.dataTask(with: request) { _, response, _ in
    code = (response as? HTTPURLResponse)?.statusCode ?? -1
    done.signal()
  }.resume()
  done.wait()
  return code
}

func run(_ label: String, _ factory: @escaping () -> BranchHarness) {
  runBranchTest(routes: routes, overrides: [:], harnessFactory: factory) { _, rec in
    rec.mark()
    let session = URLSession(configuration: .default)
    let onRoute = status(session, "https://api.test/api/a", "POST")
    let sameAsRoute = status(session, "https://sdk.example/api/a", "POST")
    _ = status(session, "https://api.test/api/abs", "GET")
    _ = status(session, "https://sdk.example/api/track", "GET")
    print("\\\\(label) onRoute=\\\\(onRoute) sameAsRoute=\\\\(sameAsRoute) served=\\\\(rec.countFor("a"))")
    print("\\\\(label) own=\\\\(rec.unmatchedCalls())")
    print("\\\\(label) foreign=\\\\(rec.unmatchedForeign())")
    session.invalidateAndCancel()
  }
}
run("declared") { DeclaredHarness(vm: dummy) }
run("none") { BaseBranchHarness(vm: dummy) }
print("classify-port \\\\(branchOriginClass(URL(string: "https://api.test:8443/x"), URL(string: "https://api.test")) == .foreign)")
print("classify-case \\\\(branchOriginClass(URL(string: "HTTPS://API.test/x"), URL(string: "https://api.test")) == .own)")
print("classify-nil \\\\(branchOriginClass(URL(string: "https://sdk.example/x"), nil) == .undetermined)")
'''


def test_xxxvi_ios_runtime_matrix_through_urlsession(tmp_path):
    tc.tool("swiftc")
    root = tmp_path / "p"
    _project(root)
    report = bt.generate_branch_tests("feed", root, platform="ios", module="feed_app",
                                      out_dir="Tests/Generated", harness_dir="Tests/Generated",
                                      config_platforms=["ios"])
    runtime = report.runtime_file.read_text(encoding="utf-8")
    assert runtime.count("\nimport XCTest\n") == 1
    (tmp_path / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (tmp_path / "runtime.swift").write_text(runtime.replace("\nimport XCTest\n", "\n", 1),
                                            encoding="utf-8")
    (tmp_path / "main.swift").write_text(_SWIFT_MAIN.replace("\\\\", "\\"), encoding="utf-8")
    binary = tmp_path / "prog"
    build = subprocess.run(["swiftc", "-Onone", "-o", str(binary), str(tmp_path / "shim.swift"),
                            str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
                           capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, build.stderr[:4000]
    out = subprocess.run([str(binary)], capture_output=True, text=True, timeout=300).stdout
    # Declared: the other host's POST to the route path is not served (599) and
    # is foreign; the API host's unmatched GET is the app's.
    assert "declared onRoute=200 sameAsRoute=599 served=1" in out, out
    assert 'declared own=["GET https://api.test/api/abs"]' in out, out
    assert 'declared foreign=["GET https://sdk.example/api/track", "POST https://sdk.example/api/a"]' in out, out
    # Not declared: nothing can be told apart — every host is the app's (red
    # side), and the route answers the other host's POST as before.
    assert "none onRoute=200 sameAsRoute=200 served=2" in out, out
    assert 'none own=["GET https://api.test/api/abs", "GET https://sdk.example/api/track"]' in out, out
    assert "none foreign=[]" in out, out
    assert "classify-port true" in out and "classify-case true" in out and "classify-nil true" in out, out


def test_xxxvi_ios_message_names_apiorigin(monkeypatch, tmp_path):
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", "0.0.1")
    root = tmp_path / "p"
    _project(root)
    report = bt.generate_branch_tests("feed", root, platform="ios", module="feed_app",
                                      out_dir="Tests/Generated", harness_dir="Tests/Generated",
                                      config_platforms=["ios"])
    text = report.test_file.read_text(encoding="utf-8")
    assert "XCTAssertEqual(rec.unmatchedCalls(), []," in text and "apiOrigin" in text
    assert "reportUnmatchedForeign(rec.unmatchedForeign())" in text


# --------------------------------------------------------------- Android ---

def test_xxxvi_android_is_unchanged(monkeypatch, tmp_path):
    """MockWebServer records only its own host:port: every recorded request is
    the app's, so the runtime has no foreign list and the message no split."""
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", "0.0.1")
    assert "unmatchedForeign" not in bt.KOTLIN_RUNTIME and "apiOrigin" not in bt.KOTLIN_RUNTIME
    root = tmp_path / "p"
    _project(root)
    report = bt.generate_branch_tests("feed", root, platform="android",
                                      package="com.example.app", out_dir="app/src/test/java",
                                      harness_dir="app/src/test/java", config_platforms=["android"])
    text = report.test_file.read_text(encoding="utf-8")
    assert "rec.unmatchedCalls())" in text and "unmatchedForeign" not in text
    assert bt.unmatched_message("android") == bt.UNMATCHED_MESSAGE + "."
