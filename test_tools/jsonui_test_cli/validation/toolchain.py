"""`jsonui-test`'s view of the vendored-toolchain check.

🚨 THE RULE ITSELF IS NOT HERE ANY MORE. It moved to
`shared/core/toolchain_sync.py` on 2026-09-08 so that `jui build` could ask
the same question — until then this module was the only place that knew, and
its only production caller was `jsonui-test`, which meant the DELIVERY path
(`deploy.sh` → `jui build`) could not see a version split at all.

This module is the thin adapter: it finds `shared/core` the way every other
consumer of it does and re-exports the names this package has always
imported, so the ten arms that drive `sync_meta_mismatches` keep driving the
real rule rather than a copy of it.

⚠️ Do not reintroduce the comparison here. Two copies of one rule is exactly
the shape that let `jui build` and `jsonui-test` disagree about whether a
project was in step — and the disagreement was invisible, because each side
was internally consistent.
"""

from __future__ import annotations

from pathlib import Path

#: Fallback spellings, used only to keep this module importable when
#: `shared/core` is absent. They are DATA, not the rule.
SYNC_META_RELPATH = Path(".jsonui-cli") / "sync-meta.json"
UNKNOWN = "unknown"


def _rule():
    """`shared/core/toolchain_sync`, or None when it is not in this tree.

    🚨 Goes through `_prefer_sibling_jui_cli` rather than a plain import. A
    bare `import jui_cli` SUCCEEDS when a previous release is installed at
    `~/.jsonui-cli`, and that copy's `shared/core` does not have this module —
    so the rule would silently come back unavailable while a checkout sat
    right here. Measured while writing this: the first draft did exactly that
    and reddened five arms.

    ⚠️ Reuses the helper in this package instead of adding another walk. Two
    copies of it already exist (`branch_tests`, `screen_ids`); a third would
    be the same duplication this module was just rewritten to remove.
    """
    from .screen_ids import _prefer_sibling_jui_cli
    _prefer_sibling_jui_cli()
    try:
        from jui_cli.core import shared_core
    except ImportError:
        return None
    return shared_core.load("toolchain_sync")


def sync_meta_mismatches(project_root, running_version: str) -> list[str]:
    """Delegates to `shared/core/toolchain_sync.sync_meta_mismatches`.

    ⚠️ Returns [] when the shared rule is unreachable — the same answer it
    gives for "nothing to compare". That collapse is deliberate here and
    reported by the CALLER, which is the only place that can say "this check
    did not run" in a line a reader will see.
    """
    rule = _rule()
    if rule is None:
        return []
    return rule.sync_meta_mismatches(project_root, running_version)


def rule_is_available() -> bool:
    """Whether the shared rule could be loaded at all.

    Exists so a caller can tell "in step" from "never asked". Without it the
    two states print identically, which is the confusion this whole check was
    created to remove.
    """
    return _rule() is not None
