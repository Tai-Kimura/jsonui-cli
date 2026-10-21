"""What an --only name runs, read from run.py's own want(...) calls (no list of its own to keep in step).

A block in run.py runs when one of its want() names is given; the last name is the block's own. A name that is the
first of many blocks' want() is a group: --only live runs nearly every suite (10-21: meant as one, it ran 49 minutes
of them and held the machine's line). run.py says what a group expands to, and stops unless --group-ok is given:
every e2e runs once, before a distribution; a fix runs its own suite by name.
"""
from __future__ import annotations

import pathlib
import re

RUN_PY = pathlib.Path(__file__).resolve().parent / "run.py"
_WANT = re.compile(r"\bwant\(\s*((?:\"[a-z0-9-]+\"\s*,?\s*)+)\)")


def blocks(src: str | None = None) -> list[tuple[str, ...]]:
    """Each want(...) call's names, in run.py's order."""
    src = RUN_PY.read_text(encoding="utf-8") if src is None else src
    return [tuple(re.findall(r'"([a-z0-9-]+)"', m.group(1))) for m in _WANT.finditer(src)]


def suites_of(name: str, src: str | None = None) -> list[str]:
    """The blocks --only name runs, each by its own name, in run.py's order."""
    out = []
    for names in blocks(src):
        if name in names and names[-1] not in out:
            out.append(names[-1])
    return out


def check(only: list[str] | None, group_ok: bool, src: str | None = None) -> tuple[list[str], bool]:
    """(lines to print, stop): each --only name that runs two or more suites is said with them; without group_ok
    such a name stops the run before it takes a ticket in the machine's line."""
    lines, stop = [], False
    for name in only or []:
        got = suites_of(name, src)
        if len(got) < 2:
            continue
        lines.append(f"--only {name} = {len(got)} suites: {', '.join(got)}")
        if not group_ok:
            stop = True
    if stop:
        lines.append("stopped: a group runs most of the e2e (every e2e runs once, before a distribution). Name the "
                     "suite (--only gitbox), or add --group-ok to run the group")
    return lines, stop
