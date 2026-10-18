"""jui viz: /app.js assembly (jui_cli/viz/bundle.py) and the shipped web files (jui_cli/viz/web/).

The browser behaviour itself is checked outside pytest (tools/viz_e2e/, plan 10 §6); these arms pin what can be
read without a browser: the parts and their order per mode, the e2e hook only on request, the page's CSP shape
(no inline script but the import map, no on* attributes), nothing fetched from outside, and the vendored files
still being the ones VENDOR.md records.
"""

from __future__ import annotations

import collections
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


# ---- nothing reaches the HTML unescaped (plan 07 §6) -----------------------------------------------------------
# The page builds HTML from template literals. A value the server sent that lands in that HTML must go through esc(),
# or a crafted id / name / command breaks the markup (dd's P3 review). This arm is an allow-list: every ${…} in HTML is
# caught unless it is one of the forms below, so a new field, a .slice(), a String(x), a DEF[…] lookup or a bare local
# is red until it is escaped or reviewed here (dd's P4–P6 review found ten shapes a deny-list of field names missed).
#
# What is HTML: a template whose own text has "<" or `="` (markup, an attribute selector) and every template inside
# it; the right-hand side of every assignment to a name ending in HTML (`rowsHTML = …`, `xHTML.push(…)`), of
# `.innerHTML = …` and of `setHTML(el, …)`; and the whole body of a declared builder. A name ending in HTML is
# therefore safe wherever it is used: everything ever put in it was checked as HTML.
# Parts that never take server data (the demo script, the robot model's canvases).
NOT_SERVER_PARTS = {"10-robot-core.js", "30-source-demo.js"}
ESCAPING_CALLS = {"esc", "CSS.escape"}
SAFE_CALLS = {
    "pct": "Math.round of a number",
    "fmtClock": "HH:MM:SS from a number of seconds", "clock": "fmtClock of a number",
    "Number": "a number", "Math.round": "a number", "Math.min": "a number", "Math.max": "a number",
}
# Functions returning HTML, per file; their bodies are checked as HTML.
BUILDERS = {
    "20-core.js": {"pill"},
    "50-panel.js": {
        "roleVar", "actAttr", "chipCls", "wfElement", "li", "tr", "projectTag", "rowHTML", "noteHTML",
        "permButtons", "permButtonsLive", "permButtonsDemo", "permBox", "permDetail", "permDetailLive", "permDetailDemo",
        "permSubject", "permSubjectLive", "sentWhat", "livePermHow", "rawDetails", "suggestionHTML", "recentHTML",
        "liveTestsHTML",
    },
}
# Builders a part may call that another part defines (each checked where it is defined).
SHARED_BUILDERS = {"pill"}
BUILDER_TABLES = {"bodies": "the sheet's section renderers, each a template checked here"}
# Lookups into tables the page defines as literals (class names, labels, colours, icons).
CONST_TABLES = {"ROLES", "ROLE_INK", "CASE_ICON", "COL_HINT", "COL_STATE", "EXACT_LABEL", "PLATFORM_JA",
                "STATUS_CLASS", "CHIP", "titles"}
