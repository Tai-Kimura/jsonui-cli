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
               With source.mode "socket" it also keeps one Socket Mode connection per workspace (socket_mode.py),
               started, restarted and stopped as slack.json changes; a message pushed there is written to inbox/
               and the loop is woken to process it at once.

slack.json is only read here (stage 2/3 write router.prompt and taskPrompt); it is read again on every pass, so an
edit applies without a restart. The state the intake keeps is <orchestrationDir>/.state/status.json.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Callable

from . import config as C
from . import fetch as F
from . import filters, routers, socket_mode, store

WATCH_SEC = 2.0
RETRY_SEC = 600.0
ERRORS_KEPT = 20

#: What the intake is doing this moment, for the sorting factory's robot (slack_room.py reads it on its 2 s pass):
#: {"stage": "fetch" | "filter" | "route", "done", "total", "since"}, {} between passes. Counts only: no path, no text.
#: One left by a pass that raised is dropped after WORK_STALE_SEC (each message sets it again: one route is well under).
_WORK: dict = {"now": {}}
WORK_STALE_SEC = 300


def now_ms() -> int:
    return int(time.time() * 1000)


def work() -> dict:
    now = _WORK["now"]
    return dict(now) if now and now_ms() - now["since"] < WORK_STALE_SEC * 1000 else {}


def _work(stage: str | None, done: int = 0, total: int = 0) -> None:
    _WORK["now"] = {"stage": stage, "done": done, "total": total, "since": now_ms()} if stage else {}


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
        """Newest first, at most ERRORS_KEPT. The same text again is one entry: its count grows, its ``at`` moves to
        now (``firstAt`` keeps the first), and it comes to the front, so one error repeating every pass never pushes
        the others out."""
        at = now_ms()
        errors = [e for e in self.data["errors"] if isinstance(e, dict)]
        same = next((e for e in errors if e.get("error") == text), None)
        entry = {"at": at, "error": text, "count": 1, "firstAt": at}
        if same is not None:
            errors.remove(same)
            entry["count"] = int(same.get("count") or 1) + 1
            entry["firstAt"] = same.get("firstAt") or same.get("at") or at
        self.data["errors"] = ([entry] + errors)[:ERRORS_KEPT]


def process_inbox(cfg: dict, root: Path, *, force: bool = False, now: float | None = None,
                  route=routers.route, apply_filter=filters.apply) -> dict:
    """{"projects", "unsorted", "chitchat", "failed", "waiting", "followed"}: counts of this pass (followed: replies
    sent where their thread went, also counted in projects or unsorted)."""
    now = time.time() if now is None else now
    store.ensure(root)
    status = Status(root)
    failed: dict = status.data["failed"]
    filter_cfg = cfg.get("filter") or {}
    router_cfg = cfg.get("router") or {}
    fp = _filter_fingerprint(filter_cfg)
    known = set(router_cfg.get("prompt", {}).get("projects") or {})
    out = {"projects": 0, "unsorted": 0, "chitchat": 0, "failed": 0, "waiting": 0, "followed": 0}
    routes = store.KeyedState(root, "routes.json")
    watch = F.watch_from(cfg, now)
    if watch is not None:
        routes.prune(watch)
    seen = set()
    files = store.inbox_files(root)
    for k, path in enumerate(files):
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
        if isinstance(record, dict) and _waits_for_parent(record, root):
            out["waiting"] += 1      # its thread's first message is still in the inbox (failed or not yet read)
            continue
        if not isinstance(record, dict):
            failed[name] = {"stage": "read", "error": "not a JSON object", "at": now_ms(), "fingerprint": fp}
            out["failed"] += 1
            continue
        _work("filter", k, len(files))
        try:
            message = apply_filter(record, filter_cfg)
        except Exception as exc:  # noqa: BLE001 — any failure keeps this file and lets the others through
            failed[name] = {"stage": "filter", "error": _said(exc, filters.FilterError), "at": now_ms(), "fingerprint": fp}
            status.error(f"filter: {name}: {_said(exc, filters.FilterError)}")
            out["failed"] += 1
            continue
        conf_min = router_cfg.get("confidenceMin", 0.6)
        thread_key = store.KeyedState.key(str(message["workspace"]), str(message["channel"]), str(message["threadTs"]))
        is_reply = message["threadTs"] != message["ts"]
        followed = routes.get(thread_key) if is_reply else None
        if isinstance(followed, dict) and (followed.get("to") == store.UNSORTED or followed.get("to") in known):
            # a reply goes where its thread went, without the router
            verdict = {"adapter": "thread", "choice": followed.get("choice"), "confidence": followed.get("confidence")}
            to = followed["to"]
            out["followed"] += 1
        else:
            # a thread's first message, or a reply whose thread was chitchat (never recorded) or is not known
            _work("route", k, len(files))
            try:
                verdict = route(message, router_cfg)
                choice, confidence = verdict["choice"], float(verdict["confidence"])
            except Exception as exc:  # noqa: BLE001 — retried later; the next message is not held up
                failed[name] = {"stage": "router", "error": _said(exc, routers.RouterError), "at": now_ms(),
                                "retryAt": int((now + RETRY_SEC) * 1000)}
                status.error(f"router: {name}: {_said(exc, routers.RouterError)}")
                out["failed"] += 1
                continue
            if choice == routers.CHITCHAT and verdict["confidence"] >= conf_min:
                to = None
            elif choice in known and C.safe_name(choice) and verdict["confidence"] >= conf_min:
                to = choice
            else:
                to = store.UNSORTED
            if to is not None:
                routes.set(thread_key, {"to": to, "choice": choice, "confidence": verdict["confidence"]})
        message["router"] = verdict
        if to is None:
            out["chitchat"] += 1     # nothing written, nothing logged
        elif to == store.UNSORTED:
            store.write_json(root / store.UNSORTED / name, message)
            out["unsorted"] += 1
        else:
            store.write_json(root / store.PROJECTS / to / name, message)
            out["projects"] += 1
        routes.save()
        path.unlink(missing_ok=True)
        failed.pop(name, None)
    for name in list(failed):
        if name not in seen:
            failed.pop(name)
    routes.save()
    _work(None)
    status.data["lastProcessed"] = {"at": now_ms(), **out}
    status.save()
    return out


