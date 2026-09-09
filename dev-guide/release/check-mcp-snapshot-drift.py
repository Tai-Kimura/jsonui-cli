#!/usr/bin/env python3
"""Report how far the MCP server's bundled snapshot has fallen behind shared/core.

🔻 THIS LEG REPORTS. IT NEVER FAILS THE RUN.

The snapshot can only be re-pinned AFTER a release exists to pin to, so between
a shared/core change and the next mcp-server bump the two ARE different, every
time, by construction. A gate that is red by construction gets switched off,
and a switched-off gate does not report that it is off. So this prints numbers
and the release report carries them; `run-suites.sh` calls it with `say`.

⚠️ WHAT THE SNAPSHOT IS. `spec_loader.ts` resolves in this order:

    JSONUI_CLI_PATH env  >  ./.jsonui-cli/  >  ~/.jsonui-cli/  >  data/ (this snapshot)

so the snapshot is the LAST fallback: it is read only where no CLI is
installed. Drift here does not reach a machine that has the CLI. That is why
the count is the information and "stale" is not.

🚨 THREE POPULATIONS, KEPT APART. Collapsing them makes a constant 2 appear in
every run and buries the one file that actually moved:

    mirrored      in shared/core AND in the snapshot -> compare bytes
    canon-only    in shared/core, not in the snapshot
    snapshot-only in the snapshot, not in shared/core

`canon-only` is not automatically a gap: the server may simply not read that
file. Rather than assume either way, this counts references to the name in the
server's own sources and prints the count, so "intentional" is measured on
every run instead of being remembered from the day someone checked.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

HASH = "sha256"  # ⚠️ named in the output: two lanes compared md5 to sha1 today.


def digest(p: Path) -> str:
    return hashlib.new(HASH, p.read_bytes()).hexdigest()[:12]


def canon_last_change(repo: Path, rel: str) -> str:
    """When the canonical side last moved — the answer to "since when"."""
    r = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%h %ad", "--date=short", "--", rel],
        capture_output=True, text=True)
    return r.stdout.strip() or "(no commit touches it)"


def references(src: Path, stem: str) -> int | None:
    """How many of the server's source files name this canon file.

    None means the question could not be asked (no sources here) — which must
    not print as 0, or "nobody reads it" and "nobody looked" become one number.
    """
    if not src.is_dir():
        return None
    r = subprocess.run(["grep", "-rl", stem, str(src)], capture_output=True, text=True)
    return len([l for l in r.stdout.splitlines() if l.strip()])


def _snapshot_roots() -> list[tuple[str, Path, Path | None]]:
    """Where the snapshots live. Overridable so the arms can point elsewhere.

    🚨 WITHOUT THE OVERRIDE THIS SCRIPT CANNOT BE TESTED. Hard-coding
    `Path.home()` means the only way to exercise the detector is to edit the
    real snapshot, and an arm that mutates a shared checkout is worse than no
    arm. `JSONUI_MCP_SNAPSHOT_DIRS` is `label=data_dir[:src_dir]`, `;`-joined.
    """
    raw = os.environ.get("JSONUI_MCP_SNAPSHOT_DIRS")
    if not raw:
        return [
            ("dev checkout", Path.home() / "resource" / "jsonui-mcp-server" / "data",
             Path.home() / "resource" / "jsonui-mcp-server" / "src"),
            ("distributed", Path.home() / ".jsonui-mcp-server" / "data", None),
        ]
    out: list[tuple[str, Path, Path | None]] = []
    for entry in raw.split(";"):
        if not entry.strip():
            continue
        label, _, rest = entry.partition("=")
        data, _, src = rest.partition(":")
        out.append((label, Path(data), Path(src) if src else None))
    return out


def main(argv: list[str]) -> int:
    repo = Path(argv[1] if len(argv) > 1 else ".").resolve()
    canon_dir = repo / "shared" / "core"
    snapshots = _snapshot_roots()
    present = [(label, d, s) for label, d, s in snapshots if d.is_dir()]
    if not present:
        print("   SKIPPED: no mcp-server checkout "
              f"({' , '.join(str(d) for _, d, _ in snapshots)}) — "
              "this is not a count of zero differences")
        return 0
    if not canon_dir.is_dir():
        print(f"   SKIPPED: no shared/core in {repo} — not a count of zero")
        return 0

    canon = {p.name: p for p in sorted(canon_dir.glob("*.json"))}
    for label, data_dir, src_dir in present:
        snap = {p.name: p for p in sorted(data_dir.glob("*.json"))}
        mirrored = sorted(set(canon) & set(snap))
        canon_only = sorted(set(canon) - set(snap))
        snap_only = sorted(set(snap) - set(canon))
        same = [n for n in mirrored if digest(canon[n]) == digest(snap[n])]
        diff = [n for n in mirrored if n not in same]
        print(f"   [{label}] {data_dir}")
        print(f"     shared/core {len(canon)} file(s): "
              f"{len(mirrored)} mirrored ({len(same)} identical, {len(diff)} differ), "
              f"{len(canon_only)} canon-only, {len(snap_only)} snapshot-only "
              f"[{HASH}]")
        for n in diff:
            print(f"     DIFFERS {n}  canon {digest(canon[n])} != snapshot {digest(snap[n])}"
                  f"  [{HASH}]")
            print(f"             canon last changed: {canon_last_change(repo, f'shared/core/{n}')}")
        for n in canon_only:
            refs = references(src_dir, n[:-len('.json')]) if src_dir else None
            how = "could not check (no sources here)" if refs is None else \
                  (f"{refs} source file(s) name it — a mirror the snapshot is MISSING"
                   if refs else "0 source files name it — the server does not read it")
            print(f"     CANON-ONLY {n}: {how}")
        for n in snap_only:
            print(f"     SNAPSHOT-ONLY {n}: not from shared/core "
                  f"(a file with another origin, not drift)")
    print("     🔻 the snapshot carries no stamp naming the CLI version it was taken from, "
          "so the 'since when' above is the canon side's last commit, not the snapshot's pin")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
