"""Capture the promo video's real-app chapters as numbered frames (ticket 2026-10-21-viz-promo-replay-and-capture-tool).

    python tools/viz_promo/run.py --lang ja --chapters hook,2,3,4 --jui-root ~/resource/jsonui-cli
    python tools/viz_promo/run.py --lang en --chapters 1a,1b --out /tmp/caps --jui-root PATH --promo PATH
    python tools/viz_promo/run.py --lang ja --measure-fps --jui-root PATH --out /tmp/fps     # frame intervals, 30 robots

Writes <out>/<lang>/<chapter>/00000.png … (frame 0 = the chapter's start, (end - start) x 30 frames, the bounds from
<promo>/src/timeline.json) and a manifest.json beside them. --out defaults to <promo>/public/captures, where the
promo's CaptureSlot reads them. A window segment inside a viz chapter (5-json: the load definition in the editor,
74–77 s) goes to a folder of its own, captured whenever its chapter is. --jui-root is the jsonui-cli checkout whose jui_tools/bin/jui serves and whose
forward.py takes the hooks (a tree with the server room's flow player for chapter 4, with the cost view for 5).
A chapter whose feature the tree lacks is reported and skipped; the others are captured.

One viz load at a time on the machine: before any serve or browser it takes --jui-root's viz e2e lock
(tools/viz_e2e/e2e_lock.py; from 2.3.16 a FIFO queue, never a priority ticket) and holds it until it exits, so it
never runs beside a browser-test run, whose timing it would spoil. Run it with the Python the viz e2e uses (Playwright and the server's
dependencies). Exit status 0 only when every chapter asked for was captured in full.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))   # viz_promo is a package under tools/ (viz_e2e has a rooms.py and a run.py too)

from viz_promo.timeline import ALL, BOARDS, CAPTURE_IDS, SEGMENTS, STANDALONE, T_CHAPTER_IDS, TERM_CHAPTER_IDS, chapters, check_bounds, promo_timeline  # noqa: E402

PROMO = Path.home() / "resource" / "jsonui-promo"
DEMO_SHOP = Path.home() / "resource" / "jsonui-demo-shop"


def parse(argv=None):
    ap = argparse.ArgumentParser(description="Capture the promo video's real-app chapters as numbered frames")
    ap.add_argument("--lang", choices=["ja", "en"], required=True)
    ap.add_argument("--chapters", default=",".join(ALL), help=f"comma-separated, of {', '.join(CAPTURE_IDS)} (default: all; "
                    "a chapter brings its window segments: 5 captures 5-json too)")
    ap.add_argument("--measure-fps", action="store_true", help="instead of capturing: the floor with every robot in real time, "
                    "frame intervals far and near (p50 / p90 / max ms) into <out>/fps-<lang>.json")
    ap.add_argument("--gpu", action="store_true", help="with --measure-fps: a headed window drawing through the GPU (opens on the screen)")
    ap.add_argument("--jui-root", required=True, type=Path, help="the jsonui-cli checkout to serve and forward with")
    ap.add_argument("--promo", type=Path, default=PROMO, help=f"the jsonui-promo project (default {PROMO})")
    ap.add_argument("--out", type=Path, default=None, help="where the frames go (default <promo>/public/captures)")
    ap.add_argument("--demo-shop", type=Path, default=DEMO_SHOP, help=f"the demo-shop workdir copied into the rooms (default {DEMO_SHOP})")
    ap.add_argument("--theme", choices=["dark", "light"], default="dark")
    ap.add_argument("--sky-time", default="14:00", help="the hour the page's sky shows (HH:MM), or 'real'")
    ap.add_argument("--keep", action="store_true", help="keep each chapter's temporary HOME and rooms (for debugging)")
    ap.add_argument("--no-lock", action="store_true", help="do not wait for the machine's viz e2e queue (when told to capture "
                    "beside a running e2e: the capture uses its own HOME, server and port either way)")
    a = ap.parse_args(argv)
    a.chapters = [c.strip() for c in a.chapters.split(",") if c.strip()]
    unknown = [c for c in a.chapters if c not in CAPTURE_IDS]
    if unknown:
        ap.error(f"unknown chapter(s) {', '.join(unknown)}; known: {', '.join(CAPTURE_IDS)}")
    for seg, (chapter, *_rest) in SEGMENTS.items():
        if chapter in a.chapters and seg not in a.chapters:
            a.chapters.insert(a.chapters.index(chapter), seg)
    for board, chapter in BOARDS.items():
        if chapter in a.chapters and board not in a.chapters:
            a.chapters.insert(a.chapters.index(chapter) + 1, board)
    if not (a.jui_root / "jui_tools" / "bin" / "jui").is_file():
        ap.error(f"--jui-root {a.jui_root}: no jui_tools/bin/jui there")
    a.out = a.out or a.promo / "public" / "captures"
    return a


async def main_async(a) -> int:
    from playwright.async_api import async_playwright
    from viz_promo.capture import capture_chapter, measure_fps
    from viz_promo.term import capture_term

    if a.measure_fps:
        async with async_playwright() as pw:
            r = await measure_fps(pw, a.lang, a.jui_root, a.demo_shop, a.out, theme=a.theme, gpu=a.gpu)
        print(f"WebGL: {r.get('webgl')}")
        for view in ("far", "near"):
            v = r.get(view) or {}
            print(f"{a.lang} {view}: {r.get('robotsShown')} robots, {v.get('frames')} frames, p50 {v.get('p50')} ms, p90 {v.get('p90')} ms, max {v.get('max')} ms")
        if r.get("error"):
            print(f"FAIL {r['error']}", file=sys.stderr)
        return 0 if not r.get("error") else 1

    promo = promo_timeline(a.promo)
    drift = check_bounds(promo)
    if drift:
        print("the promo's timeline moved since the script was written (events may fall outside their chapter):\n  " + "\n  ".join(drift), file=sys.stderr)
        return 2
    script = chapters(a.lang)
    results = []
    async with async_playwright() as pw:
        t_done = False
        for cid in a.chapters:
            if cid in T_CHAPTER_IDS:
                # T-a and T-b on one start of the stage's web app and mock server (--demo-shop: the stage, with its web
                # shell's node_modules installed)
                if t_done:
                    continue
                t_done = True
                from viz_promo.t_chapter import capture_t
                print(f"{a.lang}/T: capturing", flush=True)
                try:
                    t = await capture_t(pw, a.out, a.lang, {i: promo[i] for i in T_CHAPTER_IDS}, a.demo_shop, a.jui_root, keep=a.keep)
                    r = {"chapter": "T", "ok": True, "frames": t["Ta"]["frames"] + t["Tb"]["frames"], "t": t}
                except Exception as e:  # noqa: BLE001 — reported like a chapter's failure
                    r = {"chapter": "T", "ok": False, "frames": 0, "error": f"{type(e).__name__}: {e}"}
                results.append(r)
                print(f"{a.lang}/T: {'ok' if r['ok'] else 'FAIL'} {r['frames']} frames" + (f" — {r['error']}" if r.get("error") else ""), flush=True)
                continue
            print(f"{a.lang}/{cid}: capturing", flush=True)
            if cid in SEGMENTS:
                r = await capture_term(pw, cid, SEGMENTS[cid][1:3], a.out, a.lang, a.jui_root, a.demo_shop, keep=a.keep)
            elif cid in TERM_CHAPTER_IDS:
                r = await capture_term(pw, cid, promo[cid], a.out, a.lang, a.jui_root, a.demo_shop, keep=a.keep)
            elif cid in STANDALONE:
                r = await capture_chapter(pw, script[cid], STANDALONE[cid], a.out, a.lang, a.jui_root, a.demo_shop, theme=a.theme,
                                          sky_time=None if a.sky_time == "real" else a.sky_time, keep=a.keep)
            elif cid in BOARDS:
                r = await capture_chapter(pw, script[cid], promo[BOARDS[cid]], a.out, a.lang, a.jui_root, a.demo_shop, theme=a.theme,
                                          sky_time=None if a.sky_time == "real" else a.sky_time, keep=a.keep)
            else:
                r = await capture_chapter(pw, script[cid], promo[cid], a.out, a.lang, a.jui_root, a.demo_shop, theme=a.theme,
                                          sky_time=None if a.sky_time == "real" else a.sky_time, keep=a.keep)
            results.append(r)
            line = f"{a.lang}/{cid}: {'ok' if r['ok'] else 'FAIL'} {r['frames']} frames"
            if r.get("error"):
                line += f" — {r['error']}"
            for wline in r.get("warnings") or []:
                line += f"\n  warning: {wline}"
            for c in r.get("console") or []:
                line += f"\n  console: {c}"
            print(line, flush=True)
    (Path(a.out) / a.lang).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / a.lang / "run.json").write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0 if all(r["ok"] for r in results) else 1


def take_lock(jui_root: Path, what: str, say=print):
    """The machine's one viz load at a time: --jui-root's own viz e2e lock (its FIFO queue from 2.3.16), taken before
    any serve or browser starts and held until this process exits. Never a priority ticket. A tree without the lock
    module runs without it, and says so. Returns the lock's fd, or None."""
    import importlib.util
    path = Path(jui_root) / "jui_tools" / "tools" / "viz_e2e" / "e2e_lock.py"
    if not path.is_file():
        say(f"no viz e2e lock in {jui_root} (jui_tools/tools/viz_e2e/e2e_lock.py): running without the machine's queue")
        return None
    spec = importlib.util.spec_from_file_location("viz_promo_e2e_lock", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        return mod.hold(priority=False, only=[what])
    except TypeError:   # a lock from before 2.3.16: no queue, no ticket fields
        return mod.hold()


def main(argv=None) -> int:
    a = parse(argv)
    import os

    fd = None if a.no_lock else take_lock(a.jui_root, f"viz_promo {a.lang} {'fps' if a.measure_fps else ','.join(a.chapters)}")
    try:
        return asyncio.run(main_async(a))
    finally:
        if fd is not None:
            os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
