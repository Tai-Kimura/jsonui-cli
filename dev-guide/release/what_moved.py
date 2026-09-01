"""What moved between two tags, by consumer-visible surface.

Written because the release notice kept saying things like "the generator
did not move" and "stamps only" — true statements with a denominator the
sentence does not name. Two lanes caught the same shape in one release:

  "the generator did not move" — `branch_tests.py` was byte-identical, and
      `mock/generate.py` moved in the same tag range. The consumer gets the
      sentence and the diff together and has to split them.
  "stamps only"                — `cli.py` gained 145 lines of printing. A
      lane that publishes that output verbatim cannot take it as a stamp.

Same defect as `copied 0` (fixed in c9c287ca) with numbers replaced by
prose. So the notice's "what moved" section is DERIVED from the diff, and
an unclassified path is printed as such rather than silently dropped —
exit 1 until someone names its surface.

A file is a stamp because its DIFF is version literals, not because of its
name: `__init__.py` carries the fallback version AND the logic around it.
"""
from __future__ import annotations

import re
import subprocess
import sys

# `v?` because the sibling pin is spelled `...git@vX.Y.Z#...`: `\b` finds
# no boundary between `v` and `1`, so the pin line failed the stamp test
# and dragged document_tools/pyproject.toml into the jsonui-doc surface.
STAMP_LINE = re.compile(r"^[+-].*(?<![\w.])v?\d+\.\d+\.\d+(?![\w.])")
STAMPS = "version stamps — the whole diff is version literals"

SURFACES = [
    ("branch-tests generator — REGENERATE (`branch-tests --check` will drift)",
     r"^test_tools/jsonui_test_cli/(branch_tests|branch_runtime_prose)\.py$"),
    ("mock generator — run `mock generate --check` (output may still be unchanged)",
     r"^test_tools/jsonui_test_cli/mock/"),
    ("validate PRINTING surface — quoted output changes even when gates do not",
     r"^test_tools/jsonui_test_cli/(cli\.py|validation/)"),
    ("test CLI — other", r"^test_tools/jsonui_test_cli/"),
    ("jsonui-doc", r"^document_tools/"),
    ("vendored platform codegen — arrives via `jui sync_tool`",
     r"^(sjui_tools|kjui_tools|rjui_tools)/"),
    ("jui CLI — machine-shared, arrives via bootstrap", r"^jui_tools/"),
    ("release procedure / installer — maintainer side only",
     r"^(dev-guide|installer)/"),
    ("tests only — no shipped behaviour", r"^[^/]+/tests?/"),
    # Docs are a shipped surface: a config key a face has to WRITE lives here
    # before it lives anywhere else. v1.7.50 added `test.testDir` and the only
    # place a consumer can read what it means is this file — announcing that
    # release as code-only would have shipped a key nobody could look up.
    ("consumer docs — a config key or behaviour a face has to read",
     r"(^|/)(README|CHANGELOG)\.md$|^docs/"),
]


def _run(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True,
                          check=True).stdout


# This file is distributed: `dev-guide/` is copied into `~/.jsonui-cli` by
# the installer, so every face HAS it. Measured 2026-09-01: `~/.jsonui-cli`
# is not a git checkout, so every `git diff` below fails there. A consumer
# asked to re-derive a notice would get a CalledProcessError traceback and
# read it as the tool being broken, when the tool is fine and the tree is
# not one it can read. Arriving and being runnable are different things —
# say which one is missing.
def _needs_a_git_tree() -> str | None:
    proc = subprocess.run(("git", "rev-parse", "--git-dir"),
                          capture_output=True, text=True)
    if proc.returncode == 0:
        return None
    return ("CANNOT ATTEMPT: this is not a git checkout of jsonui-cli.\n"
            "  `dev-guide/` is copied into ~/.jsonui-cli by the installer, "
            "but that tree has no\n"
            "  history to diff. Run this from a clone of the toolchain repo, "
            "naming the two tags.")


def stamp_only(frm: str, to: str, path: str) -> bool:
    body = [l for l in _run("git", "diff", "-U0", frm, to, "--", path).splitlines()
            if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    return bool(body) and all(STAMP_LINE.match(l) for l in body)


def main(frm: str, to: str) -> int:
    problem = _needs_a_git_tree()
    if problem:
        print(problem, file=sys.stderr)
        return 2
    paths = _run("git", "diff", "--name-only", frm, to).split()
    if not paths:
        print(f"no files changed between {frm} and {to}")
        return 0

    hit: dict[str, list[str]] = {}
    unclassified: list[str] = []
    for path in paths:
        if stamp_only(frm, to, path):
            hit.setdefault(STAMPS, []).append(path)
            continue
        for label, rx in SURFACES:
            if re.search(rx, path):
                hit.setdefault(label, []).append(path)
                break
        else:
            unclassified.append(path)

    print(f"what moved, {frm} -> {to}\n")
    for label in [l for l, _ in SURFACES] + [STAMPS]:
        if label in hit:
            print(f"  {label}")
            for path in sorted(hit[label]):
                print(f"      {path}")
    # What this cannot answer, said where its answer is read. "The
    # generator did not move" became "so no regeneration is needed" in a
    # notice, and a lane regenerated 38 files that same day: the ROUTES
    # baked into a branch test are a copy of the mocks, so a backend
    # declaring 426/429/503 drifts them with branch_tests.py byte-identical.
    # A diff between two tags of THIS repo cannot see that — the input
    # lives in the consumer's swagger and specs.
    print("\n  this reads a diff of the toolchain, so it answers"
          " \"did the generator move\" only.")
    print("  whether the INPUT moved (swagger, specs, hand-written mocks)"
          " is on the consumer side:")
    print("  a byte-identical generator still drifts when its input moved."
          " Say so in the notice.")
    if unclassified:
        print("\n  UNCLASSIFIED — name the surface before announcing:")
        for path in sorted(unclassified):
            print(f"      {path}")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: what_moved.py <from-tag> <to-tag>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
