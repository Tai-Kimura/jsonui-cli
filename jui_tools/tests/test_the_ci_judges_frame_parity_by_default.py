"""CI judges frame parity by default, and a gate that does not says so.

From jsonui-cli 1.9.17 conformance-mobile.yml passes `--frame-parity` unless a
dispatch says `frame_parity=false`. Two things made "on by default" untrue
before it was written:

- the step tested `[ "${{ inputs.frame_parity }}" = true ]`. A schedule run
  has NO inputs, so the expression is empty there and the schedule stayed off
  whatever the input's default said. The test is `!= false`.
- a gate run without the flag printed no frame-parity line at all, so "judged
  and agreed" and "never asked" were the same output. It now prints
  `frame parity: NOT judged (--frame-parity not given)`.

⚠️ The workflow arm reads the YAML as text; it is not GitHub Actions
evaluating the expression. The run-time evidence is the first CI run's gate
output carrying `note: frame parity (...): N fixture(s) compared`.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance.gate import FRAME_PARITY_NOT_JUDGED, evaluate

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "conformance-mobile.yml"


class TheWorkflowTurnsItOnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_the_input_defaults_to_true(self) -> None:
        block = re.search(r"\n      frame_parity:\n((?:        .*\n)+)", self.text)
        self.assertIsNotNone(block, "the frame_parity input is gone")
        self.assertRegex(block.group(1), r"\n        default: true\n|^        default: true\n")
        self.assertIn("type: boolean", block.group(1))

    def test_the_step_tests_not_false_so_the_schedule_runs_it(self) -> None:
        lines = [l for l in self.text.splitlines() if "--frame-parity" in l and "inputs.frame_parity" in l]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn('[ "${{ inputs.frame_parity }}" != false ] && args+=(--frame-parity)', lines[0])
        self.assertNotIn("= true ]", lines[0])


class AGateWithoutTheFlagSaysSoTests(unittest.TestCase):
    """Pure enough to run anywhere: visual off, the committed tree, a scratch report."""

    def _notices(self, frame_parity: bool) -> list[str]:
        out = Path(tempfile.mkdtemp()) / "REPORT.md"
        outcome = evaluate(
            REPO / "conformance", ["web"], out_path=out, visual=False, frame_parity=frame_parity
        )
        return outcome.notices

    def test_without_the_flag_the_gate_prints_not_judged(self) -> None:
        self.assertEqual(self._notices(False).count(FRAME_PARITY_NOT_JUDGED), 1)

    def test_with_the_flag_it_does_not(self) -> None:
        self.assertNotIn(FRAME_PARITY_NOT_JUDGED, self._notices(True))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
