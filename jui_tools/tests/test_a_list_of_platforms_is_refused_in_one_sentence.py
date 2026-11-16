"""A `platforms` jui cannot read is refused in one sentence, not a traceback.

`jui init` writes `platforms` as an object keyed by platform name, each entry
carrying a `root`. The sibling test tools also accept a bare list of names, so
a project whose config said `"platforms": ["web"]` worked with `jsonui-test`
and died in `jui g project` with `AttributeError: 'list' object has no
attribute 'items'` (generate_cmd `_resolve_platforms`), and the same way in
`jui build` (ConfigManager `_platform_config`), `jui verify` and `jui
sync_tool` (measured 2026-09-28 on v1.9.0 and v1.8.120).

Reading the list as names would not have been enough: jui resolves every path
against each platform's `root`, and `{"web": {}}` crashed the same commands
with `KeyError: 'root'`. Both shapes are refused by `ConfigManager.load()` and
reported at the CLI entry as one `ERROR:` line naming the key and the shape
`jui init` writes, with exit 1.

The arms run the real launcher in fresh interpreters (`-I -S`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jui_cli.core.config_manager import ConfigManager, ConfigShapeError

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "jui_tools" / "bin" / "jui"

COMMANDS = [
    ["g", "project", "--file", "counter.spec.json", "--web-only"],
    ["g", "project", "--file", "counter.spec.json"],
    ["build"],
    ["verify"],
    ["sync_tool"],
]
IDS = ["g project --web-only", "g project", "build", "verify", "sync_tool"]


def _project(root: Path, platforms) -> Path:
    spec_dir = root / "docs/screens/json"
    spec_dir.mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps({
        "project_name": "MyApp", "spec_directory": "docs/screens/json",
        "layouts_directory": "docs/screens/layouts", "platforms": platforms}))
    (spec_dir / "counter.spec.json").write_text(json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Counter", "displayName": "Counter", "description": "A counter."},
        "structure": {
            "components": [
                {"type": "View", "id": "counter_root", "description": "root"},
                {"type": "Label", "id": "count_label", "description": "shows the count"}],
            "layout": {"root": "counter_root", "children": ["count_label"]}},
        "stateManagement": {"states": [], "uiVariables": [
            {"name": "count", "type": "Int", "defaultValue": "5", "description": "the count"}],
            "eventHandlers": [], "displayLogic": []},
        "dataFlow": {"viewModel": {"methods": [], "vars": []}}}))
    return root


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-S", str(LAUNCHER), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=300)


@pytest.mark.parametrize("command", COMMANDS, ids=IDS)
def test_a_list_of_platform_names_is_refused_naming_the_key(tmp_path, command):
    run = _run(_project(tmp_path, ["web"]), *command)
    out = run.stdout + run.stderr
    assert run.returncode == 1, out
    assert ('`platforms` must be an object like {"web": {"root": "web"}} as written '
            'by `jui init`; got a list (["web"]).') in out, out
    assert "Traceback" not in out and "AttributeError" not in out, out


@pytest.mark.parametrize("command", COMMANDS, ids=IDS)
def test_a_platform_without_root_is_refused_naming_the_key(tmp_path, command):
    run = _run(_project(tmp_path, {"web": {}}), *command)
    out = run.stdout + run.stderr
    assert run.returncode == 1, out
    assert "`platforms.web` has no `root`" in out, out
    assert "Traceback" not in out and "KeyError" not in out, out


def test_control_the_shape_jui_init_writes_generates(tmp_path):
    project = _project(tmp_path, {"web": {"root": "web", "layoutsDir": "src/Layouts"}})
    run = _run(project, "g", "project", "--file", "counter.spec.json", "--web-only")
    out = run.stdout + run.stderr
    assert run.returncode == 0, out
    assert "`platforms`" not in out and "Traceback" not in out, out
    assert (project / "docs/screens/layouts/counter.json").exists(), out


@pytest.mark.parametrize("platforms, fragment", [
    (["web", "ios"], "got a list"),
    ("web", "got a string"),
    (None, "got null"),
    ({"web": "web"}, "`platforms.web` must be an object with a `root`"),
    ({"web": {"root": ""}}, "`platforms.web` has no `root`"),
])
def test_load_refuses_each_unreadable_shape(tmp_path, platforms, fragment):
    path = tmp_path / "jui.config.json"
    path.write_text(json.dumps({"platforms": platforms}))
    with pytest.raises(ConfigShapeError) as exc:
        ConfigManager(path).load()
    assert fragment in str(exc.value)


@pytest.mark.parametrize("config", [{}, {"platforms": {}},
                                    {"platforms": {"ios": {"root": "ios"}}}])
def test_load_accepts_an_absent_empty_or_rooted_platforms(tmp_path, config):
    path = tmp_path / "jui.config.json"
    path.write_text(json.dumps(config))
    assert ConfigManager(path).load() == config
