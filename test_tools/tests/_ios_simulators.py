"""Simulators the executed iOS arms own — one set per run, never shared.

The harness-release arms (test_branch_harness_release_ios.py) found or made
ONE simulator per runtime by a fixed name (`jsonui-branch-release-<version>`)
and reused it silently. Two runs at once — two lanes, or run-suites and a
lane — then drove the same device: both `xcodebuild test` processes
installed the same probe bundle on it and ran their tests into each other
(measured 2026-09-26; the ticket test-tools-ios-simulator-arms-collide-
across-concurrent-runs has the log).

So each run makes its own device per runtime, named
`jsonui-branch-release-<version>-<pid>-<token>`, and deletes it when the
module ends. A run that was killed before it could delete its devices
leaves them behind; the next run removes exactly those — this family's
per-run names whose pid is no longer alive — and nothing else. Devices
of any other name (the old fixed-name ones included, and every shared or
user simulator) are never touched, nor is `xcode-select`: Xcode is whatever
DEVELOPER_DIR, else the selected one, resolves.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess

PREFIX = "jsonui-branch-release-"
#: `jsonui-branch-release-<version>-<pid>-<token>`; the version may be 26.5 or 18.6.
PER_RUN = re.compile(r"^jsonui-branch-release-(?P<version>[0-9.]+)-(?P<pid>\d+)-(?P<token>[0-9a-f]{6})$")
PREFERRED_DEVICE = "com.apple.CoreSimulator.SimDeviceType.iPhone-16-Pro"


def xcrun(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["xcrun", *args], capture_output=True, text=True, timeout=timeout)


def run_name(version: str, pid: int | None = None, token: str | None = None) -> str:
    """This run's device name for *version*."""
    return f"{PREFIX}{version}-{pid or os.getpid()}-{token or secrets.token_hex(3)}"


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def abandoned(devices: dict, alive=pid_alive) -> list[tuple[str, str]]:
    """(udid, name) of every per-run device whose run is gone — from a
    `simctl list devices -j` "devices" map. Only this family's per-run
    names count; a fixed-name or foreign device never does."""
    found = []
    for listed in devices.values():
        for device in listed:
            match = PER_RUN.match(device.get("name", ""))
            if match and not alive(int(match["pid"])):
                found.append((device["udid"], device["name"]))
    return found


def delete(udid: str) -> None:
    """Shut down (it may be booted) and delete one device this family owns."""
    xcrun("simctl", "shutdown", udid)
    xcrun("simctl", "delete", udid)


class RunDevices:
    """This run's devices, one per runtime, made on first use."""

    def __init__(self) -> None:
        self.made: dict[str, str] = {}   # runtime identifier -> udid

    def sweep(self) -> list[str]:
        """Delete the devices killed runs left behind; returns their names."""
        listed = xcrun("simctl", "list", "devices", "-j")
        if listed.returncode != 0:
            return []
        gone = abandoned(json.loads(listed.stdout)["devices"], alive=pid_alive)
        for udid, _ in gone:
            delete(udid)
        return [name for _, name in gone]

    def device(self, runtime: dict, missing) -> str:
        """This run's simulator for *runtime* — made for this run, never
        found by name. *missing* reports a runtime with no iPhone type."""
        key = runtime["identifier"]
        if key in self.made:
            return self.made[key]
        types = [t["identifier"] for t in runtime.get("supportedDeviceTypes", [])
                 if t.get("productFamily") == "iPhone"]
        if not types:
            missing(f"iOS {runtime['version']} lists no iPhone device type")
        kind = PREFERRED_DEVICE if PREFERRED_DEVICE in types else types[-1]
        made = xcrun("simctl", "create", run_name(runtime["version"]), kind, key)
        assert made.returncode == 0, made.stderr
        self.made[key] = made.stdout.strip()
        return self.made[key]

    def release(self) -> None:
        for udid in self.made.values():
            delete(udid)
        self.made.clear()
