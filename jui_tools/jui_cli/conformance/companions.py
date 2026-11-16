"""Companion attributes for the paired codegen probe — derived from the ledger.

Plan 41's C0/C1/C2 write ONE attribute onto a bare host and compare against a
control without it. That shape cannot judge an attribute the adjudication
ledger says renders nothing on its own. `borderWidth` is the worked example:
`attribute_semantics.json` rules that a border is drawn only when BOTH
`borderWidth` and `borderColor` are declared, so the single-attribute probe
measures the ruling, not the converter — and a bound `borderWidth` that the
codegen mangles stays invisible because the alone-form emits nothing either
way (plan 41 triage §6, orchestrator confirmation 2026-08-04).

The fix is a PAIRED probe: write the companions on the target AND on the
control, so they cancel and only the attribute under test differs.

**The companion set is derived from the ledger, never hand-listed here.**
That was the explicit instruction (2026-08-04): a second copy of "what makes a
border" would drift away from the ruling the moment the ruling moved. Two
derivations are implemented, one per shape the ledger actually uses:

``ATTRIBUTE_PAIR``
    A topic carrying ``<x>Alone: "no-draw"`` keys declares that a lone member
    of that family draws nothing. The family's members are read out of the
    topic's ``observable`` keys, and each member's companions are the other
    members. `border` is the only topic with this shape today; the sweep is
    generic, so a new family starts working the day someone rules on it.

``LAYOUT_COMPANION``
    A topic whose ``observable`` points at a SYNTHETIC fixture id — one the
    per-attribute sweep does not generate — is realised by a fixture-builder
    module, and that module is the machine-readable form of the ruling. The
    companions are read back out of the layout it builds rather than restated.
    `size.maxBoundsClampFill` → `common/maxWidth__fill_clamp` → the layout
    `bounds_fixtures` builds → `{width: matchParent, height: 60}`.

A third shape exists and is deliberately NOT implemented — see
:data:`UNMEASURABLE`. `networkImage.noSrc` gates its state images on a runtime
LOAD STATE, not on a companion attribute. No arrangement of the layout makes a
codegen probe observe an error state, so those four attributes are recorded as
structurally out of scope with the reason, instead of being probed and
reported as defects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import bounds_fixtures, rules

#: `<x>Alone: "no-draw"` — the ledger's structured way of saying "a lone member
#: of this family renders nothing".
_ALONE_KEY = re.compile(r"^(?P<member>[a-z][A-Za-z0-9]*)Alone$")
_ALONE_VERDICT = "no-draw"

#: `observable` keys are `Component/attribute__case`.
_OBSERVABLE_KEY = re.compile(r"^(?P<component>[^/]+)/(?P<attribute>[^_]+(?:_[^_]+)*)__(?P<case>.+)$")


@dataclass(frozen=True)
class CompanionSpec:
    """The companions to write on BOTH sides of one attribute's probe."""

    component: str
    attribute: str
    #: attribute -> value, written on the target and on the control alike.
    companions: dict = field(default_factory=dict)
    #: Which ledger statement this was derived from. Travels into the report so
    #: a reader can check the derivation without trusting this module.
    source: str = ""
    kind: str = ""  # ATTRIBUTE_PAIR | LAYOUT_COMPANION | PROVISIONAL
    #: True when the ledger has NO ruling for this family and the companion is
    #: an informed guess. Such a probe is evidence for WRITING a ruling; it is
    #: never evidence that a converter is broken.
    provisional: bool = False
    reason: str = ""

    @property
    def key(self) -> tuple:
        return (self.component, self.attribute)


#: Families the ledger rules on that a codegen probe can never observe, with
#: the reason. Reported, not silently skipped — plan 41 keeps a no-silent-drop
#: ledger for exactly this.
UNMEASURABLE: tuple = (
    (
        "networkImage",
        ("NetworkImage.placeholder", "NetworkImage.hint",
         "NetworkImage.errorImage", "NetworkImage.loadingImage"),
        "attribute_semantics.json#semantics.networkImage.noSrc",
        "the ruling gates these on a runtime LOAD STATE (no src / loading / "
        "error), not on a companion attribute. Codegen emits one text for all "
        "states, so no arrangement of the layout can make the states differ "
        "here — this is a render-stage question (plan 41 Phase 3).",
    ),
)


def _members(topic_body: dict) -> list[tuple[str, str]]:
    """`(component, attribute)` pairs a topic's `observable` keys name."""
    out: list[tuple[str, str]] = []
    for key in (topic_body.get("observable") or {}):
        match = _OBSERVABLE_KEY.match(key)
        if not match:
            continue
        pair = (match.group("component"), match.group("attribute"))
        if pair not in out:
            out.append(pair)
    return out


