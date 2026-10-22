"""A suite's closing line ("  notify: 41s") is time.monotonic() less the start it took (ticket
2026-10-22-viz-e2e-notify-time-line-subtracts-page-ms: notify.py took the page's performance.now() into the same name
halfway, and the line said 284205s). In every function of tools/viz_e2e, a name given time.monotonic() is given nothing
else (a function nested in it has its own names)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

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


def _names(target, value):
    """(name, the value it is given) for one target: a name; a tuple or list of them (element by element when the
    value is a tuple or list of the same length, else each is given the whole value); *name."""
    if isinstance(target, ast.Name):
        return [(target.id, value)]
    if isinstance(target, ast.Starred):
        return _names(target.value, value)
    if isinstance(target, (ast.Tuple, ast.List)):
        if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts):
            return [p for t, v in zip(target.elts, value.elts) for p in _names(t, v)]
        return [p for t in target.elts for p in _names(t, value)]
    return []


def _targets(n):
    if isinstance(n, ast.Assign):
        return [p for t in n.targets for p in _names(t, n.value)]
    if isinstance(n, (ast.AugAssign, ast.AnnAssign)):
        return _names(n.target, n.value)
    if isinstance(n, ast.NamedExpr):
        return _names(n.target, n.value)
    if isinstance(n, (ast.For, ast.AsyncFor)):
        return _names(n.target, n.iter)
    if isinstance(n, (ast.With, ast.AsyncWith)):
        return [p for i in n.items if i.optional_vars is not None for p in _names(i.optional_vars, i.context_expr)]
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


@pytest.mark.parametrize("line", [
    't0 = page_t0 = await a.evaluate("() => performance.now()")',     # a chain
    't0, page_t0 = [await a.evaluate("() => performance.now()")] * 2',  # a tuple given one value
    'page_t0, t0 = 1.0, 2.0',                                          # a tuple given a tuple
    'page_t0 = (t0 := await a.evaluate("() => performance.now()"))',   # :=
    'for t0 in range(3): pass',                                        # a loop's name
    'async with lock() as t0: pass',                                   # with … as
])
def test_the_arm_finds_each_way_of_giving_the_name(line):
    """The independent check's n1 (a tuple) and n2 (:=) were green: every way of giving a name is read."""
    src = f"async def run(pw):\n    t0 = time.monotonic()\n    {line}\n    print(time.monotonic() - t0)\n"
    assert reused(src) == ["run:3 t0"]


def test_a_tuple_that_keeps_the_start_is_not_red():
    src = "async def run(pw):\n    t0, n = time.monotonic(), 0\n    a, b = t0, 1\n"
    assert reused(src) == []
