"""Regression: generation-manifest-generatedat-ignores-source-date-epoch.

Every page the doc generator writes takes its timestamp through
`reproducible` (`SOURCE_DATE_EPOCH`), so a receiver can run twice with the
clock pinned and `cmp` the output. The one stamp that did not was the
manifest's own `generatedAt`, written by `shared/core` from
`datetime.now(timezone.utc)` — measured on rel/v1.8.109 as the control arm
of a document_tools test going red 1 run in 5: same inputs, pinned clock,
and the manifest moved by one second.

These arms drive `save` directly, so the red is deterministic rather than
"did the two runs straddle a second boundary": with the variable set, the
entry stamp IS the pinned instant, or it is not.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from jui_cli.core import generation_manifest as gm

#: 2023-11-14T22:13:20Z — a value the wall clock cannot produce by accident.
PINNED = "1700000000"
PINNED_STAMP = "2023-11-14T22:13:20Z"


class StampTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.path = self.root / "gen" / "A.kt"
        self.path.parent.mkdir()
        self.path.write_text("// A\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _save(self, *, recorded_at=None) -> dict:
        run = gm.GenerationRun(project_root=self.root, version="t")
        run.observe([self.path], roots=[self.root / "gen"])
        run.written([self.path], known=set())
        if recorded_at is not None:
            run.record_time(recorded_at)
        return gm.save(run, generated_by="arm")

    def _stamp(self, manifest: dict) -> str:
        return manifest["files"]["gen/A.kt"]["generatedAt"]

    def test_a_pinned_clock_is_the_entry_stamp(self):
        with mock.patch.dict(os.environ, {gm.SOURCE_DATE_EPOCH: PINNED}):
            self.assertEqual(self._stamp(self._save()), PINNED_STAMP)

    def test_two_pinned_saves_write_identical_bytes(self):
        """The receiver's own check, in miniature: pinned, twice, `cmp`."""
        with mock.patch.dict(os.environ, {gm.SOURCE_DATE_EPOCH: PINNED}):
            self._save()
            first = gm.manifest_path(self.root).read_bytes()
            self._save()
            second = gm.manifest_path(self.root).read_bytes()
        self.assertEqual(first, second)

    def test_unset_means_the_wall_clock_as_before(self):
        env = {k: v for k, v in os.environ.items() if k != gm.SOURCE_DATE_EPOCH}
        with mock.patch.dict(os.environ, env, clear=True):
            stamp = self._stamp(self._save())
        self.assertNotEqual(stamp, PINNED_STAMP)
        written = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertLess(abs((datetime.now(timezone.utc) - written).total_seconds()), 60)

    def test_a_recorded_time_wins_over_the_environment(self):
        """jsonui-doc records the instant it chose through its own pin —
        which a test patches in-process, where no environment variable can
        reach — and every entry carries THAT, so `files[*].generatedAt` and
        `summary.run.recordedAt` agree to the second."""
        with mock.patch.dict(os.environ, {gm.SOURCE_DATE_EPOCH: PINNED}):
            manifest = self._save(recorded_at="2026-09-17T00:00:00Z")
        self.assertEqual(self._stamp(manifest), "2026-09-17T00:00:00Z")
        self.assertEqual(manifest["summary"]["run"]["recordedAt"], "2026-09-17T00:00:00Z")

    def test_a_malformed_pin_is_named_and_the_wall_clock_is_used(self):
        """Ignored, but not silently: the problem is a value a caller with a
        warning channel prints. `reproducible.py` in document_tools makes the
        same choice for the pages."""
        with mock.patch.dict(os.environ, {gm.SOURCE_DATE_EPOCH: "yesterday"}):
            problem = gm.source_date_epoch_problem()
            stamp = self._stamp(self._save())
        self.assertIsNotNone(problem)
        self.assertIn("'yesterday'", problem)
        self.assertNotEqual(stamp, PINNED_STAMP)
        with mock.patch.dict(os.environ, {gm.SOURCE_DATE_EPOCH: PINNED}):
            self.assertIsNone(gm.source_date_epoch_problem())
        with mock.patch.dict(os.environ, {gm.SOURCE_DATE_EPOCH: "  "}):
            self.assertIsNone(gm.source_date_epoch_problem(), "blank is unset, not malformed")

    def test_jui_build_prints_the_malformed_pin_as_a_warning(self):
        """The build's `_record_generation` is the caller with the channel:
        `WARNING [manifest]:` on stderr, the shape the gate counts."""
        from jui_cli.commands import build_cmd

        class _Cfg:
            project_root = self.root

        run = gm.GenerationRun(project_root=self.root, version="t")
        run.observe([self.path], roots=[self.root / "gen"])
        err = io.StringIO()
        with mock.patch.dict(os.environ, {gm.SOURCE_DATE_EPOCH: "yesterday"}), \
                mock.patch.object(build_cmd, "_distributed_files", lambda cfg: []), \
                redirect_stderr(err):
            build_cmd._record_generation(_Cfg(), run, [self.path])
        self.assertIn("WARNING [manifest]: SOURCE_DATE_EPOCH is not an integer ('yesterday')",
                      err.getvalue())
        # The record is removed first: the file already has an entry and its
        # bytes did not move, so a second run over the same record would
        # (correctly) leave that entry alone rather than re-stamp it.
        gm.manifest_path(self.root).unlink()
        err = io.StringIO()
        run = gm.GenerationRun(project_root=self.root, version="t")
        run.observe([self.path], roots=[self.root / "gen"])
        with mock.patch.dict(os.environ, {gm.SOURCE_DATE_EPOCH: PINNED}), \
                mock.patch.object(build_cmd, "_distributed_files", lambda cfg: []), \
                redirect_stderr(err):
            build_cmd._record_generation(_Cfg(), run, [self.path])
        self.assertNotIn("WARNING", err.getvalue())
        data = json.loads(gm.manifest_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(data["files"]["gen/A.kt"]["generatedAt"], PINNED_STAMP,
                         "the build's own path, end to end")


if __name__ == "__main__":
    unittest.main()