def _representative(component: str, attribute: str, definitions: dict) -> Any:
    """The value the FIXTURE SUITE writes for this attribute, or None.

    Taken from `rules.plan_attribute` rather than re-derived, so a companion
    carries the same value the ledgered fixture carries.
    """
    section = definitions.get(component) or {}
    defn = section.get(attribute)
    if defn is None and component != "common":
        defn = (definitions.get("common") or {}).get(attribute)
    if defn is None:
        return None
    plan = rules.plan_attribute(component, attribute, defn)
    if isinstance(plan, rules.SkippedAttribute):
        return None
    cases = [c for c in plan.cases if c.alias_of is None]
    return cases[0].value if cases else None


def _attribute_pairs(semantics: dict, definitions: dict) -> list[CompanionSpec]:
    specs: list[CompanionSpec] = []
    for topic, body in (semantics or {}).items():
        if not isinstance(body, dict):
            continue
        alone = [k for k, v in body.items() if _ALONE_KEY.match(k) and v == _ALONE_VERDICT]
        if not alone:
            continue
        members = _members(body)
        if len(members) < 2:
            continue
        for component, attribute in members:
            companions = {}
            for other_component, other_attribute in members:
                if (other_component, other_attribute) == (component, attribute):
                    continue
                value = _representative(other_component, other_attribute, definitions)
                if value is not None:
                    companions[other_attribute] = value
            if not companions:
                continue
            specs.append(CompanionSpec(
                component=component,
                attribute=attribute,
                companions=companions,
                source=f"attribute_semantics.json#semantics.{topic}."
                       f"{{{','.join(sorted(alone))}}}",
                kind="ATTRIBUTE_PAIR",
            ))
    return specs


def _layout_companions(semantics: dict) -> list[CompanionSpec]:
    """Companions read back out of the module that BUILDS a ledgered fixture.

    `size.observable` names `common/maxWidth__fill_clamp`, and the only thing
    that emits an id with that case is `bounds_fixtures`. Reading the layout it
    builds keeps one truth: change the generator and the companion follows.
    """
    wanted: dict[str, tuple[str, str]] = {}
    for topic, body in (semantics or {}).items():
        if not isinstance(body, dict):
            continue
        for key in (body.get("observable") or {}):
            match = _OBSERVABLE_KEY.match(key)
            if match and match.group("case") == _BOUNDS_CASE:
                wanted[match.group("attribute")] = (topic, key)
    if not wanted:
        return []

    specs: list[CompanionSpec] = []
    # `_AXES` is the generator's own table of (axis, attribute, bound, shape).
    # Read, never written — this module must not become a second place that
    # decides what a clamp-fill fixture looks like.
    for axis, bound_attr, bound, _shape in bounds_fixtures._AXES:  # noqa: SLF001
        if bound_attr not in wanted:
            continue
        topic, observable_key = wanted[bound_attr]
        target = bounds_fixtures._target(axis, bound_attr, bound)  # noqa: SLF001
        companions = {
            k: v for k, v in target.items()
            if k not in ("type", "id", "background", bound_attr)
        }
        specs.append(CompanionSpec(
            component="common",
            attribute=bound_attr,
            companions=companions,
            source=f"attribute_semantics.json#semantics.{topic}.observable."
                   f"{observable_key} -> conformance/bounds_fixtures.py",
            kind="LAYOUT_COMPANION",
        ))
    return specs


_BOUNDS_CASE = "fill_clamp"


#: Families with NO ledger entry, probed provisionally because the measurement
#: is what a ruling would be written from. Kept tiny and loud on purpose: every
#: entry here is a gap in `attribute_semantics.json`, not a feature.
#:
#: Empty is the healthy state, and it is where a provisional probe is supposed
#: to end up: `View.highlighted` sat here until its measurement produced the
#: `highlight` topic (plan 49-E, on plan 41's paired-probe evidence), and the
#: pairing is now derived from the ledger like every other family. Anything
#: added here is a debt to be discharged the same way, not a place to park a
#: pairing that nobody wants to rule on.
PROVISIONAL: tuple = ()


def derive(semantics: dict, definitions: dict) -> dict:
    """`{(component, attribute): CompanionSpec}` for every pairable attribute."""
    specs: dict = {}
    for spec in (*_attribute_pairs(semantics, definitions),
                 *_layout_companions(semantics),
                 *PROVISIONAL):
        specs[spec.key] = spec
    return specs


def unmeasurable_report() -> list:
    """The state-gated families, as report rows."""
    return [
        {"topic": topic, "attributes": list(attributes), "source": source, "reason": reason}
        for topic, attributes, source, reason in UNMEASURABLE
    ]
