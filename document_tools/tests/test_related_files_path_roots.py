"""`relatedFiles[].path` is tried against every declared boundary above it.

The first version of this check stopped at the NEAREST ancestor holding a
`jui.config.json`. In a multi-app repository that is the app's config, not
the repository root, and a consumer measured the cost immediately: 35
warnings on a project whose 26 unique paths all resolve. Their spec
validation had been at `Warnings: 0` and is kept there deliberately, so 35
permanent findings is also the state in which a real one is invisible.

The reporter's evidence for the shape of the bug is the part worth keeping.
One warning named a repository class under an application tree that is a
SIBLING of the docs tree at the repository root — a path that cannot exist
under either candidate the message listed. **The check was searching only
places the file could not be and reporting that it was nowhere.** The
message printing its candidate roots is what made that a one-step
diagnosis; the fix keeps that.

Why the root cannot be derived from the app: the docs tree lives in the
parent repository while the application trees are submodules beside it, so a
spec has to name files in both, and the only base that spells both without
`../` chains is the repository root.

The negative arm is not optional here. Widening the candidate set silences
findings by construction, so "the false positives are gone" and "the check
is gone" produce the same `Warnings: 0` — and only a path that genuinely
does not exist tells them apart. The reporter asked for exactly this.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonui_doc_cli.spec_doc.validator import SpecValidator


def _spec(related):
    """A spec that is valid apart from whatever `related` says.

    The whole document has to pass, not just the section under test: an
    invalid `type`/`version`/`structure` makes the validator stop before it
    reaches `relatedFiles`, and every assertion of the form "no path
    warnings" then passes for that reason instead. Measured — the first
    draft of this file was green with the check unreachable.
    """
    return {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"name": "Account", "displayName": "Account",
                     "description": "d", "layoutFile": "account.json"},
        "structure": {"components": []},
        "relatedFiles": [{"type": "Repository", "path": p} for p in related],
    }


@pytest.fixture
def repo(tmp_path):
    """The reported layout: repository root, an app config below it, and a
    sibling tree the app config can never reach."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "jui.config.json").write_text("{}", encoding="utf-8")

    specs = tmp_path / "docs" / "user" / "screens" / "json"
    specs.mkdir(parents=True)
    (tmp_path / "docs" / "user" / "jui.config.json").write_text(
        "{}", encoding="utf-8")

    layouts = tmp_path / "docs" / "user" / "screens" / "layouts"
    layouts.mkdir(parents=True)
    (layouts / "account.json").write_text("{}", encoding="utf-8")

    # A submodule beside `docs/`, reachable only from the repository root.
    repo_side = tmp_path / "user" / "src" / "repository"
    repo_side.mkdir(parents=True)
    (repo_side / "AccountRepository.ts").write_text("", encoding="utf-8")

    return tmp_path


def _validate(repo, related):
    path = repo / "docs" / "user" / "screens" / "json" / "account.spec.json"
    path.write_text(json.dumps(_spec(related)), encoding="utf-8")
    return SpecValidator().validate_file(str(path))


def _path_warnings(result):
    return [m for m in result.warnings if "does not exist" in m.message]


def test_the_control_document_is_otherwise_clean(repo):
    """The control for the control. Every "no path warnings" assertion below
    would also hold if the validator stopped before `relatedFiles`, which is
    exactly what the first draft of this file measured."""
    result = _validate(repo, ["docs/user/screens/layouts/account.json"])

    assert result.errors == [], [m.message for m in result.errors]
    assert result.warnings == []


def test_a_repository_root_relative_path_resolves(repo):
    """The reported case. Both spellings in one spec, because that is what
    the layout forces — and neither is reachable from the app config."""
    result = _validate(repo, [
        "docs/user/screens/layouts/account.json",
        "user/src/repository/AccountRepository.ts",
    ])

    assert _path_warnings(result) == []


