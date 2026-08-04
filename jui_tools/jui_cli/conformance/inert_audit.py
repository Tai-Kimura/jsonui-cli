"""Inert-verdict attribution (``jui conformance inert-audit``, plan 34 Phase 0).

``control_diff`` answers "did the attribute change what this platform
rendered?" and ``cross_effect`` answers "do the platforms agree about that".
Between them they force an adjudication for exactly two shapes of inert:

- a **divergence** (ios active / android inert) — the cross-effect ledger's
  both-direction ratchet
- a **declared enum value inert everywhere** — the uniformly-inert check

Everything else falls through. ``control_diff.json`` fails a fixture only
when it is *listed and stopped differing*, so a fixture nobody listed is
"reported as inert without failing", by design — the ledger is opt-in
because a value equal to the platform default cannot differ. The cost of
that design is a blind spot with a precise shape:

    An attribute silently dropped on EVERY platform, or on the only
    platform it is declared for, produces no divergence and (unless it
    happens to test an SSoT enum value) no uniformly-inert flag. No check
    in the suite has an opinion about it.

This module measures that blind spot. It takes each platform's inert list
and asks which ledger, if any, already accounts for it:

``control_diff``   the fixture is asserted active there — an inert verdict
                   is already a regression, so it never reaches this audit
``cross_effect``   the fixture carries a ledger entry (an accepted
                   divergence or an accepted uniformly-inert value)
``attribute_semantics``  the contract declares the expected observable —
                   the ruling is machine memory, not a backlog item
``coverage``       ``coverage.json`` already records the attribute as
                   declared-but-unimplemented on that platform; adjudicating
                   it twice would just duplicate the gap ledger

What no channel claims is the **adjudication queue**: for each item, is the
inert verdict legitimate (the fixture shape leaves the attribute nothing to
do, the value equals the default) or is the attribute being silently
ignored? That question is human work — the machine's job is to guarantee
the queue is complete, which is what makes this an inventory rather than a
sample.

Phase 1 prunes the queue with the families that ARE mechanically decidable
(:func:`triage`); the residue is the human round. Nothing here fails a
build: the completeness ratchet is plan 34 Phase 3, and it can only be
switched on once the queue is empty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

#: Queue schema version; bump when the item shape changes.
SCHEMA_VERSION = 1

# --- attribution channels -------------------------------------------------- #

#: asserted active in ``control_diff.json`` — an inert verdict is a regression
CHANNEL_CONTROL_DIFF = "control_diff"
#: carries an entry in ``cross_effect.json`` (divergence or uniformly-inert)
CHANNEL_CROSS_EFFECT = "cross_effect"
#: covered by an ``observable`` block in ``attribute_semantics.json``
CHANNEL_CONTRACT = "attribute_semantics"
#: recorded in ``coverage.json`` as declared-but-unimplemented there
CHANNEL_COVERAGE = "coverage"

CHANNELS = (
    CHANNEL_CONTROL_DIFF,
    CHANNEL_CROSS_EFFECT,
    CHANNEL_CONTRACT,
    CHANNEL_COVERAGE,
)

# --- why the fixture escaped the existing checks ---------------------------- #

#: declared for one platform only — cross-effect has nothing to compare it
#: against, so its inert verdict is invisible to the agreement check
KIND_SINGLE_PLATFORM = "single-platform-scope"
#: inert on every in-scope platform while testing a value the SSoT enumerates
#: — the uniformly-inert check owns this; reaching the queue means unledgered
KIND_UNIFORM_DECLARED = "uniform-inert-declared-value"
#: inert on every in-scope platform with a representative (non-enum) value —
#: the structural hole this audit exists for
KIND_UNIFORM_UNDECLARED = "uniform-inert-undeclared-value"
#: the inert side of a divergence that carries no ledger entry
KIND_DIVERGENT_SIDE = "divergent-inert-side"
#: in scope on ≥2 platforms but lacking a verdict on at least one — the run
#: could not compare it, so it is neither adjudicated nor adjudicable
KIND_NOT_COMPARED = "not-compared"

# --- Phase 1 mechanical triage families ------------------------------------- #

#: the fixture layout is identical to its control's — removing the attribute
#: under test changed nothing about the file, so activeness is structurally
#: unmeasurable here (``Image/src``: an Image with no src renders nothing, so
#: the control must carry it). Not a defect in the implementation; a
#: limitation of the fixture shape, closed by a contract pointer.
FAMILY_CONTROL_IDENTICAL = "control-identical"
#: the fixture value equals the attribute's SSoT ``default`` — inert is the
#: definition, not a gap
FAMILY_VALUE_IS_DEFAULT = "value-is-default"
#: an alias spelling whose canonical fixture is in the queue too — one
#: adjudication covers both; the alias inherits it
FAMILY_ALIAS_OF_QUEUED = "alias-of-queued-canonical"
#: the fixture value is one of the generator's TYPE-level fallbacks
#: (``rules.DEFAULT_STRING`` / ``rules.DEFAULT_NUMBER``), not a value chosen
#: from the attribute's domain. ``hintFont: "sample"`` names no font, and the
#: numeric fallback 8 is a value platforms routinely use as their own default
#: (``spacing = json_data['spacing'] || 8`` in the kjui CheckBox is exactly
#: that collision) — either way the render cannot differ however correctly
#: the attribute is implemented. The disposition is fixture work — give the
#: attribute a representative value in ``rules.py`` and re-measure — not an
#: adjudication about the implementation.
FAMILY_TYPE_FALLBACK_VALUE = "type-fallback-value"
#: another declared value of the SAME attribute IS active on every platform
#: where this one is unattributed. The attribute is therefore demonstrably
#: implemented there, which narrows the question from "is this a gap?" to
#: "why is THIS value inert?" — it equals the platform default, or the value
#: alone is dropped. Evidence, not a verdict: ``contentMode__fill`` was a
#: real bug while its sibling values worked. Still a human call, but a much
#: cheaper one, and it rules out the expensive hypothesis.
FAMILY_SIBLING_VALUE_ACTIVE = "sibling-value-active"
#: nothing mechanical applies — the human round owns it
FAMILY_UNTRIAGED = "untriaged"


@dataclass
class InertItem:
    """One (fixture, platform-set) inert verdict nobody has adjudicated."""

    fixture: str
    component: str
    attribute: str
    value: object = None
    #: platforms the fixture is declared for (SSoT scope ∩ compared set)
    scope: list[str] = field(default_factory=list)
    #: ``{platform: "active"|"inert"|None}`` as measured this run
    verdicts: dict[str, str | None] = field(default_factory=dict)
    #: the platforms whose inert verdict is unattributed
    inert_on: list[str] = field(default_factory=list)
    kind: str = KIND_UNIFORM_UNDECLARED
    family: str = FAMILY_UNTRIAGED
    #: what the triage matched on — empty for :data:`FAMILY_UNTRIAGED`
    evidence: str = ""

    def as_dict(self) -> dict:
        return {
            "fixture": self.fixture,
            "component": self.component,
            "attribute": self.attribute,
            "value": self.value,
            "scope": list(self.scope),
            "verdicts": {p: self.verdicts.get(p) for p in self.scope},
            "inertOn": list(self.inert_on),
            "kind": self.kind,
            "family": self.family,
            "evidence": self.evidence,
        }


@dataclass
class InertAudit:
    """The whole inventory for one run."""

    platforms: list[str] = field(default_factory=list)
    #: unadjudicated items, sorted by fixture id
    items: list[InertItem] = field(default_factory=list)
    #: ``{platform: total inert verdicts measured}``
    measured: dict[str, int] = field(default_factory=dict)
    #: ``{platform: {channel: count}}`` — inert verdicts an existing ledger
    #: already accounts for
    attributed: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def unattributed(self) -> dict[str, int]:
        """``{platform: unadjudicated inert verdicts}``."""
        out = {p: 0 for p in self.platforms}
        for item in self.items:
            for p in item.inert_on:
                out[p] = out.get(p, 0) + 1
        return out

    @property
    def untriaged(self) -> list[InertItem]:
        """Items no mechanical family closes — the human adjudication round."""
        return [i for i in self.items if i.family == FAMILY_UNTRIAGED]


# --------------------------------------------------------------------------- #
# Inputs derived from the existing ledgers
# --------------------------------------------------------------------------- #


def coverage_gaps(doc: dict) -> set:
    """``{(component, attribute, platform)}`` from ``coverage.json``.

    A gap already recorded there is a known unimplemented attribute; its
    inert verdict is the expected consequence, and the coverage ledger — not
    a second one — is where it is tracked.
    """
    out = set()
    for entry in (doc or {}).get("entries", []):
        component = entry.get("component")
        attribute = entry.get("attribute")
        if not component or not attribute:
            continue
        for platform in entry.get("platforms") or []:
            out.add((component, attribute, platform))
    return out


def attribute_defaults(definitions: dict) -> dict:
    """``{(component, attribute): default}`` for definitions declaring one."""
    out: dict = {}
    for component, attrs in (definitions or {}).items():
        if not isinstance(attrs, dict):
            continue
        for attribute, defn in attrs.items():
            if isinstance(defn, dict) and "default" in defn:
                out[(component, attribute)] = defn["default"]
    return out


def _strip_generated(doc: dict) -> str:
    """Canonical JSON for a layout, minus the ``@generated`` banner."""
    body = {k: v for k, v in (doc or {}).items() if k != "_generated"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False)


def control_identical_fixtures(conformance_dir, manifest: dict) -> dict:
    """``{fixture_id: control_id}`` for fixtures whose layout IS the control's.

    Some attributes are load-bearing for the host to render at all — an
    ``Image`` without ``src`` shows nothing, so the shared control carries
    it and the ``src`` fixture ends up byte-identical to the control it is
    compared against. The comparison is then structurally incapable of
    reporting anything but inert, whatever the implementation does. Reading
    the layouts is the only way to know; missing or unreadable files are
    skipped rather than raising, so one odd fixture cannot abort an audit.
    """
    conformance_dir = Path(conformance_dir)
    layouts = {
        entry["id"]: entry.get("layout")
        for entry in manifest.get("fixtures", [])
        if entry.get("layout")
    }
    cache: dict = {}

    def body(fixture_id):
        if fixture_id not in cache:
            rel = layouts.get(fixture_id)
            path = conformance_dir / rel if rel else None
            try:
                cache[fixture_id] = _strip_generated(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, TypeError, AttributeError):
                cache[fixture_id] = None
        return cache[fixture_id]

    out: dict = {}
    for entry in manifest.get("fixtures", []):
        control_id = entry.get("control")
        if not control_id or entry.get("isControl"):
            continue
        mine, theirs = body(entry["id"]), body(control_id)
        if mine is not None and mine == theirs:
            out[entry["id"]] = control_id
    return out


# --------------------------------------------------------------------------- #
# Measurement (pure)
# --------------------------------------------------------------------------- #


def audit(
    manifest: dict,
    verdicts: dict,
    platforms,
    *,
    control_diff_ledger: dict | None = None,
    cross_effect_ledger: dict | None = None,
    contract: dict | None = None,
    coverage: set | None = None,
    enum_values: dict | None = None,
) -> InertAudit:
    """Attribute every inert verdict to a ledger, or to the queue. Pure.

    *verdicts* is :func:`cross_effect.verdicts_from_diffs`' map
    (``{platform: {fixture: "active"|"inert"}}``); *control_diff_ledger* is
    :func:`control_diff.load_ledger_all`'s (``{fixture: {platform}}``);
    *cross_effect_ledger* and *contract* are the cross-effect loaders'.
    *coverage* is :func:`coverage_gaps`' set and *enum_values* is
    :func:`cross_effect.enum_fixture_values`' map — omitting either only
    costs attribution precision, never correctness of the queue's membership.

    An item reaches the queue when at least one platform's inert verdict is
    unclaimed; the item then carries the full per-platform picture, because
    adjudicating "android silently drops this" needs to know what the other
    two did.
    """
    compared = list(dict.fromkeys(platforms))
    control_diff_ledger = control_diff_ledger or {}
    cross_effect_ledger = cross_effect_ledger or {}
    contract = contract or {}
    coverage = coverage or set()
    enum_values = enum_values or {}

    result = InertAudit(platforms=compared)
    result.measured = {p: 0 for p in compared}
    result.attributed = {p: {c: 0 for c in CHANNELS} for p in compared}

    for entry in sorted(manifest.get("fixtures", []), key=lambda e: e.get("id") or ""):
        control_id = entry.get("control")
        if not control_id or entry.get("isControl"):
            continue
        fid = entry["id"]
        component = entry.get("component") or ""
        attribute = entry.get("attribute") or ""
        scope = [p for p in compared if p in (entry.get("platforms") or [])]
        if not scope:
            continue

        measured = {p: verdicts.get(p, {}).get(fid) for p in scope}
        unclaimed = []
        for platform in scope:
            if measured[platform] != "inert":
                continue
            result.measured[platform] += 1
            channel = _claim(
                fid,
                component,
                attribute,
                platform,
                control_diff_ledger,
                cross_effect_ledger,
                contract,
                coverage,
            )
            if channel is None:
                unclaimed.append(platform)
            else:
                result.attributed[platform][channel] += 1
        if not unclaimed:
            continue

        result.items.append(
            InertItem(
                fixture=fid,
                component=component,
                attribute=attribute,
                value=entry.get("value"),
                scope=scope,
                verdicts=measured,
                inert_on=unclaimed,
                kind=_kind(fid, scope, measured, enum_values),
            )
        )

    return result


def _claim(
    fid,
    component,
    attribute,
    platform,
    control_diff_ledger,
    cross_effect_ledger,
    contract,
    coverage,
):
    """Which ledger, if any, already accounts for this inert verdict."""
    if platform in (control_diff_ledger.get(fid) or set()):
        # Asserted active here: control_diff already fails this as a
        # regression, and a fixture cannot be both a regression and an
        # unadjudicated inert.
        return CHANNEL_CONTROL_DIFF
    if fid in contract:
        return CHANNEL_CONTRACT
    if fid in cross_effect_ledger:
        return CHANNEL_CROSS_EFFECT
    if (component, attribute, platform) in coverage:
        return CHANNEL_COVERAGE
    return None


def _kind(fid, scope, measured, enum_values):
    """Why this fixture's inert verdict escaped the existing checks."""
    if len(scope) < 2:
        return KIND_SINGLE_PLATFORM
    if any(v is None for v in measured.values()):
        return KIND_NOT_COMPARED
    if all(v == "inert" for v in measured.values()):
        return (
            KIND_UNIFORM_DECLARED if fid in enum_values else KIND_UNIFORM_UNDECLARED
        )
    return KIND_DIVERGENT_SIDE


