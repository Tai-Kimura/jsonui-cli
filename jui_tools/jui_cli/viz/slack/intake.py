"""The intake: the watcher over inbox/, the schedule, and the status the viz shows (design §1, §7).

process_inbox  each inbox/ file, oldest first: filter adapter -> router adapter -> projects/<id>/ | _unsorted/ |
               deleted (chitchat: nothing written, nothing logged). The inbox file is deleted only after the result
               is written. A filter failure keeps the file in inbox/ and routes nothing; it is tried again when the
               filter config (or the adapter file) changes, or on a fetch asked by hand. A router failure keeps the
               file too and is tried again after RETRY_SEC (or on a fetch asked by hand).
next_run       the schedule: slots every schedule.everyHours hours anchored on schedule.at (local time); a slot
               missed while the server was down runs at once. everyHours 0 = by hand only.
Service        the asyncio side for ``jui viz serve``: one loop polls inbox/ every WATCH_SEC and runs the schedule;
               fetch_now() is the API's 今すぐ取る. The work (HTTP, the child adapters, claude) runs off the loop.

slack.json is only read here (stage 2/3 write router.prompt and taskPrompt); it is read again on every pass, so an
edit applies without a restart. The state the intake keeps is <orchestrationDir>/.state/status.json.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable

from . import config as C
from . import fetch as F
from . import filters, routers, store

WATCH_SEC = 2.0
RETRY_SEC = 600.0
ERRORS_KEPT = 20


def now_ms() -> int:
    return int(time.time() * 1000)


def _filter_fingerprint(filter_cfg: dict) -> str:
    raw = json.dumps(filter_cfg or {}, sort_keys=True, ensure_ascii=False)
    adapter = (filter_cfg or {}).get("adapter") or "builtin"
    if adapter != "builtin":
        try:
            raw += f"|{os.stat(os.path.expanduser(adapter)).st_mtime_ns}"
        except OSError:
            raw += "|missing"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class Status:
    """<orchestrationDir>/.state/status.json: {lastRun, failed: {name: {...}}, errors: [...], lastProcessed}."""

    def __init__(self, root: Path):
        self.path = root / store.STATE / "status.json"
        got = store.read_json(self.path, {})
        self.data: dict = got if isinstance(got, dict) else {}
        self.data.setdefault("failed", {})
        self.data.setdefault("errors", [])

    def save(self) -> None:
        store.write_json(self.path, self.data)

    def error(self, text: str) -> None:
        self.data["errors"] = ([{"at": now_ms(), "error": text}] + self.data["errors"])[:ERRORS_KEPT]


def process_inbox(cfg: dict, root: Path, *, force: bool = False, now: float | None = None,
                  route=routers.route, apply_filter=filters.apply) -> dict:
    """{"projects": n, "unsorted": n, "chitchat": n, "failed": n, "waiting": n} for this pass."""
    now = time.time() if now is None else now
    store.ensure(root)
    status = Status(root)
    failed: dict = status.data["failed"]
    filter_cfg = cfg.get("filter") or {}
    router_cfg = cfg.get("router") or {}
    fp = _filter_fingerprint(filter_cfg)
    known = set(router_cfg.get("prompt", {}).get("projects") or {})
    out = {"projects": 0, "unsorted": 0, "chitchat": 0, "failed": 0, "waiting": 0}
    seen = set()
    for path in store.inbox_files(root):
        name = path.name
        seen.add(name)
        prior = failed.get(name)
        if prior and not force:
            if prior.get("stage") == "filter" and prior.get("fingerprint") == fp:
                out["waiting"] += 1
                continue
            if prior.get("stage") == "router" and now < prior.get("retryAt", 0) / 1000:
                out["waiting"] += 1
                continue
        record = store.read_json(path)
        if not isinstance(record, dict):
            failed[name] = {"stage": "read", "error": "not a JSON object", "at": now_ms(), "fingerprint": fp}
            out["failed"] += 1
            continue
        try:
            message = apply_filter(record, filter_cfg)
        except filters.FilterError as exc:
            failed[name] = {"stage": "filter", "error": str(exc), "at": now_ms(), "fingerprint": fp}
            status.error(f"filter: {name}: {exc}")
            out["failed"] += 1
            continue
        try:
            verdict = route(message, router_cfg)
        except routers.RouterError as exc:
            failed[name] = {"stage": "router", "error": str(exc), "at": now_ms(), "retryAt": int((now + RETRY_SEC) * 1000)}
            status.error(f"router: {name}: {exc}")
            out["failed"] += 1
            continue
        message["router"] = verdict
        choice = verdict["choice"]
        if choice == routers.CHITCHAT and verdict["confidence"] >= router_cfg.get("confidenceMin", 0.6):
            out["chitchat"] += 1     # nothing written, nothing logged
        elif choice in known and C.safe_name(choice) and verdict["confidence"] >= router_cfg.get("confidenceMin", 0.6):
            store.write_json(root / store.PROJECTS / choice / name, message)
            out["projects"] += 1
        else:
            store.write_json(root / store.UNSORTED / name, message)
            out["unsorted"] += 1
        path.unlink(missing_ok=True)
        failed.pop(name, None)
    for name in list(failed):
        if name not in seen:
            failed.pop(name)
    status.data["lastProcessed"] = {"at": now_ms(), **out}
    status.save()
    return out


def next_run(last_ms: int | None, now: float, schedule: dict) -> float | None:
    """Epoch seconds of the next scheduled fetch (<= now means due now), or None when by hand only."""
    every = float((schedule or {}).get("everyHours") or 0)
    at = C.parse_at((schedule or {}).get("at")) or (9, 0)
    if every <= 0:
        return None
    step = every * 3600
    today = dt.datetime.fromtimestamp(now).replace(hour=at[0], minute=at[1], second=0, microsecond=0).timestamp()
    if last_ms is None:
        k = -(-(now - today) // step)        # the first slot at or after now
        return today + k * step
    last = last_ms / 1000
    k = (last - today) // step + 1           # the first slot after the last run
    return today + k * step


def schedule_base(status: "Status | None") -> int | None:
    """What the schedule counts from: the last run, else when the intake first saw the folder."""
    if status is None:
        return None
    return (status.data.get("lastRun") or {}).get("at") or status.data.get("since")


def start_schedule(root: Path) -> None:
    store.ensure(root)
    status = Status(root)
    status.data.setdefault("since", now_ms())
    status.save()


def run_once(cfg: dict, root: Path, trigger: str, **kw) -> dict:
    """Fetch, then process inbox/ (a fetch by hand also retries the failed files). Records lastRun."""
    got = F.fetch(cfg, root, **{k: v for k, v in kw.items() if k in ("get", "run", "now")})
    status = Status(root)
    status.data["lastRun"] = {"at": now_ms(), "trigger": trigger, "mode": (cfg.get("source") or {}).get("mode"),
                              "fetched": got["fetched"], "errors": got["errors"][:ERRORS_KEPT]}
    for err in got["errors"]:
        status.error(f"fetch: {err}")
    status.save()
    processed = process_inbox(cfg, root, force=(trigger == "manual"),
                              **{k: v for k, v in kw.items() if k in ("route", "apply_filter", "now")})
    return {"fetched": got["fetched"], "errors": got["errors"], **processed}


def snapshot(cfg: dict | None, cfg_error: str | None, running: bool, now: float | None = None) -> dict:
    """The `slack` slice and GET /api/slack/status: no key, no message text."""
    now = time.time() if now is None else now
    if cfg_error:
        return {"configured": False, "error": cfg_error, "running": running, "configPath": str(C.path())}
    if cfg is None:
        return {"configured": False, "running": running, "configPath": str(C.path())}
    root = C.orchestration_dir(cfg)
    status = Status(root) if (root / store.STATE).is_dir() else None
    last = (status.data.get("lastRun") if status else None) or None
    nxt = next_run(schedule_base(status), now, cfg.get("schedule") or {})
    mode = (cfg.get("source") or {}).get("mode")
    failed = (status.data.get("failed") if status else {}) or {}
    return {
        "configured": True, "running": running, "configPath": str(C.path()),
        "orchestrationDir": str(root), "mode": mode,
        "modeNote": C.mode_note() if mode == "connector" else None,
        "filterAdapter": (cfg.get("filter") or {}).get("adapter") or "builtin",
        "routerAdapter": (cfg.get("router") or {}).get("adapter") or "haiku",
        "schedule": cfg.get("schedule"),
        "lastRun": last, "nextRun": int(nxt * 1000) if nxt is not None else None,
        "counts": store.counts(root),
        "failed": [{"file": k, "stage": v.get("stage"), "error": v.get("error"), "at": v.get("at")} for k, v in sorted(failed.items())],
        "errors": (status.data.get("errors") if status else []) or [],
        "lastProcessed": status.data.get("lastProcessed") if status else None,
    }


class Service:
    """The intake inside ``jui viz serve``. on_change(snapshot) is called on the loop after anything changes."""

    def __init__(self, on_change: Callable[[dict], None] | None = None, *, watch_sec: float = WATCH_SEC,
                 loader: Callable[[], dict | None] = C.load, work_kw: dict | None = None):
        self.on_change = on_change
        self.watch_sec = watch_sec
        self.loader = loader
        self.work_kw = work_kw or {}
        self.running = False
        self._last: dict | None = None
        self._task: asyncio.Task | None = None

    def _config(self) -> tuple[dict | None, str | None]:
        try:
            return self.loader(), None
        except C.ConfigError as exc:
            return None, str(exc)

    def status(self) -> dict:
        cfg, err = self._config()
        return snapshot(cfg, err, self.running)

    def _publish(self) -> None:
        snap = self.status()
        if snap != self._last:
            self._last = snap
            if self.on_change:
                self.on_change(snap)

    async def fetch_now(self, trigger: str = "manual", reserved: bool = False) -> tuple[int, dict]:
        """(status code, body): 409 while a fetch runs, 409 without a usable config. ``reserved``: start_fetch has
        already set ``running`` (so a second press made before this task runs is refused)."""
        if self.running and not reserved:
            return 409, {"error": "a fetch is running"}
        cfg, err = self._config()
        if cfg is None:
            self.running = False
            return 409, {"error": err or f"no {C.path()}"}
        self.running = True
        self._publish()
        try:
            got = await asyncio.get_running_loop().run_in_executor(
                None, lambda: run_once(cfg, C.orchestration_dir(cfg), trigger, **self.work_kw))
            return 200, got
        finally:
            self.running = False
            self._publish()

    def start_fetch(self) -> tuple[int, dict]:
        """The API's 今すぐ取る: start a fetch on the loop and answer at once (202), or why not (409)."""
        if self.running:
            return 409, {"error": "a fetch is running"}
        cfg, err = self._config()
        if cfg is None:
            return 409, {"error": err or f"no {C.path()}"}
        self.running = True    # at once: the task below runs later, and a second press must see it
        self._task = asyncio.get_running_loop().create_task(self.fetch_now("manual", reserved=True))
        return 202, {"started": True}

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            cfg, _err = self._config()
            if cfg is not None and not self.running:
                root = C.orchestration_dir(cfg)
                status = Status(root) if (root / store.STATE).is_dir() else None
                base = schedule_base(status)
                nxt = next_run(base, time.time(), cfg.get("schedule") or {})
                if base is None:
                    # never run: make the folders and note when the schedule starts counting
                    await loop.run_in_executor(None, lambda: start_schedule(root))
                elif nxt is not None and nxt <= time.time():
                    await self.fetch_now("schedule")
                elif store.inbox_files(root):
                    kw = {k: v for k, v in self.work_kw.items() if k in ("route", "apply_filter")}
                    await loop.run_in_executor(None, lambda: process_inbox(cfg, root, **kw))
            self._publish()
            await asyncio.sleep(self.watch_sec)
