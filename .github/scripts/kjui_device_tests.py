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

  watch [--idle S] [--focus S] [--evidence DIR] [--adb ADB] -- <command…>
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
                         Every --focus seconds (default 15) it reads which
                         window has the focus: a system "isn't responding"
                         dialog there is saved (DIR/anr-N), its app is
                         force-stopped unless it is under test, and the time
                         and count go to DIR/anr-dialogs.txt (run
                         37618369032: Pixel Launcher's ANR dialog held the
                         focus for 14 minutes and the IME never showed).

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

# A system "isn't responding" dialog holding the window focus. Measured on
# run 37618369032: Pixel Launcher's ANR dialog held mCurrentFocus for 14
# minutes, the test activity was the focused app without the focus, the IME
# never showed (mInputShown=false), library's keyboard cases timed out and
# library-dynamic did not start a case.
ANR_FOCUS = re.compile(r"mCurrentFocus=Window\{(\S+) \S+ Application Not Responding: ([A-Za-z0-9_.]+)\}")
DEFAULT_FOCUS_SECONDS = 15
# The packages under test: an ANR of one of them is the run's own, and
# closing it would end its instrumentation, so it is recorded and left to the
# idle stop.
TEST_PACKAGES = ("com.kotlinjsonui.test", "com.kotlinjsonui.dynamic.test",
                 "com.kotlinjsonui.conformance", "com.kotlinjsonui.conformance.test")

# (file, adb arguments): the device's state, each read on its own so one
# that hangs or fails does not take the others with it.
SNAPSHOT = (
    ("screen.png", ["exec-out", "screencap", "-p"]),
    ("input_method.txt", ["shell", "dumpsys", "input_method"]),
    ("window.txt", ["shell", "dumpsys", "window"]),
    ("activities.txt", ["shell", "dumpsys", "activity", "activities"]),
    ("logcat.txt", ["logcat", "-d", "-v", "threadtime"]),
    # am_anr is written here, not to main.
    ("logcat-events.txt", ["logcat", "-d", "-b", "events", "-v", "threadtime"]),
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


def anr_focus(adb: str, timeout: float = 30) -> tuple[str, str] | None:
    """(window, package) when an ANR dialog holds the focus, else None."""
    try:
        out = subprocess.run([adb, "shell", "dumpsys", "window"], capture_output=True,
                             text=True, timeout=timeout).stdout
    except Exception:
        return None
    m = ANR_FOCUS.search(out)
    return (m.group(1), m.group(2)) if m else None


def close_anr(evidence: Path, adb: str, n: int, package: str) -> str:
    """Saves the state, then closes the dialog's app unless it is under test."""
    snapshot(evidence, f"anr-{n}", adb)
    if package in TEST_PACKAGES:
        action = "left open (a package under test: closing it would end the run's instrumentation)"
    else:
        try:
            subprocess.run([adb, "shell", "am", "force-stop", package], capture_output=True, timeout=30)
            action = f"closed (am force-stop {package})"
        except Exception as error:
            action = f"not closed ({type(error).__name__}: {error})"
    line = (f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} ANR dialog #{n}: the focus was on "
            f"'Application Not Responding: {package}' — {action}")
    print(f"watch: {line}", flush=True)
    evidence.mkdir(parents=True, exist_ok=True)
    with open(evidence / "anr-dialogs.txt", "a") as f:
        f.write(line + "\n")
    return line


def watch(command: list[str], evidence: Path, idle_seconds: float = DEFAULT_IDLE_SECONDS,
          adb: str = "adb", poll: float = 5.0, focus_seconds: float = DEFAULT_FOCUS_SECONDS) -> int:
    """Runs command and watches its output (see the module docstring).

    Every focus_seconds (0: never) it also asks which window has the focus;
    an ANR dialog there is saved and closed (close_anr), once per dialog."""
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
    anrs, seen, focus_checked = 0, set(), time.monotonic()
    while proc.poll() is None:
        time.sleep(poll)
        if focus_seconds and time.monotonic() - focus_checked >= focus_seconds:
            focus_checked = time.monotonic()
            hit = anr_focus(adb)
            if hit and hit[0] not in seen:
                seen.add(hit[0])
                anrs += 1
                close_anr(evidence, adb, anrs, hit[1])
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


# ------------------------------------------------------------------- ime
# Whether the device's IME can show at all, asked before the tests: run
# 37650134866 failed library's 10 keyboard cases with the focus on the test
# activity, every show request `onFailed at PHASE_CLIENT_REQUEST_IME_SHOW`
# and no `onShown` in the whole run — the environment, read as ten product
# failures. Green runs saw their first `onShown` at most 35 s after their
# first request (37650123422; 1 s on 37650130355), so the budget is 120 s.
DEFAULT_IME_BUDGET_SECONDS = 120
#: One request: the surface is opened, then the IME is waited for this long.
IME_ATTEMPT_SECONDS = 5.0
#: Surfaces whose field takes the focus and asks for the IME on its own, in
#: the order tried; the first that opens is used. Measured on an API 35
#: tablet AVD (2026-10-08): each opened and showed the IME within 1 s.
IME_SURFACES = (
    ["shell", "am", "start", "-W", "-a", "android.settings.APP_SEARCH_SETTINGS"],
    ["shell", "am", "start", "-W", "-a", "android.search.action.GLOBAL_SEARCH"],
)
IME_SHOWN = re.compile(r"\bmInputShown=true\b")


