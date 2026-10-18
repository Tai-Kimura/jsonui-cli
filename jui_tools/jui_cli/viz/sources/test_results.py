"""Saved test results from the three drivers: what keeps a run's pass / fail after the
server restarts, and shows the runs it never saw.

Since the drivers' default results folder (jsonui-test-runner, 2026-10-18), a run with no
resultsPath writes one results.schema.json file per run (per test file) to a
default folder, never overwriting an older run (requester's choice 2026-10-18:
"the drivers write, viz reads"). This module only reads them; the live
progress records (test_progress.py) still carry the run while it is under way,
and the two are merged per case, newest first (ingest.py).

Where the files are:
  * <base> = $JSONUI_TEST_RESULTS_DIR when absolute, else ~/.local/state/jsonui-test/results.
    XDG_STATE_HOME is NOT followed: the iOS simulator writes under
    SIMULATOR_HOST_HOME and cannot see the host's XDG value, so following it
    here would read an empty folder while the driver wrote elsewhere.
    The variable is the same one the drivers read on the host side (iOS gets
    it as TEST_RUNNER_JSONUI_TEST_RESULTS_DIR, Web from its environment);
    it has no effect on the Android device. A value that differs between this
    server and the driver reads 0 files and says nothing — `jui viz doctor`
    prints the folder this server reads.
  * iOS (simulator) and Web: <base>/<platform>/<app>/<UTC>-<run>.json.
  * Android: the device keeps /data/local/tmp/jsonui-test-results/<package>/; this
    server copies it with ``adb pull`` into <base>/android/<serial>/<package>/ at two
    moments only: once at start for every attached device, and when a run's
    run_end arrives from that device. There is no watcher of its own.
Pruning, per app folder, by the drivers' own rule (to_prune; 2.3.1): the latest result of every test file always
stays; 14 days and 500 files apply only to results a newer one of the same test file replaced, and to names of the
earlier shape. Only names of the driver's shape are ever deleted. This server prunes every app folder at start, so a
different rule here would undo the drivers'.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

BASE_ENV = "JSONUI_TEST_RESULTS_DIR"
#: A results file's name; group 1 is the run's file key (the drivers since ios 2.1.1 / android 1.19.1 / web 1.17.1),
#: absent on a name of the earlier shape.
NAME = re.compile(r"^\d{8}T\d{6}\.\d{3}Z-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:-([0-9a-f]{8}))?\.json$")
KEEP_FILES = 500
KEEP_DAYS = 14
PULL_TIMEOUT_SEC = 20.0
DEVICE_DIR = "/data/local/tmp/jsonui-test-results"
PLATFORMS = ("ios", "android", "web")
STATUSES = ("passed", "failed", "skipped")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def results_base() -> Path:
    override = os.environ.get(BASE_ENV, "")
    if os.path.isabs(override):
        return Path(override)
    return Path.home() / ".local" / "state" / "jsonui-test" / "results"


def sanitize(name: str) -> str:
    """The drivers' folder rule (Android ArtifactPaths.sanitize)."""
    cleaned = _UNSAFE.sub("_", name)
    return "unknown" if not cleaned or set(cleaned) == {"."} else cleaned


def name_time(name: str) -> float | None:
    """Seconds since the epoch encoded in a result file's name, or None."""
    if not NAME.match(name):
        return None
    try:
        return datetime.strptime(name[:19] + "000+0000", "%Y%m%dT%H%M%S.%f%z").timestamp()
    except ValueError:
        return None


def app_folders(base: Path) -> list[Path]:
    """Every folder that holds one app's files: <p>/<app>/ for ios and web, android/<serial>/<package>/."""
    out: list[Path] = []
    for platform in ("ios", "web"):
        root = base / platform
        out += sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    android = base / "android"
    for serial in sorted(p for p in android.iterdir() if p.is_dir()) if android.is_dir() else []:
        out += sorted(p for p in serial.iterdir() if p.is_dir())
    return out


