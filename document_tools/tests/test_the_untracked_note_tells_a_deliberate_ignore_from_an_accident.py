"""Regression: note-not-git-tracked-cannot-tell-a-deliberate-ignore-from-an-accident.

`ⓘ NOTE: … is NOT git-tracked here` printed one wording for two different
states: a manifest the face deliberately ignores (a rule it wrote) and one
that is merely untracked (an accident, maybe). The deliberate case printed
every run and never changed anyone's action; a reader who learns to skip it
skips the actionable one too. Triage measured one face holding both kinds
in a single run, so the two wordings must coexist in one run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402


def _manifest(root: Path) -> dict:
    return json.loads((root / ".jsonui-cli" / "generation-manifest.json").read_text(encoding="utf-8"))


def _repo(base: Path, name: str, ignore: bool) -> Path:
    root = base / name
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    if ignore:
        (root / ".gitignore").write_text(".jsonui-cli/\n", encoding="utf-8")
    return root


@pytest.fixture()
def out(tmp_path, monkeypatch):
    o = tmp_path / "out"; o.mkdir()
    monkeypatch.setattr(gen, "get_written_pages", lambda: set())
    return o


def test_one_run_with_both_kinds_prints_both_wordings(tmp_path, out, capsys):
    ignored = _repo(tmp_path, "ignored", ignore=True)
    plain = _repo(tmp_path, "plain", ignore=False)
    gen._record_generation_manifest(out, [{"app": "i", "root": ignored}, {"app": "p", "root": plain}], [], {})
    printed = capsys.readouterr().out
    assert "is ignored by this repository's .gitignore" in printed
    assert "is NOT git-tracked here" in printed
    assert _manifest(ignored)["summary"]["run"]["manifestIsGitIgnored"] is True
    assert _manifest(plain)["summary"]["run"]["manifestIsGitIgnored"] is False


def test_the_deliberate_case_says_where_the_record_lives_and_asks_nothing(tmp_path, out, capsys):
    ignored = _repo(tmp_path, "ignored", ignore=True)
    gen._record_generation_manifest(out, ignored, [], {})
    printed = capsys.readouterr().out
    # It still says the record is outside any diff — that is the fact a later
    # reader needs — but it no longer asks the face to decide anything.
    assert "outside `git status` and any diff" in printed
    assert "nothing to decide" in printed
    assert "cannot serve as evidence" not in printed


def test_a_tracked_manifest_prints_neither(tmp_path, out, capsys):
    root = _repo(tmp_path, "tracked", ignore=False)
    gen._record_generation_manifest(out, root, [], {})
    subprocess.run(["git", "-C", str(root), "add", "-f", ".jsonui-cli/generation-manifest.json"], check=True)
    capsys.readouterr()
    gen._record_generation_manifest(out, root, [], {})
    printed = capsys.readouterr().out
    assert "NOT git-tracked" not in printed and "is ignored by" not in printed
    run = _manifest(root)["summary"]["run"]
    assert run["manifestIsGitTracked"] is True and run["manifestIsGitIgnored"] is False


def test_outside_a_repository_neither_answer_is_invented(tmp_path, out, capsys):
    root = tmp_path / "norepo"; root.mkdir()
    gen._record_generation_manifest(out, root, [], {})
    run = _manifest(root)["summary"]["run"]
    assert run["manifestIsGitTracked"] is None and run["manifestIsGitIgnored"] is False
    assert "could not tell" in capsys.readouterr().out
