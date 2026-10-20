"""Chapters 1a and 1b: the editor and the terminal (plan §2 rows 1a / 1b, §2.6: no invented text).

1b runs the real gates in a copy of demo-shop (rooms.copy_demo_shop: the tracked files, one commit) with --jui-root's
launchers, keeps what each printed (stdout and stderr, in order), and types them out in a terminal window drawn in
HTML. The prompt is `demo-shop $`: no user name, no home path. What the window shows of an output is the output
with two things changed, both said in the README: colour codes taken out, and the copy's absolute paths written
relative to it (the copy lives in a temporary folder whose path means nothing to a viewer).

1a opens real files of the same copy in an editor-like window, one after another (GENERATED: files that carry the
@generated header; HAND_WRITTEN: a view model's body, written by hand), each scrolled slowly.

Both windows are pure functions of the video time (window.render(t)); the capture sets t frame by frame, so there is
no clock to drive.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from viz_promo.rooms import cleanup, copy_demo_shop
from viz_promo.timeline import frame_count, frame_time

PROMPT = "demo-shop $ "
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

# (what the window shows as typed, the launcher under --jui-root and its arguments, a line to keep in view)
GATES = (
    ("jui build", ("jui_tools/bin/jui", "build"), None),
    ("jui verify --fail-on-diff", ("jui_tools/bin/jui", "verify", "--fail-on-diff"), r"checked against the spec's declarations"),
    ("jui lint-strings", ("jui_tools/bin/jui", "lint-strings"), None),
    ("jsonui-test generate branch-tests --check --out-dir web/tests/unit/generated --harness-dir web/tests/unit/branch-harness",
     ("test_tools/jsonui-test", "generate", "branch-tests", "--check", "--out-dir", "web/tests/unit/generated",
      "--harness-dir", "web/tests/unit/branch-harness"), None),
    ("jsonui-test generate branch-tests --check -p android --package com.example.demoshop "
     "--out-dir android/app/src/test/java/com/example/demoshop --harness-dir android/app/src/test/java/com/example/demoshop",
     ("test_tools/jsonui-test", "generate", "branch-tests", "--check", "-p", "android", "--package", "com.example.demoshop",
      "--out-dir", "android/app/src/test/java/com/example/demoshop", "--harness-dir", "android/app/src/test/java/com/example/demoshop"), None),
    ("jsonui-test generate branch-tests --check -p ios --module DemoShop --out-dir ios/Tests/Generated --harness-dir ios/Tests/BranchHarness",
     ("test_tools/jsonui-test", "generate", "branch-tests", "--check", "-p", "ios", "--module", "DemoShop",
      "--out-dir", "ios/Tests/Generated", "--harness-dir", "ios/Tests/BranchHarness"), None),
    ("jsonui-test validate tests", ("test_tools/jsonui-test", "validate", "tests"), None),
    ("jsonui-doc check", ("document_tools/jsonui-doc", "check"), None),
)

# 1a: the files opened, in order (relative to demo-shop), with the seconds each stays
GENERATED = (
    ("docs/screens/json/cart.spec.json", 1.6),
    ("docs/screens/layouts/cart.json", 1.1),
    ("ios/ios/View/Cart/CartGeneratedView.swift", 1.1),
    ("android/app/src/main/kotlin/com/example/demoshop/views/cart/CartGeneratedView.kt", 1.1),
    ("web/src/generated/components/Cart.tsx", 1.1),
    ("ios/ios/ViewModel/Protocol/CartViewModelProtocol.swift", 1.0),
    ("ios/ios/Model/Generated/CartLineDto.swift", 1.0),
    ("ios/Tests/Generated/CartBranchesTest.swift", 1.0),
)
HAND_WRITTEN = (("ios/ios/ViewModel/CartViewModel.swift", 3.0),)


def clean(text: str, root: Path) -> str:
    text = ANSI.sub("", text).replace("\r\n", "\n")
    text = "\n".join(line.rsplit("\r", 1)[-1] for line in text.split("\n"))   # a progress line's last state
    return text.replace(str(root) + os.sep, "").replace(str(root), ".")


def run_gates(jui_root: Path, shop: Path, home: Path) -> list:
    """Each gate run in the copy; [{shown, argv, code, output, keep}]."""
    env = {k: v for k, v in os.environ.items() if k not in ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR", "PYTHONPATH")}
    env.update(HOME=str(home), NO_COLOR="1", COLUMNS="110")
    out = []
    for shown, (launcher, *args), keep in GATES:
        exe = Path(jui_root) / launcher
        argv = [sys.executable, str(exe), *args]
        p = subprocess.run(argv, cwd=shop, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=900)
        out.append({"shown": shown, "argv": [str(exe), *args], "code": p.returncode, "output": clean(p.stdout, shop), "keep": keep})
    return out


def read_files(shop: Path) -> list:
    files = []
    for rel, sec in GENERATED + HAND_WRITTEN:
        text = (shop / rel).read_text(encoding="utf-8")
        files.append({"path": rel, "sec": sec, "text": text, "generated": "@generated" in text[:2000]})
    return files


STYLE = """
:root { --bg: #0d1117; --panel: #161b22; --line: #30363d; --text: #e6edf3; --sub: #8b949e; --accent: #58a6ff; --ok: #3fb950; --gen: #d29922; }
html, body { margin: 0; width: 1920px; height: 1080px; background: var(--bg); color: var(--text); overflow: hidden; }
body { font: 24px/1.45 Menlo, "SF Mono", Monaco, "Hiragino Sans", monospace; }
.win { position: absolute; inset: 0; display: flex; flex-direction: column; }
.tabs { display: flex; gap: 2px; background: var(--panel); border-bottom: 1px solid var(--line); height: 54px; align-items: stretch; padding-left: 12px; }
.tab { padding: 12px 20px; color: var(--sub); font-size: 19px; white-space: nowrap; border-right: 1px solid var(--line); }
.tab.on { color: var(--text); background: var(--bg); box-shadow: inset 0 -3px 0 var(--accent); }
.path { padding: 10px 28px; color: var(--sub); font-size: 18px; border-bottom: 1px solid var(--line); }
.code { flex: 1; overflow: hidden; position: relative; }
.lines { position: absolute; left: 0; right: 0; top: 0; padding: 10px 0; }
.ln { display: flex; white-space: pre; }
.ln i { display: inline-block; width: 80px; padding-right: 24px; text-align: right; color: #484f58; font-style: normal; flex: none; }
.ln.gen { color: var(--gen); }
.term { flex: 1; padding: 26px 34px; overflow: hidden; position: relative; }
.term .body { position: absolute; left: 34px; right: 34px; top: 26px; white-space: pre-wrap; word-break: break-all; font-size: 22px; line-height: 1.4; }
.term .cmd { color: var(--text); }
.term .p { color: var(--ok); }
.term .out { color: #c9d1d9; }
.caret { display: inline-block; width: 12px; height: 26px; background: var(--text); vertical-align: -4px; }
"""

EDITOR_JS = """
const FILES = __DATA__;
const T0 = __T0__, LINE_PX = 34.8;
const tabs = document.getElementById('tabs'), path = document.getElementById('path'), lines = document.getElementById('lines');
let shown = -1;
function esc(s) { return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]); }
function open(i) {
  const f = FILES[i];
  tabs.innerHTML = FILES.slice(0, i + 1).slice(-5).map((g) => `<div class="tab${g === f ? ' on' : ''}">${esc(g.path.split('/').pop())}</div>`).join('');
  path.textContent = f.path;
  lines.innerHTML = f.text.split('\\n').map((l, n) => `<div class="ln${l.includes('@generated') ? ' gen' : ''}"><i>${n + 1}</i>${esc(l) || ' '}</div>`).join('');
  shown = i;
}
window.render = (t) => {
  let at = t - T0, i = 0;
  while (i < FILES.length - 1 && at >= FILES[i].sec) { at -= FILES[i].sec; i += 1; }
  if (i !== shown) open(i);
  const f = FILES[i], rows = f.text.split('\\n').length, view = Math.floor((1080 - 120) / LINE_PX);
  const room = Math.max(0, rows - view), k = Math.min(1, Math.max(0, (at - 0.4) / Math.max(0.1, f.sec - 0.4)));
  lines.style.transform = `translateY(${-Math.round(Math.min(room, view * 0.6 * f.sec) * LINE_PX * k * k * (3 - 2 * k))}px)`;
};
"""

TERM_JS = """
const GATES = __DATA__;
const T0 = __T0__, T1 = __T1__, LEAD = 0.3, PROMPT = __PROMPT__;
const body = document.getElementById('body'), term = body.parentElement;
function esc(s) { return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]); }
const slot = (T1 - T0 - LEAD) / GATES.length;
const prompt = `<span class="p">${esc(PROMPT)}</span>`, caret = '<span class="caret"></span>';
window.render = (t) => {
  // each gate has an equal slot: typed in its first 35 %, its output shown line by line in the next 30 %, then held
  const at = t - T0 - LEAD;
  let h = '', done = true, keepIn = -1;
  for (let i = 0; i < GATES.length; i++) {
    const g = GATES[i], s = at - i * slot, typing = slot * 0.35;
    h += prompt;
    if (s < 0) { h += caret; done = false; break; }
    h += `<span class="cmd">${esc(g.shown.slice(0, Math.floor(g.shown.length * Math.min(1, s / typing))))}</span>`;
    if (s < typing + 0.15) { h += caret; done = false; break; }
    const out = g.output.replace(/\\n+$/, '').split('\\n'), r = Math.min(1, (s - typing - 0.15) / (slot * 0.3));
    const keep = g.keep ? new RegExp(g.keep) : null;
    h += '\\n' + out.slice(0, Math.ceil(out.length * r)).map((l) => (keep && keep.test(l) ? `<span class="out keep">${esc(l)}</span>` : `<span class="out">${esc(l)}</span>`)).join('\\n') + '\\n';
    keepIn = keep ? i : -1;
    if (r < 1) { done = false; break; }
  }
  if (done) h += prompt + caret;
  body.innerHTML = h;
  // the window scrolls as a terminal does (the newest line at the bottom); while the last gate shown has a kept line,
  // the scroll stops where that line is still in view
  const room = term.clientHeight - 52, over = Math.max(0, body.scrollHeight - room);
  const k = keepIn >= 0 ? body.querySelector('.keep') : null;
  body.style.transform = `translateY(${-Math.min(over, k ? k.offsetTop : over)}px)`;
};
"""


def page_html(kind: str, data, t0: float, t1: float) -> str:
    js = (EDITOR_JS if kind == "1a" else TERM_JS).replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace(
        "__T0__", repr(t0)).replace("__T1__", repr(t1)).replace("__PROMPT__", json.dumps(PROMPT))
    if kind == "1a":
        inner = '<div class="tabs" id="tabs"></div><div class="path" id="path"></div><div class="code"><div class="lines" id="lines"></div></div>'
    else:
        inner = '<div class="term"><div class="body" id="body"></div></div>'
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(kind)}</title><style>{STYLE}</style></head>'
            f'<body><div class="win">{inner}</div><script>{js}</script></body></html>')


async def capture_term(pw, chapter_id: str, bounds: tuple, out_root: Path, lang: str, jui_root: Path, demo_shop: Path,
                       keep: bool = False) -> dict:
    """1a or 1b into out_root/<lang>/<id>/%05d.png; returns its manifest (also written beside the frames)."""
    start, end = bounds
    out = Path(out_root) / lang / chapter_id
    res = {"chapter": chapter_id, "lang": lang, "start": start, "end": end, "frames": 0, "ok": False, "jui_root": str(jui_root)}
    base = Path(tempfile.mkdtemp(prefix="jui-promo-term-", dir="/tmp")).resolve()
    data = None
    try:
        shop = copy_demo_shop(base / "work" / "demo-shop", lang, demo_shop)
        if chapter_id == "1b":
            (base / "home").mkdir()
            data = run_gates(jui_root, shop, base / "home")
            res["gates"] = [{k: g[k] for k in ("shown", "argv", "code")} for g in data]
        else:
            data = read_files(shop)
            res["files"] = [f["path"] for f in data]
        doc = page_html(chapter_id, data, start, end)
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            await page.set_content(doc)
            await page.evaluate("() => document.fonts.ready")
            out.mkdir(parents=True, exist_ok=True)
            for old in out.glob("*.png"):
                old.unlink()
            n = frame_count(start, end)
            for i in range(n):
                await page.evaluate("(t) => window.render(t)", frame_time(start, i))
                await page.screenshot(path=str(out / f"{i:05d}.png"))
            res["frames"] = n
            res["ok"] = True
        finally:
            await browser.close()
        if chapter_id == "1b":
            # what was run and what it printed, kept beside the frames (the ticket's arm: 1b's text is the output)
            (out / "gates.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except Exception as e:  # noqa: BLE001 - the chapter fails with its reason; the next one is still captured
        res["error"] = f"{type(e).__name__}: {e}"
    finally:
        if not keep:
            cleanup(base)
    (out / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return res
