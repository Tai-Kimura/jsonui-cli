"""Every way the robot card goes to a robot remembers it as its project's last picked (ticket
2026-10-23-viz-last-robot-per-project-only-on-click; requester 10-23: 「クリックで3D開く左右キーで移動、別プロジェクト行って帰って
くるの時に最後に選択してたやつを表示して欲しい」). The card's robot is rbState.id; each function of the page that sets it to a
robot (not to null) calls rbRemember with it, and nothing else writes LAST_ROBOT a robot. The page's own walk (a click,
→ twice, another project and back; ‹) is tools/viz_e2e/project_switch.py's."""
from __future__ import annotations

import re

from tests.test_viz_bundle import WEB, web_text

JS = sorted(f.name for f in WEB.joinpath("js").iterdir() if f.name.endswith(".js"))   # every script of the page


def _functions(src: str):
    """Top-level functions: name -> body (to the first `}` at column 0)."""
    for m in re.finditer(r"\nfunction (\w+)\(", src):
        end = src.find("\n}", m.start() + 1)
        yield m.group(1), src[m.start():end + 2 if end >= 0 else len(src)]


def test_every_function_that_puts_a_robot_on_the_card_remembers_it():
    setters, unremembered = {}, []
    for name in JS:
        src = web_text("js", name)
        for fn, body in _functions(src):
            for m in re.finditer(r"rbState\.id = (?!null)([\w.]+);", body):
                setters[fn] = m.group(1)
                if f"rbRemember({m.group(1)})" not in body:
                    unremembered.append(f"{name}:{fn} sets rbState.id = {m.group(1)}")
    assert setters == {"openRobot": "id", "goRobot": "next"}, setters   # a new way: it remembers too, and is listed here
    assert not unremembered, unremembered


def test_only_rb_remember_writes_a_robot_to_the_projects_memory():
    writes = []
    for name in JS:
        for m in re.finditer(r"LAST_ROBOT\.set\(([^;]*)\);", web_text("js", name)):
            writes.append((name, m.group(1)))
    robots = [w for w in writes if not w[1].endswith(", null")]
    # rbRemember's own, and selectRobot's for a robot of another project (remembered there before the switch opens it)
    assert robots == [("50-panel.js", "p, id"), ("50-panel.js", "p, id")], writes
    panel = web_text("js", "50-panel.js")
    remember = dict(_functions(panel))["rbRemember"]
    assert "LAST_ROBOT.set(p, id)" in remember and "projectOfRobot(id)" in remember
