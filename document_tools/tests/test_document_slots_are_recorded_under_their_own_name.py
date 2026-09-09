"""Regression: `collisions: 0` beside two SHARED SLOT lines, from one run.

The face was reading two quantities under one word. `summary.collisions` is
the manifest's own count — keys whose spellings normalised onto one entry —
and it was 0, truthfully. The SHARED SLOT lines came from the document-slot
report, whose return value the call site discarded, so the only place that
number existed was the terminal. Two counters, two meanings, one reader, and
no record of the second.

Now the slot report's facts land in the run block under their own key,
`documentSlots`, and `collisions` keeps the meaning the manifest already gave
it. The arms pin the SEPARATION — both numbers present, different keys — not
agreement, because the two are not supposed to agree.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
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
    root = tmp_path / "face"
    out = root / "docs" / "html"
    out.mkdir(parents=True)
    page = out / "index.html"
    page.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(gen, "get_written_pages", lambda: {page.resolve()})
    return root, out


def test_the_slot_report_is_recorded_under_its_own_key(project):
    root, out = project
    gen._record_generation_manifest(out, root, [], {}, slots={
        "paths": 5, "declarations": 7, "sharedPaths": 1,
        "sharedPathKeys": ["user/docs/x.html"]})
    summary = _manifest(root)["summary"]
    run = summary["run"]
    assert run["documentSlots"]["sharedPaths"] == 1
    assert run["documentSlots"]["sharedPathKeys"] == ["user/docs/x.html"]
    # The manifest's own word keeps the manifest's own meaning, and the run
    # block does not borrow it.
    assert "collisions" in summary
    assert "collisions" not in run


def test_zero_shared_is_recorded_as_having_looked(project):
    root, out = project
    gen._record_generation_manifest(out, root, [], {}, slots={
        "paths": 5, "declarations": 5, "sharedPaths": 0, "sharedPathKeys": []})
    assert _manifest(root)["summary"]["run"]["documentSlots"]["sharedPaths"] == 0


def test_no_report_means_no_key(project):
    root, out = project
    gen._record_generation_manifest(out, root, [], {})
    assert "documentSlots" not in _manifest(root)["summary"]["run"]


def test_the_faces_observation_end_to_end(tmp_path):
    """Two tests in one app name one page.

    The terminal says SHARED SLOT; the manifest says `collisions: 0`; both are
    true. What was missing is the third line — `documentSlots.sharedPaths: 1`
    in the same file — which is what lets a reader see two quantities instead
    of one number contradicting itself.
    """
    root = tmp_path
    tests = root / "tests"
    tests.mkdir()
    doc = "docs/user/screens/html/login.html"
    for name in ("a", "b"):
        (tests / f"{name}.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios",
            "source": {"layout": "s", "document": doc},
            "metadata": {"name": f"{name} test", "description": "d"},
            "cases": [{"name": "c", "description": "c",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
    page = root / doc
    page.parent.mkdir(parents=True)
    page.write_text("<html><head><title>Login</title></head>"
                    "<body>login</body></html>", encoding="utf-8")
    (root / "docs" / "user" / "screens" / "json").mkdir(parents=True)
    out = root / "out"
    out.mkdir()
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen.generate_html_directory(
            tests, out, "T",
            apps=[{"name": "user", "docs_path": str(root / "docs" / "user")}],
            project_root=root)
    log = buf.getvalue()
    assert "SHARED SLOT" in log, log
    assert "2 test(s) resolve to this page" in log, log
    summary = _manifest(root)["summary"]
    assert summary["collisions"] == 0
    assert summary["run"]["documentSlots"]["sharedPaths"] == 1
    assert summary["run"]["documentSlots"]["declarations"] == 2