def _said(exc: BaseException, expected: type) -> str:
    """An adapter's own error as it said it; anything else with its type, since it is a fault, not an answer."""
    return str(exc) if isinstance(exc, expected) else f"unexpected {type(exc).__name__}: {exc}"


def record_error(root: Path, text: str) -> None:
    try:
        store.ensure(root)
        status = Status(root)
        status.error(text)
        status.save()
    except OSError:
        pass       # the folder cannot be written: nothing else can be either, and the loop goes on


def _waits_for_parent(record: dict, root: Path) -> bool:
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    parent = message.get("thread_ts")
    if not store.valid_ts(parent) or parent == record.get("ts"):
        return False
    name = store.file_name(parent, str(record.get("workspace")), str(record.get("channel")))
    return (root / store.INBOX / name).exists()


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
    _work("fetch")
    try:
        got = F.fetch(cfg, root, **{k: v for k, v in kw.items() if k in ("get", "run", "now")})
    finally:
        _work(None)
    status = Status(root)
    status.data["lastRun"] = {"at": now_ms(), "trigger": trigger, "mode": (cfg.get("source") or {}).get("mode"),
                              "fetched": got["fetched"], "errors": got["errors"][:ERRORS_KEPT]}
    for err in got["errors"]:
        status.error(f"fetch: {err}")
    status.save()
    processed = process_inbox(cfg, root, force=(trigger == "manual"),
                              **{k: v for k, v in kw.items() if k in ("route", "apply_filter", "now")})
    return {"fetched": got["fetched"], "errors": got["errors"], **processed}


def snapshot(cfg: dict | None, cfg_error: str | None, running: bool, now: float | None = None,
             sockets: dict | None = None) -> dict:
    """The `slack` slice and GET /api/slack/status: no key, no message text, no path under the home (written from ~,
    the way every slice writes one: the talk e2e reads /api/snapshot for the home's path). ``sockets``: with mode
    socket, {workspace: {connected, since, lastEventAt, error, errorAt}} (socket_mode.State.public)."""
    snap = _snapshot(cfg, cfg_error, running, now)
    if snap.get("mode") == "socket":
        snap["socket"] = sockets or {}
    return _from_tilde(snap)


#: A Slack or Anthropic key's shape: never in an error the page shows (a fetch error is Slack's words, but kept safe).
KEY_SHAPE = re.compile(r"\b(?:xox[a-z]-|xapp-|sk-ant-)[A-Za-z0-9_-]+")