def ime_shown(adb: str, timeout: float = 30) -> bool:
    try:
        out = subprocess.run([adb, "shell", "dumpsys", "input_method"], capture_output=True,
                             text=True, timeout=timeout).stdout
    except Exception:
        return False
    return bool(IME_SHOWN.search(out))


def _adb_quiet(adb: str, *args: str) -> None:
    try:
        subprocess.run([adb, *args], capture_output=True, timeout=60)
    except Exception:
        pass


def _opened(adb: str, surface: list[str]) -> bool:
    """`am start -W` says `Status: ok` when the activity came up."""
    try:
        out = subprocess.run([adb, *surface], capture_output=True, text=True, timeout=60)
    except Exception:
        return False
    return "Status: ok" in out.stdout


def ime_ready(evidence: Path, budget_seconds: float = DEFAULT_IME_BUDGET_SECONDS, adb: str = "adb",
              attempt_seconds: float = IME_ATTEMPT_SECONDS, poll: float = 0.5) -> int:
    """0 once the IME showed (printing on which request and when), else the
    evidence under evidence/ime-never-shown and 3."""
    # Start from no IME on screen: an IME still up from before would read as
    # this request's (measured on the AVD: a second probe read "shown" in
    # 0.1 s with the IME disabled).
    _adb_quiet(adb, "shell", "input", "keyevent", "KEYCODE_HOME")
    settle_until = time.monotonic() + 5
    while ime_shown(adb) and time.monotonic() < settle_until:
        time.sleep(poll)
    # A surface the image lacks says nothing about the IME: it is not checked,
    # loudly, rather than failed as "never showed".
    surface = next((s for s in IME_SURFACES if _opened(adb, s)), None)
    if surface is None:
        print("ime: WARNING — no probe surface opened on this image "
              f"({', '.join(s[-1] for s in IME_SURFACES)}); the IME was NOT checked before the tests",
              flush=True)
        return 0
    started = time.monotonic()
    n = 0
    while time.monotonic() - started < budget_seconds:
        n += 1
        if n > 1:
            _adb_quiet(adb, *surface)
        until = time.monotonic() + attempt_seconds
        while time.monotonic() < until:
            if ime_shown(adb):
                took = time.monotonic() - started
                print(f"ime: shown on request {n}, {took:.1f} s after the first (surface: {surface[-1]})", flush=True)
                _adb_quiet(adb, "shell", "input", "keyevent", "KEYCODE_HOME")
                return 0
            time.sleep(poll)
        _adb_quiet(adb, "shell", "input", "keyevent", "KEYCODE_HOME")
    snapshot(evidence, "ime-never-shown", adb)
    print(f"ime: the IME never showed before the tests ({n} requests over {int(budget_seconds)} s, "
          f"surface: {surface[-1]}) — "
          "the device cannot run the keyboard cases; not a test result", flush=True)
    return 3


def _ime_main(argv: list[str]) -> int:
    budget, evidence, adb = DEFAULT_IME_BUDGET_SECONDS, Path("device-evidence"), "adb"
    i = 0
    while i < len(argv):
        if argv[i] == "--budget":
            budget = float(argv[i + 1]); i += 2
        elif argv[i] == "--evidence":
            evidence = Path(argv[i + 1]); i += 2
        elif argv[i] == "--adb":
            adb = argv[i + 1]; i += 2
        else:
            print(f"ime: unknown option {argv[i]}", file=sys.stderr)
            return 2
    return ime_ready(evidence, budget, adb)


def _watch_main(argv: list[str]) -> int:
    idle, evidence, adb, focus = DEFAULT_IDLE_SECONDS, Path("device-evidence"), "adb", DEFAULT_FOCUS_SECONDS
    i = 0
    while i < len(argv) and argv[i] != "--":
        if argv[i] == "--idle":
            idle = float(argv[i + 1]); i += 2
        elif argv[i] == "--evidence":
            evidence = Path(argv[i + 1]); i += 2
        elif argv[i] == "--adb":
            adb = argv[i + 1]; i += 2
        elif argv[i] == "--focus":
            focus = float(argv[i + 1]); i += 2
        else:
            print(f"watch: unknown option {argv[i]}", file=sys.stderr)
            return 2
    command = argv[i + 1:]
    if not command:
        print("usage: kjui_device_tests.py watch [--idle S] [--focus S] [--evidence DIR] [--adb ADB] -- <command…>",
              file=sys.stderr)
        return 2
    return watch(command, evidence, idle, adb, focus_seconds=focus)


def main(argv: list[str]) -> int:
    if argv[:1] == ["watch"]:
        return _watch_main(argv[1:])
    if argv[:1] == ["ime"]:
        return _ime_main(argv[1:])
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
