"""Unchecked mocks that live outside the validated path, found by convention.

The counting warning reads the files a run collected, so a project whose mocks
sit in another tree and whose config says nothing about them looks exactly like
a project with no mocks. The ancestor convention in `validation/mock.py` can
find them — but unbounded it walks to the filesystem root, and on a machine
where every project lives under one directory, one stray `mocks/` there
resolves for all of them. The projects it would then talk about are the ones
with no mocks at all, which is the false positive that gets a check turned off.

So the search is bounded at the project root, and the boundary is the config
this run actually loaded rather than the nearest one above some file: the
gate's inputs come from that config, so "this project" has to mean the same
directory for both.

Most of these tests are about staying quiet. Finding nothing is not evidence
that there is nothing — a project may keep its mocks where this convention
does not reach — so the feature adds a way to speak and never a way to
reassure. There is no `Unchecked mocks: 0`.
"""

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validation.mock import find_mock_dir

TEST_FILE = {
    "type": "screen",
    "source": {"layout": "test.json"},
    "metadata": {"name": "a_test", "description": "d"},
    "cases": [{"name": "c", "description": "d",
               "steps": [{"assert": "visible", "id": "root"}]}],
}


def _mock(op="opX"):
    return {"source": {"method": "GET", "path": f"/api/{op}", "operationId": op},
            "scenarios": {"default": {"status": 200, "body": {}}}}


