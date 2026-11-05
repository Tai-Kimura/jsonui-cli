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


def _retap(fid, shot=None, at=0.458):
    return {"id": fid, "tap": "under_button", "at": at, "screenshot": shot or f"artifacts/ios/{fid}.png",
            "reason": "touch not delivered"}


def _record(run, attempt, *ids):
    # a retap's time differs from one attempt to the next: the same time in one run is the same touch, carried over
    return {"run_id": str(run), "run_attempt": str(attempt), "head_sha": "x",
            "retaps": [_retap(i, at=0.4 + attempt / 100) for i in ids]}


def _row(probe, what, kind="retap", attempt="1"):
    return {"probe": probe, "what": what, "kind": kind, "attempt": attempt, "said": "no effect"}


def _probes(run, attempt, *rows, face="ios", ids=()):
    return dict(_record(run, attempt, *ids), face=face, probe_retaps=list(rows), probe_cases=10, unread=[])


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
            face = data.get("face", "ios")
            self.artifacts[run_id].append({"id": aid, "name": f"{face}-retaps-a{attempt}", "expired": expired})
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
    assert "[retaps] the run before, ios: run 9 ios-retaps-a1, 1 retap(s)" in buf.getvalue()
    w.fail.add("repos/o/r/actions/runs/9/artifacts?per_page=100")
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert R.main(args, api=w.api, download=w.download) == 0
    assert "the run before, ios: unknown" in buf.getvalue() and "'twice in a row' is not counted" in buf.getvalue()


# ---- the probes: the same count, the same rules --------------------------------------------------------------------

# Lines as a run printed them (the first-touch mutation's xcodebuild.log, SwiftJsonUI ProbeRetap).
PROBE_LOG = """Test Case '-[ConformanceHostUITests.StateNamesProbeUITests testIdlessControlsKeepAStateEach]' started.
PROBE_RETAP StateNames dynamic first Switch: no effect 3.0s after one touch (touch not delivered) — touched once more
PROBE_RETAP AnchorTap cg_at_btn_f tap: no effect 3.0s after one touch (touch not delivered) — touched once more
PROBE_RETAP A11yActivation run 1 dynLblPlain: no effect after one touch (touch not delivered) — touched once more
PROBE_RETAP CoveredTap the driver's tap on covered_target: no effect after one touch (touch not delivered) — touched once more
PROBE_RETAP PickArity dynamic open: the second touch showed nothing either
PROBE_RETAP TapArity codegen Button: no effect, and this test already retapped codegen Switch flip — not tapped again
GATE_PROBE retap swUiePlain: its value stayed 0 1.0s after one tap — tapped once more
CANTAP_PROBE retap sw_plain: did not switch on the first tap (touch not delivered) — tapped once more
Test Case '-[ConformanceHostUITests.StateNamesProbeUITests testIdlessControlsKeepAStateEach]' passed (1.2 seconds).
Test Case '-[ConformanceHostUITests.ConformanceUITests testFixtures]' started.
Test Case '-[ConformanceHostUITests.ConformanceUITests testFixtures]' passed (1.2 seconds).
Test Case '-[ConformanceHostUITests.OnClickProbeUITests testA]' started.
Test Case '-[ConformanceHostUITests.OnClickProbeUITests testA]' skipped (0.0 seconds).
some line that mentions a retap in passing
PROBE_RETAP a wording nobody wrote yet
"""


def test_every_kind_of_line_is_read():
    rows, cases, probes = R.probe_rows(PROBE_LOG)
    assert (cases, probes) == (3, 1)   # the skipped probe did not run
    assert [(r["probe"], r["what"], r["kind"]) for r in rows] == [
        ("StateNames", "dynamic first Switch", "retap"),
        ("AnchorTap", "cg_at_btn_f tap", "retap"),
        ("A11yActivation", "run 1 dynLblPlain", "retap"),
        ("CoveredTap", "the driver's tap on covered_target", "retap"),
        ("PickArity", "dynamic open", "nothing"),
        ("TapArity", "codegen Button", "refused"),
        ("InteractionGate", "swUiePlain", "retap"),
        ("CanTapGate", "sw_plain", "retap"),
        ("unparsed", "PROBE_RETAP a wording nobody wrote yet", "retap"),   # counted and named, not dropped
    ]


