"""dynamic ≡ codegen parity (``jui conformance parity`` / ``gate --parity``).

The conformance suite renders every fixture through each platform's
**dynamic** pipeline; production apps ship the **generated** code. Nothing
in CI ever said those two agree — the invariant lived in maintainer working
memory, and the same semantic bug got fixed twice (once per pipeline) four
times in a row (grid spacing, Collection defaults, enabled, .disabled
order). This module makes the invariant mechanical.

No second truth is minted: the codegen host's screenshots are compared
against the **same platform's committed dynamic baseline**
(``baselines/<env>/<platform>.hashes.json``, same dhash-64, same stored
threshold). A fixture whose codegen render matches the dynamic baseline
within the calibrated threshold is proof — for that fixture, on that
platform, in that render environment — that dynamic and codegen draw the
same thing.

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

from .baseline import DEFAULT_ENV, BaselineError, dhash_file, hamming, load_baseline

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


def ledger_path(conformance_dir: Path) -> Path:
    return Path(conformance_dir) / LEDGER_NAME


@dataclass
class ParityResult:
    """Outcome of one platform's codegen-vs-dynamic-baseline measurement."""

    platform: str
    env: str = DEFAULT_ENV
    threshold: int = 0
    #: names compared and within threshold — dynamic ≡ codegen holds
    matched: list = field(default_factory=list)
    #: (name, distance) beyond threshold — the codegen draws something else
    mismatched: list = field(default_factory=list)
    #: baseline names with no codegen screenshot — fixture missing from the
    #: codegen host (generation failed, compile skip, not captured)
    missing: list = field(default_factory=list)
    #: codegen screenshots with no baseline hash (informational — e.g. a
    #: name deliberately excluded from the baseline)
    extra: list = field(default_factory=list)
    error: str | None = None  # nothing was measured (no baseline / Pillow …)


def measure(
    conformance_dir: Path,
    platform: str,
    env: str = DEFAULT_ENV,
    codegen_dir: Path | None = None,
) -> ParityResult:
    """Compare every codegen screenshot against the dynamic baseline.

    Comparison is name-wise over the baseline's own key space: every
    baseline entry must have a matching codegen render within the stored
    threshold; anything else lands in a non-passing bucket.
    """
    conformance_dir = Path(conformance_dir)
    if codegen_dir is None:
        codegen_dir = artifacts_dir(conformance_dir, platform)
    codegen_dir = Path(codegen_dir)

    result = ParityResult(platform=platform, env=env)

    baseline = load_baseline(conformance_dir, platform, env)
    if baseline is None:
        result.error = (
            f"no dynamic baseline for env '{env}' / {platform} — parity compares "
            f"against baselines/{env}/{platform}.hashes.json; bake it first"
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
    seen = set()
    for name, expected in hashes.items():
        png = codegen_dir / name
        if not png.is_file():
            result.missing.append(name)
            continue
        seen.add(name)
        try:
            distance = hamming(dhash_file(png), expected)
        except BaselineError as exc:
            result.error = str(exc)
            return result
        if distance <= result.threshold:
            result.matched.append(name)
        else:
            result.mismatched.append((name, distance))

    for png in sorted(codegen_dir.glob("*.png")):
        if png.name not in hashes:
            result.extra.append(png.name)

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
    for name in result.missing:
        key = (name, result.platform, result.env)
        prior = existing.get(key, {})
        merged[key] = {
            "screenshot": name,
            "platform": result.platform,
            "env": result.env,
            "status": "missing",
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
    error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.unrecorded and not self.stale and self.error is None


def check(result: ParityResult, ledger: dict) -> ParityCheck:
    """Judge one platform's measurement against the ledger. Pure."""
    verdict = ParityCheck(platform=result.platform, error=result.error)
    if result.error is not None:
        return verdict

    measured = {name for name, _ in result.mismatched} | set(result.missing)
    for name, distance in result.mismatched:
        if (name, result.platform, result.env) in ledger:
            verdict.accepted += 1
        else:
            verdict.unrecorded.append(f"{name} (distance {distance})")
    for name in result.missing:
        if (name, result.platform, result.env) in ledger:
            verdict.accepted += 1
        else:
            verdict.unrecorded.append(f"{name} (missing)")

    for (name, platform, env), _entry in ledger.items():
        if platform == result.platform and env == result.env and name not in measured:
            verdict.stale.append(name)

    return verdict
