"""A `when arg.<name>` list reaches the method as ONE list argument on every
face — the generation side of the rule the spec gate now admits.

The gate (document_tools validator) accepts a list of plain scalars for an
argument since 2.5.17 because generation already wrote it this way; this pins
that it still does, so the two cannot drift apart again.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonui_test_cli.branch_tests import generate_branch_tests


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _project(tmp_path: Path, value) -> Path:
    root = tmp_path / "proj"
    _write(root / "jui.config.json", {"spec_directory": "docs/specs"})
    _write(root / "docs/specs/inbox.spec.json", {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Inbox", "displayName": "Inbox", "description": "d", "layoutFile": "inbox"},
        "structure": {"components": [], "layout": {}},
        "dataFlow": {"viewModel": {"methods": [
            {"name": "applyFilter", "params": [{"name": "types", "type": "[String]?"}]}], "vars": []}},
        "stateManagement": {"uiVariables": []},
        "branchContracts": {"methods": {"applyFilter": {"branches": [
            {"when": {"arg.types": value}, "then": {"api": "none"}}]}}},
    })
    return root


FACES = {
    "web": ({}, {("notice", "promo"): 'applyFilter(["notice", "promo"])', (): "applyFilter([])"}),
    "ios": ({"module": "App"}, {("notice", "promo"): 'h.invoke("applyFilter", args: [["notice", "promo"]])',
                                (): 'h.invoke("applyFilter", args: [[]])'}),
    "android": ({"package": "com.example.app"},
                {("notice", "promo"): 'h.invoke("applyFilter", listOf<Any?>("notice", "promo"))',
                 (): 'h.invoke("applyFilter", listOf<Any?>())'}),
}


def _generated(root: Path, platform: str) -> str:
    return "\n".join(f.read_text() for f in (root / "gen" / platform).rglob("*")
                     if f.is_file() and "untime" not in f.name)


def test_a_list_argument_is_one_argument_on_every_face(tmp_path):
    for value in (("notice", "promo"), ()):
        for platform, (kw, expected) in FACES.items():
            root = _project(tmp_path / f"{platform}-{len(value)}", list(value))
            generate_branch_tests("inbox", root, platform=platform, out_dir=f"gen/{platform}", **kw)
            assert expected[value] in _generated(root, platform), (platform, value)