def _shard(tmp_path, name, log, attempt="1"):
    shard = tmp_path / name
    shard.mkdir()
    (tmp_path / f"{name}.log").write_text(log)
    with redirect_stdout(io.StringIO()):
        assert R.main(["scan", str(tmp_path / f"{name}.log"), str(shard / R.SCAN_FILE), "--attempt", attempt]) == 0
    return shard


def _write(tmp_path, *shards, face="ios", attempt="1", fixtures=()):
    src, out = tmp_path / f"{face}.results.json", tmp_path / f"{face}-retaps-{attempt}.json"
    src.write_text(json.dumps({"results": [dict(id=i, retap={"tap": "t", "at": 1.0, "screenshot": "s", "reason": "r"}) for i in fixtures]}))
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert R.main(["write", str(src), str(out), "--run-id", "9", "--attempt", attempt, "--sha", "x", "--face", face,
                       "--shard-dirs", *map(str, shards)]) == 0
    return out, buf.getvalue()


def _judge(records, world=None):
    w = world or World()
    w.runs.setdefault("9", "2026-11-05T02:00:00Z")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = R.main(["judge", *map(str, records), "--repo", REPO, "--run-id", "9", "--attempt", "1", "--workflow", "m.yml"],
                    api=w.api, download=w.download)
    return rc, buf.getvalue()


def _log(*whats):
    return ("Test Case '-[ConformanceHostUITests.XProbeUITests testY]' started.\n"
            "Test Case '-[ConformanceHostUITests.XProbeUITests testY]' passed (1.0 seconds).\n") + "".join(
        f"PROBE_RETAP {w}: no effect 3.0s after one touch (touch not delivered) — touched once more\n" for w in whats)


def test_no_retap_is_green_and_says_the_probes_ran(tmp_path):
    out, said = _write(tmp_path, _shard(tmp_path, "s1", _log()))
    assert "0 probe touch(es) not delivered in 1 probe test case(s)" in said
    rc, said = _judge([out])
    assert rc == 0 and "1 probe test case(s)" in said


def test_at_the_cap_is_green_over_it_is_red_and_every_one_is_named(tmp_path):
    at, said = _write(tmp_path, _shard(tmp_path, "s1", _log("A one")), _shard(tmp_path, "s2", _log("B two")))
    assert "PROBE_RETAP ios A one: no effect" in said and "PROBE_RETAP ios B two: no effect" in said
    assert _judge([at])[0] == 0
    over, _ = _write(tmp_path, _shard(tmp_path, "s3", _log("A one", "B two", "C three")), attempt="2")
    rc, said = _judge([over])
    assert rc == 1 and "::error::3 retaps in run 9 attempt 1 (more than 2): A one, B two, C three" in said


def test_a_fixtures_and_a_probes_add_up_over_both_faces(tmp_path):
    ios, _ = _write(tmp_path, _shard(tmp_path, "s1", _log("A one")), fixtures=["common/f"])
    cg, _ = _write(tmp_path, _shard(tmp_path, "s2", _log()), face="ios-codegen")
    assert _judge([ios, cg])[0] == 0
    (tmp_path / "s3").mkdir(); (tmp_path / "s3" / R.SCAN_FILE).write_text(json.dumps({"attempt": "1", "test_cases": 1, "probe_cases": 1, "rows": [_row("B", "two")]}))
    cg, _ = _write(tmp_path, tmp_path / "s3", face="ios-codegen")
    rc, said = _judge([ios, cg])
    assert rc == 1 and "3 retaps in run 9" in said and "common/f, A one, B two" in said


