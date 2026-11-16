"""`jui verify` counts the ids inside an include the way the runtime spells them.

An include `{"include": "header", "id": "top"}` is replaced at runtime by the
file's tree, and every id in it takes `top` as a camelCase prefix (`title` ->
`topTitle`); the include node's own id does not survive. `jui verify` used to
record `top` itself and read the file's ids raw (`title`), and it read a file
once per screen, so the same include placed twice counted its ids once. A spec
naming the runtime id was told it was missing; one naming the raw id passed
with an id that does not exist at runtime.

The authority is the normalizer's `IncludeExpander` — the Python port of the
runtime's expander. The arms do not restate its spelling: they run the same tree
through it and compare the id sets by machine, then pin a few spellings by name
so a reader can see what "carries the prefix" means.
"""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jui_cli.core.normalizer.include_expander import IncludeExpander
from jui_cli.core.normalizer.style_merger import StyleMerger
from jui_cli.core.view_diff_checker import ViewDiffChecker


def _write(d: Path, name: str, tree) -> None:
    (d / f"{name}.json").write_text(json.dumps(tree), encoding="utf-8")


def _layouts(tmp_path):
    layouts = tmp_path / "layouts"
    styles = tmp_path / "styles"
    layouts.mkdir()
    styles.mkdir()
    _write(layouts, "header", {"type": "View", "id": "header_root", "child": [
        {"type": "Label", "id": "title"},
        {"include": "badge", "id": "badge"},
    ]})
    _write(layouts, "badge", {"type": "View", "child": [{"type": "Label", "id": "label"}]})
    _write(layouts, "cell", {"type": "View", "child": [
        {"type": "Label", "id": "cell_label"},
        {"include": "badge", "id": "cell_badge"},
    ]})
    return layouts, styles


SCREEN = {"type": "View", "id": "root", "child": [
    {"include": "header", "id": "top"},
    {"include": "header", "id": "bottom"},
    {"include": "missing_file", "id": "ghost"},
    {"type": "Collection", "id": "list", "cellClasses": ["cell"]},
]}


def _runtime_ids(tree, layouts, styles):
    """Ids of the tree as the normalizer's expander leaves them."""
    expanded = IncludeExpander(layouts, StyleMerger(styles)).expand(copy.deepcopy(tree))
    ids = set()

    def walk(n):
        if isinstance(n, dict):
            if n.get("id"):
                ids.add(n["id"])
            for k in ("child", "children"):
                if k in n:
                    walk(n[k])
        elif isinstance(n, list):
            for x in n:
                walk(x)
    walk(expanded)
    return ids


def _verify_ids(tree, layouts, styles):
    checker = ViewDiffChecker(layouts_root=layouts, styles_root=styles)
    return checker.compare({}, copy.deepcopy(tree), screen="s").actual_ids


def test_include_ids_equal_the_normalizers_expansion(tmp_path):
    layouts, styles = _layouts(tmp_path)
    runtime = _runtime_ids(SCREEN, layouts, styles)
    # cellClasses are separate layouts at runtime (not expanded into the
    # screen, not prefixed); verify reads them in on purpose, so they are the
    # only ids verify may add over the expander's set.
    cell = _runtime_ids(json.loads((layouts / "cell.json").read_text()), layouts, styles)
    assert _verify_ids(SCREEN, layouts, styles) == runtime | cell
    assert "cellBadgeLabel" in cell  # the cell's own include, expanded the same way


def test_spellings_by_name(tmp_path):
    layouts, styles = _layouts(tmp_path)
    ids = _verify_ids(SCREEN, layouts, styles)
    # Prefixed, for both placements of the same file, and through a nested include.
    assert {"topTitle", "bottomTitle", "topHeaderRoot", "bottomHeaderRoot",
            "topBadgeLabel", "bottomBadgeLabel"} <= ids
    # The raw spellings and the include nodes' own ids do not exist at runtime.
    assert not ({"title", "header_root", "label", "top", "bottom", "badge"} & ids)
    # A missing include file: the node stays as itself, as the expander keeps it.
    assert "ghost" in ids


def test_the_generated_side_is_unchanged(tmp_path):
    """Only the on-disk side is expanded; the spec side never holds includes."""
    layouts, styles = _layouts(tmp_path)
    checker = ViewDiffChecker(layouts_root=layouts, styles_root=styles)
    generated = {"type": "View", "id": "root", "child": [{"type": "Label", "id": "topTitle"}]}
    result = checker.compare(copy.deepcopy(generated), copy.deepcopy(SCREEN), screen="s")
    assert result.expected_ids == {"root", "topTitle"}
    assert "topTitle" not in {d.node_id for d in result.missing}
