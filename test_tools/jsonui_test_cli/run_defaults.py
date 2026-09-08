"""Run-scoped defaults that travel with the installed bundle.

A default orientation cannot be resolved at install time. One installed
bundle is shared by every lane — `test.install.ios.target_dir` is a single
directory, `validate` runs once per run, and the same files are then executed
against a phone and a tablet — so a resolved value would be right for at most
one of them. What CAN be installed is the *table*: tier -> orientation is a
statement about form factors, not about a device, so one copy of it answers
for all four lanes and the driver reads the row for the tier it resolves at
run time.

The table travels as a sidecar (`jsonui-test-run.json`) next to the tests
rather than as a field baked into each of them. Three reasons, in the order
they matter:

* Absence stays readable. A file with no baked-in default is
  indistinguishable from a file installed before the feature existed; a
  missing sidecar says "installed by an older CLI" and an empty
  `orientation` says "no default declared". `x-requires-driver` cannot
  make that distinction for iOS or Android, because neither driver's
  version is readable from the project tree (see `validation.runtime_support`),
  so the sidecar is where the two states separate.
* One table stays one table. Baking it into every test would make N copies
  of one declaration — 75 files on the project this came from — so changing
  one character of config would move the bytes of all of them.
* The driver side is a single known path, which both drivers can already
  read (iOS walks `resourceURL`, Android opens an asset path).

Hence `SIDECAR_ALWAYS`: the file is written on every install, including when
nothing is declared. A sidecar written only when a default exists would put
"nothing declared" and "old install" back into one observation, which is the
whole reason it is a sidecar.

`schemaVersion` is here because this file is read by drivers OLDER than the
one that introduced the field it grows next. Version-gating through
`x-requires-driver` is note-only on iOS and Android, so the sidecar has to
carry enough for a driver to say "I do not know this version" and skip,
rather than misread it.
"""

from __future__ import annotations

from .schema import ORIENTATION_DEFAULT_TIERS, RESPONSIVE_ORIENTATIONS

#: Read by the iOS/Android/Web drivers from the root of the installed bundle.
SIDECAR_FILENAME = "jsonui-test-run.json"

#: Bumped when the shape changes in a way an older driver must not guess at.
SIDECAR_SCHEMA_VERSION = 1

#: The sidecar is written even when it declares nothing. See module docstring.
SIDECAR_ALWAYS = True


def validate_orientation_defaults(test_config) -> list[str]:
    """Error strings for a bad `test.orientation` block, or [].

    Reported by `validate`, before anything is installed. A typo here is
    silent in the worst direction: an unrecognised tier key simply never
    matches, the lane keeps whatever orientation the device booted in, and
    every assertion still passes — in the orientation nobody chose. There is
    no failing step to trace back to the config.
    """
    if "orientation" not in (test_config or {}):
        return []
    block = test_config["orientation"]
    if not isinstance(block, dict):
        return [
            f"test.orientation must be an object keyed by tier "
            f"({', '.join(ORIENTATION_DEFAULT_TIERS)}), got: "
            f"{type(block).__name__}. A single value cannot be the answer for "
            f"every lane — that is the reason this key is a table."
        ]
    errors = []
    for tier in sorted(block):
        if tier not in ORIENTATION_DEFAULT_TIERS:
            errors.append(
                f"test.orientation: unknown tier '{tier}' (allowed: "
                f"{', '.join(ORIENTATION_DEFAULT_TIERS)}). The "
                f"'*-landscape' responsive buckets are not tiers — they "
                f"already name an orientation, so they cannot be given one."
            )
            continue
        value = block[tier]
        if value not in RESPONSIVE_ORIENTATIONS:
            errors.append(
                f"test.orientation.{tier}: unknown orientation {value!r} "
                f"(allowed: {', '.join(RESPONSIVE_ORIENTATIONS)})"
            )
    return errors


def build_sidecar(test_config) -> dict:
    """The sidecar content for this project's config.

    Only tiers that are both known and valid are emitted, so a config that
    failed `validate_orientation_defaults` cannot put a value the driver
    does not understand onto a device. `orientation` is always present —
    empty when nothing is declared — because an absent key and an absent
    file would otherwise mean the same thing to the reader.
    """
    block = (test_config or {}).get("orientation")
    orientation = {}
    if isinstance(block, dict):
        for tier in ORIENTATION_DEFAULT_TIERS:
            value = block.get(tier)
            if value in RESPONSIVE_ORIENTATIONS:
                orientation[tier] = value
    return {
        "schemaVersion": SIDECAR_SCHEMA_VERSION,
        "orientation": orientation,
    }
