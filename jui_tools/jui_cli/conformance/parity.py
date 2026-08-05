"""dynamic ≡ codegen parity (``jui conformance parity`` / ``gate --parity``).

The conformance suite renders every fixture through each platform's
**dynamic** pipeline; production apps ship the **generated** code. Nothing
in CI ever said those two agree — the invariant lived in maintainer working
memory, and the same semantic bug got fixed twice (once per pipeline) four
times in a row (grid spacing, Collection defaults, enabled, .disabled
order). This module makes the invariant mechanical.

No second truth is minted: the codegen host's screenshots are compared
against **this run's own dynamic renders** (``artifacts/<platform>``),
hashed with the same dhash-64 and judged against the baseline's calibrated
threshold. A fixture whose two renders agree within that threshold is
proof — for that fixture, on that platform, in that render environment —
that dynamic and codegen draw the same thing.

Comparing against the committed baseline instead was the first shape, and
it measured the wrong quantity: codegen-now against dynamic-as-of-the-bake,
which is the invariant PLUS however far the baseline has drifted. Measured
both ways over one iOS run: with a baseline faithful to that run the two
agree exactly (44 deviations either way); with a baseline from another
environment the baseline route reports 510. The stale half was all phantom.
Worse, the loop ran over the baseline's key space, so a fixture with no
baseline entry was never compared at all — 168 of 662 codegen renders in
the run that found this, and the bound fixtures this wave added were most
of them.

Same-run comparison also drops the environment coupling: both sides come
out of one renderer in one run, so a local measurement means something,
which the baseline route could never offer (a local baseline says nothing
about the CI renderer's). The baseline remains the fallback for when a run
has no dynamic artifacts to compare against.

Drift of the dynamic renders themselves is deliberately NOT this gate's
job — that is the visual check against the baseline. One gate, one
invariant; folding both in here is what made the deviations unreadable.

Deviations live in ``conformance/codegen_parity.json``, operated like
``coverage.json``: an entry is an ACCEPTED deviation with a recorded
reason, anything measured-but-unrecorded fails the gate, and an entry the
measurement no longer supports is stale and must be pruned. The initial
measurement IS the drift ledger the ecosystem was missing; consuming it —
fix the codegen, or justify the difference — is the ongoing work the gate
keeps honest.

Keys are **screenshot names** (the baseline manifest's own key space), so
the ledger needs no runner-naming knowledge; entries carry the platform.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .baseline import (
    DEFAULT_ENV,
    BaselineError,
    chrome_crop,
    dhash_file,
    hamming,
    load_baseline,
)

#: Ledger schema version; bump when the entry shape changes.
SCHEMA_VERSION = 1

LEDGER_NAME = "codegen_parity.json"

#: Platforms with a codegen host distinct from their dynamic host. Web is
#: deliberately absent: its conformance host already renders through the
#: rjui codegen (conformance/hosts/web/generate.mjs), so its baseline IS
#: the generated pipeline and parity would compare a pipeline to itself.
PARITY_PLATFORMS = ("ios", "android")

#: Reason recorded by ``--update`` for entries nobody has reviewed yet.
#: The gate treats it as accepted (it IS recorded), but the string marks
#: the consumption backlog grep-ably.
UNREVIEWED = "unreviewed-initial-measurement"

#: Codegen artifacts default directory pattern, relative to conformance/.
def artifacts_dir(conformance_dir: Path, platform: str) -> Path:
    return Path(conformance_dir) / "artifacts" / f"{platform}-codegen"


def dynamic_artifacts_dir(conformance_dir: Path, platform: str) -> Path:
    """This run's dynamic renders — the other half of the comparison."""
    return Path(conformance_dir) / "artifacts" / platform


def ledger_path(conformance_dir: Path) -> Path:
    return Path(conformance_dir) / LEDGER_NAME


