"""The coverage baseline (ratchet), design §6.1 P3c — red-check xxxv.

`jsonui-test contracts baseline` records the entries that make coverage exit
non-zero in `<spec_directory>/contracts_coverage_baseline.json`, and after that
only SHRINKS the file. Once validate gates, it fails on entries not in the
baseline (new), on baselined entries that are closed (stale), and on what can
never be baselined (declaration errors, not-evaluated rows, cannot-start).

xxxv, on the coverage suite's own project with the gate switched on:
  no baseline  × a new uncovered       -> red (every entry is new)
  baseline     × everything recorded   -> passes, though coverage exits 1
  baseline     × one new uncovered     -> red, naming it
  baseline     × a closed entry kept   -> red (stale), naming the command
and the negative: `contracts baseline` does not add the new entry. It also
writes nothing while the run holds what cannot be baselined — a floor would be
recorded, or unmeasured entries dropped as closed.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from jsonui_test_cli import contracts_baseline as cb
from jsonui_test_cli import contracts_coverage as cc
from jsonui_test_cli.cli import main
from tests import test_contracts_coverage as tcc
from tests.test_validate_coverage_section import BELOW, _section, _summary, _with_test


@pytest.fixture
def run(monkeypatch, capsys):
    def go(root: Path, *argv, gate=BELOW) -> tuple[int, str]:
        monkeypatch.chdir(root)
        monkeypatch.setattr(cc, "VALIDATE_GATE_FROM", gate)
        monkeypatch.setattr(sys, "argv", ["jsonui-test", *argv])
        rc = main()
        captured = capsys.readouterr()
        go.err = captured.err
        return rc, captured.out
    return go


def _validate(run, root, gate=BELOW):
    # --no-mock-check: validate's first run regenerates mocks from the OpenAPI
    # document, which would change what coverage measures between the
    # `contracts baseline` run and this one — the arm would then read the
    # fixture's regeneration, not the baseline.
    return run(root, "validate", "tests", "--no-install", "--no-mock-check", gate=gate)


def _baseline_file(root: Path) -> Path:
    return root / "docs/screens/json" / cb.BASELINE_FILE


def _project(tmp_path, spec=None, openapi=None):
    return _with_test(tcc._project(tmp_path, spec, openapi=openapi))


def _with_new_status(openapi=None) -> dict:
    """The same API with one more status declared on getOther — a new uncovered."""
    api = copy.deepcopy(openapi or tcc._OPENAPI)
    api["paths"]["/api/other"]["get"]["responses"]["404"] = {}
    return api


def _closing_one(spec=None) -> dict:
    """The same screen with a row that answers setApproval 401 — one entry closed."""
    spec = copy.deepcopy(spec or tcc._screen())
    spec["branchContracts"]["methods"]["approve"]["branches"].append(
        {"when": {"api.setApproval": "error_401"}, "then": {"data.banner": "login"}})
    return spec


class TestXxxv:
    def test_no_baseline_and_a_new_uncovered_is_red(self, tmp_path, run):
        root = _project(tmp_path)
        rc, out = _validate(run, root)
        assert rc == 1, out
        assert "no baseline file: every entry is new" in "\n".join(_section(out))

    def test_everything_recorded_passes_though_coverage_exits_1(self, tmp_path, run):
        root = _project(tmp_path)
        rc, out = run(root, "contracts", "baseline", "--initial")
        assert rc == 0 and "removed 0 · kept 12 · new 0 not added" in out, out
        rc, out = _validate(run, root)
        assert rc == 0, out
        assert "Coverage: passed (exit 1)" in _summary(out)
        web = next(l for l in _section(out) if l.startswith("coverage: web"))
        assert web.endswith("baselined 6 (matched 6 · new 0 · stale 0)"), web

    def test_one_new_uncovered_is_red_and_named(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        root2 = tcc._project(tmp_path / "second", openapi=_with_new_status())
        _with_test(root2)
        _baseline_file(root2).write_bytes(_baseline_file(root).read_bytes())
        rc, out = _validate(run, root2)
        assert rc == 1, out
        assert "web: 1 not in the baseline" in _summary(out)

    def test_a_closed_entry_left_in_the_baseline_is_red_and_says_how(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        spec_file = root / "docs/screens/json/detail.spec.json"
        spec_file.write_text(json.dumps(_closing_one()), encoding="utf-8")
        rc, out = _validate(run, root)
        assert rc == 1, out
        assert "web: 1 baselined but closed" in _summary(out)
        assert "run `jsonui-test contracts baseline` to drop them" in "\n".join(_section(out))

    def test_the_command_never_adds_a_new_entry(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        before = cb.load(_baseline_file(root))
        # A new uncovered status appears; the command must not record it.
        (root / "docs/api/api.json").write_text(json.dumps(_with_new_status()), encoding="utf-8")
        rc, out = run(root, "contracts", "baseline")
        assert rc == 0 and "new 2 not added (close them, or add by hand)" in out, out
        assert out.startswith("unchanged "), out
        assert cb.load(_baseline_file(root)) == before


class TestTheFile:
    def test_first_write_then_the_same_bytes_again(self, tmp_path, run):
        root = _project(tmp_path)
        rc, out = run(root, "contracts", "baseline", "--initial")
        assert out.startswith("wrote "), out
        first = _baseline_file(root).read_bytes()
        rc, out = run(root, "contracts", "baseline")
        assert out.startswith("unchanged "), out        # not "updated": nothing was
        assert _baseline_file(root).read_bytes() == first
        data = json.loads(first)
        assert list(data) == ["entries"]                      # no timestamps
        assert data["entries"] == sorted(data["entries"], key=cb.entry_key)
        assert {e["kind"] for e in data["entries"]} == {"uncovered"}

    def test_closing_shrinks_it(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        (root / "docs/screens/json/detail.spec.json").write_text(
            json.dumps(_closing_one()), encoding="utf-8")
        rc, out = run(root, "contracts", "baseline")
        assert out.startswith("updated ") and "removed 2 · kept 10 · new 0 not added" in out, out
        rc, out = _validate(run, root)
        assert rc == 0, out

    def test_unmeasured_entries_carry_their_cause(self, tmp_path, run):
        spec, openapi, mocks = tcc._clean([{"method": "GET", "path": "/api/tags"}])
        root = _with_test(tcc._project(tmp_path, spec, openapi=openapi, mocks=mocks))
        run(root, "contracts", "baseline", "--initial")
        entries = cb.load(_baseline_file(root))
        assert {(e["platform"], e["op"], e["cause"]) for e in entries} == {
            ("web", "GET /api/tags", "unbound endpoint"), ("ios", "GET /api/tags", "unbound endpoint")}
        rc, out = _validate(run, root)
        assert rc == 0, out           # exit 3 alone, fully baselined

    def test_nothing_to_record_writes_nothing(self, tmp_path, run):
        spec, openapi, mocks = tcc._clean()
        root = _with_test(tcc._project(tmp_path, spec, openapi=openapi, mocks=mocks))
        rc, out = run(root, "contracts", "baseline")
        assert rc == 0 and out.startswith("nothing to record"), out
        assert not _baseline_file(root).exists()
        rc, out = _validate(run, root)
        assert rc == 0 and "Coverage: passed (exit 0)" in _summary(out), out


def _with_declaration_error(root: Path) -> None:
    spec = tcc._screen()
    spec["branchContracts"]["methods"]["approve"]["excludedOutcomes"]["api.setApproval"] = {
        "409": {"by": "unit", "reason": "r"}}
    (root / "docs/screens/json/detail.spec.json").write_text(json.dumps(spec), encoding="utf-8")


def _with_a_row_not_evaluated(root: Path) -> None:
    # The coverage suite's xiii specimen: a `@response` path the 429 body
    # lacks, so the row's 429 copy is not evaluated — exit-3 side, but not a
    # baselinable cause (it is the row that has to be fixed). 429 was a row
    # before, so the uncovered entries are the same: nothing new, nothing stale.
    mock = root / "tests/mocks/generated/setApproval.mock.json"
    data = json.loads(mock.read_text())
    data["scenarios"]["error_429"] = {"status": 429, "body": {}}
    mock.write_text(json.dumps(data), encoding="utf-8")
    spec = tcc._screen()
    spec["branchContracts"]["methods"]["approve"]["branches"][2]["then"][
        "data.bannerText"] = "@response.message"
    (root / "docs/screens/json/detail.spec.json").write_text(json.dumps(spec), encoding="utf-8")


class TestWhatCannotBeBaselined:
    """Each specimen is baselined while clean, THEN broken: the gate has a
    full baseline to pass with, and still fails."""

    @pytest.mark.parametrize("break_it, why", [
        (_with_declaration_error, "declaration errors 1 (cannot be baselined)"),
        (_with_a_row_not_evaluated, "not evaluated 1 (cannot be baselined)"),
    ])
    def test_it_fails_whatever_the_baseline(self, tmp_path, run, break_it, why):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        break_it(root)
        rc, out = _validate(run, root)
        assert rc == 1 and why in _summary(out), out
        assert "not in the baseline" not in _summary(out)
        assert "baselined but closed" not in _summary(out)

    @pytest.mark.parametrize("break_it, why", [
        (_with_declaration_error, "web: declaration errors 1"),
        (_with_a_row_not_evaluated, "web: not evaluated 1"),
    ])
    def test_the_command_writes_nothing_then(self, tmp_path, run, break_it, why):
        root = _project(tmp_path)
        break_it(root)
        rc, out = run(root, "contracts", "baseline")      # a first write: no floor recorded
        assert rc == 1 and not _baseline_file(root).exists()
        assert out == "" and "nothing written" in run.err and why in run.err, run.err
        run_clean = _project(tmp_path / "clean")
        run(run_clean, "contracts", "baseline", "--initial")
        _baseline_file(root).write_bytes(_baseline_file(run_clean).read_bytes())
        before = _baseline_file(root).read_bytes()
        rc, _ = run(root, "contracts", "baseline")        # a shrink: nothing dropped
        assert rc == 1 and _baseline_file(root).read_bytes() == before

    def test_gate_off_the_section_reports_and_the_rc_is_untouched(self, tmp_path, run):
        root = _project(tmp_path)
        rc, out = _validate(run, root, gate="99.0.0")
        assert rc == 0 and "Coverage:" not in _summary(out)
        assert any("baselined 0 (matched 0 · new 6 · stale 0)" in l for l in _section(out))


class TestCoverageShowsIt:
    def test_text_and_json_always_carry_the_counts(self, tmp_path, run):
        root = _project(tmp_path)
        report = cc.run_coverage(root)
        text = "\n".join(cc.format_text(report))
        assert "[platform=web] baselined 0 (matched 0 · new 6 · stale 0) — no baseline file" in text
        js = cc.to_json(report)
        assert js["baseline"]["present"] is False
        web = next(p for p in js["platforms"] if p["platform"] == "web")
        assert {k: v for k, v in web["baseline"].items() if isinstance(v, int)} == {
            "baselined": 0, "matched": 0, "new": 6, "stale": 0, "hidden": 0, "vanished": 0}
        assert len(web["baseline"]["new_entries"]) == 6 and web["baseline"]["stale_entries"] == []

    def test_a_run_on_one_platform_does_not_call_the_others_stale(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        report = cc.run_coverage(root, platforms=["web"])
        assert report.baseline == {"web": {"baselined": 6, "matched": 6, "new": 0, "stale": 0, "hidden": 0, "vanished": 0}}

    def test_a_run_on_one_screen_does_not_call_the_others_stale(self, tmp_path, run):
        other = tcc._screen()
        other["metadata"]["name"] = "other"
        root = _with_test(tcc._project(tmp_path, extra_screens=[("other", other)]))
        run(root, "contracts", "baseline", "--initial")
        assert cc.run_coverage(root).baseline["web"]["baselined"] == 12
        report = cc.run_coverage(root, screen="detail")
        assert report.baseline["web"] == {"baselined": 6, "matched": 6, "new": 0, "stale": 0, "hidden": 0, "vanished": 0}

    @pytest.mark.parametrize("content", ["[]", "<<<<<<< HEAD\n{}\n=======\n"])
    def test_an_unreadable_baseline_cannot_start_and_names_the_file(self, tmp_path, run,
                                                                   content):
        # A list, and a conflict-marked file: each names the file and whose
        # call the repair is — in coverage and in the command alike (v4.21).
        root = _project(tmp_path)
        _baseline_file(root).write_text(content, encoding="utf-8")
        with pytest.raises(cc.CannotStart, match="baseline cannot be read") as caught:
            cc.run_coverage(root)
        assert str(_baseline_file(root)) in str(caught.value)
        assert "repairing it is the user's decision" in str(caught.value)
        rc, out = run(root, "contracts", "baseline")
        assert rc == 2 and str(_baseline_file(root)) in run.err, run.err
        assert "repairing it is the user's decision" in run.err


def _mock_file(root: Path, op: str) -> Path:
    return root / f"tests/mocks/generated/{op}.mock.json"


def _drop_scenario(root: Path, op: str, scenario: str) -> None:
    mock = _mock_file(root, op)
    data = json.loads(mock.read_text())
    del data["scenarios"][scenario]
    mock.write_text(json.dumps(data), encoding="utf-8")


class TestV421:
    """Design v4.21 (ee, the second review of P3b): two fail-open gaps, what
    define needs to see, and the first recording as the user's decision."""

    def test_1_no_scenario_is_per_status(self, tmp_path, run):
        # getOther declares 404 with no scenario: baselined as (op, 404, no scenario).
        root = _with_test(tcc._project(tmp_path, openapi=_with_new_status()))
        run(root, "contracts", "baseline", "--initial")
        assert {(e["op"], e.get("status"), e["cause"]) for e in cb.load(_baseline_file(root))
                if e["kind"] == "unmeasured"} == {("getOther", "404", "no scenario")}
        # Now 500 loses its scenario too. Keyed per op, it matched the recorded
        # entry and passed: new code outside the rule.
        _drop_scenario(root, "getOther", "error_500")
        rc, out = _validate(run, root)
        assert rc == 1, out
        assert "web: 1 not in the baseline (detail 1)" in _summary(out)
        assert "baselined but closed" not in _summary(out)   # 500's uncovered: hidden

    def test_2_a_shrink_under_no_mock_keeps_what_it_hides(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        before = _baseline_file(root).read_bytes()
        _mock_file(root, "getOther").unlink()              # getOther: no mock
        rc, out = run(root, "contracts", "baseline")
        assert rc == 0 and out.startswith("unchanged "), out
        # getOther is unattributed: its 200 and 500 were both uncovered (web, ios).
        assert "removed 0 · kept 12 (4 unmeasured now — not closed, kept) · new 2 not added" in out
        assert _baseline_file(root).read_bytes() == before
        rc, out = _validate(run, root)
        web = next(l for l in _section(out) if l.startswith("coverage: web"))
        assert "stale 0 · unmeasured now 2)" in web, web
        assert "baselined but closed" not in _summary(out)
        assert "web: 1 not in the baseline (detail 1)" in _summary(out)   # the no mock itself

    def test_3_the_json_lists_agree_with_the_file_both_ways(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        (root / "docs/screens/json/detail.spec.json").write_text(
            json.dumps(_closing_one()), encoding="utf-8")                   # 2 closed
        (root / "docs/api/api.json").write_text(json.dumps(_with_new_status()),
                                                encoding="utf-8")           # 2 new
        report = cc.run_coverage(root)
        js = cc.to_json(report)
        key = cb.entry_key
        recorded = {key(e) for e in cb.load(_baseline_file(root))}
        current = {key(e) for e in report.entries}
        for block in js["platforms"]:
            b = block["baseline"]
            p = block["platform"]
            new = {key(e) for e in b["new_entries"]}
            gone = {key(e) for e in b["stale_entries"] + b["hidden_entries"]}
            assert new == {k for k in current - recorded if k[1] == p}
            assert gone == {k for k in recorded - current if k[1] == p}
            assert (b["new"], b["stale"] + b["hidden"]) == (len(new), len(gone))
            assert b["baselined"] == b["matched"] + b["stale"] + b["hidden"]
        screen = next(s for s in js["platforms"][0]["screens"] if s["spec"] == "detail")
        assert {"op": "getOther", "status": "404", "cause": "no scenario"} in screen["unmeasured"]

    def test_4_the_why_names_the_screens(self, tmp_path, run):
        other = tcc._screen()
        other["metadata"]["name"] = "other"
        root = _with_test(tcc._project(tmp_path, extra_screens=[("other", other)]))
        rc, out = _validate(run, root)
        assert "web: 12 not in the baseline (detail 6, other 6)" in _summary(out), _summary(out)

    def test_5_the_first_recording_needs_initial(self, tmp_path, run):
        root = _project(tmp_path)
        rc, out = run(root, "contracts", "baseline")
        assert rc == 1 and out == "" and not _baseline_file(root).exists()
        assert "recording the first baseline accepts all current debt (12 entries) — the " \
               "user's decision; run with --initial" in run.err
        rc, out = run(root, "contracts", "baseline", "--initial")
        assert rc == 0 and out.startswith("wrote ") and _baseline_file(root).exists()


def _spec_file(root: Path) -> Path:
    return root / "docs/screens/json/detail.spec.json"


def _edit_spec(root: Path, change) -> None:
    spec = json.loads(_spec_file(root).read_text())
    change(spec)
    _spec_file(root).write_text(json.dumps(spec), encoding="utf-8")


def _edit_openapi(root: Path, change) -> None:
    api_file = root / "docs/api/api.json"
    api = json.loads(api_file.read_text())
    change(api)
    api_file.write_text(json.dumps(api), encoding="utf-8")


def _with_other_screen(tmp_path):
    other = tcc._screen()
    other["metadata"]["name"] = "other"
    return _with_test(tcc._project(tmp_path, extra_screens=[("other", other)]))


class TestVanished:
    """Design v4.22 (ee; hole #41 generalised). A baselined entry the run does
    not hold is CLOSED only when the run measured its unit and a decision
    answers it; otherwise it VANISHED — the screen left the platform, the
    spec is gone, the method or the op is no longer declared, the status left
    the OpenAPI. Vanished fails the gate and survives the shrink: removing or
    re-keying it is the user's decision, by hand. One specimen per cause; the
    method and the op each, because an uncovered key carries a method and an
    unmeasured key does not."""

    def _recorded(self, root, run):
        rc, _ = run(root, "contracts", "baseline", "--initial")
        assert rc == 0
        return _baseline_file(root).read_bytes()

    def _red_and_kept(self, root, run, before, why, count=None):
        rc, out = _validate(run, root)
        assert rc == 1, out
        assert why in _summary(out), _summary(out)
        assert "baselined but closed" not in _summary(out), _summary(out)
        rc, out = run(root, "contracts", "baseline")
        assert rc == 0 and "vanished — not closed, kept; remove or re-key them by hand" in out, out
        kept = {cb.entry_key(e) for e in cb.load(_baseline_file(root))}
        assert {cb.entry_key(e) for e in json.loads(before)["entries"]} <= kept
        return out

    def test_the_screen_left_the_platform(self, tmp_path, run):
        root = _project(tmp_path)
        before = self._recorded(root, run)
        _edit_spec(root, lambda s: s["metadata"].__setitem__("platforms", ["ios"]))
        self._red_and_kept(root, run, before, "web: 6 baselined but gone from the run (detail 6)")

    def test_the_spec_file_is_gone(self, tmp_path, run):
        root = _with_other_screen(tmp_path)
        before = self._recorded(root, run)
        _spec_file(root).unlink()
        self._red_and_kept(root, run, before, "web: 6 baselined but gone from the run (detail 6)")

    def test_the_method_is_no_longer_declared(self, tmp_path, run):
        # approve's rows go: its setApproval statuses are unattributed now
        # (new) and the approve-keyed ones vanished — both red, side by side.
        root = _project(tmp_path)
        before = self._recorded(root, run)
        _edit_spec(root, lambda s: s["branchContracts"]["methods"].clear())
        approve_keyed = sum(1 for e in json.loads(before)["entries"]
                            if e["platform"] == "web" and e.get("method") == "approve")
        assert approve_keyed > 0
        rc, out = _validate(run, root)
        summary = _summary(out)
        assert "web: " in summary and " not in the baseline (detail " in summary, summary  # re-keyed
        assert f"web: {approve_keyed} baselined but gone from the run (detail {approve_keyed})" \
            in summary, summary                                                           # old keys
        self._red_and_kept(root, run, before, "baselined but gone from the run (detail")

    def test_the_op_is_no_longer_declared(self, tmp_path, run):
        root = _project(tmp_path)
        before = self._recorded(root, run)
        _edit_spec(root, lambda s: s["dataFlow"]["repositories"][0]["methods"].__delitem__(2))
        self._red_and_kept(root, run, before, "web: 2 baselined but gone from the run (detail 2)")

    def test_the_status_left_the_openapi(self, tmp_path, run):
        root = _project(tmp_path)
        before = self._recorded(root, run)
        _edit_openapi(root, lambda a: a["paths"]["/api/other"]["get"]["responses"].pop("500"))
        self._red_and_kept(root, run, before, "web: 1 baselined but gone from the run (detail 1)")

    def test_an_unmeasured_key_vanishes_too(self, tmp_path, run):
        # getOther 404 has no scenario (an unmeasured key: no method); the
        # status leaves the OpenAPI.
        root = _with_test(tcc._project(tmp_path, openapi=_with_new_status()))
        before = self._recorded(root, run)
        _edit_openapi(root, lambda a: a["paths"]["/api/other"]["get"]["responses"].pop("404"))
        self._red_and_kept(root, run, before, "web: 1 baselined but gone from the run (detail 1)")

    def test_boundary_the_same_key_closed_by_a_row_is_stale_and_dropped(self, tmp_path, run):
        root = _project(tmp_path)
        self._recorded(root, run)
        _spec_file(root).write_text(json.dumps(_closing_one()), encoding="utf-8")
        report = cc.run_coverage(root)
        assert (report.baseline["web"]["stale"], report.baseline["web"]["vanished"]) == (1, 0)
        rc, out = run(root, "contracts", "baseline")
        assert "removed 2 · kept 10 · new 0 not added" in out and "vanished" not in out, out

    def test_boundary_an_unmeasured_key_closed_by_its_scenario_is_stale(self, tmp_path, run):
        # The no-scenario 404 gets its scenario: the status is measured now,
        # so the unmeasured key is CLOSED (its 404 is a plain uncovered now).
        root = _with_test(tcc._project(tmp_path, openapi=_with_new_status()))
        self._recorded(root, run)
        mock = _mock_file(root, "getOther")
        data = json.loads(mock.read_text())
        data["scenarios"]["error_404"] = {"status": 404, "body": {}}
        mock.write_text(json.dumps(data), encoding="utf-8")
        report = cc.run_coverage(root)
        stale = report.baseline_items["web"]["stale"]
        assert [(e["op"], e.get("status"), e["cause"]) for e in stale] == [
            ("getOther", "404", "no scenario")]
        assert report.baseline["web"]["vanished"] == 0

    def test_json_and_text_carry_vanished(self, tmp_path, run):
        root = _project(tmp_path)
        self._recorded(root, run)
        _edit_openapi(root, lambda a: a["paths"]["/api/other"]["get"]["responses"].pop("500"))
        report = cc.run_coverage(root)
        web = next(p for p in cc.to_json(report)["platforms"] if p["platform"] == "web")
        b = web["baseline"]
        assert b["vanished"] == 1 and [e["status"] for e in b["vanished_entries"]] == ["500"]
        assert b["baselined"] == b["matched"] + b["stale"] + b["hidden"] + b["vanished"]
        text = "\n".join(cc.format_text(report))
        assert "stale 0 · vanished 1)" in text and "remove or re-key them by hand" in text

    # ---- every way a decision closes a key is CLOSED, not vanished

    def test_closed_by_an_excluded_outcome(self, tmp_path, run):
        root = _project(tmp_path)
        self._recorded(root, run)
        _edit_spec(root, lambda s: s["branchContracts"]["methods"]["approve"]["excludedOutcomes"]
                   .__setitem__("api.setApproval", {"401": {"by": "unit", "reason": "r"}}))
        report = cc.run_coverage(root)
        assert [(e["op"], e["status"]) for e in report.baseline_items["web"]["stale"]] == [
            ("setApproval", "401")]
        assert report.baseline["web"]["vanished"] == 0

    def test_closed_by_unreached_ops(self, tmp_path, run):
        root = _project(tmp_path)
        self._recorded(root, run)
        _edit_spec(root, lambda s: s["branchContracts"].__setitem__(
            "unreachedOps", {"api.getOther": {"reason": "the parent calls it"}}))
        report = cc.run_coverage(root)
        assert sorted(e["status"] for e in report.baseline_items["web"]["stale"]) == ["200", "500"]
        assert report.baseline["web"]["vanished"] == 0

    def test_closed_when_the_mock_comes_back(self, tmp_path, run):
        # Recorded under no mock (an unmeasured op key); the mock returns, the
        # op is measured again: that key is CLOSED (its statuses count as
        # themselves now), not vanished.
        root = _project(tmp_path)
        saved = _mock_file(root, "getOther").read_bytes()
        _mock_file(root, "getOther").unlink()
        self._recorded(root, run)
        _mock_file(root, "getOther").write_bytes(saved)
        report = cc.run_coverage(root)
        assert [(e["op"], e["cause"]) for e in report.baseline_items["web"]["stale"]] == [
            ("getOther", "no mock")]
        assert report.baseline["web"]["vanished"] == 0


def _row_on_401(then: dict, when: str = "error_401"):
    def change(spec):
        spec["branchContracts"]["methods"]["approve"]["branches"].append(
            {"when": {"api.setApproval": when}, "then": then})
    return change


class TestUnderWhatCannotBeEvaluated:
    """ee review 4 (a), 4f 11:24. A baselined entry under a screen or a row
    the run holds but cannot evaluate is HIDDEN, not vanished: fixing the
    spec or the row brings it back as it was, so "remove or re-key it by
    hand" would have the user delete debt that is still there. What cannot
    be evaluated fails the gate on its own (cannot be baselined), and the
    command writes nothing while it does. Boundary: the same spec gone from
    disk is vanished (TestVanished.test_the_spec_file_is_gone)."""

    def _hidden_not_vanished(self, root, run, before, why, hidden):
        rc, out = _validate(run, root)
        summary = _summary(out)
        assert rc == 1, out
        assert why in summary, summary
        assert "gone from the run" not in summary and "baselined but closed" not in summary, summary
        report = cc.run_coverage(root)
        assert (report.baseline["web"]["hidden"], report.baseline["web"]["vanished"]) == (hidden, 0)
        rc, out = run(root, "contracts", "baseline")
        assert "vanished" not in out, out
        assert _baseline_file(root).read_bytes() == before

    def _recorded(self, root, run):
        rc, _ = run(root, "contracts", "baseline", "--initial")
        assert rc == 0
        return _baseline_file(root).read_bytes()

    def test_an_unreadable_spec(self, tmp_path, run):
        root = _with_other_screen(tmp_path)
        before = self._recorded(root, run)
        _spec_file(root).write_text("{ not json", encoding="utf-8")
        self._hidden_not_vanished(root, run, before,
                                  "web: screens not evaluated 1 (cannot be baselined)", 6)

    def test_a_row_reading_a_response_path_the_body_lacks(self, tmp_path, run):
        root = _project(tmp_path)
        before = self._recorded(root, run)
        _edit_spec(root, _row_on_401({"data.banner": "@response.nosuch"}))
        self._hidden_not_vanished(root, run, before, "web: not evaluated 3 (cannot be baselined)", 3)

    def test_a_row_that_does_not_bind(self, tmp_path, run):
        # It names a scenario the mock does not have: every op it reaches is
        # not evaluated for its method.
        root = _project(tmp_path)
        before = self._recorded(root, run)
        _edit_spec(root, _row_on_401({"data.banner": "x"}, when="no_such_scenario"))
        self._hidden_not_vanished(root, run, before, "web: not evaluated 3 (cannot be baselined)", 3)

    def test_boundary_the_row_fixed_the_same_entries_are_matched(self, tmp_path, run):
        # The row that answers 401 again: 401 closes (stale); the rest are as
        # they were — nothing was lost while it was hidden.
        root = _project(tmp_path)
        before = self._recorded(root, run)
        _edit_spec(root, _row_on_401({"data.banner": "login"}))
        report = cc.run_coverage(root)
        assert {k: report.baseline["web"][k] for k in ("stale", "hidden", "vanished", "new")} \
            == {"stale": 1, "hidden": 0, "vanished": 0, "new": 0}


def _declare_platforms(root: Path, platforms) -> None:
    config_file = root / "jui.config.json"
    config = json.loads(config_file.read_text())
    config["platforms"] = platforms
    config_file.write_text(json.dumps(config), encoding="utf-8")


class TestAPlatformDroppedFromTheConfig:
    """ee review 4 (b), 4f 11:24. The debt of a platform the config no longer
    declares is VANISHED — red, and kept in the file: dropping a platform is
    not a way out of it (the module docstring). Naming platforms with
    `--platform` is a narrower run, not a drop: the others are not compared."""

    def test_its_entries_vanish_and_the_gate_is_red(self, tmp_path, run):
        root = _project(tmp_path)
        rc, _ = run(root, "contracts", "baseline", "--initial")
        assert rc == 0
        before = _baseline_file(root).read_bytes()
        _declare_platforms(root, ["ios"])
        rc, out = _validate(run, root)
        assert rc == 1, out
        assert "web: 6 baselined but gone from the run (detail 6)" in _summary(out), _summary(out)
        report = cc.run_coverage(root)
        assert report.baseline["web"]["vanished"] == 6
        # The coverage command says so too, in text and in JSON.
        assert ("[platform=web] not declared in jui.config.json platforms · baselined 6 "
                "(matched 0 · new 0 · stale 0 · vanished 6)") in "\n".join(cc.format_text(report))
        undeclared = cc.to_json(report)["baseline"]["undeclared_platforms"]
        assert list(undeclared) == ["web"] and undeclared["web"]["vanished"] == 6
        assert len(undeclared["web"]["vanished_entries"]) == 6
        rc, out = run(root, "contracts", "baseline")
        assert rc == 0 and "vanished — not closed, kept; remove or re-key them by hand" in out, out
        assert {cb.entry_key(e) for e in json.loads(before)["entries"]} \
            <= {cb.entry_key(e) for e in cb.load(_baseline_file(root))}

    def test_boundary_a_narrower_run_compares_only_what_it_names(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        report = cc.run_coverage(root, platforms=["ios"])
        assert "web" not in report.baseline
        assert report.baseline["ios"]["vanished"] == 0

    def test_control_both_still_declared_nothing_vanishes(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline", "--initial")
        report = cc.run_coverage(root)
        assert {p: report.baseline[p]["vanished"] for p in ("web", "ios")} == {"web": 0, "ios": 0}


class TestTheGateLineNamesEveryCause:
    """ee, 2026-09-25: from the release the gate line is what validate prints
    about the gate, and it had not named vanished. Every cause the gate fails
    on is produced here by a real run, and the line must name each — so a
    cause added to the gate and not to the line turns this red."""

    NAMES = {  # the why's phrase -> how the gate line names it
        "not in the baseline": "entries not in the baseline",
        "baselined but closed": "baselined entries that are closed",
        "baselined but gone from the run": "baselined entries gone from the run",
        "cannot be baselined": "what cannot be baselined",
    }

    def _whys(self, root) -> list:
        lines, gate = cc.validate_section(root, "9.9.9")
        return gate["why"]

    def test_each_cause_the_gate_fails_on_is_named_on_the_line(self, tmp_path, run, monkeypatch):
        monkeypatch.setattr(cc, "VALIDATE_GATE_FROM", BELOW)      # the gate is on at 9.9.9
        produced = set()
        root = _project(tmp_path / "new")                                  # new
        produced |= {p for w in self._whys(root) for p in self.NAMES if p in w}
        root = _project(tmp_path / "stale")                                # stale
        run(root, "contracts", "baseline", "--initial")
        _spec_file(root).write_text(json.dumps(_closing_one()), encoding="utf-8")
        produced |= {p for w in self._whys(root) for p in self.NAMES if p in w}
        root = _project(tmp_path / "vanished")                             # vanished
        run(root, "contracts", "baseline", "--initial")
        _edit_openapi(root, lambda a: a["paths"]["/api/other"]["get"]["responses"].pop("500"))
        produced |= {p for w in self._whys(root) for p in self.NAMES if p in w}
        root = _project(tmp_path / "unbaselinable")                        # cannot be baselined
        _with_declaration_error(root)
        produced |= {p for w in self._whys(root) for p in self.NAMES if p in w}
        assert produced == set(self.NAMES), produced
        line = cc._gate_line("9.9.9")
        for phrase in sorted(produced):
            assert self.NAMES[phrase] in line, (phrase, line)
