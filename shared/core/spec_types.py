"""What a `*.spec.json` type means, in one place.

Three packages ask this question and they had answered it separately: the
document validator dispatches on the type, the test gate discovers app-level
declarations by it, and `jui verify` decided which specs claim a Layout. That
third one asked it BACKWARDS -- it named the one type to skip -- so the moment
1.8.52 added `app_contracts_spec`, verify read it as a screen whose layout was
missing and reddened the very file it had just told the author to write.

⚠️ The failure is worth stating exactly, because the shape recurs: the tool
shipped a REMEDY and a CHECK in one version, and the remedy tripped the check.
Nothing was inconsistent inside either package. What was missing is that a new
type is news to more readers than the one adding it.

So the question is asked positively here. A type is not a screen unless it is
named as one, and a type nobody here knows is reported rather than assumed:

    describes_a_screen(t) is True   -> this spec stands for a screen
                          is False  -> it does not, and that is known
                          is None   -> this table has never heard of it

`None` is the third state and it is deliberately not folded into either
answer. Folded into True, a future container type reddens `missing_layouts`
exactly as `app_contracts_spec` just did. Folded into False, a future screen
type silently stops being covered and `missing_specs` goes quiet -- the worse
direction, because nothing appears. Callers say which they chose and name what
they skipped.

Measured 2026-09-08 across the three consumer trees plus the docs site: 294
spec files, every one of them carrying a `type`, in four values -- 279
`screen_spec`, 12 `screen_sub_spec`, 2 `screen_parent_spec`, 1
`app_contracts_spec`. There is no "no type" case in the corpus, but the tables
below still keep `None` separate from an unknown string, because a corpus is
not a population.
"""

from __future__ import annotations

#: Types whose file stands for one screen and therefore claims a Layout.
#: `screen_parent_spec` is here: it is a screen assembled from sub-specs, and
#: it is the half that carries `metadata.layoutFile`.
SCREEN_TYPES = frozenset({
    "screen_spec",
    "screen_parent_spec",
})

#: Types that live in the spec tree and stand for something other than a
#: screen. Each one is here because a caller would otherwise treat it as a
#: screen; the comment says which caller learned that the hard way.
NON_SCREEN_TYPES = frozenset({
    # Merged into its parent. `jui verify` has skipped this since before the
    # table existed.
    "screen_sub_spec",
    # A container for unit contracts no single screen owns (1.8.52). It has no
    # `metadata.layoutFile` and no layout, because it describes no screen --
    # which is exactly what made verify read its FILENAME as a layout id.
    "app_contracts_spec",
})


def describes_a_screen(spec_type) -> bool | None:
    """Does a spec of this type stand for a screen?

    ``None`` when the type is not in either table -- including when it is
    absent or not a string. The caller decides what to do and says so; this
    function does not guess, because both guesses have been wrong in
    production and in opposite directions.
    """
    if not isinstance(spec_type, str) or not spec_type:
        return None
    if spec_type in SCREEN_TYPES:
        return True
    if spec_type in NON_SCREEN_TYPES:
        return False
    return None
