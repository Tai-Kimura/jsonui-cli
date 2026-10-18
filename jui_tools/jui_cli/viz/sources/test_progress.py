"""Per-case test progress from the three drivers. Design: P7 §B.

The record format is jsonui-test-runner's schemas/progress.schema.json
(vendored at test_tools/tests/schema_fixtures/). There is no JSON Schema
library in jui_tools' dependencies, so ``valid`` restates its rules by hand;
tests/test_viz_test_progress.py compares these key sets with the schema file
itself, so a change on either side turns that test red.

Where the records come from:
  * Web: <JSONUI_TEST_PROGRESS_DIR>/<run>.jsonl, appended by the runner
    (hooks install and the plugin put <paths.viz_home()>/test-progress there;
    serve also reads the folder of 2.1.0 and earlier, ~/.jsonui-cli/viz/test-progress, while a
    session still writes there).
  * Android: logcat tag JsonUITestProgress at Info, read per device with
    ``adb -s <serial> logcat -v raw -s JsonUITestProgress:I -T 1``.
  * iOS: unified logging, read per simulator with ``xcrun simctl spawn
    <udid> log stream --style ndjson --level info --predicate …``.
The device readers run only while a test command of that platform runs.
A record that does not fit the schema is dropped, with one warning per kind.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Callable

COMMON = {"v", "t", "platform", "run", "event"}
KEYS = {
    "run_start": COMMON | {"device", "deviceId", "files"},
    "case_start": COMMON | {"file", "test", "case", "truncated", "attempt"},
    "case_end": COMMON | {"file", "test", "case", "truncated", "attempt", "status", "durationMs"},
    "run_end": COMMON | {"passed", "failed", "skipped"},
}
REQUIRED = {
    "run_start": COMMON | {"files"},
    "case_start": COMMON | {"file", "test", "case", "attempt"},
    "case_end": COMMON | {"file", "test", "case", "attempt", "status", "durationMs"},
    "run_end": COMMON | {"passed", "failed", "skipped"},
}
PLATFORMS = ("ios", "android", "web")
RUN_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME_MAX = 201
KEEP_DAYS = 1


def _int(v, minimum: int = 0) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= minimum


def valid(rec) -> bool:
    if not isinstance(rec, dict):
        return False
    event = rec.get("event")
    if event not in KEYS or set(rec) - KEYS[event] or REQUIRED[event] - set(rec):
        return False
    if rec["v"] != 1 or not _int(rec["t"]) or rec["platform"] not in PLATFORMS:
        return False
    if not isinstance(rec["run"], str) or not RUN_ID.match(rec["run"]):
        return False
    for key in ("file", "test", "case", "device", "deviceId"):
        if key in rec and not isinstance(rec[key], str):
            return False
    for key in ("file", "test", "case"):
        if key in rec and len(rec[key]) > NAME_MAX:
            return False
    if "truncated" in rec and rec["truncated"] is not True:
        return False
    if event == "run_start":
        return _int(rec["files"])
    if event == "run_end":
        return all(_int(rec[k]) for k in ("passed", "failed", "skipped"))
    if event == "case_start":
        return _int(rec["attempt"], 1)
    # case_end
    if not _int(rec["attempt"]) or not isinstance(rec["durationMs"], (int, float)) or isinstance(rec["durationMs"], bool) or rec["durationMs"] < 0:
        return False
    if rec["attempt"] == 0:
        return rec["status"] == "skipped" and rec["durationMs"] == 0
    return rec["status"] in ("passed", "failed")


class ProgressBook:
    """Runs keyed by their UUID: the cases as they start and end."""

    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}
        self.dropped: dict[str, int] = {}

    def add(self, rec, source: str, device_id: str | None = None) -> dict | None:
        if not valid(rec):
            self.dropped[source] = self.dropped.get(source, 0) + 1
            return None
        run = self.runs.setdefault(rec["run"], {
            "run": rec["run"], "platform": rec["platform"], "cases": {}, "status": "running",
            "startedAt": rec["t"],
        })
        if device_id and "deviceId" not in run:
            run["deviceId"] = device_id
        event = rec["event"]
        if event == "run_start":
            run.update({k: rec[k] for k in ("device", "deviceId", "files") if k in rec})
            run["startedAt"] = rec["t"]
        elif event in ("case_start", "case_end"):
            # One results.json row per occurrence, not per name: a reopen whose
            # teardown fails twice writes two "teardown" rows, and keying by
            # name alone folded them into one case (independent review, 10-18).
            # A start that does not continue the attempt sequence of a finished
            # case of that name — or a lone skipped end — opens a new occurrence.
            base = f"{rec['file']}␟{rec['test']}␟{rec['case']}"
            seen = run.setdefault("_occ", {})
            n = seen.get(base, 0)
            current = run["cases"].get(f"{base}␟{n}")
            if current is not None and current["status"] != "running" and (
                    (event == "case_start" and rec["attempt"] <= current["attempt"])
                    or (event == "case_end" and rec["attempt"] == 0)):
                n += 1
            seen[base] = n
            key = f"{base}␟{n}"
            case = run["cases"].setdefault(key, {"name": rec["case"], "test": rec["test"], "file": rec["file"]})
            case["attempt"] = rec["attempt"]
            case["status"] = "running" if event == "case_start" else rec["status"]
            if rec.get("truncated"):
                case["truncated"] = True
        else:
            run.update({k: rec[k] for k in ("passed", "failed", "skipped")})
            run["status"] = "failed" if rec["failed"] else "passed"
            run["endedAt"] = rec["t"]
        run["updatedAt"] = rec["t"]
        return run

    def cases(self, run_id: str) -> list[dict]:
        run = self.runs.get(run_id)
        return [dict(c) for c in run["cases"].values()] if run else []


# ---------------------------------------------------------------- web: a folder of .jsonl files


class FolderTail:
    """New complete lines of every *.jsonl in a folder, remembered by offset."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.offsets: dict[Path, int] = {}

    def prune(self, now: float | None = None) -> int:
        now = now or time.time()
        removed = 0
        for path in self.folder.glob("*.jsonl") if self.folder.is_dir() else []:
            try:
                if now - path.stat().st_mtime > KEEP_DAYS * 86400:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
        return removed

    def read_new(self) -> list[dict]:
        out: list[dict] = []
        if not self.folder.is_dir():
            return out
        for path in sorted(self.folder.glob("*.jsonl")):
            try:
                size = path.stat().st_size
                start = self.offsets.get(path, 0)
                if size < start:
                    start = 0  # replaced
                if size == start:
                    continue
                with open(path, "rb") as f:
                    f.seek(start)
                    chunk = f.read(size - start)
            except OSError:
                continue
            end = chunk.rfind(b"\n")
            if end < 0:
                continue  # no complete line yet
            self.offsets[path] = start + end + 1
            for line in chunk[: end + 1].splitlines():
                try:
                    out.append(json.loads(line.decode("utf-8")))
                except (UnicodeDecodeError, ValueError):
                    out.append({"_bad": True})
        return out


