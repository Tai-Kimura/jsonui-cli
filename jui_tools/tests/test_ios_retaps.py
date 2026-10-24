"""The iOS conformance's named retaps (.github/scripts/ios_retaps.py; ticket 2026-10-24-ios-conformance-tap-not-
delivered-recurred, the requester's choice B): every retap written and said, and the gate's two rules of its own —
more than two in a run, the same fixture on two runs in a row — with the run before read through a stand-in API."""
from __future__ import annotations

import importlib.util
import io
import json
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "ios_retaps.py"


def _load():
    spec = importlib.util.spec_from_file_location("ios_retaps", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _load()
REPO = "o/r"


def _retap(fid, shot=None):
    return {"id": fid, "tap": "under_button", "at": 0.458, "screenshot": shot or f"artifacts/ios/{fid}.png",
            "reason": "touch not delivered"}


def _record(run, attempt, *ids):
    return {"run_id": str(run), "run_attempt": str(attempt), "head_sha": "x", "retaps": [_retap(i) for i in ids]}


def _zip(data: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("retaps.json", json.dumps(data))
    return buf.getvalue()


class World:
    """A stand-in for `gh api`: runs (id -> started), their ios-retaps artifacts, and what each holds."""

    def __init__(self):
        self.runs = {}        # run id -> started
        self.artifacts = {}   # run id -> [artifact dicts]
        self.blobs = {}       # artifact id -> bytes
        self.fail = set()     # paths that raise
        self.next_id = 1

    def run(self, run_id, started, *records, expired=False):
        self.runs[run_id] = started
        self.artifacts[run_id] = []
        for attempt, data in records:
            aid = self.next_id
            self.next_id += 1
            self.artifacts[run_id].append({"id": aid, "name": f"ios-retaps-a{attempt}", "expired": expired})
            self.blobs[aid] = _zip(data)

    def api(self, path):
        if path in self.fail:
            raise RuntimeError("HTTP 502")
        parts = path.split("?")[0].split("/")
        if parts[-1] == "artifacts":
            return {"artifacts": self.artifacts.get(parts[-2], [])}
        if parts[-1] == "runs":
            return {"workflow_runs": [{"id": int(r), "run_started_at": s} for r, s in self.runs.items()]}
        return {"id": int(parts[-1]), "run_started_at": self.runs[parts[-1]]}

    def download(self, aid):
        return self.blobs[aid]


def test_write_says_every_retap_and_records_them(tmp_path):
    results = {"results": [{"id": "common/a", "status": "pass"},
                           {"id": "common/clipToBounds__hit_overflow_true", "status": "pass",
                            "retap": {"reason": "touch not delivered", "tap": "under_button", "at": 0.458,
                                      "before": "exists=true", "after": "exists=true", "screenshot": "artifacts/ios/c.png"}}]}
    src, out = tmp_path / "ios.results.json", tmp_path / "retaps.json"
    src.write_text(json.dumps(results))
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert R.main(["write", str(src), str(out), "--run-id", "40", "--attempt", "2", "--sha", "abc"]) == 0
    said = buf.getvalue()
    assert "RETAP common/clipToBounds__hit_overflow_true: tap(under_button) at +0.458s — touch not delivered" in said
    assert "1 fixture(s) passed on a second tap" in said
    got = json.loads(out.read_text())
    assert got["run_id"] == "40" and got["run_attempt"] == "2" and [r["id"] for r in got["retaps"]] == ["common/clipToBounds__hit_overflow_true"]


def test_the_rules():
    assert R.judge(_record(9, 1, "a", "b"), _record(8, 1, "c"), "run 8") == []
    over = R.judge(_record(9, 1, "a", "b", "c"), None, "unknown")
    assert len(over) == 1 and "3 retaps in run 9 attempt 1 (more than 2): a, b, c" in over[0]
    twice = R.judge(_record(9, 2, "a"), _record(9, 1, "a"), "run 9 ios-retaps-a1")
    assert len(twice) == 1 and twice[0].startswith("a retapped twice in a row: run 9 attempt 2") and "run 9 ios-retaps-a1" in twice[0]
    assert R.judge(_record(9, 1, "a"), None, "unknown") == []   # unknown: not counted, neither green nor red by itself


def test_the_run_before_is_this_runs_attempt_before():
    w = World()
    w.run("9", "2026-10-24T02:00:00Z", (1, _record(9, 1, "a")), (2, _record(9, 2)))
    w.run("8", "2026-10-23T02:00:00Z", (1, _record(8, 1, "z")))
    before, said = R.previous(w.api, w.download, REPO, "9", 2, "m.yml")
    assert before["retaps"][0]["id"] == "a" and said == "run 9 ios-retaps-a1"


def test_a_first_attempt_reads_the_last_earlier_run_that_left_a_record():
    w = World()
    w.run("9", "2026-10-24T02:00:00Z", (1, _record(9, 1)))
    w.run("10", "2026-10-24T05:00:00Z", (1, _record(10, 1, "later")))   # started after: never "before"
    w.run("8", "2026-10-23T09:00:00Z")                                  # no iOS: skipped, said
    w.run("7", "2026-10-23T02:00:00Z", (1, _record(7, 1, "a")), (2, _record(7, 2, "b")))   # its latest attempt
    before, said = R.previous(w.api, w.download, REPO, "9", 1, "m.yml")
    assert [r["id"] for r in before["retaps"]] == ["b"] and said == "run 7 ios-retaps-a2"


def test_unknown_is_said_not_counted():
    w = World()
    w.run("9", "2026-10-24T02:00:00Z", (1, _record(9, 1)))
    w.run("8", "2026-10-23T02:00:00Z", (1, _record(8, 1, "a")), expired=True)
    before, said = R.previous(w.api, w.download, REPO, "9", 1, "m.yml")
    assert before is None and "expired" in said
    w.fail.add("repos/o/r/actions/runs/9/artifacts?per_page=100")
    before, said = R.previous(w.api, w.download, REPO, "9", 2, "m.yml")
    assert before is None and "could not be listed (HTTP 502)" in said


def test_judge_exits_red_naming_both_runs_and_green_otherwise(tmp_path):
    w = World()
    w.run("9", "2026-10-24T02:00:00Z", (1, _record(9, 1, "a")), (2, _record(9, 2, "a")))
    cur = tmp_path / "retaps.json"
    cur.write_text(json.dumps(_record(9, 2, "a")))
    args = ["judge", str(cur), "--repo", REPO, "--run-id", "9", "--attempt", "2", "--workflow", "m.yml"]
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert R.main(args, api=w.api, download=w.download) == 1
    assert "::error::a retapped twice in a row: run 9 attempt 2" in buf.getvalue()
    cur.write_text(json.dumps(_record(9, 2, "b")))
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert R.main(args, api=w.api, download=w.download) == 0
    assert "[retaps] the run before: run 9 ios-retaps-a1, 1 retap(s)" in buf.getvalue()
    w.fail.add("repos/o/r/actions/runs/9/artifacts?per_page=100")
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert R.main(args, api=w.api, download=w.download) == 0
    assert "the run before: unknown" in buf.getvalue() and "'twice in a row' is not counted" in buf.getvalue()
