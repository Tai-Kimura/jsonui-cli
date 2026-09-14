"""A backdrop that does not reach under the whole target is silent there.

`_striped_backdrop` exists because a material over a flat white field is
white at every setting — the `backdrop-collapses-8bit` ledger row, where
`prominent` and `thick` rendered IDENTICAL pictures, not close ones. Two
`Blur` attributes were given stripes and the collapse went away.

2026-09-14: the three glass fixtures (`TextField.applyLiquidGlass` x2,
`TextField.glassEffectStyle`) had NO backdrop at all and rendered over the
bare white root — the same defect, one component along, found by reading
the rule table rather than by a render disagreeing.

Fixing it surfaced the second half: `Blur`'s target is 100x100 and the
backdrop was written as a literal 100x100 to match, but `TextField`'s base
width is 200. A 100pt backdrop under a 200pt field leaves HALF THE TARGET
over white, and that half is exactly as silent as the whole thing was
before. So the width is now a parameter and the rule is checked here for
every owner, present and future, against that section's own base width.

🔻 WHAT THE ARMS BELOW CANNOT SEE: nothing photographs these three. A
filtered run on 2026-09-14 skipped all three with `mode uikit not hosted
(SwiftUI dynamic host)` — 77 fixtures share that reason, separately from
the 938 the filter dropped and the 73 not applicable to ios. Both hosts
are SwiftUI and the SSoT declares both attributes `"mode": "uikit"`.
Downstream of that the renderers are empty too (codegen emits neither
spelling; the dynamic converter parses them and reads them nowhere; the
uikit implementation is real but sits inside the `case "number",
"decimal":` keyboard branch and dresses the accessory bar, which no
fixture reaches).

So the backdrop is a NECESSARY condition placed early, not evidence that
anything works. It earns its keep on the FIRST bake after the declaration
opens: a first bake over white would record `true` and `false` as one
picture and no gate would object — see
`test_the_arms_here_do_not_claim_the_picture_changed`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jui_tools"))

from jui_cli.conformance import rules  # noqa: E402


def _striped_owners() -> list[tuple[str, dict]]:
    """Every rule entry whose root backdrop is a STRIPED one.

    Keyed off the node's shape, not off a list of names, so an owner added
    later is covered without editing this file. `weight` also declares a
    `root.backdrop` — a single flat `rival` node with no children — and is
    correctly not one of these.
    """
    found = []
    for key, extra in rules.BASE_ATTRS_BY_ATTRIBUTE.items():
        for node in (extra or {}).get("root.backdrop") or []:
            if node.get("id") == "backdrop" and node.get("child"):
                found.append((key, node))
    return found


def _target_base(key: str) -> dict:
    """The base attrs of the target the backdrop has to sit under.

    An UNSCOPED key is a `common` attribute, whose fixture is hosted on
    `DEFAULT_COMMON_HOST`. Reading `None` there (the first version of this
    helper) made `glass` skip its own coverage arm — a green run with a
    silent `s` in it, which is the failure mode this whole file is about.
    """
    section = key.split(".")[0] if "." in key else rules.DEFAULT_COMMON_HOST
    return rules.BASE_ATTRS.get(section) or {}


def _effective(key: str, axis: str) -> int | None:
    """The target's size on `axis` AFTER this attribute's own overrides."""
    merged = {**_target_base(key),
              **{k: v for k, v in
                 (rules.BASE_ATTRS_BY_ATTRIBUTE.get(key) or {}).items()
                 if not k.startswith("root.")}}
    value = merged.get(axis)
    return value if isinstance(value, int) else None


#: Axes no backdrop can be checked against, with why. `TextField` declares
#: `width` only: its height is whatever the field's content comes to
#: (`wrapContent`), so there is no number to cover. That is fine here — the
#: field is roughly 34pt against a 100pt backdrop — but it is an assumption
#: about a rendered size, not a declared one, so it is written down rather
#: than skipped past.
_UNSIZED_AXES = {
    ("TextField.applyLiquidGlass", "height"),
    ("TextField.glassEffectStyle", "height"),
}


class TestTheBackdropCoversTheTarget:
    def test_there_is_more_than_one_owner(self):
        """Positive control. Every arm below iterates this list; if the shape
        predicate stops matching, they all pass by iterating nothing."""
        owners = dict(_striped_owners())
        assert len(owners) >= 4, owners
        assert "Blur.effectStyle" in owners
        assert "TextField.applyLiquidGlass" in owners

    @pytest.mark.parametrize("key,node", _striped_owners(), ids=lambda v: v if isinstance(v, str) else "")
    @pytest.mark.parametrize("axis", ["width", "height"])
    def test_the_backdrop_reaches_the_target_on_both_axes(self, key, node, axis):
        """Both axes: a 200x100 backdrop under a 200x200 target leaves the
        bottom half over white, which is the same silence lying down."""
        want = _effective(key, axis)
        if want is None:
            assert (key, axis) in _UNSIZED_AXES, (
                f"{key}: target declares no integer {axis} and is not in "
                f"_UNSIZED_AXES — add it with the reason, or give it a size")
            return
        assert node[axis] >= want, (
            f"{key}: backdrop {node[axis]}pt vs a {want}pt target on {axis} — "
            f"{want - node[axis]}pt of the target sits over white and cannot "
            f"show the attribute")

    def test_the_unsized_list_is_exactly_what_is_unsized(self):
        """An exemption list only works while it is exact.

        The coverage arm above used to `skip` when it could not resolve a
        size, and `glass` — the one owner this file was written for — took
        that branch silently: a green run with an `s` in it. Now every
        unmeasurable axis has to be named here, and naming one that IS
        measurable is equally red, so the list cannot quietly grow to cover
        a real gap."""
        actual = {(k, axis) for k, _ in _striped_owners() for axis in
                  ("width", "height") if _effective(k, axis) is None}
        assert actual == _UNSIZED_AXES, (
            f"only in the code: {sorted(actual - _UNSIZED_AXES)}; "
            f"only in the list: {sorted(_UNSIZED_AXES - actual)}")

    @pytest.mark.parametrize("key,node", _striped_owners(), ids=lambda v: v if isinstance(v, str) else "")
    def test_the_bands_fill_the_backdrop_counting_the_fill_as_one(self, key, node):
        """The backdrop's own `background` is the LAST band, not a margin.

        This arm was first written as `stripes >= width` and went red on the
        two shipped Blur entries: four 20pt stripes cover 80 of 100pt. The
        arm was wrong and the fixture was right — the remaining 20pt is the
        red fill showing through, and the baked `ultrathin` render uses it
        (its right edge reads (190,134,108), green smeared into red). A
        200pt backdrop built by paving 10 stripes across it would have
        evicted red from the palette entirely."""
        covered = sum(s["width"] for s in node["child"])
        assert covered + rules._STRIPE_PT == node["width"], (
            f"{key}: {covered}pt of stripes + one {rules._STRIPE_PT}pt fill "
            f"band != {node['width']}pt backdrop")

    @pytest.mark.parametrize("key,node", _striped_owners(), ids=lambda v: v if isinstance(v, str) else "")
    def test_every_palette_colour_survives_at_every_width(self, key, node):
        """Widening must not drop a colour. The fill counts: it is a band."""
        shown = {s["background"].upper() for s in node["child"]}
        shown.add(node["background"].upper())
        assert shown == {c.upper() for c in rules._STRIPE_COLOURS}, (
            f"{key}: palette {sorted(shown)} is missing "
            f"{sorted({c.upper() for c in rules._STRIPE_COLOURS} - shown)}")

    @pytest.mark.parametrize("key,node", _striped_owners(), ids=lambda v: v if isinstance(v, str) else "")
    def test_the_stripes_alternate_light_and_saturated(self, key, node):
        """What makes the backdrop work is CONTRAST, not the presence of
        children. Measured on the baked `common/effectStyle__*` renders with
        this palette: the nine styles' mean colours are all distinct, and the
        left-to-right swing runs 120.7 (ultrathin) to 10.3 (thick). A flat
        palette drives both to 0."""
        colours = [s["background"] for s in node["child"]]
        assert len(set(colours)) >= 2, f"{key}: one colour is not a stripe"
        whites = [c for c in colours if c.upper() == "#FFFFFF"]
        assert whites, f"{key}: no light stripe — nothing for a dark scrim to lift"
        assert len(whites) < len(colours), f"{key}: every stripe is white"

    @pytest.mark.parametrize("key,node", _striped_owners(), ids=lambda v: v if isinstance(v, str) else "")
    def test_the_backdrop_is_not_shared_between_owners(self, key, node):
        """Built per call so one entry cannot mutate another's child list."""
        others = [n for k, n in _striped_owners() if k != key]
        assert all(n is not node for n in others)
        assert all(n["child"] is not node["child"] for n in others)


