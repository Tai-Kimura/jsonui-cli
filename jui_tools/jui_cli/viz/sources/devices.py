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
                out.append({"id": dev["udid"], "platform": "ios", "name": f"{dev.get('name', '?')}（{version}）",
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
        on_status("stopped", "xcrun も adb も見つかりません（端末の取得を止めました）")
        return
    missing = [name for name, path in (("xcrun", xcrun), ("adb", adb)) if path is None]
    on_status("running", f"{' と '.join(missing)} が無いため、その分は取りません" if missing else None)
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
        hits = [d["id"] for d in devices if d["platform"] == "ios" and d["name"].split("（")[0] == name]
        if len(hits) == 1:
            return hits[0]
    return None
