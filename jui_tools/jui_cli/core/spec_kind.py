"""Does a spec stand for a screen — the one answer every `jui` command reads.

`shared/core/spec_types.describes_a_screen`, loaded rather than restated, or
None when that module is unreachable. The table and its three answers
(True / False / None) are documented there.

🔻 ONE WRAPPER, NOT ONE PER COMMAND. `jui build` and `jui verify` each had
their own copy of this function, and the command loops that should have
called one of them did not: `verify`'s main loop and `generate project` read
every `*.spec.json` as a screen, so an `app_contracts_spec` — a file the tool
itself tells authors to write — was counted as a screen whose layout was
missing (2026-09-25, a consumer's `verify` said "verified 0 of 12 — 1 layout
not found on disk: app_contracts.spec"). Two copies of the question is how
one of them gets fixed and the other does not; every command asks it here.

A tree without `shared/` gets None for every type: callers skip AND name
what they skipped, so nothing is silently reclassified.
"""

from __future__ import annotations

from . import shared_core


def describes_a_screen(spec_type):
    core = shared_core.load("spec_types")
    if core is None:
        return None
    return core.describes_a_screen(spec_type)
