"""`validate <subset>` must not delete the tests it was not given.

The wipe's denominator was the whole destination; the repopulate's was the
command line. Passing one file deleted the rest — measured on a real
project, one file took an iOS destination from 63 installed tests to 1. The
destination is gitignored, so `git status` showed nothing: the loss was
invisible to the check a person would reach for.

WHY IT SURVIVED. In normal use every test is passed, so `cleaned ==
installed` and the line reads as a no-op. It breaks only when the argument
list is narrowed, which is what somebody does while iterating on ONE test —
so the people most likely to trigger it are the ones doing the most normal
thing, and a full-run corpus can never exhibit it.

AND THE COUNT WAS ALREADY PRINTED. `Installed 2 test file(s) → 2 target(s)
(cleaned 126 stale)` was on screen, correct and unrounded, and did not stop
the person who ran it: two numbers in one sentence with nothing comparing
them, after `Result: PASSED`, in the same words a healthy full sync uses.
`removed == installed` being an invariant of a healthy run was written
nowhere. So the fix is a COMPARISON, not a louder line — and these tests
assert the behaviour rather than the wording.

Every arm here has a non-deleting half AND a still-deleting half: a fix that
simply stopped cleaning would pass the first and is not the fix, since the
clean is what removes a test whose source was really deleted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import cli
from jsonui_test_cli.install import flatten_install


def _doc(name):
    return {"type": "screen", "source": {"layout": "l.json"},
            "metadata": {"name": f"{name}_test", "description": "d"},
            "cases": [{"name": "c", "description": "d",
                       "steps": [{"assert": "visible", "id": "root"}]}]}


@pytest.fixture
def project(tmp_path):
    """Three tests in two directories, one install target."""
    proj = tmp_path / "proj"
    for sub, names in (("a", ("alpha", "alpha2")), ("b", ("beta",))):
        (proj / "tests" / "screens" / sub).mkdir(parents=True)
        for name in names:
            (proj / "tests" / "screens" / sub / f"{name}.test.json").write_text(
                json.dumps(_doc(name)), encoding="utf-8")
    (proj / "jui.config.json").write_text(json.dumps({
        "test": {"install": {"ios": {"dir": "GeneratedTests"}}}}),
        encoding="utf-8")
    return proj


def _run(proj, files, monkeypatch, capsys):
    monkeypatch.chdir(proj)
    rc = cli.cmd_validate(argparse.Namespace(
        files=files, verbose=False, quiet=False, config=None,
        no_mock_check=True, no_install=False, strict=False))
    return rc, capsys.readouterr().out


def _installed(proj):
    return sorted(p.name for p in (proj / "GeneratedTests").glob("*.test.json"))


ALL_THREE = ["alpha.test.json", "alpha2.test.json", "beta.test.json"]


class TestANarrowedRunLeavesTheRestAlone:
    def test_one_file_does_not_delete_the_other_two(
            self, project, monkeypatch, capsys):
        _run(project, ["tests"], monkeypatch, capsys)
        # CONTROL: the destination really is populated before the narrow run.
        assert _installed(project) == ALL_THREE

        _run(project, ["tests/screens/a/alpha.test.json"], monkeypatch, capsys)

        assert _installed(project) == ALL_THREE

    def test_one_subdirectory_does_not_delete_the_others(
            self, project, monkeypatch, capsys):
        """A directory argument is still a narrowed one.

        Any rule keyed on "was an argument a directory" gets this wrong, and
        it was measured going wrong: `validate tests/screens/b` took the
        destination from 3 to 1 exactly as the single-file form did.
        """
        _run(project, ["tests"], monkeypatch, capsys)
        assert _installed(project) == ALL_THREE

        _run(project, ["tests/screens/b"], monkeypatch, capsys)

        assert _installed(project) == ALL_THREE

    def test_the_narrowed_run_says_what_it_did_not_do(
            self, project, monkeypatch, capsys):
        _run(project, ["tests"], monkeypatch, capsys)

        _, out = _run(project, ["tests/screens/b"], monkeypatch, capsys)

        assert "partial run — stale files left in place" in out
        assert "covered 1 of 3 declared test(s)" in out

    def test_a_narrowed_run_still_installs_what_it_was_given(
            self, project, monkeypatch, capsys):
        """Not a no-op: the file that WAS passed is still written."""
        _run(project, ["tests"], monkeypatch, capsys)
        target = project / "GeneratedTests" / "beta.test.json"
        target.write_text("{}", encoding="utf-8")

        _run(project, ["tests/screens/b"], monkeypatch, capsys)

        assert json.loads(target.read_text(encoding="utf-8"))["cases"]


class TestAFullSyncIsUnchanged:
    """The baseline every lane already runs. If this moves, they all move."""

    def test_it_still_removes_a_test_whose_source_is_gone(
            self, project, monkeypatch, capsys):
        """The half a "just stop cleaning" fix would fail.

        This is what the clean exists for, and it is the only thing that
        distinguishes the fix from a no-op — the ticket asked for it by
        name.
        """
        _run(project, ["tests"], monkeypatch, capsys)
        (project / "tests" / "screens" / "b" / "beta.test.json").unlink()

        _, out = _run(project, ["tests"], monkeypatch, capsys)

        assert _installed(project) == ["alpha.test.json", "alpha2.test.json"]
        assert "partial run" not in out
        # `cleaned` counts the WIPE, not the net loss: all three were
        # removed and two rewritten. That is why `cleaned 126` beside
        # `Installed 2` did not read as alarming — on a healthy run the
        # number equals the destination size, so a catastrophic one looks
        # like a large project. Pinned as a fact about the word, since the
        # fix deliberately did not change it.
        assert "(cleaned 3 stale)" in out

    def test_it_prints_nothing_new(self, project, monkeypatch, capsys):
        """Silent on the full-sync path: the new line is conditional, so a
        run that syncs everything is byte-identical to before."""
        _, out = _run(project, ["tests"], monkeypatch, capsys)

        assert "partial run" not in out
        assert "left in place" not in out

    def test_naming_every_file_is_a_full_sync_too(
            self, project, monkeypatch, capsys):
        """The set is compared, not the shape of the arguments. Someone who
        passes all three by name has given the same information as someone
        who passed the directory, and must get the same behaviour."""
        _run(project, ["tests"], monkeypatch, capsys)
        (project / "tests" / "screens" / "b" / "beta.test.json").unlink()

        _, out = _run(project,
                      ["tests/screens/a/alpha.test.json",
                       "tests/screens/a/alpha2.test.json"],
                      monkeypatch, capsys)

        assert "partial run" not in out
        assert _installed(project) == ["alpha.test.json", "alpha2.test.json"]


class TestWhenTheFullSetCannotBeEstablished:
    def test_an_absent_test_directory_declines_the_clean(
            self, tmp_path, monkeypatch, capsys):
        """"Cannot tell" is not "nothing to cover". A run that does not know
        what the full set is must not delete on the strength of not knowing
        — and it has to say which declaration would turn the clean on."""
        proj = tmp_path / "proj"
        (proj / "elsewhere").mkdir(parents=True)
        (proj / "elsewhere" / "alpha.test.json").write_text(
            json.dumps(_doc("alpha")), encoding="utf-8")
        (proj / "jui.config.json").write_text(json.dumps({
            "test": {"install": {"ios": {"dir": "GeneratedTests"}}}}),
            encoding="utf-8")
        _run(proj, ["elsewhere"], monkeypatch, capsys)
        stale = proj / "GeneratedTests" / "gone.test.json"
        stale.write_text("{}", encoding="utf-8")

        _, out = _run(proj, ["elsewhere"], monkeypatch, capsys)

        assert stale.exists()
        assert "no tests/ under" in out
        assert "test.testDir" in out

    def test_declaring_it_turns_the_clean_back_on(
            self, tmp_path, monkeypatch, capsys):
        """The control for the arm above: the same tree, one declaration,
        and the clean runs. Without this, "declines the clean" and "the
        clean is broken here" are the same result."""
        proj = tmp_path / "proj"
        (proj / "elsewhere").mkdir(parents=True)
        (proj / "elsewhere" / "alpha.test.json").write_text(
            json.dumps(_doc("alpha")), encoding="utf-8")
        (proj / "jui.config.json").write_text(json.dumps({
            "test": {"testDir": "elsewhere",
                     "install": {"ios": {"dir": "GeneratedTests"}}}}),
            encoding="utf-8")
        _run(proj, ["elsewhere"], monkeypatch, capsys)
        stale = proj / "GeneratedTests" / "gone.test.json"
        stale.write_text("{}", encoding="utf-8")

        _, out = _run(proj, ["elsewhere"], monkeypatch, capsys)

        assert not stale.exists()
        assert "partial run" not in out


