"""/api/slack/status and /api/slack/fetch (the Slack intake, design 2026-11-02 stage 1): a real `jui viz start` in a
temporary HOME on a free port, a slack.json with no workspace (so nothing reaches Slack). Both routes take the checks
of /api/prompt; the `slack` slice carries the same state; the page stores the slice without rebuilding the scene."""
from __future__ import annotations

import json

import pytest

from tests.test_viz_clock_out import DROP, Viz
from tests.test_viz_device_pane import _live_apply_rebuilds


@pytest.fixture()
def viz(tmp_path, monkeypatch):
    home = tmp_path / "home"
    for k in (*DROP, "JUI_VIZ_MANAGED_SETTINGS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(home))
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True)
    cfg = state / "slack.json"
    cfg.write_text(json.dumps({"orchestrationDir": str(tmp_path / "orch"), "schedule": {"everyHours": 0, "at": "09:00"},
                               "source": {"mode": "api", "workspaces": []},
                               "router": {"anthropicApiKey": "ant-key-QQ8", "prompt": {"projects": {"shop": "x"}}}}))
    cfg.chmod(0o600)
    v = Viz(home)
    v.orch = tmp_path / "orch"
    try:
        yield v
    finally:
        v.stop()


def _post(viz, path, **over):
    status, text = viz.raw("POST", path, viz.page_headers(**over), b"{}")
    return status, (json.loads(text) if text.strip().startswith("{") else text)


def test_status_and_fetch_now_with_the_page_checks(viz):
    status, got = _post(viz, "/api/slack/status")
    assert status == 200 and got["configured"] is True and got["mode"] == "api" and got["nextRun"] is None
    assert got["counts"] == {"inbox": 0, "projects": {}, "unsorted": 0} and "ant-key-QQ8" not in json.dumps(got)
    status, got = _post(viz, "/api/slack/fetch")
    assert status == 202 and got == {"started": True}
    viz.wait(lambda: (viz.snapshot()["slices"].get("slack") or {}).get("lastRun"), "the fetch's lastRun in the slice")
    sl = viz.snapshot()["slices"]["slack"]
    assert sl["lastRun"]["trigger"] == "manual" and sl["lastRun"]["fetched"] == 0 and sl["running"] is False
    assert (viz.orch / "inbox").is_dir() and (viz.orch / ".state" / "status.json").is_file()


@pytest.mark.parametrize("over,code", [({"Origin": "http://evil.example"}, 403), ({"X-Jui-Viz-Token": "wrong"}, 401),
                                       ({"Content-Type": "text/plain"}, 415)])
def test_each_page_check_refuses_on_its_own(viz, over, code):
    for path in ("/api/slack/status", "/api/slack/fetch"):
        assert _post(viz, path, **over)[0] == code
    assert not (viz.orch / ".state" / "status.json").exists() or "lastRun" not in json.loads((viz.orch / ".state" / "status.json").read_text())


def test_a_get_is_refused(viz):
    assert viz.raw("GET", "/api/slack/fetch", viz.page_headers(), None)[0] == 405


def test_a_push_of_the_slack_slice_alone_rebuilds_nothing():
    got = _live_apply_rebuilds([({"slack": {"configured": True}}, False), ({"slack": {}, "sessions": []}, False)])
    assert [g[0] for g in got] == [0, 1]
