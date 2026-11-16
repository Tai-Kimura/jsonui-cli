"""`jsonui-doc check --json` (ticket 2026-10-21-agents-skills-mcp-for-server-room §3a-2): stdout is one JSON object —
each check's status, counts, the results that are not ok, its report's path — and the lines the terminal shows
(each command printed before it runs among them) go to stderr. The exit code is the same as without it."""
from __future__ import annotations

import json
import subprocess
import sys

from test_infra_check import _project
from test_infra_load import TOOLS

GATED = [{"name": "infra-iac", "type": "builtin:infra-iac", "gate": True},
         {"name": "infra-code", "type": "builtin:infra-code", "gate": True}]   # a finding is a mismatch, not a warning


def _check(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "check", *args], cwd=TOOLS,
                          capture_output=True, text=True)


def test_the_checks_as_one_json_object_and_the_terminal_lines_on_stderr(tmp_path):
    root = _project(tmp_path, GATED)
    plain = _check("-p", str(root))
    got = _check("-p", str(root), "--json")
    out = json.loads(got.stdout)
    assert got.returncode == plain.returncode == out["exit"] == 1 and out["ok"] is False
    assert [(c["name"], c["type"], c["status"]) for c in out["checks"]] == [
        ("infra-iac", "builtin:infra-iac", "mismatch"), ("infra-code", "builtin:infra-code", "mismatch")]
    iac = out["checks"][0]
    assert iac["report"].endswith("docs/infra/.check-report.infra-iac.json")
    saved = json.loads((root / "docs/infra/.check-report.infra-iac.json").read_text())
    assert iac["results"] == [r for r in saved["results"] if r["status"] != "ok"] and iac["summary"] == saved["summary"]
    assert "▶ infra-iac  [builtin:infra-iac]" in got.stderr and "▶" not in got.stdout
    assert plain.stdout.splitlines()[0] == got.stderr.splitlines()[0]


def test_warnings_only_are_ok_as_without_json(tmp_path):
    root = _project(tmp_path)                                                   # not gated: findings are warnings
    got = _check("-p", str(root), "--json")
    out = json.loads(got.stdout)
    assert got.returncode == _check("-p", str(root)).returncode == 0 and out["ok"] is True
    assert {c["status"] for c in out["checks"]} == {"ok"} and any(c["results"] for c in out["checks"])


def test_list_and_no_match_are_json_too(tmp_path):
    root = _project(tmp_path)
    listed = _check("-p", str(root), "--list", "--json")
    assert listed.returncode == 0 and json.loads(listed.stdout)["selected"] == [
        {"name": "infra-iac", "type": "builtin:infra-iac"}, {"name": "infra-code", "type": "builtin:infra-code"}]
    none = _check("nothing-like-this", "-p", str(root), "--json")
    out = json.loads(none.stdout)
    assert none.returncode == 2 and out["exit"] == 2 and out["checks"] == [] and len(out["declared"]) == 2
