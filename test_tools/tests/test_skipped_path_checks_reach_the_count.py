"""A reported `Warnings: 0` says whether the path check actually ran.

Faces collect "0 findings" from every screen to decide when the declared-path
check can move from warning to error. `0` means two different things — the
check ran and found nothing, or the check declined because the directory it
resolves against is not on disk — and one project was in a position to
report zero with TWO kinds declined.

THE CONTROL IS THE POINT OF THIS FILE. A skip has to actually suppress a
finding, or there is nothing to disclose and a test asserting the disclosure
would pass over an empty fixture. Measured on one test file declaring a
missing layout AND a missing document:

    both directories present    Warnings: 2
    layouts_directory absent    Warnings: 1
    both absent                 Warnings: 0

Same file, same declarations. The number moves with the directories.

The `[NOTE]` line already said which kinds declined, several lines up and on
the other side of the mock-contract block and a divider. A face reads the
summary line, not the transcript — so the denominator goes where the count
is.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import cli
from jsonui_test_cli.validation.declared_paths import (
    PATH_KINDS, config_key_for, skipped_kinds,
)

#: One declaration naming a file for each kind, both missing on purpose.
_SOURCE = {"layout": "nope.json", "document": "alsonope.json"}


def _project(tmp_path, present):
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "jui.config.json").write_text("{}", encoding="utf-8")
    for kind in present:
        (tmp_path / PATH_KINDS[kind][1]).mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests" / "s.test.json").write_text(json.dumps({
        "type": "screen", "source": dict(_SOURCE),
        "metadata": {"name": "s", "description": "d"},
        "cases": [{"name": "c", "description": "d",
                   "steps": [{"assert": "visible", "id": "root"}]}],
    }), encoding="utf-8")
    return tmp_path


def _run(tmp_path, monkeypatch, capsys, present):
    monkeypatch.chdir(_project(tmp_path, present))
    rc = cli.cmd_validate(argparse.Namespace(
        files=["tests"], verbose=False, quiet=False, config=None,
        no_mock_check=True, no_install=True, strict=False))
    out = capsys.readouterr().out
    [summary] = [l for l in out.splitlines() if l.startswith("Files:")]
    return rc, summary, out


class TestTheControl:
    """Without these, everything below passes over a fixture that never
    skipped anything — the failure mode that has cost this repository four
    empty probes in one day."""

    @pytest.mark.parametrize("present,warnings", [
        (("layout", "document"), "Warnings: 2"),
        (("document",), "Warnings: 1"),
        ((), "Warnings: 0"),
    ])
    def test_the_count_moves_with_the_directories(
            self, tmp_path, monkeypatch, capsys, present, warnings):
        _, summary, _ = _run(tmp_path, monkeypatch, capsys, present)

        assert warnings in summary, summary

    def test_the_fixture_really_declines(self, tmp_path, monkeypatch, capsys):
        _run(tmp_path, monkeypatch, capsys, ())

        assert set(skipped_kinds()) == set(PATH_KINDS)


class TestTheDenominatorIsOnTheCountLine:
    def test_a_declined_kind_is_named_beside_the_count(
            self, tmp_path, monkeypatch, capsys):
        _, summary, _ = _run(tmp_path, monkeypatch, capsys, ("document",))

        assert "Warnings: 1" in summary
        assert "Path checks skipped: layout" in summary, summary

    def test_every_declined_kind_is_named(self, tmp_path, monkeypatch, capsys):
        """Named rather than counted: "2 kinds skipped" leaves the reader
        unable to decide what their own zero covers."""
        _, summary, _ = _run(tmp_path, monkeypatch, capsys, ())

        for kind in PATH_KINDS:
            assert kind in summary, summary

    def test_nothing_is_added_when_every_kind_ran(
            self, tmp_path, monkeypatch, capsys):
        """A standing line is the one the next finding hides behind, so a
        healthy run gains no field and no line."""
        _, summary, out = _run(tmp_path, monkeypatch, capsys,
                               ("layout", "document"))

        assert "Path checks skipped" not in out
        assert summary == "Files: 1, Errors: 0, Warnings: 2", summary

    def test_the_exit_code_is_untouched(self, tmp_path, monkeypatch, capsys):
        """Visibility, not weight. These are warnings by design until each
        project has measured its own count down to zero."""
        # Two projects, not one directory reused: the second `_run` would
        # otherwise build over the first and measure a tree that is neither.
        skipped, _, _ = _run(tmp_path / "a", monkeypatch, capsys, ())
        ran, _, _ = _run(tmp_path / "b", monkeypatch, capsys,
                         ("layout", "document"))

        assert skipped == ran == 0


class TestTheKindTableHasOneDeclaration:
    """The note naming the absent directory used to spell
    `'layouts_directory' if kind == 'layout' else 'spec_directory'`, which
    answers `spec_directory` for every kind that is not `layout` — including
    a third one nobody has added yet. Wrong silently, and only for the case
    that does not exist."""

    @pytest.mark.parametrize("kind", sorted(PATH_KINDS))
    def test_every_kind_can_name_its_config_key(self, kind):
        assert config_key_for(kind) == PATH_KINDS[kind][0]

    def test_the_note_names_the_key_for_the_kind_that_declined(
            self, tmp_path, monkeypatch, capsys):
        _, _, out = _run(tmp_path, monkeypatch, capsys, ("document",))

        [note] = [l for l in out.splitlines()
                  if l.startswith("[NOTE]") and "layout" in l]
        assert config_key_for("layout") in note, note
        assert config_key_for("document") not in note, note

    def test_a_third_kind_names_its_own_key(self, tmp_path, monkeypatch,
                                            capsys):
        """The arm that can tell the two implementations apart.

        Red-checked and it came back GREEN: restoring the ternary broke
        nothing, because `layout -> layouts_directory` and `document ->
        spec_directory` are what both spellings answer. Every test above
        passes on the version this change replaced, so none of them was
        protecting it — the defect only exists for a kind that does not
        exist yet, which is exactly the kind of hole that ships.

        So the third kind is registered here. Under the ternary this note
        says `spec_directory`, silently and confidently.
        """
        monkeypatch.setitem(PATH_KINDS, "asset",
                            ("assets_directory", "docs/assets"))

        # The note itself, not the loop: a kind only reaches `skipped_kinds()`
        # when something resolves against it, and nothing resolves an
        # `asset`. Driving the loop would measure that absence instead.
        note = cli._skipped_path_note("asset", tmp_path)

        assert "assets_directory" in note, note
        assert "spec_directory" not in note, note
