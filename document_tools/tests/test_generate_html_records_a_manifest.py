"""Regression: doc-generate-html-never-records-a-generation-manifest.

`generate_html_directory` has taken `project_root: Path | None = None` since
the manifest was added; `cmd_generate_html` never passed it. So EVERY run of
`generate html`, on every face, printed "no project root for this run" and
recorded nothing. The `--config` help had documented the walk-up fallback for
longer than the fallback existed.

🚨 THE ACCEPTANCE CONDITION IS NOT "THE NOTE IS GONE". A face that also runs
`jui build` already has a manifest, so "a manifest exists" is true there before
any fix. The earlier ticket
`doc-generation-manifest-untracked-cannot-serve-as-run-evidence` was tripped by
exactly that: it argued from "generate html now records" while its own measured
block printed `docs/html 0 件` and `generatedBy: 見た範囲すべて "jui build"` —
the refutation sat thirteen lines below the claim, twice, and nobody read it
because the ticket's argument was about TRACKING and those lines do not
contradict a claim about tracking.

⇒ so the arms assert the ENTRY: `generatedBy == "jsonui-doc generate html"`.
That is the only thing a `jui build` manifest cannot already satisfy.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _spec() -> str:
    return json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": "s", "name": "S", "displayName": "S",
                     "description": "d."},
        "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                      "layout": {"root": "root", "children": []}}})


def _test_json() -> str:
    return json.dumps({
        "type": "screen", "platform": "ios", "source": {"layout": "s"},
        "metadata": {"name": "s", "description": "d"},
        "cases": [{"name": "o", "description": "o",
                   "steps": [{"action": "tap", "id": "x"}]}]})


@pytest.fixture()
def project():
    """An ISOLATED root. ⚠️ A fixture nested under another fixture walks up
    into ITS config, so a "no config" control built that way is not negative —
    measured while writing this file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        (root / "tests" / "screens").mkdir(parents=True)
        (root / "tests" / "screens" / "s.test.json").write_text(_test_json(), encoding="utf-8")
        (root / "docs" / "screens" / "json").mkdir(parents=True)
        (root / "docs" / "screens" / "json" / "s.spec.json").write_text(_spec(), encoding="utf-8")
        yield root


def run(root: Path, *extra: str) -> str:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO / "test_tools"), str(REPO / "document_tools")])
    r = subprocess.run(
        [sys.executable, "-m", "jsonui_doc_cli.cli", "generate", "html",
         str(root / "tests"), "-o", str(root / "out"), *extra],
        capture_output=True, text=True, env=env, cwd=str(REPO / "document_tools"))
    return r.stdout + r.stderr


def manifest(root: Path) -> dict:
    p = root / ".jsonui-cli" / "generation-manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _config(root: Path) -> None:
    (root / "jui.config.json").write_text(
        json.dumps({"spec_directory": "docs/screens/json"}), encoding="utf-8")


def test_the_run_records_pages_it_wrote(project):
    _config(project)
    run(project)
    files = manifest(project).get("files") or {}
    assert files, "the manifest must exist AND hold entries"
    produced = {e.get("generatedBy") for e in files.values()}
    # 🔻 THE discriminator. "a manifest exists" is already true wherever
    # `jui build` has run; only this entry is new.
    assert produced == {"jsonui-doc generate html"}, produced


def test_it_records_with_app_too(project):
    """⚠️ Three faces reported the same NOTE and all three used --app, so the
    condition looked like "multi-app". It is not: the condition is "this is
    generate html". Shooting only one arm's worth of `--app` would re-narrow
    it."""
    _config(project)
    run(project, "--app", f"only:{project / 'docs'}")
    files = manifest(project).get("files") or {}
    assert files
    assert {e.get("generatedBy") for e in files.values()} == {"jsonui-doc generate html"}


def test_without_any_config_it_says_so_and_writes_nothing(project):
    """🔻 Negative control: the NOTE is correct here, and must stay."""
    out = run(project)                      # no jui.config.json anywhere above
    assert "Project root: unresolved" in out
    assert "no project root for this run" in out
    assert not (project / ".jsonui-cli").exists(), "it must not write half a record"


def test_the_run_says_which_source_the_root_came_from(project):
    """🚨 A root from the app's own declaration and a root drifted into by
    walk-up produce identical manifests. Only the printed source separates
    them, and the walk-up is the one that can silently attach a face's output
    to whatever repository sits above it."""
    _config(project)
    assert "(from walk-up from the input directory)" in run(project)
    assert "(from --config)" in run(project, "--config", str(project / "jui.config.json"))


def test_unresolved_is_a_third_value(project):
    """Not-found must not read as either way of being found, nor as "there was
    nothing to record"."""
    out = run(project)
    assert "unresolved" in out
    assert "from --config" not in out and "from walk-up" not in out
    assert "nothing will be recorded" in out
