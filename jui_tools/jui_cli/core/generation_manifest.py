"""`jui build`'s view of the generation manifest.

🚨 THE RULE ITSELF IS NOT HERE ANY MORE. It moved to
`shared/core/generation_manifest.py` on 2026-09-09 so that `jsonui-doc` could
write the same record — until then this module was reachable only from
`jui_tools`, and the documentation site wrote 1061 files per run while
recording none of them. Answering "which version generated this page" then
cost four separate measurements (the page's own stamp, which carries a time
and no version; the bootstrap landing time; the shared checkout's reflog; and
an enumeration of every generator reachable on the machine — five copies, of
which the first sweep found one).

This module is the thin adapter: it finds `shared/core` the way every other
consumer of it does and re-exports the names this package has always
imported, so `build_cmd` and the arms that drive them keep driving the real
rule rather than a copy of it. Same shape as
`test_tools/jsonui_test_cli/validation/toolchain.py`, for the same reason.

⚠️ Do not reintroduce the writer here. Two copies of one record is the shape
that lets two tools disagree about what a project's tree contains while each
stays internally consistent.

**When `shared/core` is absent this module does not raise on import.**
`AVAILABLE` says so and every name is missing rather than wrong. A tool tree
synced without `shared/` still runs everything that does not need the
manifest, and the CALLER says what it is skipping — the same contract
`shared_core.load` states for itself. Importing this module must therefore
never be the thing that fails a build: a missing record is a gap, and a
build that dies because it could not write a note about itself would be
worse than the gap.
"""

from __future__ import annotations

#: Where the manifest lives. DATA, not the rule — kept here so a caller can
#: name the path in a message even when the rule itself is unreachable.
MANIFEST_DIRNAME = ".jsonui-cli"
MANIFEST_FILENAME = "generation-manifest.json"


def _rule():
    """`shared/core/generation_manifest`, or None when it is not in this tree."""
    from . import shared_core
    return shared_core.load("generation_manifest")


_MODULE = _rule()

#: False when `shared/core` is not in this tree. Callers check this and say
#: what they are skipping; they do not guess at a version they cannot record.
AVAILABLE = _MODULE is not None

if _MODULE is not None:
    # Re-export the real names. `vars()` rather than an explicit list: the
    # surface is twenty-odd names across two call sites and two test modules,
    # and a hand-written list is a second declaration of the same thing —
    # it goes stale silently, and the failure is an AttributeError pointing
    # at this file rather than at the omission.
    for _name, _value in vars(_MODULE).items():
        if not _name.startswith("_"):
            globals()[_name] = _value
    del _name, _value


def __getattr__(name: str):
    """Explain the absence instead of raising a bare AttributeError.

    Without this, a caller that forgot to check `AVAILABLE` fails with
    "module has no attribute 'save'", which reads as a typo in this package
    rather than as a tree without `shared/`. The distinction is the whole
    point of the flag, so the error says which of the two it is.
    """
    if not AVAILABLE:
        raise AttributeError(
            f"generation_manifest.{name} is unavailable: "
            f"shared/core/generation_manifest.py is not in this tree. "
            f"Check `generation_manifest.AVAILABLE` and report the skip "
            f"rather than treating the manifest as empty."
        )
    raise AttributeError(f"module 'generation_manifest' has no attribute {name!r}")
