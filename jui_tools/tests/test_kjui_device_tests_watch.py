"""The watch of conformance-mobile's android-library-tests job.

.github/scripts/kjui_device_tests.py `watch` runs the job's Gradle command
and stops it when a module's cases stop moving (ticket ci-android-library-
tests-emulator-dies-in-the-keyboard-tests-and-the-run-hangs: two runs printed
"Tests 0/203" and nothing more for 99 minutes). The job needs an emulator;
the watch is plain Python, so it is checked here with a stand-in Gradle (a
script that prints AGP's lines) and a stand-in adb (a script that records
what it was asked).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import stat
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "kjui_device_tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("kjui_device_tests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


K = _load()

# Lines as AGP printed them in run 37596542034.
STARTING = "Starting 3 tests on emulator-5554 - 15"
COUNT = "emulator-5554 - 15 Tests {n}/3 completed. (0 skipped) ({f} failed)"
FAILED = ("com.example.KeyboardTest > aCase[emulator-5554 - 15] \x1b[31mFAILED \x1b[0m")
FINISHED = "Finished 3 tests on emulator-5554 - 15"
CONSOLE = "[EmulatorConsole]: Failed to start Emulator console for 5554"


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.calls = self.dir / "adb-calls.txt"
        adb = self.dir / "adb"
        adb.write_text(textwrap.dedent(f"""\
            #!{sys.executable}
            import sys
            with open({str(self.calls)!r}, "a") as f:
                f.write(" ".join(sys.argv[1:]) + "\\n")
            print("stand-in adb")
            """))
        adb.chmod(adb.stat().st_mode | stat.S_IEXEC)
        self.adb = str(adb)
        self.evidence = self.dir / "device-evidence"

    def gradle(self, script: str) -> list[str]:
        """A stand-in Gradle: python running `script`, its prints flushed."""
        body = "import sys, time\n" + textwrap.dedent(script)
        return [sys.executable, "-u", "-c", body]

    def run_watch(self, script: str, idle: float = 1.0):
        out = io.StringIO()
        started = time.monotonic()
        with contextlib.redirect_stdout(out):
            rc = K.watch(self.gradle(script), self.evidence, idle_seconds=idle, adb=self.adb, poll=0.05)
        return rc, out.getvalue(), time.monotonic() - started

    def test_an_idle_count_while_cases_run_saves_the_state_and_stops_the_command(self):
        rc, out, took = self.run_watch(f"""
            print({STARTING!r}); print({COUNT.format(n=1, f=0)!r})
            time.sleep(60)
        """)
        self.assertEqual(rc, 124, out)
        self.assertLess(took, 30, "the stand-in's 60 s sleep ran out: the command was not stopped")
        self.assertIn("progress has not moved for 1 s (last count: 1)", out)
        for name in ("screen.png", "input_method.txt", "window.txt", "logcat.txt"):
            self.assertTrue((self.evidence / "stopped" / name).is_file(), name)
        self.assertIn("shell dumpsys input_method", self.calls.read_text())

    def test_an_idle_count_right_after_starting_is_one_too(self):
        # The red runs' shape: "Starting 203 tests", "Tests 0/203", then nothing.
        rc, out, _ = self.run_watch(f"""
            print({CONSOLE!r}); print({STARTING!r}); print({COUNT.format(n=0, f=0)!r})
            time.sleep(60)
        """)
        self.assertEqual(rc, 124, out)

    def test_counts_that_keep_moving_are_not_idle(self):
        rc, out, _ = self.run_watch(f"""
            print({STARTING!r})
            for n in range(1, 4):
                time.sleep(0.6); print({COUNT!r}.format(n=n, f=0))
            print({FINISHED!r})
        """)
        self.assertEqual(rc, 0, out)
        self.assertFalse((self.evidence / "stopped").exists())

    def test_a_long_build_before_the_cases_is_not_timed(self):
        # Compiling took ~5 min on CI before any case ran; only a module's run is timed.
        rc, out, _ = self.run_watch(f"""
            time.sleep(2.5)
            print({STARTING!r}); print({COUNT.format(n=3, f=0)!r}); print({FINISHED!r})
        """)
        self.assertEqual(rc, 0, out)

    def test_the_wait_between_two_modules_is_not_timed(self):
        rc, out, _ = self.run_watch(f"""
            print({STARTING!r}); print({COUNT.format(n=3, f=0)!r}); print({FINISHED!r})
            time.sleep(2.5)
            print({STARTING!r}); print({COUNT.format(n=3, f=0)!r}); print({FINISHED!r})
        """)
        self.assertEqual(rc, 0, out)

    def test_the_first_failed_case_saves_the_state_once(self):
        rc, out, _ = self.run_watch(f"""
            print({STARTING!r})
            print({FAILED!r}); print({COUNT.format(n=1, f=1)!r})
            time.sleep(0.4)
            print({FAILED!r}); print({COUNT.format(n=2, f=2)!r})
            time.sleep(0.4)
            print({COUNT.format(n=3, f=2)!r}); print({FINISHED!r})
            sys.exit(1)
        """)
        self.assertEqual(rc, 1, "the command's own exit is the watch's when nothing stalls")
        self.assertTrue((self.evidence / "first-failure" / "input_method.txt").is_file())
        self.assertEqual(out.count("device evidence (first-failure) saved"), 1)

    def test_a_gradle_task_failure_line_is_not_a_failed_case(self):
        rc, out, _ = self.run_watch(f"""
            print({STARTING!r}); print({COUNT.format(n=3, f=0)!r}); print({FINISHED!r})
            print("> Task :library:connectedDebugAndroidTest FAILED")
            print("Execute com.example.KeyboardTest.aCase: FAILED")
        """)
        self.assertEqual(rc, 0, out)
        self.assertFalse((self.evidence / "first-failure").exists())

    def test_a_dead_adb_does_not_stop_the_verdict(self):
        self.adb = str(self.dir / "no-such-adb")
        rc, out, _ = self.run_watch(f"""
            print({STARTING!r}); print({COUNT.format(n=0, f=0)!r})
            time.sleep(60)
        """)
        self.assertEqual(rc, 124, out)
        self.assertTrue((self.evidence / "stopped" / "input_method.txt.error").is_file())

    def test_the_output_is_passed_through(self):
        rc, out, _ = self.run_watch(f"""
            print({STARTING!r}); print({COUNT.format(n=3, f=0)!r}); print({FINISHED!r})
        """)
        self.assertEqual(rc, 0)
        self.assertIn(FINISHED, out)

    # --- an ANR dialog holding the focus (run 37618369032) -----------------

    def focus_adb(self, focus_line: str) -> None:
        """A stand-in adb whose `dumpsys window` reports focus_line."""
        adb = self.dir / "adb-focus"
        adb.write_text(textwrap.dedent(f"""\
            #!{sys.executable}
            import sys
            with open({str(self.calls)!r}, "a") as f:
                f.write(" ".join(sys.argv[1:]) + "\\n")
            if sys.argv[1:4] == ["shell", "dumpsys", "window"]:
                print("  mFocusedApp=ActivityRecord{{725902a u0 com.kotlinjsonui.test/.KeyboardActivity t39}}")
                print("  " + {focus_line!r})
            """))
        adb.chmod(adb.stat().st_mode | stat.S_IEXEC)
        self.adb = str(adb)

    LAUNCHER_ANR = "mCurrentFocus=Window{39e6b5b u0 Application Not Responding: com.google.android.apps.nexuslauncher}"

    def run_focus(self, seconds: float = 1.2):
        out = io.StringIO()
        script = f"""
            print({STARTING!r}); print({COUNT.format(n=1, f=0)!r})
            time.sleep({seconds}); print({COUNT.format(n=3, f=0)!r}); print({FINISHED!r})
        """
        with contextlib.redirect_stdout(out):
            rc = K.watch(self.gradle(script), self.evidence, idle_seconds=30, adb=self.adb,
                         poll=0.05, focus_seconds=0.1)
        return rc, out.getvalue()

    def test_an_anr_dialog_holding_the_focus_is_saved_and_its_app_closed(self):
        self.focus_adb(self.LAUNCHER_ANR)
        rc, out = self.run_focus()
        self.assertEqual(rc, 0, out)
        calls = self.calls.read_text()
        self.assertIn("shell am force-stop com.google.android.apps.nexuslauncher", calls)
        self.assertTrue((self.evidence / "anr-1" / "window.txt").is_file())
        record = (self.evidence / "anr-dialogs.txt").read_text()
        self.assertIn("ANR dialog #1", record)
        self.assertIn("closed (am force-stop com.google.android.apps.nexuslauncher)", record)

    def test_the_same_dialog_is_counted_once(self):
        self.focus_adb(self.LAUNCHER_ANR)
        rc, out = self.run_focus(seconds=1.5)
        self.assertEqual(out.count("ANR dialog #"), 1, out)
        self.assertEqual(self.calls.read_text().count("am force-stop"), 1)

    def test_an_anr_of_a_package_under_test_is_recorded_and_left_open(self):
        self.focus_adb("mCurrentFocus=Window{1a2b3c u0 Application Not Responding: com.kotlinjsonui.dynamic.test}")
        rc, out = self.run_focus()
        self.assertNotIn("am force-stop", self.calls.read_text())
        self.assertIn("left open", (self.evidence / "anr-dialogs.txt").read_text())

    def test_an_ordinary_focus_is_not_touched(self):
        self.focus_adb("mCurrentFocus=Window{317c0d7 u0 com.kotlinjsonui.test/com.kotlinjsonui.components.KeyboardActivity}")
        rc, out = self.run_focus()
        self.assertEqual(rc, 0, out)
        calls = self.calls.read_text()
        self.assertIn("shell dumpsys window", calls, "the focus was never read: the check did not run")
        self.assertNotIn("am force-stop", calls)
        self.assertFalse((self.evidence / "anr-dialogs.txt").exists())

    def test_the_command_line(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(K.main(["watch", "--idle", "5"]), 2)
            self.assertEqual(K.main(["watch", "--nope", "1", "--", "true"]), 2)


if __name__ == "__main__":
    unittest.main()
