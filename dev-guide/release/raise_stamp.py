#!/usr/bin/env python3
"""Raise the stamp of a jsonui-cli tree to another version.

    python3 raise_stamp.py <repo> <version>          rewrite the stamp lines
    python3 raise_stamp.py <repo> <version> --list   print them, write nothing

The stamp is what dev-guide/09-release-distribution.md §2 calls 刻印: the
lines test_version_lockstep holds to the root VERSION. They are found by the
runbook's predicate, never listed by hand (counted by hand once, the answer
was 5 and the tree had 9): among the TRACKED files outside tests/, spec/ and
docs/, a line holding the current version that is
    X.Y.Z                                   (a VERSION file)
    VERSION = 'X.Y.Z'                       (the Ruby tools)
    _FALLBACK_VERSION = "X.Y.Z"             (the Python packages)
    version = "X.Y.Z"                       (pyproject)
    jsonui-cli.git@vX.Y.Z#subdirectory=     (the sibling pin)
Prose that carries a version is not a stamp line and is left alone.

run-suites.sh uses it on a throwaway clone to run the suites at the next
stamp; it is not the release procedure. Prints each line it raised and the
count; exits 1 when it finds none (a predicate that matches nothing would
"raise" a tree to the version it already has).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PATTERNS = (
    r"^{v}$",
    r"VERSION = '{v}'",
    r'_FALLBACK_VERSION = "{v}"',
    r'^version = "{v}"',
    r"jsonui-cli\.git@v{v}#subdirectory=",
)
EXCLUDED = (":!*/tests/*", ":!*/spec/*", ":!docs/*", ":!tests/*", ":!spec/*")


def stamp_lines(repo: str, current: str) -> list[tuple[str, int, str]]:
    """(path, 1-based line number, text) of every stamp line at *current*."""
    listing = subprocess.run(
        ["git", "-C", repo, "grep", "-n", "-F", current, "--", ".", *EXCLUDED],
        capture_output=True, text=True)
    if listing.returncode not in (0, 1):
        raise RuntimeError(f"git grep: {listing.stderr.strip()}")
    rules = [re.compile(p.format(v=re.escape(current))) for p in PATTERNS]
    found = []
    for row in listing.stdout.splitlines():
        path, number, text = row.split(":", 2)
        if any(rule.search(text) for rule in rules):
            found.append((path, int(number), text))
    return found


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[2])
        return 2
    repo, target, listing_only = argv[1], argv[2], "--list" in argv[3:]
    current = (Path(repo) / "VERSION").read_text(encoding="utf-8").strip()
    lines = stamp_lines(repo, current)
    if not lines:
        print(f"no stamp line holds {current} — the predicate found nothing to raise")
        return 1
    by_file: dict[str, list[tuple[int, str]]] = {}
    for path, number, text in lines:
        by_file.setdefault(path, []).append((number, text))
    for path, rows in sorted(by_file.items()):
        file = Path(repo) / path
        content = file.read_text(encoding="utf-8").split("\n")
        for number, text in rows:
            assert content[number - 1] == text, (path, number)
            raised = text.replace(current, target)
            print(f"{path}:{number}: {text.strip()} -> {raised.strip()}")
            content[number - 1] = raised
        if not listing_only:
            file.write_text("\n".join(content), encoding="utf-8")
    verb = "would raise" if listing_only else "raised"
    print(f"{verb} {len(lines)} stamp line(s) in {len(by_file)} file(s): {current} -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
