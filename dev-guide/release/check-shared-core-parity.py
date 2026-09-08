#!/usr/bin/env python3
"""shared/core vs each tool's lib/core — including the files only ONE side has.

Why this is not `diff -rq | grep -v "Only in"` (2026-09-08)
----------------------------------------------------------
The release leg filtered every `Only in` line away and counted what was left.
That filter deletes a whole DIRECTION of the comparison, and the two failures
it hides are the ones a mirror actually suffers:

    [A] a file deleted from one tool's lib/core        → "Only in shared/core"
    [C] a new file added to shared/core, unmirrored    → "Only in shared/core"

Measured on a clean tree at a4c0e06b and again at 46fad0cb: the filter
dropped 33 / 27 / 28 lines — 88 in total — and printed `parity IDENTICAL`. It was not measuring
nothing: the 13-14 files present on both sides were genuinely byte-compared
(a one-byte edit is caught). But A and C were invisible, and 88 legitimate
one-sided lines are exactly the noise a real one would have hidden in.

⚠️ That count moves with WHEN you measure, not only with which tree: running
the Python suites leaves a `shared/core/__pycache__`, which adds one line per
tool (34 / 28 / 29). Two lanes comparing this number reached different totals
for that reason. The population below is `shared/core/*.rb`, so build
droppings cannot enter it.

The population is DERIVED, not hand-listed
------------------------------------------
`shared/core/*.rb` is the mirrored set — the `.py` and `.json` files next to
them are the Python canon and its data, which no Ruby tool mirrors. Which
tools are expected to carry which mirror is already declared, once, in each
tool's own `spec/core/shared_core_mirror_spec.rb` `%w[...]` list. That list is
the authority here too, so a decision recorded in one place is not re-typed
into a second one that can drift from it.

    R1  a mirror file missing from SOME tools is a defect UNLESS that tool's
        own %w list omits it (rjui_tools deliberately does not carry
        data_model_updater_core.rb — measured 2026-09-08, and it is the only
        such case in the tree)
    R2  a shared/core *.rb missing from ALL THREE mirrors is always a defect:
        nothing carries it, so "shared" is a claim with no referent
    R3  a file a tool DECLARES must exist in shared/core. Without this the
        population is `shared/core/*.rb`, so deleting the canonical copy makes
        the file leave the population and every rule pass over what remains —
        the first draft of this script did exactly that (measured: 13 files
        became 12 and the exit stayed 0). The rspec mirror guards cannot cover
        it either: they carry `skip ... unless File.exist?(shared_copy)`, so
        the same deletion turns all ten arms into silent skips.

⚠️ R1 cannot be written as "missing ⇒ allowed if undeclared", because a NEW
unmirrored file is undeclared everywhere and would be waved through — that is
why R2 exists as a separate rule rather than a branch of R1.
"""
from __future__ import annotations

import filecmp
import re
import sys
from pathlib import Path

TOOLS = ("sjui_tools", "kjui_tools", "rjui_tools")
MIRROR_SPEC = "spec/core/shared_core_mirror_spec.rb"


def declared_mirrors(root: Path, tool: str) -> set[str]:
    """The files `tool` says it mirrors, read from its own spec's %w[...]."""
    src = (root / tool / MIRROR_SPEC).read_text(encoding="utf-8")
    match = re.search(r"%w\[([^\]]*)\]", src)
    if not match:
        raise SystemExit(
            f"FAIL: {tool}/{MIRROR_SPEC} has no %w[...] list — the expected "
            f"mirror set has no source, so this check cannot run"
        )
    return set(match.group(1).split())


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    shared = root / "shared" / "core"
    if not shared.is_dir():
        print(f"FAIL: {shared} does not exist")
        return 1

    declared = {t: declared_mirrors(root, t) for t in TOOLS}
    mirrored = sorted(p.name for p in shared.glob("*.rb"))
    if not mirrored:
        print("FAIL: shared/core holds no *.rb — the population is empty and "
              "every rule below would pass vacuously")
        return 1

    problems: list[str] = []
    compared = identical = recorded = 0

    # R3 first: a canonical copy that has been deleted takes its whole row out
    # of the loop below, so it has to be judged against the DECLARATION rather
    # than against what is on disk.
    for tool in TOOLS:
        for name in sorted(declared[tool]):
            if not (shared / name).is_file():
                problems.append(
                    f"R3 {name}: {tool}/{MIRROR_SPEC} declares it, but "
                    f"shared/core has no such file"
                )

    for name in mirrored:
        absent = [t for t in TOOLS if not (root / t / "lib" / "core" / name).is_file()]
        if len(absent) == len(TOOLS):
            problems.append(f"R2 {name}: in shared/core, mirrored by NO tool")
            continue
        for tool in absent:
            if name in declared[tool]:
                problems.append(
                    f"R1 {name}: missing from {tool}/lib/core, but "
                    f"{tool}/{MIRROR_SPEC} declares it"
                )
            else:
                recorded += 1
        for tool in TOOLS:
            copy = root / tool / "lib" / "core" / name
            if not copy.is_file():
                continue
            compared += 1
            if filecmp.cmp(shared / name, copy, shallow=False):
                identical += 1
            else:
                problems.append(f"DIFFERS {tool}/lib/core/{name}")

    print(f"   {len(mirrored)} mirrored file(s) x {len(TOOLS)} tool(s): "
          f"{identical}/{compared} byte-identical, "
          f"{recorded} recorded omission(s)")
    for line in problems:
        print(f"   {line}")
    if problems:
        print(f"FAIL: shared/core parity: {len(problems)} problem(s)")
        return 1
    print("OK: shared/core parity (presence AND bytes, both directions)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
