"""Contract-check report page (docs ⇔ implementation drift).

Rendered by `generate html` when a `.check-report.json` artifact exists
(written by `jsonui-doc check`). Pure renderer: this module never runs
checks, connects to databases, or executes code — absence of a report
simply means the page is not generated.
"""

from __future__ import annotations

from .sidebar import escape_html
from .styles import get_nav_sidebar_scroll_script, get_nav_sidebar_styles


def _rel_root(doc_path: str) -> str:
    depth = doc_path.count("/")
    return "../" * depth if depth else "./"


_STATUS_LABELS = {
    "mismatch": ("MISMATCH", "#d93025"),
    "missing_in_impl": ("DOC ONLY", "#e37400"),
    "missing_in_doc": ("IMPL ONLY", "#b05a00"),
    "skipped": ("SKIPPED", "#888"),
    "ok": ("OK", "#188038"),
}


def generate_check_report_html(
    report,
    title: str,
    current_doc_path: str,
    category_docs: list[dict] | None = None,
    stale: bool = False,
) -> str:
    """Render one CheckReport as a standalone HTML page."""
    rel_root = _rel_root(current_doc_path)
    s = report.summary
    problems = [r for r in report.results if r.status != "ok"]
    clean = not report.has_mismatch

    parts = [
        "<!DOCTYPE html>",
        "<html lang='ja'>",
        "<head>",
        "  <meta charset='UTF-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"  <title>{escape_html(title)}</title>",
        "  <style>",
        "    * { margin: 0; padding: 0; box-sizing: border-box; }",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',"
        " Roboto, sans-serif; background: #f5f5f5; color: #333;"
        " line-height: 1.6; display: flex; }",
        *get_nav_sidebar_styles(),
        "    .main { margin-left: 280px; padding: 30px 40px; max-width: 1100px;"
        " width: 100%; }",
        "    h1 { font-size: 1.5em; margin-bottom: 6px; }",
        "    .banner { border-radius: 8px; padding: 16px 20px; margin: 16px 0;"
        " border: 1px solid; }",
        "    .banner.ok { background: #e6f4ea; border-color: #188038; }",
        "    .banner.bad { background: #fce8e6; border-color: #d93025; }",
        "    .banner .headline { font-size: 1.15em; font-weight: 600; }",
        "    .banner .meta { color: #555; font-size: 0.9em; margin-top: 4px; }",
        "    .stale { background: #fef7e0; border: 1px solid #f9ab00;"
        " border-radius: 8px; padding: 12px 20px; margin: 12px 0;"
        " font-size: 0.95em; }",
        "    .disclaimer { color: #666; font-size: 0.85em; margin: 10px 0 20px; }",
        "    .chips { display: flex; gap: 10px; flex-wrap: wrap; margin: 14px 0; }",
        "    .chip { background: white; border: 1px solid #ddd;"
        " border-radius: 16px; padding: 4px 14px; font-size: 0.85em; }",
        "    table { width: 100%; border-collapse: collapse; background: white;"
        " border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px"
        " rgba(0,0,0,0.08); margin: 14px 0; }",
        "    th { background: #34495e; color: white; text-align: left;"
        " padding: 8px 12px; font-size: 0.85em; }",
        "    td { padding: 8px 12px; border-bottom: 1px solid #eee;"
        " font-size: 0.85em; vertical-align: top; }",
        "    td.code { font-family: 'SF Mono', Monaco, monospace;"
        " font-size: 0.8em; }",
        "    .status-badge { display: inline-block; padding: 2px 8px;"
        " border-radius: 4px; color: white; font-size: 0.75em;"
        " font-weight: 600; white-space: nowrap; }",
        "    .warnings { background: white; border-radius: 8px; padding: 14px"
        " 20px; margin: 14px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }",
        "    .warnings li { margin-left: 20px; font-size: 0.85em; color: #666; }",
        "  </style>",
        "</head>",
        "<body>",
        "  <aside class='sidebar'>",
        "    <div class='sidebar-header'>",
        f"      <a href='{rel_root}index.html' class='back-link'>"
        "&larr; Back to Index</a>",
        "    </div>",
    ]
    if category_docs:
        section_title = "Tables" if report.target_kind == "db" else "Documents"
        parts.extend([
            "    <nav class='sidebar-nav'>",
            "      <div class='nav-section'>",
            f"        <div class='nav-section-title'>{section_title}</div>",
            "        <ul class='nav-list'>",
        ])
        for doc in category_docs:
            if doc.get("path") == current_doc_path:
                continue
            parts.append(
                f"          <li><a href='{rel_root}{doc['path']}'>"
                f"{escape_html(doc.get('name', ''))}</a></li>"
            )
        parts.extend([
            "        </ul>",
            "      </div>",
            "    </nav>",
        ])
    parts.append("  </aside>")
    parts.append("  <main class='main'>")
    parts.append(f"    <h1>{escape_html(title)}</h1>")

    banner_cls = "ok" if clean else "bad"
    mismatch_total = s["mismatch"] + s["missing_in_impl"] + s["missing_in_doc"]
    headline = ("✓ ドキュメントと実装の宣言が一致しています" if clean
                else f"✗ {mismatch_total} 件のズレが検出されました")
    target_desc = f"{report.target_kind}:{report.target_name}"
    extra = ", ".join(f"{k}={v}" for k, v in report.target_extra.items())
    if extra:
        target_desc += f" ({extra})"
    parts.extend([
        f"    <div class='banner {banner_cls}'>",
        f"      <div class='headline'>{escape_html(headline)}</div>",
        f"      <div class='meta'>checker: {escape_html(report.checker)} ・ "
        f"対象: {escape_html(target_desc)} ・ 検証時刻: "
        f"{escape_html(report.executed_at)}</div>",
        "    </div>",
    ])
    if stale:
        parts.append(
            "    <div class='stale'>⚠ この検証の後にドキュメントが変更されて"
            "います。結果は古い可能性があります — <code>jsonui-doc check"
            "</code> を再実行してください。</div>"
        )
    parts.append(
        "    <div class='disclaimer'>この結果はチェッカー実行時点での照合です。"
        "実装側(実 DB / 実 API)のその後の変更は検出できません。"
        "また OpenAPI diff は実装が宣言するスキーマとの照合であり、"
        "実レスポンスの検証ではありません。</div>"
    )

    parts.append("    <div class='chips'>")
    for key in ("ok", "mismatch", "missing_in_impl", "missing_in_doc", "skipped"):
        parts.append(f"      <div class='chip'>{key}: <b>{s[key]}</b></div>")
    parts.append("    </div>")

    if problems:
        parts.extend([
            "    <table>",
            "      <thead><tr><th>Status</th><th>Target</th><th>Expected"
            "</th><th>Actual</th><th>Message</th></tr></thead>",
            "      <tbody>",
        ])
        for r in problems:
            label, color = _STATUS_LABELS.get(r.status, (r.status, "#666"))
            parts.append(
                "        <tr>"
                f"<td><span class='status-badge' style='background:{color}'>"
                f"{label}</span></td>"
                f"<td class='code'>{escape_html(r.target)}</td>"
                f"<td class='code'>{escape_html(r.expected or '')}</td>"
                f"<td class='code'>{escape_html(r.actual or '')}</td>"
                f"<td>{escape_html(r.message or '')}</td>"
                "</tr>"
            )
        parts.extend(["      </tbody>", "    </table>"])

    if report.warnings:
        parts.append("    <div class='warnings'><b>Warnings</b><ul>")
        for w in report.warnings:
            parts.append(f"      <li>{escape_html(w)}</li>")
        parts.append("    </ul></div>")

    parts.append("  </main>")
    parts.extend(get_nav_sidebar_scroll_script())
    parts.extend(["</body>", "</html>"])
    return "\n".join(parts)
