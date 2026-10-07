#!/usr/bin/env python3
"""KotlinJsonUI's device tests, judged from their results.

conformance-mobile's `android-library-tests` job runs this through
kjui_device_tests.sh.

Why it exists (2026-09-26): `library` and `library-dynamic` keep instrumented
tests in src/androidTest, and no CI job ran them. KotlinJsonUI's ci.yml runs
the JVM units, and this workflow's `android` job runs only the conformance
host's suite. Arms written for a fix (a tap gate, a choice kept across a data
change, a badge a screen reader reads) were green on a developer's emulator and
nowhere else.

Two commands:

  flags <KotlinJsonUI>   The opt-in switches, one name per line. A switch is
                         any instrumentation argument that a test compares to
                         "1" (`getArguments().getString("x") == "1"`). The
                         list is derived from the tests, so a new probe needs no
                         edit here.
  judge <KotlinJsonUI>   Reads each module's connected-test XML. Fails on any
                         of these:
                         - a failed case, or a case with an error;
                         - a module with no results;
                         - a class that has @Test in source but no case in the
                           results. Such a class did not run: a filter, a crash
                           before it, or a module that was not built. Gradle
                           can exit 0 over it;
                         - a module of the checkout with @Test in its
                           src/androidTest that this job does not run and that
                           UNREACHED_MODULES does not name with a reason.

  watch [--idle S] [--evidence DIR] [--adb ADB] -- <command…>
                         Runs the Gradle command, its output passed through,
                         and watches it (ticket ci-android-library-tests-
                         emulator-dies-in-the-keyboard-tests-and-the-run-hangs):
                         - at the first failed case it saves the device's
                           state once (DIR/first-failure: a screenshot,
                           `dumpsys input_method`, `dumpsys window`, the top
                           activities, the logcat);
                         - while a module's cases run (between "Starting N
                           tests" and "Finished"), when the progress count has
                           not moved for S seconds (default 600) it saves the
                           state again (DIR/stopped), stops the command and exits
                           124. Measured on five green runs (2026-10-05 to
                           10-07): the longest wait between two counts was 120
                           s. Two red runs printed "Tests 0/203" and nothing
                           more for 99 minutes, to the step's budget, and the
                           evidence the job saves after Gradle never ran.
                         The emulator console's failure line is not the sign:
                         it is printed before every module on green runs too.

conformance-host is run here for its probes (2026-10-04, ticket
kjui-conformance-host-androidtest-probes-never-run-in-ci): 13 probe classes
sat in its androidTest, and the `android` job instruments ConformanceSuiteTest
only. One of them, TapRoleProbeTest, had been red since KotlinJsonUI 14c075b
(2026-09-26) without anyone seeing it.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

MODULES = ("library", "library-dynamic", "conformance-host")

# A class a module holds that this job leaves out, and the job that runs it.
# kjui_device_tests.sh passes these as notClass.
RUN_ELSEWHERE = {
    ("conformance-host", "com.kotlinjsonui.conformance.ConformanceSuiteTest"):
        "the android and android-codegen jobs run it (conformance-host/scripts/run_conformance.sh)",
}

# A module with device tests that no CI invocation runs, and why. A module
# with @Test in its androidTest must be in MODULES or here.
UNREACHED_MODULES = {
    "sample-app": "ViewModelDrivenImeTest measures what the platform does (KotlinJsonUI 413553f, "
                  "the Android 17 lane's question): its ViewModel-raises-the-keyboard arm records "
                  "that API 35 ignores keyboardController.show() without a user gesture, which is "
                  "an answer, not a regression guard; the app also signs with a debug keystore the "
                  "repository does not carry",
}

FLAG = re.compile(r'getArguments\(\)\s*\.getString\("([A-Za-z0-9_]+)"\)\s*==\s*"1"')
# Top-level classes only: a declaration at column 0. A nested helper declared
# above the tests (`private class Reading(...)` inside the test class) would
# otherwise take their @Test and name a class the results never contain.
CLASS = re.compile(
    r"^((?:(?:public|internal|private|open|abstract|final|data)\s+)*)"
    r"class\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)
TEST = re.compile(r"^[ \t]*@Test\b", re.M)


def _sources(kjui: Path, module: str) -> list[Path]:
    root = kjui / module / "src" / "androidTest"
    return sorted(root.rglob("*.kt")) if root.is_dir() else []


def flags(kjui: Path) -> list[str]:
    found: set[str] = set()
    for module in MODULES:
        for path in _sources(kjui, module):
            found |= set(FLAG.findall(path.read_text(encoding="utf-8")))
    return sorted(found)


def test_classes(kjui: Path, module: str) -> set[str]:
    """Simple names of the classes whose body holds an @Test, less the ones
    RUN_ELSEWHERE names for this module.

    Each @Test is assigned to the last top-level `class` declared before it in
    the file. An abstract class runs only through its subclasses, so it is left
    out.
    """
    elsewhere = {fq.rsplit(".", 1)[-1] for (m, fq) in RUN_ELSEWHERE if m == module}
    return _declared(kjui, module) - elsewhere


def _declared(kjui: Path, module: str) -> set[str]:
    names: set[str] = set()
    for path in _sources(kjui, module):
        text = path.read_text(encoding="utf-8")
        decls = [(m.start(), m.group(2), "abstract" in m.group(1)) for m in CLASS.finditer(text)]
        for t in TEST.finditer(text):
            owner = [d for d in decls if d[0] < t.start()]
            if owner and not owner[-1][2]:
                names.add(owner[-1][1])
    return names


def modules_with_device_tests(kjui: Path) -> list[str]:
    """Every top-level module of the checkout whose src/androidTest holds an @Test."""
    found = []
    for child in sorted(p for p in kjui.iterdir() if p.is_dir()):
        root = child / "src" / "androidTest"
        if root.is_dir() and any(TEST.search(f.read_text(encoding="utf-8")) for f in root.rglob("*.kt")):
            found.append(child.name)
    return found


def unreached(kjui: Path) -> list[str]:
    """Modules with device tests that this job does not run and nothing names."""
    return [m for m in modules_with_device_tests(kjui) if m not in MODULES and m not in UNREACHED_MODULES]


def _results(kjui: Path, module: str) -> list[Path]:
    root = kjui / module / "build" / "outputs" / "androidTest-results" / "connected"
    return sorted(root.rglob("TEST-*.xml")) if root.is_dir() else []


def judge(kjui: Path) -> int:
    problems: list[str] = []
    for module in MODULES:
        files = _results(kjui, module)
        declared = test_classes(kjui, module)
        passed = failed = skipped = 0
        failures: list[str] = []
        skips: list[str] = []
        seen: set[str] = set()
        cases = 0
        for path in files:
            for case in ET.parse(path).getroot().iter("testcase"):
                cases += 1
                cls = case.get("classname", "")
                name = f"{cls.rsplit('.', 1)[-1]}.{case.get('name', '')}"
                seen.add(cls.rsplit(".", 1)[-1])
                bad = case.find("failure")
                if bad is None:
                    bad = case.find("error")
                skip = case.find("skipped")
                if bad is not None:
                    failed += 1
                    first = (bad.get("message") or bad.text or "").strip().splitlines()
                    failures.append(f"{name}: {first[0][:160] if first else '(no message)'}")
                elif skip is not None:
                    skipped += 1
                    reason = (skip.get("message") or skip.text or "").strip().splitlines()
                    skips.append(f"{name}: {reason[0][:160] if reason else '(no reason)'}")
                else:
                    passed += 1
        # The breakdown must add up to the total, or a branch above dropped cases.
        assert passed + failed + skipped == cases, (module, passed, failed, skipped, cases)
        not_run = sorted(declared - seen)
        print(f"== {module}: {cases} case(s) from {len(files)} result file(s) — "
              f"{passed} passed, {failed} failed, {skipped} skipped; "
              f"classes with @Test in source {len(declared)}, seen in results "
              f"{len(declared & seen)}")
        for line in skips:
            print(f"   skipped  {line}")
        for line in failures:
            print(f"   FAILED   {line}")
        for cls in not_run:
            print(f"   NOT RUN  {cls} (has @Test in source, no case in the results)")
        if not files:
            problems.append(f"{module}: no results — the tests did not run, or the module was not built")
        if failed:
            problems.append(f"{module}: {failed} failed")
        if not_run:
            problems.append(f"{module}: {len(not_run)} class(es) with @Test did not run")
    for module in modules_with_device_tests(kjui):
        if module in UNREACHED_MODULES:
            print(f"== {module}: not run by this job — {UNREACHED_MODULES[module]}")
    for (module, fq), why in sorted(RUN_ELSEWHERE.items()):
        print(f"== {module}: {fq.rsplit('.', 1)[-1]} left out here — {why}")
    for module in unreached(kjui):
        problems.append(f"{module}: has @Test in src/androidTest and no CI invocation runs it "
                        "(add it to MODULES, or name it in UNREACHED_MODULES with the reason)")
    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        return 1
    return 0


# ----------------------------------------------------------------- watch
# What AGP prints per device while a module's cases run, and a failed case.
PROGRESS = re.compile(r"Tests (\d+)/(\d+) completed")
STARTING = re.compile(r"Starting (\d+) tests on ")
FINISHED = re.compile(r"Finished (\d+) tests on ")
FAILED_CASE = re.compile(r" > \S+\[[^\]]+\].*FAILED")
DEFAULT_IDLE_SECONDS = 600

# (file, adb arguments): the device's state, each read on its own so one
# that hangs or fails does not take the others with it.
SNAPSHOT = (
    ("screen.png", ["exec-out", "screencap", "-p"]),
    ("input_method.txt", ["shell", "dumpsys", "input_method"]),
    ("window.txt", ["shell", "dumpsys", "window"]),
    ("activities.txt", ["shell", "dumpsys", "activity", "activities"]),
    ("logcat.txt", ["logcat", "-d", "-v", "threadtime"]),
    ("devices.txt", ["devices", "-l"]),
)


def snapshot(evidence: Path, tag: str, adb: str, timeout: float = 60) -> Path:
    """Saves the device's state under evidence/tag. Never raises."""
    out = evidence / tag
    out.mkdir(parents=True, exist_ok=True)
    for name, args in SNAPSHOT:
        try:
            done = subprocess.run([adb, *args], capture_output=True, timeout=timeout)
            data = done.stdout if name.endswith(".png") else done.stdout + done.stderr
            (out / name).write_bytes(data)
        except Exception as error:  # a dead device must not stop the verdict
            (out / f"{name}.error").write_text(f"{type(error).__name__}: {error}\n")
    print(f"device evidence ({tag}) saved: {out}", flush=True)
    return out


