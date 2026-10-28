"""The spec lists (2.3.20): the spec that moved on last comes first (ticket 2026-10-23-viz-spec-list-not-recent-first),
the whiteboard's side list brings the open spec's row into view however it was opened (ticket
2026-10-23-viz-whiteboard-list-not-scrolled-to-opened-spec), a prose field written as {"md": ...} is read from its
texts file and drawn as Markdown (ticket 2026-10-23-viz-spec-sheet-shows-md-reference-raw), and the time it last moved
on stands beside its share (ticket 2026-10-23-viz-spec-no-last-updated-time).

specNewer, specWhen, wbSideShowOpen, histMarkdown and fillProse are cut out of the page's JS and run in node with the
page's state (and, for the Markdown, a small DOM) stood in.
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
from jui_cli.viz import sheet
from jui_cli.viz.sheet import sheet_for
from jui_cli.viz.sources import jsonui_project
from jui_cli.viz.sources.jsonui_project import JsonUIProject
from jui_cli.viz.state import VizState, now_ms
from tests.test_viz_bundle import web_text
from tests.test_viz_jsonui_project import _spec, make_project

OLD = 1_700_000_000   # seconds: older than anything the test writes


def _cut(file: str, *names: str) -> str:
    src = web_text("js", file)
    parts = []
    for name in names:
        # a top-level function ends at the first "}" in column 0 (_match counts the braces of a regex like {3,} too)
        start = re.search(rf"\nfunction {name}\(", src).start() + 1
        parts.append(src[start:src.index("\n}", start) + 2])
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
    when = lambda f: {k: _by_file(project)[f].get(k) for k in ("advancedAt", "advancedBy")}   # noqa: E731
    assert when(login) == {"advancedAt": OLD * 1000, "advancedBy": "spec"}   # a tie names the spec
    os.utime(root / "docs/screens/layouts/login.json", (OLD + 50, OLD + 50))   # the Layout written: implemented further
    assert when(login) == {"advancedAt": (OLD + 50) * 1000, "advancedBy": "layout"}
    os.utime(root / "docs/screens/json/empty.spec.json", (OLD + 70, OLD + 70))   # a spec written
    assert when(empty) == {"advancedAt": (OLD + 70) * 1000, "advancedBy": "spec"}
    sid = next(k for k in project.specs if k.endswith("login.spec.json"))
    project.test_results[sid] = {"passed": 1, "failed": 0, "running": False, "lastAt": (OLD + 90) * 1000}   # a result
    assert when(login) == {"advancedAt": (OLD + 90) * 1000, "advancedBy": "test"}


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
    md = lambda t: {"markdown": t}   # noqa: E731  from a texts file: Markdown, for the page to draw
    assert doc["metadata"]["description"] == md("説明の本文")
    assert doc["eventHandlers"][0][1] == md("送る")
    assert doc["userActions"][0][1] == md("押して送る")
    assert doc["transitions"][0][0] == md("成功した時")
    assert ["onSubmit", "note", md("ネットワークが落ちている")] in doc["branches"]
    assert ["Label", "title", md("画面の見出し"), 0] in doc["components"]
    assert '"md"' not in json.dumps(doc, ensure_ascii=False)
    assert doc["metadata"]["name"] == "Login" and doc["userActions"][0][0] == "Tap submit"   # written inline: text as before


def test_markdown_keeps_its_lines_and_a_long_one_is_cut_at_a_line(tmp_path):
    root = _md_project(tmp_path)
    body = "\n".join(f"- 項目 {k}" for k in range(2000))
    (root / "docs/screens/json/auth/login.texts.yaml").write_text(TEXTS.replace("  description: 説明の本文", "  description: |\n" + "\n".join("    " + x for x in body.split("\n"))))
    project = JsonUIProject(root, "p")
    project.load_all(0)
    text = sheet_for(project, next(k for k in project.specs if k.endswith("login.spec.json")))["metadata"]["description"]["markdown"]
    assert text.startswith("- 項目 0\n- 項目 1\n") and text.endswith("\n\n…") and len(text) <= sheet.MD_MAX + 3
    assert (body + "\n").startswith(text[:-3] + "\n")   # cut at a line's end: whole lines only


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
    assert sheet_for(project, sid)["metadata"]["description"] == {"markdown": "書き直した説明"}


def test_an_edit_to_a_shared_texts_file_another_spec_names_reads_that_spec_again(tmp_path):
    """A reference may name a file other than its paired one (`shared.texts.yaml#key`, relative to the spec's
    folder): editing that file alone reaches every spec of the app that names it, not only a `<spec>.texts.yaml`."""
    root = make_project(tmp_path)
    spec = _spec("Login")
    spec["metadata"]["description"] = {"md": "shared.texts.yaml#login.description"}
    (root / "docs/screens/json/auth/login.spec.json").write_text(json.dumps(spec, ensure_ascii=False))
    shared = root / "docs/screens/json/auth/shared.texts.yaml"
    shared.write_text("login:\n  description: 共通の説明\n")
    world = World(VizState())
    world.apply_hook({"session_id": "s1", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    project = next(iter(world.jsonui.values()))
    sid = next(k for k in project.specs if k.endswith("login.spec.json"))
    assert sheet_for(project, sid)["metadata"]["description"] == {"markdown": "共通の説明"}
    shared.write_text("login:\n  description: 書き直した共通の説明\n")
    world.file_changed(project.project_id, str(shared), 100)
    assert sheet_for(project, sid)["metadata"]["description"] == {"markdown": "書き直した共通の説明"}


def test_the_watcher_detects_a_spec_created_after_it_started(tmp_path):
    import time
    project = JsonUIProject(make_project(tmp_path), 'p')
    seen = []
    observer = jsonui_project.watch(project, seen.append)
    assert observer is not None
    path = tmp_path / 'docs/screens/json/new.spec.json'
    try:
        path.write_text('{}')
        deadline = time.monotonic() + 5
        while str(path) not in seen and time.monotonic() < deadline:
            time.sleep(0.05)
        assert str(path) in seen
    finally:
        observer.stop()
        observer.join(timeout=2)


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
    import watchdog.observers.polling
    monkeypatch.setattr(watchdog.observers, "Observer", FakeObserver)
    monkeypatch.setattr(watchdog.observers.polling, 'PollingObserver', FakeObserver)
    seen = []
    jsonui_project.watch(project, seen.append)

    class Event:
        is_directory, event_type, dest_path = False, "modified", ""

        def __init__(self, path):
            self.src_path = path

    for name in ("auth/login.texts.yaml", "auth/login.spec.json", "auth/notes.yaml"):
        handlers[0].on_any_event(Event(str(tmp_path / "docs/screens/json" / name)))
    assert [Path(p).name for p in seen] == ["login.texts.yaml", "login.spec.json"]


# ---------------------------------------------------------------- drawn as Markdown on the sheet


DOM = r"""
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
class El {
  constructor(tag) { this.tag = tag; this.kids = []; this.attrs = {}; this.className = ''; this.dataset = {}; }
  set textContent(t) { this.kids = [{ text: String(t) }]; }
  set innerHTML(h) { this.kids = [{ raw: String(h) }]; }   // markup, as a browser would read it: never escaped
  appendChild(k) { this.kids.push(k); return k; }
  append(...ks) { for (const k of ks) this.kids.push(typeof k === 'string' ? { text: k } : k); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  get firstChild() { return this.kids[0] || null; }
  html() {
    const a = Object.entries(this.attrs).map(([k, v]) => ` ${k}="${esc(v)}"`).join('') + (this.className ? ` class="${this.className}"` : '');
    return `<${this.tag}${a}>${this.kids.map((k) => (k instanceof El ? k.html() : 'raw' in k ? k.raw : esc(k.text))).join('')}</${this.tag}>`;
  }
}
const document = { createElement: (t) => new El(t), createTextNode: (t) => ({ text: String(t) }) };
const tl = (k, p = {}) => `${k}${JSON.stringify(p)}`;
const md = (t) => histMarkdown(t).html();
"""


def _md(cases: str):
    hist = _cut("55-history.js", "hNode", "histDecodeRefs", "histSafeHref", "histInline", "histMarkdown")
    src = web_text("js", "55-history.js")
    consts = "\n".join(re.search(rf"\nconst {n} = [^\n]*", src).group(0) for n in ("HIST_INLINE", "histCells"))
    return _node(DOM + consts + "\n" + hist + "\n" + _cut("50-panel.js", "fillProse") + f"\nprocess.stdout.write(JSON.stringify({cases}));")


def test_the_sheets_markdown_makes_bold_strong_keeps_a_lt_a_character_and_opens_http_links_only():
    got = _md("""{ bold: md('写真の**登録**をする'), lt: md('a <b>x</b> <script>alert(1)</script>'), ltCode: md('\x60<i>y</i>\x60'),
      js: md('[開く](javascript:alert(1))'), http: md('[開く](https://example.com/a)'), list: md('- 一\\n- 二\\n\\n1. 三'),
      table: md('| a | b |\\n|---|---|\\n| 1 | 2 |'), head: md('## 見出し') }""")
    assert "<strong>登録</strong>" in got["bold"]
    assert "&lt;b&gt;x&lt;/b&gt;" in got["lt"] and "<b>" not in got["lt"] and "<script>" not in got["lt"]
    assert got["ltCode"].count("<code>&lt;i&gt;y&lt;/i&gt;</code>") == 1 and "<i>" not in got["ltCode"]
    assert "<a" not in got["js"] and "javascript:alert(1)" in got["js"]
    assert '<a href="https://example.com/a" target="_blank" rel="noopener noreferrer">開く</a>' in got["http"]
    assert "<ul" in got["list"] and "<li>一</li>" in got["list"] and "<ol" in got["list"]
    assert "<table" in got["table"] and "<h5" in got["head"]   # headings and tables: the texts files have them (counted)


def test_each_placeholder_of_the_sheet_is_filled_with_its_markdown_once():
    got = _md("""(() => { const a = new El('span'), b = new El('span'), filled = new El('span');
      a.dataset.md = '0'; b.dataset.md = '1'; filled.dataset.md = '0'; filled.append('kept');
      const root = { querySelectorAll: () => [a, b, filled] };
      fillProse(root, ['**一**', '二']);
      return [a.html(), b.html(), filled.html()]; })()""")
    assert "<strong>一</strong>" in got[0] and "<p" in got[1] and "二" in got[1] and got[2] == "<span>kept</span>"


def test_every_prose_field_of_the_sheet_is_drawn_the_one_way():
    """The family (the ticket's table): the description, a part's, an event's and a step's (nameCells), an API's
    notes, a transition's condition, a branch's note — each through prose(), and the sheet fills them once set."""
    sheet_src = _cut("50-panel.js", "renderSheet")
    for shape in ("prose(m.description)", '<span class="desc">${prose(desc)}</span>', "j === 0 && named ? esc(c) : prose(c)",
                  '<span class="desc">${prose(op)}</span>', "${prose(trig)}<span class=\"to\">", "bjCell(when, i, 1, prose)",
                  "bjCell(then, i, 2, prose)", "fillProse(wbCode, mdTexts);"):
        assert shape in sheet_src, shape
    assert "esc(m.description)" not in sheet_src
    assert "isProse(v) ? `<td>${prose(v)}</td>`" in web_text("js", "50-panel.js")   # a branch's note, not a JSON block
    assert "description: sheetProse(meta.description)" in web_text("js", "30-source-live.js")


# ---------------------------------------------------------------- the time beside the share


WHEN = """
const JA = %s;
const tl = (k, p = {}) => JA[k].replace(/\\{(\\w+)\\}/g, (m, n) => (n in p ? String(p[n]) : m));
const now = new Date(2026, 9, 23, 0, 30, 0);
const at = (y, mo, d, h, mi, s = 0) => new Date(y, mo - 1, d, h, mi, s).getTime();
const w = (x) => specWhen(x, now);
""" % web_text("i18n", "ja.json")


def test_the_time_beside_the_share_is_today_yesterday_or_the_date_with_what_moved_it_on_the_title():
    got = _node(WHEN + _cut("20-core.js", "specWhen") + """
process.stdout.write(JSON.stringify([w({ advancedAt: at(2026, 10, 23, 0, 5), advancedBy: 'spec' }),
  w({ advancedAt: at(2026, 10, 22, 18, 0, 30), advancedBy: 'layout' }), w({ advancedAt: at(2026, 10, 21, 9, 7), advancedBy: 'test' }),
  w({ advancedAt: 0 }), w({})]));""")
    assert got[0] == {"text": "00:05", "title": "最終更新 2026/10/23 00:05:00（spec の書き込み）"}
    assert got[1] == {"text": "昨日 18:00", "title": "最終更新 2026/10/22 18:00:30（レイアウトの書き込み）"}
    assert got[2] == {"text": "10/21 09:07", "title": "最終更新 2026/10/21 09:07:00（テストの結果）"}
    assert got[3] is None and got[4] is None   # none sent (the demo): no time


def test_every_place_the_share_is_shown_has_the_time_beside_it():
    """The family (every s.status.text the page shows): the panel's row, the board's card, the side list's row, the
    whiteboard's head, a task's spec, the robot card's spec now, and the room's 3D board (drawn, and redrawn when the
    time's text changes)."""
    panel = web_text("js", "50-panel.js")
    scene = web_text("js", "40-scene.js")
    assert "fitText(ctx, specStatus(s).text," in scene and scene.count("specStatus(") == 4 and ".status.text" not in scene
    assert '${esc(specStatus(spec).text)}</span>' in panel and "paintStatus(rbEl.querySelector('[data-rb-specnow]')" in panel
    assert "paintStatus(b.querySelector('.stx'), specStatus(s));" in _cut("50-panel.js", "renderPanel")
    assert "paintStatus(st, specStatus(s));" in _cut("50-panel.js", "renderOverview")
    assert "paintStatus(b.lastElementChild, specStatus(x, UI.project === 'all'" in _cut("50-panel.js", "renderWbSide")
    assert _cut("50-panel.js", "renderSheet").count("specStatus(s)") == 3   # the head, loading or not, live or demo
    assert "paintStatus(st, typeof stText === 'object'" in _cut("50-panel.js", "setHead")
    assert re.findall(r"\w+\.status\.text", panel) == []   # no share shown without its time
    assert "advancedBy: typeof x.advancedBy === 'string' ? x.advancedBy : ''" in web_text("js", "30-source-live.js")
