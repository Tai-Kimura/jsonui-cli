"""run-suites.sh's "python suites at the next stamp" leg, and its two parts.

Raised to 1.8.121 on a copy, test_tools went 16 red, and nothing had run it
there before the stamp's own CI (2026-09-26): the *_GATE_FROM literals switch
behaviour by the running VERSION. The leg runs the python suites on a clone
raised to the next patch when that patch switches a gate on (4f's ruling (b)).
  next_stamp_plan.py   which literals the next patch switches on — read by the
                       tag gate's own collector, never a list
  raise_stamp.py       the runbook's stamp predicate, applied to a clone
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RELEASE = REPO / "dev-guide" / "release"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_leg_{name}", RELEASE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _needs_git():
    if not (REPO / ".git").exists():
        pytest.skip("not a git checkout: the collector and the stamp predicate read tracked files")


def _version():
    return (REPO / "VERSION").read_text(encoding="utf-8").strip()


def test_the_plan_reads_what_the_tag_gate_collects():
    _needs_git()
    plan, tag_gate = _load("next_stamp_plan"), _load("validate_gate_version")
    cur, nxt, found, _, problems = plan.plan(str(REPO))
    assert cur == _version() and nxt == tag_gate.next_patch(cur)
    collected, _ = tag_gate.collect(str(REPO), "HEAD")
    assert found == collected and not problems


def test_a_literal_crosses_at_its_own_release_and_not_after():
    """Both sides of the boundary, from a literal this tree carries: at the
    patch before it the next patch switches it on; at it, it is already on."""
    _needs_git()
    plan = _load("next_stamp_plan")
    _, _, found, _, _ = plan.plan(str(REPO))
    releases = {v for _, v in found.values() if isinstance(v, str) and v.count(".") == 2 and v.split(".")[2] != "0"}
    if not releases:
        pytest.skip("no *_GATE_FROM in this tree names a patch release")
    gate = sorted(releases)[0]
    before = ".".join(gate.split(".")[:2] + [str(int(gate.split(".")[2]) - 1)])
    names = {n for n, (_, v) in found.items() if v == gate}
    _, nxt, _, crossing, _ = plan.plan(str(REPO), current=before)
    assert nxt == gate and {n for n, _, _ in crossing} >= names
    _, _, _, crossing, _ = plan.plan(str(REPO), current=gate)
    assert not names & {n for n, _, _ in crossing}


def _stamp_list(repo: Path):
    run = subprocess.run([sys.executable, str(RELEASE / "raise_stamp.py"), str(repo), "0.0.0", "--list"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    return [line for line in run.stdout.splitlines() if " -> " in line and not line.startswith("would")]


def test_the_stamp_predicate_finds_every_file_lockstep_holds():
    _needs_git()
    lines = _stamp_list(REPO)
    files = {line.split(":", 1)[0] for line in lines}
    assert {"VERSION", "rjui_tools/VERSION", "sjui_tools/lib/cli/version.rb",
            "kjui_tools/lib/cli/version.rb"} <= files, files
    assert all(_version() in line.split(" -> ")[0] for line in lines), lines


def test_raising_a_clone_leaves_no_stamp_line_behind(tmp_path):
    _needs_git()
    clone = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--no-tags", f"file://{REPO}", str(clone)], check=True)
    before = _stamp_list(clone)
    run = subprocess.run([sys.executable, str(RELEASE / "raise_stamp.py"), str(clone), "9.9.9"],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    subprocess.run(["git", "-C", str(clone), "-c", "user.name=t", "-c", "user.email=t@localhost",
                    "commit", "-qam", "raise"], check=True)
    assert (clone / "VERSION").read_text(encoding="utf-8").strip() == "9.9.9"
    after = _stamp_list(clone)            # the predicate at 9.9.9: the same lines, raised
    assert len(after) == len(before) and all("9.9.9" in line.split(" -> ")[0] for line in after)
    assert "VERSION = '9.9.9'" in (clone / "sjui_tools/lib/cli/version.rb").read_text(encoding="utf-8")


def test_run_suites_runs_the_leg_and_says_what_it_skips():
    text = (RELEASE / "run-suites.sh").read_text(encoding="utf-8")
    assert 'next_stamp_plan.py" "$C"' in text and 'raise_stamp.py" "$STAMPED/repo"' in text
    assert "skipped: no gate literal at $next_version" in text
    assert "blind spot:" in text
    assert "py_suite test_tools jsonui_test_cli" in text.split("python suites at the next stamp", 1)[1]
