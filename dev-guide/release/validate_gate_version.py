#!/usr/bin/env python3
"""Red-check xxxi at the tag: is every `*_GATE_FROM` what this release needs?

A gate literal names the release from which something starts failing —
`VALIDATE_GATE_FROM` (validate fails on contracts coverage against its
baseline — an entry not in it, one it keeps that has closed, and what cannot
be recorded; P3a, P3c)
and `UNMATCHED_GATE_FROM` (a generated branch test fails on a request no
declared route answered, P2e(a)) at the time of writing. Each is a literal
written when the announcing release is cut, never derived: a derived one
agrees with every build and would pass this check whatever it said.

The tag gate judges each constant on the pair (the previous tag's value, this
tree's value) — design v4.18, §6.1 P3a-1:

  previous -> now                                  verdict
  unset -> unset                                   ok    nothing announced yet
  unset -> the next release (patch/minor/major)    ok    announces
  L -> L, with L <= the tag                        ok    the gate is in
  L -> the next release, later than L              ok    postponed (re-announced)
  anything -> "withdrawn"                          ok    the announcement is withdrawn
                                                         by hand, and says so
  unset -> at or below the tag                     FAIL  a gate nobody announced
  L -> unset, or L -> earlier than L               FAIL  an undeclared withdrawal or
                                                         a gate brought forward
  a release that cannot follow the tag             FAIL  the notice would name a
                                                         release that is not next

and, for `VALIDATE_GATE_FROM` only, unset is FAIL (P3a-1's notice must ship).
Pairs the table leaves open are read by its intent: "withdrawn" before counts
as unset (it may be announced again); L -> L while L is still the next
release is ok (the same notice again); a constant that had a literal at the
previous tag and is gone from this tree is FAIL (the announcement vanished).

The constants are COLLECTED, not named here: every module-level assignment to
a name ending in `_GATE_FROM` in the tree's tracked Python files, read two
independent ways — Python's parser, and a line scan of column-0 assignments —
and the two must agree, so a spelling one reader misses is a FAIL, not a
constant quietly left out. The count and the names are printed. As a positive
control, a tree whose contracts coverage module names VALIDATE_GATE_FROM must
yield it.

Usage:
  validate_gate_version.py <tag version> --repo <dir> <this ref> <previous tag>
  validate_gate_version.py <tag version> <this tree's file> [<previous tag's file>]
      (the single-file form judges VALIDATE_GATE_FROM alone, as before)
Prints `ok` or `FAIL` and a summary, then one line per constant; exits 0 / 1.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys

WITHDRAWN = "withdrawn"
ABSENT = "absent"                     # not in the tree at all
VALIDATE = "VALIDATE_GATE_FROM"
#: The module the positive control reads: if it names VALIDATE_GATE_FROM, the
#: collector must have found it there.
CONTROL_PATH = "test_tools/jsonui_test_cli/contracts_coverage.py"

_NAME = re.compile(r"^[A-Z][A-Z0-9_]*_GATE_FROM$")
#: A gate version is three numbers and nothing else (the rule the gates read).
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_LINE = re.compile(r"^([A-Z][A-Z0-9_]*_GATE_FROM)\s*(?::[^=\n]*)?=(?!=)", re.M)
#: An assignment below module level (inside an `if`, a function): both readers
#: above look at the top level only, so without this a gate literal written
#: there would be missed by both, and agreement would prove nothing.
_INDENTED = re.compile(r"^[ \t]+([A-Z][A-Z0-9_]*_GATE_FROM)\s*(?::[^=\n]*)?=(?!=)", re.M)
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


def _describe(value) -> str:
    if value == ABSENT:
        return "not in the tree"
    if value is None:
        return "unset"
    return repr(value)


def judge(name: str, tag_version: str, current, previous=ABSENT) -> tuple[bool, str]:
    """One constant's verdict on the pair (previous tag's value, this tree's).

    Values are ABSENT, None (unset), WITHDRAWN, or a version string.
    """
    tag = tag_version.lstrip("v")
    # A previous value that is not a version (unreadable) announced nothing.
    before = previous if isinstance(previous, str) and _VERSION.match(previous) else None
    if current == ABSENT:
        if before is None:
            return True, f"n/a — no {name} in this tree"
        return False, (f"{name} was {before!r} at the previous tag and is gone from this tree "
                       f"— withdraw it with \"{WITHDRAWN}\" first (an announcement must not vanish)")
    if current == WITHDRAWN:
        return True, f"withdrawn (was {_describe(previous)}) — no gate, and the release note says so"
    if current is None:
        if name == VALIDATE:
            return False, (f"{name} is unset — the section would ship announcing no release; "
                           f"set it to {next_patch(tag)} (the next patch)")
        if before is None:
            return True, "unset — nothing announced, no gate"
        return False, (f"unset, but the previous tag announced {before!r} — withdraw it with "
                       f"\"{WITHDRAWN}\" (unsetting makes an announcement vanish)")
    if not _VERSION.match(current):
        return False, (f"{current!r} is unreadable — a gate version is three numbers "
                       f"(x.y.z) or \"{WITHDRAWN}\"; the gates read it as no gate")
    if before is not None and _key(current) < _key(before):
        return False, (f"{current} is earlier than the release the previous tag announced "
                       f"{before!r} — a gate brought forward")
    if current in next_releases(tag):
        if before is None:
            return True, f"announces {current}, a release that can follow {tag}"
        if current == before:
            return True, f"announces {current} again, a release that can follow {tag}"
        return True, f"postpones {before!r} to {current}, a release that can follow {tag}"
    if _key(current) <= _key(tag):
        if before == current:
            return True, f"gates since {current} (tag {tag}; the previous tag announced it)"
        was = ("had no section" if previous == ABSENT
               else "had it unset" if previous is None
               else "had it withdrawn" if previous == WITHDRAWN
               else f"announced {previous!r}")
        return False, (f"gates from {current} at {tag}, but the previous tag {was}"
                       " — a gate no release announced (design U5: announce once first)")
    return False, (f"announces {current}, which cannot be the next release after "
                   f"{tag} ({' / '.join(next_releases(tag))})")


# ------------------------------------------------------ single-file form ---

def literal(source: str):
    """`absent`, None (unset), or the declared string — VALIDATE_GATE_FROM only."""
    match = _LITERAL.search(source or "")
    if match is None:
        return ABSENT
    if match.group(1) == "None":
        return None
    return match.group(2) if match.group(2) is not None else match.group(3)


def verdict(tag_version: str, source: str, previous: str = "") -> tuple[bool, str]:
    """VALIDATE_GATE_FROM judged from two file texts (the form before v4.18)."""
    declared = literal(source)
    if declared == ABSENT:
        return True, "n/a — no VALIDATE_GATE_FROM in this tree (it predates the section)"
    return judge(VALIDATE, tag_version, declared, literal(previous))


# ------------------------------------------------------------- tree form ---

def _git(repo: str, *args: str) -> str:
    run = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if run.returncode not in (0, 1) or (run.returncode == 1 and run.stderr.strip()):
        raise RuntimeError(f"git {' '.join(args)}: {run.stderr.strip() or run.returncode}")
    return run.stdout


def collect_source(path: str, source: str) -> tuple[dict, list]:
    """The `*_GATE_FROM` assignments at module level in one file, and problems.

    Two readings that must agree: the parser (what Python binds) and a line
    scan of column-0 assignments (what a reader sees).
    """
    problems: list[str] = []
    found: dict = {}
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        return {}, [f"{path}: does not parse ({e.msg}, line {e.lineno})"]
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        for target in targets:
            if not (isinstance(target, ast.Name) and _NAME.match(target.id)):
                continue
            value_node = node.value
            if value_node is None:
                problems.append(f"{path}: {target.id} is declared without a value")
                continue
            try:
                value = ast.literal_eval(value_node)
            except ValueError:
                problems.append(f"{path}: {target.id} is not a literal — a gate version is "
                                "written, never computed")
                continue
            if value is not None and not isinstance(value, str):
                problems.append(f"{path}: {target.id} = {value!r} is neither a version string nor None")
                continue
            if target.id in found:
                problems.append(f"{path}: {target.id} is assigned twice")
            found[target.id] = value
    scanned = set(_LINE.findall(source))
    if scanned != set(found) and not problems:
        problems.append(f"{path}: the parser reads {sorted(found)} and the line scan reads "
                        f"{sorted(scanned)} — a gate constant one of them cannot see")
    if not _is_test(path):
        for name in sorted(set(_INDENTED.findall(source))):
            problems.append(f"{path}: {name} is assigned below module level — a gate literal "
                            "is written at column 0, where the tag gate reads it")
    return found, problems


def _is_test(path: str) -> bool:
    """Test files quote gate assignments in strings (fixtures); only shipped
    code is held to column 0."""
    parts = path.split("/")
    return "tests" in parts[:-1] or parts[-1].startswith("test_")


def collect(repo: str, ref: str) -> tuple[dict, list]:
    """Every `*_GATE_FROM` in *ref*'s tracked Python files: {name: (path, value)}."""
    problems: list[str] = []
    found: dict = {}
    listing = _git(repo, "grep", "-l", "-F", "_GATE_FROM", ref, "--", "*.py")
    for line in listing.splitlines():
        path = line.split(":", 1)[1] if line.startswith(f"{ref}:") else line
        source = _git(repo, "show", f"{ref}:{path}")
        names, file_problems = collect_source(path, source)
        problems += file_problems
        for name, value in names.items():
            if name in found:
                problems.append(f"{name} is assigned in {found[name][0]} and in {path} — "
                                "which one gates is ambiguous")
            found[name] = (path, value)
    control = _git(repo, "grep", "-c", "-F", VALIDATE, ref, "--", CONTROL_PATH)
    if control.strip() and VALIDATE not in found:
        problems.append(f"control: {CONTROL_PATH} names {VALIDATE} but the collector did not "
                        "find it — the collector is blind, not the tree empty")
    return found, problems


