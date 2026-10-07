"""The IME probe of conformance-mobile's android-library-tests job.

.github/scripts/kjui_device_tests.py `ime` asks, before the device tests,
whether the emulator's IME can show at all (ticket ci-android-library-tests-
emulator-dies-in-the-keyboard-tests-and-the-run-hangs: run 37650134866 failed
library's 10 keyboard cases with every show request failing and no `onShown`
in the whole run — the environment, read as ten product failures). Checked
here with a stand-in adb whose IME shows on the Nth request, or never.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import stat
import sys
import tempfile
import textwrap
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


class ImeProbeTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.calls = self.dir / "adb-calls.txt"
        self.requests = self.dir / "requests.txt"
        self.evidence = self.dir / "device-evidence"

    def adb(self, shows_on: int | None, opens: bool = True) -> str:
        """A stand-in adb: the IME is shown once the surface was opened
        `shows_on` times (never when None); `opens` False: no surface opens."""
        adb = self.dir / "adb"
        adb.write_text(textwrap.dedent(f"""\
            #!{sys.executable}
            import sys
            from pathlib import Path
            args = sys.argv[1:]
            with open({str(self.calls)!r}, "a") as f:
                f.write(" ".join(args) + "\\n")
            counter = Path({str(self.requests)!r})
            if args[:3] == ["shell", "am", "start"]:
                counter.write_text(str(int(counter.read_text() or 0) + 1) if counter.exists() else "1")
                print("Status: ok" if {opens!r} else "Error: Activity not started, unable to resolve Intent")
            elif args[:3] == ["shell", "dumpsys", "input_method"]:
                n = int(counter.read_text()) if counter.exists() else 0
                shows_on = {shows_on!r}
                shown = shows_on is not None and n >= shows_on
                print("  mServedView=null")
                print(f"  mInputShown={{'true' if shown else 'false'}}")
            """))
        adb.chmod(adb.stat().st_mode | stat.S_IEXEC)
        return str(adb)

    def probe(self, shows_on: int | None, budget: float = 2.0, opens: bool = True):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = K.ime_ready(self.evidence, budget_seconds=budget, adb=self.adb(shows_on, opens),
                             attempt_seconds=0.2, poll=0.05)
        return rc, out.getvalue()

    def test_an_ime_that_shows_on_the_third_request_passes_and_says_so(self):
        rc, out = self.probe(shows_on=3)
        self.assertEqual(rc, 0, out)
        self.assertIn("ime: shown on request 3,", out)
        self.assertFalse((self.evidence / "ime-never-shown").exists())

    def test_an_ime_that_shows_on_the_first_request_passes(self):
        rc, out = self.probe(shows_on=1)
        self.assertEqual(rc, 0, out)
        self.assertIn("ime: shown on request 1,", out)

    def test_an_ime_that_never_shows_fails_by_name_with_the_evidence(self):
        rc, out = self.probe(shows_on=None, budget=1.0)
        self.assertEqual(rc, 3, out)
        self.assertIn("the IME never showed before the tests", out)
        for name in ("screen.png", "input_method.txt", "window.txt", "logcat.txt", "logcat-events.txt"):
            self.assertTrue((self.evidence / "ime-never-shown" / name).is_file(), name)
        # It kept asking within the budget, not once.
        self.assertGreater(int(self.requests.read_text()), 1)

    def test_each_request_opens_the_surface_and_goes_home_after(self):
        rc, out = self.probe(shows_on=2)
        calls = self.calls.read_text().splitlines()
        opens = [c for c in calls if c.startswith("shell am start")]
        homes = [c for c in calls if c == "shell input keyevent KEYCODE_HOME"]
        self.assertEqual(len(opens), 2)
        self.assertEqual(len(homes), 3, "home before the first request, after the failed one and after the shown one")
        self.assertEqual(calls.index("shell input keyevent KEYCODE_HOME"), 0, "the first thing is home: no IME left up")

    def test_an_image_without_a_surface_is_not_checked_and_says_so_loudly(self):
        rc, out = self.probe(shows_on=None, budget=1.0, opens=False)
        self.assertEqual(rc, 0, out)
        self.assertIn("the IME was NOT checked", out)
        self.assertNotIn("never showed", out)
        self.assertFalse((self.evidence / "ime-never-shown").exists())

    def test_the_budget_is_bound_to_what_green_runs_took(self):
        # Green runs' first onShown came at most 35 s after their first request.
        self.assertGreaterEqual(K.DEFAULT_IME_BUDGET_SECONDS, 3 * 35)

    def test_the_command_line(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(K.main(["ime", "--nope", "1"]), 2)


if __name__ == "__main__":
    unittest.main()
