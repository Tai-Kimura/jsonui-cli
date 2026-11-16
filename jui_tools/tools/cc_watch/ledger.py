"""The ledger (ledger.json) and its gate: what tests/test_cc_dependency_ledger.py asserts is empty."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import marks as M
from .probes import PROBES

LEDGER = Path(__file__).with_name("ledger.json")
REQUIRED = ("id", "name", "relies_on", "probe", "impact", "files")


def load(path: Path = LEDGER) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def listed(ledger: dict) -> set[str]:
    """The repository files the ledger lists (an external ~/... entry is a note, not a file to check)."""
    return {f for e in ledger["entries"] for f in e.get("files", []) if not f.startswith("~")}


def check(root: Path, ledger: dict | None = None, marks: dict[str, re.Pattern] | None = None,
          files: list[str] | None = None) -> list[str]:
    """Every way the ledger and the code disagree, one line each (empty: the gate is green)."""
    ledger = load() if ledger is None else ledger
    problems: list[str] = []
    ids = [e.get("id") for e in ledger.get("entries", [])]
    for e in ledger.get("entries", []):
        missing = [k for k in REQUIRED if not e.get(k)]
        if missing:
            problems.append(f"entry {e.get('id')!r}: missing {', '.join(missing)}")
        if e.get("probe") and e["probe"] not in PROBES:
            problems.append(f"entry {e.get('id')!r}: probe {e['probe']!r} does not exist in tools/cc_watch/probes.py")
        for f in e.get("files", []):
            if f.startswith("/"):
                problems.append(f"entry {e.get('id')!r}: {f!r} is an absolute path (write files outside the repository as ~/...)")
    if len(set(ids)) != len(ids):
        problems.append(f"duplicate entry ids: {sorted(i for i in set(ids) if ids.count(i) > 1)}")
    tracked = M.tracked_files(root) if files is None else files
    hits = M.scan(root, marks, tracked)
    known = listed(ledger)
    excused = ledger.get("not_relying", {})
    def is_excused(rel: str) -> str | None:
        return next((p for p in excused if rel == p or (p.endswith("/") and rel.startswith(p))), None)
    for path, reason in sorted(excused.items()):
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"not_relying {path!r}: no reason (say why it does not rely on Claude Code, or list it in an entry)")
        if not (root / path).exists():
            problems.append(f"not_relying {path!r}: the path does not exist any more (remove it from not_relying)")
        both = sorted(k for k in known if k == path or (path.endswith("/") and k.startswith(path)))
        for k in both:
            problems.append(f"{k}: both in a ledger entry and in not_relying {path!r} (it cannot be both: keep one)")
    # default-deny: in the areas that face the CLI, a human decides for every file, whatever the marks say
    for rel in sorted(tracked):
        if M.FACING.search(rel) and rel not in known and not is_excused(rel):
            seen = "".join(f"; line {n} matches {mark!r}" for mark, n, _t in hits.get(rel, []))
            problems.append(f"{rel}: a file in an area that faces Claude Code (marks.FACING{seen}) with no decision: add it to "
                            "a ledger entry's files, or to not_relying with a reason (jui_tools/tools/cc_watch/ledger.json)")
    for rel, found in sorted(hits.items()):
        if rel not in known and not is_excused(rel) and not M.FACING.search(rel):   # FACING: reported above
            where = "; ".join(f"line {n} matches {mark!r}: {text}" for mark, n, text in found)
            problems.append(f"{rel} relies on Claude Code ({where}) but no ledger entry lists it: add an entry to "
                            "jui_tools/tools/cc_watch/ledger.json, or add the file to an existing entry's files")
    for rel in sorted(known):
        if not (root / rel).exists():
            problems.append(f"{rel}: listed in the ledger but the file does not exist")
        elif M.in_scope(rel) and rel not in hits and not M.FACING.search(rel):
            problems.append(f"{rel}: listed in the ledger but no mark matches it any more (remove it, or extend the marks)")
    return problems