def _write(path: Path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _project(tmp_path, config=None, mocks_at=None, test_at="tests/screens/a.test.json"):
    """A project with its test files, optionally with mocks somewhere."""
    proj = tmp_path / "proj"
    _write(proj / test_at, TEST_FILE)
    _write(proj / "jui.config.json", config if config is not None else {"test": {}})
    if mocks_at:
        _write(proj / mocks_at / "m.mock.json", _mock())
    return proj


def _validate(proj, monkeypatch, files=("tests",)):
    from jsonui_test_cli.cli import cmd_validate

    monkeypatch.chdir(proj)
    args = type("Args", (), {
        "files": list(files), "verbose": False, "quiet": True, "config": None,
        "no_install": True, "no_mock_check": False,
    })()
    out = io.StringIO()
    with redirect_stdout(out):
        code = cmd_validate(args)
    return code, out.getvalue()


class TestTheWarningFires:
    def test_mocks_in_the_project_but_outside_the_validated_path(self, tmp_path, monkeypatch):
        # The reported configuration: nothing declared, and `validate tests`
        # never walks the tree the mocks are in.
        proj = _project(tmp_path)
        _write(proj / "mocks" / "m.mock.json", _mock())
        code, output = _validate(proj, monkeypatch)
        assert "mock contract check did not run" in output
        assert "Unchecked mocks: 1" in output
        assert code == 0, "a warning, never the exit code"

    def test_the_conventional_tests_mocks_location(self, tmp_path, monkeypatch):
        # Validated path narrowed to the screens dir, so `tests/mocks` is NOT
        # collected and only the ancestor convention can reach it. With the
        # wider path this test passed with the discovery removed — the
        # collection warning was answering for it.
        proj = _project(tmp_path, test_at="tests/screens/a.test.json")
        _write(proj / "tests" / "mocks" / "m.mock.json", _mock())
        _, output = _validate(proj, monkeypatch, files=("tests/screens",))
        assert "Unchecked mocks: 1" in output


class TestTheWarningStaysQuiet:
    def test_no_mocks_anywhere(self, tmp_path, monkeypatch):
        proj = _project(tmp_path)
        _, output = _validate(proj, monkeypatch)
        assert "Unchecked mocks" not in output
        assert "did not run" not in output

    def test_an_unrelated_mocks_dir_at_the_repository_root(self, tmp_path, monkeypatch):
        # Measured against the unbounded convention: this resolved, and the
        # project it spoke about had no mocks of its own.
        proj = tmp_path / "repo" / "apps" / "web"
        _write(proj / "tests" / "screens" / "a.test.json", TEST_FILE)
        _write(proj / "jui.config.json", {"test": {}})
        _write(tmp_path / "repo" / "mocks" / "unrelated.mock.json", _mock())
        _, output = _validate(proj, monkeypatch)
        assert "Unchecked mocks" not in output

    def test_a_mocks_dir_outside_the_repository(self, tmp_path, monkeypatch):
        # The heavier one, and it was not on anyone's list: the walk had no
        # stop condition at all, so a directory above the checkout resolved.
        proj = _project(tmp_path)
        _write(tmp_path / "mocks" / "someone_elses.mock.json", _mock())
        _, output = _validate(proj, monkeypatch)
        assert "Unchecked mocks" not in output

    def test_a_config_without_a_mock_block_does_not_open_the_boundary(self, tmp_path, monkeypatch):
        # `jui.config.json` was read for `mockDir` and never treated as an
        # edge, so a config with no mock block let the walk straight through.
        proj = _project(tmp_path, config={"test": {}})
        (proj / ".git").mkdir()
        _write(tmp_path / "mocks" / "someone_elses.mock.json", _mock())
        _, output = _validate(proj, monkeypatch)
        assert "Unchecked mocks" not in output

    def test_a_sibling_app_in_the_same_repository(self, tmp_path, monkeypatch):
        # Validated per app, so the sibling's mocks are neither collected nor
        # on the ancestor chain. (Under a shared validated path they ARE
        # collected, and the counting warning fires on its own terms — a
        # different code path, and correct there: this run did validate them.)
        proj = _project(tmp_path, test_at="tests/admin/screens/a.test.json")
        _write(proj / "tests" / "user" / "mocks" / "m.mock.json", _mock())
        _, output = _validate(proj, monkeypatch, files=("tests/admin",))
        assert "Unchecked mocks" not in output

    def test_nothing_is_claimed_when_the_search_finds_nothing(self, tmp_path, monkeypatch):
        # No `Unchecked mocks: 0`. "Did not find" and "counted none" are
        # different sentences, and only one of them is true here.
        #
        # Two independent guards hold this: the helper returns None, and the
        # summary only appends the field when the value is truthy. Neutralising
        # either one alone leaves the output correct, so this assertion cannot
        # fail on its own — the one below is the red-checkable half.
        proj = _project(tmp_path)
        _, output = _validate(proj, monkeypatch)
        assert "Unchecked mocks: 0" not in output

    def test_the_helper_returns_none_rather_than_zero(self, tmp_path, monkeypatch):
        from jsonui_test_cli.cli import _unchecked_mocks_elsewhere

        # An EMPTY mocks/ directory: the convention resolves it, and there is
        # nothing in it. Without a directory at all the function returns early
        # and never reaches the branch this pins.
        proj = _project(tmp_path)
        (proj / "mocks").mkdir()
        monkeypatch.chdir(proj)
        found = _unchecked_mocks_elsewhere(
            None, [proj / "tests" / "screens" / "a.test.json"])
        assert found is None, (
            "0 would be a count; the search not finding anything is not a "
            "count, and a later caller printing it unconditionally would say "
            "so in the summary")


class TestNestedProjects:
    """A monorepo: the boundary decides, and it decides the same way twice."""

    def _monorepo(self, tmp_path, child_has_own_mocks):
        mono = tmp_path / "mono"
        _write(mono / "jui.config.json", {"mock": {"mockDir": "mocks"}})
        _write(mono / "mocks" / "shared.mock.json", _mock("sharedOp"))
        child = mono / "apps" / "web"
        _write(child / "tests" / "screens" / "a.test.json", TEST_FILE)
        _write(child / "jui.config.json", {"test": {}})
        if child_has_own_mocks:
            _write(child / "tests" / "mocks" / "own.mock.json", _mock("ownOp"))
        return mono, child

    def test_the_child_does_not_reach_the_parents_aggregated_mocks(self, tmp_path, monkeypatch):
        # Unbounded, this resolved to the parent's `mocks/`. Bounded, it does
        # not: the run's config is the child's, so the child is the project.
        # This costs a detection — a genuine parent-aggregated layout goes
        # unreported — and that is the acceptable direction, because the
        # feature only ever promises to speak, never that silence means none.
        # Updated: this used to assert `== mono / "mocks"`, pinning the
        # unbounded default that the class below documented as deliberate.
        # The two halves of this test then disagreed — the CLI was silent, the
        # direct call reached the parent — and the test's own name described
        # the CLI half. Now the walk derives its own bound, so both halves say
        # the same thing.
        _mono, child = self._monorepo(tmp_path, child_has_own_mocks=False)
        assert find_mock_dir(child / "tests" / "screens" / "a.test.json") is None
        _, output = _validate(child, monkeypatch)
        assert "Unchecked mocks" not in output

    def test_the_child_finds_its_own(self, tmp_path, monkeypatch):
        _mono, child = self._monorepo(tmp_path, child_has_own_mocks=True)
        _, output = _validate(child, monkeypatch, files=("tests/screens",))
        assert "Unchecked mocks: 1" in output


class TestTheBoundaryIsNotOptional:
    """Reversed, with a measurement. This class used to read `stop_at` is
    opt-in: every existing caller keeps the unbounded walk`, on the reasoning
    that narrowing it for everyone would shrink an existing check silently.

    That reasoning was about the wrong risk. Opt-in meant the walk was bounded
    exactly where someone remembered to bound it, and the three validators
    running the *reference* check never did — so a project declaring no
    mockDir had a decoy above its own root supply the entire operationId index
    and fail the run. Same mechanism as the blocker of v1.6.55, in the case
    v1.6.55 did not cover, found by measuring rather than by a fifth report.

    The walk now derives the project it is in. There is no argument left to
    forget.
    """

    def test_the_walk_does_not_leave_the_project(self, tmp_path):
        proj = _project(tmp_path)
        _write(tmp_path / "mocks" / "m.mock.json", _mock())
        assert find_mock_dir(proj / "tests" / "screens" / "a.test.json") is None

    def test_the_project_root_itself_is_searched(self, tmp_path):
        # Inclusive: mocks at the project root are the project's own.
        proj = _project(tmp_path)
        _write(proj / "mocks" / "m.mock.json", _mock())
        assert (find_mock_dir(proj / "tests" / "screens" / "a.test.json")
                == proj / "mocks")

    def test_a_checkout_with_no_config_falls_back_to_git(self, tmp_path):
        """A boundary definition, not a second rule for where mocks live."""
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        _write(tmp_path / "repo" / "tests" / "screens" / "a.test.json",
               TEST_FILE)
        _write(tmp_path / "mocks" / "m.mock.json", _mock())      # outside
        _write(tmp_path / "repo" / "mocks" / "m.mock.json", _mock())
        assert (find_mock_dir(tmp_path / "repo" / "tests" / "screens" / "a.test.json")
                == tmp_path / "repo" / "mocks")


class TestDeclaredConfigurationIsUnaffected:
    def test_a_declared_gate_still_runs_and_this_stays_out_of_it(self, tmp_path, monkeypatch):
        spec = _write(tmp_path / "docs" / "spec.json", {
            "openapi": "3.0.3",
            "paths": {"/api/opX": {"get": {
                "operationId": "opX", "tags": ["X"],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"type": "object"}}}}}}}},
        })
        proj = _project(tmp_path, config={"mock": {
            "swagger": f"../{spec.relative_to(tmp_path)}", "mockDir": "tests/mocks"}})
        _write(proj / "tests" / "mocks" / "x" / "m.mock.json", _mock())
        _, output = _validate(proj, monkeypatch)
        assert "Unchecked mocks" not in output
        assert "Orphan mocks:" in output, "the gate ran, so it reports"


