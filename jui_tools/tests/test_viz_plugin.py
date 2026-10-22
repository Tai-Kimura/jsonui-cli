"""The jui-viz Claude Code plugin (plugins/jui-viz) and its marketplace (.claude-plugin/).

The plugin carries copies of forward.py and channel.py, because a plugin only
ships its own folder. These arms keep the copies, the hooks and the events in
step with jui_cli/viz, so a fix there cannot miss the plugin.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jui_cli.viz import hooks_installer as hi
from jui_cli.viz import paths
from jui_cli.viz.config import ASK_WAIT_CHOICES, VizConfig, ask_hook_wait_sec

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "jui-viz"
VIZ = REPO / "jui_tools" / "jui_cli" / "viz"


@pytest.mark.parametrize("name", ["forward.py", "channel.py"])
def test_the_plugins_scripts_are_byte_identical_to_the_packages(name):
    assert (PLUGIN / "scripts" / name).read_bytes() == (VIZ / name).read_bytes()


def test_the_plugin_hooks_cover_the_same_events_as_the_installer():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(hooks) == set(hi.EVENTS)
    for event in hi.EVENTS:
        first = hooks[event][0]
        assert ("matcher" in first) == (event in hi.TOOL_EVENTS), event
        (handler,) = first["hooks"]
        assert handler["async"] is True and handler["args"][-1].endswith("/scripts/forward.py"), event
    decide = [h for g in hooks["PermissionRequest"] for h in g["hooks"] if h.get("args", [])[-1:] == ["--decide"]]
    assert len(decide) == 1 and "async" not in decide[0] and decide[0]["timeout"] == hi.DECIDE_TIMEOUT_SEC
    ask = [h for g in hooks["PreToolUse"] if g.get("matcher") == "AskUserQuestion" for h in g["hooks"]]
    assert len(ask) == 1 and ask[0]["args"][-1] == "--ask" and "async" not in ask[0]
    # ticket 2026-10-20 question-window-over-5-min: the plugin's --ask timeout is the installer's, over every window
    assert ask[0]["timeout"] == hi.ASK_TIMEOUT_SEC
    longest = max(ask_hook_wait_sec(VizConfig(askWaitSec=c)) for c in ASK_WAIT_CHOICES)
    assert ask[0]["timeout"] >= longest + 5 and hi.ASK_TIMEOUT_SEC >= longest + 5
    # 2.3.20, the page's 停止: one synchronous --stop item on PreToolUse and PostToolUse, the installer's timeout
    for event in hi.STOP_EVENTS:
        stop = [h for g in hooks[event] if g.get("matcher") == "*" for h in g["hooks"] if h.get("args", [])[-1:] == ["--stop"]]
        assert len(stop) == 1 and "async" not in stop[0] and stop[0]["timeout"] == hi.STOP_TIMEOUT_SEC, event
    assert [e for e in hooks if any(h.get("args", [])[-1:] == ["--stop"] for g in hooks[e] for h in g["hooks"])] == list(hi.STOP_EVENTS)
    env = [h for g in hooks["SessionStart"] for h in g["hooks"] if "session_env.sh" in h.get("command", "")]
    assert len(env) == 1
    script = (PLUGIN / "scripts" / "session_env.sh").read_text()
    assert "CLAUDE_ENV_FILE" in script and hi.PROGRESS_ENV in script and "/test-progress" in script
    assert ".jsonui-cli" not in script  # the install folder is replaced by every bootstrap (test_viz_state_home.py runs it)


def test_the_manifest_binds_the_channel_and_the_marketplace_lists_the_plugin():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "jui-viz"
    assert manifest["channels"] == [{"server": "jui-viz", "displayName": "jui viz"}]
    assert manifest["mcpServers"]["jui-viz"]["args"][-1] == "${CLAUDE_PLUGIN_ROOT}/scripts/channel.py"
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert market["name"] == "jsonui"
    (entry,) = market["plugins"]
    assert entry["name"] == "jui-viz" and (REPO / entry["source"]).resolve() == PLUGIN.resolve()
    assert hi.PLUGIN_PREFIX == f"{manifest['name']}@"


def test_hooks_install_refuses_when_the_plugin_is_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    paths.claude_settings().parent.mkdir(parents=True)
    paths.claude_settings().write_text(json.dumps({"enabledPlugins": {"jui-viz@jsonui": True}}))
    with pytest.raises(hi.SettingsError, match="twice"):
        hi.install(python="/work/py")
    assert json.loads(paths.claude_settings().read_text()) == {"enabledPlugins": {"jui-viz@jsonui": True}}
    assert hi.status()["plugin"] == "jui-viz@jsonui"
    paths.claude_settings().write_text(json.dumps({"enabledPlugins": {"jui-viz@jsonui": False}}))
    assert hi.install(python="/work/py").changed  # disabled: the installer is the way in
