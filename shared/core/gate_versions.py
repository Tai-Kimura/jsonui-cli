"""A `*_GATE_FROM` literal: which release a gate switches on in, read whole.

Design §6.1 (P3a, v4.18's transition table, v4.20). Every gate that is
announced one release ahead holds its release as a LITERAL — never derived
(a derived one agrees with every build). The tag gate
(dev-guide/release/validate_gate_version.py) holds each literal to the
release; this is how the running code reads one:

  undeclared  None / ""       announces nothing, never gates
  withdrawn   "withdrawn"     the notice withdrawn by hand; never gates
  unreadable  anything else   not a release number: announces nothing and
                              never gates (U5) — the tag gate turns it red
  release     "1.8.120"       announced below it, gating from it on

ONE reader for every such gate (design v4.20, ee): validate's contracts
coverage (`VALIDATE_GATE_FROM`, test_tools), the spec validator's layout ids
(`LAYOUT_ID_GATE_FROM`, document_tools), P2e's generator
(`UNMATCHED_GATE_FROM`) and the tag gate. The "withdrawn" defect appeared in
two of them in two different shapes (the gate always on; generation
stopping) precisely because each had its own copy. The literals stay next to
their owners; only the reading is here.

Loaded by file path through each package's `shared_core` loader (it imports
nothing of its own, like every module under shared/core).
"""
from __future__ import annotations

import re

#: The one literal besides a release number: the notice withdrawn by hand
#: (design v4.18: "任意 → withdrawn … 門は入らない").
GATE_WITHDRAWN = "withdrawn"
#: A release number, all of it. `version_key` reads a part up to its digits
#: and stops at the first part without one, so "withdrawn", "next" or "1.8"
#: came out as a PREFIX every running version is at or above — the gate went
#: ON for the literal that says it never will (ee, 2026-09-25).
_GATE_RELEASE = re.compile(r"^\d+\.\d+\.\d+$")


def version_key(version: str) -> tuple:
    """`1.8.120` -> (1, 8, 120): numeric, so 1.8.100 sorts after 1.8.99."""
    out = []
    for part in version.lstrip("v").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        out.append(int(digits))
    return tuple(out)


def gate_state(literal: str | None) -> str:
    """`undeclared`, `withdrawn`, `unreadable` or `release` — only the last
    ever gates."""
    if not literal:
        return "undeclared"
    if literal == GATE_WITHDRAWN:
        return "withdrawn"
    return "release" if _GATE_RELEASE.match(literal) else "unreadable"


def gate_is_on(version: str, literal: str | None) -> bool:
    """Is the gate *literal* names on in the running *version*?"""
    return gate_state(literal) == "release" and version_key(version) >= version_key(literal)


def state_note(name: str, literal: str | None) -> str:
    """What a gate that is not a release number says about itself, after its
    subject ("coverage gate …"): `withdrawn (NAME = "withdrawn")`, `version
    unreadable (NAME = "…") — …`, `version not declared (NAME) — …`. Empty
    for a release number: its line is the owner's notice or its gate."""
    state = gate_state(literal)
    if state == "withdrawn":
        return f'withdrawn ({name} = "{GATE_WITHDRAWN}")'
    if state == "unreadable":
        return (f'version unreadable ({name} = "{literal}") — not a release number: '
                "this build announces no release and does not gate")
    if state == "undeclared":
        return f"version not declared ({name}) — this build announces no release"
    return ""