# Literal markup the page defines once; each declaration is checked as HTML, like an …HTML name.
CONST_HTML = {"SEGS", "SWATCHES", "RELAY_HOW", "PERM_NOTE", "OV_LEGEND", "SHEET_LEGEND", "SHEET_LEGEND_LIVE"}
# Numbers: names that only ever hold one, and fields the page itself computes as numbers.
NUMERIC_NAMES = {"i", "k", "n", "specIdx", "pPct", "rPct", "fPct", "elsewhere", "compAll", "COMP_MAX"}
NUMERIC_FIELDS = {"at", "start", "end", "abs", "seq", "passed", "failed", "busy", "live", "pend", "sessions"}
# Reviewed exceptions: (file, expression) -> (how many times it appears, why it is safe). The count is exact, so a new
# use of the same expression is red until it is reviewed too.
# Reviewed exceptions: (file, name) -> (how many times the name appears in the file as a word, why it is safe). The
# count is exact, so a new use is red until it is reviewed too.
SAFE_EXCEPTIONS = {
    ("50-panel.js", "innerHTML"): (2, "li's third parameter: every call passes a template literal (checked as HTML)"),
    ("50-panel.js", "cellsHTML"): (2, "tr's third parameter: every call passes a template literal (checked as HTML)"),
    ("50-panel.js", "bHTML"): (2, "the second element of the overview rows, each built with esc() one line above"),
    ("50-panel.js", "whoHTML"): (2, "setHead's last parameter: every call passes pill(…) or ''"),
}
_ID = r"[A-Za-z_$][\w$]*"
_HTML_NAME = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*HTML)\s*(?:\+?=(?!=)|\.push\()")
# Calls that put an argument into the DOM as HTML: name -> which argument (0-based). Their own definitions are not
# checked (what they are given is).
SINK_CALLS = {"setHTML": 1, "addTag": 1, "keyed": 2}
_SINK = re.compile(r"\.innerHTML\s*=(?!=)")

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


def _match(e: str, i: int) -> int:
    """Index of the bracket closing the one at e[i] (strings and templates skipped), or -1."""
    depth, j, n = 0, i, len(e)
    while j < n:
        c = e[j]
        if c in "\"'":
            j = _skip_string(e, j)
            continue
        if c == "`":
            j = _scan_template(e, j, [], False)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _top_opens(e: str) -> list[int]:
    """Indexes of the brackets that open at depth 0."""
    out, i, n = [], 0, len(e)
    while i < n:
        c = e[i]
        if c in "\"'":
            i = _skip_string(e, i)
            continue
        if c == "`":
            i = _scan_template(e, i, [], False)
            continue
        if c in "([{":
            out.append(i)
            j = _match(e, i)
            if j < 0:
                return out
            i = j + 1
            continue
        i += 1
    return out


def _strip_parens(e: str) -> str:
    e = e.strip()
    while e.startswith("(") and _match(e, 0) == len(e) - 1:
        e = e[1:-1].strip()
    return e


def _split_top(e: str, sep: str) -> list[str]:
    cuts = [i for i, c in _top_level(e) if c == sep]
    if not cuts:
        return [e]
    out, last = [], 0
    for i in cuts:
        out.append(e[last:i])
        last = i + 1
    return out + [e[last:]]


def _returns(body: str) -> list[str]:
    """The expressions a block returns at its own level (not inside nested functions' braces)."""
    top = list(_top_level(body))
    out = []
    for n, (i, c) in enumerate(top):
        if body.startswith("return", i) and not re.match(r"[\w$]", body[i - 1:i] or " ") and not re.match(r"[\w$]", body[i + 6:i + 7] or " "):
            end = next((j for j, cj in top[n:] if cj == ";" and j > i), len(body))
            out.append(body[i + 6:end].strip())
    return out


def _arrow_safe(arrow: str, ctx) -> bool:
    """`(a, b) => expr`, `(a) => { … return expr; }`, or a builder's name: every value it returns is safe."""
    arrow = arrow.strip()
    if arrow in ctx["builders"]:
        return True
    head = _split_top(arrow, "=")
    parts = arrow.split("=>", 1)
    if len(parts) != 2:
        return False
    body = parts[1].strip()
    if body.startswith("{") and _match(body, 0) == len(body) - 1:
        rets = _returns(body[1:-1])
        return bool(rets) and all(_safe(r, ctx) for r in rets)
    return _safe(body, ctx)


def _call(e: str):
    """(callee, args, rest) when e is `callee(args)rest` with callee a dotted name, else None."""
    m = re.match(rf"({_ID}(?:\.{_ID})*)\(", e)
    if not m:
        return None
    close = _match(e, m.end() - 1)
    return (m.group(1), e[m.end():close], e[close + 1:]) if close > 0 else None


def _safe(expr: str, ctx) -> bool:
    e = _strip_parens(expr)
    if not e or (ctx.get("file"), " ".join(e.split())) in SAFE_EXCEPTIONS:
        return True                                   # a reviewed exception (its count is checked on its own)
    commas = _split_top(e, ",")
    if len(commas) > 1:
        return _safe(commas[-1], ctx)                 # a comma expression's value is its last
    outs = _outputs(e)
    if outs != [e]:
        return all(_safe(o, ctx) for o in outs)
    plus = [i for i, c in _top_level(e) if c == "+" and e[i - 1:i] != "+" and e[i + 1:i + 2] not in ("+", "=")]
    if plus and not re.fullmatch(r"[\w$.\s+\-*/%()]+", e):
        bounds = [0] + [i + 1 for i in plus] + [len(e) + 1]
        return all(_safe(e[a:b - 1], ctx) for a, b in zip(bounds, bounds[1:]))
    if re.fullmatch(r"'[^'\\]*'|\"[^\"\\]*\"|-?\d+(\.\d+)?", e):
        return True
    if e.startswith("`") and _scan_template(e, 0, [], False) == len(e):
        inner: list = []
        _scan_template(e, 0, inner, True)             # a template bound for the DOM: what goes into it
        return all(_safe(x, ctx) for x, h in inner if h)
    if re.fullmatch(r"'[^']*'\.repeat\(\d+\)", e):
        return True
    top = "".join(c for _, c in _top_level(e))
    if top.endswith(".length") or re.search(r"===|!==|<=|>=|(?<![=>-])[<>](?!=)", top) or e.startswith("!"):
        return True                                   # a count, or true / false
    num = rf"(?:{'|'.join(sorted(NUMERIC_NAMES))})(?![\w$])|[\w$.]*\.(?:{'|'.join(sorted(NUMERIC_FIELDS))})(?![\w$(])|\d+(?:\.\d+)?"
    if re.fullmatch(rf"(?:\s*\(?\s*(?:{num})\s*\)?\s*[-+*/%]?)+", e):
        return True
    call = _call(e)
    if call:
        callee, args, rest = call
        if not rest and callee in ESCAPING_CALLS | set(SAFE_CALLS) | ctx["builders"]:
            return True
        # xs.map(arrow) / xs.map(arrow).join('…'): the outermost map only; every value it maps to is safe
        m = re.fullmatch(r"\.join\((?:'[^']*'|\"[^\"]*\")?\)|", rest)
        if m is not None and callee.endswith(".map") and _arrow_safe(args, ctx):
            return True
    m = re.match(rf"({_ID})\[", e)
    if m:
        close = _match(e, m.end() - 1)
        rest = e[close + 1:] if close > 0 else "?"
        if m.group(1) in CONST_TABLES and re.fullmatch(rf"(?:\.{_ID}|\[\d+\])*", rest):
            return True
        if m.group(1) in BUILDER_TABLES and rest.startswith("(") and _match(rest, 0) == len(rest) - 1:
            return True
    # e.g. `xs.filter(f).map(arrow).join('')`: find the outermost .map( at the top level
    for i in _top_opens(e):
        if e[i] != "(":
            continue
        if e[:i].endswith(".map") and _match(e, i) > 0:
            close = _match(e, i)
            rest = e[close + 1:]
            if re.fullmatch(r"\.join\((?:'[^']*'|\"[^\"]*\")?\)|", rest) and _arrow_safe(e[i + 1:close], ctx):
                return True
    if e.startswith("["):
        close = _match(e, 0)
        rest = e[close + 1:] if close > 0 else "?"
        if re.fullmatch(r"\.join\((?:'[^']*'|\"[^\"]*\")?\)|", rest):
            items = [x.strip() for x in _split_top(e[1:close], ",") if x.strip()]
            return all(_safe(x[3:] if x.startswith("...") else x, ctx) for x in items)
    if e in CONST_HTML:
        return True
    if re.fullmatch(rf"{_ID}HTML(?:\.join\((?:'[^']*'|\"[^\"]*\")?\))?", e):
        return e.split(".")[0] in ctx["assigned"]     # only a name whose every assignment was checked
    return False


def _extent(src: str, i: int) -> int:
    """End of the expression starting at i: the first `;` or `,`, a closing bracket, or a line end not continued
    by an operator — at depth 0."""
    depth, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            i = _skip_string(src, i)
            continue
        if c == "`":
            i = _scan_template(src, i, [], False)
            continue
        if src.startswith("//", i):
            i = src.find("\n", i)
            if i < 0:
                return n
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif depth == 0 and c in ";,":
            return i
        elif depth == 0 and c == "\n":
            rest = src[i + 1:].lstrip()
            if rest[:1] not in ("?", ":", ".", "+", "|", "&") and not rest.startswith("=>"):
                return i
        i += 1
    return n


def _is_function(rhs: str) -> bool:
    return bool(re.match(rf"\s*(?:async\s+)?(?:function\b|\([^()]*\)\s*=>|{_ID}\s*=>)", rhs))


def _builder_bodies(src: str, names) -> dict[str, str]:
    out = {}
    for m in re.finditer(rf"(?:^|\n)\s*(?:const ({_ID}) = |function ({_ID})\()", src):
        name = m.group(1) or m.group(2)
        if name not in names:
            continue
        if m.group(2):
            start = src.index("{", m.end())
            out[name] = src[start:_match(src, start) + 1]
        else:
            rhs = src[m.end():_extent(src, m.end())]
            arrow = rhs.split("=>", 1)
            out[name] = arrow[1].strip() if len(arrow) == 2 else rhs
    return out


def html_checks(name: str, src: str) -> list[str]:
    """Everything in one part file that is checked as HTML and is not safe, as `file: ${expr}` lines."""
    builders = BUILDERS.get(name, set()) | SHARED_BUILDERS
    problems, rhs, assigned = [], [], set()
    for m in _HTML_NAME.finditer(src):
        value = src[m.end():_extent(src, m.end())]
        if m.group(1) in SINK_CALLS:
            continue
        if _is_function(value):
            if m.group(1) not in builders:
                problems.append(f"{name}: {m.group(1)} is a function returning HTML; declare it in BUILDERS")
            continue
        assigned.add(m.group(1))
        rhs.append(value)
    defs = []                                          # spans of the sink helpers' own definitions
    for m in re.finditer(rf"(?:const ({'|'.join(SINK_CALLS)}) = |function ({'|'.join(SINK_CALLS)})\()", src):
        end = _match(src, src.index("{", m.end())) if m.group(2) else _extent(src, m.end())
        defs.append((m.start(), end))
    inside = lambda i: any(a <= i <= b for a, b in defs)
    for m in _SINK.finditer(src):
        if not inside(m.start()):
            rhs.append(src[m.end():_extent(src, m.end())])
    for m in re.finditer(rf"(?<![\w$.])({'|'.join(SINK_CALLS)})\(", src):
        if inside(m.start()):
            continue
        args, i = [], m.end()
        for _ in range(SINK_CALLS[m.group(1)] + 1):
            j = _extent(src, i)
            args.append(src[i:j])
            i = j + 1
        value = args[-1].strip()
        if m.group(1) == "keyed":
            value = value.split("=>", 1)[1] if "=>" in value else value
        rhs.append(value)
    for decl in re.finditer(rf"const ({'|'.join(sorted(CONST_HTML))}) = ", src):
        rhs.append(src[decl.end():_extent(src, decl.end())])
    rhs += list(_builder_bodies(src, builders).values())
    ctx = {"builders": builders, "assigned": assigned, "file": name}
    exprs = list(_templates(src))
    values = []
    for r in rhs:
        r = r.strip()
        if r.startswith("{") and _match(r, 0) == len(r) - 1:
            values += _returns(r[1:-1])              # a block: what it returns
        else:
            values.append(r)
    exprs += [(v, True) for v in values]              # _safe follows a value into its templates and returns
    bad = collections.Counter(" ".join(e.split()) for e, h in exprs if h and not _safe(e, ctx))
    for e, count in bad.items():
        problems.append(f"{name}: ${{{e[:140]}}}")
    for (file, word), (declared, _why) in SAFE_EXCEPTIONS.items():
        if file == name:
            seen = len(re.findall(rf"(?<![\w$.]){re.escape(word)}(?![\w$])", src))
            if seen != declared:
                problems.append(f"{name}: {word} appears {seen} times (declared {declared})")
    return sorted(set(problems))


def test_nothing_reaches_the_html_unescaped():
    bad = []
    for name in sorted(set(bundle.ORDER["live"]) | {"80-dbg.js"}):
        if name in NOT_SERVER_PARTS:
            continue
        bad += html_checks(name, web_text("js", name))
    assert bad == [], "into HTML without esc() or a reviewed reason:\n" + "\n".join(sorted(bad))


# dd's ten shapes the field-name deny-list could not see, and the shapes that must pass.
CAUGHT = [
    "`<b>${DEF[x.id].agent}</b>`", "`<b>${x.name.slice(0, 4)}</b>`", "`<b>${String(x.name)}</b>`",
    "`<b>${[x.name].join()}</b>`", "`<b>${x.message}</b>`", "`<b>${p.toolName}</b>`", "`<b>${x.name.toUpperCase()}</b>`",
    "`<b>${JSON.stringify(x)}</b>`", "`<b>${x ? x.name : ''}</b>`", "`<b>${x.name || '-'}</b>`",
    "`<i data-k=\"${x.key}\"></i>`", "`<b>${label}</b>`", "`<b>${xs.map((x) => x.name).join('')}</b>`",
    "`<b>${xs.map((x) => { return x.name; }).join('')}</b>`", "`<b>${x.at.name}</b>`",
    "const fooHTML = x.name;", "el.innerHTML = x.name;", "setHTML($('a'), x.name);", "const lHTML = `#${x.id}`;",
    "`<b>${'a' + x.name}</b>`", "`<b>${barHTML}</b>`",
]
PASSED = [
    "`<b>${esc(x.name)}</b>`", "`<b>${esc(DEF[x.id].agent)}</b>`", "`<b>${x.items.length} 件</b>`", "`<b>${i + 1}</b>`",
    "`<b>${ROLES[r].color}</b>`", "`<b>${ok ? esc(a) : ''}</b>`", "`<b>${xs.map((x) => `<i>${esc(x)}</i>`).join('')}</b>`",
    "`<b>${a === b}</b>`", "const fooHTML = `<i></i>`; const z = `<b>${fooHTML}</b>`;", "`<b>${pill(id, 'main')}</b>`", "`<b>${'<i></i>'.repeat(7)}</b>`",
    "const fooHTML = `<i>${esc(x.name)}</i>`;", "el.innerHTML = `<i>${esc(a)}</i>`;",
]


@pytest.mark.parametrize("snippet", CAUGHT)
def test_the_arm_catches(snippet):
    assert html_checks("probe.js", snippet), snippet


@pytest.mark.parametrize("snippet", PASSED)
def test_the_arm_passes(snippet):
    assert html_checks("probe.js", snippet) == [], snippet


def test_a_declared_exception_is_exact():
    """One more use of a reviewed expression is red until the count is reviewed too."""
    two = "const li = (m, key, innerHTML) => `<li>${innerHTML}</li>`; const z = `<p>${innerHTML}</p>`;"
    assert "50-panel.js: innerHTML appears 3 times (declared 2)" in html_checks("50-panel.js", two)
    one = "const li = (m, key, innerHTML) => `<li>${innerHTML}</li>`;"
    assert not any("innerHTML" in line for line in html_checks("50-panel.js", one))
