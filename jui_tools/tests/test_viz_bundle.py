"""jui viz: /app.js assembly (jui_cli/viz/bundle.py) and the shipped web files (jui_cli/viz/web/).

The browser behaviour itself is checked outside pytest (tools/viz_e2e/, plan 10 §6); these arms pin what can be
read without a browser: the parts and their order per mode, the e2e hook only on request, the page's CSP shape
(no inline script but the import map, no on* attributes), nothing fetched from outside, and the vendored files
still being the ones VENDOR.md records.
"""

from __future__ import annotations

import hashlib
import re
from importlib import resources

import pytest

from jui_cli.viz import bundle

WEB = resources.files("jui_cli.viz").joinpath("web")


def web_text(*parts):
    return WEB.joinpath(*parts).read_text(encoding="utf-8")


def test_each_mode_is_its_parts_in_order():
    assert bundle.parts("demo", e2e=False) == ("10-robot-core.js", "20-core.js", "30-source-demo.js",
                                               "40-scene.js", "50-panel.js", "60-log.js", "70-main.js")
    assert bundle.parts("live", e2e=False) == ("10-robot-core.js", "20-core.js", "25-net.js", "30-source-live.js",
                                               "40-scene.js", "50-panel.js", "60-log.js", "70-main.js")


def test_build_joins_the_parts_in_that_order_with_a_marker_each():
    for mode in bundle.MODES:
        js = bundle.build(mode, e2e=False)
        marks = re.findall(r"^// ---- web/js/(\S+) ----$", js, re.M)
        assert tuple(marks) == bundle.parts(mode, e2e=False)
        for name in marks:
            assert web_text("js", name) in js


def test_the_demo_has_no_socket_and_the_live_view_no_script():
    demo, live = bundle.build("demo", e2e=False), bundle.build("live", e2e=False)
    assert "new WebSocket(" not in demo and "new WebSocket(" in live
    # The demo script's own names (its loop, its still states) stay out of the live bundle.
    for name in ("const LOOP = 84", "const STILL = {", "function computeSpecs("):
        assert name in demo and name not in live


def test_the_e2e_hook_is_appended_only_when_asked():
    assert "window.__dbg" not in bundle.build("live", e2e=False)
    assert "window.__dbg" not in bundle.build("demo", e2e=False)
    for mode in bundle.MODES:
        assert bundle.build(mode, e2e=True).rstrip().endswith(web_text("js", "80-dbg.js").rstrip())


def test_the_environment_decides_by_default(monkeypatch):
    monkeypatch.delenv("JUI_VIZ_E2E", raising=False)
    assert "window.__dbg" not in bundle.build("demo")
    monkeypatch.setenv("JUI_VIZ_E2E", "1")
    assert "window.__dbg" in bundle.build("demo")
    monkeypatch.setenv("JUI_VIZ_E2E", "0")  # only "1" turns it on
    assert "window.__dbg" not in bundle.build("demo")
    assert bundle.dev_enabled({"JUI_VIZ_DEV": "1"}) and not bundle.dev_enabled({})


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="unknown mode 'debug'"):
        bundle.build("debug")


def test_every_part_is_read_from_the_package_not_the_checkout():
    for mode in bundle.MODES:
        for name in bundle.parts(mode, e2e=True):
            assert WEB.joinpath("js", name).is_file(), name


# ---- the page and its CSP (plan 05 §4, plan 07 §6) ----------------------------------------------------------

def test_the_page_has_one_inline_script_the_import_map_and_no_handlers():
    html = web_text("index.html")
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
    inline = [attrs for attrs, body in scripts if body.strip()]
    assert inline == [' type="importmap"']
    assert [attrs for attrs, body in scripts if not body.strip()] == [' type="module" src="/boot.js"']
    assert not re.search(r"\son[a-z]+\s*=", html), "an on* attribute would need 'unsafe-inline'"
    assert '<meta name="jui-viz-token" content="__JUI_VIZ_TOKEN__">' in html


def test_the_import_map_points_at_the_vendored_three():
    html = web_text("index.html")
    assert '"three": "/vendor/three-0.160.0/three.module.min.js"' in html
    assert '"three/addons/": "/vendor/three-0.160.0/addons/"' in html
    for rel in ("three.module.min.js", "addons/controls/OrbitControls.js", "addons/geometries/RoundedBoxGeometry.js"):
        assert WEB.joinpath("vendor", "three-0.160.0", *rel.split("/")).is_file()
    js = bundle.build("live", e2e=False)
    assert set(re.findall(r"from '([^']+)'", js)) == {"three", "three/addons/controls/OrbitControls.js",
                                                     "three/addons/geometries/RoundedBoxGeometry.js"}


