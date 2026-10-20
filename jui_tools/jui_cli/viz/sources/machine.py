"""This machine's load, for the デバイス button and its pane (ticket 2026-10-20-jui-viz-device-panel-machine-load-and-
emulators; requester: 「今いろんな作業やってる時にどういう状態か分かりづらい」「負荷に応じてボタンの色合いが変わる」).

Every INTERVAL_SEC: the load average (os.getloadavg) and how much memory is free (macOS: the kernel's
kern.memorystatus_level, the per cent the memory pressure gauge shows; Linux: MemAvailable of /proc/meminfo). Both
are read in this process — no command is started — so the reading costs the viz server next to nothing (the
requester asked whether it adds load). Nothing here changes anything on the machine.

The level, worse of two (the numbers proposed in the ticket before the work):
  * the 1-minute load over the cores: ok < 0.7 <= busy < 1.0 <= high;
  * the free memory: ok >= 25 % > busy >= 10 % > high.
"""
from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import os
import sys
import time
from typing import Callable

INTERVAL_SEC = 5.0
LOAD_BUSY, LOAD_HIGH = 0.7, 1.0
MEM_BUSY, MEM_HIGH = 25, 10      # per cent free, under which busy / high
LEVELS = ("ok", "busy", "high")

_libc = None


def _sysctl_int(name: str) -> int | None:
    """One integer sysctl by name (macOS), through libc: no process."""
    global _libc
    try:
        if _libc is None:
            _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        value = ctypes.c_uint64(0)
        size = ctypes.c_size_t(ctypes.sizeof(value))
        if _libc.sysctlbyname(name.encode(), ctypes.byref(value), ctypes.byref(size), None, ctypes.c_size_t(0)) != 0:
            return None
        return int(value.value) if size.value == 8 else int(value.value & 0xFFFFFFFF)
    except (OSError, AttributeError, TypeError):
        return None


def _meminfo(path: str = "/proc/meminfo") -> tuple[int | None, int | None]:
    """(total bytes, available bytes) on Linux."""
    got: dict[str, int] = {}
    try:
        with open(path, encoding="ascii", errors="replace") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if key in ("MemTotal", "MemAvailable") and parts and parts[0].isdigit():
                    got[key] = int(parts[0]) * 1024
    except OSError:
        return None, None
    return got.get("MemTotal"), got.get("MemAvailable")


def level(load1: float | None, cpus: int | None, mem_free_pct: int | None) -> str:
    """ok / busy / high: the worse of the load over the cores and the free memory. Unknown halves count as ok."""
    worst = 0
    if load1 is not None and cpus:
        ratio = load1 / cpus
        worst = max(worst, 2 if ratio >= LOAD_HIGH else 1 if ratio >= LOAD_BUSY else 0)
    if mem_free_pct is not None:
        worst = max(worst, 2 if mem_free_pct < MEM_HIGH else 1 if mem_free_pct < MEM_BUSY else 0)
    return LEVELS[worst]


def read(now_ms: Callable[[], int] = lambda: int(time.time() * 1000), platform: str = sys.platform) -> dict:
    """The machine slice: load (1, 5, 15 min), cores, memory total and free per cent, the level, when read."""
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        load = None
    cpus = os.cpu_count()
    total = free_pct = None
    if platform == "darwin":
        total = _sysctl_int("hw.memsize")
        lvl = _sysctl_int("kern.memorystatus_level")
        free_pct = lvl if lvl is not None and 0 <= lvl <= 100 else None
    elif platform.startswith("linux"):
        total, avail = _meminfo()
        free_pct = round(avail * 100 / total) if total and avail is not None else None
    return {"load": load, "cpus": cpus, "memTotal": total, "memFreePct": free_pct,
            "level": level(load[0] if load else None, cpus, free_pct), "at": now_ms()}


async def run(on_machine: Callable[[dict], None], interval: float = INTERVAL_SEC) -> None:
    while True:
        on_machine(read())
        await asyncio.sleep(interval)
