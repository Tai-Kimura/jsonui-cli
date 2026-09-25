"""The iOS runtime releases a test's harness on iOS 26 and later, and keeps it
below 26 without crashing and without hiding what that leaves open —
measured by RUNNING the emitted runtime under XCTest on two simulators.

The probe (fixtures/branch-harness-release) is shaped like a consuming app:
deployment 17, the MainActor default isolation in the app and the test
target. Its view models answer an app-wide notification with GET /ping.
Two tests only build a harness; the third posts the notification inside its
own window (after `mark()`) and prints what its recorder saw and which view
models are still alive (weak references). A last class posts it from a test
whose own view model never calls /ping.

Measured 2026-09-26 (Xcode 26.6, iOS 26.5 and 18.6) before the change — the
harness retained on every version: the third test's recorder held 3 pings
for its own 1 on both runtimes, 6 in the next class (the first class's view
models answered too), and every view model stayed alive. Released on every
version instead: on 26.5, 1 ping and only its own view model alive; on 18.6,
6 of 6 tests crashed at their end (`malloc: pointer being freed was not
allocated`, swift_task_deinitOnExecutorMainActorBackDeploy ->
TaskLocal::StopLookupScope). Releasing the kept harnesses on another thread
crashed too: the harness's deinit runs as a main-actor job and the view
model released inside it takes the back-deploy shim's fast path.

So: released from 26, kept below — and there the absence messages carry a
note, and one notice (retained_harnesses) names both directions: an earlier
view model's call can fail a row's not-called / unexpectedOps, and it can
satisfy a row's `called` that this test's view model never made (the last
class prints that happening).

Needs two iOS simulator runtimes, one from 26 (no newer than the SDK) and
one below; the file is in no CI job, and run-suites.sh's iOS leg owns it
with JSONUI_REQUIRE_IOS_SIMULATORS=1, where a missing runtime FAILS naming
itself. The simulators are this run's own (tests/_ios_simulators.py): made
per run and runtime as jsonui-branch-release-<version>-<pid>-<token>, deleted
when the module ends, and what a killed run left is swept by the next. Until
1.8.121 they were one fixed-name device per runtime, found by name and
reused, and two runs at once drove the same device (ticket test-tools-ios-
simulator-arms-collide-across-concurrent-runs). Shared devices and
`xcode-select` are never touched — Xcode is whatever DEVELOPER_DIR, else the
selected one, resolves.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests._ios_simulators import RunDevices

PROBE = Path(__file__).parent / "fixtures" / "branch-harness-release"
#: Row 1's view model posting 1 s after its act, from a Task that holds it
#: strongly (the app's view model leaks) or weakly; row 2 calls nothing.
LATE_PROBE = Path(__file__).parent / "fixtures" / "branch-late-calls"
#: The one retain call, inside `if #unavailable(iOS 26)` — the control takes it out.
NO_RETAIN = "      BranchHarnessRetainer.retain(harness)\n"


def _missing(why: str) -> None:
    if os.environ.get("CI") or os.environ.get("JSONUI_REQUIRE_IOS_SIMULATORS"):
        pytest.fail(why)
    pytest.skip(why)


def _xcrun(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["xcrun", *args], capture_output=True, text=True, timeout=timeout)


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", text))


def _runtimes() -> tuple[dict, dict]:
    """The newest available iOS runtime from 26 that the SDK can run, and
    the newest below 26."""
    if shutil.which("xcrun") is None:
        _missing("no xcrun: the iOS harness-release arms are UNMEASURED here")
    sdk = _xcrun("--sdk", "iphonesimulator", "--show-sdk-version")
    listed = _xcrun("simctl", "list", "runtimes", "-j")
    if sdk.returncode != 0 or listed.returncode != 0:
        _missing(f"no iOS simulator SDK or runtimes: {(sdk.stderr + listed.stderr)[-500:]}")
    ios = [r for r in json.loads(listed.stdout)["runtimes"]
           if r.get("platform") == "iOS" and r.get("isAvailable")]
    from26 = [r for r in ios if 26 <= _version(r["version"])[0] and _version(r["version"]) <= _version(sdk.stdout)]
    below = [r for r in ios if _version(r["version"])[0] < 26]
    if not from26 or not below:
        _missing(f"needs an iOS simulator runtime from 26 (no newer than the SDK, {sdk.stdout.strip()}) "
                 f"and one below 26; available: {[r['version'] for r in ios]}")
    newest = lambda rs: max(rs, key=lambda r: _version(r["version"]))  # noqa: E731
    return newest(from26), newest(below)


@pytest.fixture(scope="module")
def sims():
    """This run's simulators: made on first use, deleted when the module
    ends; what killed runs left is swept first."""
    devices = RunDevices()
    devices.sweep()
    yield devices
    devices.release()


def _run(work: Path, runtime_source: str, udid: str, probe: Path = PROBE) -> tuple[int, str]:
    """`xcodebuild test` of *probe* with *runtime_source* as the emitted
    runtime; its exit code and log."""
    shutil.copytree(probe, work)
    (work / "Tests" / "ProbeTests" / "JsonuiBranchRuntime.swift").write_text(runtime_source, encoding="utf-8")
    run = subprocess.run(
        ["xcodebuild", "test", "-scheme", "RetainProbe", "-destination", f"id={udid}",
         "-derivedDataPath", str(work / "dd"), "-parallel-testing-enabled", "NO",
         # A crash is the control's expected outcome; without this xcodebuild
         # sits in `simctl diagnose` for up to 600 s afterwards.
         "-collect-test-diagnostics", "never"],
        cwd=work, capture_output=True, text=True, timeout=900)
    return run.returncode, run.stdout + run.stderr


def _probe(log: str, name: str) -> str:
    lines = [line for line in log.splitlines() if line.startswith(f"PROBE {name} ")]
    assert len(lines) == 1, (name, lines, log[-3000:])
    return lines[0]


CRASH = "pointer being freed was not allocated"


@pytest.fixture(scope="module")
def runs(tmp_path_factory, sims) -> dict:
    from26, below = _runtimes()
    fixed = bt.SWIFT_RUNTIME
    assert fixed.count(NO_RETAIN) == 1
    out = {}
    for key, runtime, source in (("from26", from26, fixed), ("below", below, fixed),
                                 ("below-unretained", below, fixed.replace(NO_RETAIN, "      _ = harness\n"))):
        rc, log = _run(tmp_path_factory.mktemp(key) / "pkg", source, sims.device(runtime, _missing))
        out[key] = (runtime["version"], rc, log)
    return out


# ------------------------------------------------------------ from iOS 26 --

def test_from_26_an_earlier_tests_view_model_is_released(runs):
    version, rc, log = runs["from26"]
    assert "alive=[\"iso-3\"]" in _probe(log, "iso"), version
    assert "alive=[\"plain-3\"]" in _probe(log, "plain"), version


def test_from_26_its_requests_stay_out_of_a_later_window(runs):
    version, rc, log = runs["from26"]
    assert " ping=1 " in _probe(log, "iso") and " ping=1 " in _probe(log, "plain"), version
    assert "note=[]" in _probe(log, "iso"), version
    assert "retained_harnesses" not in log, version


def test_from_26_a_row_expecting_a_call_only_an_earlier_view_model_would_make_is_red(runs):
    """The silent-green direction, closed: nothing earlier is alive to make
    the call, so the row waits EXPECT_MS and names it."""
    version, rc, log = runs["from26"]
    assert "calledRowHolds=false" in _probe(log, "silent"), version
    assert "settle: the row expects ping, never called within EXPECT_MS (10000 ms)" in log, version
    assert rc != 0 and "Executed 8 tests, with 1 failure" in log, (version, log[-3000:])


# ------------------------------------------------------------- below 26 ---

def test_below_26_the_kept_harnesses_crash_nothing(runs):
    version, rc, log = runs["below"]
    assert rc == 0 and "Executed 8 tests, with 0 failures" in log, (version, log[-3000:])
    assert CRASH not in log and "Restarting after unexpected exit" not in log, version


def test_below_26_both_directions_are_real_and_named(runs):
    version, rc, log = runs["below"]
    iso = _probe(log, "iso")
    # A red that belongs to another test: 2 earlier view models answered.
    assert " ping=3 " in iso and "harnesses of 2 earlier test(s) in this process are kept alive" in iso, (version, iso)
    # A green that belongs to another test: this view model never called.
    assert "own=0" in _probe(log, "silent") and "calledRowHolds=true" in _probe(log, "silent"), version
    notices = [line for line in log.splitlines() if " retained_harnesses: " in line]
    assert len(notices) == 1, (version, notices)
    assert notices[0].startswith("jsonui-test branch test [probe A test_3] retained_harnesses: ")
    for words in ("it can fail not-called / unexpectedOps",
                  "it can satisfy a called / request / when row this test's view model never made"):
        assert words in notices[0], notices[0]


def test_control_below_26_a_released_harness_crashes_the_process(runs):
    """Why below 26 keeps them: the same probe with the retain taken out."""
    version, rc, log = runs["below-unretained"]
    assert log.count(CRASH) >= 1 and "Restarting after unexpected exit" in log, (version, log[-3000:])


# ------------------------------------------- an earlier row's view model ---
#
# From 26 the harness is released at its test's end, and a view model that
# is still alive after that is kept by the app: a Task, Timer or observer
# holding it strongly — the app's view model leaks. Its call lands in the
# next row's window, and the URL protocol cannot see which view model sent
# it, so it counts there; the row after names the leak (outlived_its_test).
# Measured before this (2026-09-26, iOS 26.5): strongly held, 1 call landed in
# the next row; weakly held, the view model was released and none did.

@pytest.fixture(scope="module")
def late_runs(tmp_path_factory, sims) -> dict:
    from26, below = _runtimes()
    out = {}
    for key, runtime in (("from26", from26), ("below", below)):
        rc, log = _run(tmp_path_factory.mktemp(f"late-{key}") / "pkg", bt.SWIFT_RUNTIME,
                       sims.device(runtime, _missing), LATE_PROBE)
        out[key] = (runtime["version"], rc, log)
    return out


def _notices(log: str, kind: str) -> list[str]:
    return [line for line in log.splitlines() if f"] {kind}: " in line]


def test_from_26_a_view_model_that_outlives_its_test_is_named_as_the_apps_leak(late_runs):
    version, rc, log = late_runs["from26"]
    assert rc == 0, (version, log[-3000:])
    # Counted where it landed: the protocol cannot tell which view model sent it.
    assert "row2=1" in _probe(log, "strong"), version
    said = _notices(log, "outlived_its_test")
    assert len(said) == 1, (version, said)
    assert said[0].startswith('jsonui-test branch test [strong row 2] outlived_its_test: the view model of '
                              '"strong row 1" is still alive after its test ended — the app\'s view model leaks'), said


def test_from_26_a_view_model_held_weakly_is_released_and_not_named(late_runs):
    version, rc, log = late_runs["from26"]
    assert "row2=0" in _probe(log, "weak"), version
    assert not any("weak row" in line for line in _notices(log, "outlived_its_test")), version


def test_below_26_the_kept_harnesses_are_named_instead(late_runs):
    version, rc, log = late_runs["below"]
    assert rc == 0, (version, log[-3000:])
    assert "row2=1" in _probe(log, "strong") and "row2=1" in _probe(log, "weak"), version
    assert _notices(log, "outlived_its_test") == [], version
    assert len(_notices(log, "retained_harnesses")) == 1, version