def test_nothing_is_fetched_from_outside():
    """No absolute URL in what the page loads or runs (plan 07 §6). Vendor files are pinned by sha256 below."""
    texts = {"index.html": web_text("index.html"), "app.css": web_text("app.css"), "boot.js": web_text("boot.js")}
    for mode in bundle.MODES:
        texts[f"app.js ({mode})"] = bundle.build(mode, e2e=True)
    for name, text in texts.items():
        hits = [u for u in re.findall(r"(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}[^\s'\"`)]*", text, re.I)]
        assert hits == [], f"{name}: {hits[:5]}"
    css = texts["app.css"]
    assert "fonts.googleapis" not in css and "@import" not in css
    assert set(re.findall(r'url\("([^"]+)"\)', css)) == {"/fonts/JetBrainsMono-Medium.woff2", "/fonts/JetBrainsMono-Bold.woff2"}


def test_the_vendored_files_are_the_ones_vendor_md_records():
    md = web_text("vendor", "VENDOR.md")
    rows = re.findall(r"^\| `([^`]+)` \| `[^`]+` \| `([0-9a-f]{64})` \|$", md, re.M)
    assert len(rows) == 7
    for rel, digest in rows:
        parts = rel.split("/")
        f = WEB.joinpath(*(parts[1:] if parts[0] == ".." else ["vendor", *parts]))
        assert hashlib.sha256(f.read_bytes()).hexdigest() == digest, rel
    assert WEB.joinpath("vendor", "three-0.160.0", "LICENSE").is_file()
    assert WEB.joinpath("fonts", "OFL.txt").is_file()


# ---- every server string goes through esc() (plan 07 §6) --------------------------------------------------------
# The page builds HTML with template literals. A value the server sent (an id, a key, a file name, a status …)
# that lands in that HTML must go through esc() — text and attribute values alike — or a crafted session id
# breaks the markup (dd's P3 review: `"><img …` in session_id). This arm reads every ${…} inside an HTML template
# (a template with "<" or `="`, and every template nested in one) and fails on a bare reference to a field the
# server supplies. Declared here, so a new field is one line:
SERVER_FIELDS = {
    "id", "key", "list", "file", "device", "text", "status", "bucket", "name", "subject", "summary", "tool",
    "agent", "act", "room", "path", "who", "owner", "by", "realId", "label", "command", "statusText", "title",
    "cwd", "kind", "what", "screen", "project", "dep", "detail", "preview", "sentReason", "mode", "destination",
    "blockedBy", "task",
}
# Not listed on purpose — numbers the page or the server computes: at, start, seq, passed, length, rev.
# Bare identifiers that hold server strings where they are used — destructured names too (`([op, method, path]) =>`
# over a sheet's API rows). Found by printing every bare name that reaches the HTML and reading each by hand.
SERVER_NAMES = {"id", "who", "key", "where_id", "method", "op", "path", "r"}
# Parts that never take server data (the demo script, the robot model's canvases).
NOT_SERVER_PARTS = {"10-robot-core.js", "30-source-demo.js"}
# Reviewed exceptions: (file, expression) — each safe for the reason given.
SAFE_EXCEPTIONS = {
    ("50-panel.js", "where"): "the data-fk prefix argument ('s', 'p', 'k', 'tbd', 'rb'), never server data",
}


_ESCAPES = re.compile(r"(?:esc|CSS\.escape)\((?s:.*)\)$")


def _skip_string(src: str, i: int) -> int:
    """i at a quote; returns the index after the closing one (a JS string cannot run past its line)."""
    q, i = src[i], i + 1
    while i < len(src) and src[i] not in (q, "\n"):
        i += 2 if src[i] == "\\" else 1
    return i + 1


def _scan_code(src: str, i: int, out: list, html: bool, stop: str = "") -> int:
    """Reads code from i up to an unmatched `stop` (or the end); records the ${…} of every template it meets."""
    depth, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            i = _skip_string(src, i)
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            i = src.find("*/", i) + 2
        elif c == "`":
            i = _scan_template(src, i, out, html)
        elif c == "{":
            depth, i = depth + 1, i + 1
        elif c == "}":
            if not depth and stop == "}":
                return i
            depth, i = depth - 1, i + 1
        else:
            i += 1
    return i