def watch(command: list[str], evidence: Path, idle_seconds: float = DEFAULT_IDLE_SECONDS,
          adb: str = "adb", poll: float = 5.0) -> int:
    """Runs command and watches its output (see the module docstring)."""
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, start_new_session=True)
    state = {"running": False, "count": None, "moved": time.monotonic(), "failed": False}
    lock = threading.Lock()

    def read() -> None:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            with lock:
                if STARTING.search(line):
                    state.update(running=True, count=None, moved=time.monotonic())
                elif FINISHED.search(line):
                    state.update(running=False)
                elif (m := PROGRESS.search(line)) and m.group(1) != state["count"]:
                    state.update(count=m.group(1), moved=time.monotonic())
                if FAILED_CASE.search(line):
                    state["failed"] = True

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    snapped = False
    while proc.poll() is None:
        time.sleep(poll)
        with lock:
            failed, running, moved, count = state["failed"], state["running"], state["moved"], state["count"]
        if failed and not snapped:
            snapshot(evidence, "first-failure", adb)
            snapped = True
        if running and time.monotonic() - moved > idle_seconds:
            print(f"watch: the cases' progress has not moved for {int(idle_seconds)} s "
                  f"(last count: {count if count is not None else 'none since Starting'}) — "
                  "saving the device's state and stopping the command", flush=True)
            snapshot(evidence, "stopped", adb)
            for sig, wait in ((signal.SIGTERM, 30), (signal.SIGKILL, 10)):
                try:
                    os.killpg(proc.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    proc.wait(timeout=wait)
                    break
                except subprocess.TimeoutExpired:
                    continue
            reader.join(timeout=5)
            return 124
    reader.join(timeout=5)
    with lock:
        failed = state["failed"]
    if failed and not snapped:
        snapshot(evidence, "first-failure", adb)
    return proc.returncode


def _watch_main(argv: list[str]) -> int:
    idle, evidence, adb = DEFAULT_IDLE_SECONDS, Path("device-evidence"), "adb"
    i = 0
    while i < len(argv) and argv[i] != "--":
        if argv[i] == "--idle":
            idle = float(argv[i + 1]); i += 2
        elif argv[i] == "--evidence":
            evidence = Path(argv[i + 1]); i += 2
        elif argv[i] == "--adb":
            adb = argv[i + 1]; i += 2
        else:
            print(f"watch: unknown option {argv[i]}", file=sys.stderr)
            return 2
    command = argv[i + 1:]
    if not command:
        print("usage: kjui_device_tests.py watch [--idle S] [--evidence DIR] [--adb ADB] -- <command…>",
              file=sys.stderr)
        return 2
    return watch(command, evidence, idle, adb)


def main(argv: list[str]) -> int:
    if argv[:1] == ["watch"]:
        return _watch_main(argv[1:])
    if len(argv) != 2 or argv[0] not in ("flags", "judge", "not-class"):
        print("usage: kjui_device_tests.py flags|judge|not-class <KotlinJsonUI checkout>", file=sys.stderr)
        return 2
    kjui = Path(argv[1])
    if not (kjui / "library").is_dir():
        print(f"error: {kjui} is not a KotlinJsonUI checkout (no library/)", file=sys.stderr)
        return 2
    if argv[0] == "flags":
        for name in flags(kjui):
            print(name)
        return 0
    if argv[0] == "not-class":
        # One comma-separated value for -Pandroid.testInstrumentationRunnerArguments.notClass.
        print(",".join(sorted(fq for (_, fq) in RUN_ELSEWHERE)))
        return 0
    return judge(kjui)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
