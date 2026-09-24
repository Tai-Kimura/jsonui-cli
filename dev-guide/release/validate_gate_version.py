#!/usr/bin/env python3
"""Red-check xxxi at the tag: is `VALIDATE_GATE_FROM` what this release needs?

`jsonui-test validate` announces, one release ahead, the release from which
it fails unless contracts coverage exits 0, and switches the gate on at that
version (design §6.1, P3a; test_tools/jsonui_test_cli/contracts_coverage.py).
The version is a literal written when the announcing release is cut — never
derived, because a derived one agrees with every build and would pass this
check whatever it said. So the tag gate holds the literal to the tag:

  absent      the tree predates the section                    ok (n/a)
  unset       the section ships announcing no release          FAIL
  == next     this release announces the next release —        ok (announces)
              patch, minor or major (1.8.120 / 1.9.0 / 2.0.0 after 1.8.119)
  <= tag      this release gates                               ok (gates)
  otherwise   it announces a release that is not the next one  FAIL

Usage: validate_gate_version.py <tag version> < contracts_coverage.py
Prints one word — `ok` or `FAIL` — then the reason; exits 0 / 1.
"""
from __future__ import annotations

import re
import sys

_LITERAL = re.compile(r'^VALIDATE_GATE_FROM\s*:[^=\n]*=\s*(None|"([^"]*)"|\'([^\']*)\')\s*$', re.M)


def _key(version: str) -> tuple:
    out = []
    for part in version.lstrip("v").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        out.append(int(digits))
    return tuple(out)


def next_patch(version: str) -> str:
    parts = version.lstrip("v").split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def next_releases(version: str) -> tuple:
    """The versions that can follow *version*: next patch, minor, major."""
    major, minor, *_ = (int(x) for x in version.lstrip("v").split("."))
    return (next_patch(version), f"{major}.{minor + 1}.0", f"{major + 1}.0.0")


def verdict(tag_version: str, source: str) -> tuple[bool, str]:
    match = _LITERAL.search(source)
    if match is None:
        return True, "n/a — no VALIDATE_GATE_FROM in this tree (it predates the section)"
    if match.group(1) == "None":
        return False, ("VALIDATE_GATE_FROM is unset — the section would ship announcing "
                       f"no release; set it to {next_patch(tag_version)} (the next patch)")
    declared = match.group(2) if match.group(2) is not None else match.group(3)
    if declared in next_releases(tag_version):
        return True, f"announces {declared}, a release that can follow {tag_version}"
    if _key(declared) <= _key(tag_version):
        return True, f"gates since {declared} (tag {tag_version})"
    return False, (f"announces {declared}, which cannot be the next release after "
                   f"{tag_version} ({' / '.join(next_releases(tag_version))})")


def main(argv: list) -> int:
    ok, why = verdict(argv[1], sys.stdin.read())
    print(("ok" if ok else "FAIL") + " " + why)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