def check_tree(tag_version: str, repo: str, ref: str, previous_ref: str) -> tuple[bool, list]:
    lines: list[str] = []
    current, problems = collect(repo, ref)
    before, previous_problems = collect(repo, previous_ref)
    for problem in problems:
        lines.append(f"  FAIL {problem}")
    for problem in previous_problems:
        lines.append(f"  note (previous tag) {problem}")
    names = sorted(set(current) | {n for n, (_, v) in before.items() if isinstance(v, str)})
    ok = not problems
    for name in names:
        value = current[name][1] if name in current else ABSENT
        prev = before[name][1] if name in before else ABSENT
        good, why = judge(name, tag_version, value, prev)
        ok = ok and good
        where = current[name][0] if name in current else before[name][0]
        lines.append(f"  {'ok' if good else 'FAIL'} {name} ({where}): {why}")
    head = (f"{'ok' if ok else 'FAIL'} {len(current)} gate constant(s) in {ref}: "
            f"{', '.join(sorted(current)) or '(none)'}")
    return ok, [head] + lines


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def main(argv: list) -> int:
    if len(argv) >= 6 and argv[2] == "--repo":
        try:
            ok, lines = check_tree(argv[1], argv[3], argv[4], argv[5])
        except RuntimeError as e:
            print(f"FAIL the gate constants could not be read: {e}")
            return 1
        print("\n".join(lines))
        return 0 if ok else 1
    ok, why = verdict(argv[1], _read(argv[2]), _read(argv[3]) if len(argv) > 3 else "")
    print(("ok" if ok else "FAIL") + " " + why)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
