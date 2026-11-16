#!/usr/bin/env python3
"""Refuse code that signals a process this repo's tools did not start.

THE PROPERTY, AND WHY THE CHECK IS ONLY AN APPROXIMATION OF IT.

What must not ship is a tool that ends a process it does not own. It cannot
tell whether it owns one unless it started it and kept the pid: a name, a
port, or a `ps` line identifies a process, never its owner. These tools are
vendored into every consumer, so a sweep here runs on a machine where other
people's work is running — on 2026-09-03 an outside SIGTERM mid-run turned a
consumer's E2E suite red three times.

That property is not decidable by reading source. What follows is a list of
SPELLINGS that have meant it in practice. The list is the approximation, not
the rule, and it is expected to grow: when a new spelling turns up, the right
response is to add it here, not to conclude the code is fine because the
check was silent.

The list already grew once, which is the reason this file exists. The first
guard (jsonui-cli 1.8.21) matched `pkill|killall` — the spelling that had
just been removed from `rjui hotload stop`. Consumers then found four lines
of the same harm keyed on a port instead of a name:

    lsof -nP -iTCP:$PORT -sTCP:LISTEN -t | xargs kill

The guard was silent on all four, and so was an audit that asked every lane
"do you have a name-matching kill?" and collected zeroes: the question named
a spelling, so the answers were about that spelling, and the denominator
closed on four lines that existed.

WHAT PASSES, DELIBERATELY: killing a pid you recorded yourself —
`kill "$MY_PID"`, `kill $(cat run.pid)`, `Process.kill('TERM', pid)`. That is
the shape that knows what it owns, and the whole point of the rule is to
leave it available.

THIS FILE EXCLUDES ITSELF. It has to name the spellings it hunts, so it
matches itself by construction. What checks it instead is its test suite
(jui_tools/tests/test_unowned_kill_guard.py), which plants each spelling and
asserts the flag fires — the check a silent guard cannot pass. The first
version of the 1.8.21 guard could not fire at all (`\\b` is a GNU extension
that git's POSIX matcher does not implement) and only planting found it.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: Paths whose content is about this rule rather than subject to it.
SELF_EXCLUDED = (
    "dev-guide/ci/check-unowned-kills.py",
    "jui_tools/tests/test_unowned_kill_guard.py",
    ".github/workflows/ci.yml",
)

#: File kinds a tool's executable text lives in. `package.json` is included
#: because an npm `scripts` entry is a shell command like any other — the
#: consumer lines that prompted this lived in exactly that kind of place.
TRACKED_GLOBS = ("*.rb", "*.py", "*.sh", "*.bash", "*.zsh", "*.mjs", "*.js", "*.ts", "*package.json")

_KILL = re.compile(r"(?<![\w./-])kill(?![\w-])")
_NAME_SWEEP = re.compile(r"(?<![\w./-])(pkill|killall)(?![\w-])")
_FUSER_KILL = re.compile(r"(?<![\w./-])fuser(?![\w-])[^;&|]*?(-k\b|--kill\b)")
#: Commands that FIND processes belonging to whoever happens to be running.
_DISCOVERY = re.compile(r"(?<![\w./-])(lsof|pgrep|ps)(?![\w-])")
_XARGS = re.compile(r"(?<![\w./-])xargs(?![\w-])")


def is_comment(line: str) -> bool:
    """A line that only talks about this. Saying why we do not do it must
    stay possible, or the rule forbids its own explanation."""
    stripped = line.lstrip()
    return stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*")


def flag(line: str) -> str | None:
    """Why this line signals a process it does not own, or None."""
    if is_comment(line):
        return None
    if _NAME_SWEEP.search(line):
        return "kills by process NAME (a name does not identify an owner)"
    if _FUSER_KILL.search(line):
        return "kills whatever holds a PORT (fuser -k)"
    if _KILL.search(line):
        if _DISCOVERY.search(line):
            return "kills a pid found by a LOOKUP (lsof / pgrep / ps), not one it started"
        if _XARGS.search(line):
            return "kills pids piped in from a lookup (xargs)"
    return None


def tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", *TRACKED_GLOBS],
        capture_output=True, text=True, check=True,
    ).stdout
    return [root / p for p in out.split("\0") if p and p not in SELF_EXCLUDED]


def scan(root: Path) -> list[tuple[str, int, str, str]]:
    hits: list[tuple[str, int, str, str]] = []
    for path in tracked_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            why = flag(line)
            if why:
                hits.append((str(path.relative_to(root)), number, line.strip(), why))
    return hits


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[2]
    hits = scan(root)
    if not hits:
        print("no unowned-process kills in tracked tool sources")
        return 0
    print("::error::these end a process the tool did not start "
          "(use a pid you recorded yourself):")
    for rel, number, line, why in hits:
        print(f"  {rel}:{number}: {line}")
        print(f"      -> {why}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
