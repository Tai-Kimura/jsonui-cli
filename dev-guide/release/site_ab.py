#!/usr/bin/env python3
"""A/B two generated docs sites, so "only additions" is measured, not asserted.

WHY THIS EXISTS. A change that adds a section to the generated site carries a
claim about everything it did NOT touch: the existing pages are unchanged. A
file count cannot see a changed byte inside a page that is still there, and
eyeballing one sample cannot see the page that disappeared. This hashes every
file on both sides and classifies all of them, printing the denominator.

THE WALL CLOCK. The generator stamps a generation time into every page, in
THREE spellings:

    <strong>Generated:</strong> 2026-09-05 00:56:31
    <p class='generated'>Generated: 2026-09-05 00:56:32</p>
    <span class="info">Generated: 2026-09-05 00:56:31</span>

So the generator is not deterministic: running the SAME tool twice on the
SAME input differed in 77 of 275 files for that reason alone (measured
2026-09-05). A raw byte comparison reports "existing output moved" every
time, including when comparing a tool against itself -- and a check that
fires unconditionally says nothing.

Only the timestamp VALUE is replaced. The markup around it stays in the hash,
so renaming a class or restructuring that line still shows up as a change.
The number of stamps blanked on each side is printed: a normaliser that
quietly ate a real difference would be worse than no normaliser at all. (The
first version of this file anchored on the first spelling only, and still
reported 2 of 275 files changed between a tool and itself. That failure is
how the other two spellings were found -- if a future spelling appears, the
same symptom will point at it.)

WHAT IT DOES NOT DO. It does not know which pages are supposed to be new. It
reports added paths; deciding that they are exactly the intended section is
the reader's job.

CONTROLS (run 2026-09-05, all as expected):
  same tool twice ............................. 275/0/0/0, exit 0
  distributed release vs dev HEAD ............. 275/0/0/0, exit 0
  one byte planted in an existing page ........ CHANGED,  exit 1
  an existing page deleted .................... REMOVED,  exit 1
  markup around a normalised stamp changed .... CHANGED   (not swallowed)
  a new page added ............................ ADDED,    exit 0
  two sides sharing no paths .................. exit 2, INCONCLUSIVE
  a tree containing sockets ................... counted as skipped, exit 2
                                                (it used to raise, and the
                                                traceback's exit 1 read as a
                                                finding)

Usage:
  site_ab.py <before_dir> <after_dir>

Exit 0 when nothing existing changed or disappeared, 1 when something did,
2 when the comparison could not be made.
"""
import hashlib
import os
import re
import sys

# Anchored on the word, because the markup around it varies (see above).
STAMP = re.compile(
    rb"(Generated:(?:</[a-zA-Z]+>)?\s*)\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
)


def manifest(root):
    """path relative to root -> (sha256 of normalised bytes, stamps blanked).

    Anything that is not a regular readable file is COUNTED and skipped, not
    hashed and not swallowed. Pointed at a directory holding a socket, the
    first version raised OSError mid-walk; the traceback exited 1, which this
    tool's own contract reads as "existing output moved". A crash must not be
    able to impersonate a finding.
    """
    out = {}
    skipped = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            if not os.path.isfile(full):
                skipped.append(rel)
                continue
            try:
                with open(full, "rb") as fh:
                    raw = fh.read()
            except OSError as exc:
                skipped.append(f"{rel} ({exc.strerror})")
                continue
            body, n = STAMP.subn(rb"\1 <normalised>", raw)
            out[rel] = (hashlib.sha256(body).hexdigest(), n)
    return out, skipped


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    before_dir, after_dir = sys.argv[1], sys.argv[2]
    for d in (before_dir, after_dir):
        if not os.path.isdir(d):
            print(f"INCONCLUSIVE: not a directory: {d}")
            return 2
    before, skipped_before = manifest(before_dir)
    after, skipped_after = manifest(after_dir)

    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    common = sorted(set(before) & set(after))
    changed = sorted(p for p in common if before[p][0] != after[p][0])
    same = [p for p in common if before[p][0] == after[p][0]]

    print(f"before : {len(before)} files  ({before_dir})")
    print(f"after  : {len(after)} files  ({after_dir})")
    print(
        "normalised 'Generated:' stamps: "
        f"before {sum(n for _h, n in before.values())} / "
        f"after {sum(n for _h, n in after.values())}"
    )
    print(
        f"unchanged {len(same)} / changed {len(changed)} / "
        f"added {len(added)} / removed {len(removed)}"
    )

    if skipped_before or skipped_after:
        print(f"unreadable/not-a-file: before {len(skipped_before)} / after {len(skipped_after)}")
        for p in (skipped_before + skipped_after)[:10]:
            print(f"  SKIPPED: {p}")

    for label, paths in (("CHANGED", changed), ("REMOVED", removed), ("ADDED", added)):
        for p in paths:
            print(f"  {label}: {p}")

    # Two sides that share no paths compare nothing, and would otherwise
    # print a clean "0 changed" -- the shape of a pass.
    if not common:
        print("INCONCLUSIVE: the two sides share no paths — nothing was compared")
        return 2

    ok = not changed and not removed
    print("RESULT: " + ("only additions" if ok else "EXISTING OUTPUT MOVED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
