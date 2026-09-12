"""The build manifest's scan roots include the per-screen view dirs.

Reported 2026-09-12 on two mobile faces running 1.8.75: `summary.scan`
said `outsideDeclaredRoots 88` on one and `200` on the other — each
exactly the number of `*GeneratedView.{swift,kt}` files on that face. The
files were recorded (the `_view_targets` collection finds them), but their
parents — `View/<screen>/`, `views/<screen>/` — are not named `generated`
and are not layout distribution dirs, so no declared root covered them. A
constant "outside" is worse than none: a root really missing would move
the number, not create it.

Closed at the declaration, as the layouts case was in 1.8.75 (ticket
`record-claims-…` §5-2): the view parents are DECLARED roots, derived
from the same collection that finds the files. Declared, not walked —
the hand-written `<Screen>View.swift` lives beside the generated one.

🔻 THE CONTROL IS THE OLD DERIVATION: the same paths against roots without
the view parents put every view file outside; with them, nothing is.
🔻 THE BOUNDARY: a sibling file in a view dir is NOT claimed; the same
sibling under a `generated` tree IS (that tree is walked).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.core.config_manager import ConfigManager  # noqa: E402
from jui_cli.commands import build_cmd  # noqa: E402
from jui_cli.core import generation_manifest as gm  # noqa: E402


def _project(root: Path):
    (root / "jui.config.json").write_text(json.dumps({
        "layouts_directory": "docs/layouts",
        "platforms": {
            "ios": {"root": "ios"},
            "android": {"root": "android"},
        },
    }), encoding="utf-8")
    ios_view = root / "ios" / "App" / "View" / "home"
    ios_view.mkdir(parents=True)
    ios_gen = ios_view / "HomeGeneratedView.swift"
    ios_gen.write_text("// @generated\n", encoding="utf-8")
    (ios_view / "HomeView.swift").write_text("// hand-written\n", encoding="utf-8")
    (ios_view / "notes.txt").write_text("hand-placed\n", encoding="utf-8")
    kt_view = root / "android" / "app" / "src" / "main" / "java" / "x" / "views" / "settings"
    kt_view.mkdir(parents=True)
    kt_gen = kt_view / "SettingsGeneratedView.kt"
    kt_gen.write_text("// @generated\n", encoding="utf-8")
    (kt_view / "SettingsScreen.kt").write_text("// hand-written\n", encoding="utf-8")
    # A generated TREE on the same face: walked, every file in it claimed.
    gen_tree = root / "android" / "app" / "src" / "main" / "java" / "x" / "generated" / "views" / "about"
    gen_tree.mkdir(parents=True)
    (gen_tree / "AboutGeneratedView.kt").write_text("// @generated\n", encoding="utf-8")
    (gen_tree / "notes.txt").write_text("inside a generated tree\n", encoding="utf-8")
    cfg = ConfigManager(root / "jui.config.json")
    return cfg, {"ios": ios_view, "kt": kt_view, "gen": gen_tree}, {"ios": ios_gen, "kt": kt_gen}


def _resolved(items):
    return {Path(x).resolve() for x in items}


class TestTheDeclaration:
    def test_the_view_parents_are_declared_roots(self, tmp_path):
        cfg, dirs, _ = _project(tmp_path)
        _, roots = build_cmd._generated_paths_and_roots(cfg)
        r = _resolved(roots)
        assert dirs["ios"].resolve() in r, roots
        assert dirs["kt"].resolve() in r, roots
        assert dirs["gen"].resolve() in r, roots

    def test_the_view_files_are_recorded(self, tmp_path):
        cfg, _, gens = _project(tmp_path)
        paths, _ = build_cmd._generated_paths_and_roots(cfg)
        p = _resolved(paths)
        assert gens["ios"].resolve() in p
        assert gens["kt"].resolve() in p

    def test_the_view_dir_is_declared_not_walked(self, tmp_path):
        """Boundary, both sides of it: the hand-written sibling and a
        hand-placed note in a view dir are not the build's; the same note
        under a `generated` tree is (the tree is walked)."""
        cfg, dirs, _ = _project(tmp_path)
        paths, _ = build_cmd._generated_paths_and_roots(cfg)
        p = _resolved(paths)
        assert (dirs["ios"] / "HomeView.swift").resolve() not in p
        assert (dirs["ios"] / "notes.txt").resolve() not in p
        assert (dirs["kt"] / "SettingsScreen.kt").resolve() not in p
        assert (dirs["gen"] / "notes.txt").resolve() in p


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

    def test_the_old_derivation_put_every_view_file_outside(self, tmp_path):
        """Control: the same paths against roots without the view parents.
        The count is the number of view files not under a `generated`
        tree — the reported shape (88 of 88, 200 of 200)."""
        cfg, dirs, gens = _project(tmp_path)
        paths, roots = build_cmd._generated_paths_and_roots(cfg)
        view_parents = {dirs["ios"].resolve(), dirs["kt"].resolve()}
        old_roots = [r for r in roots if Path(r).resolve() not in view_parents]
        assert len(old_roots) == len(roots) - 2
        run = self._observe(tmp_path, paths, old_roots)
        rel = lambda p: str(p.resolve().relative_to(tmp_path.resolve())).replace("\\", "/")
        assert sorted(run.outside_roots) == sorted([rel(gens["ios"]), rel(gens["kt"])])
        assert run.claims()["scan"]["outsideDeclaredRoots"] == 2
