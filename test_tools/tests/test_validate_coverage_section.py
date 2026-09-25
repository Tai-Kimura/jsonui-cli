"""`jsonui-test validate` reports contracts coverage, announces its gate, then gates.

Design §2.6 / §6.1, P3a (the user's ruling U5 = plan C: announce once, then
gate; no flag, U1). validate gains a coverage section: one denominator line per
platform, the declaration errors, and one line about the gate. The gate is a
VERSION, `VALIDATE_GATE_FROM`, written as a literal when the announcing release
is cut:
  unset          "coverage gate version not declared" — announces nothing
  above running  the notice names it; the return code does not read coverage
  at or below    validate fails unless coverage exits 0 — after installing the
                 valid tests, with `Result: FAILED` and `Coverage: exit N`
No default derived from the running version: it would agree with every build,
so red-check xxxi could not fail, and "running >= derived" never switches on.

The red-checks, on the real `validate` (in process, so the gate version can be
set) over the coverage suite's own fixtures:
  xxxi   announcing: uncovered and clean projects — the section, the notice
         naming the declared release, the rc of the same run without the
         section; and at the tag, `dev-guide/release/validate_gate_version.py`
  xxiv   gating: the declaration error in the section, the tests INSTALLED,
         and then rc 1
  xxvi   gating: an exit-3-only project fails validate; a project with neither
         mock.swagger nor branchContracts does not, with one line — and the
         boundary: branchContracts without swagger cannot start, and fails
Plus never silent: stopped by the run's own errors, skipped by the flag.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from jsonui_test_cli import __version__
from jsonui_test_cli import contracts_coverage as cc
from jsonui_test_cli.cli import main
from tests import test_contracts_coverage as tcc

REPO = Path(__file__).resolve().parents[2]
# What every announcing line holds after its version — derived, so a new text
# cannot leave the negative arms below asserting the absence of an old one.
NOTICE_HEAD = cc.VALIDATE_NOTICE.split("{version}", 1)[1]
ABOVE, BELOW = "99.0.0", "0.0.1"   # a gate the running version has not / has reached


def _with_test(root: Path, *, valid: bool = True, install_to: str | None = None) -> Path:
    t = root / "tests/screens/detail/detail.test.json"
    t.parent.mkdir(parents=True, exist_ok=True)
    step = {"action": "tap", "id": "btn"} if valid else {"action": "no_such_action"}
    t.write_text(json.dumps({
        "type": "screen", "source": {"layout": "test.json"}, "metadata": {"name": "detail"},
        "cases": [{"name": "c1", "description": "d", "steps": [step]}]}), encoding="utf-8")
    if install_to:
        config = json.loads((root / "jui.config.json").read_text(encoding="utf-8"))
        config["test"] = {"install": {"web": install_to}}
        (root / "jui.config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


@pytest.fixture
def validate(monkeypatch, capsys):
    def run(root: Path, *extra, gate=ABOVE, install: bool = False) -> tuple[int, str]:
        monkeypatch.chdir(root)
        monkeypatch.setattr(cc, "VALIDATE_GATE_FROM", gate)
        argv = ["jsonui-test", "validate", "tests", *extra]
        if not install:
            argv.append("--no-install")
        monkeypatch.setattr(sys, "argv", argv)
        rc = main()
        return rc, capsys.readouterr().out
    return run


def _summary(out: str) -> str:
    return next(line for line in out.splitlines() if line.startswith("Files: "))


def _section(out: str) -> list:
    """The lines after the summary: what the coverage section printed."""
    tail = out.split("Files: ", 1)[1].split("\n", 1)[1]
    return [line for line in tail.splitlines() if line.strip()]


def _uncovered(tmp_path, **kw):
    return _with_test(tcc._project(tmp_path / "uncovered"), **kw)


def _clean(tmp_path, **kw):
    spec, openapi, mocks = tcc._clean()
    return _with_test(tcc._project(tmp_path / "clean", spec, openapi=openapi, mocks=mocks), **kw)


def _exit3(tmp_path, **kw):
    spec, openapi, mocks = tcc._clean([{"method": "GET", "path": "/api/tags"}])
    return _with_test(tcc._project(tmp_path / "exit3", spec, openapi=openapi, mocks=mocks), **kw)


def _no_contracts(tmp_path, *, with_branch_contracts=False):
    root = tmp_path / "plain"
    (root / "docs/screens/json").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(
        {"spec_directory": "docs/screens/json", "platforms": ["web"]}), encoding="utf-8")
    spec = tcc._screen() if with_branch_contracts else {"type": "screen_spec", "metadata": {"name": "home"}}
    (root / "docs/screens/json/home.spec.json").write_text(json.dumps(spec), encoding="utf-8")
    return _with_test(root)


# ------------------------------------------------------- announcing (N) ---

class TestXxxiAnnouncing:
    @pytest.mark.parametrize("make, exit_word", [(_uncovered, "exit 1 (uncovered)"),
                                                  (_clean, "exit 0 (pass)")])
    def test_the_section_the_notice_and_the_same_rc(self, tmp_path, validate, make, exit_word):
        root = make(tmp_path)
        rc, out = validate(root)
        rc_without, _ = validate(root, "--no-coverage-check")
        assert rc == rc_without == 0, out
        assert "Result: PASSED" in out and "Coverage:" not in _summary(out)
        section = _section(out)
        lines = [line for line in section if line.startswith("coverage: ")]
        assert [line.split()[1] for line in lines] == ["web", "ios"], section
        assert all(exit_word in line for line in lines), lines
        assert section[-1] == cc.VALIDATE_NOTICE.format(version=ABOVE), section

    def test_undeclared_announces_nothing_and_says_so(self, tmp_path, validate):
        rc, out = validate(_uncovered(tmp_path), gate=None)
        assert rc == 0
        section = _section(out)
        assert section[-1].startswith("coverage gate version not declared"), section
        assert not any(NOTICE_HEAD in line for line in section)

    @pytest.mark.parametrize("gate, line", [
        ("withdrawn", 'coverage gate withdrawn (VALIDATE_GATE_FROM = "withdrawn")'),
        ("1.8", 'coverage gate version unreadable (VALIDATE_GATE_FROM = "1.8") — not a '
                "release number: this build announces no release and does not gate"),
    ])
    def test_withdrawn_or_unreadable_says_so_and_does_not_fail(self, tmp_path, validate,
                                                               gate, line):
        # The project is uncovered: at BELOW a gate would fail it (rc 1).
        root = _uncovered(tmp_path)
        rc, out = validate(root, gate=gate)
        rc_without, _ = validate(root, "--no-coverage-check", gate=gate)
        assert rc == rc_without == 0, out
        assert "Coverage:" not in _summary(out)
        section = _section(out)
        assert section[-1] == line, section
        assert not any(NOTICE_HEAD in l or l.startswith("validate gates on") for l in section)

    def test_the_numbers_are_the_coverage_commands_own(self, tmp_path, validate):
        root = _uncovered(tmp_path)
        report = cc.run_coverage(root)
        _, out = validate(root)
        for block in report.platforms:
            assert any(line.startswith(cc.denominator_line(block) + " · baselined ")
                       for line in _section(out)), _section(out)
        web = next(b for b in report.platforms if b.platform == "web")
        assert cc.denominator_line(web) == (
            "coverage: web units 2 · statuses required 12 · row 5 · excluded 1 · "
            "uncovered 6 · not evaluated 0 → exit 1 (uncovered)")


# ------------------------------------------------------------ gating (N+1) ---

class TestGating:
    def test_xxiv_the_error_is_reported_the_tests_installed_then_rc_1(self, tmp_path, validate):
        spec = tcc._screen()
        spec["branchContracts"]["methods"]["approve"]["excludedOutcomes"]["api.setApproval"] = {
            "409": {"by": "unit", "reason": "tested in the view model's unit tests"}}
        dest = tmp_path / "installed"
        root = _with_test(tcc._project(tmp_path / "p", spec), install_to=str(dest))
        message = next(e["message"] for e in
                       tcc._screen_result(cc.run_coverage(root)).declaration_errors
                       if "both a row and an excludedOutcomes" in e["message"])
        rc, out = validate(root, gate=BELOW, install=True)
        assert f"  declaration error  [web] detail: {message}" in _section(out), _section(out)
        installed = sorted(p.name for p in dest.rglob("*.test.json"))
        assert installed, f"nothing installed before the rc — {out}"
        assert rc == 1
        assert "Result: FAILED" in out and "Coverage: FAILED (exit 1;" in _summary(out)

    @pytest.mark.parametrize("make, rc_expected, exit_code", [
        (_uncovered, 1, 1), (_clean, 0, 0), (_exit3, 1, 3)])
    def test_the_rc_follows_coverage(self, tmp_path, validate, make, rc_expected, exit_code):
        rc, out = validate(make(tmp_path), gate=BELOW)
        assert rc == rc_expected, out
        # No baseline file: every entry is new, so the gate asks what exit 0 asked.
        verdict = "FAILED" if rc_expected else "passed"
        assert f"Coverage: {verdict} (exit {exit_code}" in _summary(out)
        assert ("Result: FAILED" in out) == bool(rc_expected)
        assert _section(out)[-1].startswith("validate gates on contracts coverage (from jsonui-cli 0.0.1)")

    def test_xxvi_exit_3_names_its_cause(self, tmp_path, validate):
        _, out = validate(_exit3(tmp_path), gate=BELOW)
        line = next(l for l in _section(out) if l.startswith("coverage: web"))
        assert "uncovered 0" in line and "n/a(unbound endpoint) 1" in line
        assert "exit 3 (unmeasured) · baselined 0 (matched 0 · new 1 · stale 0)" in line

    def test_xxvi_not_applicable_does_not_fail(self, tmp_path, validate):
        rc, out = validate(_no_contracts(tmp_path), gate=BELOW)
        assert _section(out) == ["coverage not applicable: the project declares no "
                                 "mock.swagger and no spec has branchContracts"]
        assert rc == 0 and "Coverage:" not in _summary(out)

    def test_boundary_branch_contracts_without_swagger_cannot_start_and_fails(self, tmp_path, validate):
        rc, out = validate(_no_contracts(tmp_path, with_branch_contracts=True), gate=BELOW)
        assert _section(out)[0].startswith("coverage cannot start: mock.swagger is not declared")
        assert _section(out)[0].endswith("→ exit 2 (cannot_start)")
        assert rc == 1 and "Coverage: FAILED (exit 2; cannot start)" in _summary(out)

    def test_boundary_the_same_project_announcing_does_not_fail(self, tmp_path, validate):
        rc, _ = validate(_no_contracts(tmp_path, with_branch_contracts=True), gate=ABOVE)
        assert rc == 0

    def test_the_flag_skips_and_does_not_fail(self, tmp_path, validate):
        rc, out = validate(_uncovered(tmp_path), "--no-coverage-check", gate=BELOW)
        assert _section(out) == ["coverage skipped (--no-coverage-check)"]
        assert rc == 0


class TestNeverSilent:
    @pytest.mark.parametrize("gate", [ABOVE, BELOW])
    def test_stopped_by_the_runs_own_errors(self, tmp_path, validate, gate):
        root = _with_test(tcc._project(tmp_path), valid=False)
        rc, out = validate(root, gate=gate)
        assert rc == 1
        assert _section(out)[0].startswith("coverage not run: 1 error(s) above"), _section(out)


# ---------------------------------------------------------- the version ---

class TestTheGateVersion:
    def test_it_compares_numerically(self):
        assert cc.version_key("1.8.100") > cc.version_key("1.8.99")
        assert cc.gate_is_on("1.8.120", "1.8.120") and cc.gate_is_on("1.9.0", "1.8.120")
        assert not cc.gate_is_on("1.8.119", "1.8.120")

    def test_unset_is_never_on(self, monkeypatch):
        monkeypatch.setattr(cc, "VALIDATE_GATE_FROM", None)
        assert not cc.gate_is_on(__version__) and not cc.gate_is_on("999.0.0")

    # A literal that is not a release number never gates, however far the
    # running version is past it. `version_key` read "withdrawn" as () and "1.8"
    # as (1, 8) — prefixes every version is at or above, so each of these was
    # ON (ee, 2026-09-25). "1.8.l20" read as 1.8.20.
    @pytest.mark.parametrize("literal, state", [
        ("withdrawn", "withdrawn"), ("next", "unreadable"), ("1.8", "unreadable"),
        ("1.8.l20", "unreadable"), ("v1.8.120", "unreadable"), ("1.8.120rc1", "unreadable")])
    def test_a_literal_that_is_not_a_release_never_gates(self, literal, state):
        assert cc.gate_state(literal) == state
        assert not cc.gate_is_on("999.0.0", literal)
        assert not cc.gate_is_on("1.8.119", literal)

    def test_control_a_release_number_is_one(self):
        assert cc.gate_state("1.8.120") == "release" and cc.gate_is_on("1.8.120", "1.8.120")

    def test_the_shipped_value_is_a_literal_or_unset(self):
        # Whatever a release sets, it is written, not computed (see the module).
        src = (REPO / "test_tools/jsonui_test_cli/contracts_coverage.py").read_text(encoding="utf-8")
        assert len([l for l in src.splitlines() if l.startswith("VALIDATE_GATE_FROM")]) == 1


def _tag_check():
    path = REPO / "dev-guide/release/validate_gate_version.py"
    spec = importlib.util.spec_from_file_location("validate_gate_version", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestXxxiAtTheTag:
    """The tag gate's half: the literal against the tag being cut."""

    @staticmethod
    def _src(literal: str) -> str:
        return f"x = 1\nVALIDATE_GATE_FROM: str | None = {literal}\n"

    @pytest.mark.parametrize("literal, ok, word", [
        ('"1.8.120"', True, "announces"), ('"1.9.0"', True, "announces"),
        ('"2.0.0"', True, "announces"),
        ('None', False, "unset"), ('"1.8.121"', False, "cannot be"), ('"1.10.0"', False, "cannot be"),
    ])
    def test_the_verdict(self, literal, ok, word):
        got, why = _tag_check().verdict("1.8.119", self._src(literal))
        assert (got, word in why) == (ok, True), why

    @pytest.mark.parametrize("literal", ['"1.8.119"', '"1.8.99"'])
    def test_gating_needs_the_previous_tag_to_have_announced_it(self, literal):
        check = _tag_check()
        ok, why = check.verdict("1.8.119", self._src(literal), previous=self._src(literal))
        assert ok and "gates since" in why, why

    def test_the_first_release_setting_it_to_n_is_red(self):
        # ee, v4.14: in N — the first release with the section — a literal
        # <= N would switch the gate on with no release having announced it.
        ok, why = _tag_check().verdict("1.8.119", self._src('"1.8.119"'), previous="no section here\n")
        assert not ok and "had no section" in why, why

    def test_a_different_previous_announcement_is_red(self):
        ok, why = _tag_check().verdict("1.8.120", self._src('"1.8.120"'),
                                       previous=self._src('"1.8.121"'))
        assert not ok and "announced '1.8.121'" in why, why

    def test_a_tree_before_the_section_is_n_a(self):
        assert _tag_check().verdict("1.8.117", "nothing\n") == (
            True, "n/a — no VALIDATE_GATE_FROM in this tree (it predates the section)")

    def test_this_tree_reads_as_what_the_constant_says(self):
        src = (REPO / "test_tools/jsonui_test_cli/contracts_coverage.py").read_text(encoding="utf-8")
        ok, why = _tag_check().verdict(__version__, src)
        if cc.VALIDATE_GATE_FROM is None:
            assert not ok and "unset" in why
        else:
            assert ok, why

    def test_check_tag_runs_it(self):
        text = (REPO / "dev-guide/release/check-tag.sh").read_text(encoding="utf-8")
        assert 'validate_gate_version.py" "$VER"' in text
        assert '--repo "$R" "$BRANCH" "$PREV"' in text   # the previous tag's tree, too
        assert 'ck "validate gate version (xxxi)"' in text
