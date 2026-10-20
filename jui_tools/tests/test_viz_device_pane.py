"""The デバイス button and pane, server side (ticket 2026-10-20-jui-viz-device-panel-machine-load-and-emulators).

The machine slice (sources/machine.py: the level's boundaries, read without starting a process) and who uses a
device, strongest first (ingest.devices_slice): a running test, a process naming the device under a session's
process, the last Bash command naming it (30 minutes).
"""
from __future__ import annotations

import asyncio
import subprocess

import pytest

from jui_cli.viz.ingest import World
from jui_cli.viz.sources import devices, machine
from jui_cli.viz.state import VizState

UDID = "11111111-2222-3333-4444-555555555555"
SIM = {"id": UDID, "platform": "ios", "name": "iPhone 16（iOS 26.2）", "state": "booted"}
EMU = {"id": "emulator-5554", "platform": "android", "name": "sdk gphone64 arm64", "state": "device"}


# ---------------------------------------------------------------- the level (the numbers proposed in the ticket)

@pytest.mark.parametrize("load1, cpus, free, want", [
    (12.5, 18, 91, "ok"),       # 0.69
    (12.6, 18, 91, "busy"),     # 0.70
    (17.9, 18, 91, "busy"),     # 0.99
    (18.0, 18, 91, "high"),     # 1.00
    (1.0, 18, 25, "ok"),
    (1.0, 18, 24, "busy"),
    (1.0, 18, 10, "busy"),
    (1.0, 18, 9, "high"),
    (12.6, 18, 9, "high"),      # the worse of the two
    (18.0, 18, 50, "high"),
    (None, None, None, "ok"),   # nothing known: no colour of alarm
    (None, 18, 9, "high"),
    (20.0, None, None, "ok"),
])
def test_the_level_is_the_worse_of_load_over_cores_and_free_memory(load1, cpus, free, want):
    assert machine.level(load1, cpus, free) == want


