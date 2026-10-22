"""The spec lists (2.3.20): the spec that moved on last comes first (ticket 2026-10-23-viz-spec-list-not-recent-first),
the whiteboard's side list brings the open spec's row into view however it was opened (ticket
2026-10-23-viz-whiteboard-list-not-scrolled-to-opened-spec), and a prose field written as {"md": ...} is read from its
texts file (ticket 2026-10-23-viz-spec-sheet-shows-md-reference-raw).

specNewer and wbSideShowOpen are cut out of the page's JS and run in node with the page's state stood in.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from jui_cli.viz import i18n
from jui_cli.viz.ingest import World
from jui_cli.viz.sheet import sheet_for
from jui_cli.viz.sources import jsonui_project
from jui_cli.viz.sources.jsonui_project import JsonUIProject
from jui_cli.viz.state import VizState, now_ms
from tests.test_viz_bundle import _match, web_text
from tests.test_viz_jsonui_project import _spec, make_project

OLD = 1_700_000_000   # seconds: older than anything the test writes


def _cut(file: str, *names: str) -> str:
    src = web_text("js", file)
    parts = []
    for name in names:
        start = re.search(rf"\nfunction {name}\(", src).start() + 1
        parts.append(src[start:_match(src, src.index("{", start)) + 1])
    return "\n".join(parts)


def _node(code: str):
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    out = subprocess.run([node, "-"], input=code, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _age(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (OLD, OLD))


def _by_file(project: JsonUIProject) -> dict:
    return {s["file"]: s for s in project.summaries(0)}


# ---------------------------------------------------------------- what "moved on" is


def test_advanced_at_is_the_newest_of_the_spec_its_layout_and_its_newest_result(tmp_path):
    root = make_project(tmp_path)
    _age(root)
    project = JsonUIProject(root, "p")
    project.load_all(0)
    login, empty = "docs/screens/json/auth/login.spec.json", "docs/screens/json/empty.spec.json"
    assert _by_file(project)[login]["advancedAt"] == OLD * 1000
    os.utime(root / "docs/screens/layouts/login.json", (OLD + 50, OLD + 50))   # the Layout written: implemented further
    assert _by_file(project)[login]["advancedAt"] == (OLD + 50) * 1000
    os.utime(root / "docs/screens/json/empty.spec.json", (OLD + 70, OLD + 70))   # a spec written
    assert _by_file(project)[empty]["advancedAt"] == (OLD + 70) * 1000
    sid = next(k for k in project.specs if k.endswith("login.spec.json"))
    project.test_results[sid] = {"passed": 1, "failed": 0, "running": False, "lastAt": (OLD + 90) * 1000}   # a result
    assert _by_file(project)[login]["advancedAt"] == (OLD + 90) * 1000


def test_a_result_this_server_saw_run_moves_the_spec_on_too(tmp_path):
    """lastAt: the newest of a spec's results, saved or seen run here (latest stays the saved ones only)."""
    root = make_project(tmp_path)
    world = World(VizState())
    world.apply_hook({"session_id": "s1", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    project = next(iter(world.jsonui.values()))
    sid = next(k for k in project.specs if k.endswith("login.spec.json"))
    later = now_ms() + 3_600_000
    world.live_cases[project.project_id] = {sid: {("tests/screens/login.test.json", "login", "a"): (later, "passed"),
                                                  ("tests/screens/login.test.json", "login", "b"): (later - 5, "failed")}}
    world._merge_results(project)
    assert project.test_results[sid]["lastAt"] == later and "latest" not in project.test_results[sid]
    login = next(s for s in project.summaries(0) if s["id"] == sid)
    assert login["advancedAt"] == later


# ---------------------------------------------------------------- the order


SORT = "\nconst rows = %s;\nprocess.stdout.write(JSON.stringify(rows.map((s, i) => [s, i]).sort(specNewer).map(([s]) => s.n)));"


def test_the_spec_that_moved_on_last_comes_first_and_a_tie_keeps_the_order_it_had():
    rows = [{"n": "a", "advancedAt": 10}, {"n": "b", "advancedAt": 30}, {"n": "c"}, {"n": "d", "advancedAt": 30},
            {"n": "e", "advancedAt": 20}, {"n": "f"}]
    got = _node(_cut("20-core.js", "specNewer") + SORT % json.dumps(rows))
    assert got == ["b", "d", "e", "a", "c", "f"]   # newest first; b before d and c before f, as SPECS had them


def test_the_panel_the_board_and_its_side_list_all_sort_with_it():
    """One rule for the three lists the requester reads (the panel, 「ボードで全部見る」's board and its side list)."""
    panel = _cut("50-panel.js", "renderPanel")
    side = _cut("50-panel.js", "renderWbSide")
    board = _cut("50-panel.js", "renderOverview")
    assert re.search(r"\.sort\(\(a, b\) => roomOrder\[a\[0\]\.project\] - roomOrder\[b\[0\]\.project\] \|\| specNewer\(a, b\)\)", panel)
    assert ".filter(([s]) => s.bucket === b && match(s)).sort(specNewer)]" in side
    assert ".filter(([s]) => s.bucket === b && inScope(s.project) && inApp(s)).sort(specNewer);" in board
    # the board's cards are drawn again when only the order changed
    assert "${s.advancedAt || 0}" in board
    assert "advancedAt: Number.isFinite(x.advancedAt) ? x.advancedAt : 0" in web_text("js", "30-source-live.js")


# ---------------------------------------------------------------- the open spec's row in view


SCROLL_STAND_IN = """
const wb = { idx: 5 };
function list(rowTop, shown = true) {
  const row = { offsetParent: shown ? {} : null, getBoundingClientRect: () => ({ top: rowTop, bottom: rowTop + 40 }) };
  return { scrollTop: 1000, _shownFor: undefined,
    querySelector: (q) => (q === '.ws-item[aria-current="true"]' ? row : null),
    getBoundingClientRect: () => ({ top: 100, bottom: 600 }) };
}
let wbSideList;
function at(rowTop, shown) { wbSideList = list(rowTop, shown); wbSideShowOpen(); return [wbSideList.scrollTop, wbSideList._shownFor === wb.idx]; }
"""


def test_the_open_specs_row_is_brought_into_view_once_per_spec_opened():
    got = _node(SCROLL_STAND_IN + _cut("50-panel.js", "wbSideShowOpen") + """
const below = at(900), above = at(20), inside = at(300), hidden = at(900, false);
wbSideList = list(900); wbSideList._shownFor = 5; wbSideShowOpen();   // shown for this spec already: the reader's scroll stays
process.stdout.write(JSON.stringify({ below, above, inside, hidden, again: wbSideList.scrollTop }));""")
    assert got == {"below": [1348, True], "above": [912, True], "inside": [1000, True], "hidden": [1000, False], "again": 1000}


def test_every_way_of_opening_a_spec_ends_in_the_side_lists_redraw_that_scrolls():
    """The family: the panel, a board card, the side list, a robot, the URL and the follow all call openWhiteboard; it
    clears the mark and redraws the side list (renderWhiteboard -> renderWbSide), which ends in wbSideShowOpen."""
    src = web_text("js", "50-panel.js")
    opener = _cut("50-panel.js", "openWhiteboard")
    assert "wbSideList._shownFor = undefined;" in opener and opener.count("renderWhiteboard(latestModel, true)") == 2
    assert _cut("50-panel.js", "renderWbSide").rstrip().endswith("wbSideShowOpen();\n}")
    assert "renderWbSide(model);" in _cut("50-panel.js", "renderWhiteboard")
    # wb.idx is set nowhere but openWhiteboard and the project switch's way back to the board (-1, whose row the
    # redraw brings into view the same way): no way of opening goes round it
    assert [line.strip() for line in src.splitlines() if re.search(r"\bwb\.idx = ", line)] == [
        "if (wb.open && wb.idx >= 0 && !inScope(SPECS[wb.idx].project)) wb.idx = -1;",
        "wb.idx = i; wb.lastActive = null; wb.board = board || null;"]


# ---------------------------------------------------------------- {"md": ...} prose


TEXTS = """metadata:
  description: 説明の本文
handlers:
  submit: 送る
actions:
  tap: 押して送る
moves:
  ok: 成功した時
branches:
  down: ネットワークが落ちている
parts:
  title: 画面の見出し
"""


def _md_project(tmp_path: Path) -> Path:
    root = make_project(tmp_path)
    spec = _spec("Login", branchContracts={"methods": {"onSubmit": {"branches": [{"note": {"md": "branches.down"}}]}}})
    spec["metadata"]["description"] = {"md": "metadata.description"}
    spec["stateManagement"]["eventHandlers"][0]["description"] = {"md": "handlers.submit"}
    spec["userActions"][0]["processing"] = {"md": "actions.tap"}
    spec["transitions"][0]["condition"] = {"md": "moves.ok"}
    spec["structure"]["components"] = [{"type": "Label", "id": "title", "description": {"md": "parts.title"}}]
    (root / "docs/screens/json/auth/login.spec.json").write_text(json.dumps(spec, ensure_ascii=False))
    (root / "docs/screens/json/auth/login.texts.yaml").write_text(TEXTS)
    return root


def test_every_prose_field_of_the_sheet_is_read_from_the_texts_file(tmp_path):
    project = JsonUIProject(_md_project(tmp_path), "p")
    project.load_all(0)
    sid = next(k for k in project.specs if k.endswith("login.spec.json"))
    doc = sheet_for(project, sid)
    assert doc["metadata"]["description"] == "説明の本文"
    assert doc["eventHandlers"][0][1] == "送る"
    assert doc["userActions"][0][1] == "押して送る"
    assert doc["transitions"][0][0] == "成功した時"
    assert ["onSubmit", "note", "ネットワークが落ちている"] in doc["branches"]
    assert ["Label", "title", "画面の見出し", 0] in doc["components"]
    assert '"md"' not in json.dumps(doc, ensure_ascii=False)


def test_a_reference_it_cannot_read_is_named_never_shown_as_json(tmp_path):
    root = _md_project(tmp_path)
    (root / "docs/screens/json/auth/login.texts.yaml").write_text("other: x\n")
    project = JsonUIProject(root, "p")
    project.load_all(0)
    doc = sheet_for(project, next(k for k in project.specs if k.endswith("login.spec.json")))
    assert doc["metadata"]["description"] == i18n.tl("sheet.md.unread", ref="metadata.description")
    assert "{" not in json.dumps(doc["metadata"], ensure_ascii=False).replace('{"name"', "")


def test_an_edit_to_the_texts_file_alone_reads_the_spec_again(tmp_path):
    root = _md_project(tmp_path)
    world = World(VizState())
    world.apply_hook({"session_id": "s1", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    project = next(iter(world.jsonui.values()))
    sid = next(k for k in project.specs if k.endswith("login.spec.json"))
    texts = root / "docs/screens/json/auth/login.texts.yaml"
    texts.write_text(TEXTS.replace("説明の本文", "書き直した説明"))
    world.file_changed(project.project_id, str(texts), 100)
    assert sheet_for(project, sid)["metadata"]["description"] == "書き直した説明"


def test_the_watcher_passes_a_texts_file_on(tmp_path, monkeypatch):
    project = JsonUIProject(make_project(tmp_path), "p")
    handlers = []

    class FakeObserver:
        daemon = False

        def schedule(self, handler, *_a, **_k):
            handlers.append(handler)

        def start(self):
            pass

    import watchdog.observers
    monkeypatch.setattr(watchdog.observers, "Observer", FakeObserver)
    seen = []
    jsonui_project.watch(project, seen.append)

    class Event:
        is_directory, event_type, dest_path = False, "modified", ""

        def __init__(self, path):
            self.src_path = path

    for name in ("auth/login.texts.yaml", "auth/login.spec.json", "auth/notes.yaml"):
        handlers[0].on_any_event(Event(str(tmp_path / "docs/screens/json" / name)))
    assert [Path(p).name for p in seen] == ["login.texts.yaml", "login.spec.json"]
