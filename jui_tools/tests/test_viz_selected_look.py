"""The selected-look family is whole (tools/viz_e2e/selected_look.py MEMBERS and SOURCES).

Every control the page gives a state of its own — aria-pressed, aria-selected, aria-checked or aria-current, in
index.html or the page's scripts, or an on rule of app.css — is a member the e2e measures, light and dark. A new toggle
that is not listed is red here, before anyone has to ask which one is on (requester 10-22: 「トークのタブどっち選択して
るのかわからない」).
"""
from __future__ import annotations

import ast
import pathlib
import re

JT = pathlib.Path(__file__).resolve().parents[1]
WEB = JT / "jui_cli" / "viz" / "web"
STATE = re.compile(r"aria-(?:pressed|selected|checked|current)")


def _module() -> dict:
    """MEMBERS, SOURCES and READS as literals (the e2e module imports Playwright; it is read, not imported)."""
    out = {}
    for node in ast.parse((JT / "tools" / "viz_e2e" / "selected_look.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], "id", "") in ("MEMBERS", "SOURCES", "READS"):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return out


def _state_lines() -> list[tuple[str, str]]:
    out = []
    for f in [WEB / "index.html", *sorted((WEB / "js").glob("*.js"))]:
        if f.name == "80-dbg.js":   # the e2e hook reads states, sets none
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if STATE.search(line):
                out.append((f"{f.name}:{i}", line))
    return out


def test_every_control_given_a_state_is_a_member():
    m = _module()
    keys = {k for k, *_ in m["MEMBERS"]}
    assert set(m["SOURCES"]) == keys, set(m["SOURCES"]) ^ keys
    lines = _state_lines()
    assert len(lines) >= 30, len(lines)
    marks = [(k, x) for k, xs in m["SOURCES"].items() for x in xs]
    missing = [f"{at}: {line.strip()[:140]}" for at, line in lines
               if not any(x in line for _, x in marks) and not any(r in line for r in m["READS"])]
    assert not missing, "a control is given a state that selected_look.py does not measure:\n" + "\n".join(missing)
    stale = [f"{k}: {x}" for k, x in marks if not any(x in line for _, line in lines)]
    assert not stale, f"marks on no line of the page: {stale}"


def test_every_on_rule_of_the_stylesheet_is_a_members():
    """Each on rule's own class or id is in a member's selector or made markup."""
    m = _module()
    text = repr(m["MEMBERS"])
    css = (WEB / "app.css").read_text(encoding="utf-8")
    sels = [s.strip() for r in re.findall(r"([^{}]*\[aria-(?:pressed|selected|checked|current)=\"?true\"?\][^{]*)\{", css)
            for s in r.split(",") if STATE.search(s)]
    assert len(sels) >= 16, sels
    missing = []
    for sel in sels:
        names = [n.lstrip(".#") for n in re.findall(r"[.#][A-Za-z][\w-]*", sel.split("/*")[-1])]
        if not names or not any(n in text for n in names):
            missing.append(sel)
    assert not missing, f"on rules no member measures: {missing}"
