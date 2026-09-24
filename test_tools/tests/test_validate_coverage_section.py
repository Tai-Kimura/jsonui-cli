"""`jsonui-test validate` reports contracts coverage — and, this release, only reports it.

Design §2.6 / §6.1, P3a-1 (the user's ruling U5 = plan C: announce once, then
gate). validate gains a coverage section: one denominator line per platform,
the declaration errors, and a one-line notice naming the release from which
validate FAILS unless coverage exits 0. The return code does not read it in
this release.

The red-checks here run the real entrypoint on synthetic projects (the
coverage suite's own fixtures):
  xxxi   a project with uncovered statuses and one with none: the section and
         the notice on both, the notice naming the next release, and the rc
         exactly what the same run gives without the section
  xxiv   (half of it — the rc half is P3a-2's) the declaration error coverage
         reports appears in validate's section
  xxvi   an exit-3-only project names `n/a(unbound endpoint) 1` and exit 3 on
         its line; a project with neither mock.swagger nor branchContracts
         gets one "coverage not applicable" line — and its boundary: either
         one alone is applicable, and failing to start then SAYS so
Plus never silent: stopped by the run's own errors ("coverage not run"),
skipped by the flag ("coverage skipped").
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jsonui_test_cli import __version__
from jsonui_test_cli import contracts_coverage as cc
from tests import test_contracts_coverage as tcc

TEST_TOOLS = Path(__file__).resolve().parents[1]
NOTICE_HEAD = "validate fails unless contracts coverage exits 0"


def _with_test(root: Path, *, valid: bool = True) -> Path:
    t = root / "tests/screens/detail/detail.test.json"
    t.parent.mkdir(parents=True, exist_ok=True)
    step = {"action": "tap", "id": "btn"} if valid else {"action": "no_such_action"}
    t.write_text(json.dumps({
        "type": "screen", "source": {"layout": "test.json"}, "metadata": {"name": "detail"},
        "cases": [{"name": "c1", "description": "d", "steps": [step]}]}), encoding="utf-8")
    return root


def _validate(root: Path, *extra) -> tuple[int, str]:
    env = dict(os.environ, PYTHONPATH=f"{TEST_TOOLS}:{TEST_TOOLS.parent / 'jui_tools'}")
    r = subprocess.run([sys.executable, "-m", "jsonui_test_cli.cli", "validate", "tests",
                        "--no-install", *extra],
                       cwd=root, capture_output=True, text=True, env=env, timeout=300)
    return r.returncode, r.stdout


def _section(out: str) -> list:
    """The lines after the summary: what the coverage section printed."""
    tail = out.split("Files: ", 1)[1].split("\n", 1)[1]
    return [line for line in tail.splitlines() if line.strip()]


def _uncovered(tmp_path):
    return _with_test(tcc._project(tmp_path / "uncovered"))


def _clean(tmp_path):
    spec, openapi, mocks = tcc._clean()
    return _with_test(tcc._project(tmp_path / "clean", spec, openapi=openapi, mocks=mocks))


class TestXxxiReportedNotGating:
    @pytest.mark.parametrize("make, exit_word", [(_uncovered, "exit 1 (uncovered)"),
                                                  (_clean, "exit 0 (pass)")])
    def test_the_section_and_the_notice_and_the_same_rc(self, tmp_path, make, exit_word):
        root = make(tmp_path)
        rc, out = _validate(root)
        rc_without, out_without = _validate(root, "--no-coverage-check")
        assert rc == rc_without == 0, out
        section = _section(out)
        lines = [line for line in section if line.startswith("coverage: ")]
        assert [line.split()[1] for line in lines] == ["web", "ios"], section
        assert all(exit_word in line for line in lines), lines
        notices = [line for line in section if NOTICE_HEAD in line]
        assert len(notices) == 1, section
        assert notices[0].startswith(f"from jsonui-cli {cc.validate_gate_release(__version__)},")

    def test_the_numbers_are_the_coverage_commands_own(self, tmp_path):
        root = _uncovered(tmp_path)
        report = cc.run_coverage(root)
        _, out = _validate(root)
        for block in report.platforms:
            assert cc.denominator_line(block) in _section(out)
        web = next(b for b in report.platforms if b.platform == "web")
        assert cc.denominator_line(web) == (
            "coverage: web units 2 · statuses required 12 · row 5 · excluded 1 · "
            "uncovered 6 · not evaluated 0 → exit 1 (uncovered)")


class TestTheNoticesVersion:
    def test_it_is_the_next_patch_release(self):
        assert cc.validate_gate_release("1.8.119") == "1.8.120"
        assert cc.validate_gate_release("2.0.9") == "2.0.10"   # numeric, not string, increment

    def test_a_release_that_is_not_a_patch_bump_sets_it(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cc, "VALIDATE_GATE_FROM", "1.9.0")
        assert cc.validate_gate_release("1.8.119") == "1.9.0"
        lines, _ = cc.validate_section(tcc._project(tmp_path), "1.8.119")
        assert lines[-1].startswith("from jsonui-cli 1.9.0, "), lines

    def test_no_project_is_not_applicable_and_names_where_it_looked(self):
        lines, exit_code = cc.validate_section(Path("/nonexistent"), "1.8.119", blocked_by=1)
        assert (lines, exit_code) == (["coverage not applicable: no jui.config.json in /nonexistent"], None)


def test_xxiv_the_declaration_error_coverage_reports_is_in_the_section(tmp_path):
    spec = tcc._screen()
    spec["branchContracts"]["methods"]["approve"]["excludedOutcomes"]["api.setApproval"] = {
        "409": {"by": "unit", "reason": "tested in the view model's unit tests"}}
    root = _with_test(tcc._project(tmp_path, spec))
    report = cc.run_coverage(root)
    message = next(e["message"] for e in tcc._screen_result(report).declaration_errors
                   if "both a row and an excludedOutcomes" in e["message"])
    rc, out = _validate(root)
    assert rc == 0, out   # reported, not gating, in this release
    assert f"  declaration error  [web] detail: {message}" in _section(out), _section(out)


class TestXxviExit3AndNotApplicable:
    def test_an_exit_3_only_project_names_the_unbound_endpoint(self, tmp_path):
        spec, openapi, mocks = tcc._clean([{"method": "GET", "path": "/api/tags"}])
        root = _with_test(tcc._project(tmp_path, spec, openapi=openapi, mocks=mocks))
        rc, out = _validate(root)
        lines = [line for line in _section(out) if line.startswith("coverage: web")]
        assert len(lines) == 1 and "uncovered 0" in lines[0], _section(out)
        assert "n/a(unbound endpoint) 1" in lines[0] and "exit 3 (unmeasured)" in lines[0]
        assert rc == 0

    def test_neither_swagger_nor_branch_contracts_is_one_line(self, tmp_path):
        root = tmp_path / "plain"
        (root / "docs/screens/json").mkdir(parents=True)
        (root / "jui.config.json").write_text(json.dumps(
            {"spec_directory": "docs/screens/json", "platforms": ["web"]}), encoding="utf-8")
        (root / "docs/screens/json/home.spec.json").write_text(
            json.dumps({"type": "screen_spec", "metadata": {"name": "home"}}), encoding="utf-8")
        _with_test(root)
        rc, out = _validate(root)
        assert _section(out) == ["coverage not applicable: the project declares no "
                                 "mock.swagger and no spec has branchContracts"], out
        assert rc == 0

    def test_boundary_branch_contracts_without_swagger_cannot_start(self, tmp_path):
        root = tmp_path / "half"
        (root / "docs/screens/json").mkdir(parents=True)
        (root / "jui.config.json").write_text(json.dumps(
            {"spec_directory": "docs/screens/json", "platforms": ["web"]}), encoding="utf-8")
        (root / "docs/screens/json/detail.spec.json").write_text(
            json.dumps(tcc._screen()), encoding="utf-8")
        _with_test(root)
        rc, out = _validate(root)
        section = _section(out)
        assert section[0].startswith("coverage cannot start: mock.swagger is not declared"), section
        assert section[0].endswith("→ exit 2 (cannot_start)")
        assert any(NOTICE_HEAD in line for line in section)
        assert rc == 0

    def test_boundary_swagger_without_branch_contracts_is_applicable(self, tmp_path):
        spec = tcc._screen()
        del spec["branchContracts"]
        root = _with_test(tcc._project(tmp_path, spec))
        _, out = _validate(root)
        assert any(line.startswith("coverage: web") for line in _section(out)), _section(out)


class TestNeverSilent:
    def test_stopped_by_the_runs_own_errors(self, tmp_path):
        root = _with_test(tcc._project(tmp_path), valid=False)
        rc, out = _validate(root)
        rc_without, _ = _validate(root, "--no-coverage-check")
        assert rc == rc_without == 1, out
        section = _section(out)
        assert section[0].startswith("coverage not run: 1 error(s) above"), section
        assert any(NOTICE_HEAD in line for line in section)

    def test_the_flag_says_it_skipped(self, tmp_path):
        _, out = _validate(_uncovered(tmp_path), "--no-coverage-check")
        assert _section(out) == ["coverage skipped (--no-coverage-check)"]
