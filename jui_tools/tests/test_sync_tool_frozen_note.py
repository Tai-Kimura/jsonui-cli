"""What the destination has and the source does not, `sync_tool` names.

`jui sync_tool` mirrors a tool directory and preserves `extensions/`. What
it does with a directory that exists only in the destination is nothing at
all: it neither updates nor removes it, so the directory sits in the
consumer's tree looking exactly as synced as the code beside it.

The measured case is `spec/`. The distributed `rjui_tools` carries no
`spec/`, so each face keeps whatever spec tree it vendored once. One face's
is 73 files frozen at 2026-08-10, tracked in git, and named in no gate — so
it cannot go falsely green. What it produces instead is a person reading
"there are tests here" and not looking. On the day this was filed, that
tree held a 182-line spec pinning a helper that had changed by +101 lines
that morning.

Deleting is the consumer's call (their tree, their `git status`), so the
command's job is to make the invisible sayable: one line, with the freeze
date, because "it is there" is not the question and "how old is it" is.

The exclusions are each measured, not guessed. Run unfiltered over the 27
vendored trees on the maintainer's machine, the rule produced 32 lines: 9
of them `shared/`, which THIS COMMAND WRITES (from the CLI root, so it is
absent from the source tool directory and a naive test calls it unsynced),
and 8 `coverage/`, a generated HTML report nobody mistakes for a check.
With both excluded: 15 lines, one per tree, every one `spec/`.
"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from jui_cli.commands.sync_tool_cmd import _sync_one_tool


def _write(path: Path, text: str = "x", mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


class FrozenTreeIsNamed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sync_note_"))
        self.source_root = self.tmp / "source"   # the CLI root, as the command is given it
        self.src = self.source_root / "rjui_tools"
        self.dst = self.tmp / "face" / "rjui_tools"
        self.platform_root = self.tmp / "face"
        _write(self.src / "lib" / "thing.rb", "class Thing; end")
        _write(self.dst / "lib" / "thing.rb", "class Thing; end")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sync(self, **kwargs):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            counters = _sync_one_tool(
                self.src, self.dst, self.platform_root,
                prune=kwargs.pop("prune", False),
                dry_run=kwargs.pop("dry_run", False),
                **kwargs,
            )
        return out.getvalue(), counters

    def test_a_spec_tree_the_source_does_not_have_is_named_with_its_date(self):
        frozen = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
        _write(self.dst / "spec" / "thing_spec.rb", "describe Thing", mtime=frozen)
        text, counters = self._sync()
        self.assertIn("spec/ is not synced", text)
        self.assertIn("frozen 2026-08-10", text)
        self.assertIn("does not run against the lib just synced", text)
        self.assertEqual(counters["unsynced"], 1)

    def test_the_date_is_the_newest_file_in_the_tree(self):
        old = time.mktime((2026, 1, 1, 12, 0, 0, 0, 0, -1))
        new = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
        _write(self.dst / "spec" / "a_spec.rb", "a", mtime=old)
        _write(self.dst / "spec" / "b_spec.rb", "b", mtime=new)
        text, _ = self._sync()
        self.assertIn("frozen 2026-08-10", text)

    def test_a_source_that_carries_spec_says_nothing(self):
        # The control: a pin-checkout source DOES ship spec/, and then the
        # tree is synced like everything else. Without this arm the note
        # could fire on every sync and still pass the arm above.
        _write(self.src / "spec" / "thing_spec.rb", "describe Thing")
        _write(self.dst / "spec" / "thing_spec.rb", "describe Thing")
        text, counters = self._sync()
        self.assertNotIn("not synced", text)
        self.assertEqual(counters["unsynced"], 0)

    def test_extensions_is_never_named(self):
        # It is the consumer's own by design and the command preserves it.
        _write(self.dst / "extensions" / "face_thing.rb", "class FaceThing; end")
        text, counters = self._sync()
        self.assertNotIn("not synced", text)
        self.assertEqual(counters["unsynced"], 0)

    def test_a_directory_this_command_writes_is_never_named(self):
        # `shared/` reaches the target from the CLI ROOT, not from the source
        # tool directory, so "absent from the source" is true of it and
        # naming it would be a lie about the command's own work. Measured: 9
        # of the first 32 lines were this.
        #
        # The tree here carries a .rb ON PURPOSE. With only the JSON payload
        # the real `shared/` holds, this arm passed with the exclusion
        # DELETED — the source-suffix filter was quietly doing the work, and
        # the arm was not testing the rule its name claims. (Registered as a
        # 1-failure prediction for that red check; measured 0.)
        _write(self.dst / "shared" / "core" / "attribute_definitions.json", "{}")
        _write(self.dst / "shared" / "core" / "loader.rb", "# ruby in a synced tree")
        text, counters = self._sync(source_root=self.source_root)
        self.assertNotIn("shared/", text)
        self.assertEqual(counters["unsynced"], 0)

    def test_a_generated_report_is_not_named(self):
        # `coverage/` is stale too, but nobody reads an HTML report as a
        # check, and a second line costs the first one its attention.
        _write(self.dst / "coverage" / "index.html", "<html>")
        _write(self.dst / "coverage" / "assets" / "app.js", "//")
        text, counters = self._sync()
        self.assertNotIn("coverage/", text)
        self.assertEqual(counters["unsynced"], 0)

    def test_an_empty_directory_is_not_named(self):
        (self.dst / "spec").mkdir(parents=True)
        text, counters = self._sync()
        self.assertNotIn("not synced", text)
        self.assertEqual(counters["unsynced"], 0)

    def test_it_is_said_on_a_dry_run_too_and_the_dry_run_writes_nothing(self):
        # The note is worth more before the sync than after, and a dry run
        # that writes is a trap of its own (a sibling command's --dry-run
        # rewrites a tracked cache file). Both halves are asserted here.
        frozen = time.mktime((2026, 8, 10, 12, 0, 0, 0, 0, -1))
        _write(self.dst / "spec" / "thing_spec.rb", "describe Thing", mtime=frozen)
        _write(self.src / "lib" / "new_file.rb", "class New; end")
        before = {
            p: p.stat().st_mtime_ns
            for p in self.dst.rglob("*") if p.is_file()
        }
        text, counters = self._sync(dry_run=True)
        self.assertIn("spec/ is not synced", text)
        self.assertEqual(counters["unsynced"], 1)
        after = {p: p.stat().st_mtime_ns for p in self.dst.rglob("*") if p.is_file()}
        self.assertEqual(before, after, "the dry run wrote to the target tree")


if __name__ == "__main__":
    unittest.main()
