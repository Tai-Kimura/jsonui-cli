"""The build manifest's scan roots include where the build distributes layouts.

The `summary.scan` block (1.8.73) flagged its first real discrepancy on a
web face: `outsideDeclaredRoots 25`, every one of them a layout copy under
`src/Layouts` — files the SAME build had written and recorded, under no
root it declared. The claim was right; the scan's declaration was short:
roots were the `generated`-named trees and the parents of generated files,
while the layout JSON came from `platforms.<p>.root/layoutsDir` in
`_collect_targets`. Two derivations of "where generated files live".

Closed at the declaration (ticket `record-claims-…` §5-2: the next ticket
of this kind closes by extending the ledger's inputs, not per symptom):
`_layout_distribution_dirs` is the one declaration, read by the lint
collection AND by the scan roots.

🔻 THE CONTROL IS THE OLD DERIVATION: the same paths observed against roots
without the layout dir put the copy outside; with it, nothing is outside.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.core.config_manager import ConfigManager  # noqa: E402
from jui_cli.commands import build_cmd, lint_generated_cmd  # noqa: E402
from jui_cli.core import generation_manifest as gm  # noqa: E402


def _project(root: Path) -> tuple[ConfigManager, Path, Path]:
    (root / "jui.config.json").write_text(json.dumps({
        "layouts_directory": "docs/layouts",
        "platforms": {
            "web": {"root": "web", "layoutsDir": "src/Layouts"},
            "ios": {"root": "ios", "layoutsDir": "Layouts"},   # root absent on disk
            "bogus": "not a mapping",
        },
    }), encoding="utf-8")
    layouts = root / "web" / "src" / "Layouts" / "home"
    layouts.mkdir(parents=True)
    page = layouts / "home.json"
    page.write_text('{"type": "View"}\n', encoding="utf-8")
    (root / "web" / "src" / "generated").mkdir(parents=True)
    (root / "web" / "src" / "generated" / "Home.tsx").write_text("// @generated\n", encoding="utf-8")
    return ConfigManager(root / "jui.config.json"), (root / "web" / "src" / "Layouts"), page


class TestOneDeclaration:
    def test_the_helper_names_existing_layout_dirs_only(self, tmp_path):
        cfg, layouts_dir, _ = _project(tmp_path)
        assert lint_generated_cmd._layout_distribution_dirs(cfg) == {layouts_dir}

    def test_the_lint_collection_still_finds_the_layout_json(self, tmp_path):
        cfg, _, page = _project(tmp_path)
        kinds = {p.resolve(): k for k, p in lint_generated_cmd._collect_targets(cfg)}
        assert kinds.get(page.resolve()) == "json"

    def test_the_scan_roots_include_the_layout_dir(self, tmp_path):
        cfg, layouts_dir, page = _project(tmp_path)
        paths, roots = build_cmd._generated_paths_and_roots(cfg)
        resolved_roots = {Path(r).resolve() for r in roots}
        assert layouts_dir.resolve() in resolved_roots, roots
        assert page.resolve() in {Path(p).resolve() for p in paths}


class TestTheLedgerAgrees:
    def _observe(self, root, paths, roots):
        run = gm.GenerationRun(project_root=root, version="t")
        run.observe(paths, roots=roots)
        run.written(paths)
        return run

    def test_nothing_is_outside_a_declared_root(self, tmp_path):
        cfg, _, _ = _project(tmp_path)
        paths, roots = build_cmd._generated_paths_and_roots(cfg)
        run = self._observe(tmp_path, paths, roots)
        assert run.outside_roots == []
        assert run.claims()["scan"]["outsideDeclaredRoots"] == 0

    def test_the_old_derivation_put_the_layout_copy_outside(self, tmp_path):
        """Control: the same paths against roots without the layout dir."""
        cfg, layouts_dir, page = _project(tmp_path)
        paths, roots = build_cmd._generated_paths_and_roots(cfg)
        old_roots = [r for r in roots if Path(r).resolve() != layouts_dir.resolve()]
        assert len(old_roots) == len(roots) - 1
        run = self._observe(tmp_path, paths, old_roots)
        assert run.outside_roots == [
            str(page.resolve().relative_to(tmp_path.resolve())).replace("\\", "/")]
