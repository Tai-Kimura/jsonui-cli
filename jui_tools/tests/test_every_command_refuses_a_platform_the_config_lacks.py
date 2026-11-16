"""Every command that takes a platform by name refuses one the config lacks.

jsonui-cli 1.9.9 made `jui build` and `jui sync_tool` say so (ticket
jui-platform-asked-by-name-and-absent-from-config-exits-0). The rest did not:
with a config that has web only and a top-level layouts_directory,
`jui verify --platform ios` verified every screen as "skipped (layout not
found on disk)" and exited 0; `g project --ios-only` generated nothing and
exited 0; `g api --platform ios` and `ls api-models --platform ios` exited 0
(ticket jui-verify-and-others-platform-asked-by-name-absent-exits-0).

They now share one sentence (config_manager.absent_platform_message). The
last arm counts the commands: a jui_cli command module that declares a
platform-naming argument and does not call the helper fails here, so a new
command cannot repeat this.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
LAUNCHER = TOOLS / "bin" / "jui"
COMMANDS_DIR = TOOLS / "jui_cli" / "commands"

SPEC = {
    "type": "screen_spec", "version": "1.0",
    "metadata": {"name": "Counter", "displayName": "Counter", "description": "A counter."},
    "structure": {
        "components": [{"type": "View", "id": "counter_root", "description": "root"},
                       {"type": "Label", "id": "count_label", "description": "shows the count"}],
        "layout": {"root": "counter_root", "children": ["count_label"]}},
    "stateManagement": {"states": [], "uiVariables": [], "eventHandlers": [], "displayLogic": []},
    "dataFlow": {"viewModel": {"methods": [], "vars": []}},
}

# Each command with a platform named on it: `{p}` is ios for the arms, web for the boundary.
COMMANDS = [
    ("verify", "--platform", "{p}"),
    ("g", "project", "--file", "counter.spec.json", "--{p}-only"),
    ("g", "api", "--dry-run", "--platform", "{p}"),
    ("ls", "api-models", "--platform", "{p}"),
    ("migrate-layouts", "--from", "{p}", "--dry-run"),
]
IDS = ["verify", "g project", "g api", "ls api-models", "migrate-layouts"]


def _project(root: Path, platforms) -> Path:
    # The reporter's shape: a top-level layouts_directory beside the platforms.
    (root / "docs/screens/json").mkdir(parents=True)
    (root / "docs/screens/layouts").mkdir(parents=True)
    (root / "web/src/Layouts").mkdir(parents=True)
    config = {"project_name": "MyApp", "spec_directory": "docs/screens/json",
              "layouts_directory": "docs/screens/layouts"}
    if platforms is not None:
        config["platforms"] = platforms
    (root / "jui.config.json").write_text(json.dumps(config))
    (root / "docs/screens/json/counter.spec.json").write_text(json.dumps(SPEC))
    return root


def _run(cwd: Path, command, platform: str) -> tuple[int, str]:
    args = [a.format(p=platform) for a in command]
    run = subprocess.run([sys.executable, "-I", "-S", str(LAUNCHER), *args],
                         cwd=cwd, capture_output=True, text=True, timeout=300)
    return run.returncode, run.stdout + run.stderr


WEB_ONLY = {"web": {"root": "web", "layoutsDir": "src/Layouts"}}


@pytest.mark.parametrize("command", COMMANDS, ids=IDS)
def test_a_web_only_config_refuses_ios_naming_the_config_and_its_platforms(tmp_path, command):
    rc, out = _run(_project(tmp_path, WEB_ONLY), command, "ios")
    assert rc == 1, out
    assert (f"ios was asked for, and {tmp_path / 'jui.config.json'} has no such platform "
            "(its platforms: web).") in out, out


@pytest.mark.parametrize("command", COMMANDS, ids=IDS)
def test_a_config_without_platforms_refuses_ios(tmp_path, command):
    rc, out = _run(_project(tmp_path, None), command, "ios")
    assert rc == 1, out
    assert "ios was asked for" in out and "(its platforms: none)" in out, out


@pytest.mark.parametrize("command", COMMANDS[:4], ids=IDS[:4])
def test_boundary_the_platform_the_config_has_is_not_refused(tmp_path, command):
    # migrate-layouts is left out: copying from web needs a web Layouts tree,
    # which is not what this arm asks.
    rc, out = _run(_project(tmp_path, WEB_ONLY), command, "web")
    assert "was asked for" not in out, out
    assert rc == 0, out


def test_every_command_that_names_a_platform_calls_the_one_helper():
    # Declares `--platform`, `--X-only` or `--from` with the platform choices.
    names_a_platform = re.compile(r'"--platform"|"--(ios|android|web)-only"|dest="source_platform"')
    # conformance's --platform is a conformance face, not a config platform
    # (conformance_cmd does not read jui.config.json).
    exempt = {"conformance_cmd.py"}
    declaring = sorted(p.name for p in COMMANDS_DIR.glob("*.py")
                       if names_a_platform.search(p.read_text(encoding="utf-8")))
    assert declaring, "the census found no command at all — the pattern is broken"
    missing = [n for n in declaring if n not in exempt
               and "absent_platform_message" not in (COMMANDS_DIR / n).read_text(encoding="utf-8")]
    assert missing == [], f"these commands name a platform without the shared check: {missing}"
    print("commands that name a platform:", declaring)
