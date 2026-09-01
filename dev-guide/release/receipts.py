#!/usr/bin/env python3
"""Enumerate the sync receipts, so a notice's recipient list is measured.

WHY THIS EXISTS. The notice recipient list was kept in the release lane's head
and rebuilt from who introduced themselves. A consumer that never introduced
itself fell off it and missed three releases' notices -- while its receipts
were being updated correctly the whole time. So the receipts knew, and the
list did not.

WHAT IT DOES NOT DO. It cannot compare against the recipient list: that list
is not in this repository, and putting it here would put consumer identities
in a public tree. So this prints the measured set and the writer reconciles.
That asymmetry is the point -- the half that can be measured is measured, and
the half that cannot is at least placed beside it.

`syncedAt` IS PRINTED, DELIBERATELY. It is not a per-run timestamp: the file
says "when this version arrived, not when sync last ran". The day this was
written, a consumer's experiment was invalidated by a distribution landing
mid-run, and that field was the only way to tell which arms straddled the
swap. An earlier draft of this script normalised it away as noise.

Exit codes: 0 every receipt agrees on one version, 1 they disagree,
2 could not be attempted (no roots, or no receipts under them) -- never pass
on absence, because "no receipts" and "all receipts agree" are the same
silence otherwise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RECEIPT = ".jsonui-cli/sync-meta.json"


def receipts(roots: list[Path]):
    """(face, platform, version, sha, syncedAt) for every receipt found.

    Roots are searched two levels deep: a consumer is either a repository or a
    directory of them, and hard-coding either shape would miss the other.
    """
    rows = []
    for root in roots:
        candidates = [root] + [p for p in sorted(root.iterdir())
                               if p.is_dir()] if root.is_dir() else []
        for candidate in candidates:
            meta = candidate / RECEIPT
            if not meta.is_file():
                continue
            # KEYED ON THE PATH, NOT THE BASENAME. The first run of this
            # script reported "6 faces" for eleven receipts under seven
            # directories, because two products each have a face directory
            # called the same thing and `candidate.name` collapsed them. That
            # is the exact defect this script exists to catch -- a face going
            # missing from a list -- reproduced inside the tool on its first
            # run. The name a face answers to is its path from the root above
            # the consumer, which is unique by construction.
            try:
                face = str(candidate.relative_to(root.parent))
            except ValueError:
                face = str(candidate)
            try:
                platforms = json.loads(
                    meta.read_text(encoding="utf-8"))["platforms"]
            except Exception as exc:
                rows.append((face, "?", f"UNREADABLE: {exc}", "", ""))
                continue
            for platform, m in sorted(platforms.items()):
                rows.append((face, platform, m.get("version", "?"),
                             (m.get("sourceSha") or "")[:12],
                             m.get("syncedAt", "")))
    return rows


def main(argv: list[str]) -> int:
    roots = [Path(a).expanduser().resolve() for a in argv[1:]]
    if not roots:
        print(f"usage: {argv[0]} <consumer root> [<consumer root> ...]",
              file=sys.stderr)
        return 2
    rows = receipts(roots)
    if not rows:
        print("CANNOT ATTEMPT: no sync receipts under the roots given "
              f"({', '.join(str(r) for r in roots)}) -- either the roots are "
              "wrong or nothing has ever been synced there", file=sys.stderr)
        return 2

    width = max(len(r[0]) for r in rows)
    for face, platform, version, sha, synced in rows:
        print(f"{face:<{width}}  {platform:<8} {version:<9} {sha:<13} {synced}")

    versions = {r[2] for r in rows}
    faces = sorted({r[0] for r in rows})
    print(f"\n{len(rows)} receipt(s) across {len(faces)} face(s): "
          f"{', '.join(faces)}")
    if len(versions) != 1:
        print(f"DISAGREE: {len(versions)} versions in play: "
              f"{', '.join(sorted(versions))}", file=sys.stderr)
        return 1
    print(f"all on {versions.pop()}")
    print("\nthis is the measured recipient set. Reconcile it against the "
          "notice list before sending -- a face missing from the list is "
          "silent here, because its receipts are correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
