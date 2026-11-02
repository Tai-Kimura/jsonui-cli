"""Socket Mode (source.mode "socket"): Slack pushes each message to ``jui viz serve`` as it is written.

Per workspace with an appToken (xapp-…, the app's connections:write): apps.connections.open -> a WebSocket (aiohttp's
client). Every envelope is acknowledged at once ({"envelope_id"}), before anything else is done with it. A
``disconnect`` (refresh_requested, warning) reconnects at once; a connection that fails or drops reconnects after
BACKOFF_SEC[attempt] (the attempts start again after a ``hello``); ``link_disabled`` (Socket Mode turned off in the
app) waits the longest step.

An events_api envelope whose event is a message (channel_type channel, group, im or mpim) in one of that workspace's
channels is written to inbox/ the way a fetch writes one (fetch.write_message: the same file, the same dedupe by
channel + ts), so it takes the same road: filter -> router -> projects/ | _unsorted/ (attachments dropped and secrets
masked before anything leaves the machine). Slack's notices and edits/deletions (a subtype in SKIP_SUBTYPES) are
not taken. The schedule still fetches through the Web API in this mode (the workspace's token), to pick up what a
dropped connection missed; a message taken here is not taken again there.

The state the status shows (State.public): connected, since, lastEventAt, error, errorAt. No token, no text.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Awaitable, Callable

import aiohttp

from . import fetch as F

OPEN_METHOD = "apps.connections.open"
CHANNEL_TYPES = {"channel", "group", "im", "mpim"}
#: Edits and deletions arrive as message events too; they are not new words.
SKIP_SUBTYPES = F.SKIP_SUBTYPES | {"message_changed", "message_deleted", "message_replied"}
BACKOFF_SEC = (1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
HTTP_TIMEOUT_SEC = 30.0
HEARTBEAT_SEC = 30.0


class SocketError(Exception):
    pass


def now_ms() -> int:
    return int(time.time() * 1000)


class State:
    def __init__(self) -> None:
        self.connected = False
        self.since: int | None = None
        self.last_event_at: int | None = None
        self.error: str | None = None
        self.error_at: int | None = None

    def fail(self, text: str) -> None:
        self.error, self.error_at = text, now_ms()

    def public(self) -> dict:
        return {"connected": self.connected, "since": self.since, "lastEventAt": self.last_event_at,
                "error": self.error, "errorAt": self.error_at}


def wanted_message(event, channels) -> bool:
    """A message event the intake takes: a person's (or a bot's) new words in one of the workspace's channels."""
    return (isinstance(event, dict) and event.get("type") == "message"
            and event.get("channel_type") in CHANNEL_TYPES
            and isinstance(event.get("channel"), str) and event["channel"] in channels
            and event.get("subtype") not in SKIP_SUBTYPES
            and F.store.valid_ts(event.get("ts")))


class Client:
    """One workspace's connection. ``on_message(workspace, event)`` is awaited for each wanted message (after its
    ack); ``on_change()`` is called whenever the state changes."""

    def __init__(self, workspace: dict, on_message: Callable[[str, dict], Awaitable[None]],
                 on_change: Callable[[], None] | None = None, *, api_base: str = F.SLACK_API,
                 backoff: tuple[float, ...] = BACKOFF_SEC):
        self.name = str(workspace.get("name"))
        self.app_token = str(workspace.get("appToken") or "")
        self.channels = set(workspace.get("channels") or [])
        self.on_message = on_message
        self.on_change = on_change or (lambda: None)
        self.api_base = api_base
        self.backoff = backoff
        self.state = State()
        self.attempt = 0
        self.acked = 0

    def _changed(self) -> None:
        try:
            self.on_change()
        except Exception:  # noqa: BLE001 — the status is a view; a failing view never stops the connection
            pass

    async def _open(self, session: aiohttp.ClientSession) -> str:
        try:
            async with session.post(self.api_base + OPEN_METHOD, headers={"Authorization": f"Bearer {self.app_token}"},
                                    timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SEC)) as resp:
                if resp.status != 200:
                    raise SocketError(f"{OPEN_METHOD}: HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            raise SocketError(f"{OPEN_METHOD}: {exc or type(exc).__name__}") from None
        if not isinstance(data, dict) or not data.get("ok") or not isinstance(data.get("url"), str):
            raise SocketError(f"{OPEN_METHOD}: {data.get('error') if isinstance(data, dict) else 'not JSON'}")
        return data["url"]

    async def run_once(self, session: aiohttp.ClientSession) -> float:
        """One connection, until it ends. Returns how long to wait before the next one."""
        if not self.app_token:
            self.state.fail("no appToken")
            self._changed()
            return self.backoff[-1]
        url = await self._open(session)
        reason = None
        async with session.ws_connect(url, heartbeat=HEARTBEAT_SEC) as ws:
            async for frame in ws:
                if frame.type != aiohttp.WSMsgType.TEXT:
                    if frame.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
                    continue
                try:
                    data = json.loads(frame.data)
                except ValueError:
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("envelope_id"):
                    await ws.send_str(json.dumps({"envelope_id": data["envelope_id"]}))   # at once, before the work
                    self.acked += 1
                kind = data.get("type")
                if kind == "hello":
                    self.state.connected, self.state.since, self.state.error = True, now_ms(), None
                    self.attempt = 0
                    self._changed()
                elif kind == "disconnect":
                    reason = str(data.get("reason") or "")
                    break
                elif kind == "events_api":
                    event = (data.get("payload") or {}).get("event") if isinstance(data.get("payload"), dict) else None
                    if wanted_message(event, self.channels):
                        self.state.last_event_at = now_ms()
                        await self.on_message(self.name, event)
                        self._changed()
        self.state.connected = False
        if reason == "link_disabled":
            self.state.fail("disconnect: link_disabled (Socket Mode is off for the app)")
            self._changed()
            return self.backoff[-1]
        if reason is not None:
            self._changed()
            return 0.0           # refresh_requested, warning: Slack asks for a new connection now
        self.state.fail("the connection closed")
        self._changed()
        return self._next_backoff()

    def _next_backoff(self) -> float:
        delay = self.backoff[min(self.attempt, len(self.backoff) - 1)]
        self.attempt += 1
        return delay

    async def run(self) -> None:
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    delay = await self.run_once(session)
                except asyncio.CancelledError:
                    raise
                except (SocketError, aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                    self.state.connected = False
                    self.state.fail(str(exc) or type(exc).__name__)
                    self._changed()
                    delay = self._next_backoff()
                if delay:
                    await asyncio.sleep(delay)


def plan(cfg: dict | None) -> dict[str, tuple]:
    """{workspace: what its connection depends on}: a change (or socket mode off) restarts or stops it."""
    src = (cfg or {}).get("source") or {}
    if src.get("mode") != "socket":
        return {}
    return {str(ws["name"]): (str(ws.get("appToken") or ""), tuple(ws.get("channels") or []), str(ws.get("token") or ""))
            for ws in src.get("workspaces") or [] if isinstance(ws, dict) and ws.get("name")}