# --------------------------------------------------------------------------- #
# Phase 1 — mechanical triage
# --------------------------------------------------------------------------- #


def sibling_value_evidence(
    manifest: dict, verdicts: dict, result: InertAudit
) -> dict:
    """``{fixture: {platform: [sibling fixtures active there]}}``. Pure.

    Siblings are the other fixtures testing the SAME (component, attribute) —
    the generator emits one per declared enum value plus the representative
    cases. A sibling that moves pixels on a platform is a live demonstration
    that the platform reads the attribute, which is the one hypothesis a
    screenshot round is expensive to rule out.

    Only recorded when the demonstration holds on EVERY platform where the
    item is unattributed: "android reads it" says nothing about web.
    """
    siblings: dict = {}
    for entry in manifest.get("fixtures", []):
        if not entry.get("control") or entry.get("isControl"):
            continue
        key = (entry.get("component"), entry.get("attribute"))
        siblings.setdefault(key, []).append(entry["id"])

    out: dict = {}
    for item in result.items:
        others = [
            s
            for s in siblings.get((item.component, item.attribute), [])
            if s != item.fixture
        ]
        proof = {}
        for platform in item.inert_on:
            active = [
                s for s in others if verdicts.get(platform, {}).get(s) == "active"
            ]
            if active:
                proof[platform] = sorted(active)
        if proof and set(proof) == set(item.inert_on):
            out[item.fixture] = proof
    return out


