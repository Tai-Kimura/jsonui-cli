"""The manifest records which version WROTE each generated file.

A defective 1.8.2 shipped and 1.8.3 fixed it; every consumer was told to
regenerate if their tree came from 1.8.2, and none could read that from
their own files. One approximated with mtimes — which say when, not by
what — and translating that into a version needed the release lane's
timetable.

The property that makes it worth having is that it does not overstate. A
partial regeneration must leave untouched files at the version that last
wrote them: a manifest claiming the current version for a file it never
looked at is worse than no manifest, because a record is trusted in a way a
guess is not.

Each test below is one of the three arms that a half-done implementation
would fail differently:
  (a) a full run records every file;
  (b) a partial run records only what it touched, and the rest keep their
      older version;
  (c) a file that disappeared stops being claimed at all.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core import generation_manifest as gm


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.gen = self.root / "gen"
        self.gen.mkdir()
        self.files = []
        for name in ("A.kt", "B.kt", "C.kt"):
            path = self.gen / name
            path.write_text(f"// {name} v1\n", encoding="utf-8")
            self.files.append(path)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, version):
        run = gm.GenerationRun(project_root=self.root, version=version)
        run.observe(self.files)
        return run

    def _save(self, run, present=None):
        paths = present if present is not None else self.files
        written = run.written(paths)
        gm.save(self.root, run.version, written,
                present_keys=[run._key(p) for p in paths])
        return written

    def _versions(self):
        data = json.loads(gm.manifest_path(self.root).read_text(encoding="utf-8"))
        return {k: v["version"] for k, v in data["files"].items()}

    # (a) ---------------------------------------------------------------
    def test_a_full_run_records_every_file(self):
        run = self._run("1.8.4")
        for path in self.files:
            path.write_text("// rewritten by 1.8.4\n", encoding="utf-8")
        written = self._save(run)

        self.assertEqual(3, len(written))
        self.assertEqual(
            {"gen/A.kt": "1.8.4", "gen/B.kt": "1.8.4", "gen/C.kt": "1.8.4"},
            self._versions(),
        )

    # (b) ---------------------------------------------------------------
    def test_a_partial_run_leaves_untouched_files_at_their_old_version(self):
        first = self._run("1.8.3")
        for path in self.files:
            path.write_text("// written by 1.8.3\n", encoding="utf-8")
        self._save(first)
        self.assertEqual({"gen/A.kt": "1.8.3", "gen/B.kt": "1.8.3",
                          "gen/C.kt": "1.8.3"}, self._versions())

        # Regenerate one file only, as `jui g project --file <spec>` does.
        second = self._run("1.8.4")
        self.files[0].write_text("// rewritten by 1.8.4\n", encoding="utf-8")
        written = self._save(second)

        self.assertEqual(["gen/A.kt"], written)
        self.assertEqual(
            {"gen/A.kt": "1.8.4", "gen/B.kt": "1.8.3", "gen/C.kt": "1.8.3"},
            self._versions(),
            "a file this run never wrote must not be claimed for its version",
        )

    def test_the_line_names_both_numbers(self):
        # A partial run reporting only its numerator reads like a full one.
        line = gm.coverage_line(1, 3, "1.8.4")
        self.assertIn("wrote 1 of 3", line)
        self.assertIn("1.8.4", line)
        # And says what it is not, since a reader's next move depends on it.
        self.assertIn("records writes, not currency", line)

    # (c) ---------------------------------------------------------------
    def test_a_file_that_disappeared_is_no_longer_claimed(self):
        first = self._run("1.8.3")
        for path in self.files:
            path.write_text("// written by 1.8.3\n", encoding="utf-8")
        self._save(first)

        self.files[1].unlink()
        remaining = [self.files[0], self.files[2]]
        second = gm.GenerationRun(project_root=self.root, version="1.8.4")
        second.observe(remaining)
        self._save(second, present=remaining)

        versions = self._versions()
        self.assertNotIn("gen/B.kt", versions,
                         "the manifest kept asserting a version for a file "
                         "that is not there")
        self.assertEqual({"gen/A.kt", "gen/C.kt"}, set(versions))

    # The limitation, pinned so it cannot be quietly lost -----------------
    def test_an_unwritten_file_keeps_its_version_even_on_a_later_run(self):
        # A generator that produces byte-identical content and skips the
        # write leaves the earlier version in place. That is the honest
        # answer for a manifest that records writes — and the reason the
        # line says so out loud rather than implying currency.
        first = self._run("1.8.3")
        for path in self.files:
            path.write_text("// stable output\n", encoding="utf-8")
        self._save(first)

        second = self._run("1.8.4")  # nothing rewritten
        written = self._save(second)

        self.assertEqual([], written)
        self.assertEqual({"gen/A.kt": "1.8.3", "gen/B.kt": "1.8.3",
                          "gen/C.kt": "1.8.3"}, self._versions())

    def test_the_manifest_is_not_the_sync_record(self):
        # Two different facts: which toolchain copy a project holds, and
        # which version wrote its outputs. One file cannot answer both.
        self.assertEqual("generation-manifest.json", gm.MANIFEST_FILENAME)
        self.assertNotEqual("sync-meta.json", gm.MANIFEST_FILENAME)


if __name__ == "__main__":
    unittest.main()
