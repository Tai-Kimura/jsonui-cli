#!/usr/bin/env python3
"""Compare this tree against the canonical repo it copies from.

TWO LINKS, NEITHER OF WHICH ANY EXISTING GATE COVERS.

1. `mock.schema.json`. `schema_fixtures/VENDOR.md` makes jsonui-test-runner
   canonical and this repo's `static/mock.schema.json` a copy refreshed by
   hand. `test_schema_drift.py` compares the SHIPPED copy against the CLI
   constants — nothing compares shipped against canonical. So a fix applied
   to one copy survives until the next re-vendor and is then silently
   reverted, with every gate green.

   That is not hypothetical: it happened while the fix that prompted this
   script was being written, and then a SECOND time within minutes, when the
   same sentence was written into both copies by hand and they differed by
   one `\\u2014` escape. Two copies edited deliberately, on purpose, in the
   same sitting, still drifted.

2. Condition keys. The set lives in FIVE places — the canonical schema, this
   repo's `VALID_CONDITION_KEYS`, and one hard-coded set in each of the three
   drivers. `test_schema_drift.py` pins the first two to each other. Nothing
   pins the drivers.

   The failure mode is silence. All three drivers treat a condition holding
   an unknown key as fail-safe UNMET, so the gated step is SKIPPED — and a
   skip reads on a report exactly like a pass. Adding a sixth condition key
   here disables every step gated on it, on every platform, until all three
   drivers ship, with nothing anywhere saying so.

WHY IT IS HERE AND NOT IN A pytest. The comparison needs a checkout of
another repository. A test that skips when the sibling is absent is green on
every developer machine and real only in CI, which makes "it passed" and "it
did not run" the same result — the defect this whole guard family is about.
So: a script with three outcomes, run as an explicit CI step.

Exit codes: 0 in sync, 1 drifted, 2 could not be attempted (missing checkout,
or an extractor that found nothing — never pass on absence).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
SHIPPED_MOCK = HERE / "test_tools/jsonui_test_cli/static/mock.schema.json"

#: Where each driver states the condition keys it can evaluate, and the
#: pattern that lifts the set out. Declared as data so that adding a fourth
#: driver is one entry rather than a fourth copy of the comparison.
DRIVER_CONDITION_KEYS = {
    "ios": ("drivers/ios/Sources/JsonUITestRunner/Models/TestModels.swift",
            r"knownKeys\s*:\s*Set<String>\s*=\s*\[([^\]]+)\]"),
    "android": ("drivers/android/jsonuitestrunner/src/main/kotlin/com/jsonui/"
                "testrunner/models/StepConditionSerializer.kt",
                r"KNOWN_KEYS\s*=\s*setOf\(([^)]+)\)"),
    "web": ("drivers/web/src/models/types.ts",
            r"KNOWN_CONDITION_KEYS\s*:\s*ReadonlySet<string>\s*=\s*new Set\(\[([^\]]+)\]"),
}

problems: list[str] = []


def cannot_attempt(message: str) -> None:
    print(f"CANNOT ATTEMPT: {message}", file=sys.stderr)
    sys.exit(2)


def check_mock_schema(canonical_root: Path) -> None:
    """Byte-identical, because the re-vendor step is `cp`.

    Structural comparison was the other option and is weaker in the way that
    matters: the drift that actually occurred was one escape inside a
    description, which every structural comparison calls equal and `cp`
    does not.
    """
    canonical = canonical_root / "schemas/mock.schema.json"
    if not canonical.is_file():
        cannot_attempt(f"{canonical} is not there")
    if canonical.read_bytes() != SHIPPED_MOCK.read_bytes():
        problems.append(
            "mock.schema.json: the shipped copy and the canonical copy are "
            "not byte-identical.\n"
            f"    canonical: {canonical}\n"
            f"    shipped  : {SHIPPED_MOCK}\n"
            "    The re-vendor step is `cp`, so whichever was edited alone "
            "loses its change on the next re-vendor.")


def check_condition_keys(canonical_root: Path) -> None:
    schema = canonical_root / "schemas/actions.schema.json"
    if not schema.is_file():
        cannot_attempt(f"{schema} is not there")
    declared = set(json.loads(schema.read_text(encoding="utf-8"))
                   ["definitions"]["condition"]["properties"])
    if not declared:
        cannot_attempt("actions.schema.json declares no condition properties")

    for driver, (rel, pattern) in DRIVER_CONDITION_KEYS.items():
        path = canonical_root / rel
        if not path.is_file():
            cannot_attempt(f"{driver}: {path} is not there")
        match = re.search(pattern, path.read_text(encoding="utf-8"))
        if match is None:
            # A refactor that renames the constant must stop the guard
            # loudly. Returning "no keys" here would make every comparison
            # below trivially unequal or trivially equal depending on the
            # direction, and either way the guard would be reporting on
            # something it did not read.
            cannot_attempt(
                f"{driver}: no condition-key set matched in {rel} — the "
                "constant was renamed or moved, so this guard is not "
                "reading it any more")
        found = {a or b for a, b in
                 re.findall(r'"([^"]+)"|\'([^\']+)\'', match.group(1))}
        if not found:
            cannot_attempt(f"{driver}: the matched set is empty")
        if found != declared:
            problems.append(
                f"condition keys: the {driver} driver and the canonical "
                "schema disagree.\n"
                f"    only in schema: {sorted(declared - found)}\n"
                f"    only in {driver:<7}: {sorted(found - declared)}\n"
                "    A condition key a driver does not know is fail-safe "
                "UNMET, so every step gated on it is SKIPPED — which reads "
                "on a report exactly like a pass.")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path to jsonui-test-runner checkout>",
              file=sys.stderr)
        return 2
    canonical_root = Path(argv[1]).resolve()
    if not canonical_root.is_dir():
        cannot_attempt(f"{canonical_root} is not a directory")

    check_mock_schema(canonical_root)
    check_condition_keys(canonical_root)

    if problems:
        for problem in problems:
            print(f"DRIFTED: {problem}", file=sys.stderr)
        return 1
    print(f"OK: shipped mock.schema.json matches canonical; condition keys "
          f"agree across {len(DRIVER_CONDITION_KEYS)} driver(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