class TestTheBlurBaselinesAreNotDisturbed:
    """The two Blur entries have baked baselines. Widening the shared helper
    for the glass family must not move them — so the default stays 100 and
    the letter ids stay letters. A change here is a twelve-fixture re-bake
    that says nothing new, which is why it is worth an arm."""

    @pytest.mark.parametrize("key", ["Blur.blurRadius", "Blur.effectStyle"])
    def test_blur_keeps_the_geometry_its_baselines_were_baked_with(self, key):
        node = dict(_striped_owners())[key]
        assert (node["width"], node["height"]) == (100, 100)
        assert [s["id"] for s in node["child"]] == [
            "stripe_a", "stripe_b", "stripe_c", "stripe_d"]
        assert [s["background"] for s in node["child"]] == [
            "#FFFFFF", "#0000FF", "#FFFFFF", "#00AA00"]

    def test_the_default_width_is_the_blur_width(self):
        """The default is what protects the baselines; a caller that forgets
        to pass a width gets the baked geometry, not a new one."""
        node = rules._striped_backdrop()[0]
        assert node["width"] == 100
        assert [s["id"] for s in node["child"]] == [
            "stripe_a", "stripe_b", "stripe_c", "stripe_d"]


#: Every glass spelling, and what it is. `glass` is the live one — common,
#: `mode: [uikit, swiftui]`, class `visual`, the only one a SwiftUI host can
#: photograph. The other two are TextField-only, uikit-only and SUPERSEDED
#: by it (SSoT 16b350d6); the normalizer fold is not written yet, so both
#: spellings are live and both get a backdrop.
_GLASS_KEYS = ("glass",
               "TextField.applyLiquidGlass",
               "TextField.glassEffectStyle")