# ---------------------------------------------------------------- device logs


def logcat_argv(adb: str, serial: str) -> list[str]:
    return [adb, "-s", serial, "logcat", "-v", "raw", "-s", "JsonUITestProgress:I", "-T", "1"]


def simctl_log_argv(xcrun: str, udid: str) -> list[str]:
    return [xcrun, "simctl", "spawn", udid, "log", "stream", "--style", "ndjson", "--level", "info",
            "--predicate", 'subsystem == "com.jsonui.testrunner" AND category == "progress"']


def parse_logcat_line(line: str):
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        return json.loads(line)
    except ValueError:
        return {"_bad": True}


def parse_ndjson_line(line: str):
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    message = entry.get("eventMessage") if isinstance(entry, dict) else None
    if not isinstance(message, str) or not message.startswith("{"):
        return None
    try:
        return json.loads(message)
    except ValueError:
        return {"_bad": True}


async def follow(argv: list[str], parse: Callable[[str], object], on_record: Callable[[object], None]) -> None:
    """Run a log reader (its own process group) and hand each record on, until cancelled."""
    proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            rec = parse(line.decode("utf-8", "replace"))
            if rec is not None:
                on_record(rec)
    finally:
        if proc.returncode is None:
            try:
                os.killpg(proc.pid, 15)  # the group started above
            except (ProcessLookupError, PermissionError):
                # gone, or (macOS) its leader exited and is not reaped yet: EPERM, nothing left to stop
                pass
            transport = getattr(proc, "_transport", None)
            if transport is not None:
                transport.close()
