"""The generation manifest's `summary.scan.observed` counts the tree after the build.

Through 2.5.25 `jui build` recorded the count of the scan BEFORE the run, while
`tracked`, `outsideDeclaredRoots` and the roots spoke of the tree after it. A
build that created a file recorded the old count, and the next build — which
changed nothing — rewrote the record to catch up: 235 → 236 one build late on a
consumer's 2.5.25 acceptance (ticket jui-generation-manifest-observed-lags-a-
new-file). Measured on a jui init project: 2 → 24 after the first build, 24 → 31
after a layout was added, 31 → 25 after it was removed, each one build late.

The clock is pinned (SOURCE_DATE_EPOCH) so a record that does not move is byte
for byte the same.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.commands import build_cmd  # noqa: E402

MANIFEST = Path(".jsonui-cli") / "generation-manifest.json"


def _project(root: Path) -> Path:
    (root / "docs" / "screens" / "layouts").mkdir(parents=True)
    (root / "docs" / "screens" / "layouts" / "home.json").write_text('{"type": "View"}\n', encoding="utf-8")
    (root / "web").mkdir()
    (root / "jui.config.json").write_text(json.dumps({
        "layouts_directory": "docs/screens/layouts",
        "platforms": {"web": {"root": "web", "layoutsDir": "src/Layouts"}},
    }), encoding="utf-8")
    return root


@pytest.fixture
def build(monkeypatch, tmp_path):
    """The real cmd_build; the platform tool is a stand-in that writes Home.js, and Extra.js when asked to."""
    root = _project(tmp_path)
    monkeypatch.chdir(root)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1790000000")
    outputs = {"extra": False}

    def run_tool(_cmd, cwd):
        out = Path(cwd) / "src" / "generated"
        out.mkdir(parents=True, exist_ok=True)
        (out / "Home.js").write_text("// @generated\n", encoding="utf-8")
        extra = out / "Extra.js"
        if outputs["extra"]:
            extra.write_text("// @generated\n", encoding="utf-8")
        elif extra.exists():
            extra.unlink()
        return True

    monkeypatch.setattr(build_cmd, "_run_tool", run_tool)

    def run(extra=False):
        outputs["extra"] = extra
        with contextlib.redirect_stdout(io.StringIO()):
            assert build_cmd.cmd_build(argparse.Namespace(
                clean=False, ios_only=False, android_only=False, web_only=False, platform=None,
                lint_strings=False, normalize_layouts=None)) == 0
        return (root / MANIFEST).read_text(encoding="utf-8")

    return run


def _scan(record: str) -> dict:
    return json.loads(record)["summary"]["scan"]


def _tracked(record: str) -> int:
    return json.loads(record)["summary"]["tracked"]


def test_the_first_build_counts_what_it_wrote_and_the_second_moves_nothing(build):
    first = build()
    assert _scan(first)["observed"] == _tracked(first) == 2       # home.json distributed, Home.js
    assert build() == first


def test_a_build_that_adds_a_file_counts_it_and_the_next_moves_nothing(build):
    build()
    added = build(extra=True)
    assert _scan(added)["observed"] == _tracked(added) == 3
    assert build(extra=True) == added


def test_a_build_that_removes_a_file_counts_without_it(build):
    """Only the count is asked of here: the next build also clears `dropped`, a fact of the run that removed it."""
    build(extra=True)
    removed = build()
    assert _scan(removed)["observed"] == _tracked(removed) == 2
    assert _scan(build())["observed"] == 2


def test_the_control_the_count_before_the_run_is_one_build_behind(build, monkeypatch):
    """With `observe_after` taken out, the record is 2.5.25's: the old count, caught up a build later."""
    from jui_cli.core import generation_manifest as gm
    monkeypatch.setattr(gm.GenerationRun, "observe_after", lambda self, paths: None)
    build()
    added = build(extra=True)
    assert _scan(added)["observed"] == 2 and _tracked(added) == 3
    again = build(extra=True)
    assert _scan(again)["observed"] == 3 and again != added
