"""The plan's usage limits for the header: the 5-hour and the weekly window (requester, 10-18).

The only source is the JSON Claude Code gives a statusLine command (measured in the 2.1.302 binary,
10-18): ``rate_limits: {five_hour: {used_percentage, resets_at}, seven_day: {...}}`` — used_percentage
0-100 with one decimal, capped at 100 (so 100 means the limit is reached), resets_at in epoch seconds,
a window whose reset has passed left out. statusline.py posts it here; this module checks it, keeps the
last value in <viz_home>/usage.json (a restart still shows it, with when it came) and makes the slice.

⚠️ Only a terminal claude runs a statusLine: the VS Code extension shows its own usage and never runs
the command (read in extension 2.1.301, 10-18), and neither does the desktop app (it runs Claude Code as
stream-json too; one turn ran statusline.py 0 times, measured 10-19). With no terminal claude running the value goes stale;
the header says how old it is, and doctor says why.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from . import paths

WINDOWS = (("five_hour", "fiveHour"), ("seven_day", "sevenDay"))
MAX_BODY = 64_000


#: The second plan shown beside Claude's (requester 10-26: 「セレクトでどっち表示するか選べる…ホバーで両方」): Codex's, from
#: the app-server daemon's account/rateLimits/updated (sources/codex_app_server.py). Kept in its own file and slice
#: (usage-codex.json, "usageCodex"); Claude Code's stay as they were ("usage", usage.json).
CODEX = "codex"


def store_path(which: str = "") -> Path:
    return paths.viz_home() / ("usage-codex.json" if which == CODEX else "usage.json")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def parse(rate_limits) -> dict | None:
    """{fiveHour?: {pct, resetsAt}, sevenDay?: {...}} from Claude Code's rate_limits, or None when it holds neither."""
    if not isinstance(rate_limits, dict):
        return None
    out = {}
    for src, key in WINDOWS:
        w = rate_limits.get(src)
        if not isinstance(w, dict) or not _num(w.get("used_percentage")) or not _num(w.get("resets_at")):
            continue
        pct = max(0.0, min(100.0, float(w["used_percentage"])))
        resets = int(w["resets_at"])
        if resets <= 0:
            continue
        out[key] = {"pct": round(pct, 1), "resetsAt": resets * 1000}
    return out or None


def parse_codex(rate_limits) -> dict | None:
    """{fiveHour?, sevenDay?} from the daemon's rateLimits ({primary, secondary: {usedPercent 0-100, windowDurationMins,
    resetsAt epoch s}}, measured on macOS 10-26: primary 300 min), or None. A window goes by its length (up to 6 hours:
    fiveHour; a week: sevenDay); without one, primary is the 5-hour and secondary the weekly."""
    if not isinstance(rate_limits, dict):
        return None
    out = {}
    for src, fallback in (("primary", "fiveHour"), ("secondary", "sevenDay")):
        w = rate_limits.get(src)
        if not isinstance(w, dict) or not _num(w.get("usedPercent")) or not _num(w.get("resetsAt")):
            continue
        mins = w.get("windowDurationMins")
        key = fallback if not _num(mins) else "fiveHour" if mins <= 360 else "sevenDay" if mins >= 6 * 1440 else None
        resets = int(w["resetsAt"])
        if key is None or resets <= 0 or key in out:
            continue
        out[key] = {"pct": round(max(0.0, min(100.0, float(w["usedPercent"]))), 1), "resetsAt": resets * 1000}
    return out or None


def make_slice(windows: dict | None, received_at: int | None) -> dict:
    return {"windows": windows, "receivedAt": received_at} if windows else {}


#: usage.json is written again only when the windows changed, or this long after the last write: every terminal claude's
#: status line posts here every few seconds with the same numbers, and each write was a temp file and a rename that
#: fseventsd records (ticket 2026-11-24-viz-talk-db-autocommit-floods-fsevents, 34 renames a minute measured). A restart
#: then shows a receivedAt at most this old; the header shows the age, so it reads a little older than it was.
KEEP_EVERY_MS = 60_000
_kept: dict[str, tuple[dict, int]] = {}          # the file -> (the windows last written, their receivedAt)


def _keep(value: dict, which: str, run: Callable[[Callable[[], None]], Any] | None) -> None:
    """Write value when due (see KEEP_EVERY_MS), through run (the server hands its executor, so the event loop never
    touches the file), else here."""
    key = str(store_path(which))
    last = _kept.get(key)
    if last is not None and last[0] == value["windows"] and value["receivedAt"] - last[1] < KEEP_EVERY_MS:
        return
    _kept[key] = (value["windows"], value["receivedAt"])

    def write() -> None:
        try:
            save(value, which)
        except OSError:
            _kept.pop(key, None)   # shown anyway; the next value tries again
    (run or (lambda fn: fn()))(write)


def save(value: dict, which: str = "") -> None:
    path = store_path(which)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".usage.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(value).encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)


def load(which: str = "") -> dict:
    """The last value kept, as a slice, or {} (none, or unreadable)."""
    try:
        data = json.loads(store_path(which).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("windows"), dict) or not _num(data.get("receivedAt")):
        return {}
    windows = {k: v for k, v in data["windows"].items() if k in dict(WINDOWS).values() and isinstance(v, dict)
               and _num(v.get("pct")) and _num(v.get("resetsAt"))}
    return make_slice(windows or None, int(data["receivedAt"]))


def accept(payload, now_ms: int | None = None, run: Callable[[Callable[[], None]], Any] | None = None) -> dict | None:
    """A POST /usage body ({rate_limits}) → the new slice (kept on disk when due, through run), or None when it carries
    nothing usable."""
    if not isinstance(payload, dict):
        return None
    windows = parse(payload.get("rate_limits"))
    if windows is None:
        return None
    value = make_slice(windows, int(now_ms if now_ms is not None else time.time() * 1000))
    _keep(value, "", run)   # shown anyway; a write that fails only loses it for a restart
    return value


def accept_codex(rate_limits, now_ms: int | None = None, run: Callable[[Callable[[], None]], Any] | None = None) -> dict | None:
    """The daemon's rateLimits -> the new usageCodex slice (kept on disk), or None when it carries nothing usable."""
    windows = parse_codex(rate_limits)
    if windows is None:
        return None
    value = make_slice(windows, int(now_ms if now_ms is not None else time.time() * 1000))
    _keep(value, CODEX, run)
    return value
