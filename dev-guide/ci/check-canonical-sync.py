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

   Since 2026-09-02 the byte comparison covers EVERY canonical schema, the
   vendored fixtures included: the clearState rewrite sat in
   actions.schema.json with the vendored copy a commit behind and every gate
   green, because only mock.schema.json had a byte guard.

2. The Android permission map. Cross-platform permission names ->
   android.permission.* lives in the Android driver
   (ANDROID_PERMISSION_MAP in JsonUITestRunner.kt) and, since `pregrant`
   grew an Android arm (2026-09-02), as a deliberate copy in this repo's
   schema.py — the fourth copy of a cross-repo table. A divergent copy
   means pregrant revokes a different permission than the driver asserts,
   and the deny-assert then fails for a reason nobody declared.

3. Condition keys. The set lives in FIVE places — the canonical schema, this
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
FIXTURES = HERE / "test_tools/tests/schema_fixtures"

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


def check_schema_bytes(canonical_root: Path) -> tuple[int, int]:
    """Byte-identical, because the re-vendor step is `cp`.

    Structural comparison was the other option and is weaker in the way that
    matters: the drift that actually occurred was one escape inside a
    description, which every structural comparison calls equal and `cp`
    does not.

    ALL canonical schemas are compared, not just mock.schema.json: the
    clearState rewrite (2026-09-02) drifted in actions.schema.json with
    every gate green, because only mock had a byte guard. mock stays the
    one special case in WHERE the local copy lives — it is the only schema
    the CLI ships (static/, so the `$schema` line next to generated mocks
    resolves in an editor); the rest are test-only vendored fixtures. That
    shipped path is the reason it was the only one guarded at first.

    Returns (identical, total) so the green line reports what this run
    MEASURED, not the size of a table it was configured with.
    """
    schemas = sorted(canonical_root.glob("schemas/*.schema.json"))
    if not schemas:
        cannot_attempt(
            f"no *.schema.json under {canonical_root}/schemas — there was "
            "nothing to compare")
    identical = 0
    for canonical in schemas:
        local = (SHIPPED_MOCK if canonical.name == "mock.schema.json"
                 else FIXTURES / canonical.name)
        if not local.is_file():
            problems.append(
                f"{canonical.name}: no local copy at {local} — a canonical "
                "schema without a vendored counterpart is pinned by "
                "nothing. Vendor it (schema_fixtures/VENDOR.md).")
            continue
        if canonical.read_bytes() != local.read_bytes():
            problems.append(
                f"{canonical.name}: the local copy and the canonical copy "
                "are not byte-identical.\n"
                f"    canonical: {canonical}\n"
                f"    local    : {local}\n"
                "    The re-vendor step is `cp`, so whichever was edited "
                "alone loses its change on the next re-vendor.")
            continue
        identical += 1
    return identical, len(schemas)


PERMISSION_MAP_SOURCES = {
    "android driver": (
        "drivers/android/jsonuitestrunner/src/main/kotlin/com/jsonui/"
        "testrunner/runner/JsonUITestRunner.kt",
        r"ANDROID_PERMISSION_MAP\s*=\s*mapOf\(([^)]+)\)",
        r'"([^"]+)"\s+to\s+"([^"]+)"'),
}
CLI_PERMISSION_MAP = (
    HERE / "test_tools/jsonui_test_cli/schema.py",
    r"ANDROID_PERMISSION_MAP\s*=\s*\{([^}]+)\}",
    r'"([^"]+)":\s*"([^"]+)"')


def check_permission_map(canonical_root: Path) -> int:
    """The pregrant copy and the driver's map must be the same table."""
    def extract(path: Path, block_pattern: str, pair_pattern: str, label: str) -> dict:
        if not path.is_file():
            cannot_attempt(f"{label}: {path} is not there")
        match = re.search(block_pattern, path.read_text(encoding="utf-8"))
        if match is None:
            cannot_attempt(
                f"{label}: no ANDROID_PERMISSION_MAP matched in {path.name} — "
                "the constant was renamed or moved, so this guard is not "
                "reading it any more")
        table = dict(re.findall(pair_pattern, match.group(1)))
        if not table:
            cannot_attempt(f"{label}: the matched map is empty")
        return table

    (rel, block, pair), = PERMISSION_MAP_SOURCES.values()
    driver = extract(canonical_root / rel, block, pair, "android driver")
    cli_path, cli_block, cli_pair = CLI_PERMISSION_MAP
    cli = extract(cli_path, cli_block, cli_pair, "cli schema.py")
    if driver != cli:
        only_driver = {k: v for k, v in driver.items() if cli.get(k) != v}
        only_cli = {k: v for k, v in cli.items() if driver.get(k) != v}
        problems.append(
            "android permission map: pregrant's copy and the driver's "
            "disagree.\n"
            f"    driver-side entries not mirrored: {only_driver}\n"
            f"    cli-side entries not mirrored   : {only_cli}\n"
            "    A divergent copy makes pregrant revoke a different "
            "permission than the driver's deny-assert reads.")
    return len(driver)


def check_condition_keys(canonical_root: Path) -> list[int]:
    schema = canonical_root / "schemas/actions.schema.json"
    if not schema.is_file():
        cannot_attempt(f"{schema} is not there")
    declared = set(json.loads(schema.read_text(encoding="utf-8"))
                   ["definitions"]["condition"]["properties"])
    if not declared:
        cannot_attempt("actions.schema.json declares no condition properties")

    # What the green line reports has to be what this run MEASURED, not the
    # size of the table it was configured with: `3 driver(s)` is true even in
    # a run that read nothing, and this file's whole subject is guards that
    # pass without a subject.
    compared: list[int] = []
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
        compared.append(len(found))
        if found != declared:
            problems.append(
                f"condition keys: the {driver} driver and the canonical "
                "schema disagree.\n"
                f"    only in schema: {sorted(declared - found)}\n"
                f"    only in {driver:<7}: {sorted(found - declared)}\n"
                "    A condition key a driver does not know is fail-safe "
                "UNMET, so every step gated on it is SKIPPED — which reads "
                "on a report exactly like a pass.")
    return compared


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path to jsonui-test-runner checkout>",
              file=sys.stderr)
        return 2
    canonical_root = Path(argv[1]).resolve()
    if not canonical_root.is_dir():
        cannot_attempt(f"{canonical_root} is not a directory")

    identical, total = check_schema_bytes(canonical_root)
    map_entries = check_permission_map(canonical_root)
    compared = check_condition_keys(canonical_root)

    if problems:
        for problem in problems:
            print(f"DRIFTED: {problem}", file=sys.stderr)
        return 1
    print(f"OK: {identical}/{total} schema(s) byte-identical to canonical "
          f"(mock from the shipped copy, the rest vendored fixtures); "
          f"permission map agrees ({map_entries} entries); "
          f"condition keys agree across {len(compared)} driver(s), "
          f"{'/'.join(str(n) for n in compared)} key(s) read")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
