"""What a `screen_parent_spec` may declare, and what it may not.

A parent spec is a container: its content comes from the sub-specs it lists.
The merger reads only `version`, `metadata`, `relatedFiles`, `notes`,
`structure.notes`, and scalar leftovers under the three merged sections. Every
list value under `structure` / `stateManagement` / `dataFlow`, and every
section it does not enumerate, is **discarded without a word**.

Measured on a real parent: its `dataFlow.repositories` declared nine methods
across two repositories, and editing them changed nothing. `jui build`,
`jui verify`, `jsonui-doc validate spec` and `generate project --dry-run` were
all green, in both directions, for months. A probe that renamed a parameter in
the parent produced the sub-spec's value and reported zero conflicts, because
the parent was never a participant to conflict with.

So declaring one of these in a parent is an error, not a conflict: there is no
disagreement to resolve, only a declaration that will not be read. The fix is
always the same — put it in a sub-spec, which is where the merger looks.
"""

from __future__ import annotations

#: Sections the merger reads from the parent. Anything else it drops.
PARENT_READS_TOP_LEVEL = frozenset({
    "$schema", "type", "version", "metadata", "subSpecs",
    "relatedFiles", "notes",
    # Read partially — see PARENT_READS_WITHIN.
    "structure", "stateManagement", "dataFlow",
})

#: Within those three, the parent's scalar values fill empty slots and its
#: `structure.notes` is carried. Lists are the ones that vanish.
PARENT_READS_WITHIN = {"structure": frozenset({"notes"})}

#: Dict-valued keys the parent must not declare either. `dataFlow.viewModel`
#: is not a list, so the list rule below never saw it — and it was read from
#: the parent and dropped from the sub-specs, the exact mirror of the
#: repositories defect. Now that the sub-specs supply it, a parent declaring
#: one would be silently ignored, which is the failure being removed rather
#: than a new one worth keeping.
PARENT_MUST_NOT_DECLARE = {"dataFlow": ("viewModel",)}

MERGED_SECTIONS = ("structure", "stateManagement", "dataFlow")


def dropped_parent_declarations(parent_spec) -> list:
    """`[(path, message)]` for everything this parent declares in vain.

    Empty when the parent is a pure container, which is the shape a parent
    spec is for. Never guesses at intent: a declared-but-empty list says
    nothing and is left alone, because deleting it is the author's call and
    an empty list changes no output.
    """
    if not isinstance(parent_spec, dict):
        return []
    if parent_spec.get("type") != "screen_parent_spec":
        return []

    out: list = []
    for key, value in parent_spec.items():
        if key in PARENT_READS_TOP_LEVEL:
            continue
        if not value:
            continue
        out.append((key, _message(key)))

    for section in MERGED_SECTIONS:
        holder = parent_spec.get(section)
        if not isinstance(holder, dict):
            continue
        kept = PARENT_READS_WITHIN.get(section, frozenset())
        named = PARENT_MUST_NOT_DECLARE.get(section, ())
        for key, value in holder.items():
            if key in kept or not value:
                continue
            if not isinstance(value, list) and key not in named:
                continue
            out.append((f"{section}.{key}", _message(f"{section}.{key}")))
    return sorted(out)


def _message(path: str) -> str:
    return (
        f"a screen_parent_spec cannot declare '{path}' — it is a container, "
        "and the merger builds this section from the sub-specs in `subSpecs`. "
        "Anything written here is discarded, silently, and the generated code "
        "keeps whatever the sub-specs say. Move the declaration into the "
        "sub-spec it belongs to."
    )
