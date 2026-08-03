"""Cross-platform attribute-effect matching (``jui conformance cross-effect``).

Parity (codegen_parity) mechanized *dynamic ≡ codegen within one platform*.
The remaining unverified claim is **semantic sameness across platforms** —
until now detectable only by a human noticing something adjacent while doing
parity work (``borderWidth`` alone drawing on one platform and not another,
``leftAligned`` diverging between renderers were both accidental finds).

Pixel comparison across platforms is impossible by design, but each
platform's control-diff verdict — *did this attribute change what was
rendered?* — is a platform-independent predicate. So:

    A fixture's activeness must agree across every platform the attribute
    is declared for. ``ios: active / android: inert`` is a drift suspect.

No new screenshots are involved: the input is the per-platform
``control_diff.DiffResult`` every run already computes. This module is set
arithmetic over those verdicts.

Scope rules (what is compared):

- only visual fixtures with a control (the same population control-diff
  compares); skip-classified attributes never become fixtures at all
- a platform outside the fixture's SSoT ``platforms`` declaration is not
  compared (the manifest already encodes that scope)
- a fixture is judged only when it produced a verdict on **all** in-scope
  compared platforms — a missing screenshot or control on any platform
  makes the fixture ``not_compared``, never a silent pass

A second check rides on the same data: **declared-value activeness**. An
enum value the SSoT enumerates that is inert on *every* platform never
diverges, so the agreement check cannot see it — yet "declared but does
nothing anywhere" is exactly what ``layout: leftAligned`` was (uniformly
identical to the default on all three platforms). Such fixtures are flagged
``uniformly-inert``; a legitimate case (the value IS the default, so the
control cannot differ) is accepted on the ledger with that reason.

Divergences live in ``conformance/cross_effect.json``, operated like
``codegen_parity.json``: an entry is an ACCEPTED divergence (a platform
idiom) with a recorded reason, an unrecorded divergence fails, and an entry
the measurement no longer supports is stale and must be pruned. The first
measurement IS the adjudication queue — fix the platform, or justify the
difference. The machine detects disagreement; deciding what "the same"
means stays human work.

Adjudicated rulings graduate out of the ledger into the **semantics
contract** (``shared/core/attribute_semantics.json``, the
``binding_semantics.json`` pattern): the ruling is declared once, its
``observable`` block states the expected cross-platform effect, and this
checker verifies it every run — expected-and-measured is verified,
expected-but-contradicted is a contract violation (a failure no ledger
reason can excuse; changing the semantics means changing the contract).
Contract-covered fixtures need no ledger entry, and one left behind is
stale. Comments in the toolchains point at the contract instead of
restating it — comment canon rots (the border ruling reversed direction
twice in 48 hours while living as comments).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

#: Ledger schema version; bump when the entry shape changes.
SCHEMA_VERSION = 1

LEDGER_NAME = "cross_effect.json"

#: Verdict labels, as recorded in the ledger and printed everywhere.
ACTIVE = "active"
INERT = "inert"

#: Ledger ``verdict`` marking a declared enum value inert on every platform.
UNIFORMLY_INERT = "uniformly-inert"

#: Reason recorded by ``--update`` for entries nobody has reviewed yet.
#: Same marker as codegen_parity so one grep finds the whole backlog.
UNREVIEWED = "unreviewed-initial-measurement"


#: Contract expectation values an ``observable`` block may declare.
UNIFORMLY_ACTIVE = "uniformly-active"
CONTRACT_EXPECTATIONS = (UNIFORMLY_INERT, UNIFORMLY_ACTIVE)

CONTRACT_NAME = "attribute_semantics.json"


def ledger_path(conformance_dir) -> Path:
    return Path(conformance_dir) / LEDGER_NAME


def contract_path(conformance_dir) -> Path:
    """The semantics contract in the repo layout (shared/core beside conformance/)."""
    return Path(conformance_dir).parent / "shared" / "core" / CONTRACT_NAME


def load_contract(path) -> dict:
    """``{fixture_id: expectation}`` from the contract's ``observable`` blocks.

    An expectation is either one of ``CONTRACT_EXPECTATIONS`` or a
    per-platform verdict pattern (``{"ios": "inert", "android": "active",
    ...}``) — the machine memory for an adjudicated EXPECTED difference
    (platform idiom): the divergence must keep exactly that shape, and both
    disappearing and mutating fail the gate. Permissive on unknown values so
    a newer contract does not brick an older checker; the pytest suite is
    where authoring errors get caught loudly.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict = {}
    for entry in (raw.get("semantics") or {}).values():
        if not isinstance(entry, dict):
            continue
        for fid, expected in (entry.get("observable") or {}).items():
            if expected in CONTRACT_EXPECTATIONS:
                out[fid] = expected
            elif isinstance(expected, dict) and expected and all(
                v in (ACTIVE, INERT) for v in expected.values()
            ):
                out[fid] = dict(expected)
    return out


