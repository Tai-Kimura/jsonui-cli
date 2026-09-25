#!/usr/bin/env python3
"""The second tag gate: judge a tag CUT BUT NOT PUSHED with expectations taken
from the PREVIOUS tag, not from the branch or the working tree.

Usage: check-tag-from-prev.py <repo> <prev-tag> <tag> [tested-sha]

🔻 TIMING IS PART OF THE CONTRACT, as for check-tag.sh: run it after `git tag
-a` and before `git push --atomic`, and read its EXIT STATUS — with nothing
piped after it. `gate | tail` reports tail's status: the gate this one
replaces printed GATE_RC=0 over a red run that way.

🔻 WHY A SECOND GATE. check-tag.sh takes its expected values from the branch
and the working tree. This one takes them from three places only, and every
check line says which:
  from PREV      the previous tag's tree and first-parent history
  from rev-list  git's own answer for PREV..TAG (never the tag body's claim)
  from the tag   the tag's name (vX.Y.Z)
  HAND-SUPPLIED  the optional tested SHA, compared, never derived
It reads no VERSION of the candidate, no working tree, and takes no expected
value by hand except the one labelled so. What makes the two gates
independent is WHERE EACH GETS ITS EXPECTED VALUES: merging them, or deleting
one as a duplicate, leaves one source whose agreement with itself means
nothing.

⚠️ HISTORY. The first second gate (the triage lane's verify_tag.sh) lived in a
scratch directory, last ran at v1.8.94 (2026-09-16 01:34 JST), and was gone
from every disk by 2026-09-25 while check-tag.sh's header still said it
agreed. Its RANGE check compared counts only, so one deleted listing line
plus a duplicated or out-of-range one passed. This file is in the repo so it
cannot vanish again, and the RANGE arm judges membership per commit.

What it does NOT see (the silences this design makes, on purpose):
  - a stamp file new in this release (not in PREV's stamp commit) —
    jui_tools/tests/test_version_lockstep.py covers it from the tree side;
  - prose naming any version other than PREV's;
  - the wording of the tag body (check-tag.sh's hand-supplied words).
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter

LISTING = re.compile(r"^  ([0-9a-f]{7,40}) ")
RANGE_LINE = re.compile(r"^RANGE: (\d+) commits? since (\S+)")
VERSION_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def git(repo: str, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout if result.returncode == 0 else ""


def version_of(tag: str) -> tuple[int, int, int] | None:
    """(major, minor, patch) from 'vX.Y.Z'. Compared as numbers: as strings
    '1.12.0' sorts before '1.9.0'."""
    match = VERSION_TAG.match(tag)
    return tuple(int(part) for part in match.groups()) if match else None


def later(prev: str, tag: str) -> bool:
    """The tag names a later version than PREV, compared as numbers."""
    old, new = version_of(prev), version_of(tag)
    return old is not None and new is not None and new > old


def mentions(version: str) -> re.Pattern:
    """A version as a whole token: '1.9.10' is not in '1.9.100' or '11.9.10'."""
    return re.compile(r"(?<![0-9.])" + re.escape(version) + r"(?![0-9])")


def count_in(text: str, version: str) -> int:
    return sum(1 for line in text.splitlines() if mentions(version).search(line))


def resolve(repo: str, abbrev: str) -> str | None:
    out = git(repo, "rev-parse", "-q", "--verify", f"{abbrev}^{{commit}}", check=False).strip()
    return out or None


def tag_body(repo: str, tag: str) -> str:
    raw = git(repo, "cat-file", "tag", tag, check=False)
    return raw.split("\n\n", 1)[1] if "\n\n" in raw else ""


def range_sets(repo: str, prev: str, tag: str, body: str) -> dict:
    """Arm A's four sets. Expected = rev-list PREV..TAG (full OIDs); listed =
    each listing line resolved to a full OID — so a longer or shorter
    abbreviation is the same commit, and a subject that names another commit
    ("Merge commit 'af04a42c' …") is not a listing."""
    expected = set(git(repo, "rev-list", f"{prev}..{tag}^{{}}").split())
    listed: Counter = Counter()
    unresolved = []
    for line in body.splitlines():
        match = LISTING.match(line)
        if not match:
            continue
        oid = resolve(repo, match.group(1))
        if oid is None:
            unresolved.append(match.group(1))
        else:
            listed[oid] += 1
    declared = None
    for line in body.splitlines():
        match = RANGE_LINE.match(line)
        if match:
            declared = (int(match.group(1)), match.group(2))
            break
    return {
        "expected": expected,
        "missing": sorted(expected - set(listed)),
        "extra": sorted(set(listed) - expected),
        "duplicate": sorted(oid for oid, n in listed.items() if n > 1),
        "unresolved": unresolved,
        "listed_lines": sum(listed.values()) + len(unresolved),
        "declared": declared,
    }


def stamp_commit(repo: str, prev: str) -> str | None:
    """PREV's stamp commit: the last commit on PREV's FIRST-PARENT line that
    touched VERSION. A train may re-apply the stamp by cherry-pick or bring
    it in by a merge, so 'the bump' is not always a plain commit on main."""
    out = git(repo, "log", "-1", "--first-parent", "--format=%H", prev, "--", "VERSION").strip()
    return out or None


def stamps_from(repo: str, commit: str, before: str, after: str) -> list[str]:
    """Files where `commit` (against its first parent) removed a line naming
    `before` and added a line naming `after` — the stamp shape. A line that
    only ADDS `after` (prose about the new version) is not a stamp."""
    diff = git(repo, "diff", "-U0", f"{commit}^1", commit)
    removed: set[str] = set()
    added: set[str] = set()
    path = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("--- "):
            continue
        elif path and line.startswith("-") and mentions(before).search(line):
            removed.add(path)
        elif path and line.startswith("+") and mentions(after).search(line):
            added.add(path)
    return sorted(removed & added)


def marks(repo: str, ref: str, version: str, exclude: set[str]) -> Counter:
    """Lines naming `version` outside the stamp files, as (path, text) — the
    line number is dropped so an edit above a mark does not move it."""
    out = git(repo, "grep", "-I", "-n", "-z", "-F", version, ref, "--", ".", check=False)
    found: Counter = Counter()
    pattern = mentions(version)
    for record in out.splitlines():
        parts = record.split("\0")
        if len(parts) < 3:
            continue
        path = parts[0].split(":", 1)[1] if ":" in parts[0] else parts[0]
        text = "\0".join(parts[2:])
        if path in exclude or not pattern.search(text):
            continue
        found[(path, text)] += 1
    return found


class Gate:
    def __init__(self) -> None:
        self.n = self.passed = self.failed = 0

    def check(self, source: str, what: str, ok: bool, detail: str = "") -> bool:
        self.n += 1
        verdict = "PASS" if ok else "FAIL"
        self.passed += ok
        self.failed += not ok
        print(f"  {self.n:2d} {verdict} [{source}] {what}" + (f" — {detail}" if detail else ""))
        return ok


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    repo, prev, tag = argv[:3]
    tested = argv[3] if len(argv) == 4 else None
    gate = Gate()
    print(f"== second tag gate  repo={repo}  {prev}..{tag}  (expectations from {prev}, rev-list, the tag name)")

    # --- D: the tag's shape -------------------------------------------------
    gate.check("from the tag", f"{tag} is an annotated tag object",
               git(repo, "cat-file", "-t", tag, check=False).strip() == "tag")
    peel = git(repo, "rev-parse", "-q", "--verify", f"{tag}^{{commit}}", check=False).strip()
    gate.check("from PREV", f"{prev} is an ancestor of {tag}",
               bool(peel) and subprocess.run(
                   ["git", "-C", repo, "merge-base", "--is-ancestor", prev, peel]).returncode == 0)
    old, new = version_of(prev), version_of(tag)
    gate.check("from the tag", f"{tag} names a later version than {prev} (numeric)",
               later(prev, tag), f"{old} -> {new}")
    if tested is not None:
        want = resolve(repo, tested)
        gate.check("HAND-SUPPLIED", f"{tag} peels to the tested commit {tested}",
                   want is not None and want == peel, f"peel={peel[:12]} tested={(want or '?')[:12]}")

    # --- A: RANGE membership, per commit -------------------------------------
    body = tag_body(repo, tag) if peel else ""
    sets = range_sets(repo, prev, tag, body) if peel else None
    if sets is not None:
        n = len(sets["expected"])
        counts = (f"expected {n} (from rev-list) | lines {sets['listed_lines']} | missing {len(sets['missing'])}"
                  f" extra {len(sets['extra'])} duplicate {len(sets['duplicate'])}"
                  f" unresolved {len(sets['unresolved'])}")
        print(f"     range: {counts}")
        for name in ("missing", "extra", "duplicate", "unresolved"):
            for oid in sets[name]:
                subject = git(repo, "log", "-1", "--format=%s", oid, check=False).strip() if name != "unresolved" else ""
                print(f"       {name.upper():10s} {oid[:12]} {subject[:90]}")
        gate.check("from rev-list", f"the range {prev}..{tag} is not empty", n > 0, f"{n} commit(s)")
        gate.check("from rev-list", "every range commit is listed once, and nothing else is",
                   not (sets["missing"] or sets["extra"] or sets["duplicate"] or sets["unresolved"]), counts)
        declared = sets["declared"]
        gate.check("from rev-list", "the body's RANGE line states that count since PREV",
                   declared == (n, prev), f"declared {declared}, rev-list {n} since {prev}")

    # --- B: stamps, derived from PREV's stamp commit -------------------------
    stamps: list[str] = []
    if old is not None and new is not None:
        old_s, new_s = ".".join(map(str, old)), ".".join(map(str, new))
        commit = stamp_commit(repo, prev)
        before = git(repo, "show", f"{commit}^1:VERSION", check=False).strip() if commit else ""
        at_prev = git(repo, "show", f"{prev}:VERSION", check=False).strip()
        gate.check("from PREV", f"{prev}:VERSION says {old_s}", at_prev == old_s, f"read {at_prev or '<none>'}")
        if commit and before:
            stamps = stamps_from(repo, commit, before, old_s)
            print(f"     stamp commit {commit[:12]} ({before} -> {old_s}, first-parent): {len(stamps)} file(s)")
        gate.check("from PREV", "the stamp set is derived and contains VERSION", "VERSION" in stamps,
                   f"{len(stamps)} file(s)")
        for path in stamps:
            prev_text = git(repo, "show", f"{prev}:{path}", check=False)
            tag_text = git(repo, "show", f"{tag}:{path}", check=False)
            had, has_new, has_old = count_in(prev_text, old_s), count_in(tag_text, new_s), count_in(tag_text, old_s)
            gate.check("from PREV", f"stamp {path}", has_new == had and has_old == 0,
                       f"{prev} had {old_s}x{had}; {tag} has {new_s}x{has_new} {old_s}x{has_old}")

        # --- C: history marks, asymmetric ----------------------------------
        a = marks(repo, prev, old_s, set(stamps))
        b = marks(repo, tag, old_s, set(stamps))
        gone = a - b
        added = b - a
        print(f"     marks naming {old_s} outside the stamps: {prev}={sum(a.values())} {tag}={sum(b.values())}"
              f" | gone {sum(gone.values())} added {sum(added.values())} (added is printed, not judged)")
        if not a:
            print(f"     ℹ️  {prev} has no mark naming {old_s}: this arm is INERT this train (nothing to rewrite)")
        tag_lines = {(p, t) for p, t in b} | {(p, t) for p, t in marks(repo, tag, new_s, set(stamps))}
        for (path, text), k in sorted(gone.items()):
            kind = "BUMPED" if (path, mentions(old_s).sub(new_s, text)) in tag_lines else "GONE"
            print(f"       {kind:6s} x{k} {path}: {text.strip()[:110]}")
        gate.check("from PREV", f"every mark naming {old_s} in {prev} survives in {tag}", not gone,
                   f"{sum(gone.values())} rewritten or removed")

    verdict = "ALL CHECKS PASSED" if gate.failed == 0 else "SOME CHECKS FAILED"
    print(f"== {verdict}: {gate.passed} PASS / {gate.failed} FAIL of {gate.n}")
    return 0 if gate.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
