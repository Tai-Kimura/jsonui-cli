"""Does a declaration that names a file actually name one?

Four declarations across two tools point at files — `source.layout`,
`source.document`, `sources[].layout` / `.document`, and (in the doc tool)
`relatedFiles[].path`. None of them was ever resolved. A test naming a
layout that does not exist validated clean, `Errors: 0, Warnings: 0`; a spec
repository was measured with 11 of 353 `relatedFiles` paths pointing at
files that are not there, across three specs, with the run reporting PASSED.

It stayed hidden the way its two siblings did this week: **the neighbour
being checked reads as evidence that this one is**. `relatedFiles[].type` is
validated against an allow-list and errors on a bad value, so `relatedFiles`
looks like a checked declaration — and `path`, sitting beside something that
is guarded, is not suspected. The same shape as a schema whose
`additionalProperties: false` was enforced while its `required` was not.

It also decides what a green run means. Rewriting one `source.layout` to a
path that does not exist and re-running produced the same PASSED as before,
so the green was explained equally well by "the paths are right" and by
"nothing looked at the paths".

**A warning, on purpose, and not permanently.** One repository already has
11 findings and nobody knows how many the others have, so shipping this as
an error would turn a gate red in places that cannot act on it that day —
which is how a gate teaches people to skip it. Each project measures its own
count first; the weight moves to error once they reach zero. That intent
belongs in the message, because "temporarily a warning" and "a warning
forever" are indistinguishable to a reader, and the second is the one that
gets ignored.

Resolution is deliberately generous — every plausible root is tried and the
finding only appears when the path is under NONE of them. A false positive
here costs more than a miss: this check's whole purpose is that people act
on it, and the first thing that stops them is one wrong finding.
"""

from __future__ import annotations

from pathlib import Path

#: Roots a declared path may be written relative to, resolved once from the
#: config the run read and pushed in — the same shape as the platform
#: declaration, and for the same reason: a validator that searches for a
#: config from the file it is checking answers a different question in a
#: split tree, which has already gone wrong three times here.
_ROOTS: dict = {}

#: Kinds whose configured directory does not exist, so the check declined to
#: run. Reported once per run rather than silently skipped: a check that
#: quietly does nothing is indistinguishable from one that found nothing, and
#: that difference is the reason this whole file exists.
_SKIPPED: set = set()


def set_path_roots(project_root=None, config=None):
    """Declare where declared paths resolve from (`None` clears them).

    Cleared means silent: a run that cannot tell where the project is has no
    business reporting that a path is missing from it.
    """
    _ROOTS.clear()
    _SKIPPED.clear()
    if project_root is None:
        return
    root = Path(project_root)
    config = config or {}
    _ROOTS["project"] = root
    _ROOTS["layout"] = root / config.get(
        "layouts_directory", "docs/screens/layouts")
    _ROOTS["document"] = root / config.get(
        "spec_directory", "docs/screens/json")


def skipped_kinds() -> list:
    return sorted(_SKIPPED)


def _root_for(kind: str):
    """The directory this kind resolves under, or None when it is unusable.

    A project that keeps its layouts somewhere this run cannot name would
    otherwise have every single reference reported as missing — hundreds of
    findings, none of them actionable, on the first run after upgrading.
    Declining is the right answer; declining SILENTLY is not, so the caller
    is told.
    """
    root = _ROOTS.get(kind)
    if root is None:
        return None
    if not root.is_dir():
        _SKIPPED.add(kind)
        return None
    return root


def _candidates(value: str, kind: str):
    kind_root = _root_for(kind)
    if kind_root is not None:
        yield kind_root / value
        # A path written from the repository root rather than from the
        # declaration's own directory. Both spellings are in use, and this
        # check is not the place to decide between them.
        yield _ROOTS["project"] / value


def resolves(value, kind: str) -> bool:
    """True when *value* names a file under any root this run knows about.

    Also true when there is nothing to resolve against, so a caller cannot
    turn "we do not know" into a finding.

    The test file's own directory is NOT a candidate. These declarations are
    project-rooted — the driver resolves a layout from the layouts directory,
    not from beside the test — and accepting a file that happens to sit next
    to the test would make the check pass for a reason the runtime does not
    share.
    """
    if not isinstance(value, str) or not value.strip():
        return True          # a shape problem, reported by the shape check
    if Path(value).is_absolute():
        return Path(value).exists()
    candidates = list(_candidates(value.strip(), kind))
    if not candidates:
        return True          # nothing to resolve against — see `_root_for`
    return any(candidate.exists() for candidate in candidates)


def unresolved_message(key: str, value: str, kind: str) -> str:
    where = _ROOTS.get(kind)
    under = f" (looked under {where}" if where is not None else ""
    if where is not None:
        under += f" and {_ROOTS['project']})"
    return (
        f"'{key}' names a file that does not exist: {value}{under}. "
        "A warning for now — projects are measuring their existing counts "
        "and this becomes an error once they reach zero, so it is worth "
        "clearing rather than living with."
    )
