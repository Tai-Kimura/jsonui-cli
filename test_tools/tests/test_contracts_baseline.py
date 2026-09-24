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
        rc, out = run(root, "contracts", "baseline")
        assert rc == 0 and "removed 0 · kept 12 · new 0 not added" in out, out
        rc, out = _validate(run, root)
        assert rc == 0, out
        assert "Coverage: passed (exit 1)" in _summary(out)
        web = next(l for l in _section(out) if l.startswith("coverage: web"))
        assert web.endswith("baselined 6 (matched 6 · new 0 · stale 0)"), web

    def test_one_new_uncovered_is_red_and_named(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline")
        root2 = tcc._project(tmp_path / "second", openapi=_with_new_status())
        _with_test(root2)
        _baseline_file(root2).write_bytes(_baseline_file(root).read_bytes())
        rc, out = _validate(run, root2)
        assert rc == 1, out
        assert "web: 1 not in the baseline" in _summary(out)

    def test_a_closed_entry_left_in_the_baseline_is_red_and_says_how(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline")
        spec_file = root / "docs/screens/json/detail.spec.json"
        spec_file.write_text(json.dumps(_closing_one()), encoding="utf-8")
        rc, out = _validate(run, root)
        assert rc == 1, out
        assert "web: 1 baselined but closed" in _summary(out)
        assert "run `jsonui-test contracts baseline` to drop them" in "\n".join(_section(out))

    def test_the_command_never_adds_a_new_entry(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline")
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
        rc, out = run(root, "contracts", "baseline")
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
        run(root, "contracts", "baseline")
        (root / "docs/screens/json/detail.spec.json").write_text(
            json.dumps(_closing_one()), encoding="utf-8")
        rc, out = run(root, "contracts", "baseline")
        assert out.startswith("updated ") and "removed 2 · kept 10 · new 0 not added" in out, out
        rc, out = _validate(run, root)
        assert rc == 0, out

    def test_unmeasured_entries_carry_their_cause(self, tmp_path, run):
        spec, openapi, mocks = tcc._clean([{"method": "GET", "path": "/api/tags"}])
        root = _with_test(tcc._project(tmp_path, spec, openapi=openapi, mocks=mocks))
        run(root, "contracts", "baseline")
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
        run(root, "contracts", "baseline")
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
        run(run_clean, "contracts", "baseline")
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
        assert web["baseline"] == {"baselined": 0, "matched": 0, "new": 6, "stale": 0}

    def test_a_run_on_one_platform_does_not_call_the_others_stale(self, tmp_path, run):
        root = _project(tmp_path)
        run(root, "contracts", "baseline")
        report = cc.run_coverage(root, platforms=["web"])
        assert report.baseline == {"web": {"baselined": 6, "matched": 6, "new": 0, "stale": 0}}

    def test_a_run_on_one_screen_does_not_call_the_others_stale(self, tmp_path, run):
        other = tcc._screen()
        other["metadata"]["name"] = "other"
        root = _with_test(tcc._project(tmp_path, extra_screens=[("other", other)]))
        run(root, "contracts", "baseline")
        assert cc.run_coverage(root).baseline["web"]["baselined"] == 12
        report = cc.run_coverage(root, screen="detail")
        assert report.baseline["web"] == {"baselined": 6, "matched": 6, "new": 0, "stale": 0}

    def test_an_unreadable_baseline_cannot_start(self, tmp_path):
        root = _project(tmp_path)
        _baseline_file(root).write_text("[]", encoding="utf-8")
        with pytest.raises(cc.CannotStart, match="baseline cannot be read"):
            cc.run_coverage(root)
