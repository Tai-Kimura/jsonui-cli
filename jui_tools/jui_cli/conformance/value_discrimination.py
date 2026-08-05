"""Do an attribute's declared VALUES draw differently from each other?

Every other check in this package asks a fixture how it compares to its
control, or to another platform, or to the codegen's render of itself. None
of them asks whether two declared values of the same attribute produce
different pictures — and an attribute that reads its input, reacts to it,
and then maps every value onto the same layout passes all of them.

`distribution` was found that way, by hand: `fillEqually` and
`equalCentering` draw the same thing on android and web, `equalSpacing` and
`equalCentering` on iOS. Both members of each pair differ from the control,
so the inert check is satisfied; both pipelines collapse them the same way,
so parity is satisfied; all three platforms agree they are active, so the
cross-platform check is satisfied. The SSoT declares four values and the
suite proves three of them.

What counts as two values, and what does not:

  * an ALIAS case is the same value spelled another way, and is supposed to
    render identically — comparing it here would report the alias working
  * a BOUND case is the same value written as `@{...}`, seeded with the
    literal it mirrors, and is likewise supposed to match
  * two enum values that differ only in case are one value: `AttrEnum`
    matches case-insensitively, and `contentMode` lists `bottom` and
    `Bottom` as separate entries for authors who write either
  * a pair the SSoT itself calls the same, through `valueAliases`

The first two come off facts the manifest already carries (`aliasOf`, and a
`value` that is a binding expression), not off a name convention. The last
two come from the SSoT, which is the thing that decides what counts as two
values in the first place — this module must not hold a second opinion
about that.

What is deliberately NOT excluded: `contentMode`'s `fill` and `ScaleToFill`
draw identically on all three platforms and the SSoT declares them as two
separate enum entries with no `valueAliases` between them. Either the
declaration should say they are the same, or they should draw differently.
Reporting it is the point.

Screenshots are compared through `control_diff.diff_pixels` with the same
ignore bands, because the android CI status bar has a clock in it and two
captures of a pair are seconds apart. Without the bands every pair on that
platform reads as "different", which is the failure this module exists to
detect, inverted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from .baseline import DEFAULT_ENV
from .control_diff import DEFAULT_MIN_PIXELS, diff_pixels, ignore_bands

LEDGER_NAME = "value_discrimination.json"

SCHEMA_VERSION = 1

#: Reason recorded by ``--update`` for pairs nobody has reviewed yet.
UNREVIEWED = "unreviewed-initial-measurement"

#: Fields every accepted collapse must carry. An accepted defect with no
#: owner is a permanent one (plan 50).
REQUIRED_FIELDS = ("owner", "reason")


def ledger_path(conformance_dir) -> Path:
    return Path(conformance_dir) / LEDGER_NAME


def is_binding(value) -> bool:
    return isinstance(value, str) and value.startswith("@{")


def same_declared_value(value_a, value_b, aliases: dict) -> bool:
    """Do the SSoT and the enum machinery treat these as one value?"""
    if json.dumps(value_a, sort_keys=True) == json.dumps(value_b, sort_keys=True):
        return True
    if isinstance(value_a, str) and isinstance(value_b, str):
        if value_a.lower() == value_b.lower():
            return True
        # valueAliases maps alias -> canonical; either direction, or both
        # pointing at the same canonical, means one value.
        canon_a = aliases.get(value_a, value_a)
        canon_b = aliases.get(value_b, value_b)
        if canon_a.lower() == canon_b.lower():
            return True
    return False


def value_aliases_for(definitions: dict, component: str, attribute: str) -> dict:
    """`{alias: canonical}` the SSoT declares for this attribute."""
    section = definitions.get(component) or {}
    defn = section.get(attribute) if isinstance(section, dict) else None
    if not isinstance(defn, dict):
        defn = (definitions.get("common") or {}).get(attribute)
    if isinstance(defn, dict) and isinstance(defn.get("valueAliases"), dict):
        return defn["valueAliases"]
    return {}


@dataclass
class Pair:
    """Two value cases of one attribute, and how far apart they drew."""

    component: str
    attribute: str
    platform: str
    case_a: str
    case_b: str
    value_a: object = None
    value_b: object = None
    pixels: int = 0

    @property
    def key(self) -> tuple:
        # Case names, not values: a value can be a dict, and the case name is
        # what the fixture id is built from, so this keys the same way the
        # rest of the suite names things.
        return (self.component, self.attribute, self.platform,
                *sorted((self.case_a, self.case_b)))

    def __str__(self) -> str:
        return (
            f"{self.component}.{self.attribute} [{self.platform}] "
            f"{self.case_a} ≡ {self.case_b} — {self.value_a!r} and {self.value_b!r} "
            f"draw the same picture"
        )


@dataclass
class DiscriminationResult:
    platform: str
    #: (component, attribute) groups that had two or more distinct values
    groups: int = 0
    #: pairs actually compared
    compared: int = 0
    #: pairs whose two values drew the same picture
    collapsed: list = field(default_factory=list)
    #: pairs skipped because a screenshot was missing
    unmeasured: list = field(default_factory=list)
    #: excluded before comparing, by reason — reported so the narrowing is
    #: visible rather than implied
    excluded: dict = field(default_factory=dict)


def value_groups(manifest: dict, platform: str) -> dict:
    """`{(component, attribute): [fixture, …]}` for distinct declared values."""
    groups: dict = {}
    excluded = {"alias": 0, "binding": 0}
    for entry in manifest.get("fixtures", []):
        if entry.get("isControl") or entry.get("class") != "visual":
            continue
        if platform not in (entry.get("platforms") or []):
            continue
        if entry.get("aliasOf"):
            excluded["alias"] += 1
            continue
        if is_binding(entry.get("value")):
            excluded["binding"] += 1
            continue
        key = (entry.get("component"), entry.get("attribute"))
        groups.setdefault(key, []).append(entry)

    out = {}
    for key, entries in groups.items():
        seen = {json.dumps(e.get("value"), sort_keys=True) for e in entries}
        if len(seen) > 1:
            out[key] = entries
    return out, excluded


def measure(
    conformance_dir,
    platform: str,
    manifest: dict,
    results: dict,
    artifacts_dir=None,
    min_pixels: int = DEFAULT_MIN_PIXELS,
    env: str = DEFAULT_ENV,
    definitions: dict | None = None,
    active: set | None = None,
) -> DiscriminationResult:
    """Compare every pair of distinct declared values, per attribute."""
    conformance_dir = Path(conformance_dir)
    if artifacts_dir is None:
        artifacts_dir = conformance_dir / "artifacts" / platform
    artifacts_dir = Path(artifacts_dir)

    result = DiscriminationResult(platform=platform)
    top, bottom = ignore_bands(platform, env)

    shots = {}
    for fid, entry in (results or {}).items():
        if isinstance(entry, dict) and isinstance(entry.get("screenshot"), str):
            shots[str(fid)] = Path(entry["screenshot"]).name

    groups, excluded = value_groups(manifest, platform)
    result.groups = len(groups)
    result.excluded = excluded

    for (component, attribute), entries in sorted(groups.items()):
        aliases = value_aliases_for(definitions or {}, component, attribute)
        for a, b in combinations(sorted(entries, key=lambda e: e["id"]), 2):
            if same_declared_value(a.get("value"), b.get("value"), aliases):
                result.excluded["same-value"] = (
                    result.excluded.get("same-value", 0) + 1
                )
                continue
            # Only pairs where BOTH values do something. If either is inert
            # against its control the attribute is not discriminating at all,
            # which --inert-complete already owns; reporting it here would
            # bury the case only this check can see under the case another
            # check already has.
            if active is not None and not (a["id"] in active and b["id"] in active):
                result.excluded["not-both-active"] = (
                    result.excluded.get("not-both-active", 0) + 1
                )
                continue
            shot_a, shot_b = shots.get(a["id"]), shots.get(b["id"])
            if not (shot_a and shot_b):
                result.unmeasured.append(f"{a['id']} / {b['id']}")
                continue
            png_a, png_b = artifacts_dir / shot_a, artifacts_dir / shot_b
            if not (png_a.is_file() and png_b.is_file()):
                result.unmeasured.append(f"{a['id']} / {b['id']}")
                continue
            pixels = diff_pixels(png_a, png_b, ignore_bottom=bottom, ignore_top=top)
            result.compared += 1
            if pixels <= min_pixels:
                result.collapsed.append(
                    Pair(
                        component=component,
                        attribute=attribute,
                        platform=platform,
                        case_a=a.get("case"),
                        case_b=b.get("case"),
                        value_a=a.get("value"),
                        value_b=b.get("value"),
                        pixels=pixels,
                    )
                )
    return result


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


def load_ledger(path) -> dict:
    path = Path(path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for entry in raw.get("entries", []):
        cases = entry.get("cases") or []
        key = (
            entry.get("component"),
            entry.get("attribute"),
            entry.get("platform"),
            *sorted(cases),
        )
        if all(key):
            out[key] = entry
    return out


def render_ledger(entries: dict) -> str:
    doc = {
        "schemaVersion": SCHEMA_VERSION,
        "_comment": (
            "Accepted value collapses: two declared values of one attribute that "
            "draw the same picture on a platform. An entry means the collapse is "
            "known and accepted FOR A STATED REASON — not that the values are "
            "equivalent. Unrecorded collapses fail `jui conformance gate "
            "--value-discrimination`; entries the measurement no longer supports "
            "are stale and fail too, so making a value discriminate again forces "
            "its row out. Alias cases and bound cases are never compared: both "
            "are the same value in another spelling and are supposed to match."
        ),
        "entries": [entries[k] for k in sorted(entries)],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def update_ledger(existing: dict, result: DiscriminationResult) -> dict:
    merged = {k: v for k, v in existing.items() if k[2] != result.platform}
    for pair in result.collapsed:
        prior = existing.get(pair.key, {})
        merged[pair.key] = {
            "component": pair.component,
            "attribute": pair.attribute,
            "platform": pair.platform,
            "cases": sorted((pair.case_a, pair.case_b)),
            "owner": prior.get("owner", UNREVIEWED),
            "reason": prior.get("reason", UNREVIEWED),
            "note": prior.get("note", ""),
        }
    return merged


@dataclass
class DiscriminationCheck:
    platform: str
    unrecorded: list = field(default_factory=list)
    stale: list = field(default_factory=list)
    incomplete: list = field(default_factory=list)
    accepted: int = 0

    @property
    def ok(self) -> bool:
        return not (self.unrecorded or self.stale or self.incomplete)


def check(result: DiscriminationResult, ledger: dict) -> DiscriminationCheck:
    verdict = DiscriminationCheck(platform=result.platform)
    measured = {p.key for p in result.collapsed}

    for pair in result.collapsed:
        entry = ledger.get(pair.key)
        if entry is None:
            verdict.unrecorded.append(str(pair))
            continue
        missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
        if missing:
            verdict.incomplete.append(
                f"{pair.component}.{pair.attribute} [{pair.platform}] — "
                f"missing {', '.join(missing)}"
            )
        else:
            verdict.accepted += 1

    for key in sorted(ledger):
        if key[2] == result.platform and key not in measured:
            verdict.stale.append(
                f"{key[0]}.{key[1]} [{key[2]}] {' / '.join(key[3:])}"
            )
    return verdict