# --------------------------------------------------------------------------- #
# Measurement (pure)
# --------------------------------------------------------------------------- #


@dataclass
class CrossEffectResult:
    """Outcome of one activeness comparison across *platforms*."""

    #: the platform set this comparison spanned
    platforms: list[str] = field(default_factory=list)
    #: fixtures whose verdict agrees on every in-scope platform
    consistent: list[str] = field(default_factory=list)
    #: ``{fixture: agreed verdict}`` for the consistent fixtures — what the
    #: contract expectations are judged against
    agreed_verdicts: dict[str, str] = field(default_factory=dict)
    #: ``{fixture: {platform: "active"|"inert"}}`` — the drift suspects
    mismatched: dict[str, dict[str, str]] = field(default_factory=dict)
    #: ``{fixture: declared enum value}`` — consistent, but inert everywhere
    #: despite testing a value the SSoT enumerates (the leftAligned class)
    uniform_inert: dict[str, object] = field(default_factory=dict)
    #: fixtures in scope on ≥2 platforms but lacking a verdict on at least
    #: one of them (no screenshot / no control / platform not measured).
    #: Not compared — never a pass.
    not_compared: list[str] = field(default_factory=list)
    #: visual fixtures declared for <2 of the compared platforms — there is
    #: nothing to cross-compare
    out_of_scope: int = 0


def scope_from_manifest(manifest: dict) -> dict[str, list[str]]:
    """``{fixture_id: declared platforms}`` for every control-bearing fixture.

    The same population :func:`control_diff.compare` iterates: visual
    fixtures with a control, controls themselves excluded. Skip-classified
    attributes never reach the manifest's fixture list, so their exclusion
    is inherited rather than re-implemented.
    """
    out: dict[str, list[str]] = {}
    for entry in manifest.get("fixtures", []):
        if not entry.get("control") or entry.get("isControl"):
            continue
        out[entry["id"]] = list(entry.get("platforms") or [])
    return out


def enum_fixture_values(manifest: dict, definitions: dict) -> dict[str, object]:
    """``{fixture_id: declared value}`` for fixtures testing an SSoT enum value.

    The manifest does not mark enum-ness, but it carries the tested ``value``
    and the definitions carry each attribute's declared enum values — a
    fixture whose value appears there is a declared-value probe. Only these
    participate in the uniformly-inert check: a representative number or
    colour that happens to equal the platform default is control-diff's
    documented benign case, but a *declared* value that does nothing on any
    platform is either the default (ledger it with that reason) or dead.
    """
    from .rules import normalize_type  # noqa: PLC0415 — avoid import cycle at module load

    out: dict[str, object] = {}
    for entry in manifest.get("fixtures", []):
        if not entry.get("control") or entry.get("isControl"):
            continue
        component = entry.get("component") or ""
        attribute = entry.get("attribute") or ""
        defn = (definitions.get(component) or {}).get(attribute)
        if not isinstance(defn, dict):
            continue
        _, enum_values = normalize_type(defn)
        value = entry.get("value")
        if value is not None and value in enum_values:
            out[entry["id"]] = value
    return out