class TestSplitTreeLayouts:
    """Tests in one tree, the app (config and mocks) in another.

    Walking up from a test file never passes through the app directory, so a
    single starting point cannot see those mocks however the boundary is
    defined. Two consumers use this layout. A second start at the project root
    closes it; the boundary still decides what is in and out.
    """

    def _split(self, tmp_path, in_bounds=0, decoy=0, extra=None):
        repo = tmp_path / "repo"
        _write(repo / "tests" / "admin" / "screens" / "a.test.json", TEST_FILE)
        app = repo / "admin"
        _write(app / "jui.config.json", {"test": {}})
        for i in range(in_bounds):
            _write(app / "tests" / "mocks" / f"m{i}.mock.json", _mock(f"in{i}"))
        for i in range(decoy):
            _write(repo / "mocks" / f"d{i}.mock.json", _mock(f"out{i}"))
        for rel, body in (extra or []):
            _write(app / rel, body)
        return app

    def _run(self, app, monkeypatch):
        return _validate(app, monkeypatch, files=("../tests/admin",))

    def test_the_apps_own_mocks_are_found(self, tmp_path, monkeypatch):
        app = self._split(tmp_path, in_bounds=3)
        _, output = self._run(app, monkeypatch)
        assert "Unchecked mocks: 3" in output

    def test_the_decoy_outside_the_boundary_is_still_not(self, tmp_path, monkeypatch):
        # The v1.6.53 regression, preserved: closing the detection must not
        # reopen the false positive it was closed around.
        app = self._split(tmp_path, in_bounds=3, decoy=9)
        _, output = self._run(app, monkeypatch)
        assert "Unchecked mocks: 3" in output
        assert "9 mock file(s)" not in output

    def test_a_decoy_alone_stays_silent(self, tmp_path, monkeypatch):
        app = self._split(tmp_path, decoy=4)
        _, output = self._run(app, monkeypatch)
        assert "Unchecked mocks" not in output

    def test_mock_json_files_kept_for_another_purpose_are_reported(self, tmp_path, monkeypatch):
        # Adjudicated: the sentence is true of them — this many `*.mock.json`
        # are here and nothing declares a contract to check them against.
        # Only the project knows the intent, and both ways to silence it are
        # its own declaration: declare `mock.swagger`, or do not use the name.
        app = self._split(tmp_path, extra=[("mocks/other.mock.json", _mock())])
        _, output = self._run(app, monkeypatch)
        assert "Unchecked mocks: 1" in output
        assert str(app / "mocks") in output, (
            "the directory is what makes the finding actionable; the ruling "
            "to report these depends on the reader being able to see which "
            "directory is meant")

    def test_a_directory_with_no_mock_files_is_silent(self, tmp_path, monkeypatch):
        # The count decides, not the directory's existence. That is what keeps
        # a `mocks/` folder used for something else quiet unless it actually
        # holds files this check would have read.
        app = self._split(tmp_path)
        (app / "mocks").mkdir(parents=True)
        (app / "mocks" / "README.md").write_text("fixtures", encoding="utf-8")
        _, output = self._run(app, monkeypatch)
        assert "Unchecked mocks" not in output


