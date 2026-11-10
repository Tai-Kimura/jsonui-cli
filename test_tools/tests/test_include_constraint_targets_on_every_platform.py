"""A constraint inside an include names its target as the target is spelled
after expansion (ticket rjui-include-root-sibling-constraint-dropped, row D4).

shared/core/include_constraint_targets_fixture.json holds specimens — a
screen and the partials it includes, and, for each constrained element, its
expanded id and its constraint attributes with their expanded targets. Each
specimen goes through the sjui and kjui include expanders (the codegen's
expansion; SwiftUI and Compose are generated from what they return) and jui's
own Python expander, and the constraints of the expanded screen are read
back. Each must equal `expected`.

Measured on v2.5.24 before the change: under an include with an id the
elements' ids were prefixed (`cardA`) and the targets naming them were not
(`a`), so sjui dropped the constraint and kjui emitted `linkTo(a.top)` with no
`a` declared (Gradle: Unresolved reference). The SwiftJsonUI / KotlinJsonUI
dynamic expanders read the same file from their own tests; the web, which
draws an include as a component, is held by
rjui_tools/spec/cli/include_root_sibling_constraint_spec.rb.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((REPO / "shared/core/include_constraint_targets_fixture.json").read_text(encoding="utf-8"))
SPECIMENS = sorted(FIXTURE["specimens"])
KEYS = FIXTURE["constraint_keys"]

EXPAND = r"""
require 'json'
tool, root, screen = ARGV
if tool == 'sjui_tools'
  require 'swiftui/include_expander'
  expander = SjuiTools::SwiftUI::IncludeExpander
else
  require 'compose/include_expander'
  expander = KjuiTools::Compose::IncludeExpander
end
layouts = File.join(root, 'layouts')
expander.layouts_root = layouts
json = JSON.parse(File.read(File.join(layouts, screen)))
puts JSON.generate(expander.process_includes(json, layouts, nil, layouts))
"""


def _constraints(node, keys, out=None):
    """{element id: {attribute: target}} for every element with a constraint."""
    out = {} if out is None else out
    if isinstance(node, dict):
        found = {k: node[k] for k in keys if isinstance(node.get(k), str)}
        if found:
            out[node.get("id")] = found
        for key in ("child", "children"):
            kids = node.get(key)
            for kid in kids if isinstance(kids, list) else [kids] if isinstance(kids, dict) else []:
                _constraints(kid, keys, out)
    return out


@pytest.fixture(scope="module")
def roots(tmp_path_factory):
    base = tmp_path_factory.mktemp("include_constraints")
    out = {}
    for name in SPECIMENS:
        root = base / name
        for rel, tree in FIXTURE["specimens"][name]["layouts"].items():
            path = root / "layouts" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(tree), encoding="utf-8")
        out[name] = root
    return out


def _expand(tool: str, root: Path) -> dict:
    if shutil.which("ruby") is None:
        pytest.skip("ruby is not available — the include constraint targets are UNMEASURED here")
    result = subprocess.run(
        ["ruby", "-I", str(REPO / tool / "lib"), "-e", EXPAND, tool, str(root), FIXTURE["screen"]],
        capture_output=True, text=True, cwd=str(REPO))
    assert result.returncode == 0, f"{tool}: {result.stderr[-2000:]}"
    return json.loads(result.stdout)


def test_the_fixture_covers_every_constraint_key():
    covered = {k for name in SPECIMENS for attrs in FIXTURE["specimens"][name]["expected"].values() for k in attrs}
    assert covered == set(KEYS)


@pytest.mark.parametrize("tool", ["sjui_tools", "kjui_tools"])
@pytest.mark.parametrize("name", SPECIMENS)
def test_the_expanded_screen_names_each_target_as_it_is_spelled(roots, tool, name):
    expanded = _expand(tool, roots[name])
    assert _constraints(expanded, KEYS) == FIXTURE["specimens"][name]["expected"]


@pytest.mark.parametrize("name", SPECIMENS)
def test_the_python_expander_names_each_target_as_the_codegen_does(roots, name):
    """jui's own expander (`jui_cli.core.normalizer`, what the spec validator,
    coverage and `jui build`'s relative-constraint check read layouts with)
    applies the same rule (ticket jui-relative-constraint-target-not-a-sibling)."""
    from jui_cli.core.normalizer.include_expander import CONSTRAINT_TARGET_KEYS, IncludeExpander
    from jui_cli.core.normalizer.style_merger import StyleMerger

    assert list(CONSTRAINT_TARGET_KEYS) == KEYS
    layouts = roots[name] / "layouts"
    screen = json.loads((layouts / FIXTURE["screen"]).read_text(encoding="utf-8"))
    expanded = IncludeExpander(layouts, StyleMerger(layouts)).expand(screen)
    assert _constraints(expanded, KEYS) == FIXTURE["specimens"][name]["expected"]