def test_a_path_that_exists_nowhere_is_still_reported(repo):
    """The negative arm. Widening the candidates silences findings by
    construction, so without this "the false positives are gone" and "the
    check is gone" are the same observation."""
    result = _validate(repo, ["user/src/repository/Missing.ts"])

    [warning] = _path_warnings(result)
    assert "Missing.ts" in warning.message


def test_the_two_are_separated_in_one_run(repo):
    """Both arms together: the check is neither silent nor indiscriminate."""
    result = _validate(repo, [
        "docs/user/screens/layouts/account.json",   # resolves
        "user/src/repository/AccountRepository.ts",  # resolves
        "docs/user/screens/layouts/gone.json",       # does not
    ])

    [warning] = _path_warnings(result)
    assert "gone.json" in warning.message


@pytest.mark.parametrize("relative_to", ["spec", "app", "repo"])
def test_a_path_near_one_candidate_but_absent_still_warns(repo, relative_to):
    """One candidate implemented and the others not would pass the first
    test on whichever spelling that candidate happens to cover. A miss is
    placed beside each root in turn so the arms cannot cover for each other.
    """
    near = {
        "spec": "sibling-of-the-spec.json",
        "app": "screens/layouts/absent.json",
        "repo": "user/src/absent.ts",
    }[relative_to]

    result = _validate(repo, [near])

    assert len(_path_warnings(result)) == 1, relative_to


def test_the_spec_directory_is_still_a_candidate(repo):
    """Not a regression test for the fix — a guard on the root it replaced.
    Widening the set must not drop the narrow spellings that already
    worked."""
    beside = repo / "docs" / "user" / "screens" / "json" / "notes.md"
    beside.write_text("", encoding="utf-8")

    assert _path_warnings(_validate(repo, ["notes.md"])) == []


def test_the_message_names_the_roots_it_tried(repo):
    """The one thing that made this a one-step diagnosis: the reporter read
    the candidate list and saw `user/` was not reachable from any of them.
    A finding that does not say where it looked costs several rounds."""
    result = _validate(repo, ["user/src/repository/Missing.ts"])

    [warning] = _path_warnings(result)
    assert "looked under" in warning.message
    assert str(repo) in warning.message


class TestTheAscentStopsAtTheProject:
    """A neighbouring checkout is not a candidate root.

    Collecting every marker above the spec had no ceiling, so on a machine
    where the repository sits inside another checkout, the OUTER checkout's
    `.git` became a candidate and a path that exists only outside this
    project resolved. A consumer produced 43 such paths on one machine
    without contriving anything.

    The damage is that the check becomes machine-dependent: green at a
    desk, warning in CI, on a check scheduled to become an error. That
    arrives as "CI fails and I cannot reproduce it", which is the shape
    that costs the most to chase.
    """

    def _tree(self, tmp_path):
        outer = tmp_path / "outer"
        (outer / ".git").mkdir(parents=True)
        repo = outer / "repo"
        (repo / ".git").mkdir(parents=True)
        specs = repo / "docs" / "screens" / "json"
        specs.mkdir(parents=True)
        # exists ONLY above the repository under test
        (outer / "elsewhere.ts").write_text("x", encoding="utf-8")
        (repo / "inside.ts").write_text("x", encoding="utf-8")
        return outer, repo, specs

    def test_a_file_only_outside_the_repo_does_not_resolve(self, tmp_path):
        outer, repo, specs = self._tree(tmp_path)
        v = SpecValidator()
        v._spec_file_path = specs / "s.spec.json"
        roots = v._related_file_roots()
        assert outer not in roots, (
            "the enclosing checkout is not part of this project")
        assert repo in roots

    def test_a_file_inside_the_repo_still_resolves(self, tmp_path):
        # The control. Without it, "the outer root is gone" and "every root
        # is gone" are the same result, and the previous fix existed to add
        # the repository root.
        outer, repo, specs = self._tree(tmp_path)
        v = SpecValidator()
        v._spec_file_path = specs / "s.spec.json"
        roots = v._related_file_roots()
        assert any((r / "inside.ts").exists() for r in roots)
