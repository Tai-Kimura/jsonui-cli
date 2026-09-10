"""Regression: doc-generate-html-records-its-manifest-in-one-root-so-a-multi-app-run-leaves-the-other-faces-without-one
(and doc-manifest-run-record-lands-in-one-face-and-carries-the-others-paths).

`_resolve_project_root` returned ONE root — the first `--app` with a config —
so a site run over four apps wrote its pages and its run facts into one face's
manifest, and the other three could never hold `summary.run`. The v1.8.66
notice had told every face to read `summary.run.outsideOutput.*` as the
outside-writes discriminator; for three of four faces that key was
structurally absent, which reads exactly like "nothing written outside".

Measured 2026-09-10 on isolated copies: 4 apps → 1 manifest, 2 apps → 1.

The record now lands in every root the run resolved: `--config` alone, else
every app with a config, else the walk-up. Each copy carries the same run
facts and the same `recordedAt` (one stamp per run), names the apps it
covered, records the pages under ITS root only, and reports its own
`manifestIsGitTracked`.

⚠️ The CLI arm SHOOTS THE COMMAND. The one-root defect lived in the wiring
between `cmd_generate_html` and the generator; a function-level arm passes a
list the command never built.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402


def _manifest(root: Path) -> dict:
    p = root / ".jsonui-cli" / "generation-manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


# ---------------------------------------------------------------- unit ----

@pytest.fixture()
def two_roots(tmp_path, monkeypatch):
    """Two app roots and an output tree holding one page under each."""
    out = tmp_path / "site" / "html"
    roots = {}
    written = []
    for name in ("a", "b"):
        root = tmp_path / name
        page = root / "docs" / "html" / "index.html"
        page.parent.mkdir(parents=True)
        page.write_text("<html></html>", encoding="utf-8")
        roots[name] = root
        written.append(page.resolve())
    out.mkdir(parents=True)
    monkeypatch.setattr(gen, "get_written_pages", lambda: set(written))
    return out, roots


def test_every_root_gets_the_same_run_record(two_roots, capsys):
    out, roots = two_roots
    outside = {"directories": ["/elsewhere"], "gitTrackedDirectories": {}, "uncheckable": []}
    gen._record_generation_manifest(
        out, [{"app": "a", "root": roots["a"]}, {"app": "b", "root": roots["b"]}],
        [], outside, slots={"declarations": 2, "paths": 2, "sharedPaths": 0, "sharedPathKeys": []})
    runs = {n: _manifest(r)["summary"]["run"] for n, r in roots.items()}
    assert runs["a"]["recordedAt"] == runs["b"]["recordedAt"], "one stamp per run"
    assert runs["a"]["recordedBy"] == runs["b"]["recordedBy"] == "jsonui-doc generate html"
    assert runs["a"]["apps"] == runs["b"]["apps"] == ["a", "b"]
    # The outside-writes record is scoped per root (see the arm below), so
    # here — nothing under either root — both say so explicitly.
    assert runs["a"]["outsideOutput"]["directories"] == [] == runs["b"]["outsideOutput"]["directories"]
    assert runs["a"]["documentSlots"] == runs["b"]["documentSlots"]
    printed = capsys.readouterr().out
    assert printed.count("Manifest created:") == 2, printed


def test_pages_are_recorded_under_their_own_root_only(two_roots):
    out, roots = two_roots
    gen._record_generation_manifest(
        out, [{"app": "a", "root": roots["a"]}, {"app": "b", "root": roots["b"]}], [], {})
    assert set(_manifest(roots["a"])["files"]) == {"docs/html/index.html"}
    assert set(_manifest(roots["b"])["files"]) == {"docs/html/index.html"}
    # Same relative key, two different files: neither manifest lists a page
    # that lives under the other root.
    assert _manifest(roots["a"])["summary"]["tracked"] == 1


def test_a_second_run_says_updated_not_created(two_roots, capsys):
    out, roots = two_roots
    targets = [{"app": "a", "root": roots["a"]}, {"app": "b", "root": roots["b"]}]
    gen._record_generation_manifest(out, targets, [], {})
    capsys.readouterr()
    gen._record_generation_manifest(out, targets, [], {})
    printed = capsys.readouterr().out
    assert printed.count("Manifest updated:") == 2 and "Manifest created:" not in printed


def test_a_single_root_keeps_the_single_tree_spelling(two_roots, capsys):
    """One root, one manifest, no per-root line, no `apps` — unchanged."""
    out, roots = two_roots
    gen._record_generation_manifest(out, roots["a"], [], {})
    run = _manifest(roots["a"])["summary"]["run"]
    assert "apps" not in run
    assert "Manifest created:" not in capsys.readouterr().out
    assert not (roots["b"] / ".jsonui-cli").exists()


# ----------------------------------------------------------------- CLI ----

def _spec() -> str:
    return json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": "s", "name": "S", "displayName": "S", "description": "d."},
        "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                      "layout": {"root": "root", "children": []}}})


def _test_json() -> str:
    return json.dumps({
        "type": "screen", "platform": "ios", "source": {"layout": "s"},
        "metadata": {"name": "s", "description": "d"},
        "cases": [{"name": "o", "description": "o",
                   "steps": [{"action": "tap", "id": "x"}]}]})


@pytest.fixture()
def two_apps(tmp_path):
    """Two apps, each with its own config and specs, under one site."""
    site = tmp_path / "site"
    (site / "tests" / "screens").mkdir(parents=True)
    (site / "tests" / "screens" / "s.test.json").write_text(_test_json(), encoding="utf-8")
    for name in ("a", "b"):
        app = site / name
        (app / "docs" / "screens" / "json").mkdir(parents=True)
        (app / "docs" / "screens" / "json" / "s.spec.json").write_text(_spec(), encoding="utf-8")
        (app / "jui.config.json").write_text(
            json.dumps({"spec_directory": "docs/screens/json"}), encoding="utf-8")
    return site


def _run(site: Path, *extra: str) -> str:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "test_tools"), str(REPO / "document_tools")])
    r = subprocess.run(
        [sys.executable, "-m", "jsonui_doc_cli.cli", "generate", "html",
         str(site / "tests"), "-o", str(site / "out"), *extra],
        capture_output=True, text=True, env=env, cwd=str(REPO / "document_tools"))
    return r.stdout + r.stderr


def test_the_command_records_into_every_app_root(two_apps):
    out = _run(two_apps, "--app", f"a:{two_apps / 'a' / 'docs'}", "--app", f"b:{two_apps / 'b' / 'docs'}")
    # isfile, not "the note is gone": the historical path writes one file.
    files = [two_apps / n / ".jsonui-cli" / "generation-manifest.json" for n in ("a", "b")]
    assert [f.is_file() for f in files] == [True, True], out
    runs = [_manifest(two_apps / n)["summary"]["run"] for n in ("a", "b")]
    assert runs[0]["recordedAt"] == runs[1]["recordedAt"]
    assert runs[0]["apps"] == runs[1]["apps"] == ["a", "b"]
    assert "Manifests recorded at: 2 roots" in out
    assert out.count("Manifest created:") == 2


def test_config_narrows_the_set_to_one_root(two_apps):
    out = _run(two_apps, "--config", str(two_apps / "a" / "jui.config.json"),
               "--app", f"a:{two_apps / 'a' / 'docs'}", "--app", f"b:{two_apps / 'b' / 'docs'}")
    assert (two_apps / "a" / ".jsonui-cli" / "generation-manifest.json").is_file()
    assert not (two_apps / "b" / ".jsonui-cli").exists(), out
    assert "Manifests recorded at:" not in out
    assert "(from --config)" in out


def test_outside_writes_are_scoped_to_each_root(two_roots):
    """One face's block used to carry every face's directories; now each block
    names writes under ITS root, and says so — an empty list is an answer."""
    out, roots = two_roots
    a_dir = str((roots["a"] / "docs" / "components").resolve())
    b_dir = str((roots["b"] / "docs" / "requirements").resolve())
    elsewhere = "/elsewhere/docs"
    outside = {"directories": [a_dir, b_dir, elsewhere],
               "gitTrackedDirectories": {a_dir: 5, b_dir: 14},
               "gitModifiedDirectories": {b_dir: 2},
               "uncheckable": [elsewhere]}
    gen._record_generation_manifest(
        out, [{"app": "a", "root": roots["a"]}, {"app": "b", "root": roots["b"]}], [], outside)
    a = _manifest(roots["a"])["summary"]["run"]["outsideOutput"]
    b = _manifest(roots["b"])["summary"]["run"]["outsideOutput"]
    assert a["directories"] == [a_dir] and b["directories"] == [b_dir]
    assert a["gitTrackedDirectories"] == {a_dir: 5} and b["gitTrackedDirectories"] == {b_dir: 14}
    assert a["gitModifiedDirectories"] == {} and b["gitModifiedDirectories"] == {b_dir: 2}
    assert a["uncheckable"] == [] and b["uncheckable"] == []
    assert a["scope"] == str(roots["a"].resolve()) and b["scope"] == str(roots["b"].resolve())


def test_a_single_root_keeps_the_run_level_outside_record(two_roots):
    out, roots = two_roots
    outside = {"directories": ["/elsewhere/docs"], "gitTrackedDirectories": {}, "uncheckable": []}
    gen._record_generation_manifest(out, roots["a"], [], outside)
    assert _manifest(roots["a"])["summary"]["run"]["outsideOutput"] == outside
