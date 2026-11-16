"""P2e(b): condition controls — does a harness condition change what a row asserts?

A row that names `harness.<name>` away from its default rests on the
consumer's hook. The pilot measured the case where it rests on nothing: 51
rows with `harness.session: "present"` stayed green with the session absent,
because no mock served the 401 the session decides. `generate branch-tests
--condition-controls` emits, after each such row, a CONTROL that runs the same
act and assertions with every condition at its default and never fails; when
all of them still hold it prints `condition_without_effect` (info).

Shipping condition xxxiii: a row whose condition does not change the result
gets `condition_without_effect`, a row whose condition does gets nothing. The
web face is RUN (the P2d fixture: the view model reads the session when it is
built); the Kotlin control body is compiled and run against stand-ins for the
assertions; the Swift test is type-checked against XCTest.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc
from tests.test_branch_act_window_and_bound import _HOOKS, _REGISTER, _VITEST
from tests.test_harness_conditions import (
    _CONDITIONS_HOOK, _SESSION_STATE, _SUMMARY_HARNESS, _SUMMARY_RUNNER, _generate, _summary)

#: Row 1 (the P2d fixture): signed in, the account is read — the session decides it.
#: Row 3: signed in, but the row asserts only what happens either way.
_ROWS = [
    {"when": {"api.getOrder": "default", "api.getAccount": "default",
              "harness.session": "present"},
     "then": {"data.status": "ready", "data.me": "loaded"}},
    {"when": {"api.getOrder": "default"},
     "then": {"data.status": "ready", "api.getAccount": "not-called"}},
    {"when": {"api.getOrder": "default", "harness.session": "present"},
     "then": {"data.status": "ready"}},
]


def _project(tmp_path: Path) -> Path:
    return _summary(tmp_path / "p", rows=_ROWS)


def _run_web(root: Path) -> tuple[dict, str, str, object]:
    report = _generate(root, condition_controls=True)
    harness = root / "tests/unit/branch-harness"
    (harness / "summary.ts").write_text(_SUMMARY_HARNESS, encoding="utf-8")
    (harness / "session-state.ts").write_text(_SESSION_STATE, encoding="utf-8")
    (harness / "branch-conditions.ts").write_text(_CONDITIONS_HOOK, encoding="utf-8")
    (root / "node_modules/vitest").mkdir(parents=True, exist_ok=True)
    (root / "node_modules/vitest/package.json").write_text(
        '{"name": "vitest", "type": "module", "main": "index.js"}', encoding="utf-8")
    (root / "node_modules/vitest/index.js").write_text(_VITEST, encoding="utf-8")
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (root / "hooks.mjs").write_text(_HOOKS, encoding="utf-8")
    (root / "register.mjs").write_text(_REGISTER, encoding="utf-8")
    (root / "runner.mjs").write_text(_SUMMARY_RUNNER, encoding="utf-8")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--import", "./register.mjs", "runner.mjs"],
        cwd=root, capture_output=True, text=True, timeout=120)
    rows = {}
    for line in run.stdout.splitlines():
        m = re.match(r"^(PASS|FAIL) (.+?)(?: :: (.*))?$", line)
        if m:
            rows[m.group(2)] = (m.group(1) == "PASS", m.group(3) or "")
    assert rows, f"no rows:\n{run.stdout}\n{run.stderr[:4000]}"
    return rows, run.stdout, run.stderr, report


def test_xxxiii_the_control_says_when_a_condition_changes_nothing(tmp_path):
    tc.tool("node")
    rows, out, err, report = _run_web(_project(tmp_path))
    assert report.condition_controls == 2           # rows 1 and 3 name the session
    controls = {n: v for n, v in rows.items() if "[control:" in n}
    assert len(controls) == 2 and all(v[0] for v in controls.values()), rows   # never fail
    assert all(v[0] for v in rows.values()), rows   # nor do the rows themselves
    # The notice's exit is the process's stderr (a runner's console capture
    # hid it), one line naming the row; stdout carries none of it.
    infos = [l for l in err.splitlines()
             if l.startswith("jsonui-test branch test [") and "] condition_without_effect: " in l]
    assert len(infos) == 1, err
    assert "condition_without_effect" not in out, out
    assert "branch 3:" in infos[0] and "session=absent instead of present" in infos[0], infos
    # Row 1: the session decides whether the account is read — no info for it.
    assert not any("branch 1:" in l for l in infos), infos


def test_without_the_flag_nothing_changes(tmp_path):
    root = _project(tmp_path)
    plain = _generate(root)
    text = plain.test_file.read_text(encoding="utf-8")
    assert plain.condition_controls == 0
    assert "[control:" not in text and "reportConditionWithoutEffect" not in text
    with_flag = _generate(root, condition_controls=True).test_file.read_text(encoding="utf-8")
    assert len(re.findall(r'^  it\(".*\[control: ', with_flag, re.M)) == 2
    assert "reportConditionWithoutEffect" in with_flag


def test_a_row_at_the_defaults_gets_no_control(tmp_path):
    rows = [{"when": {"api.getOrder": "default", "harness.session": "absent"},
             "then": {"data.status": "ready"}}]
    report = _generate(_summary(tmp_path / "p", rows=rows), condition_controls=True)
    assert report.condition_controls == 0


def test_the_control_title_and_every_face_name_it(tmp_path):
    root = _project(tmp_path)
    web = _generate(root, condition_controls=True).test_file.read_text(encoding="utf-8")
    assert len(re.findall(r'^  it\(".*\[control: session=absent instead of present\]"', web, re.M)) == 2
    android = _generate(root, "android", condition_controls=True).test_file.read_text(encoding="utf-8")
    assert "fun `loadSummary branch 3 control`()" in android
    ios = _generate(root, "ios", condition_controls=True).test_file.read_text(encoding="utf-8")
    assert "func test_loadSummary_branch_3_control()" in ios
    assert "override func record(_ issue: XCTIssue)" in ios
    plain_ios = _generate(root, "ios").test_file.read_text(encoding="utf-8")
    assert "override func record" not in plain_ios


# ------------------------------------------------ Kotlin: compiled and run ---

_KOTLIN_STANDINS = '''
class Recorder(val counts: Map<String, Int>) {
  fun countFor(op: String): Int = counts[op] ?: 0
  fun unexpectedOps(allowed: Set<String>): List<String> = emptyList()
  fun unmatchedCalls(): List<String> = emptyList()
  fun mark() {}
}
class H(val fields: Map<String, Any?>) {
  fun invoke(name: String, vararg args: Any?) {}
  fun settle() {}
  fun readField(name: String): Any? = fields[name]
}
fun assertEquals(message: String, expected: Any?, actual: Any?) {
  if (expected != actual) throw AssertionError(message)
}
fun assertEquals(expected: Any?, actual: Any?) { if (expected != actual) throw AssertionError() }
fun assertTrue(message: String, value: Boolean) { if (!value) throw AssertionError(message) }
fun assertTrue(value: Boolean) { if (!value) throw AssertionError() }
fun assertFieldEquals(expected: Any?, actual: Any?) { if (expected != actual) throw AssertionError() }
fun reportUnmatched(calls: List<String>, gateFrom: String?, row: String) {}
object BranchEndedRows { fun drain(): List<String> = emptyList() }
fun reportEarlierRowCalls(calls: List<String>, row: String) {}
'''


def _kotlin_control_probe(tmp_path: Path) -> str:
    root = _project(tmp_path)
    report = _generate(root, "android", condition_controls=True)
    runtime = report.runtime_file.read_text(encoding="utf-8")
    start = runtime.index("fun reportConditionWithoutEffect(")
    reporter = runtime[start:runtime.index("\n}\n", start) + 3]
    notice = runtime[runtime.index("private val noticeStream ="):]
    notice = notice[:notice.index("\n}\n", notice.index("fun notice(")) + 3]
    reporter = notice + "\n" + reporter
    test = report.test_file.read_text(encoding="utf-8")
    body = test[test.index("fun `loadSummary branch 3 control`()"):]
    body = body[body.index("{ h, rec ->") + len("{ h, rec ->"):]
    body = body[:body.index("\n    }\n")]
    return (_KOTLIN_STANDINS + reporter + "\nfun control(h: H, rec: Recorder) {" + body + "\n}\n"
            + 'fun main() {\n'
            + '  control(H(mapOf("status" to "ready")), Recorder(mapOf("getOrder" to 1)))\n'
            + '  control(H(mapOf("status" to "idle")), Recorder(mapOf("getOrder" to 1)))\n'
            + '  println("done")\n}\n')


def test_the_kotlin_control_compiles_holds_and_never_fails(tmp_path):
    run = tc.compile_and_run_kotlin(tmp_path, _kotlin_control_probe(tmp_path))
    assert run.returncode == 0, run.stderr[:3000]
    # First call: every assertion holds -> the info, on fd 2. Second: status
    # differs -> caught, silent. Then the probe goes on (it did not throw).
    lines = run.stderr.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("jsonui-test branch test ["), run.stderr
    assert "] condition_without_effect: holds with" in lines[0] and "branch 3:" in lines[0], run.stderr
    assert run.stdout.strip() == "done", run.stdout


# ------------------------------------------- Swift: type-checked, XCTest ---

def test_the_swift_controls_type_check_against_xctest(tmp_path):
    tc.tool("xcrun")
    root = _project(tmp_path)
    report = _generate(root, "ios", condition_controls=True)
    files = [report.runtime_file, report.harness_file, report.test_file,
             report.conditions_hook_file]
    for f in files[1:]:
        text = f.read_text(encoding="utf-8")
        f.write_text(text.replace("@testable import summary_app\n", ""), encoding="utf-8")

    def show(*args: str) -> str:
        return subprocess.run(["xcrun", *args], capture_output=True, text=True,
                              timeout=120).stdout.strip()

    platform = show("--sdk", "macosx", "--show-sdk-platform-path")
    done = subprocess.run(
        ["xcrun", "swiftc", "-typecheck", "-sdk", show("--sdk", "macosx", "--show-sdk-path"),
         "-F", f"{platform}/Developer/Library/Frameworks",
         "-I", f"{platform}/Developer/usr/lib", *[str(f) for f in files]],
        capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[:4000]
