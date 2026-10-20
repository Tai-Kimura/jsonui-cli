"""``jui viz export-demo --out DIR``: the demo page as a static folder (P8).

For the documentation site: the page with the demo data source, no server.
Written with relative paths so it works from any folder of a static site
(not from file://, where module loading stops). What a live page has and a
static copy must not — the token meta tag, the WebSocket client, the e2e
hook (window.__dbg) — is left out, and the export checks that it did.
"""
from __future__ import annotations

import re
import shutil
from importlib import resources
from pathlib import Path

from . import bundle, i18n

TOKEN_META = re.compile(r'\s*<meta name="jui-viz-token" content="__JUI_VIZ_TOKEN__">')
LIVE_ONLY = ("__JUI_VIZ_TOKEN__", "jui-viz-token", "new WebSocket", "__dbg")


class ExportError(Exception):
    pass


def _web():
    return resources.files("jui_cli.viz") / "web"


#: Left out of the export: Mermaid (3.6 MB) draws the live view's diagrams from specs; the demo's sheets are written by
#: hand, without the spec structure its diagrams are built from, and show the boxes instead (2.3.5).
NOT_EXPORTED = ("mermaid-",)


def _copy_tree(src, dst: Path) -> int:
    count = 0
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name.startswith(".") or item.name.startswith(NOT_EXPORTED):
            continue
        if item.is_dir():
            count += _copy_tree(item, dst / item.name)
        else:
            (dst / item.name).write_bytes(item.read_bytes())
            count += 1
    return count


def page_html(language: str = i18n.DEFAULT_LANGUAGE) -> str:
    html = (_web() / "index.html").read_text(encoding="utf-8")
    html = i18n.page_html(html, i18n.load(language, use_env=False))
    html = TOKEN_META.sub("", html)
    html = html.replace('href="/app.css"', 'href="app.css"')
    html = html.replace('"/vendor/', '"./vendor/')
    html = html.replace('<script type="module" src="/boot.js"></script>', '<script type="module" src="app.js"></script>')
    return html


def export(out: Path, language: str = i18n.DEFAULT_LANGUAGE) -> dict:
    """Write the demo into ``out`` (created; must be empty if it exists), its words in ``language``. Returns a summary."""
    if language not in i18n.LANGUAGES:
        raise ExportError(f"--lang must be one of {', '.join(i18n.LANGUAGES)}")
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ExportError(f"{out} is not empty (name an empty folder or a path that does not exist)")
    out.mkdir(parents=True, exist_ok=True)
    html = page_html(language)
    app = bundle.build("demo", e2e=False)
    css = (_web() / "app.css").read_text(encoding="utf-8").replace('url("/fonts/', 'url("fonts/')
    for name, text in (("index.html", html), ("app.js", app), ("app.css", css)):
        leaked = [m for m in LIVE_ONLY if m in text]
        if leaked:
            shutil.rmtree(out)
            raise ExportError(f"{name} still holds live parts: {', '.join(leaked)}")
        absolute = re.findall(r'(?:src|href)="/(?!/)|url\("/', text)
        if absolute:
            shutil.rmtree(out)
            raise ExportError(f"{name} still holds absolute paths ({len(absolute)})")
        (out / name).write_text(text, encoding="utf-8")
    files = 3 + _copy_tree(_web() / "vendor", out / "vendor") + _copy_tree(_web() / "fonts", out / "fonts")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    return {"out": str(out), "files": files, "bytes": size}
