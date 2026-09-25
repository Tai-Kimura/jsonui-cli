"""The runtime's notices reach an agent's run of the test runner, one line each.

Ticket web-branch-test-unmatched-warnings-are-hidden-from-agent-runs-of-vitest.
The runtimes printed `unmatched`, `unmatched_foreign` and
`condition_without_effect` through the test runner's console capture, and the
runner decided what to show:

- vitest 4.1.11 picks its "agent" reporter (MinimalReporter, `silent:
  "passed-only"`) when std-env says an agent runs it — AI_AGENT, else any of
  CLAUDECODE, CLAUDE_CODE, CODEX_SANDBOX, CODEX_THREAD_ID, CURSOR_AGENT … —
  and drops every console line a passing test (or its afterAll) wrote. An
  agent read 0 notices whatever the rows did.
- Gradle's Test task replaces System.out / System.err and shows a passing
  test's output only with `testLogging.showStandardStreams`: the Android lines
  reached the XML report and never the console, agent or not.

Now each runtime writes one line, `jsonui-test branch test [<row>] <kind>:
<body>`, to the process's own stderr and nowhere else: not stdout, where
`--reporter=json` writes its report; not console as well, which a reporter
that shows console would print a second time. iOS moves to stderr for the one
shape — xcodebuild shows a passing test's print and stderr alike and `-quiet`
drops both (measured 2026-09-25, Xcode 26.6, iOS 26.5 simulator), so there
the exit changes no visibility.

The web arms run the PINNED vitest (fixtures/vitest-pin, `npm ci` in the
compiler job): a stand-in cannot reproduce a reporter. Each run carries its
own discriminator — a console line from a passing row, shown by the default
reporter and dropped by the agent one — so a case that is not the reporter it
names fails instead of passing for the wrong reason. The pre-fix exit is the
control: the same run with the runtime's line put back on console.warn shows
0 in an agent's run.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc
from tests.test_branch_act_window_and_bound import _swift_block
from tests.test_branch_condition_controls import _project as _condition_project
from tests.test_harness_conditions import (
    _CONDITIONS_HOOK, _SESSION_STATE, _SUMMARY_HARNESS, _generate)

PIN = Path(__file__).parent / "fixtures" / "vitest-pin"
PINNED = "4.1.11"

#: std-env 4.2.0 (what vitest 4.1.11 resolves) names an agent by AI_AGENT, else
#: by the first of these that is set. Every case starts with none of them.
AGENT_VARS = ("AI_AGENT", "CLAUDECODE", "CLAUDE_CODE", "REPL_ID", "GEMINI_CLI",
              "CODEX_SANDBOX", "CODEX_THREAD_ID", "OPENCODE", "AUGMENT_AGENT",
              "GOOSE_PROVIDER", "JUNIE_DATA", "JUNIE_SHIM_PATH", "CURSOR_AGENT")

AGENTS = {"AI_AGENT": {"AI_AGENT": "claude-code_test_agent"},
          "CLAUDECODE": {"CLAUDECODE": "1"},
          "CODEX_SANDBOX": {"CODEX_SANDBOX": "seatbelt"}}

NOTICE = re.compile(r"^jsonui-test branch test \[(?P<row>.+?)\] "
                    r"(?P<kind>unmatched|unmatched_foreign|condition_without_effect): (?P<body>.*)$",
                    re.M)
PROBE = "PROBE_CONSOLE_FROM_A_PASSING_ROW"

# The pre-fix exit, put back: the runtime's line through console again.
_RAW_WRITE = 'proc.stderr.write(line + "\\n");'
_CONSOLE_EXIT = "console.warn(line);"


def _vitest() -> Path:
    pkg = PIN / "node_modules" / "vitest" / "package.json"
    if not pkg.is_file():
        why = (f"vitest {PINNED} is not installed under {PIN} — run `npm ci --prefix "
               "test_tools/tests/fixtures/vitest-pin`; the agent-reporter arms are UNMEASURED here")
        if os.environ.get("CI"):
            pytest.fail(why)
        pytest.skip(why)
    version = json.loads(pkg.read_text(encoding="utf-8"))["version"]
    assert version == PINNED, f"{pkg} is vitest {version}, not the pinned {PINNED}: run npm ci"
    return pkg.parent / "vitest.mjs"


def _env(agent: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in AGENT_VARS and k != "FORCE_COLOR"}
    env["NO_COLOR"] = "1"       # vitest's colour codes would open the line it prints
    env.update(agent)
    return env


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _runner_files(root: Path) -> None:
    (root / "node_modules").symlink_to(PIN / "node_modules", target_is_directory=True)
    _write(root / "package.json", '{"type": "module"}')
    _write(root / "vitest.config.mjs",
           f'export default {{ cacheDir: {json.dumps(str(root / ".vite"))}, '
           'test: { environment: "node", include: ["tests/unit/**/*.test.ts"] } };\n')


def _vitest_run(root: Path, agent: dict[str, str], *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(["node", str(_vitest()), "run", *extra], cwd=root, env=_env(agent),
                          capture_output=True, text=True, timeout=300)


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _notices(stream: str) -> list[tuple[str, str, str]]:
    return [(m["row"], m["kind"], m["body"]) for m in NOTICE.finditer(_ANSI.sub("", stream))]


# ------------------------------------------------------------------- web ---

_FEED_SPEC = {
    "type": "screen_spec", "metadata": {"name": "feed"},
    "dataFlow": {"viewModel": {"methods": [{"name": "load"}, {"name": "refresh"}]},
                 "repositories": [{"name": "FeedRepository", "methods": [
                     {"name": "getFeed", "endpoint": "GET /api/feed"}]}]},
    "branchContracts": {"methods": {
        "load": {"branches": [{"when": {"api.getFeed": "default"}, "then": {"data.status": "ready"}}]},
        "refresh": {"branches": [{"when": {"api.getFeed": "default"}, "then": {"data.status": "ready"}}]},
    }},
}

_FEED_HARNESS = '''import { applyDeclaredKeys } from "../generated/jsonui-branch-runtime";
export const apiOrigins = ["https://api.test"];
class FeedViewModel {
  status = "idle";
  async load() {
    console.warn("PROBE");                                            // shown or dropped by the reporter
    await fetch("https://api.test/api/feed");
    await fetch("https://api.test/api/unknown");                      // the app's API, no route
    await fetch("https://sdk.example/collect", { method: "POST" });   // another host
    this.status = "ready";
  }
  async refresh() {
    await fetch("https://api.test/api/feed");
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
'''.replace("PROBE", PROBE)


def _feed(root: Path, exit_mutant: bool = False) -> Path:
    _write(root / "jui.config.json", json.dumps({"spec_directory": "docs/screens/json",
                                                 "platforms": ["web"]}))
    _write(root / "docs/screens/json/feed.spec.json", json.dumps(_FEED_SPEC))
    _write(root / "tests/mocks/generated/feed.mock.json", json.dumps({
        "source": {"method": "GET", "path": "/api/feed", "operationId": "getFeed"},
        "activeScenario": "default", "scenarios": {"default": {"status": 200, "body": []}}}))
    report = bt.generate_branch_tests("feed", root, platform="web", config_platforms=["web"])
    _write(root / "tests/unit/branch-harness/feed.ts", _FEED_HARNESS)
    if exit_mutant:
        text = report.runtime_file.read_text(encoding="utf-8")
        assert text.count(_RAW_WRITE) == 1, "the runtime's stderr write moved; update the mutant"
        report.runtime_file.write_text(text.replace(_RAW_WRITE, _CONSOLE_EXIT), encoding="utf-8")
    _runner_files(root)
    return root


#: The feed's two rows: `load` makes one request to the app's API that no
#: route answers and one to another host; `refresh` makes neither.
_FEED_EXPECTED = [("unmatched", "GET https://api.test/api/unknown reached no declared route"),
                  ("unmatched_foreign", "1 — POST https://sdk.example/collect")]


def _assert_feed(run: subprocess.CompletedProcess, *, agent: bool) -> None:
    both = run.stdout + run.stderr
    assert run.returncode == 0, both[-4000:]
    # The discriminator: the case is the reporter it names.
    assert both.count(PROBE) == (0 if agent else 1), both[-4000:]
    got = _notices(run.stderr)
    assert [(k, b.split(" and ")[0] if k == "unmatched" else b) for _, k, b in got] == \
        _FEED_EXPECTED, run.stderr[-4000:]
    # The row: screen, method and title, as no runner heading comes with it.
    assert all(r.startswith("feed.load branch 1:") for r, _, _ in got), got
    assert not _notices(run.stdout), run.stdout[-4000:]


@pytest.mark.parametrize("name", sorted(AGENTS))
def test_an_agents_run_shows_each_notice_once(tmp_path, name):
    tc.tool("node")
    _vitest()
    _assert_feed(_vitest_run(_feed(tmp_path / "p"), AGENTS[name]), agent=True)


def test_the_default_reporter_shows_each_notice_once_not_twice(tmp_path):
    tc.tool("node")
    _vitest()
    _assert_feed(_vitest_run(_feed(tmp_path / "p"), {}), agent=False)


def test_the_json_reporter_keeps_stdout_a_report(tmp_path):
    tc.tool("node")
    _vitest()
    run = _vitest_run(_feed(tmp_path / "p"), AGENTS["AI_AGENT"], "--reporter=json")
    assert run.returncode == 0, (run.stdout + run.stderr)[-4000:]
    report = json.loads(run.stdout)
    assert (report["numPassedTests"], report["numFailedTests"]) == (2, 0), report
    assert [k for _, k, _ in _notices(run.stderr)] == ["unmatched", "unmatched_foreign"], run.stderr


def test_control_the_pre_fix_exit_is_invisible_to_an_agent(tmp_path):
    """The console exit, put back: an agent's run shows 0 — the arms above
    discriminate — while the default reporter still shows the lines."""
    tc.tool("node")
    _vitest()
    agent = _vitest_run(_feed(tmp_path / "a", exit_mutant=True), AGENTS["AI_AGENT"])
    assert agent.returncode == 0, (agent.stdout + agent.stderr)[-4000:]
    assert not _notices(agent.stdout + agent.stderr), agent.stderr[-4000:]
    plain = _vitest_run(_feed(tmp_path / "d", exit_mutant=True), {})
    assert len(_notices(plain.stdout + plain.stderr)) == 2, (plain.stdout + plain.stderr)[-4000:]


def test_an_agents_run_shows_condition_without_effect(tmp_path):
    tc.tool("node")
    _vitest()
    root = _condition_project(tmp_path)
    _generate(root, condition_controls=True)
    harness = root / "tests/unit/branch-harness"
    (harness / "summary.ts").write_text(_SUMMARY_HARNESS, encoding="utf-8")
    (harness / "session-state.ts").write_text(_SESSION_STATE, encoding="utf-8")
    (harness / "branch-conditions.ts").write_text(_CONDITIONS_HOOK, encoding="utf-8")
    _runner_files(root)
    run = _vitest_run(root, AGENTS["CLAUDECODE"])
    assert run.returncode == 0, (run.stdout + run.stderr)[-4000:]
    got = [(r, b) for r, k, b in _notices(run.stderr) if k == "condition_without_effect"]
    assert len(got) == 1 and "branch 3:" in got[0][0], run.stderr[-4000:]
    assert "session=absent instead of present" in got[0][1], got


_BOUNDARY_PROBE = '''import { reportUnmatched } from "./runtime.ts";
const warned: string[] = [];
console.warn = (...a: unknown[]) => { warned.push(a.map(String).join(" ")); };
reportUnmatched(["GET /with-process"], null, "row A");
const proc = (globalThis as any).process;
Object.defineProperty(globalThis, "process", { value: undefined, configurable: true, writable: true });
reportUnmatched(["GET /without-process"], null, "row B");
Object.defineProperty(globalThis, "process", { value: proc, configurable: true, writable: true });
proc.stdout.write(JSON.stringify(warned) + "\\n");
'''


def test_without_a_process_the_line_goes_to_console_warn(tmp_path):
    """Both sides of the one branch: with `process` the line is on stderr and
    console.warn is not called; without it (a browser) console.warn is."""
    tc.tool("node")
    _write(tmp_path / "runtime.ts", bt.RUNTIME_TS)
    _write(tmp_path / "probe.ts", _BOUNDARY_PROBE)
    run = subprocess.run(["node", "--experimental-strip-types", "probe.ts"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-3000:]
    assert [r for r, _, _ in _notices(run.stderr)] == ["row A"], run.stderr
    warned = json.loads(run.stdout.strip().splitlines()[-1])
    assert len(warned) == 1 and warned[0].startswith(
        "jsonui-test branch test [row B] unmatched: GET /without-process"), warned


# --------------------------------------------------------------- Android ---

_KOTLIN_MAIN = '''
fun main() {
  val realOut = System.out
  val realErr = System.err
  val captured = java.io.ByteArrayOutputStream()
  val capture = java.io.PrintStream(captured, true, "UTF-8")
  System.setOut(capture)              // what Gradle's Test task does to both
  System.setErr(capture)
  reportUnmatched(listOf("GET /api/unknown"), null, "row A")
  reportUnmatched(emptyList(), null, "row B")
  reportConditionWithoutEffect(true, "row C", "session=absent")
  reportConditionWithoutEffect(false, "row D", "session=absent")
  System.setOut(realOut)
  System.setErr(realErr)
  println("CAPTURED " + captured.toString("UTF-8").lines().count { it.isNotBlank() })
}
'''


def _kotlin_probe(runtime: str) -> str:
    def block(signature: str) -> str:
        i = runtime.index(signature)
        return runtime[i:runtime.index("\n}\n", i) + 3]

    notice = runtime[runtime.index("private val noticeStream ="):]
    notice = notice[:notice.index("\n}\n", notice.index("fun notice(")) + 3]
    return "\n\n".join([notice, block("fun reportConditionWithoutEffect("),
                        block("fun reportUnmatched(")]) + _KOTLIN_MAIN


def test_android_writes_past_the_capture_gradle_installs(tmp_path):
    run = tc.compile_and_run_kotlin(tmp_path, tc.KOTLIN_SHIM + "\n" + _kotlin_probe(bt.KOTLIN_RUNTIME))
    assert run.returncode == 0, run.stderr[-3000:]
    assert run.stdout.strip() == "CAPTURED 0", run.stdout
    assert [(r, k) for r, k, _ in _notices(run.stderr)] == \
        [("row A", "unmatched"), ("row C", "condition_without_effect")], run.stderr


def test_android_control_system_err_lands_in_the_capture(tmp_path):
    runtime = bt.KOTLIN_RUNTIME.replace("  noticeStream.println(", "  System.err.println(", 1)
    assert runtime != bt.KOTLIN_RUNTIME
    run = tc.compile_and_run_kotlin(tmp_path, tc.KOTLIN_SHIM + "\n" + _kotlin_probe(runtime))
    assert run.returncode == 0, run.stderr[-3000:]
    assert run.stdout.strip() == "CAPTURED 2", run.stdout
    assert not _notices(run.stderr), run.stderr


# ------------------------------------------------------------------- iOS ---

_SWIFT_MAIN = '''
reportUnmatched(["GET /api/unknown"], nil, "row A")
reportUnmatched([], nil, "row B")
reportUnmatchedForeign(["POST https://sdk.example/collect"], "row A")
reportConditionWithoutEffect(true, "row C", "session=absent")
reportConditionWithoutEffect(false, "row D", "session=absent")
'''


def _run_swift(tmp_path: Path, runtime: str) -> subprocess.CompletedProcess:
    parts = [_swift_block(runtime, "func notice("),
             _swift_block(runtime, "func reportUnmatchedForeign("),
             _swift_block(runtime, "func reportConditionWithoutEffect("),
             _swift_block(runtime, "func reportUnmatched(")]
    _write(tmp_path / "runtime.swift", "import Foundation\n\n" + "\n\n".join(parts))
    _write(tmp_path / "main.swift", _SWIFT_MAIN)
    binary = tmp_path / "probe"
    build = subprocess.run(["swiftc", "-Onone", "-o", str(binary), str(tmp_path / "runtime.swift"),
                            str(tmp_path / "main.swift")], capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, f"emitted Swift did not compile:\n{build.stderr[:4000]}"
    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)


def test_ios_writes_the_line_to_stderr(tmp_path):
    tc.tool("swiftc")
    run = _run_swift(tmp_path, bt.SWIFT_RUNTIME)
    assert run.returncode == 0, run.stderr[-3000:]
    assert [(r, k) for r, k, _ in _notices(run.stderr)] == \
        [("row A", "unmatched"), ("row A", "unmatched_foreign"), ("row C", "condition_without_effect")], \
        run.stderr
    assert run.stdout == "", run.stdout


def test_ios_control_standard_output_is_not_the_exit(tmp_path):
    tc.tool("swiftc")
    runtime = bt.SWIFT_RUNTIME.replace("FileHandle.standardError.write(", "FileHandle.standardOutput.write(", 1)
    assert runtime != bt.SWIFT_RUNTIME
    run = _run_swift(tmp_path, runtime)
    assert run.returncode == 0, run.stderr[-3000:]
    assert not _notices(run.stderr) and len(_notices(run.stdout)) == 3, run.stdout + run.stderr
