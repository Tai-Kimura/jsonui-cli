#!/usr/bin/env python3
"""Say which Python files in a range changed only their PROSE.

🔻 A "DOCUMENTATION-ONLY" CLAIM IS THE ONE NOBODY CHECKS. Gates read grammar
and tests; a sentence in a release notice saying "this changes no code" is
believed because reading the diff is tedious and because the obvious way to
read it is wrong. Measured 2026-09-15 on v1.8.89..v1.8.90: a predicate that
excludes `^[-+]\\s*#` — comment lines — still counts every changed docstring
line as code, because a docstring is not a `#` comment. A person skimming the
same diff makes the same mistake.

So the claim is DERIVED instead: parse both versions, drop the leading
docstring of every module, class and function, and compare the dumped trees. If
they are identical, nothing but prose moved — and unlike a line-based reading,
that survives reformatting, moved comments and renamed locals inside the text.

⚠️ THE COMPARISON NEEDS ITS OWN CONTROL, PRINTED. Two files that could not be
read at all also compare equal, and so do two reads of the same blob. Every row
carries whether the RAW sources differ: a row saying "prose only" with raw
sources identical means nothing changed at all, and a row where the raw sources
could not be obtained is reported as unreadable rather than as agreement.

🔻 SCOPE, STATED: Python only. Ruby, Kotlin and Swift files in the same range
are listed as NOT CHECKED rather than silently dropped — a count of "prose
only" that quietly covered a third of the range would be worse than no count.

Usage:  python tools/check_prose_only.py <from-ref> <to-ref> [repo]
"""

from __future__ import annotations

import ast
import subprocess
import sys


def _git(repo: str, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", repo, *args), capture_output=True, text=True, check=True
    ).stdout


def _blob(repo: str, ref: str, path: str) -> str | None:
    proc = subprocess.run(
        ("git", "-C", repo, "show", f"{ref}:{path}"), capture_output=True, text=True
    )
    return proc.stdout if proc.returncode == 0 else None


def _without_docstrings(source: str) -> str | None:
    """`ast.dump` of the tree with every leading docstring removed."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    frm, to = argv[1], argv[2]
    repo = argv[3] if len(argv) == 4 else "."

    paths = _git(repo, "diff", "--name-only", frm, to).split()
    if not paths:
        print(f"[prose] no files changed between {frm} and {to}")
        return 0

    python = [p for p in paths if p.endswith(".py")]
    other = [p for p in paths if not p.endswith(".py")]
    prose_only: list[str] = []
    code_moved: list[str] = []
    unreadable: list[str] = []

    for path in python:
        a, b = _blob(repo, frm, path), _blob(repo, to, path)
        if a is None or b is None:
            # Added or deleted: there is no pair to compare, which is not the
            # same as "the code did not move".
            unreadable.append(f"{path} (added or deleted)")
            continue
        da, db = _without_docstrings(a), _without_docstrings(b)
        if da is None or db is None:
            unreadable.append(f"{path} (does not parse)")
            continue
        # The control, per file: if the raw sources are equal there was nothing
        # to judge, and calling that "prose only" would inflate the count.
        if a == b:
            unreadable.append(f"{path} (raw sources identical — nothing changed)")
        elif da == db:
            prose_only.append(path)
        else:
            code_moved.append(path)

    print(
        f"[prose] {frm}..{to}: python {len(python)} "
        f"(prose-only {len(prose_only)}, code moved {len(code_moved)}, "
        f"not comparable {len(unreadable)}); not checked (non-python) {len(other)}"
    )
    for path in prose_only:
        print(f"[prose]   PROSE ONLY  {path}")
    for path in code_moved:
        print(f"[prose]   code moved  {path}")
    for note in unreadable:
        print(f"[prose]   NOT COMPARABLE  {note}")
    for path in other:
        print(f"[prose]   not checked  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
