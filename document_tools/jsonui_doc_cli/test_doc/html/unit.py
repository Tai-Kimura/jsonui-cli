"""Unit contract (hand-written business logic test) HTML generation.

One page per `unitContracts.target`. The page shows what the spec DECLARES
and whether each face implements it — nothing about the test bodies, which
are hand-written and are not parsed. That line is deliberate: the mechanism
exists so the two faces cannot drift apart silently, and drift is a fact
about the SET of case names, not about what any body asserts.

The judgment itself is not made here. `jsonui_test_cli.unit_contracts` owns
it, and `jsonui-test generate unit-stubs --check` reads the same function, so
a case cannot be green on the site and red at the gate. A second
implementation here would be a second opinion, which is the one thing a
drift detector must not have.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .styles import get_unit_styles, get_toggle_script
from .sidebar import generate_screen_sidebar, escape_html
from ...reproducible import build_datetime


#: Per-face case states, in the order a reader should scan them, with the
#: label shown on the badge.
#:
#: ⚠️ `missing` and `never_runs` are different states and the page must not
#: merge them. `never_runs` is a method that EXISTS in the face's test source
#: but which the runner will never discover (an XCTest method without the
#: `test` prefix compiles, reads as present to any name scan, and executes
#: zero times). Rendering it as `missing` sends the reader to write a test
#: that is already written — and writing it again does not fix it, because
#: the name is what stops it running.
_STATUS_LABEL = {
    "implemented": "implemented",
    "missing": "missing",
    "never_runs": "never runs",
    "not_declared_for_face": "not declared",
    "undeclared": "undeclared",
}

#: What a status means, shown once under the table rather than repeated per
#: badge. A colour with no key is a colour the reader has to guess.
_STATUS_HELP = {
    "implemented": "declared in the spec and found in this face's test sources",
    "missing": "declared for this face, no implementation found — write it",
    "never_runs": "a method with this name exists but the runner will not discover it "
                  "(XCTest needs a 'test' prefix); it compiles, reads as present, and runs zero times",
    "not_declared_for_face": "this case does not name this face — nothing is expected here",
    "undeclared": "implemented in this face, declared in no spec",
}


def _status_badge(status: str) -> str:
    """One badge. An unrecognised status renders as itself, not as blank.

    A status this page does not know about is a contract change, and showing
    an empty cell for it would make the page look complete while saying
    nothing — the failure mode the whole section exists to prevent.
    """
    label = _STATUS_LABEL.get(status, status or "unknown")
    css = status if status in _STATUS_LABEL else "unknown"
    return f"<span class='status status-{escape_html(css)}'>{escape_html(label)}</span>"


def generate_unit_html(
    target: dict,
    platforms: list[str],
    spec_href_fn=None,
    all_tests_nav: dict | None = None,
    current_path: str | None = None,
    unscannable: dict[str, str] | None = None,
    undiscoverable: dict[str, list[str]] | None = None,
) -> str:
    """HTML for one unit contract target.

    Args:
        target: one entry of ``unit_contract_pages()["targets"]``
        platforms: every face the project compares, so a face with no cases
            on this target still appears as a column rather than vanishing
        spec_href_fn: ``(screen, spec_file) -> href or None``. The site
            layout is the caller's knowledge, not this module's — the same
            split screen.py uses for its description resolver.
        all_tests_nav: navigation data for the sidebar
        current_path: this page's path, for sidebar highlighting
        unscannable: face -> why that face could not be compared at all

    Returns:
        Complete HTML string
    """
    name = str(target.get("target") or "Unit")
    cases = target.get("cases") or []
    faces = target.get("faces") or {}
    screens = target.get("screens") or []
    spec_files = target.get("spec_files") or []
    unscannable = unscannable or {}

    case_displays = [str(c.get("name") or "case") for c in cases]

    html_parts = _get_html_header(name)
    html_parts.extend(generate_screen_sidebar(name, case_displays, all_tests_nav, current_path))

    html_parts.append("  <main class='main-content'>")
    html_parts.append(f"    <h1>{escape_html(name)}</h1>")
    html_parts.append(
        "    <p class='test-description'>Hand-written business logic tests declared by "
        "<code>unitContracts</code>. The spec declares which cases exist and on which "
        "faces; the bodies are written by hand and are not parsed here.</p>"
    )

    # Where the declaration comes from. A split screen declares through more
    # than one file, so this is a list even when it is usually one entry.
    html_parts.append("    <div class='info'>")
    if screens:
        links = []
        for i, screen in enumerate(screens):
            spec_file = spec_files[i] if i < len(spec_files) else None
            href = spec_href_fn(screen, spec_file) if spec_href_fn else None
            if href:
                links.append(f"<a href='{escape_html(href)}'>{escape_html(str(screen))}</a>")
            else:
                links.append(f"<code>{escape_html(str(screen))}</code>")
        label = "Declared in" if len(links) == 1 else f"Declared in ({len(links)} specs)"
        html_parts.append(f"      <strong>{label}:</strong> {', '.join(links)}<br>")
    html_parts.append(
        f"      <strong>Faces:</strong> {escape_html(', '.join(platforms)) or 'none'}<br>"
    )
    html_parts.append(f"      <strong>Cases declared:</strong> {len(cases)}<br>")
    html_parts.append(
        f"      <strong>Generated:</strong> {build_datetime().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    html_parts.append("    </div>")

    # A face that could not be compared at all is not a face with zero
    # problems. Saying so here keeps "0 missing" from reading as "checked".
    for face in platforms:
        if face in unscannable:
            html_parts.append(
                f"    <div class='not-checked'><strong>{escape_html(face)}: NOT CHECKED</strong><br>"
                f"{escape_html(str(unscannable[face]))}</div>"
            )

    # Per-face roll-up
    if platforms:
        html_parts.append("    <h2>Implementation status by face</h2>")
        # Scoped to THIS target, and every declared case falls in exactly one
        # of the three states after it. `unit-stubs --check` prints a
        # per-face line counting every test method it found in the face's
        # sources, including ones no spec declares, so its `implemented` is a
        # larger number over a different set. Saying which set this is stops
        # the two from reading as a contradiction.
        html_parts.append(
            "    <p class='denominator'>Cases declared by this target only. "
            "Implemented + Missing + Never runs = Declared, per face.</p>"
        )
        html_parts.append("    <table class='face-table'>")
        # No `undeclared` column: a case implemented but declared nowhere has
        # no target to belong to (the target name comes from the declaration),
        # so it is a project-level fact and lives on the index. Putting a
        # column here would either be always zero or attribute a stray test to
        # a target by guessing from its filename.
        html_parts.append(
            "      <tr><th>Face</th><th>Declared</th><th>Implemented</th>"
            "<th>Missing</th><th>Never runs</th></tr>"
        )
        for face in platforms:
            entry = faces.get(face) or {}
            if face in unscannable:
                html_parts.append(
                    f"      <tr><td><code>{escape_html(face)}</code></td>"
                    f"<td colspan='4'>not checked</td></tr>"
                )
                continue
            cells = []
            for key in ("declared", "implemented", "missing", "never_runs"):
                n = len(entry.get(key) or [])
                css = "num zero" if n == 0 else "num"
                cells.append(f"<td class='{css}'>{n}</td>")
            html_parts.append(
                f"      <tr><td><code>{escape_html(face)}</code></td>{''.join(cells)}</tr>"
            )
        html_parts.append("    </table>")

    # Cases
    if cases:
        html_parts.append("    <h2>Declared cases</h2>")
        html_parts.append("    <table>")
        header = ["<th>#</th>", "<th>Case</th>", "<th>Intent</th>"]
        header.extend(f"<th>{escape_html(f)}</th>" for f in platforms)
        html_parts.append(f"      <tr>{''.join(header)}</tr>")
        for i, case in enumerate(cases, 1):
            case_name = str(case.get("name") or f"case {i}")
            intent = str(case.get("intent") or "")
            status = case.get("status") or {}
            # Built outside the f-string: a backslash in an f-string
            # expression is a SyntaxError before 3.12, and this package
            # declares >=3.10 (CI runs 3.11).
            intent_cell = escape_html(intent) if intent else "<span class='zero'>&mdash;</span>"
            row = [
                f"<td>{i}</td>",
                f"<td id='case-{i}'><code>{escape_html(case_name)}</code></td>",
                f"<td>{intent_cell}</td>",
            ]
            for face in platforms:
                row.append(f"<td>{_status_badge(str(status.get(face) or 'unknown'))}</td>")
            html_parts.append(f"      <tr>{''.join(row)}</tr>")
        html_parts.append("    </table>")

        used = {str(c.get("status", {}).get(f) or "unknown") for c in cases for f in platforms}
        legend = [s for s in _STATUS_LABEL if s in used]
        if legend:
            html_parts.append("    <div class='notes'>")
            for s in legend:
                html_parts.append(
                    f"      {_status_badge(s)} {escape_html(_STATUS_HELP[s])}<br>"
                )
            html_parts.append("    </div>")
    else:
        html_parts.append(
            "    <div class='problem'>This target declares no readable case. A "
            "misspelled key inside <code>unitContracts</code> drops the declaration "
            "silently, so an empty target is worth checking rather than ignoring.</div>"
        )

    # Implementation files, per face. Rendered as paths rather than links:
    # the sources live outside the generated site, so a link would resolve
    # against the site root and 404 — silently, which is worse than plain
    # text because a broken link looks like a working one until it is clicked.
    files_by_face = [(f, (faces.get(f) or {}).get("files") or []) for f in platforms]
    if any(files for _, files in files_by_face):
        html_parts.append("    <h2>Implementation files</h2>")
        for face, files in files_by_face:
            if not files:
                continue
            html_parts.append(f"    <h3>{escape_html(face)}</h3>")
            html_parts.append("    <ul class='impl-files'>")
            for path in files:
                html_parts.append(f"      <li><code>{escape_html(str(path))}</code></li>")
            html_parts.append("    </ul>")

    # Methods that exist but never run, named so the reader can fix the name
    # rather than rewrite the test. These are RAW method names as found in the
    # source (project-level, from the top-level `undiscoverable`), which is
    # what the reader has to go and rename — the declared case name would not
    # locate the line.
    undiscoverable = undiscoverable or {}
    for face in platforms:
        never = undiscoverable.get(face) or []
        if not never:
            continue
        html_parts.append(
            f"    <div class='not-checked'><strong>{escape_html(face)}: "
            f"{len(never)} method(s) will never run</strong><br>"
            f"{escape_html(_STATUS_HELP['never_runs'])}<ul class='impl-files'>"
            + "".join(f"<li><code>{escape_html(str(n))}</code></li>" for n in never)
            + "</ul></div>"
        )

    html_parts.append("  </main>")
    html_parts.append("</body>")
    html_parts.append("</html>")

    return "\n".join(html_parts)


def _get_html_header(title: str) -> list[str]:
    """HTML header with styles for unit contract pages."""
    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        f"  <title>{escape_html(title)} - Unit Contracts</title>",
        "  <meta charset='utf-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1'>",
        "  <style>",
    ]
    parts.extend(get_unit_styles())
    parts.append("  </style>")
    parts.extend(get_toggle_script())
    parts.extend([
        "</head>",
        "<body>",
    ])
    return parts
