"""Fetch: the configured channels' new messages into inbox/ (design §1, §2, §4, §7).

mode "api"        the Slack Web API with each workspace's token (auth.test once for the team's URL, then
                  conversations.history from the cursor, and conversations.replies for a fetched message's thread).
                  No LLM. Every call goes through ``api_get``, which a test replaces.
mode "connector"  ``claude -p`` without a screen, reading Slack through the person's Slack connector, asked to print
                  the messages as JSON. The messages then pass through Claude (Anthropic) BEFORE the filter: the
                  config's source._modeNote and the status say so. The command is source.claudeCommand or ``claude``
                  on PATH, run in <orchestrationDir>/.state with only the Slack connector's tools allowed.

A channel never fetched starts from the last schedule.everyHours (24 when the schedule is manual only).
The cursor moves only after a channel's messages are written; a failure leaves it where it was.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import store

SLACK_API = "https://slack.com/api/"
HTTP_TIMEOUT_SEC = 30.0
PAGES_MAX = 50
CONNECTOR_TIMEOUT_SEC = 900.0
CONNECTOR_TOOLS = "mcp__claude_ai_Slack"
# Slack's own notices, not anyone's words.
SKIP_SUBTYPES = {"channel_join", "channel_leave", "channel_topic", "channel_purpose", "channel_name",
                 "channel_archive", "channel_unarchive", "group_join", "group_leave", "pinned_item", "unpinned_item"}


class FetchError(Exception):
    pass


def api_get(method: str, token: str, params: dict) -> dict:
    url = SLACK_API + method + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:  # noqa: S310 — fixed https URL
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        wait = exc.headers.get("Retry-After") if exc.headers else None
        raise FetchError(f"{method}: HTTP {exc.code}" + (f" (retry after {wait} s)" if wait else "")) from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise FetchError(f"{method}: {exc}") from None
    if not isinstance(data, dict) or not data.get("ok"):
        raise FetchError(f"{method}: {data.get('error') if isinstance(data, dict) else 'not JSON'}")
    return data


def first_oldest(cfg: dict, now: float) -> str:
    hours = (cfg.get("schedule") or {}).get("everyHours") or 24
    return f"{now - float(hours) * 3600:.6f}"


def permalink(team_url: str, channel: str, ts: str, thread_ts: str | None = None) -> str:
    if not team_url:
        return ""
    link = f"{team_url.rstrip('/')}/archives/{channel}/p{ts.replace('.', '')}"
    if thread_ts and thread_ts != ts:
        link += f"?thread_ts={thread_ts}&cid={channel}"
    return link


def _write(root: Path, workspace: str, channel: str, message: dict, link: str, via: str) -> bool:
    ts = message.get("ts")
    if not store.valid_ts(ts) or message.get("subtype") in SKIP_SUBTYPES:
        return False
    target = root / store.INBOX / store.file_name(ts, workspace, channel)
    if target.exists():
        return False
    store.write_json(target, {"workspace": workspace, "channel": channel, "ts": ts, "permalink": link,
                              "via": via, "fetchedAt": int(time.time() * 1000), "message": message})
    return True


def fetch_api(cfg: dict, root: Path, get=api_get, now: float | None = None) -> dict:
    """{"fetched": n, "errors": [str]}: one workspace's or channel's failure does not stop the others."""
    now = time.time() if now is None else now
    cursor = store.Cursor(root)
    fetched, errors = 0, []
    for ws in (cfg.get("source") or {}).get("workspaces") or []:
        name, token = ws["name"], ws.get("token") or ""
        if not token:
            errors.append(f"{name}: no token")
            continue
        try:
            team_url = str(get("auth.test", token, {}).get("url") or "")
        except FetchError as exc:
            errors.append(f"{name}: {exc}")
            continue
        for channel in ws.get("channels") or []:
            oldest = cursor.get(name, channel) or first_oldest(cfg, now)
            try:
                messages = _history(get, token, channel, oldest)
                newest = oldest
                for msg in messages:
                    ts = msg.get("ts")
                    if not store.valid_ts(ts) or float(ts) <= float(oldest):
                        continue     # oldest is exclusive: a message already taken (and maybe placed) is not taken again
                    if _write(root, name, channel, msg, permalink(team_url, channel, ts, msg.get("thread_ts")), "api"):
                        fetched += 1
                    if store.valid_ts(ts) and float(ts) > float(newest):
                        newest = ts
                    if msg.get("reply_count") and msg.get("thread_ts") == ts:
                        for reply in _replies(get, token, channel, ts, oldest):
                            if reply.get("ts") == ts:
                                continue
                            if _write(root, name, channel, reply, permalink(team_url, channel, reply.get("ts", ""), ts), "api"):
                                fetched += 1
                if newest != oldest:
                    cursor.set(name, channel, newest)
            except FetchError as exc:
                errors.append(f"{name}/{channel}: {exc}")
    return {"fetched": fetched, "errors": errors}


def _paged(get, method: str, token: str, params: dict) -> list[dict]:
    out, page_cursor = [], ""
    for _ in range(PAGES_MAX):
        got = get(method, token, {**params, **({"cursor": page_cursor} if page_cursor else {})})
        out += [m for m in got.get("messages") or [] if isinstance(m, dict)]
        page_cursor = ((got.get("response_metadata") or {}).get("next_cursor") or "")
        if not got.get("has_more") or not page_cursor:
            break
    return out


def _history(get, token: str, channel: str, oldest: str) -> list[dict]:
    msgs = _paged(get, "conversations.history", token, {"channel": channel, "oldest": oldest, "limit": 200})
    return sorted(msgs, key=lambda m: float(m["ts"]) if store.valid_ts(m.get("ts")) else 0.0)


def _replies(get, token: str, channel: str, thread_ts: str, oldest: str) -> list[dict]:
    return _paged(get, "conversations.replies", token, {"channel": channel, "ts": thread_ts, "oldest": oldest, "limit": 200})


# ---------------------------------------------------------------- connector

def connector_command(cfg: dict) -> str | None:
    given = (cfg.get("source") or {}).get("claudeCommand")
    if isinstance(given, str) and given:
        path = os.path.expanduser(given)
        return path if os.path.isabs(path) and os.access(path, os.X_OK) else None
    return shutil.which("claude")


def connector_prompt(cfg: dict, root: Path, now: float) -> str:
    cursor = store.Cursor(root)
    lines = []
    for ws in (cfg.get("source") or {}).get("workspaces") or []:
        for channel in ws.get("channels") or []:
            lines.append(f'- workspace "{ws["name"]}", channel {channel}: messages newer than ts '
                         f'{cursor.get(ws["name"], channel) or first_oldest(cfg, now)}')
    return ("Read these Slack channels with the Slack connector (read only; do not post, react or change anything):\n"
            + "\n".join(lines) +
            "\n\nInclude thread replies. Print ONLY one JSON array, no prose, one object per message: "
            '{"workspace": "<as given>", "channel": "<channel id>", "ts": "<message ts>", "thread_ts": "<or null>", '
            '"user": "<user id or name>", "text": "<the text as written>", "permalink": "<or empty>", '
            '"files": [{"name": "<attached file name>"}]}. Print [] when there is nothing new.')


_ARRAY = re.compile(r"\[[\s\S]*\]")


def parse_connector_output(stdout: str) -> list[dict]:
    try:
        outer = json.loads(stdout)
        text = outer.get("result") if isinstance(outer, dict) else stdout
    except ValueError:
        text = stdout
    if not isinstance(text, str):
        raise FetchError("connector: no result text")
    m = _ARRAY.search(text)
    if not m:
        raise FetchError("connector: no JSON array in the answer")
    try:
        items = json.loads(m.group(0))
    except ValueError:
        raise FetchError("connector: the array is not JSON") from None
    if not isinstance(items, list):
        raise FetchError("connector: not an array")
    return [i for i in items if isinstance(i, dict)]


def fetch_connector(cfg: dict, root: Path, run=subprocess.run, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    command = connector_command(cfg)
    if not command:
        return {"fetched": 0, "errors": ["connector: claude not found (source.claudeCommand or PATH)"]}
    wanted = {(ws["name"], ch) for ws in (cfg.get("source") or {}).get("workspaces") or [] for ch in ws.get("channels") or []}
    if not wanted:
        return {"fetched": 0, "errors": []}
    try:
        proc = run([command, "-p", connector_prompt(cfg, root, now), "--output-format", "json",
                    "--allowedTools", CONNECTOR_TOOLS], capture_output=True, text=True,
                   timeout=CONNECTOR_TIMEOUT_SEC, cwd=str(root / store.STATE), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"fetched": 0, "errors": [f"connector: no answer in {CONNECTOR_TIMEOUT_SEC:g} s"]}
    except OSError as exc:
        return {"fetched": 0, "errors": [f"connector: {exc}"]}
    if proc.returncode != 0:
        return {"fetched": 0, "errors": [f"connector: claude exited {proc.returncode}"]}
    try:
        items = parse_connector_output(proc.stdout or "")
    except FetchError as exc:
        return {"fetched": 0, "errors": [str(exc)]}
    cursor, fetched, newest = store.Cursor(root), 0, {}
    for item in items:
        key = (item.get("workspace"), item.get("channel"))
        if key not in wanted or not store.valid_ts(item.get("ts")):
            continue
        before = cursor.get(*key)
        if before is not None and float(item["ts"]) <= float(before):
            continue     # already taken: the model may repeat what the cursor has passed
        message = {k: item.get(k) for k in ("ts", "thread_ts", "user", "text") if item.get(k) is not None}
        if isinstance(item.get("files"), list):
            message["files"] = [f for f in item["files"] if isinstance(f, dict)]
        if _write(root, key[0], key[1], message, str(item.get("permalink") or ""), "connector"):
            fetched += 1
        ts = item.get("ts")
        if store.valid_ts(ts) and (key not in newest or float(ts) > float(newest[key])):
            newest[key] = ts
    for (workspace, channel), ts in newest.items():
        cursor.set(workspace, channel, ts)
    return {"fetched": fetched, "errors": []}


def fetch(cfg: dict, root: Path, **kw) -> dict:
    store.ensure(root)
    if (cfg.get("source") or {}).get("mode") == "connector":
        return fetch_connector(cfg, root, **{k: v for k, v in kw.items() if k in ("run", "now")})
    return fetch_api(cfg, root, **{k: v for k, v in kw.items() if k in ("get", "now")})