def _scan_template(src: str, i: int, out: list, html: bool) -> int:
    """i at a backtick; records (expression, in_html) for each ${…} and returns the index after the closing one."""
    j, n, parts, exprs = i + 1, len(src), [], []
    while j < n and src[j] != "`":
        if src[j] == "\\":
            j += 2
        elif src.startswith("${", j):
            k = _scan_code(src, j + 2, [], False, stop="}")   # find the end first
            exprs.append((j + 2, k))
            j = k + 1
        else:
            parts.append(src[j])
            j += 1
    text = "".join(parts)
    here = html or "<" in text or '="' in text
    for a, b in exprs:
        expr = src[a:b].strip()
        out.append((expr, here))
        # Templates inside the expression are HTML too — unless the expression escapes its whole value (esc(…),
        # CSS.escape(…)): what is built in there is plain text, and escaping its parts again would show "&amp;".
        _scan_code(src[a:b], 0, out, here and not _ESCAPES.match(expr))
    return j + 1


def _templates(src: str):
    """(expression, in_html) for every ${…} in every template literal of src, nested ones included. A template is
    HTML when its own text has "<" or `="` (markup, or an attribute selector) or it sits inside such a template."""
    out: list = []
    _scan_code(src, 0, out, False)
    return out


def _top_level(expr: str):
    """Yields (index, char) for the characters of expr outside brackets, strings and templates."""
    depth, i, n = 0, 0, len(expr)
    while i < n:
        c = expr[i]
        if c in "\"'":
            i = _skip_string(expr, i)
            continue
        if c == "`":
            i = _scan_template(expr, i, [], False)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif not depth:
            yield i, c
        i += 1


def _outputs(expr: str) -> list[str]:
    """The parts of expr whose value can be what lands in the HTML: both branches of `c ? a : b` (not c), both
    sides of `a || b` and `a ?? b`, the right side of `a && b`; the expression itself otherwise."""
    expr = expr.strip()
    top = list(_top_level(expr))
    q = next((i for i, c in top if c == "?" and expr[i:i + 2] not in ("?.", "??") and expr[i - 1] != "?"), None)
    if q is not None:
        level, colon = 0, None
        for i, c in top:
            if i <= q:
                continue
            if c == "?" and expr[i:i + 2] not in ("?.", "??") and expr[i - 1] != "?":
                level += 1
            elif c == ":":
                if not level:
                    colon = i
                    break
                level -= 1
        if colon is not None:
            return _outputs(expr[q + 1:colon]) + _outputs(expr[colon + 1:])
    for op, both in (("||", True), ("??", True), ("&&", False)):
        cut = next((i for i, c in top if expr.startswith(op, i)), None)
        if cut is not None:
            return (_outputs(expr[:cut]) if both else []) + _outputs(expr[cut + 2:])
    return [expr]


def _is_ref(expr: str) -> bool:
    if not re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\[\d+\])*", expr):
        return False
    last = re.split(r"[.\[]", expr)[-1].rstrip("]")
    return last in SERVER_FIELDS if "." in expr else expr in SERVER_NAMES


def _bare_server_ref(expr: str) -> bool:
    """A field the server supplies reaches the HTML as it is: the whole expression, or one of its outputs."""
    return any(_is_ref(o) for o in _outputs(expr))


def test_server_strings_in_html_go_through_esc():
    bad = []
    for name in sorted(set(bundle.ORDER["live"]) | {"80-dbg.js"}):
        if name in NOT_SERVER_PARTS:
            continue
        for expr, html in _templates(web_text("js", name)):
            if html and _bare_server_ref(expr) and (name, expr) not in SAFE_EXCEPTIONS:
                bad.append(f"{name}: ${{{expr}}}")
    assert bad == [], "server strings into HTML without esc():\n" + "\n".join(sorted(set(bad)))


def test_the_esc_arm_sees_a_bare_id_and_passes_an_escaped_one():
    """The arm's own control: the shape dd reported is caught; esc() and numbers pass."""
    caught = [e for e, h in _templates('const a = `<button data-robot-open="${x.id}">${esc(x.name)}</button>`;') if h and _bare_server_ref(e)]
    assert caught == ["x.id"]
    nested = [e for e, h in _templates("const b = `<li>${ok ? `perm:${p.id}` : ''}</li>`;") if h and _bare_server_ref(e)]
    assert nested == ["p.id"]
    assert [e for e, h in _templates("const c = `<b>${esc(T.file)} ${n}</b>`; const d = `${x.list}#${x.id}`;") if h and _bare_server_ref(e)] == []
    # A branch of a ternary or a logical expression is an output too; the condition is not.
    branch = [e for e, h in _templates("const e = `<a data-open=\"${x ? p.task : 'none'}\">${who ? 'yes' : ''}${p.label || esc(p.name)}</a>`;") if h and _bare_server_ref(e)]
    assert branch == ["x ? p.task : 'none'", "p.label || esc(p.name)"]
