"""The judge names a device whose input layer stopped taking window focus.

Runs 37650134866 and 42011943298 went red in 16 and 30 library cases, with
`Focus request` answered by no `Focus entering` for the rest of the run. The
lines below are the shape of those runs' logcat of the events buffer.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "kjui_device_tests.py"
SHELL = REPO_ROOT / ".github" / "scripts" / "kjui_device_tests.sh"


def _load():
    spec = importlib.util.spec_from_file_location("kjui_device_tests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


K = _load()

REQUEST = "11-05 10:43:18.138   553   578 I input_focus: [Focus request e89c141 com.kotlinjsonui.test/Activity,reason=UpdateInputWindows]"
NULL = "11-05 10:43:18.448   553   578 I input_focus: [Requesting to set focus to null window,reason=UpdateInputWindows]"
LEAVE = "11-05 10:43:17.445   553   667 I input_focus: [Focus leaving 6704df2 com.kotlinjsonui.test/Activity (server),reason=Waiting]"


def _enter(stamp="10:43:16.956"):
    return f"11-05 {stamp}   553   667 I input_focus: [Focus entering 6704df2 com.kotlinjsonui.test/Activity (server),reason=Window]"


class FocusStopTest(unittest.TestCase):
    def _read(self, *lines):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "events.txt"
            path.write_text("\n".join(lines) + "\n")
            return K.focus_stop(path)

    def test_requests_answered_by_entries_are_not_a_stop(self):
        got = self._read(*[REQUEST, _enter()] * 10)
        self.assertEqual((got["requests"], got["entered"], got["longest"]), (10, 10, 1))

    def test_requests_left_unanswered_are_counted_from_the_last_entry(self):
        got = self._read(REQUEST, _enter("10:43:16.956"), LEAVE, *[REQUEST, NULL] * 7)
        self.assertEqual((got["requests"], got["entered"], got["longest"]), (8, 1, 7))
        self.assertEqual(got["since"], "11-05 10:43:16.956")

    def test_a_stop_that_recovers_is_still_the_longest_run(self):
        got = self._read(*[REQUEST] * 9, _enter(), REQUEST)
        self.assertEqual(got["longest"], 9)

    def test_a_missing_file_is_not_read_not_zero(self):
        self.assertIsNone(K.focus_stop(Path("/nonexistent/events.txt")))

    def test_a_log_with_no_focus_line_is_not_read_not_zero(self):
        self.assertIsNone(self._read("11-05 10:43:18.138   553   578 I am_anr  : [0,1187]"))


class JudgeSaysTheDeviceStoppedTest(unittest.TestCase):
    def _judge(self, *lines):
        """The judge's stderr and stdout for a checkout with the given events, or no file for None."""
        with tempfile.TemporaryDirectory() as d:
            kjui = Path(d)
            if lines != (None,):
                (kjui / "device-evidence").mkdir()
                (kjui / "device-evidence" / "logcat-events.txt").write_text("\n".join(lines) + "\n")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                K.judge(kjui)
            return out.getvalue(), err.getvalue()

    def test_at_the_threshold_it_is_named_and_red(self):
        out, err = self._judge(_enter("10:43:16.956"), *[REQUEST] * K.FOCUS_STOP_REQUESTS)
        self.assertIn("the device stopped taking window focus", err)
        self.assertIn(f"{K.FOCUS_STOP_REQUESTS} requests in a row", err)
        self.assertIn("11-05 10:43:16.956", err)

    def test_one_below_the_threshold_says_nothing_of_a_stop(self):
        out, err = self._judge(_enter(), *[REQUEST] * (K.FOCUS_STOP_REQUESTS - 1))
        self.assertNotIn("stopped taking window focus", err)
        self.assertIn(f"at most {K.FOCUS_STOP_REQUESTS - 1} in a row", out)

    def test_a_file_not_read_is_said_and_does_not_read_as_healthy(self):
        out, err = self._judge(None)
        self.assertIn("window focus not read", out)
        self.assertNotIn("stopped taking window focus", err)

    def test_the_threshold_is_above_every_healthy_run_and_below_every_stopped_one(self):
        # 42022979525 and eight runs before it: at most 4. 37650134866: 1084. 42011943298: 1121.
        self.assertGreater(K.FOCUS_STOP_REQUESTS, 4)
        self.assertLess(K.FOCUS_STOP_REQUESTS, 1084)


class EvidenceTest(unittest.TestCase):
    def test_the_first_failure_keeps_what_the_input_layer_holds(self):
        names = [name for name, _ in K.SNAPSHOT]
        self.assertIn("input.txt", names)
        self.assertIn("surfaceflinger.txt", names)

    def test_the_end_of_the_run_keeps_it_too(self):
        text = SHELL.read_text()
        self.assertIn('dumpsys input >"$evidence/input.txt"', text)
        self.assertIn('dumpsys SurfaceFlinger >"$evidence/surfaceflinger.txt"', text)


if __name__ == "__main__":
    unittest.main()
