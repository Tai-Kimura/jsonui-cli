"""`validate` rebuilds `generated/` before it checks, so it can hide its own
finding. What it repaired has to reach the reader.

The rebuild runs ahead of the contract check. Anything it puts back is
something the check will not report, and the two lines a reader actually sees
— `Regenerated N mock file(s)` and `PASSED` — do not say that a file was
missing a moment ago. A consumer deleted one, got a green run, and could not
tell the tree had been repaired underneath the check.

A line existed for this and could not fire for it. It was guarded by
`if name in before`, and a whole file that was deleted is not in `before` —
its key is gone with it. Measured on a fixture, each arm with the file
confirmed absent and then confirmed back:

    whole generated file deleted   -> restored SILENTLY, PASSED, exit 0
    one scenario deleted from a file -> not rebuilt at all; reported as
        [ABSENT] with exit 1, which is correct and is a different mechanism
    swagger gains a response       -> the file IS rewritten, the old line
        DID fire, and called a legitimate addition "a scenario the tree was
        missing"

So the only path that could print it printed a false description, and the
path it was written for could not print. Relaxing the guard alone would have
turned a silent branch into a lying one — hence two lines with two sentences,
each true of its own case, rather than one loosened condition.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import cli

_OK = {"description": "d", "content": {"application/json": {
    "schema": {"type": "object", "properties": {"id": {"type": "string"}}}}}}


@pytest.fixture
def project(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "api.json").write_text(json.dumps({"openapi": "3.0.0", "paths": {
        "/api/x": {"get": {"operationId": "getX",
                           "responses": {"200": _OK, "404": _OK}}},
        "/api/y": {"get": {"operationId": "getY", "responses": {"200": _OK}}},
    }}), encoding="utf-8")
    proj = tmp_path / "proj"
    (proj / "tests" / "mocks").mkdir(parents=True)
    (proj / "tests" / "s.test.json").write_text(json.dumps({
        "type": "screen", "source": {"layout": "l.json"},
        "metadata": {"name": "s_test", "description": "d"},
        "cases": [{"name": "c", "description": "d",
                   "steps": [{"assert": "visible", "id": "root"}]}],
    }), encoding="utf-8")
    (proj / "jui.config.json").write_text(json.dumps({"mock": {
        "swagger": "../docs/api.json", "mockDir": "tests/mocks"}}),
        encoding="utf-8")
    return proj


# --no-coverage-check: these arms ask the mock gate, not contracts coverage.
# From jsonui-cli 1.8.121 (VALIDATE_GATE_FROM) coverage gates validate, and
# these fixtures declare a mock.swagger and no spec_directory: coverage
# cannot start and the run fails on that, at every release from the gate
# on. On a copy stamped 1.8.121, 49 validate runs in these eight files
# failed on coverage and 15 of their arms went red; below it, none
# (2026-09-26). The flag is how a user says coverage is not the run's
# subject; coverage's own arms are test_validate_coverage_section.
def _run(proj, monkeypatch, capsys):
    monkeypatch.chdir(proj)
    rc = cli.cmd_validate(argparse.Namespace(
        files=["tests"], verbose=False, quiet=False, config=None,
        no_mock_check=False, no_coverage_check=True, no_install=True, strict=False))
    return rc, capsys.readouterr().out


def _generated(proj):
    return sorted((proj / "tests" / "mocks" / "generated").rglob("*.mock.json"))


class TestAFileThatCameBackIsNamed:
    def test_a_deleted_generated_file_is_reported(
            self, project, monkeypatch, capsys):
        _run(project, monkeypatch, capsys)
        target = _generated(project)[0]
        target.unlink()
        # CONTROL: it really is gone before the run that must notice.
        assert not target.exists()

        rc, out = _run(project, monkeypatch, capsys)

        assert target.exists(), "the fixture did not exercise a repair"
        assert "regenerated a file that was missing from the tree" in out
        assert rc == 0

    def test_it_names_the_path_not_just_the_basename(
            self, project, monkeypatch, capsys):
        """The generated tree is `generated/<tag>/<operationId>.mock.json`,
        so a basename is ambiguous the moment two tags scaffold the same
        operation — and the table this compares was keyed on it."""
        _run(project, monkeypatch, capsys)
        target = _generated(project)[0]
        rel = target.relative_to(project / "tests" / "mocks" / "generated")
        target.unlink()

        _, out = _run(project, monkeypatch, capsys)

        assert str(rel) in out, out
        assert "/" in str(rel), "the fixture has no subdirectory to prove this"


class TestAnAdditionIsNotCalledARepair:
    def test_a_swagger_that_grows_says_so_in_its_own_words(
            self, project, tmp_path, monkeypatch, capsys):
        """The one path the old line could take, and it described it wrongly.
        Whether a scenario had ALSO been deleted is not knowable here, and
        "restored" asserts it."""
        _run(project, monkeypatch, capsys)
        spec_path = tmp_path / "docs" / "api.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["paths"]["/api/y"]["get"]["responses"]["500"] = _OK
        spec_path.write_text(json.dumps(spec), encoding="utf-8")

        rc, out = _run(project, monkeypatch, capsys)

        assert "generation added a scenario this file did not have" in out
        assert "error_500" in out
        assert "missing from the tree" not in out
        assert rc == 0


class TestTheOrdinaryRunGainsNothing:
    """The non-firing arms. A line on every run is the standing line the next
    real finding hides behind — and every consumer baseline moves."""

    def test_a_clean_rerun_prints_neither_line(
            self, project, monkeypatch, capsys):
        _run(project, monkeypatch, capsys)

        rc, out = _run(project, monkeypatch, capsys)

        assert "missing from the tree" not in out
        assert "did not have" not in out
        assert "removed " not in out
        assert rc == 0

    def test_the_first_build_is_not_a_repair(
            self, project, monkeypatch, capsys):
        """Every file is new when there is no tree yet. Reporting that as a
        repair would put the line on the one run where it is guaranteed
        meaningless — and on every fresh clone."""
        rc, out = _run(project, monkeypatch, capsys)

        assert "Regenerated 2 mock file(s)" in out
        assert "missing from the tree" not in out
        assert rc == 0

    def test_a_deleted_scenario_is_left_to_the_contract_check(
            self, project, monkeypatch, capsys):
        """Not this mechanism's case, measured rather than assumed: the file
        exists, so the rebuild does not run, and the check reports it loudly.
        A fix that made this print a repair line would be hiding a red."""
        _run(project, monkeypatch, capsys)
        target = _generated(project)[0]
        doc = json.loads(target.read_text(encoding="utf-8"))
        victim = sorted(doc["scenarios"])[-1]
        del doc["scenarios"][victim]
        target.write_text(json.dumps(doc), encoding="utf-8")

        rc, out = _run(project, monkeypatch, capsys)

        assert rc == 1
        assert "[ABSENT]" in out
        assert "missing from the tree" not in out
        assert "did not have" not in out


def _bump_mtime(path: Path, seconds: float = 10.0) -> None:
    st = path.stat()
    os.utime(path, (st.st_atime + seconds, st.st_mtime + seconds))


class TestAPruneIsNamed:
    """The rebuild empties generated/ and writes back only what the in-scope
    swagger generates, so a file no in-scope operation generates is deleted —
    intended, and it runs under `--no-install` (which skips only the install).
    Measured on a consumer project (2026-09-28): `validate --no-install`
    removed a mock and the editor schema copy beside it from one tag
    directory of generated/, and printed nothing about either. The deletion stays; the silence goes."""

    @pytest.fixture
    def tagged(self, project, tmp_path):
        spec_path = tmp_path / "docs" / "api.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["paths"]["/api/x"]["get"]["tags"] = ["x"]
        spec["paths"]["/api/y"]["get"]["tags"] = ["x"]
        spec["paths"]["/api/z"] = {"get": {
            "operationId": "getZ", "tags": ["z"],
            "responses": {"200": _OK}}}
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return project, spec_path

    def test_a_dropped_operation_and_its_schema_copy_are_named(
            self, tagged, monkeypatch, capsys):
        project, spec_path = tagged
        _run(project, monkeypatch, capsys)
        gen = project / "tests" / "mocks" / "generated"
        mock = gen / "z" / "getZ.mock.json"
        schema = gen / "z" / ".mock.schema.json"
        # CONTROL: both files are there before the run that removes them.
        assert mock.exists() and schema.exists(), sorted(gen.rglob("*"))

        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        del spec["paths"]["/api/z"]
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        _bump_mtime(spec_path)

        rc, out = _run(project, monkeypatch, capsys)

        # The prune itself is unchanged: generated/ follows the swagger.
        assert not mock.exists() and not schema.exists()
        assert (f"removed a file no in-scope operation generates "
                f"— {Path('z', 'getZ.mock.json')}") in out, out
        assert (f"removed the editor schema copy of a directory with no "
                f"generated mock left — {Path('z', '.mock.schema.json')}") in out, out
        # Only what went is named: the x/ mocks and their schema copy stay.
        assert len([line for line in out.splitlines() if line.startswith("  removed ")]) == 2, out
        assert (gen / "x" / ".mock.schema.json").exists()
        assert rc == 0

    def test_a_file_no_operation_generates_is_named_even_if_unparseable(
            self, tagged, monkeypatch, capsys):
        """`_scenario_names` skips a file it cannot parse; the prune does not."""
        project, spec_path = tagged
        _run(project, monkeypatch, capsys)
        stray = project / "tests" / "mocks" / "generated" / "x" / "stray.mock.json"
        stray.write_text("{not json", encoding="utf-8")
        _bump_mtime(spec_path, 20.0)

        _, out = _run(project, monkeypatch, capsys)

        assert not stray.exists()
        assert (f"removed a file no in-scope operation generates "
                f"— {Path('x', 'stray.mock.json')}") in out, out
        # Its directory still has generated mocks: the schema copy stays, and
        # is not reported.
        assert "editor schema copy" not in out

    def test_the_no_install_help_says_the_rebuild_still_runs(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["jsonui-test", "validate", "--help"])
        with pytest.raises(SystemExit):
            cli.main()
        text = " ".join(capsys.readouterr().out.split())
        assert "generated/ tree is still rebuilt" in text, text
