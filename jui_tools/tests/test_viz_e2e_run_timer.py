"""A suite's closing line ("  notify: 41s") is time.monotonic() less the start it took (ticket
2026-10-22-viz-e2e-notify-time-line-subtracts-page-ms: notify.py took the page's performance.now() into the same name
halfway, and the line said 284205s). In every function of tools/viz_e2e, a name given time.monotonic() is given nothing
else (a function nested in it has its own names)."""
from __future__ import annotations

import ast
from pathlib import Path

E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"


def _monotonic(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "monotonic"
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "time")


def _own(fn):
    """The function's own nodes: not those of a function or a lambda inside it."""
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(n))


def _targets(n):
    if isinstance(n, ast.Assign):
        return [(t.id, n.value) for t in n.targets if isinstance(t, ast.Name)]
    if isinstance(n, (ast.AugAssign, ast.AnnAssign)) and isinstance(n.target, ast.Name):
        return [(n.target.id, n.value)]
    return []


def reused(source: str) -> list[str]:
    out = []
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        given = [(name, value, n.lineno) for n in _own(fn) for name, value in _targets(n)]
        clocks = {name for name, value, _ in given if _monotonic(value)}
        out += [f"{fn.name}:{line} {name}" for name, value, line in given if name in clocks and not _monotonic(value)]
    return sorted(out)


def test_no_suite_gives_its_start_another_value():
    found = {p.name: r for p in sorted(E2E.glob("*.py")) if (r := reused(p.read_text(encoding="utf-8")))}
    assert found == {}


def test_the_arm_finds_the_notify_shape():
    src = '''
async def run_notify(pw, out, failures):
    t0 = time.monotonic()
    async def inner():
        t0 = 5            # its own name
    t0 = await a.evaluate("() => performance.now()")
    print(time.monotonic() - t0)
'''
    assert reused(src) == ["run_notify:6 t0"]