@dataclass
class ParityResult:
    """Outcome of one platform's codegen-vs-dynamic-baseline measurement."""

    platform: str
    env: str = DEFAULT_ENV
    threshold: int = 0
    #: what the codegen renders were compared against: "dynamic" (this run's
    #: own renders — the real invariant) or "baseline" (the fallback).
    source: str = "dynamic"
    #: names compared and within threshold — dynamic ≡ codegen holds
    matched: list = field(default_factory=list)
    #: (name, distance) beyond threshold — the codegen draws something else
    mismatched: list = field(default_factory=list)
    #: rendered by dynamic, absent from the codegen host (generation failed,
    #: compile skip, not captured)
    missing: list = field(default_factory=list)
    #: rendered by the codegen host, absent from dynamic. Kept apart from
    #: `missing` because the two have opposite causes, and out of the
    #: deviation count entirely: neither is "the two pipelines draw
    #: different things", it is "only one pipeline drew it".
    codegen_only: list = field(default_factory=list)
    #: baseline names neither side produced — rename/deletion residue. Purely
    #: informational: it says something about the baseline's age, nothing
    #: about either pipeline, and folding it into the deviation count is what
    #: made a run report 104 "codegen defects" of which 78 were phantom.
    baseline_only: list = field(default_factory=list)
    error: str | None = None  # nothing was measured (no baseline / Pillow …)


def measure(
    conformance_dir: Path,
    platform: str,
    env: str = DEFAULT_ENV,
    codegen_dir: Path | None = None,
    dynamic_dir: Path | None = None,
) -> ParityResult:
    """Compare this run's codegen screenshots against its dynamic ones.

    Comparison is name-wise over the INTERSECTION of the two render sets,
    so a fixture is compared the day it is added — the old loop ran over
    the baseline's key space and silently skipped anything the baseline
    predated.

    Falls back to the committed baseline when the run has no dynamic
    artifacts (a codegen-only job). That path measures the invariant plus
    the baseline's drift, so it is a fallback and says so in `source`.
    """
    conformance_dir = Path(conformance_dir)
    if codegen_dir is None:
        codegen_dir = artifacts_dir(conformance_dir, platform)
    codegen_dir = Path(codegen_dir)

    result = ParityResult(platform=platform, env=env)

    if dynamic_dir is None:
        dynamic_dir = dynamic_artifacts_dir(conformance_dir, platform)
    dynamic_dir = Path(dynamic_dir)

    # The threshold is calibrated per env and lives with the baseline, so it
    # is read even when the baseline is not the comparison target.
    baseline = load_baseline(conformance_dir, platform, env)
    if baseline is None:
        result.error = (
            f"no dynamic baseline for env '{env}' / {platform} — parity needs its "
            f"calibrated threshold from baselines/{env}/{platform}.hashes.json; "
            f"bake it first"
        )
        return result
    if not codegen_dir.is_dir():
        result.error = (
            f"codegen artifacts directory not found: {codegen_dir} — run the "
            f"{platform} codegen host first"
        )
        return result

    result.threshold = int(baseline.get("threshold", 0))
    hashes: dict = baseline.get("hashes", {})
    # Both sides are hashed with this lane's chrome crop; mixing crops would
    # read as a deviation on every fixture.
    crop = chrome_crop(platform, env)
    codegen = {png.name: png for png in sorted(codegen_dir.glob("*.png"))}

    dynamic = {}
    if dynamic_dir.is_dir():
        dynamic = {png.name: png for png in sorted(dynamic_dir.glob("*.png"))}
    if not dynamic:
        result.source = "baseline"

    try:
        if result.source == "dynamic":
            for name in sorted(set(codegen) & set(dynamic)):
                distance = hamming(
                    dhash_file(codegen[name], crop), dhash_file(dynamic[name], crop)
                )
                if distance <= result.threshold:
                    result.matched.append(name)
                else:
                    result.mismatched.append((name, distance))
            result.missing = sorted(set(dynamic) - set(codegen))
            result.codegen_only = sorted(set(codegen) - set(dynamic))
            result.baseline_only = sorted(
                set(hashes) - set(dynamic) - set(codegen)
            )
        else:
            for name in sorted(set(codegen) & set(hashes)):
                distance = hamming(dhash_file(codegen[name], crop), hashes[name])
                if distance <= result.threshold:
                    result.matched.append(name)
                else:
                    result.mismatched.append((name, distance))
            result.missing = sorted(set(hashes) - set(codegen))
            result.codegen_only = sorted(set(codegen) - set(hashes))
    except BaselineError as exc:
        result.error = str(exc)
        return result

    return result


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


