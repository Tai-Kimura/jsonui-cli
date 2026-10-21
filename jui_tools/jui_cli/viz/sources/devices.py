"""Booted simulators and attached Android devices, for the desks. Design: P7 §A1–A2.

Every 10 s: ``xcrun simctl list devices booted -j`` and ``adb devices -l``,
each cut off after 3 s. A missing command stops only its own half, and says
why. These commands only read; nothing here starts, stops or signals a
device.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from typing import Callable

from .. import i18n

TIMEOUT_SEC = 3.0
INTERVAL_SEC = 10.0


def find_adb() -> str | None:
    found = shutil.which("adb")
    if found:
        return found
    for base in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                 os.path.expanduser("~/Library/Android/sdk"), os.path.expanduser("~/Android/Sdk")):
        if base:
            path = os.path.join(base, "platform-tools", "adb")
            if os.path.isfile(path):
                return path
    return None


def parse_simctl(stdout: bytes) -> list[dict]:
    try:
        data = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return []
    out = []
    for runtime, devices in (data.get("devices") or {}).items() if isinstance(data, dict) else []:
        version = runtime.rsplit(".", 1)[-1].replace("iOS-", "iOS ").replace("-", ".")
        for dev in devices if isinstance(devices, list) else []:
            if isinstance(dev, dict) and dev.get("state") == "Booted" and isinstance(dev.get("udid"), str):
                out.append({"id": dev["udid"], "platform": "ios", "baseName": dev.get("name", "?"),
                            "name": i18n.tl("srv.device.name", name=dev.get('name', '?'), version=version),
                            "state": "booted"})
    return out


_ADB_LINE = re.compile(r"^(\S+)\s+(device|offline|unauthorized|recovery|sideload|bootloader)\b(.*)$")


def parse_adb(stdout: bytes) -> list[dict]:
    out = []
    for line in stdout.decode("utf-8", "replace").splitlines():
        m = _ADB_LINE.match(line.strip())
        if not m:
            continue
        serial, state, rest = m.groups()
        model = re.search(r"\bmodel:(\S+)", rest)
        name = (model.group(1).replace("_", " ") if model else serial)
        out.append({"id": serial, "platform": "android", "name": name, "state": state})
    return out


async def _run(argv: list[str]) -> bytes | None:
    try:
        proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return None
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT_SEC)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, 9)  # the group started just above
        except ProcessLookupError:
            pass
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            transport.close()
        return None
    return stdout if proc.returncode == 0 else None


async def run(on_devices: Callable[[list[dict]], None], on_status: Callable[[str, str | None], None],
              which: Callable[[str], str | None] = shutil.which, adb: str | None = None,
              interval: float = INTERVAL_SEC) -> None:
    xcrun = which("xcrun")
    adb = adb or find_adb()
    if xcrun is None and adb is None:
        on_status("stopped", i18n.tl("srv.device.none"))
        return
    missing = [name for name, path in (("xcrun", xcrun), ("adb", adb)) if path is None]
    on_status("running", i18n.tl("srv.device.missing", tools=i18n.tl("srv.and").join(missing)) if missing else None)
    while True:
        devices: list[dict] = []
        if xcrun:
            raw = await _run([xcrun, "simctl", "list", "devices", "booted", "-j"])
            devices += parse_simctl(raw) if raw else []
        if adb:
            raw = await _run([adb, "devices", "-l"])
            devices += parse_adb(raw) if raw else []
        on_devices(devices)
        await asyncio.sleep(interval)


# ---------------------------------------------------------------- which device a command drives

_DEST_NAME = re.compile(r"-destination\s+['\"]?[^'\"]*?name=([^,'\"]+)")
_DEST_ID = re.compile(r"-destination\s+['\"]?[^'\"]*?id=([0-9A-Fa-f-]{36})")
_SERIAL_ENV = re.compile(r"\bANDROID_SERIAL=(\S+)")
_ADB_S = re.compile(r"\badb\s+-s\s+(\S+)")


def device_for_command(command: str, devices: list[dict]) -> str | None:
    """The id of the device a test command names, if it names one we know."""
    for pattern in (_DEST_ID, _SERIAL_ENV, _ADB_S):
        m = pattern.search(command)
        if m:
            wanted = m.group(1).strip("'\"")
            for dev in devices:
                if dev["id"] == wanted:
                    return dev["id"]
    m = _DEST_NAME.search(command)
    if m:
        name = m.group(1).strip()
        hits = [d["id"] for d in devices if d["platform"] == "ios" and (d.get("baseName") or re.split(r"[\uff08(]", d["name"])[0].strip()) == name]
        if len(hits) == 1:
            return hits[0]
    return None


# ---------------------------------------------------------------- who uses a device (estimated; the デバイス pane)
# Ticket 2026-10-20-jui-viz-device-panel-machine-load-and-emulators. Nothing records a device's user: a simulator runs
# under launchd, an emulator under whoever started it. So the pane says how each user was found, strongest first:
#   test     a running test's command names the device (busyBy, above);
#   process  a process whose arguments name the device runs under a session's process (ps, only while a device is up);
#   command  the last Bash command that named the device (any robot, within COMMAND_KEPT_MS).

_UUID = re.compile(r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")
_EMULATOR = re.compile(r"\bemulator-\d+\b")
COMMAND_KEPT_MS = 30 * 60_000
ANCESTORS_MAX = 64


def ids_in_command(command: str, devices: list[dict]) -> set[str]:
    """The device ids a command names: a UUID, an emulator serial, adb -s / ANDROID_SERIAL=, and a -destination
    name= that fits one booted simulator only. A UUID is kept even before its device is seen (simctl boot <udid>)."""
    found = {m.group(0).upper() for m in _UUID.finditer(command)} | {m.group(0) for m in _EMULATOR.finditer(command)}
    for pattern in (_SERIAL_ENV, _ADB_S):
        found |= {m.group(1).strip("'\"") for m in pattern.finditer(command)}
    named = device_for_command(command, devices)
    if named:
        found.add(named)
    known = {d["id"].upper(): d["id"] for d in devices}
    return {known.get(x.upper(), x) for x in found}


def sessions_using(rows: list[tuple[int, int, str]], devices: list[dict], pid_to_session: dict[int, str]) -> dict[str, list[str]]:
    """Device id -> the sessions (oldest pid first) with a process under them whose arguments name the device."""
    parent = {pid: ppid for pid, ppid, _ in rows}
    out: dict[str, list[str]] = {}
    for dev in devices:
        dev_id = dev["id"]
        if len(dev_id) < 8:   # a serial too short to look for in a command line
            continue
        sids: list[str] = []
        for pid, _ppid, command in rows:
            if dev_id not in command:
                continue
            seen, cur = 0, pid
            while cur and seen < ANCESTORS_MAX and cur not in pid_to_session:
                cur, seen = parent.get(cur, 0), seen + 1
            sid = pid_to_session.get(cur)
            if sid and sid not in sids:
                sids.append(sid)
        if sids:
            out[dev_id] = sids
    return out