def verdicts_from_diffs(diffs: dict) -> dict[str, dict[str, str]]:
    """``{platform: {fixture_id: "active"|"inert"}}`` from DiffResults.

    A platform whose comparison errored contributes no verdicts — every
    fixture becomes ``not_compared`` there rather than silently agreeing.
    """
    out: dict[str, dict[str, str]] = {}
    for platform, d in (diffs or {}).items():
        if d is None or d.error:
            continue
        verdicts: dict[str, str] = {}
        for fid in d.active:
            verdicts[str(fid)] = ACTIVE
        for fid, _changed in d.inert:
            verdicts[str(fid)] = INERT
        out[platform] = verdicts
    return out


def measure(
    scope: dict[str, list[str]],
    verdicts: dict[str, dict[str, str]],
    platforms: Sequence[str],
    enum_values: dict[str, object] | None = None,
) -> CrossEffectResult:
    """Compare activeness across *platforms*. Pure — no filesystem.

    *scope* is :func:`scope_from_manifest`'s map, *verdicts* is
    :func:`verdicts_from_diffs`'s, *enum_values* is
    :func:`enum_fixture_values`'s (omit it and the uniformly-inert check is
    off). Platforms outside a fixture's declared scope are excluded before
    the all-compared rule is applied.
    """
    compared_platforms = list(dict.fromkeys(platforms))
    enum_values = enum_values or {}
    result = CrossEffectResult(platforms=compared_platforms)

    for fid in sorted(scope):
        in_scope = [p for p in compared_platforms if p in scope[fid]]
        if len(in_scope) < 2:
            result.out_of_scope += 1
            continue
        fixture_verdicts = {p: verdicts.get(p, {}).get(fid) for p in in_scope}
        if any(v is None for v in fixture_verdicts.values()):
            result.not_compared.append(fid)
            continue
        agreed = set(fixture_verdicts.values())
        if len(agreed) == 1:
            result.consistent.append(fid)
            result.agreed_verdicts[fid] = next(iter(agreed))
            if agreed == {INERT} and fid in enum_values:
                result.uniform_inert[fid] = enum_values[fid]
        else:
            result.mismatched[fid] = dict(fixture_verdicts)

    return result


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


