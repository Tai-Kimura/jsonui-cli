"""Regression: the outside-writes report said things it had not measured.

Two defects in one printer (`_report_writes_outside_output`), both reported on
2026-09-10 by faces reading its output, and both the same shape — a word in
the output stronger than the measurement behind it:

  C2  ONE DIRECTORY, NAMED TWICE. The root scope records its docs directory
      as the run was given it (relative, when the input was); every `--app`
      records its docs path `.resolve()`d. A run pointed at an app that is
      also passed as `--app` — the ordinary shape for a face listing all of
      its apps — put one directory in the set in two spellings, and the
      manifest's `outsideOutput.directories` listed it twice.

  B1  "this run CHANGED files another lane owns" — printed from the number
      of files git TRACKS under the directory, which says nothing about
      whether a byte moved. On the reporting face every one of the 38 was
      rewritten identical and `git status` showed 0; the line said changed.

The arms pin the MEASUREMENT, not the wording. A wording change alone
("wrote" for "changed") would leave the number exactly as unmeasured.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402
from test_document_page_links_and_writes_outside_output import (  # noqa: E402
    COMPONENT_FILE, _component_spec, _screen_spec,
)


# --- C2: one directory, one entry ------------------------------------------

def test_one_directory_spelled_two_ways_is_named_once(tmp_path, monkeypatch, capsys):
    gen.reset_page_failures()
    real = (tmp_path / "docs" / "x").resolve()
    real.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gen, "_git_tracked_file_count", lambda d: 0)
    gen._written_outside_output.update({Path("docs/x"), real})
    # The baseline arm: both spellings really are in the set. Without this a
    # future normalisation at the writer would leave the test passing for a
    # reason it no longer exercises.
    assert len(gen._written_outside_output) == 2
    facts = gen._report_writes_outside_output(tmp_path / "out")
    assert facts["directories"] == [str(real)]
    assert "(1 directories)" in capsys.readouterr().out


def test_two_different_directories_are_still_two(tmp_path, monkeypatch, capsys):
    """The control: deduplication is by identity, not by shortening the list."""
    gen.reset_page_failures()
    for name in ("x", "y"):
        (tmp_path / "docs" / name).mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gen, "_git_tracked_file_count", lambda d: 0)
    gen._written_outside_output.update({Path("docs/x"), (tmp_path / "docs" / "y").resolve()})
    facts = gen._report_writes_outside_output(tmp_path / "out")
    assert len(facts["directories"]) == 2
    assert "(2 directories)" in capsys.readouterr().out


def test_the_reported_shape_a_run_pointed_at_an_app_it_also_lists(tmp_path, monkeypatch):
    """The shape the report describes: relative input, the same app as `--app`.

    The root pass records `<input>/../docs` as given and the app pass records
    the same directory resolved. Asserted in two steps on purpose — first that
    the run DID record both spellings (otherwise the fixture is not the shape
    and the second assertion is vacuous), then that the report names each
    real directory once.
    """
    root = tmp_path
    tests = root / "client" / "tests"
    tests.mkdir(parents=True)
    (tests / "s.test.json").write_text(json.dumps({
        "type": "screen", "platform": "ios", "source": {"layout": "s"},
        "metadata": {"name": "s", "description": "d"},
        "cases": [{"name": "opens", "description": "opens",
                   "steps": [{"action": "tap", "id": "x"}]}],
    }), encoding="utf-8")
    docs = root / "client" / "docs"
    (docs / "screens" / "json").mkdir(parents=True)
    (docs / "components" / "json").mkdir(parents=True)
    (docs / "screens" / "json" / "home.spec.json").write_text(
        json.dumps(_screen_spec("home", COMPONENT_FILE)), encoding="utf-8")
    (docs / "components" / "json" / COMPONENT_FILE).write_text(
        json.dumps(_component_spec()), encoding="utf-8")
    (root / "out").mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(gen, "_git_tracked_file_count", lambda d: 0)
    with redirect_stdout(io.StringIO()):
        gen.generate_html_directory(
            Path("client/tests"), Path("out"), "T",
            apps=[{"name": "client", "docs_path": str(docs.resolve())}])

    raw = set(gen._written_outside_output)
    spellings = {d.is_absolute() for d in raw}
    assert spellings == {True, False}, f"fixture lacks the shape: {sorted(map(str, raw))}"
    distinct = {d.resolve() for d in raw}
    assert len(raw) > len(distinct), "both spellings must be present for this arm to mean anything"

    facts = gen._report_writes_outside_output(Path("out"))
    listed = facts["directories"]
    assert len(listed) == len({Path(p).resolve() for p in listed}), listed
    assert len(listed) == len(distinct), (listed, sorted(map(str, distinct)))
