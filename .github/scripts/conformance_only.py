#!/usr/bin/env python3
"""Narrow a conformance directory to the fixtures a dispatch names, and their controls.

    conformance_only.py narrow CONFORMANCE_DIR "id1,id2"

conformance-mobile.yml's `only` input: a run that draws the named fixtures —
and each one's control, which the report compares it with — and nothing else,
so a fixture whose picture is new or changed can be baked
(`jui conformance baseline update --only-new`, or `--take` for a moved one)
from a short run before the full run, instead of a full run that goes red for
want of the baseline, a bake, and a second full run.

The manifest is rewritten in place: `fixtures` keeps the named ids and their
controls in manifest order, `counts.fixtures` says how many, and
`peerExpectedIdentical` keeps only the groups whose members are all kept. The
layouts and companions stay where they are (each face reads what the manifest
names). An id the manifest does not have is refused, naming it: a typo would
otherwise draw nothing and look like a run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


class Refused(Exception):
    pass


def parse_ids(text: str) -> list[str]:
    ids = [part.strip() for part in text.split(",")]
    ids = [i for i in ids if i]
    if not ids:
        raise Refused("no fixture id given")
    return ids


def narrowed(manifest: dict, ids: list[str]) -> dict:
    fixtures = manifest["fixtures"]
    by_id = {f["id"]: f for f in fixtures}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise Refused("the manifest has no " + ", ".join(missing))
    keep = set(ids)
    for i in ids:
        control = by_id[i].get("control")
        if isinstance(control, str) and control:
            if control not in by_id:
                raise Refused(f"{i}: its control {control} is not in the manifest")
            keep.add(control)
    out = dict(manifest)
    out["fixtures"] = [f for f in fixtures if f["id"] in keep]
    if isinstance(manifest.get("counts"), dict):
        out["counts"] = dict(manifest["counts"], fixtures=len(out["fixtures"]))
    peers = manifest.get("peerExpectedIdentical")
    if isinstance(peers, list):
        out["peerExpectedIdentical"] = [g for g in peers
                                        if isinstance(g, (list, tuple)) and g and all(m in keep for m in g)]
    return out


def narrow(conformance: Path, text: str) -> list[str]:
    path = conformance / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    out = narrowed(manifest, parse_ids(text))
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return [f["id"] for f in out["fixtures"]]


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "narrow":
        kept = narrow(Path(argv[1]), argv[2])
        print(f"only: {len(kept)} fixture(s) — the named ones and their controls")
        for fid in kept:
            print(f"  {fid}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Refused as e:
        print(f"error: only: {e}", file=sys.stderr)
        sys.exit(1)