class TestTheMediaWipeIsNotGatedByThis:
    """`media` comes from `test.mediaDir` in config, never from the command
    line, so narrowing the arguments cannot narrow it — it is a full sync on
    every run. Making the two symmetrical "for safety" would silently stop
    cleaning media a project really did delete, so the asymmetry is measured
    rather than assumed."""

    def _partial(self, tmp_path):
        """A destination holding BOTH a stale test and a stale media file.

        The stale test is not decoration. The first version of this fixture
        had only the media file, so `report.removed == 0` below was an
        assertion that could not fail — nothing was there to remove — and
        restoring the bug left it green. It is the shape this whole file is
        about, one level down: an assertion whose subject does not exist.
        """
        src = tmp_path / "a.test.json"
        src.write_text(json.dumps(_doc("a")), encoding="utf-8")
        ios = tmp_path / "ios"
        (ios / "media").mkdir(parents=True)
        stale_test = ios / "was_installed_earlier.test.json"
        stale_test.write_text("{}", encoding="utf-8")
        stale_media = ios / "media" / "gone.mp4"
        stale_media.write_bytes(b"old")
        return src, ios, stale_test, stale_media

    def test_media_is_still_cleaned_on_a_partial_run(self, tmp_path):
        src, ios, _, stale_media = self._partial(tmp_path)

        report = flatten_install([src], [("ios", ios)], clean=False)

        assert not stale_media.exists()
        assert report.media_removed == 1

    def test_the_test_wipe_is_the_one_that_stands_down(self, tmp_path):
        """The other half, at the level the flag lives on.

        `clean=False` reaching `flatten_install` and being honoured there is
        pinned here rather than only through `validate`, so a change inside
        the installer cannot be green on the strength of the caller.
        """
        src, ios, stale_test, _ = self._partial(tmp_path)

        report = flatten_install([src], [("ios", ios)], clean=False)

        assert stale_test.exists()
        assert report.removed == 0
        assert report.clean_skipped

    def test_the_same_fixture_loses_the_stale_test_on_a_full_sync(
            self, tmp_path):
        """The control. Without it, "the stale test survived" and "this
        installer never removes anything" are the same result."""
        src, ios, stale_test, _ = self._partial(tmp_path)

        report = flatten_install([src], [("ios", ios)], clean=True)

        assert not stale_test.exists()
        assert report.removed == 1
        assert not report.clean_skipped
