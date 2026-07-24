"""Variant-file helpers for responsive layout variants (``home@regular.json``).

A layout variant is a sibling file of a base screen layout whose stem is
``<base>@<sizeClass>``. The variant replaces the WHOLE tree when the
runtime size class matches; there is no partial merge (structure sharing
stays with include/style). v1 accepts the single-size-class vocabulary
(compact / medium / regular) only — landscape and combined forms remain
inline-``responsive`` territory.

Mirrors ``shared/core/layout_variant.rb`` — keep the two in sync.
"""

from __future__ import annotations

# v1 file-suffix vocabulary. The inline `responsive` attribute keeps its
# full 7-value vocabulary (see responsive_resolver.rb) — only these three
# are legal as a file suffix.
VALID_VARIANT_CLASSES: tuple[str, ...] = ("compact", "medium", "regular")

# Recognized inline-responsive vocabulary that v1 rejects as a file suffix.
INLINE_ONLY_CLASSES: tuple[str, ...] = (
    "landscape",
    "compact-landscape",
    "medium-landscape",
    "regular-landscape",
)


def split_variant(stem: str) -> tuple[str, str | None]:
    """Split a layout file stem into ``(base, size_class)``.

    ``home@regular`` → ``("home", "regular")``; ``home`` → ``("home", None)``.
    Splits on the LAST ``@`` so a nested ``a@b@c`` yields base ``a@b`` —
    the constraint gate rejects that base separately.
    """
    if "@" not in stem:
        return stem, None
    base, _, cls = stem.rpartition("@")
    return base, cls


def is_variant(stem: str) -> bool:
    """True when the stem carries an ``@`` variant suffix (any suffix —
    invalid suffixes still make the file a variant for exclusion purposes,
    the gate reports them)."""
    return "@" in stem


def variant_struct_stem(base: str, cls: str) -> str:
    """The synthetic snake stem reserved for the generated variant view
    (``home`` + ``regular`` → ``home_regular_variant``). A real layout with
    this stem would collide with the generated type name — the gate
    rejects that."""
    return f"{base}_{cls}_variant"
