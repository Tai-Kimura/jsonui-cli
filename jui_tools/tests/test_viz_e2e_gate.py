"""The browser suites' gate on the real server's progress folder is alive (tools/viz_e2e/common.py, 10-18).

run.py checks the real ~/.local/state/jui-viz/test-progress after the history and robot-tests suites: no file of
this run (one of its run ids or its output folder in the file) may have appeared there. Writing to the real folder to
show the gate can turn red would feed the real server a file, so the same gate is pointed at a temporary folder here:
a file of this run turns it red; another lane's run on the real HOME (2.3.21: 405 -> 412 at the same time) does not.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"))
import common  # noqa: E402


def record(run, **extra):
    return json.dumps({"v": 1, "t": 1, "platform": "web", "run": run, "event": "run_start", "files": 1, **extra}) + "\n"


def test_the_gate_is_red_on_a_file_of_this_run_and_quiet_on_another_lanes(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "E2E_MARKS", set())
    folder = tmp_path / "test-progress"
    before = common.progress_count(folder)
    assert before == {} and common.progress_grew("s", before, folder) is None          # no folder yet: quiet
    folder.mkdir()
    (folder / "other.txt").write_text("x")
    other = str(uuid.uuid4())
    (folder / f"{other}.jsonl").write_text(record(other))
    assert common.progress_grew("s", before, folder) is None                           # another lane's run: quiet
    ours = common.e2e_run_id()
    (folder / f"{ours}.jsonl").write_text(record(ours))
    assert common.progress_grew("s", before, folder) == f"s: this run wrote to the real test-progress folder (1: {ours}.jsonl)"
    assert common.progress_grew("s", common.progress_count(folder), folder) is None    # taken after: quiet again


def test_a_record_naming_this_runs_folder_is_this_runs(tmp_path, monkeypatch):
    out = tmp_path / "e2e-out"
    monkeypatch.setattr(common, "E2E_MARKS", {str(out)})
    folder = tmp_path / "test-progress"
    folder.mkdir()
    other = str(uuid.uuid4())
    (folder / f"{other}.jsonl").write_text(record(other, file="tests/a.test.json"))
    before = common.progress_count(folder)
    assert common.progress_grew("s", before, folder) is None
    with open(folder / f"{other}.jsonl", "a") as f:                                    # a file grown by this run
        f.write(record(other, file=f"{out}/robot-tests/home/tests/a.test.json"))
    assert common.progress_grew("s", before, folder) == f"s: this run wrote to the real test-progress folder (1: {other}.jsonl)"


def test_the_gate_checks_the_real_folder_by_default():
    assert common.REAL_PROGRESS == Path.home() / ".local" / "state" / "jui-viz" / "test-progress"