class TestTheGlassFixturesGotOne:
    @pytest.mark.parametrize("key", _GLASS_KEYS)
    def test_the_glass_attributes_declare_a_backdrop(self, key):
        assert key in dict(_striped_owners()), (
            f"{key} renders over the bare white root; a material over white "
            f"is white at every setting")

    @pytest.mark.parametrize("key", _GLASS_KEYS)
    def test_each_glass_backdrop_matches_its_own_targets_width(self, key):
        node = dict(_striped_owners())[key]
        assert node["width"] == _effective(key, "width") == 200
        assert len(node["child"]) == 9    # 200/20, less the fill band

    def test_the_live_spelling_is_square_because_its_target_is(self):
        """`glass` is hosted on the common `View` base, 200x200 — so unlike
        the TextField pair its backdrop needs the second axis too."""
        node = dict(_striped_owners())["glass"]
        assert (node["width"], node["height"]) == (200, 200)
        assert _effective("glass", "height") == 200


class TestTheTargetDoesNotCoverItsOwnBackdrop:
    """A backdrop behind an OPAQUE target is decoration.

    The common `View` base paints its target `#DDDDDD` — 87% white — across
    the full 200x200. An effect that works on what is behind the view then
    has an opaque grey sheet behind it and the stripes never reach the lens,
    so the backdrop would have been added and changed nothing. `glass`
    therefore also carries `background: None`, which REMOVES the base key.
    """

    def test_glass_drops_the_opaque_base_fill(self):
        extra = rules.BASE_ATTRS_BY_ATTRIBUTE["glass"]
        assert "background" in extra and extra["background"] is None
        assert "background" in rules.BASE_ATTRS[rules.DEFAULT_COMMON_HOST], (
            "the base no longer paints the target; this override is now a "
            "no-op and the reason written beside it is stale")

    def test_the_blur_families_keep_their_own_fill_rules(self):
        """Control: the override is scoped to `glass`. `Blur`'s target is the
        effect itself, not a view painted behind it, so it neither has nor
        needs this."""
        for key in ("Blur.blurRadius", "Blur.effectStyle"):
            assert "background" not in rules.BASE_ATTRS_BY_ATTRIBUTE[key]


class TestWhatTheseArmsDoNotClaim:
    def test_the_arms_here_do_not_claim_the_picture_changed(self):
        """A backdrop is necessary, not sufficient.

        MEASURED after this change (iPhone 17 Pro, ios 26.4, the new SSoT):
        `common/glass__true`, `common/glass__false` and their shared control
        all three render and all three are byte-identical — 0 differing
        pixels in every pairing, control included. `glass` is ignored end to
        end; the emitters are the SwiftJsonUI lane's work. The backdrop is
        what makes the FIRST bake after they land able to disagree.

        The two superseded uikit spellings are not photographed at all.
        """
        for key in ("TextField.applyLiquidGlass", "TextField.glassEffectStyle",
                    "glass"):
            node = dict(_striped_owners())[key]
            # The rule table is the whole of what this change touched.
            assert set(node) == {"type", "id", "width", "height",
                                 "background", "orientation", "child"}
