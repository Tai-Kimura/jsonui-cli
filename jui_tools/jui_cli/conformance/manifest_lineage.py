"""Which manifests describe the same render.

THE COST THIS EXISTS TO REMOVE

A results file records the sha256 of the whole `manifest.json` it was rendered
against, and the gate calls it stale when that differs from the manifest on
disk. The check asks the right question — "are these pictures from this
manifest" — but the manifest carries `generatedFrom`, the hash of
`shared/core/attribute_definitions.json`. So editing ONE `description` string
in the SSoT, changing nothing that a fixture can be a function of, moves the
value and makes every platform's committed results stale. Measured 2026-09-15:
`conformance/fixtures/` 0 files changed, `manifest.json` 1 line changed, three
faces red, and the way back is web ~3 min + android ~8 min + ios ~45 min.

⚠️ THE GATE WAS ANSWERING TWO QUESTIONS WITH ONE VALUE, and that is the root:

  * *must the pictures be drawn again?*  — only if the FIXTURES moved.
  * *must the results be judged again?*  — whenever the manifest moved, and
    that judgment is re-done from the current manifest on every gate run
    anyway, at no cost.

WHY NOT JUST HASH LESS OF THE MANIFEST

The obvious fix — hash the manifest with `generatedFrom` removed — was measured
and rejected. The manifest holds no content hash of any fixture file: `layout`
and `test` are PATHS. So a change to the fixture generator that alters what
1099 layouts emit leaves every path, every count and the whole manifest
identical, and a gate keyed on the manifest alone would accept yesterday's
pictures as fresh. That trades a cost ticket for a correctness hole. The render
is a function of `conformance/fixtures/**`, so that is what is hashed here.

WHY A SIDECAR AND NOT A NEW MANIFEST FIELD

Each host computes the recorded value independently, in its own repository
(SwiftJsonUI's `ConformanceUITests.swift`, the web runner's `run.ts`,
KotlinJsonUI's conformance host). Putting `fixturesHash` in the manifest would
change the manifest, restaling everything once, and still leave three hosts to
change in lockstep before any of it meant something. This file changes nothing
the hosts read: it records, next to the manifest, what each manifest this tool
generated was equivalent TO. The hosts keep reporting the manifest hash they
already report.

THE MIGRATION HAS NO NEW SILENCE. A manifest hash with no lineage entry is
treated exactly as it is treated today — stale. Nothing becomes green that was
not green before; entries only ever move results OUT of "must re-render" once
this tool has recorded, from the files themselves, that the render inputs were
identical.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

#: Bumped when the meaning of a recorded digest changes. Entries written under
#: a different version are ignored rather than trusted — an equivalence is a
#: claim about how it was computed, and reading an old digest with new rules
#: would assert something nobody measured.
LINEAGE_VERSION = 1

FIXTURES_DIRNAME = "fixtures"
LINEAGE_FILENAME = "manifest_lineage.json"


def lineage_path(conformance_dir: Path) -> Path:
    return Path(conformance_dir) / LINEAGE_FILENAME


def manifest_digest(manifest_path: Path) -> str:
    """The value the hosts record — sha256 of the whole file, byte for byte."""
    return hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()


def fixtures_digest(conformance_dir: Path) -> str:
    """sha256 over every file under `conformance/fixtures/`, path and content.

    Paths are included, so a rename moves it; contents are included, so an
    in-place edit moves it. Both directions matter — the rejected
    manifest-minus-provenance hash could see neither.
    """
    root = Path(conformance_dir) / FIXTURES_DIRNAME
    digest = hashlib.sha256()
    if not root.is_dir():
        # An empty tree is a legitimate state with a stable answer; refusing
        # here would turn a packaging question into a comparison failure.
        return digest.hexdigest()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def ids_digest(manifest: dict) -> str:
    """sha256 over the manifest's fixture ids, in order.

    🔻 WHY THIS IS SEPARATE FROM THE FIXTURE FILES. A fixture can be renamed
    while its layout stays byte-identical: `fixtures_digest` would not move,
    but every result keyed on the old id now names a fixture that no longer
    exists. Requiring BOTH digests to match is what stops this file from
    declaring two manifests equivalent when only the pictures are.
    """
    ids = [
        f["id"]
        for f in manifest.get("fixtures", [])
        if isinstance(f, dict) and isinstance(f.get("id"), str)
    ]
    return hashlib.sha256("\0".join(sorted(ids)).encode("utf-8")).hexdigest()


def current_signature(conformance_dir: Path, manifest: dict) -> dict:
    return {
        "version": LINEAGE_VERSION,
        "fixtures": fixtures_digest(conformance_dir),
        "ids": ids_digest(manifest),
    }


def load(conformance_dir: Path) -> dict:
    path = lineage_path(conformance_dir)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Unreadable is not equivalent. Falling back to today's behaviour
        # costs a re-render; trusting a half-parsed file costs a wrong answer.
        return {}
    entries = raw.get("manifests")
    return entries if isinstance(entries, dict) else {}


def record(conformance_dir: Path, manifest_path: Path) -> tuple[Path, bool]:
    """Record what the manifest now on disk is equivalent to.

    Returns ``(path, changed)``. Called by `jui conformance generate` right
    after the manifest is written, so the entry is made from the same files
    the generator just produced rather than from a later reading of them.
    """
    conformance_dir = Path(conformance_dir)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    signature = current_signature(conformance_dir, manifest)
    entries = load(conformance_dir)
    key = manifest_digest(manifest_path)
    if entries.get(key) == signature:
        return lineage_path(conformance_dir), False
    entries[key] = signature
    payload = {
        "_generated": {
            "doNotEdit": True,
            "source": "jui conformance generate",
            "humanWarning": (
                "Append-only. Each key is the sha256 a runner records as "
                "manifestHash; the value says which fixture tree and id set that "
                "manifest described. The gate uses it to tell a manifest that "
                "DRIFTED (prose in the SSoT) from one whose fixtures MOVED — only "
                "the second needs the pictures drawn again."
            ),
        },
        "manifests": {k: entries[k] for k in sorted(entries)},
    }
    lineage_path(conformance_dir).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return lineage_path(conformance_dir), True


def equivalent_manifest_hashes(conformance_dir: Path, manifest: dict) -> frozenset[str]:
    """Manifest hashes whose render inputs are identical to what is on disk.

    Every recorded hash is filtered against the signature measured from the
    tree right now, so this is not "what the file contains" — an entry whose
    fixtures or ids have since moved is dropped even though it is in the file.
    The current manifest's own hash is included when it has been recorded, and
    that is harmless: the caller tests `hash != current` before ever consulting
    this set, so the value never reaches it.
    """
    signature = current_signature(Path(conformance_dir), manifest)
    return frozenset(
        key
        for key, recorded in load(Path(conformance_dir)).items()
        if isinstance(recorded, dict)
        and recorded.get("version") == LINEAGE_VERSION
        and recorded.get("fixtures") == signature["fixtures"]
        and recorded.get("ids") == signature["ids"]
    )
