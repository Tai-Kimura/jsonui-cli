"""`jui build` must not exit 0 over a screen it failed to generate.

Measured on 1.8.42 (`9b76082c`), a throwaway web project, one layout whose
Collection declares `sections: "@{secs}"`:

    [ERROR] Error processing src/Layouts/sample.json: undefined method `each'
    [ERROR] 1 stage(s) did not complete; the build carried on without them
    [ERROR] Build finished with 1 stage(s) incomplete — see above
    exit 0, and src/generated/components/Sample.jsx absent

Four `[ERROR]` lines, zero screens written, exit 0. A CI gating on the exit
code goes green and ships the hole. The 1.8.15 fix reached the closing LINE
and not the exit code, which is why the consumer's own build kept a
hand-rolled guard (`grep [ERROR]` on the log) for this exact case.

`jsonui-doc generate html` already makes the opposite call, and this now
matches it verbatim in judgment and in flag name: a partial tree fails the
command unless `--allow-partial` says otherwise.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands import build_cmd


class _Args:
    def __init__(self, allow_partial: bool = False):
        self.allow_partial = allow_partial


class StageLedgerReading(unittest.TestCase):
    """The ledger the three faces write, as python reads it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "stage-failures.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_ledger_file_means_nothing_failed(self):
        self.assertEqual(build_cmd._stage_failures(self.ledger), [])

    def test_entries_are_read_back(self):
        self.ledger.write_text(
            json.dumps([{"stage": "layout", "detail": "src/Layouts/sample.json"}]),
            encoding="utf-8",
        )
        self.assertEqual(len(build_cmd._stage_failures(self.ledger)), 1)


class ExitDecision(unittest.TestCase):
    """The three arms. The exit code is the whole point of the ticket, so it
    is asserted directly rather than inferred from the printed text — the
    1.8.15 fix changed the text and left the code at 0."""

    def test_incomplete_without_the_flag_is_a_failure(self):
        self.assertEqual(build_cmd._exit_for_incomplete(["one"], _Args()), 1)

    def test_incomplete_with_allow_partial_is_accepted(self):
        self.assertEqual(
            build_cmd._exit_for_incomplete(["one"], _Args(allow_partial=True)), 0
        )

    def test_a_clean_build_is_zero(self):
        self.assertEqual(build_cmd._exit_for_incomplete([], _Args()), 0)

    def test_a_clean_build_is_zero_with_the_flag_too(self):
        # --allow-partial must not change the healthy path in any way.
        self.assertEqual(
            build_cmd._exit_for_incomplete([], _Args(allow_partial=True)), 0
        )

    def test_a_caller_without_the_attribute_still_fails_closed(self):
        # Other entry points build their own args object (the MCP tool, the
        # older callers). Missing the flag must mean "not allowed", not
        # "crash" and not "allowed".
        class Bare:
            pass

        self.assertEqual(build_cmd._exit_for_incomplete(["one"], Bare()), 1)


if __name__ == "__main__":
    unittest.main()
