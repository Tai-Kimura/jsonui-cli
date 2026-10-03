"""A platform asked for by name that the config read does not have is an ERROR.

Until jsonui-cli 1.9.9 `jui build --platform ios` built nothing and said
"Build completed successfully — 0 tracked generated file(s)", rc 0, when the
config it found had no ios; `jui sync_tool --platform ios` said "nothing to
sync", rc 0, when that config had no platforms at all (its own "not in" check
sat after that early return). The case that hit it: a submodule extracted
empty, where jui walks up to the superproject's docs-only config (ticket
jui-platform-asked-by-name-and-absent-from-config-exits-0).

The boundary: the same command against a config that HAS the platform stays
green, and a run that names no platform keeps "nothing to sync".
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / "bin" / "jui"
ASKED = "ERROR: ios was asked for"


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-S", str(LAUNCHER), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=300)


def _superproject_with_an_empty_submodule(root: Path) -> Path:
    # The superproject's own config is for docs checks only: no platforms.
    (root / "jui.config.json").write_text(json.dumps({"_comment": "docs only", "checks": []}))
    sub = root / "bar"
    sub.mkdir()
    return sub


@pytest.mark.parametrize("args", [("build", "--platform", "ios"), ("build", "--ios-only")],
                         ids=["build --platform ios", "build --ios-only"])
def test_build_of_a_platform_the_config_lacks_fails_naming_the_config(tmp_path, args):
    run = _run(_superproject_with_an_empty_submodule(tmp_path), *args)
    out = run.stdout + run.stderr
    assert run.returncode == 1, out
    assert f"{ASKED}, and {tmp_path / 'jui.config.json'} has no such platform (its platforms: none)" in out, out
    assert "jui walked up to it" in out, out
    assert "Build completed successfully" not in out, out


def test_sync_tool_of_a_platform_the_config_lacks_fails_before_nothing_to_sync(tmp_path):
    run = _run(_superproject_with_an_empty_submodule(tmp_path), "sync_tool", "--platform", "ios")
    out = run.stdout + run.stderr
    assert run.returncode == 1, out
    assert f"platform 'ios' not in {tmp_path / 'jui.config.json'} (its platforms: none)" in out, out
    assert "nothing to sync" not in out, out


def test_a_config_with_other_platforms_names_them_and_says_nothing_about_walking_up(tmp_path):
    (tmp_path / "jui.config.json").write_text(json.dumps(
        {"project_name": "MyApp", "platforms": {"web": {"root": "web"}}}))
    run = _run(tmp_path, "build", "--platform", "ios")
    out = run.stdout + run.stderr
    assert run.returncode == 1, out
    assert "(its platforms: web)" in out, out
    assert "walked up" not in out, out


def test_boundary_the_same_ask_against_a_config_that_has_it_stays_green(tmp_path):
    (tmp_path / "web" / "src" / "Layouts").mkdir(parents=True)  # what `rjui init` makes
    (tmp_path / "jui.config.json").write_text(json.dumps(
        {"project_name": "MyApp", "platforms": {"web": {"root": "web"}}}))
    run = _run(tmp_path, "build", "--platform", "web")
    out = run.stdout + run.stderr
    assert run.returncode == 0, out
    assert "was asked for" not in out, out


def test_boundary_naming_no_platform_keeps_nothing_to_sync(tmp_path):
    run = _run(_superproject_with_an_empty_submodule(tmp_path), "sync_tool")
    out = run.stdout + run.stderr
    assert run.returncode == 0, out
    assert "nothing to sync" in out, out


def test_boundary_sync_tool_of_ios_against_a_config_that_has_ios_stays_green(tmp_path):
    # ios itself, on the command whose check moved: a dry run from this tree.
    (tmp_path / "ios").mkdir()
    (tmp_path / "jui.config.json").write_text(json.dumps(
        {"project_name": "MyApp", "platforms": {"ios": {"root": "ios"}}}))
    source = LAUNCHER.resolve().parents[2]
    run = _run(tmp_path, "sync_tool", "--platform", "ios", "--dry-run", "--from", str(source))
    out = run.stdout + run.stderr
    assert run.returncode == 0, out
    assert "not in" not in out, out
    assert "DRY RUN" in out, out
