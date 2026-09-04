"""`spec/` and `coverage/` are residue, and sync deletes them by default.

The source does not ship either — `spec/` is absent from the distribution
entirely (bootstrap carries none) and `coverage/` is a generated report — so
a vendored tree that has them got them from an older sync whose source was a
git CHECKOUT. Measured 2026-09-04 across the faces: 74-338 files each, all
git-tracked, in no consumer gate, one of them holding an rspec `examples.txt`
(a pass/fail record) 100 KB long. Nothing removed them, because sync only
adds; deletion was opt-in behind `--prune`.

`--prune` stays opt-in because it is the whole-tree version: on one measured
face it would have deleted 2006 files, and 1647 of those were a vendored
`lib/hotloader/node_modules` — deleting that breaks hot reload. The default
here is exactly two top-level names, and the test is "absent from THIS
source", so a face syncing from a pin checkout keeps the `spec/` that
checkout ships.
"""
from __future__ import annotations

import io
import contextlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.sync_tool_cmd import _sync_one_tool


def _write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class PrunesUndistributedTrees(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sync_prune_"))
        self.src = self.tmp / "source" / "rjui_tools"
        self.dst = self.tmp / "face" / "rjui_tools"
        self.platform_root = self.tmp / "face"
        _write(self.src / "lib" / "thing.rb", "class Thing; end")
        _write(self.dst / "lib" / "thing.rb", "class Thing; end")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sync(self, prune: bool = False, dry_run: bool = False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            counters = _sync_one_tool(self.src, self.dst, self.platform_root,
                                      prune=prune, dry_run=dry_run)
        return out.getvalue(), counters

    def test_a_spec_tree_the_source_does_not_ship_is_deleted(self):
        _write(self.dst / "spec" / "thing_spec.rb", "describe Thing")
        _write(self.dst / "spec" / "examples.txt", "example_id | status")
        text, counters = self._sync()
        self.assertFalse((self.dst / "spec").exists())
        self.assertEqual(counters["pruned"], 2)
        self.assertIn("pruned:", text)
        self.assertIn("spec/", text)

    def test_coverage_goes_too(self):
        _write(self.dst / "coverage" / "index.html", "<html>")
        self._sync()
        self.assertFalse((self.dst / "coverage").exists())

    def test_extensions_and_node_modules_are_untouched(self):
        # `extensions/` is the consumer's own by design. A vendored
        # `node_modules` is what makes the whole-tree --prune dangerous: on
        # one face it holds 1647 of the 2006 prunable files and hot reload
        # needs it. Neither is in the list, and the nested one is not even
        # top-level.
        ext = _write(self.dst / "extensions" / "face_thing.rb", "class FaceThing; end")
        top_nm = _write(self.dst / "node_modules" / "pkg" / "index.js", "//")
        nested_nm = _write(self.dst / "lib" / "hotloader" / "node_modules" / "ws" / "index.js", "//")
        self._sync()
        for survivor in (ext, top_nm, nested_nm):
            self.assertTrue(survivor.exists(), survivor)

    def test_a_source_that_ships_spec_keeps_it(self):
        # Syncing from a pin CHECKOUT: `spec/` is content there, not
        # residue. Deleting it would fight the source just copied from.
        _write(self.src / "spec" / "thing_spec.rb", "describe Thing")
        _write(self.dst / "spec" / "thing_spec.rb", "describe Thing")
        text, counters = self._sync()
        self.assertTrue((self.dst / "spec" / "thing_spec.rb").exists())
        self.assertEqual(counters["pruned"], 0)
        self.assertNotIn("pruned:", text)

    def test_a_dry_run_says_so_and_deletes_nothing(self):
        spec = _write(self.dst / "spec" / "thing_spec.rb", "describe Thing")
        text, counters = self._sync(dry_run=True)
        self.assertTrue(spec.exists())
        self.assertIn("would prune:", text)
        self.assertEqual(counters["pruned"], 1)


if __name__ == "__main__":
    unittest.main()
