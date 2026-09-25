#!/usr/bin/env python3
"""Which `*_GATE_FROM` literals the next patch switches on.

    python3 next_stamp_plan.py <repo>

run-suites.sh asks this before its "python suites at the next stamp" leg.
A gate here is switched by the running VERSION, not by a flag, so a suite
green at this stamp can be red at the next: raised to 1.8.121 on a copy,
test_tools went 16 red and nothing had run it there before the stamp's own
CI (2026-09-26). The leg runs the suites at the next patch only when that
patch turns a gate on that the current stamp leaves off (4f's ruling (b)).

The literals are read by the tag gate's own collector
(validate_gate_version.collect — every tracked Python file, with its control
for a blind collector), never listed here. Prints:
    CUR <version>                 this tree's stamp
    NEXT <version>                the next patch
    READ <NAME> = <value> (<path>)   each literal the collector found
    CROSS <NAME> <value> <path>   each one NEXT switches on (none: the leg skips)
    PROBLEM <text>                what the collector could not read cleanly
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _tag_gate():
    spec = importlib.util.spec_from_file_location("_next_stamp_tag_gate", HERE / "validate_gate_version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plan(repo: str, ref: str = "HEAD", current: str | None = None):
    """(current, next, found, crossing, problems) for *repo* at *ref*.
    *current* defaults to the tree's VERSION."""
    tag_gate = _tag_gate()
    if tag_gate.gates is None:
        raise RuntimeError(f"{tag_gate.GATE_VERSIONS_PATH} is not there — no gate can be read")
    cur = current or (Path(repo) / "VERSION").read_text(encoding="utf-8").strip()
    nxt = tag_gate.next_patch(cur)
    found, problems = tag_gate.collect(repo, ref)
    crossing = sorted(
        (name, path, value) for name, (path, value) in found.items()
        if tag_gate.gates.gate_is_on(nxt, value) and not tag_gate.gates.gate_is_on(cur, value))
    return cur, nxt, found, crossing, problems


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: next_stamp_plan.py <repo>")
        return 2
    try:
        cur, nxt, found, crossing, problems = plan(argv[1])
    except RuntimeError as e:
        print(f"PROBLEM {e}")
        return 1
    print(f"CUR {cur}")
    print(f"NEXT {nxt}")
    for name, (path, value) in sorted(found.items()):
        print(f"READ {name} = {value!r} ({path})")
    for name, path, value in crossing:
        print(f"CROSS {name} {value} {path}")
    for problem in problems:
        print(f"PROBLEM {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
