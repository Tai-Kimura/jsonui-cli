"""The ids `layout_facts` counts are the ids codegen emits (design U8).

The duplicate-id gate in `jui build`, the spec validator and coverage all read
a layout through `jui_cli.core.layout_facts`; SwiftUI and Compose code is
generated from the Ruby expanders (sjui / kjui `include_expander.rb`). If the
two expanded an include differently, the gate would count ids no platform
has. ee's six collision specimens go through all three, and the id
multisets — counts included, since a duplicate is what the gate is for —
must be equal. Needs `ruby` (every CI image carries it); without it the arm
skips and says so.
"""
from __future__ import annotations

import collections
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from jui_cli.core.layout_facts import layout_facts

REPO = Path(__file__).resolve().parents[2]
EXPANDERS = {
    "sjui": ("sjui_tools/lib", "swiftui/include_expander", "SjuiTools::SwiftUI::IncludeExpander"),
    "kjui": ("kjui_tools/lib", "compose/include_expander", "KjuiTools::Compose::IncludeExpander"),
}

SPECIMENS = {
    # 1: two spellings in one partial meet
    "s1": {"screen": {"type": "View", "id": "root", "child": [{"include": "p/hero", "id": "hero"}]},
           "p/hero": {"type": "View", "id": "box", "child": [
               {"type": "Label", "id": "type_badge"}, {"type": "Label", "id": "typeBadge"}]}},
    # 2: two include ids meet
    "s2": {"screen": {"type": "View", "id": "root", "child": [
               {"include": "p/a", "id": "hero"}, {"include": "p/b", "id": "hero_card"}]},
           "p/a": {"type": "View", "id": "a_box", "child": [{"type": "Label", "id": "card_type_badge"}]},
           "p/b": {"type": "View", "id": "b_box", "child": [{"type": "Label", "id": "type_badge"}]}},
    # 3: an include id with `_`
    "s3": {"screen": {"type": "View", "id": "root", "child": [{"include": "p/c", "id": "hero_card"}]},
           "p/c": {"type": "View", "id": "c_box", "child": [{"type": "Label", "id": "label"}]}},
    # 4: an upper-case segment
    "s4": {"screen": {"type": "View", "id": "root", "child": [{"include": "p/d", "id": "hero"}]},
           "p/d": {"type": "View", "id": "d_box", "child": [{"type": "Label", "id": "info_URL"}]}},
    # 5: nested, only the inner include has an id
    "s5": {"screen": {"type": "View", "id": "root", "child": [{"include": "p/outer"}]},
           "p/outer": {"type": "View", "id": "outer_box", "child": [{"include": "p/inner", "id": "inner_box"}]},
           "p/inner": {"type": "View", "id": "in_box", "child": [{"type": "Label", "id": "deep_label"}]}},
    # 6: one partial twice, two ids and one id
    "s6": {"screen": {"type": "View", "id": "root", "child": [
               {"include": "p/e", "id": "hero"}, {"include": "p/e", "id": "side"},
               {"include": "p/e", "id": "hero"}]},
           "p/e": {"type": "View", "id": "e_box", "child": [{"type": "Label", "id": "title"}]}},
}

RUBY = """
require 'json'
require '%(lib)s'
root = ARGV[0]
expanded = %(mod)s.process_includes(JSON.parse(File.read(File.join(root, 'screen.json'))), root, nil, root)
def ids(node, out)
  return out unless node.is_a?(Hash)
  out << node['id'] if node['id']
  Array(node['child']).each { |c| ids(c, out) }
  out
end
puts JSON.generate(ids(expanded, []))
"""


def _write(root: Path, specimen: dict) -> None:
    for name, tree in specimen.items():
        path = root / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tree), encoding="utf-8")


def _ruby_ids(tool: str, root: Path) -> collections.Counter:
    lib, required, mod = EXPANDERS[tool]
    script = RUBY % {"lib": required, "mod": mod}
    out = subprocess.run(["ruby", "-I", str(REPO / lib), "-e", script, str(root)],
                         capture_output=True, text=True, check=True,
                         env={"LC_ALL": "en_US.UTF-8", "PATH": _path()})
    return collections.Counter(json.loads(out.stdout))


def _path() -> str:
    import os
    return os.environ.get("PATH", "")


@pytest.mark.skipif(shutil.which("ruby") is None, reason="ruby not installed — the codegen "
                    "expanders cannot be run here; the agreement is UNMEASURED")
@pytest.mark.parametrize("tool", sorted(EXPANDERS))
@pytest.mark.parametrize("name", sorted(SPECIMENS))
def test_layout_facts_counts_the_ids_codegen_emits(tmp_path, tool, name):
    _write(tmp_path, SPECIMENS[name])
    facts = layout_facts({"metadata": {"layoutFile": "screen"}}, None,
                         layouts_dir=tmp_path, styles_dir=tmp_path)
    assert facts.id_counts == _ruby_ids(tool, tmp_path), (name, tool)


def test_the_answers_are_the_codegen_spelling():
    """What the table above agrees ON — so a change to both sides at once
    shows here (the vectors: shared/core/camel_case_vectors.json)."""
    expected = {
        "s1": {"heroTypeBadge": 2}, "s2": {"heroCardTypeBadge": 2},
        "s3": {"heroCardLabel": 1}, "s4": {"heroInfoUrl": 1},
        "s5": {"innerBoxDeepLabel": 1}, "s6": {"heroTitle": 2, "sideTitle": 1},
    }
    import tempfile
    for name, want in expected.items():
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, SPECIMENS[name])
            counts = layout_facts({"metadata": {"layoutFile": "screen"}}, None,
                                  layouts_dir=root, styles_dir=root).id_counts
            assert {k: counts[k] for k in want} == want, (name, dict(counts))