def to_prune(names, now: float, keep_files: int = KEEP_FILES, keep_days: int = KEEP_DAYS) -> list[str]:
    """The names pruning deletes from one app folder, in name order — the drivers' rule (jsonui-test-runner
    specs/vectors/results-prune.json, copied in tests/fixtures/viz/): the newest name of each file key always stays,
    so a test file not rerun keeps its latest result however old and however many others ran since; older names of
    the same key, and names of the earlier shape, go when older than keep_days, then oldest first until at most
    keep_files names remain. A name not of the driver's shape is never chosen. *now* is in seconds."""
    matching = sorted({n for n in names if NAME.match(n)})
    latest: dict[str, str] = {}
    for name in matching:
        key = NAME.match(name).group(1)
        if key:
            latest[key] = name          # sorted: the last one seen is the newest
    kept = set(latest.values())
    replaced = [n for n in matching if n not in kept]
    doomed = {n for n in replaced if (name_time(n) or now) < now - keep_days * 86400}
    remaining = len(matching) - len(doomed)
    for name in replaced:
        if remaining <= keep_files:
            break
        if name not in doomed:
            doomed.add(name)
            remaining -= 1
    return [n for n in matching if n in doomed]


def prune(folder: Path, now: float | None = None) -> int:
    """Remove what to_prune chooses in *folder*. Only names of the driver's shape are ever touched; nothing is
    removed outside *folder* (no recursion)."""
    now = time.time() if now is None else now
    try:
        names = [e.name for e in os.scandir(folder) if e.is_file(follow_symlinks=False) and NAME.match(e.name)]
    except OSError:
        return 0
    doomed = to_prune(names, now)
    removed = 0
    for name in doomed:
        try:
            (folder / name).unlink()
            removed += 1
        except OSError:
            pass
    return removed


def _str(v) -> bool:
    return isinstance(v, str)


def rows(data, path: Path) -> list[dict]:
    """The case rows of one file, or [] when it is not a results file this reader can trust."""
    if not isinstance(data, dict) or data.get("format") != "jsonui-test-results" or data.get("version") != 1:
        return []
    if data.get("platform") not in PLATFORMS or not isinstance(data.get("suites"), list):
        return []
    at = name_time(path.name)
    if at is None:
        return []
    out = []
    for suite in data["suites"]:
        if not isinstance(suite, dict) or not isinstance(suite.get("results"), list):
            continue
        file = suite.get("file") if _str(suite.get("file")) else None
        for row in suite["results"]:
            if not isinstance(row, dict) or not _str(row.get("testName")) or not _str(row.get("caseName")):
                continue
            if row.get("status") not in STATUSES:
                continue
            out.append({"platform": data["platform"], "run": data.get("run") if _str(data.get("run")) else None,
                        "app": data.get("app") if _str(data.get("app")) else None, "file": file,
                        "test": row["testName"], "case": row["caseName"], "status": row["status"],
                        "t": int(at * 1000), "path": str(path)})
    return out


class ResultShelf:
    """Every saved result file under a base, re-read only when a file is new or changed."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self._seen: dict[Path, tuple[int, int, list[dict]]] = {}
        self.bad = 0

    def scan(self) -> list[dict]:
        found: dict[Path, tuple[int, int, list[dict]]] = {}
        for folder in app_folders(self.base):
            try:
                entries = [e for e in os.scandir(folder) if e.is_file(follow_symlinks=False) and NAME.match(e.name)]
            except OSError:
                continue
            for entry in entries:
                path = Path(entry.path)
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                old = self._seen.get(path)
                if old is not None and old[:2] == (st.st_mtime_ns, st.st_size):
                    found[path] = old
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, ValueError):
                    self.bad += 1
                    continue
                got = rows(data, path)
                if not got:
                    self.bad += 1
                found[path] = (st.st_mtime_ns, st.st_size, got)
        self._seen = found
        return [r for _, _, got in found.values() for r in got]


def pull_argv(adb: str, serial: str, dest: Path) -> list[str]:
    return [adb, "-s", serial, "pull", f"{DEVICE_DIR}/.", str(dest)]


def android_dest(base: Path, serial: str) -> Path:
    return base / "android" / sanitize(serial)


async def pull(adb: str, serial: str, base: Path, timeout: float = PULL_TIMEOUT_SEC) -> bool:
    """Copy one device's result folders to the host, then prune the copies. False when the pull did not finish
    (no folder on the device yet, adb failed, or the timeout). Only reads the device."""
    dest = android_dest(base, serial)
    try:
        dest.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(*pull_argv(adb, serial, dest), stdout=asyncio.subprocess.DEVNULL,
                                                    stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    try:
        rc = await asyncio.wait_for(proc.wait(), timeout)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, 9)
        except ProcessLookupError:
            pass
        await proc.wait()
        return False
    for folder in (p for p in dest.iterdir() if p.is_dir()) if dest.is_dir() else []:
        prune(folder)
    return rc == 0