def triage(
    result: InertAudit,
    *,
    defaults: dict | None = None,
    control_identical: dict | None = None,
    manifest: dict | None = None,
    fallback_values=(),
    sibling_active: dict | None = None,
) -> InertAudit:
    """Tag queue items the existing canonical data can close. Pure; in place.

    Only families whose evidence is machine-checkable belong here — a family
    that needs somebody to look at two screenshots is a Phase 2 round, and
    labelling it automatically would be the same silent pass this audit
    exists to remove. Returns *result* for chaining.
    """
    defaults = defaults or {}
    control_identical = control_identical or {}
    # ``aliasOf`` already holds the canonical FIXTURE id, not the attribute
    # name — the generator writes the pointer, so no id is reconstructed here.
    alias_of = {
        entry["id"]: entry["aliasOf"]
        for entry in (manifest or {}).get("fixtures", [])
        if entry.get("aliasOf")
    }
    queued = {item.fixture for item in result.items}

    for item in result.items:
        if item.fixture in control_identical:
            item.family = FAMILY_CONTROL_IDENTICAL
            item.evidence = (
                f"layout is identical to its control ({control_identical[item.fixture]}) "
                "— the attribute is load-bearing for the host to render, so the "
                "control carries it and activeness cannot be measured at this shape"
            )
            continue
        default = defaults.get((item.component, item.attribute))
        if default is not None and default == item.value:
            item.family = FAMILY_VALUE_IS_DEFAULT
            item.evidence = (
                f"fixture value equals the SSoT default ({default!r}) — inert is "
                "the definition of a default-valued fixture"
            )
            continue
        if any(item.value == v for v in fallback_values):
            item.family = FAMILY_TYPE_FALLBACK_VALUE
            item.evidence = (
                f"value is the generator's type-level fallback ({item.value!r}), "
                "not a value from the attribute's domain — give the attribute a "
                "representative value in rules.py and re-measure"
            )
            continue
        canonical = alias_of.get(item.fixture)
        if canonical and canonical in queued:
            item.family = FAMILY_ALIAS_OF_QUEUED
            item.evidence = (
                f"alias spelling ({item.fixture.rsplit('__', 1)[-1]}) of the queued "
                f"canonical fixture {canonical} — one adjudication covers both"
            )
            continue
        proof = (sibling_active or {}).get(item.fixture)
        if proof:
            shown = "; ".join(
                f"{p}: {', '.join(proof[p][:2])}" for p in sorted(proof)
            )
            item.family = FAMILY_SIBLING_VALUE_ACTIVE
            item.evidence = (
                f"another declared value of {item.component}.{item.attribute} is "
                f"active on every unattributed platform ({shown}) — the attribute "
                "is read there, so this is a value-level question, not a gap"
            )
            continue
        item.family = FAMILY_UNTRIAGED
        item.evidence = ""
    return result


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def render_queue(result: InertAudit) -> str:
    """Deterministic JSON for the adjudication queue.

    Same treatment as the 33 campaign's first measurement: the file IS the
    worklist, so it carries the counts that justify its own size and every
    item's full per-platform picture.
    """
    doc = {
        "schemaVersion": SCHEMA_VERSION,
        "_comment": (
            "Inert control-diff verdicts no ledger accounts for — the plan-34 "
            "adjudication queue. An entry is NOT a defect: it is a fixture "
            "whose attribute changed no pixels on the listed platforms and "
            "which neither control_diff.json, cross_effect.json, "
            "attribute_semantics.json nor coverage.json has an opinion about. "
            "Adjudicate each one to a fix (the attribute is silently dropped) "
            "or to a reasoned ledger/contract entry (the fixture shape or the "
            "value leaves nothing to observe). This file is generated by `jui "
            "conformance inert-audit --json`; it is a report, not a ledger."
        ),
        "platforms": list(result.platforms),
        "counts": {
            "measuredInert": dict(result.measured),
            "attributed": {p: dict(c) for p, c in result.attributed.items()},
            "unattributed": result.unattributed,
            "queuedFixtures": len(result.items),
            "untriagedFixtures": len(result.untriaged),
        },
        "entries": [item.as_dict() for item in result.items],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
