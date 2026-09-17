"""`.rspec_status` and `.byebug_history` are files, and sync must skip them.

Both names sat in `SKIP_DIR_NAMES`, so `_should_skip(name, is_dir)` only ever
saw them on the `is_dir` branch — which a file never takes. Syncing from a
checkout that had run rspec delivered `rjui_tools/spec/.rspec_status` (about
190 KB of example status persistence) to the consumer as `copied: 1`; the
docsite lane measured it on 2026-09-17 while pinning to a local checkout. A
name that means "never sync this" has to be judged by its name, not by which
list a guess about its kind put it in.

Two arms: the file arm is red before the fix, and the directory arm is the
control that the existing pruning of skippable DIRECTORIES did not move.
"""
from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.sync_tool_cmd import _should_skip, _sync_one_tool


def _write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class SkipNamesAreJudgedByName(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sync_skipnames_"))
        self.src = self.tmp / "checkout" / "rjui_tools"
        self.dst = self.tmp / "face" / "rjui_tools"
        _write(self.src / "lib" / "thing.rb", "class Thing; end")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sync(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            return _sync_one_tool(self.src, self.dst, self.tmp / "face",
                                  prune=False, dry_run=False)

    def test_the_names_are_skipped_as_files(self):
        """The unit: a skip-listed FILE name skips with is_dir=False."""
        for name in (".rspec_status", ".byebug_history"):
            with self.subTest(name=name):
                self.assertTrue(_should_skip(name, False), name)

    def test_rspec_status_does_not_reach_the_face(self):
        """The symptom: a checkout that ran rspec, synced as the pin."""
        _write(self.src / "spec" / ".rspec_status", "example_id | status | run_time")
        _write(self.src / "spec" / "thing_spec.rb", "describe Thing")
        counters = self._sync()
        self.assertFalse((self.dst / "spec" / ".rspec_status").exists())
        # The control in the same tree: a real spec file the checkout ships
        # still arrives, so this is a name skip and not a `spec/` skip.
        self.assertTrue((self.dst / "spec" / "thing_spec.rb").exists())
        self.assertEqual(counters["copied"], 2)  # lib/thing.rb + spec/thing_spec.rb

    def test_skippable_directories_still_prune(self):
        """Control: the directory side keeps its existing behaviour."""
        _write(self.src / "lib" / "hotloader" / "node_modules" / "left-pad" / "index.js")
        _write(self.src / "lib" / "__pycache__" / "thing.cpython-312.pyc")
        _write(self.src / "coverage" / "index.html", "<html>")
        counters = self._sync()
        self.assertFalse((self.dst / "lib" / "hotloader" / "node_modules").exists())
        self.assertFalse((self.dst / "lib" / "__pycache__").exists())
        self.assertFalse((self.dst / "coverage").exists())
        self.assertTrue((self.dst / "lib" / "thing.rb").exists())
        self.assertEqual(counters["copied"], 1)
        for name in ("node_modules", "__pycache__", "coverage"):
            self.assertTrue(_should_skip(name, True), name)