def test_the_second_touch_showing_nothing_is_not_a_second_retap(tmp_path):
    log = _log("A one", "B two") + "PROBE_RETAP B two: the second touch showed nothing either\n"
    out, _ = _write(tmp_path, _shard(tmp_path, "s1", log))
    assert _judge([out])[0] == 0


def test_a_lost_touch_with_no_retap_left_is_counted(tmp_path):
    log = _log("A one", "B two") + "PROBE_RETAP C three: no effect, and this test already retapped x — not tapped again\n"
    out, _ = _write(tmp_path, _shard(tmp_path, "s1", log))
    assert _judge([out])[0] == 1


def test_a_shard_whose_log_was_not_read_is_red_never_zero(tmp_path):
    empty = _shard(tmp_path, "s1", "")                 # a log with no test case
    missing = tmp_path / "s2"; missing.mkdir()         # no record at all
    (tmp_path / "gone").mkdir()
    with redirect_stdout(io.StringIO()):
        assert R.main(["scan", str(tmp_path / "no.log"), str(tmp_path / "gone" / R.SCAN_FILE), "--attempt", "1"]) == 0
    out, said = _write(tmp_path, empty, missing, tmp_path / "gone")
    assert said.count("not read") == 3
    rc, said = _judge([out])
    assert rc == 1 and "s1: its log held no test case" in said and "s2: no record of its log" in said


def test_a_run_with_the_probes_off_says_the_count_says_nothing(tmp_path, monkeypatch):
    log = ("Test Case '-[ConformanceHostUITests.ConformanceUITests testFixtures]' started.\n"
           "Test Case '-[ConformanceHostUITests.OnClickProbeUITests testA]' started.\n"
           "Test Case '-[ConformanceHostUITests.OnClickProbeUITests testA]' skipped (0.0 seconds).\n")
    out, _ = _write(tmp_path, _shard(tmp_path, "s1", log))
    target = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))
    assert _judge([out])[0] == 0
    assert "no probe ran: the probes' count says nothing" in target.read_text()


def test_the_summary_has_the_count_and_the_names(tmp_path, monkeypatch):
    out, _ = _write(tmp_path, _shard(tmp_path, "s1", _log(*[f"P{i} row" for i in range(40)])))
    target = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))
    rc, said = _judge([out])
    text = target.read_text()
    assert rc == 1 and "**40** in this run, at most 2: 0 fixture(s), 40 probe touch(es)" in text
    assert "- probe P0 row" in text and "- and 10 more" in text and "🔴 40 retaps" in text
    assert "and 10 more (all in this step's log)" in said and said.count("\nPROBE_RETAP P") == 40


def test_the_same_probe_twice_in_a_row_is_red_whatever_its_row(tmp_path):
    w = World()
    w.run("8", "2026-11-04T02:00:00Z", (1, _probes(8, 1, _row("StateNames", "dynamic c1"))))
    w.run("9", "2026-11-05T02:00:00Z")
    cur = tmp_path / "r.json"
    cur.write_text(json.dumps(_probes(9, 1, _row("StateNames", "codegen a2"))))
    rc, said = _judge([cur], w)
    assert rc == 1 and "probe StateNames retapped twice in a row: run 9 attempt 1 (codegen a2) and run 8 ios-retaps-a1 (dynamic c1)" in said
    cur.write_text(json.dumps(_probes(9, 1, _row("LinkTap", "codegen a2"))))
    assert _judge([cur], w)[0] == 0


def test_the_codegen_faces_run_before_is_read_under_its_own_name(tmp_path):
    w = World()
    w.run("8", "2026-11-04T02:00:00Z", (1, _probes(8, 1, _row("LinkTap", "x"), face="ios-codegen")))
    w.run("9", "2026-11-05T02:00:00Z")
    ios, cg = tmp_path / "a.json", tmp_path / "b.json"
    ios.write_text(json.dumps(_probes(9, 1)))
    cg.write_text(json.dumps(_probes(9, 1, _row("LinkTap", "y"), face="ios-codegen")))
    rc, said = _judge([ios, cg], w)
    assert rc == 1 and "run 8 ios-codegen-retaps-a1" in said


