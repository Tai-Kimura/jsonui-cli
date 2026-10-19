"""Mermaid vendored (2.3.5): the view draws diagrams with its own copy, strict, and asks nothing outside.

The real `jui viz serve` in a throwaway HOME on a free port. Opening the page reads no Mermaid (3.6 MB, only when a
diagram is first drawn). Drawing one reads /vendor/mermaid-11.17.2/mermaid.min.js from the server, once, and nothing
from anywhere else; it runs with securityLevel 'strict'. A diagram whose labels carry a <script>, an <img onerror>
and a javascript: link, and a click directive, comes out with none of them able to run: no script element, no on*
attribute, no javascript: link, nothing set on window, the <img> never loaded (labels are SVG text: htmlLabels off). The theme follows the page (default / dark). No console error.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
PLAIN = 'flowchart LR\n    V_login["ログイン<br/>(View)"]\n    VM_login["loginViewModel<br/>3 methods"]\n    V_login --> VM_login'
HOSTILE = ("flowchart LR\n"
           '    A["<script>window.__pwned = 1</script>a"]\n'
           '    B["<img src=x onerror=\'window.__pwned = 2\'>b"]\n'
           '    C["<a href=\'javascript:window.__pwned = 3\'>c</a>"]\n'
           "    A --> B --> C\n"
           '    click A call window.alert("x")\n'
           '    click B "javascript:window.__pwned = 4"\n')


# A diagram may not set its own config (dd's review, 10-19): each of these turned htmlLabels back on (a foreignObject
# with the <img>, fetched) or put a url() in the CSS (fetched) before mermaidSafeText and the extra secure keys.
LABEL = '    A["<img src=/ds-probe-{n}.png>a"] --> B'
UNLOCKS = {
    "init": '%%{init: {"htmlLabels": true, "flowchart": {"htmlLabels": true}}}%%\nflowchart LR\n' + LABEL.format(n=1),
    "secure-emptied": '%%{init: {"secure": [], "htmlLabels": true, "flowchart": {"htmlLabels": true}}}%%\nflowchart LR\n' + LABEL.format(n=2),
    "front-matter": '---\nconfig:\n  htmlLabels: true\n  flowchart:\n    htmlLabels: true\n---\nflowchart LR\n' + LABEL.format(n=3),
    "themeCSS": '%%{init: {"themeCSS": ".node rect { fill: url(/ds-probe-4.png); } .label { background: url(/ds-probe-4b.png); }"}}%%\nflowchart LR\n    A --> B',
    # dd's review 2 (B): a directive taken out left a front matter at the start, which Mermaid then read
    "directive-then-front-matter": '%%{x}%%---\nconfig:\n  htmlLabels: true\n  class:\n    htmlLabels: true\n  flowchart:\n    htmlLabels: true\n---\nflowchart LR\n' + LABEL.format(n=8),
}
# Keys not in 3f340439's fourteen secure names (c2's fourth check). sequence.mirrorActors is the one that shows: with
# only the fourteen secure the directive turns it off (2 actor boxes, measured), with every key secure the diagram
# keeps Mermaid's 4. class.htmlLabels (asked for) draws no foreignObject either way in 11.17.2 — its class diagrams
# read the top-level htmlLabels, which the fourteen hold — so it guards the key without telling the two apart.
BEYOND_LIST = {
    "sequence.mirrorActors": ('%%{init: {"sequence": {"mirrorActors": false}}}%%\nsequenceDiagram\n    Alice->>Bob: hi', 4),
    "class.htmlLabels": ('%%{init: {"class": {"htmlLabels": true}}}%%\nclassDiagram\n    class U["<img src=/ds-probe-13.png>u"]\n    class V\n    U --> V', None),
}
# dd's review 2 (A): a style in the diagram's own syntax, kept by Mermaid as written: a url() fetched from the origin
URL_STYLES = {
    "classDiagram style": 'classDiagram\n    class U\n    class V\n    U --> V\n    style U fill:url(/ds-probe-6.png)',
    "stateDiagram classDef": 'stateDiagram-v2\n    [*] --> S\n    S --> [*]\n    classDef c fill:url(/ds-probe-7.png)\n    class S c',
}


def check(failures, cond, text):
    if not cond:
        failures.append(f"mermaid: {text}")


async def run_mermaid(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "mermaid"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    port = free_port()
    env = dict({k: v for k, v in os.environ.items() if k not in ISOLATE}, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "mermaid", **DESKTOP)
        asked = []
        page.on("request", lambda r: asked.append(r.url))
        await page.emulate_media(color_scheme="light")
        await page.goto(url + "/")
        await ready(page)
        await page.wait_for_timeout(1500)
        res["atOpen"] = [u for u in asked if "mermaid" in u]
        check(failures, not res["atOpen"], f"opening the page reads no Mermaid: {res['atOpen']}")

        light = res["light"] = await page.evaluate("(t) => window.__dbg.mermaid(t)", PLAIN)
        check(failures, light["svg"] and light["nodes"] == 2 and not light["error"] and "ログイン" in light["text"],
              f"a diagram is drawn (2 nodes, the spec's text): {light}")
        check(failures, light["securityLevel"] == "strict", f"securityLevel strict: {light['securityLevel']}")
        check(failures, light["theme"] == "default", f"light page: the default theme: {light['theme']}")
        await page.screenshot(path=str(out / "drawn-light.png"))

        hostile = res["hostile"] = await page.evaluate("(t) => window.__dbg.mermaid(t)", HOSTILE)
        await page.wait_for_timeout(500)
        pwned = await page.evaluate("() => window.__pwned === undefined ? null : window.__pwned")
        check(failures, hostile["svg"] and hostile["scripts"] == 0 and hostile["onAttrs"] == 0 and hostile["jsLinks"] == 0 and pwned is None,
              f"labels with a script, an onerror, a javascript: link and click directives run nothing: {hostile} pwned={pwned}")
        boxes = await page.evaluate("() => [...document.querySelectorAll('#e2e-mermaid g.node')].map((g) => { const r = g.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })")
        for x, y in boxes:
            await page.mouse.click(x, y)
        await page.wait_for_timeout(300)
        pwned = await page.evaluate("() => window.__pwned === undefined ? null : window.__pwned")
        check(failures, pwned is None, f"clicking the nodes runs nothing: {pwned}")

        for name, text in UNLOCKS.items():
            before = len(asked)
            u = res[f"unlock-{name}"] = await page.evaluate("(t) => window.__dbg.mermaid(t)", text)
            await page.wait_for_timeout(400)
            got = [x for x in asked[before:] if "mermaid.min.js" not in x]
            u["asked"] = got
            check(failures, u["foreignObjects"] == 0 and u["imgs"] == 0 and not got and u["htmlLabels"] is False,
                  f"{name}: the diagram cannot set its own config (no foreignObject, no img, nothing fetched): {u['foreignObjects']} {u['imgs']} {got} htmlLabels={u['htmlLabels']}")
        for name, text in URL_STYLES.items():
            before = len(asked)
            u = res[f"style-{name}"] = await page.evaluate("(t) => window.__dbg.mermaid(t)", text)
            await page.wait_for_timeout(400)
            got = [x for x in asked[before:] if "mermaid.min.js" not in x]
            u["asked"] = got
            check(failures, u["svg"] and not got, f"{name}: drawn, and its url() fetches nothing: svg={u['svg']} {got} {u['error']}")
        # the first lock alone: what Mermaid is handed has no directive and no front matter left
        handed = res["handed"] = await page.evaluate("(t) => window.__dbg.mermaidSafeText(t)", UNLOCKS["directive-then-front-matter"])
        check(failures, "%%{" not in handed and not handed.lstrip(" \t").startswith("---") and "htmlLabels" not in handed,
              f"directive then front matter: neither is left in what Mermaid is handed: {handed[:160]!r}")
        # each lock on its own (dd / c2, 10-19): the drawn SVG's cleaning, given an SVG straight; `secure`, given the
        # texts with mermaidSafeText skipped
        svg_in = ('<svg xmlns="http://www.w3.org/2000/svg"><style>@import "/ds-probe-10.css"; .a { fill: url(/ds-probe-11.png) }</style>'
                  '<rect style="fill:url( \'/ds-probe-12.png\')" marker-end="url(#arrow)"/></svg>')
        cleaned = res["svgCleaned"] = await page.evaluate("(s) => window.__dbg.mermaidSafeSvg(s)", svg_in)
        import re as _re
        left = _re.findall(r"url\(\s*(?![\'\"]?\s*#)[^)]*\)", cleaned) + _re.findall(r"@import", cleaned)
        check(failures, not left and "url(#arrow)" in cleaned, f"the SVG's cleaning alone: no url() out and no @import left, url(#…) kept: {left} {cleaned[:200]}")
        for name, text in UNLOCKS.items():
            before = len(asked)
            u = res[f"secureOnly-{name}"] = await page.evaluate("(t) => window.__dbg.mermaidRenderUnsanitized(t)", text)
            await page.wait_for_timeout(400)
            got = [x for x in asked[before:] if "mermaid.min.js" not in x]
            check(failures, u["foreignObjects"] == 0 and u["imgs"] == 0 and u["htmlLabels"] is False and not got,
                  f"secure alone, {name} drawn unsanitized: {u} {got}")
        # keys outside 3f340439's fourteen (c2's fourth check): only `secure` = every key of Mermaid's config stops these
        for name, (text, actors) in BEYOND_LIST.items():
            before = len(asked)
            u = res[f"secureAll-{name}"] = await page.evaluate("(t) => window.__dbg.mermaidRenderUnsanitized(t)", text)
            await page.wait_for_timeout(400)
            got = [x for x in asked[before:] if "mermaid.min.js" not in x]
            u["actors"] = await page.evaluate("() => document.querySelectorAll('#e2e-mermaid-raw rect.actor').length")
            check(failures, u["svg"] and u["foreignObjects"] == 0 and u["imgs"] == 0 and u["htmlLabels"] is False and not got
                  and (actors is None or u["actors"] == actors),
                  f"secure (every key), {name} drawn unsanitized: the directive changes nothing: {u} {got}")
        plain = res["plainAfter"] = await page.evaluate("(t) => window.__dbg.mermaid(t)", PLAIN)
        check(failures, plain["svg"] and plain["nodes"] == 2, f"a diagram without directives still draws: {plain}")

        await page.emulate_media(color_scheme="dark")
        dark = res["dark"] = await page.evaluate("(t) => window.__dbg.mermaid(t)", PLAIN)
        check(failures, dark["svg"] and dark["theme"] == "dark", f"dark page: the dark theme: {dark}")
        await page.screenshot(path=str(out / "drawn-dark.png"))

        res["mermaidAsked"] = [u for u in asked if "mermaid" in u]
        check(failures, res["mermaidAsked"] == [f"{url}/vendor/mermaid-11.17.2/mermaid.min.js"],
              f"Mermaid read once, from the server's vendored copy: {res['mermaidAsked']}")
        # The sanitizer (DOMPurify inside Mermaid) parses the hostile label in an inert document, and Chromium reports
        # the onerror there against the page's CSP: one report, from mermaid.min.js, nothing run, nothing loaded. Any
        # other console line is a failure.
        sanitizer = [c for c in watch.console if "Executing inline event handler violates" in c]
        rest = [c for c in watch.console if c not in sanitizer]
        res["sanitizerReports"] = len(sanitizer)
        check(failures, not any(u.rstrip("/").endswith("/x") for u in asked), f"the <img src=x> in a label is never loaded: {[u for u in asked if u.endswith('/x')]}")
        check(failures, len(sanitizer) <= 1 and not rest and not watch.foreign,
              f"no console error (but the sanitizer's one report), nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    except Exception as e:
        failures.append(f"mermaid: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  mermaid: {time.monotonic() - t0:.0f}s", flush=True)