def load_ledger(path: Path) -> dict:
    """``{(name, platform, env): entry}`` for the whole ledger.

    Entries carry their render environment: a deviation measured against
    the local baselines says nothing about the CI renderer's, and vice
    versa. Entries written before the env field default to ``local``.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict = {}
    for entry in raw.get("entries", []):
        name = entry.get("screenshot")
        platform = entry.get("platform")
        env = entry.get("env", DEFAULT_ENV)
        if name and platform:
            entry.setdefault("env", env)
            out[(name, platform, env)] = entry
    return out


def render_ledger(entries: dict) -> str:
    """Deterministic ledger JSON for ``{(name, platform): entry}``."""
    doc = {
        "schemaVersion": SCHEMA_VERSION,
        "_comment": (
            "Accepted dynamic≢codegen deviations, per screenshot, platform and "
            "render environment (a deviation measured against the local "
            "baselines says nothing about the CI renderer's). "
            "The codegen host's render of this screenshot does NOT match the "
            "committed dynamic baseline (status 'mismatch', with the measured "
            "distance) or was never produced (status 'missing'). Every entry "
            "needs a reason: fix the codegen and drop the entry, or justify "
            "the difference here. Unrecorded deviations fail `jui conformance "
            "gate --parity`; entries the measurement no longer supports are "
            "stale and must be pruned (re-run `jui conformance parity "
            "--update`). Reason '" + UNREVIEWED + "' marks the "
            "initial-measurement backlog — consume it."
        ),
        "entries": [
            entries[key]
            for key in sorted(entries, key=lambda k: (k[2], k[1], k[0]))
        ],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def update_ledger(existing: dict, result: ParityResult) -> dict:
    """Fold one platform's measurement into the ledger entries.

    Same platform: measured deviations replace that platform's entries
    (reasons/notes of surviving entries are preserved); clean measurements
    drop stale entries. Other platforms are untouched — an ios measurement
    says nothing about android.
    """
    merged = {
        key: entry
        for key, entry in existing.items()
        if not (key[1] == result.platform and key[2] == result.env)
    }
    for name, distance in result.mismatched:
        key = (name, result.platform, result.env)
        prior = existing.get(key, {})
        merged[key] = {
            "screenshot": name,
            "platform": result.platform,
            "env": result.env,
            "status": "mismatch",
            "distance": distance,
            "reason": prior.get("reason", UNREVIEWED),
            "note": prior.get("note", ""),
        }
    one_sided = [(name, "missing") for name in result.missing]
    one_sided += [(name, "codegen-only") for name in result.codegen_only]
    for name, status in one_sided:
        key = (name, result.platform, result.env)
        prior = existing.get(key, {})
        merged[key] = {
            "screenshot": name,
            "platform": result.platform,
            "env": result.env,
            "status": status,
            "reason": prior.get("reason", UNREVIEWED),
            "note": prior.get("note", ""),
        }
    return merged


@dataclass
class ParityCheck:
    """Pure ledger-vs-measurement verdict (consumed by the gate)."""

    platform: str
    unrecorded: list = field(default_factory=list)  # deviations not in ledger
    stale: list = field(default_factory=list)  # ledger entries now clean
    accepted: int = 0  # deviations covered by ledger entries
    #: names only one pipeline produced, not on the ledger. Reported apart
    #: from `unrecorded` because "only one side drew it" and "the two sides
    #: drew different things" need different fixes, and merging them makes
    #: the deviation count a number nobody can act on.
    one_sided: list = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return (
            not self.unrecorded
            and not self.stale
            and not self.one_sided
            and self.error is None
        )


def check(result: ParityResult, ledger: dict) -> ParityCheck:
    """Judge one platform's measurement against the ledger. Pure."""
    verdict = ParityCheck(platform=result.platform, error=result.error)
    if result.error is not None:
        return verdict

    one_sided = [(name, "codegen host did not render it") for name in result.missing]
    one_sided += [(name, "dynamic did not render it") for name in result.codegen_only]

    measured = (
        {name for name, _ in result.mismatched}
        | set(result.missing)
        | set(result.codegen_only)
    )
    for name, distance in result.mismatched:
        if (name, result.platform, result.env) in ledger:
            verdict.accepted += 1
        else:
            verdict.unrecorded.append(f"{name} (distance {distance})")
    for name, why in one_sided:
        if (name, result.platform, result.env) in ledger:
            verdict.accepted += 1
        else:
            verdict.one_sided.append(f"{name} ({why})")

    for (name, platform, env), _entry in ledger.items():
        if platform == result.platform and env == result.env and name not in measured:
            verdict.stale.append(name)

    return verdict
