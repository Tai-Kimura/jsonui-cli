"""Devices and per-case test progress (jui viz P7, jsonui-cli side)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

from jui_cli.viz.ingest import World
from jui_cli.viz.sources import devices, test_progress as tp
from jui_cli.viz.state import VizState

SCHEMA = Path(__file__).resolve().parents[2] / "test_tools" / "tests" / "schema_fixtures" / "progress.schema.json"
RUN = "0f8f8f8f-1111-4222-8333-444455556666"


def _rec(event, **kw):
    base = {"v": 1, "t": 1_000, "platform": "ios", "run": RUN, "event": event}
    return {**base, **kw}


def test_the_hand_written_rules_name_the_schemas_keys():
    """The authority is the vendored schema: per event, the allowed and required
    keys read from the file must equal the validator's. Changing either side
    alone turns this red."""
    schema = json.loads(SCHEMA.read_text())
    assert set(schema["properties"]["event"]["enum"]) == set(tp.KEYS)
    for branch in schema["allOf"]:
        event = branch["if"]["properties"]["event"]["const"]
        allowed = set(branch["then"]["propertyNames"]["enum"])
        required = set(schema["required"]) | set(branch["then"]["required"])
        assert allowed == tp.KEYS[event], event
        assert required == tp.REQUIRED[event], event
    assert schema["properties"]["file"]["maxLength"] == tp.NAME_MAX
    assert schema["properties"]["platform"]["enum"] == list(tp.PLATFORMS)
    assert schema["properties"]["run"]["pattern"] == tp.RUN_ID.pattern


@pytest.mark.parametrize("rec,ok", [
    (_rec("run_start", files=3, device="iPhone 16"), True),
    (_rec("case_start", file="screens/a.test.json", test="a", case="c1", attempt=1), True),
    (_rec("case_end", file="f", test="a", case="c1", attempt=1, status="passed", durationMs=12.5), True),
    (_rec("case_end", file="f", test="a", case="c1", attempt=0, status="skipped", durationMs=0), True),
    (_rec("run_end", passed=1, failed=0, skipped=0), True),
    (_rec("case_end", file="f", test="a", case="c1", attempt=0, status="passed", durationMs=0), False),
    (_rec("case_end", file="f", test="a", case="c1", attempt=1, status="skipped", durationMs=1), False),
    (_rec("case_start", file="f", test="a", case="c1", attempt=0), False),
    (_rec("run_start", files=3, extra=1), False),
    (_rec("run_start", files=3, truncated=True), False),
    (_rec("case_start", file="f", test="a", case="c" * 202, attempt=1), False),
    (_rec("case_start", file="f", test="a", case="c", attempt=1, truncated=False), False),
    ({**_rec("run_start", files=1), "run": RUN.upper()}, False),
    ({**_rec("run_start", files=1), "v": 2}, False),
    ({**_rec("run_start", files=1), "t": True}, False),
    ("not a dict", False),
])
def test_valid_follows_the_schema(rec, ok):
    assert tp.valid(rec) is ok


def test_folder_tail_reads_complete_lines_once(tmp_path):
    tail = tp.FolderTail(tmp_path)
    f = tmp_path / f"{RUN}.jsonl"
    f.write_text(json.dumps(_rec("run_start", files=1)) + "\n" + '{"partial": ')
    assert [r["event"] for r in tail.read_new()] == ["run_start"]
    assert tail.read_new() == []
    with open(f, "a") as h:
        h.write('1}\nnot json\n')
    assert tail.read_new() == [{"partial": 1}, {"_bad": True}]
    old = tmp_path / "old.jsonl"
    old.write_text("{}\n")
    os.utime(old, (time.time() - 3 * 86400,) * 2)
    assert tail.prune() == 1 and not old.exists() and f.exists()


def test_device_log_lines():
    rec = _rec("run_start", files=1)
    assert tp.parse_logcat_line(json.dumps(rec)) == rec
    assert tp.parse_logcat_line("--------- beginning of main") is None
    entry = {"eventMessage": json.dumps(rec), "subsystem": "com.jsonui.testrunner"}
    assert tp.parse_ndjson_line(json.dumps(entry)) == rec
    assert tp.parse_ndjson_line("Filtering the log data using …") is None
    assert tp.parse_ndjson_line(json.dumps({"eventMessage": "not ours"})) is None


def test_follow_hands_on_each_record_of_a_reader_process(tmp_path):
    script = tmp_path / "reader.sh"
    lines = [json.dumps(_rec("run_start", files=1)), "noise", json.dumps(_rec("run_end", passed=1, failed=0, skipped=0))]
    script.write_text("#!/bin/sh\n" + "".join(f"echo '{line}'\n" for line in lines))
    script.chmod(0o755)
    got = []
    asyncio.run(tp.follow([str(script)], tp.parse_logcat_line, got.append))
    assert [r["event"] for r in got] == ["run_start", "run_end"]


def test_devices_parse_and_name_the_device_a_command_drives():
    simctl = json.dumps({"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-26-2": [
        {"udid": "11111111-2222-3333-4444-555555555555", "name": "iPhone 16", "state": "Booted"},
        {"udid": "x", "name": "iPad", "state": "Shutdown"}]}}).encode()
    adb = (b"List of devices attached\nemulator-5554          device product:sdk model:Pixel_Tablet transport_id:3\n"
           b"23031FDF6008A0         unauthorized usb:1\n")
    found = devices.parse_simctl(simctl) + devices.parse_adb(adb)
    assert [(d["id"], d["platform"], d["name"], d["state"]) for d in found] == [
        ("11111111-2222-3333-4444-555555555555", "ios", "iPhone 16（iOS 26.2）", "booted"),
        ("emulator-5554", "android", "Pixel Tablet", "device"),
        ("23031FDF6008A0", "android", "23031FDF6008A0", "unauthorized"),
    ]
    assert devices.device_for_command("xcodebuild test -destination 'platform=iOS Simulator,name=iPhone 16'", found) == found[0]["id"]
    assert devices.device_for_command("xcodebuild test -destination id=11111111-2222-3333-4444-555555555555", found) == found[0]["id"]
    assert devices.device_for_command("ANDROID_SERIAL=emulator-5554 ./gradlew connectedDebugAndroidTest", found) == "emulator-5554"
    assert devices.device_for_command("adb -s emulator-5554 shell am instrument", found) == "emulator-5554"
    assert devices.device_for_command("./gradlew connectedDebugAndroidTest", found) is None


def test_devices_run_says_why_when_no_command_exists(monkeypatch):
    monkeypatch.setattr(devices, "find_adb", lambda: None)
    statuses = []
    asyncio.run(devices.run(lambda d: None, lambda st, err: statuses.append((st, err)), which=lambda n: None))
    assert statuses == [("stopped", "xcrun も adb も見つかりません（端末の取得を止めました）")]


def _project(root: Path) -> Path:
    (root / "docs/screens/json").mkdir(parents=True)
    (root / "docs/screens/layouts").mkdir(parents=True)
    (root / "tests/screens").mkdir(parents=True)
    (root / "jui.config.json").write_text("{}")
    (root / "docs/screens/json/login.spec.json").write_text(json.dumps({"metadata": {"name": "Login", "layoutFile": "login"}}))
    (root / "docs/screens/layouts/login.json").write_text(json.dumps({"type": "View", "id": "root"}))
    (root / "tests/screens/login.test.json").write_text(json.dumps({"source": {"layout": "docs/screens/layouts/login.json"},
                                                                      "cases": [{"name": "ok"}, {"name": "ng"}]}))
    return root


def test_progress_records_fill_the_test_run_the_device_and_the_spec(tmp_path):
    root = _project(tmp_path)
    state = VizState()
    world = World(state)
    base = {"session_id": "s1", "cwd": str(root)}
    world.apply_hook({**base, "hook_event_name": "SessionStart"}, 0)
    world.apply_devices([{"id": "11111111-2222-3333-4444-555555555555", "platform": "ios", "name": "iPhone 16（iOS 26.2）", "state": "booted"}])
    cmd = "xcodebuild test -destination 'platform=iOS Simulator,name=iPhone 16'"
    world.apply_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "b", "tool_input": {"command": cmd}}, 100)
    world.publish()
    assert state.slices["devices"][0]["busyBy"] == "s1"
    assert "iPhone 16" in state.slices["agents"][0]["act"]

    for rec in (_rec("run_start", t=200, files=1, deviceId="11111111-2222-3333-4444-555555555555"),
                _rec("case_start", t=300, file="screens/login.test.json", test="login", case="ok", attempt=1)):
        assert world.apply_progress(rec, "ios", "11111111-2222-3333-4444-555555555555", 300)
    world.publish()
    run = state.slices["tests"][0]
    assert run["cases"] == [{"name": "ok", "status": "running"}]
    login = state.slices["specs"][0]
    assert login["tests"] == {"total": 2, "passed": 0, "failed": 0, "running": True}

    for rec in (_rec("case_end", t=400, file="screens/login.test.json", test="login", case="ok", attempt=1, status="passed", durationMs=90),
                _rec("case_start", t=410, file="screens/login.test.json", test="login", case="ng", attempt=1),
                _rec("case_end", t=500, file="screens/login.test.json", test="login", case="ng", attempt=1, status="failed", durationMs=90)):
        world.apply_progress(rec, "ios", None, 500)
    assert not world.apply_progress({"v": 1, "nope": True}, "ios", None, 500)  # dropped, counted
    world.publish()
    assert state.slices["tests"][0]["summary"] == "1 passed, 1 failed"
    assert state.slices["specs"][0]["tests"] == {"total": 2, "passed": 1, "failed": 1, "running": False}
    assert world.progress.dropped == {"ios": 1}
    world.apply_hook({**base, "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_use_id": "b", "tool_input": {"command": cmd},
                      "tool_response": {"stdout": "Executed 2 tests, with 1 failure", "stderr": ""}}, 600)
    world.publish()
    assert "busyBy" not in state.slices["devices"][0]
    assert "progressRun" not in state.slices["tests"][0]  # the link stays on the server


def test_mock_status_tells_our_mock_from_another_projects(tmp_path):
    """identity names the projectRoot: another project's mock on our port is not ours."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    from jui_cli.viz.sources import mock_status

    root = {"value": str(tmp_path)}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps({"pid": 4242, "projectRoot": root["value"], "mockDir": "x"}).encode()
            self.send_response(200 if self.path == "/__jsonui__/identity" else 404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    config = {"mock": {"server": {"port": port}}}
    try:
        assert mock_status.status(tmp_path, config) == {"running": True, "port": port, "pid": 4242}
        root["value"] = "/work/another-project"
        assert mock_status.status(tmp_path, config) == {"running": False, "port": port, "other": True}
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert mock_status.status(tmp_path, config) == {"running": False, "port": port}
    assert mock_status.mock_port({}) == 8790 and mock_status.mock_port({"mock": {"server": {"port": True}}}) == 8790



def test_records_the_real_drivers_wrote_are_all_accepted():
    """16 lines from the Android driver and 10 from the iOS driver, captured
    from real runs (b6, 10-18): every one fits, and each run's last case_end
    statuses add up to its run_end."""
    folder = Path(__file__).parent / "fixtures" / "viz" / "progress"
    for name, platform in (("android.jsonl", "android"), ("ios.jsonl", "ios")):
        lines = (folder / name).read_text().splitlines()
        assert lines, name
        book = tp.ProgressBook()
        for line in lines:
            rec = json.loads(line)
            assert tp.valid(rec), (name, line[:120])
            assert rec["platform"] == platform
            book.add(rec, platform)
        assert book.dropped == {}
        for run in book.runs.values():
            if "passed" in run:
                counts = [c["status"] for c in run["cases"].values()]
                assert (counts.count("passed"), counts.count("failed"), counts.count("skipped")) == \
                       (run["passed"], run["failed"], run["skipped"]), (name, run["run"])
