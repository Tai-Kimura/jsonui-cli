"""Capture the promo video's real-app chapters as numbered frames (ticket 2026-10-21-viz-promo-replay-and-capture-tool).

    python tools/viz_promo/run.py --lang ja --chapters hook,2,3,4 --jui-root ~/resource/jsonui-cli
    python tools/viz_promo/run.py --lang en --chapters 1a,1b --out /tmp/caps --jui-root PATH --promo PATH

Writes <out>/<lang>/<chapter>/00000.png … (frame 0 = the chapter's start, (end - start) x 30 frames, the bounds from
<promo>/src/timeline.json) and a manifest.json beside them. --out defaults to <promo>/public/captures, where the
promo's CaptureSlot reads them. --jui-root is the jsonui-cli checkout whose jui_tools/bin/jui serves and whose
forward.py takes the hooks (a tree with the server room's flow player for chapter 4, with the cost view for 5).
A chapter whose feature the tree lacks is reported and skipped; the others are captured.

One capture at a time on the machine: it waits for the viz e2e's lock (e2e_lock.py), so it never runs beside a
browser-test run, whose timing it would spoil. Run it with the Python the viz e2e uses (Playwright and the server's
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

from viz_promo.timeline import ALL, TERM_CHAPTER_IDS, chapters, check_bounds, promo_timeline  # noqa: E402

PROMO = Path.home() / "resource" / "jsonui-promo"
DEMO_SHOP = Path.home() / "resource" / "jsonui-demo-shop"


def parse(argv=None):
    ap = argparse.ArgumentParser(description="Capture the promo video's real-app chapters as numbered frames")
    ap.add_argument("--lang", choices=["ja", "en"], required=True)
    ap.add_argument("--chapters", default=",".join(ALL), help=f"comma-separated, of {', '.join(ALL)} (default: all)")
    ap.add_argument("--jui-root", required=True, type=Path, help="the jsonui-cli checkout to serve and forward with")
    ap.add_argument("--promo", type=Path, default=PROMO, help=f"the jsonui-promo project (default {PROMO})")
    ap.add_argument("--out", type=Path, default=None, help="where the frames go (default <promo>/public/captures)")
    ap.add_argument("--demo-shop", type=Path, default=DEMO_SHOP, help=f"the demo-shop workdir copied into the rooms (default {DEMO_SHOP})")
    ap.add_argument("--theme", choices=["dark", "light"], default="dark")
    ap.add_argument("--sky-time", default="14:00", help="the hour the page's sky shows (HH:MM), or 'real'")
    ap.add_argument("--keep", action="store_true", help="keep each chapter's temporary HOME and rooms (for debugging)")
    a = ap.parse_args(argv)
    a.chapters = [c.strip() for c in a.chapters.split(",") if c.strip()]
    unknown = [c for c in a.chapters if c not in ALL]
    if unknown:
        ap.error(f"unknown chapter(s) {', '.join(unknown)}; known: {', '.join(ALL)}")
    if not (a.jui_root / "jui_tools" / "bin" / "jui").is_file():
        ap.error(f"--jui-root {a.jui_root}: no jui_tools/bin/jui there")
    a.out = a.out or a.promo / "public" / "captures"
    return a


async def main_async(a) -> int:
    from playwright.async_api import async_playwright
    from viz_promo.capture import capture_chapter
    from viz_promo.term import capture_term

    promo = promo_timeline(a.promo)
    drift = check_bounds(promo)
    if drift:
        print("the promo's timeline moved since the script was written (events may fall outside their chapter):\n  " + "\n  ".join(drift), file=sys.stderr)
        return 2
    script = chapters(a.lang)
    results = []
    async with async_playwright() as pw:
        for cid in a.chapters:
            print(f"{a.lang}/{cid}: capturing", flush=True)
            if cid in TERM_CHAPTER_IDS:
                r = await capture_term(pw, cid, promo[cid], a.out, a.lang, a.jui_root, a.demo_shop, keep=a.keep)
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


def main(argv=None) -> int:
    a = parse(argv)
    import os

    sys.path.append(str(TOOLS / "viz_e2e"))
    from e2e_lock import hold
    fd = hold()   # held until this process exits
    try:
        return asyncio.run(main_async(a))
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