def _from_tilde(value):
    if isinstance(value, str):
        home = str(Path.home()).rstrip(os.sep)
        value = KEY_SHAPE.sub("…", value)
        return re.sub(re.escape(home) + r"(?![\w.-])", "~", value) if home else value
    if isinstance(value, dict):
        return {k: _from_tilde(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_tilde(v) for v in value]
    return value


def _snapshot(cfg: dict | None, cfg_error: str | None, running: bool, now: float | None = None) -> dict:
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
                 loader: Callable[[], dict | None] = C.load, work_kw: dict | None = None,
                 socket_kw: dict | None = None):
        self.on_change = on_change
        self.watch_sec = watch_sec
        self.loader = loader
        self.work_kw = work_kw or {}
        self.running = False
        self._last: dict | None = None
        self._task: asyncio.Task | None = None
        self.socket_kw = socket_kw or {}       # socket_mode.Client's api_base / backoff (a test's fake server)
        self.sockets: dict[str, tuple[tuple, socket_mode.Client, asyncio.Task]] = {}
        self._team_urls: dict[str, str] = {}
        self._wake: asyncio.Event | None = None

    def _config(self) -> tuple[dict | None, str | None]:
        try:
            return self.loader(), None
        except C.ConfigError as exc:
            return None, str(exc)

    def status(self) -> dict:
        cfg, err = self._config()
        return snapshot(cfg, err, self.running, sockets={n: c.state.public() for n, (_k, c, _t) in self.sockets.items()})

    # ---------------------------------------------------------------- Socket Mode

    def _reconcile_sockets(self, cfg: dict | None) -> None:
        """One connection per workspace while mode is socket; a workspace whose appToken, channels or token changed
        is reconnected, one gone (or mode no longer socket) is closed."""
        want = socket_mode.plan(cfg)
        for name in list(self.sockets):
            key, _client, task = self.sockets[name]
            if want.get(name) != key or task.done():
                task.cancel()
                del self.sockets[name]
                self._team_urls.pop(name, None)
        workspaces = {str(ws.get("name")): ws for ws in ((cfg or {}).get("source") or {}).get("workspaces") or []
                      if isinstance(ws, dict)}
        for name, key in want.items():
            if name not in self.sockets:
                client = socket_mode.Client(workspaces[name], self._on_socket_message, self._publish, **self.socket_kw)
                self.sockets[name] = (key, client, asyncio.get_running_loop().create_task(client.run()))

    def _stop_sockets(self) -> None:
        for _key, _client, task in self.sockets.values():
            task.cancel()
        self.sockets.clear()

    async def _on_socket_message(self, workspace: str, event: dict) -> None:
        cfg, _err = self._config()
        if cfg is None or (cfg.get("source") or {}).get("mode") != "socket":
            return
        ws = next((w for w in cfg["source"].get("workspaces") or [] if isinstance(w, dict) and w.get("name") == workspace), None)
        if ws is None or event.get("channel") not in (ws.get("channels") or []):
            return
        root = C.orchestration_dir(cfg)
        get = self.work_kw.get("get", F.api_get)

        def write() -> bool:
            store.ensure(root)
            url = self._team_urls.get(workspace)
            if url is None and ws.get("token"):
                try:
                    url = str(get("auth.test", ws["token"], {}).get("url") or "")
                    self._team_urls[workspace] = url
                except F.FetchError:
                    url = ""       # asked again with the next message
            link = F.permalink(url or "", event["channel"], event["ts"], event.get("thread_ts"))
            return F.write_message(root, workspace, event["channel"], dict(event), link, "socket")

        if await asyncio.get_running_loop().run_in_executor(None, write) and self._wake is not None:
            self._wake.set()       # processed now, not on the next poll

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
        loop = asyncio.get_running_loop()
        try:
            got = await loop.run_in_executor(None, lambda: run_once(cfg, C.orchestration_dir(cfg), trigger, **self.work_kw))
            return 200, got
        except Exception as exc:  # noqa: BLE001 — said on the status; the schedule and the next press go on
            text = f"{trigger} fetch: unexpected {type(exc).__name__}: {exc}"
            await loop.run_in_executor(None, lambda: record_error(C.orchestration_dir(cfg), text))
            return 500, {"error": text}
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
        self._wake = asyncio.Event()
        try:
            await self._loop(loop)
        finally:
            self._stop_sockets()

    async def _loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Every pass; an exception in one is written to status.errors (counted when it repeats) and the next pass
        runs as usual: a long-running serve never stops taking messages over one fault."""
        while True:
            cfg = None
            try:
                cfg, _err = self._config()
                self._reconcile_sockets(cfg)
                await self._pass(cfg, loop)
                self._publish()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                if cfg is not None:
                    text = f"intake: unexpected {type(exc).__name__}: {exc}"
                    await loop.run_in_executor(None, lambda: record_error(C.orchestration_dir(cfg), text))
                try:
                    self._publish()
                except Exception:  # noqa: BLE001 — the view only
                    pass
            try:
                await asyncio.wait_for(self._wake.wait(), self.watch_sec)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def _pass(self, cfg: dict | None, loop: asyncio.AbstractEventLoop) -> None:
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
