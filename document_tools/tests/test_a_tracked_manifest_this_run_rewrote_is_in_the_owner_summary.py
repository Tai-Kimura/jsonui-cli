"""Regression: doc-outside-writes-summary-omits-tracked-manifest.

The outside-writes summary — "0 tracked file(s) differ from the index …
nothing to review" — was computed over the DIRECTORIES this run wrote
outside `-o`, while the same run also rewrote `.jsonui-cli/generation-
manifest.json` under every root it recorded into. A manifest is a single
file under no listed directory, so it was structurally outside that
denominator; and the note beside `Manifest updated:` spoke only for the
untracked and the ignored cases. The one combination that costs the owning
lane a review — tracked, and now different — was the one that said nothing.
Measured 2026-09-17 on a four-app site: two tracked manifests moved
(`recordedAt`, `apps`, `leftoversOutsideScanned`, `elsewhere`) under a
summary that said there was nothing to review.

These arms drive the generator end to end against a real repository, with
the doc tree in the reported shape (tracked, every rewrite byte-identical),
so the summary has exactly one reason left to say "differ": the manifest.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli import reproducible  # noqa: E402
from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402

MANIFEST = Path(".jsonui-cli") / "generation-manifest.json"


def _spec(name: str) -> str:
    return json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": name, "name": name.upper(), "displayName": name.upper(),
                     "description": "d."},
        "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                      "layout": {"root": "root", "children": []}}})


def _test_json() -> str:
    return json.dumps({
        "type": "screen", "platform": "ios", "source": {"layout": "s"},
        "metadata": {"name": "s", "description": "d"},
        "cases": [{"name": "o", "description": "o",
                   "steps": [{"action": "tap", "id": "x"}]}]})


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), "-c", "commit.gpgsign=false",
                        "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
                       check=True, capture_output=True, text=True)
    return r.stdout


def _md5(path: Path) -> str:
    import hashlib
    return hashlib.md5(path.read_bytes()).hexdigest()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """One app root that is a git repository: a committed spec under `docs/`
    (so the doc tree is TRACKED and its regenerated pages are untracked
    newcomers — the reported shape, 0 differing) and, after the first run,
    a committed generation manifest."""
    root = tmp_path / "app"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "s.test.json").write_text(_test_json(), encoding="utf-8")
    (root / "docs" / "screens" / "json").mkdir(parents=True)
    (root / "docs" / "screens" / "json" / "one.spec.json").write_text(_spec("one"), encoding="utf-8")
    (root / "jui.config.json").write_text(
        json.dumps({"spec_directory": "docs/screens/json"}), encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "seed")
    monkeypatch.chdir(root)
    # One instant for every run in the arm: with the clock pinned, a second
    # run over identical inputs writes an identical manifest, which is what
    # lets the control arm mean "byte-identical" rather than "same second".
    monkeypatch.setattr(reproducible, "_pinned",
                        lambda: datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc))
    return root


def _run(root: Path) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen.generate_html_directory(
            Path("tests"), Path("out"), "T",
            apps=[{"name": "app", "docs_path": str((root / "docs").resolve())}],
            project_root=root,
            manifest_roots=[{"app": "app", "root": str(root), "docs": str(root / "docs")}])
    return buf.getvalue()


def _settle(root: Path, *, manifest: bool = True) -> str:
    """Runs and commits until a further identical run writes identical bytes.

    The manifest records facts about its own surroundings that move as the
    fixture is built — `gitTrackedDirectories` once the doc tree is
    committed, `manifestIsGitTracked` once the manifest itself is — so each
    run here is followed by the commit that changes the next run's answer,
    and the last run happens after nothing is left to change. The manifest
    is committed unless the arm wants it left untracked. Returns its md5.
    """
    _run(root)
    assert (root / MANIFEST).is_file()
    _git(root, "add", "docs")
    _git(root, "commit", "-q", "-m", "doc tree")
    for msg in ("manifest", "settled"):
        _run(root)
        _git(root, "add", "docs")
        if manifest:
            _git(root, "add", str(MANIFEST))
        _git(root, "commit", "-q", "--allow-empty", "-m", msg)
    return _md5(root / MANIFEST)


def test_a_tracked_manifest_that_now_differs_is_not_under_nothing_to_review(repo):
    before = _settle(repo)
    # A second spec: the next run records one more page, so the manifest's
    # content — not just its stamp — moves while every doc page it rewrites
    # is byte-identical (the committed spec) or an untracked newcomer.
    (repo / "docs" / "screens" / "json" / "two.spec.json").write_text(_spec("two"), encoding="utf-8")
    out = _run(repo)
    # The fixture is the reported shape, asserted before the claim: git says
    # the manifest is tracked and differs, and the doc tree has no differing
    # tracked file.
    assert _md5(repo / MANIFEST) != before, "the manifest did not move; the arm is vacuous"
    assert _git(repo, "status", "--porcelain", "--untracked-files=no", "--",
                str(MANIFEST)).strip().startswith("M"), _git(repo, "status", "--porcelain")
    assert "GIT-TRACKED" in out, out
    assert "0 now differ from the index" in out, "the doc tree must be the byte-identical shape"
    assert "nothing to review" not in out, out
    # The manifest is named next to the word that measured it, so the owner
    # can find the file `git status` will show them.
    assert "generation-manifest.json" in out and "differ" in out, out
    assert "1 tracked file(s) now differ" in out, out


def test_a_tracked_manifest_rewritten_byte_identical_is_nothing_to_review(repo):
    """The control: same inputs, pinned clock → identical bytes → the summary
    may still say nothing to review, and the manifest is counted as 0."""
    before = _settle(repo)
    out = _run(repo)
    assert _md5(repo / MANIFEST) == before, "the control lost its shape: the manifest moved"
    assert "GIT-TRACKED" in out, out
    assert "nothing to review" in out, out
    assert "0 tracked file(s) differ" in out, out
    # The scope is said: what the zero was measured over, both populations.
    assert "0 generation manifest(s)" in out, out
    assert "generation manifest(s) this run wrote are GIT-TRACKED" not in out, (
        "an identical rewrite is in the count, not on a line of its own")


def test_an_untracked_manifest_is_not_counted_as_differing(repo):
    """Never committed: the existing NOTE says it is not tracked, and the
    summary's denominator does not gain a file git will never show."""
    _settle(repo, manifest=False)  # the manifest stays untracked
    (repo / "docs" / "screens" / "json" / "two.spec.json").write_text(_spec("two"), encoding="utf-8")
    out = _run(repo)
    assert "is NOT git-tracked here" in out, out
    assert "1 tracked file(s) now differ" not in out, out
