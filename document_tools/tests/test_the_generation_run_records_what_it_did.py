"""Regression: doc-the-generation-run-leaves-no-persistent-record-of-what-it-did.

`jui build` has recorded which version wrote each generated file since
2026-09-03 (`.jsonui-cli/generation-manifest.json`). `jsonui-doc generate
html` wrote 1061 files on one face and recorded none of them, so answering
"which version generated this page" cost four separate measurements: the
page's own stamp (a time, no version), the bootstrap landing time, the shared
checkout's reflog, and an enumeration of every generator reachable on the
machine — a first sweep of which found one copy where there were five.

THREE THINGS were being lost the same way, and the arms below cover all
three, because fixing one and leaving the others is the asymmetry the ticket
is about:

  A. the pages the run wrote          — nothing recorded them
  B. the leftovers the run detected   — `_report_stale_pages` returns them and
                                        the caller discarded the return value;
                                        64 unreachable pages shipped on one face
  C. the directories written outside -o — `_report_writes_outside_output`
                                        returned None at all, and had just been
                                        enriched with git-tracked counts, so the
                                        value of what scrolled away went UP

⚠️ The last two are not "the return value was dropped". `C` had no return
value to drop and has the same defect, which is what shows the shared
property is PERSISTENCE rather than a discarded result.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402


def _manifest(root: Path) -> dict:
    path = root / ".jsonui-cli" / "generation-manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """A project root with two written pages the run reports."""
    root = tmp_path / "face"
    out = root / "docs" / "html"
    (out / "client" / "unit").mkdir(parents=True)
    written = []
    for name in ("client/unit/AppInfoViewModel.html", "index.html"):
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("<html></html>", encoding="utf-8")
        written.append(p.resolve())
    monkeypatch.setattr(gen, "get_written_pages", lambda: set(written))
    return root, out


def test_a_the_pages_this_run_wrote_are_recorded(project):
    root, out = project
    gen._record_generation_manifest(out, root, [], {})
    files = _manifest(root).get("files") or {}
    assert len(files) == 2, "both written pages must be recorded"
    assert all(e["generatedBy"] == "jsonui-doc generate html" for e in files.values())
    # Keys are project-relative, so the record reads the same from any cwd.
    assert "docs/html/index.html" in files


def test_b_the_leftovers_it_found_survive_the_run(project):
    """The 64-page finding must outlive the terminal it was printed to."""
    root, out = project
    stale = [out / "client" / "unit" / f"Gone{i}.html" for i in range(25)]
    gen._record_generation_manifest(out, root, stale, {})
    run = (_manifest(root).get("summary") or {}).get("run") or {}
    assert run.get("leftovers") == 25
    assert len(run.get("leftoverPaths") or []) == 20
    assert run.get("leftoverPathsNote") == "first 20 of 25", (
        "a list cut at 20 reads as the whole list unless it says otherwise")


def test_c_the_writes_outside_output_survive_too(project):
    """C has no return value to discard, and the same defect. Same fix."""
    root, out = project
    outside = {
        "directories": ["/other/lane/docs"],
        "gitTrackedDirectories": {"/other/lane/docs": 7},
        "uncheckable": [],
    }
    gen._record_generation_manifest(out, root, [], outside)
    run = (_manifest(root).get("summary") or {}).get("run") or {}
    assert run.get("outsideOutput", {}).get("gitTrackedDirectories") == {"/other/lane/docs": 7}


def test_a_quiet_run_records_only_the_facts_that_are_always_true(project):
    """Nothing observed must not look the same as something observed.

    ⚠️ Changed 2026-09-09: the run block is now always written, because
    "is this record visible to anyone else" is a fact about EVERY run, not
    only about runs that found something. The absence of `leftovers` is what
    carries "nothing was found".
    """
    root, out = project
    gen._record_generation_manifest(out, root, [], {})
    run = (_manifest(root).get("summary") or {}).get("run") or {}
    assert "manifestIsGitTracked" in run
    assert "leftovers" not in run and "outsideOutput" not in run


def test_the_git_sense_of_tracked_is_spelled_differently(project):
    """🚨 One file must not carry two meanings of `tracked`.

    `summary.tracked` and `summary.trackedByDirectory` count files the
    MANIFEST tracks. The outside-writes block counts files GIT tracks. Both
    land in one JSON, and the reader who hit the collision was reading that
    JSON — not the source, and not any printed line. So the fix has to be in
    the key, which is why a wording change alone would not have reached them.
    """
    root, out = project
    gen._record_generation_manifest(
        out, root, [], {"directories": ["/x"], "gitTrackedDirectories": {"/x": 3},
                        "uncheckable": []})
    summary = _manifest(root).get("summary") or {}
    assert "tracked" in summary, "the manifest sense stays where it was"
    outside = (summary.get("run") or {}).get("outsideOutput") or {}
    assert "gitTrackedDirectories" in outside
    assert "trackedDirectories" not in outside, "the colliding spelling is gone"


def test_it_records_whether_the_record_itself_is_visible(project):
    """The gap the admin face reported: a record nothing else can see."""
    root, out = project
    gen._record_generation_manifest(out, root, [], {})
    run = (_manifest(root).get("summary") or {}).get("run") or {}
    # tmp_path is not a repository, so the honest answer is "cannot tell".
    assert run.get("manifestIsGitTracked") is None


def test_not_tracked_and_cannot_tell_do_not_print_the_same(project, monkeypatch, capsys):
    """Three states, because two of them make opposite claims."""
    root, out = project

    monkeypatch.setattr(gen, "_git_tracks_file", lambda p, cwd: False)
    gen._record_generation_manifest(out, root, [], {})
    not_tracked = capsys.readouterr().out
    assert "NOT git-tracked" in not_tracked
    assert "readable in place" in not_tracked, (
        "untracked is not unusable — it is unusable AS A DIFF")

    monkeypatch.setattr(gen, "_git_tracks_file", lambda p, cwd: None)
    gen._record_generation_manifest(out, root, [], {})
    unknown = capsys.readouterr().out
    assert "could not tell" in unknown
    assert "not a statement that it is untracked" in unknown
    assert not_tracked != unknown

    monkeypatch.setattr(gen, "_git_tracks_file", lambda p, cwd: True)
    gen._record_generation_manifest(out, root, [], {})
    assert capsys.readouterr().out == "", "the common case stays quiet"


def test_a_directory_that_does_not_exist_yet_is_not_reported_as_untracked(tmp_path):
    """The first draft of the helper answered False when git could not look.

    On the run that CREATES the manifest, its directory does not exist yet.
    Running git there fails for a reason that says nothing about tracking,
    and a confident "not tracked" is the wrong half of the three states.
    """
    missing = tmp_path / "nowhere"
    assert gen._git_tracks_file(missing / "x.json", missing) is None


def test_without_shared_core_it_says_what_it_skipped(project, monkeypatch, capsys):
    """The skip is announced, not silent — `shared_core.load`'s own contract.

    ⚠️ This is the population the fix does not reach: `shared/` is not in the
    pip distribution (`include = ['jsonui_doc_cli*']`), so a face that
    installed the doc tool from a bare pip lands here every run. The notice is
    the only thing that tells it the manifest is not merely empty.
    """
    root, out = project
    from jsonui_doc_cli import shared_core
    monkeypatch.setattr(shared_core, "load", lambda name: None)
    gen._record_generation_manifest(out, root, [], {})
    said = capsys.readouterr().out
    assert "shared/core/generation_manifest.py" in said
    assert not (root / ".jsonui-cli").exists(), "it must not write half a record"


def test_without_a_project_root_it_says_that_instead(project, capsys):
    """A different absence, kept apart because it calls for a different fix."""
    _root, out = project
    gen._record_generation_manifest(out, None, [], {})
    said = capsys.readouterr().out
    assert "no project root" in said
    assert "not a statement that there was nothing to record" in said


def test_the_notice_promises_nothing_about_gates(project, monkeypatch, capsys):
    """🚫 The trap closed in build_cmd.py this morning, not rebuilt here.

    That docstring reasoned from a tally that did not exist ("not counted
    toward the zero-warnings gate"). A new printer is exactly when that gets
    written again, so the notice describes what it did and claims nothing
    about what any check will do with it.
    """
    root, out = project
    from jsonui_doc_cli import shared_core
    monkeypatch.setattr(shared_core, "load", lambda name: None)
    gen._record_generation_manifest(out, root, [], {})
    said = capsys.readouterr().out.lower()
    for promise in ("gate", "exit", "warning", "does not count", "safe to ignore"):
        assert promise not in said, f"the notice must not promise {promise!r}"
