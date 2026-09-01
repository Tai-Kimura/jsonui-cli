"""``jui sync_tool``'s totals must say what they counted.

The counters are per-vendored-platform-tool. `copied: 0` is therefore a
true statement with a denominator the line does not name, and three lanes
read it as one about the whole toolchain in a single release: two skipped
`branch-tests --check` after a version that changed the generator (which
ships in `test_tools`, via bootstrap, not via this command), and a third
nearly put that check on a deployment gate on the strength of `copied 0`.

The assertion here is not that a sentence is present. It is that the
sentence stays true: every tool this command can actually mirror has to be
named in it, so adding a fourth platform reddens this test until the line
is updated rather than leaving a denominator that quietly excludes one.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.sync_tool_cmd import PLATFORM_TO_TOOL, cmd_sync_tool

#: Trees that reach a machine through installer/bootstrap.sh and are NOT
#: counted by this command. Named so the message cannot drop one silently.
UNCOUNTED_TREES = ("test_tools", "document_tools")


def _run_dry_sync(project: Path, source: Path) -> str:
    args = argparse.Namespace(
        source=str(source), platform=None, prune=False, dry_run=True)
    out = io.StringIO()
    cwd = os.getcwd()
    os.chdir(project)
    try:
        with contextlib.redirect_stdout(out):
            cmd_sync_tool(args)
    finally:
        os.chdir(cwd)
    return out.getvalue()


def _counted_block(output: str) -> str:
    """Just the `counted:` sentence — not the whole run.

    Asserting against the whole output passes for the wrong reason: a tool
    name appears in the per-platform section whether or not the denominator
    line names it. Measured — adding a fourth entry to PLATFORM_TO_TOOL left
    a whole-output assertion green, because the new tool showed up in that
    platform's own section.
    """
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("counted:"):
            block = [line]
            for follow in lines[index + 1:]:
                if not follow.startswith(" " * 10) or follow.strip().startswith(
                        ("copied:", "counted:", "meta:")):
                    break
                block.append(follow)
            return "\n".join(block)
    return ""


class TotalsNameTheirDenominatorTest(unittest.TestCase):
    def _output(self) -> str:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "src"
            for tool in PLATFORM_TO_TOOL.values():
                (source / tool / "lib").mkdir(parents=True)
                (source / tool / "lib" / "x.rb").write_text("# x\n")
            (source / "VERSION").write_text("9.9.9\n")

            project = root / "project"
            for platform in PLATFORM_TO_TOOL:
                (project / platform).mkdir(parents=True)
            (project / "jui.config.json").write_text(json.dumps({
                "platforms": {p: {"root": p} for p in PLATFORM_TO_TOOL}}))
            return _run_dry_sync(project, source)

    def test_every_tool_it_counts_is_named(self):
        """A fourth platform tool must not join the count unannounced."""
        block = _counted_block(self._output())
        self.assertTrue(block, "the totals do not say what they counted")
        for tool in PLATFORM_TO_TOOL.values():
            self.assertIn(tool, block, f"{tool} is counted but not named")

    def test_the_trees_it_does_not_count_are_named(self):
        """The reading that went wrong was `0` about something uncounted."""
        block = _counted_block(self._output())
        for tree in UNCOUNTED_TREES:
            self.assertIn(tree, block, f"{tree} is not counted and not named")

    def test_it_says_how_the_uncounted_trees_arrive(self):
        """Naming the exclusion without naming the remedy leaves the reader
        where they were: knowing a number is narrow, not what to run."""
        self.assertIn("bootstrap", _counted_block(self._output()))


if __name__ == "__main__":
    unittest.main()
