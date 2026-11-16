"""A test hands node its script on stdin (`node -`, input=), never as an argument.

Linux caps one argument at 131072 bytes (MAX_ARG_STRLEN) and macOS caps them all at ARG_MAX: a script carrying the
words' table (two languages, 2.3.15) passed the first, and the release's CI stopped with "Argument list too long" on a
test that passed here (docs/bugs/2026-10-21-viz-tests-node-script-argument-too-long.md)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

TESTS = Path(__file__).resolve().parent
#: over both caps on any machine: Linux's per argument (128 KiB) and this machine's whole list (ARG_MAX)
BIG = max(1 << 21, os.sysconf("SC_ARG_MAX") + (1 << 16))


def test_a_script_far_over_the_argument_caps_runs_on_stdin():
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it)"
    pad = "// " + "x" * 1000 + "\n"
    script = pad * (BIG // len(pad) + 1) + "process.stdout.write(JSON.stringify({ ok: true, n: 2 + 2 }));"
    assert len(script.encode()) > 200_000
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout == '{"ok":true,"n":4}'


def test_no_test_hands_node_its_script_as_an_argument():
    """The family, closed: every node call in the tests reads its script on stdin (node -e / --eval / -p none)."""
    found = [f"{p.name}:{i}" for p in sorted(TESTS.glob("*.py")) if p.name != Path(__file__).name
             for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if re.search(r"\[\s*node\s*,\s*[\"'](?:-e|--eval|-p|--print)[\"']", line)]
    assert found == []
