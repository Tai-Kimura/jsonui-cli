"""The browser suites' gate on the real server's progress folder is alive (tools/viz_e2e/common.py, 10-18).

run.py counts the real ~/.local/state/jui-viz/test-progress after the history and robot-tests suites. Writing to the
real folder to show the gate can turn red would feed the real server a file, so the same gate is pointed at a
temporary folder here: one file written turns it red, none keeps it quiet.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"))
import common  # noqa: E402


def test_the_gate_is_red_when_the_folder_grew_and_quiet_when_not(tmp_path):
    folder = tmp_path / "test-progress"
    before = common.progress_count(folder)
    assert before == 0 and common.progress_grew("s", before, folder) is None          # no folder yet: quiet
    folder.mkdir()
    (folder / "other.txt").write_text("x")
    assert common.progress_grew("s", before, folder) is None                          # not a progress file
    (folder / "0000.jsonl").write_text("{}\n")
    assert common.progress_grew("s", before, folder) == "s: the real test-progress folder grew (0 -> 1)"
    assert common.progress_grew("s", common.progress_count(folder), folder) is None   # counted after: quiet again


def test_the_gate_counts_the_real_folder_by_default():
    assert common.REAL_PROGRESS == Path.home() / ".local" / "state" / "jui-viz" / "test-progress"
