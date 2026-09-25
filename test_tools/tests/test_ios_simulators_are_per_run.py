"""tests/_ios_simulators.py without a simulator: each run owns its devices.

The executed iOS arms shared one fixed-name simulator per runtime across
runs, and two runs at once drove the same device (ticket
test-tools-ios-simulator-arms-collide-across-concurrent-runs). These arms
hold the parts that make a run's devices its own: the name, the sweep of
what killed runs left, and that nothing is found by name or deleted that
this run did not make. The executed arm itself is run twice at once in the
ticket's measurement.
"""
from __future__ import annotations

import json
import os
import subprocess

from tests import _ios_simulators as sims


def test_a_run_name_carries_the_pid_and_differs_per_call():
    a, b = sims.run_name("26.5"), sims.run_name("26.5")
    assert a != b
    for name in (a, b):
        match = sims.PER_RUN.match(name)
        assert match and match["version"] == "26.5" and int(match["pid"]) == os.getpid(), name


def _listing(*names):
    return {"com.apple.CoreSimulator.SimRuntime.iOS-26-5": [
        {"udid": f"U{i}", "name": name} for i, name in enumerate(names)]}


def test_the_sweep_takes_only_this_familys_per_run_devices_of_dead_runs():
    dead, alive = 999_999_1, os.getpid()
    listing = _listing(
        f"jsonui-branch-release-26.5-{dead}-abc123",    # a killed run's: swept
        f"jsonui-branch-release-18.6-{alive}-def456",   # a live run's (this one): kept
        "jsonui-branch-release-26.5",                   # the old fixed name: never touched
        f"jsonui-branch-release-26.5-{dead}",           # not the per-run shape: never touched
        "iPhone 16 Pro",                                # a shared device: never touched
        f"other-26.5-{dead}-abc123",                    # another family: never touched
    )
    swept = sims.abandoned(listing, alive=lambda pid: pid == alive)
    assert swept == [("U0", f"jsonui-branch-release-26.5-{dead}-abc123")]


class _FakeXcrun:
    def __init__(self, devices=None):
        self.calls = []
        self.devices = devices or {}
        self.count = 0

    def __call__(self, *args, timeout=120):
        self.calls.append(args)
        if args[:3] == ("simctl", "list", "devices"):
            return subprocess.CompletedProcess(args, 0, json.dumps({"devices": self.devices}), "")
        if args[:2] == ("simctl", "create"):
            self.count += 1
            return subprocess.CompletedProcess(args, 0, f"NEW-{self.count}\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")


RUNTIME = {"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-5", "version": "26.5",
           "supportedDeviceTypes": [{"identifier": sims.PREFERRED_DEVICE, "productFamily": "iPhone"}]}


def test_a_device_is_made_for_the_run_once_per_runtime_and_never_found_by_name(monkeypatch):
    fake = _FakeXcrun(devices=_listing("jsonui-branch-release-26.5"))  # the old one exists
    monkeypatch.setattr(sims, "xcrun", fake)
    run = sims.RunDevices()
    first = run.device(RUNTIME, missing=lambda why: None)
    assert run.device(RUNTIME, missing=lambda why: None) == first == "NEW-1"
    creates = [c for c in fake.calls if c[:2] == ("simctl", "create")]
    assert len(creates) == 1 and sims.PER_RUN.match(creates[0][2]), creates
    assert not [c for c in fake.calls if c[:3] == ("simctl", "list", "devices")], "found by name"


def test_release_deletes_what_the_run_made_and_nothing_else(monkeypatch):
    fake = _FakeXcrun()
    monkeypatch.setattr(sims, "xcrun", fake)
    run = sims.RunDevices()
    run.device(RUNTIME, missing=lambda why: None)
    run.release()
    touched = [c for c in fake.calls if c[:2] in (("simctl", "shutdown"), ("simctl", "delete"))]
    assert touched == [("simctl", "shutdown", "NEW-1"), ("simctl", "delete", "NEW-1")]
    run.release()  # twice is harmless: nothing left to delete
    assert len([c for c in fake.calls if c[:2] == ("simctl", "delete")]) == 1


def test_the_sweep_deletes_the_dead_runs_devices(monkeypatch):
    dead = 999_999_2
    fake = _FakeXcrun(devices=_listing(f"jsonui-branch-release-18.6-{dead}-aaaaaa", "jsonui-branch-release-18.6"))
    monkeypatch.setattr(sims, "xcrun", fake)
    monkeypatch.setattr(sims, "pid_alive", lambda pid: pid != dead)
    assert sims.RunDevices().sweep() == [f"jsonui-branch-release-18.6-{dead}-aaaaaa"]
    assert ("simctl", "delete", "U0") in fake.calls and ("simctl", "delete", "U1") not in fake.calls