def test_a_rerun_that_did_not_rerun_a_shard_does_not_count_its_touch_twice(tmp_path):
    # attempt 2 re-ran the shard that failed; the merge carries the other shard's rows and fixtures, from attempt 1
    w = World()
    first = _probes(9, 1, _row("LinkTap", "x", attempt="1"))
    first["retaps"] = [_retap("common/f", at=1.25)]
    w.run("9", "2026-11-05T02:00:00Z", (1, first))
    second = _probes(9, 2, _row("LinkTap", "x", attempt="1"))
    second["retaps"] = [_retap("common/f", at=1.25)]
    cur = tmp_path / "r.json"
    cur.write_text(json.dumps(second))
    assert _judge([cur], w)[0] == 0
    second["probe_retaps"] = [_row("LinkTap", "x", attempt="2")]   # the same row, lost again on the re-run: a second touch
    cur.write_text(json.dumps(second))
    assert _judge([cur], w)[0] == 1
    second["probe_retaps"] = []
    second["retaps"] = [_retap("common/f", at=2.5)]
    cur.write_text(json.dumps(second))
    assert _judge([cur], w)[0] == 1


def test_a_rerun_whose_merge_passed_judges_the_record_it_left(tmp_path):
    # re-running failed jobs does not re-run a merge that passed: there is no a2, and that is not a broken run
    w = World()
    w.run("8", "2026-11-04T02:00:00Z", (1, _probes(8, 1)))
    w.run("9", "2026-11-05T02:00:00Z", (1, _probes(9, 1)))
    cur = tmp_path / "r.json"
    cur.write_text(json.dumps(_probes(9, 1)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = R.main(["judge", str(cur), "--repo", REPO, "--run-id", "9", "--attempt", "2", "--workflow", "m.yml"],
                    api=w.api, download=w.download)
    assert rc == 0 and "the run before, ios: run 8 ios-retaps-a1" in buf.getvalue()


def test_each_face_is_judged_on_its_latest_record(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(_probes(9, 1, _row("A", "1"), _row("B", "2"), _row("C", "3"))))
    b.write_text(json.dumps(_probes(9, 2)))
    assert _judge([a, b])[0] == 0
    assert _judge([b, a])[0] == 0


def test_a_record_that_cannot_be_read_is_red(tmp_path):
    rc, said = _judge([tmp_path / "retaps" / "*" / "retaps.json"])
    assert rc == 1 and "could not be read" in said


def test_a_face_with_no_record_is_said(tmp_path):
    cur = tmp_path / "r.json"
    cur.write_text(json.dumps(_probes(9, 1)))
    rc, said = _judge([cur])
    assert rc == 0 and "ios-codegen: no record in this run" in said


def test_the_workflow_carries_both_faces_to_the_judge():
    text = (REPO_ROOT / ".github" / "workflows" / "conformance-mobile.yml").read_text()
    for log in ("/tmp/jsonui-conformance-ios.ci/xcodebuild.log", "/tmp/jsonui-conformance-ios-codegen.ci/xcodebuild.log"):
        assert f'ios_retaps.py scan {log} "$out/probe_retaps.json" --attempt "$GITHUB_RUN_ATTEMPT"' in text
    assert "--face ios --shard-dirs shards/ios-shard-*" in text
    assert "--face ios-codegen --shard-dirs shards/ios-codegen-shard-*" in text
    assert "name: ios-retaps-a${{ github.run_attempt }}\n          if-no-files-found: error" in text   # the uploads
    assert "name: ios-codegen-retaps-a${{ github.run_attempt }}\n          if-no-files-found: error" in text
    # The download is by pattern: re-running failed jobs leaves no record under this attempt's name.
    assert "pattern: ios*-retaps-a*" in text and "ios_retaps.py judge retaps/*/retaps.json" in text
    assert "name: ios-retaps-a${{ github.run_attempt }}\n          path: retaps" not in text