def test_a_reading_starts_no_process(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("machine.read started a process")
    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", refuse)
    got = machine.read(now_ms=lambda: 42)
    assert set(got) == {"load", "cpus", "memTotal", "memFreePct", "level", "at"}
    assert got["at"] == 42 and got["level"] in machine.LEVELS
    assert got["load"] is None or len(got["load"]) == 3


def test_linux_free_memory_from_meminfo(tmp_path, monkeypatch):
    info = tmp_path / "meminfo"
    info.write_text("MemTotal:       16000000 kB\nMemFree:  100 kB\nMemAvailable:    1200000 kB\n")
    real = machine._meminfo
    monkeypatch.setattr(machine, "_meminfo", lambda: real(str(info)))
    got = machine.read(platform="linux")
    assert got["memTotal"] == 16000000 * 1024 and got["memFreePct"] == 8


# ---------------------------------------------------------------- what a command names

def test_a_command_names_devices_by_udid_serial_and_one_simulator_name():
    devs = [SIM, EMU]
    assert devices.ids_in_command(f"xcrun simctl install {UDID.lower()} App.app", devs) == {UDID}
    assert devices.ids_in_command("adb -s emulator-5554 install a.apk", devs) == {"emulator-5554"}
    assert devices.ids_in_command("ANDROID_SERIAL=R58M123 ./gradlew connectedCheck", devs) == {"R58M123"}
    assert devices.ids_in_command("xcodebuild test -destination 'platform=iOS Simulator,name=iPhone 16'", devs) == {UDID}
    assert devices.ids_in_command("ls -la", devs) == set()
    # a simulator booted by the command itself: its UDID is kept before the scan sees the device
    other = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
    assert devices.ids_in_command(f"xcrun simctl boot {other}", devs) == {other}


# ---------------------------------------------------------------- a process under a session's process

def test_a_process_naming_the_device_under_a_session_tells_the_session():
    rows = [
        (1, 0, "/sbin/launchd"),
        (100, 1, "claude"),                                                   # the session's process
        (200, 100, "/bin/zsh -c source ~/.claude/shell-snapshots/snapshot-zsh-1.sh && xcodebuild"),
        (300, 200, f"xcodebuild test -destination id={UDID}"),
        (400, 1, f"/Library/Developer/CoreSimulator/Devices/{UDID}/data/launchd_sim"),   # the simulator itself
        (500, 1, "claude"),                                                   # another session
        (600, 500, "adb -s emulator-5554 logcat"),
    ]
    got = devices.sessions_using(rows, [SIM, EMU], {100: "s1", 500: "s2"})
    assert got == {UDID: ["s1"], "emulator-5554": ["s2"]}
    assert devices.sessions_using(rows, [SIM], {}) == {}            # no session process known: none
    short = {"id": "abc", "platform": "android", "name": "x", "state": "device"}
    assert devices.sessions_using([(9, 100, "adb -s abc shell")], [short], {100: "s1"}) == {}   # too short to look for


def test_a_parent_loop_ends():
    rows = [(10, 11, f"x {UDID}"), (11, 10, "y")]
    assert devices.sessions_using(rows, [SIM], {100: "s1"}) == {}


# ---------------------------------------------------------------- the devices slice: strongest first

def _world(tmp_path):
    state = VizState()
    world = World(state)
    world.wall_ms = lambda: 1_000_000
    for sid in ("s1", "s2"):
        world.apply_hook({"session_id": sid, "cwd": str(tmp_path), "hook_event_name": "SessionStart"}, 0)
    world.apply_devices([SIM, EMU])
    return state, world


def _bash(world, sid, command, at, use="u"):
    world.apply_hook({"session_id": sid, "cwd": "/", "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_use_id": f"{use}-{at}", "tool_input": {"command": command}}, at)


def _used(state):
    return {d["id"]: d.get("usedBy") for d in state.slices["devices"]}


def test_nobody_is_named_without_a_record(tmp_path):
    state, world = _world(tmp_path)
    world.publish()
    assert _used(state) == {UDID: None, "emulator-5554": None}


def test_the_last_command_naming_a_device_tells_who_for_thirty_minutes(tmp_path):
    state, world = _world(tmp_path)
    _bash(world, "s1", f"xcrun simctl io {UDID} screenshot a.png", 900_000)
    _bash(world, "s2", f"xcrun simctl io {UDID} screenshot b.png", 950_000)
    world.publish()
    assert _used(state)[UDID] == {"agentId": "s2", "how": "command", "at": 950_000}
    world.wall_ms = lambda: 950_000 + devices.COMMAND_KEPT_MS + 1
    world.apply_devices([SIM, EMU])   # the next scan: the estimate went out of date
    world.publish()
    assert _used(state)[UDID] is None


def test_a_process_beats_a_command_and_a_test_beats_both(tmp_path):
    state, world = _world(tmp_path)
    _bash(world, "s2", f"xcrun simctl io {UDID} screenshot b.png", 950_000)
    world.pid_to_session.update({100: "s1"})
    world.apply_device_procs([(100, 1, "claude"), (300, 100, f"xcrun simctl spawn {UDID} log stream")])
    world.publish()
    assert _used(state)[UDID] == {"agentId": "s1", "how": "process", "others": []}
    _bash(world, "s2", f"xcodebuild test -destination id={UDID}", 960_000, use="t")
    world.publish()
    assert _used(state)[UDID] == {"agentId": "s2", "how": "test"}
    assert state.slices["devices"][0]["busyBy"] == "s2"   # the test pane's field stays


def test_the_process_estimate_clears_when_the_process_goes(tmp_path):
    state, world = _world(tmp_path)
    world.pid_to_session.update({100: "s1"})
    world.apply_device_procs([(100, 1, "claude"), (300, 100, "adb -s emulator-5554 logcat")])
    world.publish()
    assert _used(state)["emulator-5554"]["agentId"] == "s1"
    world.apply_device_procs([(100, 1, "claude")])
    world.publish()
    assert _used(state)["emulator-5554"] is None
    world.apply_device_procs(None)   # ps failed: the last answer stays as it is
    world.publish()
    assert _used(state)["emulator-5554"] is None


def test_the_machine_slice(tmp_path):
    state, world = _world(tmp_path)
    reading = {"load": [1.0, 2.0, 3.0], "cpus": 18, "memTotal": 1, "memFreePct": 50, "level": "ok", "at": 5}
    world.apply_machine(reading)
    world.publish()
    assert state.slices["machine"] == reading


def test_a_test_started_before_its_device_was_seen_is_tied_when_it_shows(tmp_path):
    state = VizState()
    world = World(state)
    world.wall_ms = lambda: 1_000_000
    world.apply_hook({"session_id": "s1", "cwd": str(tmp_path), "hook_event_name": "SessionStart"}, 0)
    _bash(world, "s1", f"xcodebuild test -scheme App -destination id={UDID}", 900_000, use="t")   # no device seen yet
    world.apply_devices([SIM])
    world.publish()
    assert _used(state)[UDID] == {"agentId": "s1", "how": "test"}
    assert state.slices["tests"][0]["deviceId"] == UDID