class TestTheTwoStartsDoNotDoubleCount:
    def test_one_directory_reached_from_both_starts_is_counted_once(self, tmp_path, monkeypatch):
        # The common layout: tests and config share a tree, so both starts
        # walk to the same `tests/mocks`. Counting it twice would put a number
        # in the summary that matches nothing on disk.
        proj = _project(tmp_path, test_at="tests/screens/a.test.json")
        for i in range(3):
            _write(proj / "tests" / "mocks" / f"m{i}.mock.json", _mock(f"op{i}"))
        _, output = _validate(proj, monkeypatch, files=("tests/screens",))
        assert "Unchecked mocks: 3" in output
        assert "Unchecked mocks: 6" not in output

    def test_two_directories_are_both_named(self, tmp_path, monkeypatch):
        # The two starts land apart only when the test tree has its own mocks
        # deeper than the project root's: the walk from the test file stops at
        # `tests/admin/mocks`, and the walk from the root finds `mocks`
        # because `tests/mocks` is not there. A first attempt at this test put
        # both at the usual places and they resolved to one directory — the
        # convention checks `tests/mocks` before `mocks` at every level.
        proj = _project(tmp_path, test_at="tests/admin/screens/a.test.json")
        _write(proj / "tests" / "admin" / "mocks" / "a.mock.json", _mock("a"))
        _write(proj / "mocks" / "b.mock.json", _mock("b"))
        _, output = _validate(proj, monkeypatch, files=("tests/admin/screens",))
        assert "Unchecked mocks: 2" in output
        assert str(proj / "tests" / "admin" / "mocks") in output
        assert str(proj / "mocks") in output
