"""An include node's maps (``shared_data`` then ``data``, objects) are read the
same way by every expander: the Python normalizer's, sjui's, kjui's and rjui's
(ruling 2026-10-02 — an included layout reads the including layout's data with
the include node's maps over it; shared/core/include_data_map.rb).

Until jsonui-cli 1.9.6 the expanders dropped an object map (they merged only an
array ``data``, as declarations), so ``@{title}`` inside the partial read the
screen's ``title`` whatever the map said (ticket
native-include-object-map-is-ignored).

One corpus goes through all four and the expanded trees must be equal —
machine against machine; the answers themselves are pinned once below, so a
change to every side at once shows. Needs ``ruby``; without it the Ruby arms
skip and say so.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from jui_cli.core.normalizer.include_expander import IncludeExpander
from jui_cli.core.normalizer.style_merger import StyleMerger

REPO = Path(__file__).resolve().parents[2]
EXPANDERS = {
    "sjui": ("sjui_tools/lib", "swiftui/include_expander", "SjuiTools::SwiftUI::IncludeExpander"),
    "kjui": ("kjui_tools/lib", "compose/include_expander", "KjuiTools::Compose::IncludeExpander"),
    "rjui": ("rjui_tools/lib", "react/include_expander", "RjuiTools::React::IncludeExpander"),
}
# rjui's mark on an expanded include's root — read by its Data walk only.
RJUI_ONLY_KEYS = {"_jui_include_root"}

FIXTURE = json.loads((REPO / "shared/core/include_maps_fixture.json").read_text(encoding="utf-8"))
SPECIMENS = sorted(FIXTURE["specimens"])

RUBY = """
require 'json'
require '%(lib)s'
root = ARGV[0]
puts JSON.generate(%(mod)s.process_includes(JSON.parse(File.read(File.join(root, 'screen.json'))), root, nil, root))
"""


def _write(root: Path, specimen: str) -> None:
    for name, tree in FIXTURE["specimens"][specimen]["layouts"].items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tree), encoding="utf-8")


def _python_tree(root: Path):
    expander = IncludeExpander(root, StyleMerger(root / "styles"))
    return expander.expand(json.loads((root / "screen.json").read_text(encoding="utf-8")))


def _strip(node):
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in node.items() if k not in RJUI_ONLY_KEYS}
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def _ruby_tree(tool: str, root: Path):
    lib, required, mod = EXPANDERS[tool]
    out = subprocess.run(["ruby", "-I", str(REPO / lib), "-e", RUBY % {"lib": required, "mod": mod},
                          str(root)], capture_output=True, text=True, check=True,
                         env={"LC_ALL": "en_US.UTF-8", "PATH": os.environ.get("PATH", "")})
    return _strip(json.loads(out.stdout))


def _drawn(tree) -> dict:
    """{ id: the text / visibility it draws } over the expanded tree."""
    out = {}

    def walk(node):
        if isinstance(node, dict):
            if "id" in node:
                for key in ("text", "visibility"):
                    if key in node:
                        out[node["id"]] = node[key]
            child = node.get("child")
            for c in (child if isinstance(child, list) else [child] if child else []):
                walk(c)
    walk(tree)
    return out


@pytest.mark.skipif(shutil.which("ruby") is None, reason="ruby not installed — the codegen "
                    "expanders cannot be run here; the agreement is UNMEASURED")
@pytest.mark.parametrize("tool", sorted(EXPANDERS))
@pytest.mark.parametrize("specimen", SPECIMENS)
def test_every_expander_expands_the_maps_alike(tmp_path, tool, specimen):
    _write(tmp_path, specimen)
    assert _ruby_tree(tool, tmp_path) == _python_tree(tmp_path)


@pytest.mark.parametrize("specimen", SPECIMENS)
def test_the_answers(tmp_path, specimen):
    """What the arms above agree ON: the fixture's own answers."""
    _write(tmp_path, specimen)
    assert _drawn(_python_tree(tmp_path)) == FIXTURE["specimens"][specimen]["expected"]