def load_ledger(path) -> dict[str, dict]:
    """``{fixture_id: entry}`` for the whole ledger."""
    path = Path(path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for entry in raw.get("entries", []):
        fixture = entry.get("fixture")
        if fixture:
            out[fixture] = entry
    return out


def _render_entry(fid: str, entry: dict) -> dict:
    """One ledger entry in its canonical key order (divergence or uniform)."""
    if entry.get("verdict") == UNIFORMLY_INERT:
        return {
            "fixture": fid,
            "verdict": UNIFORMLY_INERT,
            "declared": entry.get("declared"),
            "reason": entry.get("reason", UNREVIEWED),
            "note": entry.get("note", ""),
        }
    return {
        "fixture": fid,
        "platforms": {
            p: entry.get("platforms", {})[p]
            for p in sorted(entry.get("platforms", {}))
        },
        "reason": entry.get("reason", UNREVIEWED),
        "note": entry.get("note", ""),
    }


def render_ledger(entries: dict[str, dict]) -> str:
    """Deterministic ledger JSON for ``{fixture_id: entry}``."""
    doc = {
        "schemaVersion": SCHEMA_VERSION,
        "_comment": (
            "Accepted cross-platform attribute-effect findings, two kinds. "
            "DIVERGENCE ({fixture, platforms}): the control-diff verdict "
            "(active = the attribute changed the render, inert = it did not) "
            "disagrees across the platforms the attribute is declared for — "
            "semantic drift unless a deliberate platform idiom; the reason "
            "says which. UNIFORMLY-INERT ({fixture, verdict, declared}): a "
            "value the SSoT enumerates changes nothing on ANY platform — "
            "either it is the default rendering (say so in the reason) or it "
            "is dead/unimplemented everywhere. Unrecorded findings fail `jui "
            "conformance gate --cross-effect`; entries the measurement no "
            "longer supports are stale and must be pruned (`jui conformance "
            "cross-effect --update`). Reason '" + UNREVIEWED + "' marks the "
            "initial-measurement backlog — consume it."
        ),
        "entries": [_render_entry(fid, entries[fid]) for fid in sorted(entries)],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def update_ledger(
    existing: dict[str, dict],
    result: CrossEffectResult,
    contract: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Fold one measurement into the ledger entries.

    Measured findings replace their fixtures' entries — an entry whose
    recorded fact still matches (same divergence pattern, or same declared
    value for a uniformly-inert entry) keeps its reason and note; a changed
    fact returns to the unreviewed backlog. Fixtures the measurement no
    longer flags drop off the ledger. Fixtures the run could not compare
    keep their entries untouched: an unverified assertion is not a resolved
    one.

    Contract-covered fixtures are never written (and existing entries are
    dropped): a violation of declared semantics cannot be accepted with a
    ledger reason — either fix the platform or change the contract.
    """
    covered = set(contract or {})
    compared = set(result.consistent) | set(result.mismatched)
    merged = {
        fid: entry
        for fid, entry in existing.items()
        if fid not in compared and fid not in covered
    }
    for fid, verdicts in result.mismatched.items():
        if fid in covered:
            continue
        prior = existing.get(fid, {})
        fact_holds = prior.get("platforms") == verdicts
        merged[fid] = {
            "fixture": fid,
            "platforms": dict(verdicts),
            "reason": prior.get("reason", UNREVIEWED) if fact_holds else UNREVIEWED,
            "note": prior.get("note", "") if fact_holds else "",
        }
    for fid, declared in result.uniform_inert.items():
        if fid in covered:
            continue
        prior = existing.get(fid, {})
        fact_holds = (
            prior.get("verdict") == UNIFORMLY_INERT and prior.get("declared") == declared
        )
        merged[fid] = {
            "fixture": fid,
            "verdict": UNIFORMLY_INERT,
            "declared": declared,
            "reason": prior.get("reason", UNREVIEWED) if fact_holds else UNREVIEWED,
            "note": prior.get("note", "") if fact_holds else "",
        }
    return merged


# --------------------------------------------------------------------------- #
# Judgment (pure — consumed by the gate and the standalone command)
# --------------------------------------------------------------------------- #


@dataclass
class CrossEffectCheck:
    """Ledger-vs-measurement verdict, both ratchet directions."""

    #: measured findings with no (or a no-longer-matching) ledger entry
    unrecorded: list[str] = field(default_factory=list)
    #: ledger entries the measurement no longer supports — the fixture is
    #: clean, or the recorded fact changed shape — prune them
    stale: list[str] = field(default_factory=list)
    #: ledger entries whose fixture this run could not compare (notice)
    unverified: list[str] = field(default_factory=list)
    #: measured findings covered by a matching ledger entry
    accepted: int = 0
    #: contract expectations the measurement contradicts — failures no
    #: ledger reason can excuse (changing the semantics means changing the
    #: contract, not accepting the violation)
    contract_violations: list[str] = field(default_factory=list)
    #: contract expectations measured and holding
    contract_verified: int = 0
    #: contract expectations the run could not compare (notice)
    contract_unverified: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unrecorded and not self.stale and not self.contract_violations


def _format_verdicts(verdicts: dict[str, str]) -> str:
    return ", ".join(f"{p}: {verdicts[p]}" for p in sorted(verdicts))


def check(
    result: CrossEffectResult,
    ledger: dict[str, dict],
    contract: dict[str, str] | None = None,
) -> CrossEffectCheck:
    """Judge one measurement against the ledger and the semantics contract. Pure.

    An entry is accepted only while it records the measured fact: a
    divergence entry whose pattern changed, or a uniformly-inert entry whose
    fixture now diverges (and vice versa), justified something else — the
    finding is unrecorded again and the obsolete entry is stale.

    A contract-covered fixture is judged against the declared semantics
    instead of the ledger: measurement holding the expectation is verified,
    contradicting it is a violation, and a ledger entry left behind for a
    covered fixture is stale (the contract is now the record).
    """
    contract = contract or {}
    covered = set(contract)
    verdict = CrossEffectCheck()

    for fid, expected in sorted(contract.items()):
        if isinstance(expected, dict):
            # Expected difference (adjudicated platform idiom): the
            # divergence must keep exactly this shape — disappearing OR
            # mutating is a contract violation.
            if fid in result.mismatched:
                if result.mismatched[fid] == expected:
                    verdict.contract_verified += 1
                else:
                    verdict.contract_violations.append(
                        f"{fid}: contract expects the divergence "
                        f"({_format_verdicts(expected)}), measured "
                        f"({_format_verdicts(result.mismatched[fid])})"
                    )
            elif fid in result.agreed_verdicts:
                verdict.contract_violations.append(
                    f"{fid}: contract expects the divergence "
                    f"({_format_verdicts(expected)}), measured uniformly "
                    f"{result.agreed_verdicts[fid]}"
                )
            else:
                verdict.contract_unverified.append(fid)
            continue
        if fid in result.mismatched:
            verdict.contract_violations.append(
                f"{fid}: contract expects {expected}, measured diverging "
                f"({_format_verdicts(result.mismatched[fid])})"
            )
        elif fid in result.agreed_verdicts:
            wanted = INERT if expected == UNIFORMLY_INERT else ACTIVE
            agreed = result.agreed_verdicts[fid]
            if agreed == wanted:
                verdict.contract_verified += 1
            else:
                verdict.contract_violations.append(
                    f"{fid}: contract expects {expected}, measured uniformly {agreed}"
                )
        else:
            verdict.contract_unverified.append(fid)

    for fid, verdicts in sorted(result.mismatched.items()):
        if fid in covered:
            continue  # judged as a contract violation above
        entry = ledger.get(fid)
        if entry is not None and entry.get("platforms") == verdicts:
            verdict.accepted += 1
        elif entry is not None:
            recorded = (
                _format_verdicts(entry.get("platforms") or {})
                if entry.get("verdict") != UNIFORMLY_INERT
                else UNIFORMLY_INERT
            )
            verdict.unrecorded.append(
                f"{fid} ({_format_verdicts(verdicts)}) — recorded fact differs: "
                f"{recorded}"
            )
        else:
            verdict.unrecorded.append(f"{fid} ({_format_verdicts(verdicts)})")

    for fid, declared in sorted(result.uniform_inert.items()):
        if fid in covered:
            continue  # the contract is the record for this fixture
        entry = ledger.get(fid)
        if (
            entry is not None
            and entry.get("verdict") == UNIFORMLY_INERT
            and entry.get("declared") == declared
        ):
            verdict.accepted += 1
        else:
            verdict.unrecorded.append(
                f"{fid} ({UNIFORMLY_INERT}: declared value {declared!r} changes "
                "nothing on any platform)"
            )

    compared = set(result.consistent) | set(result.mismatched)
    for fid in sorted(ledger):
        entry = ledger[fid]
        if fid in covered:
            # Redundant regardless of what this run measured — the contract
            # supersedes the ledger for this fixture.
            verdict.stale.append(fid)
            continue
        if fid not in compared:
            verdict.unverified.append(fid)
            continue
        if entry.get("verdict") == UNIFORMLY_INERT:
            fact_holds = (
                fid in result.uniform_inert
                and result.uniform_inert[fid] == entry.get("declared")
            )
        else:
            fact_holds = result.mismatched.get(fid) == entry.get("platforms")
        if not fact_holds:
            verdict.stale.append(fid)

    return verdict
