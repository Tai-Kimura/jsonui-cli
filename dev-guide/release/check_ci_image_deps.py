#!/usr/bin/env python3
"""Check the python CI job's SVG dependencies, including its cached apt installer.

The release runner used to require one literal apt-get line. CI now builds a package list and installs it through
apt_install_cached.sh, so that check reported missing dependencies while CI actually installed and exercised them.
Only executable step bodies count: a comment or a different job cannot stand in for the python suite's setup.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


def missing(workflow: dict) -> list[str]:
    steps = workflow.get("jobs", {}).get("python-suite", {}).get("steps", [])
    bodies = ["\n".join(line for line in step.get("run", "").splitlines() if not line.lstrip().startswith("#"))
              for step in steps if isinstance(step, dict)]
    shell = "\n".join(bodies)
    apt = re.search(r"\bapt-get\s+install\b[^\n]*\blibrsvg2-bin\b", shell)
    if not apt:
        # The list step publishes its packages, and the install step consumes that exact output.
        for step in steps:
            ident = step.get("id") if isinstance(step, dict) else None
            body = step.get("run", "") if isinstance(step, dict) else ""
            if not ident or not re.search(r'^\s*pkgs="librsvg2-bin(?:\s|"|$)', body, re.M):
                continue
            if 'packages=$pkgs' in body:
                apt = any("bash .github/scripts/apt_install_cached.sh" in b
                          and "steps." + ident + ".outputs.packages" in b for b in bodies)
    cairo = re.search(r"(?:^|\n)\s*(?:python3?\s+-m\s+)?pip\s+install\b[^\n]*\bcairosvg\b", shell)
    return (["librsvg2-bin"] if not apt else []) + (["cairosvg"] if not cairo else [])


def main() -> int:
    absent = missing(yaml.safe_load(Path(sys.argv[1]).read_text()) or {})
    if absent:
        print("python-suite does not install: " + ", ".join(absent), file=sys.stderr)
    return int(bool(absent))


if __name__ == "__main__":
    raise SystemExit(main())
