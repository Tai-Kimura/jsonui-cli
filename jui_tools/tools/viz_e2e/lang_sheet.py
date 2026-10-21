"""The English screen beside the Japanese one, in one file to open (ticket 2026-10-21-viz-english-screen-checks §2d).

    python3 tools/viz_e2e/lang_sheet.py <out of the ja run> <out of the en run> -o sheet.html

Each run's suites leave <out>/demo/<suite>/shots/<name>.png and shots.json (common.shot: the language the run was in
and screen_check's report). The sheet lays every shot out as Japanese | English, and under the English one what the
report found there: elements whose words do not fit, canvas words past the canvas or cut with "…", Japanese left on
the English page. The pictures are inside the file (data: URIs), so it opens anywhere and can be shared as is — what
the eye checks after the language switch is this sheet, not every screen. A shot one run has and the other lacks is
listed as such.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import sys
from pathlib import Path

LIMIT = 15 * 1024 * 1024   # a page to share stays under 16 MB


def shots(out: Path) -> dict[str, dict]:
    """name -> {png, language, report} for every shot under <out> (suite/name when two suites share a name)."""
    found: dict[str, dict] = {}
    for index in sorted(Path(out).rglob("shots/shots.json")):
        suite = index.parent.parent.name
        for name, entry in json.loads(index.read_text(encoding="utf-8")).items():
            png = index.parent / f"{name}.png"
            key = name if name not in found else f"{suite}/{name}"
            found[key] = {"png": png if png.exists() else None, "language": entry.get("language", ""),
                          "report": entry.get("report") or {}}
    return found


def _img(png: Path | None, alt: str) -> str:
    if png is None:
        return '<p class="none">no picture</p>'
    data = base64.b64encode(png.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{html.escape(alt)}" loading="lazy">'


def _list(title: str, items: list[str]) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{html.escape(i)}</li>" for i in items)
    return f'<details open><summary>{html.escape(title)} <b>{len(items)}</b></summary><ul>{lis}</ul></details>'


def findings(report: dict) -> dict[str, list[str]]:
    return {
        "keys": list(report.get("keys", [])),
        "overflow": [f"{o['at']} — “{o['text']}” ({o['over']}px over)" for o in report.get("overflow", [])],
        "overlap": [f"{o['a']} and {o['b']} cover each other ({o['w']}×{o['h']}px): “{o['text'][0]}” / “{o['text'][1]}”"
                    for o in report.get("overlap", [])],
        "canvas": [f"“{c['text']}” {'cut' if c['text'].endswith('…') else 'past the edge'} "
                   f"({c['left']}–{c['right']} of {c['canvas']}px, {c['font']})" for c in report.get("canvas", [])],
        "japanese": list(report.get("japanese", [])),
    }


CSS = """
:root { --bg: #f6f7f9; --card: #ffffff; --ink: #1d2433; --sub: #5b6475; --line: #d9dee7; --warn: #b42318; --mark: #fff4e5; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #10141b; --card: #171c25; --ink: #e6e9ef;
  --sub: #9aa3b5; --line: #2a3242; --warn: #ff8a7a; --mark: #2b2416; } }
:root[data-theme="dark"] { --bg: #10141b; --card: #171c25; --ink: #e6e9ef; --sub: #9aa3b5; --line: #2a3242; --warn: #ff8a7a; --mark: #2b2416; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 system-ui, sans-serif; }
main { max-width: 1400px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 22px; margin: 0 0 4px; } .lede { color: var(--sub); margin: 0 0 20px; }
table.sum { border-collapse: collapse; width: 100%; margin-bottom: 28px; background: var(--card); }
.sum th, .sum td { border: 1px solid var(--line); padding: 6px 8px; text-align: left; font-size: 13px; }
.sum td.n { text-align: right; } .sum td.hot { color: var(--warn); font-weight: 700; }
section { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin-bottom: 20px; }
section h2 { font-size: 17px; margin: 0 0 12px; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 760px) { .pair { grid-template-columns: 1fr; } }
figure { margin: 0; } figcaption { font-size: 12px; color: var(--sub); margin-bottom: 4px; }
img { width: 100%; height: auto; border: 1px solid var(--line); border-radius: 4px; display: block; }
.none { color: var(--sub); font-style: italic; }
details { margin-top: 10px; } summary { cursor: pointer; font-weight: 600; } summary b { color: var(--warn); }
ul { margin: 6px 0 0; padding-left: 20px; font-size: 13px; overflow-wrap: anywhere; }
.keys summary { color: var(--warn); } .ok { color: var(--sub); font-size: 13px; margin-top: 8px; }
"""


def build(ja_out: Path, en_out: Path) -> str:
    ja, en = shots(ja_out), shots(en_out)
    names = sorted(set(ja) | set(en))
    rows, sections = [], []
    for name in names:
        f = findings((en.get(name) or {}).get("report") or {})
        counts = {k: len(v) for k, v in f.items()}
        cells = "".join(f'<td class="n{" hot" if counts[k] else ""}">{counts[k]}</td>'
                        for k in ("keys", "overflow", "overlap", "canvas", "japanese"))
        rows.append(f'<tr><td><a href="#s-{html.escape(name)}">{html.escape(name)}</a></td>{cells}</tr>')
        lists = (_list("Keys shown as themselves (a failure)", f["keys"]).replace("<details", '<details class="keys"', 1)
                 + _list("Words that do not fit their element", f["overflow"])
                 + _list("Boxes of words covering each other", f["overlap"])
                 + _list("Canvas words past the canvas or cut with …", f["canvas"])
                 + _list("Japanese left on the English page", f["japanese"]))
        sections.append(
            f'<section id="s-{html.escape(name)}"><h2>{html.escape(name)}</h2><div class="pair">'
            f'<figure><figcaption>日本語 (ja)</figcaption>{_img((ja.get(name) or {}).get("png"), name + " ja")}</figure>'
            f'<figure><figcaption>English (en)</figcaption>{_img((en.get(name) or {}).get("png"), name + " en")}</figure>'
            f'</div>{lists or "<p class=ok>Nothing found on the English page.</p>"}</section>')
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>viz English check</title><style>{CSS}</style></head><body><main>"
            "<h1>viz English check</h1>"
            f"<p class=\"lede\">{len(names)} screens, Japanese beside English. Under each English screen: what the page "
            "reported there. Keys shown as themselves fail the browser tests; the rest is for the eye.</p>"
            "<table class=\"sum\"><thead><tr><th>Screen</th><th>Keys</th><th>Overflow</th><th>Overlap</th><th>Canvas</th>"
            f"<th>Japanese left</th></tr></thead><tbody>{''.join(rows)}</tbody></table>{''.join(sections)}"
            "</main></body></html>")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The English screen beside the Japanese one, in one HTML file")
    ap.add_argument("ja_out", type=Path, help="--out of the run with JUI_VIZ_LANGUAGE=ja")
    ap.add_argument("en_out", type=Path, help="--out of the run with JUI_VIZ_LANGUAGE=en")
    ap.add_argument("-o", "--output", type=Path, default=Path("lang-sheet.html"))
    a = ap.parse_args(argv)
    page = build(a.ja_out, a.en_out)
    a.output.write_text(page, encoding="utf-8")
    size = a.output.stat().st_size
    print(f"{a.output}: {size / 1024 / 1024:.1f} MB")
    if size > LIMIT:
        print(f"warning: over {LIMIT // 1024 // 1024} MB — take fewer or smaller shots (clip) to share it", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
