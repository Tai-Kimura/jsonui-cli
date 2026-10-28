"""The talk view's data (ticket 2026-10-20-jui-viz-talk-view; plan docs/plans/2026-10-20-jui-viz-talk-view.md): every
SendMessage between the robots on this machine, as conversations of two, read from the transcripts.

What is read (``TalkIndex.step``, always in the talk worker's one thread, never on the event loop):
  * ~/.claude/sessions/<pid>.json (sources/session_files: the ``<digits>.json`` files only, never a ``.key``): which
    sessions are alive, their names, sockets and pids;
  * each live session's transcript ``projects/<folder>/<session id>.jsonl`` and its subagents' ``<session id>/
    subagents/**/agent-<id>.jsonl``: regular files under the projects folder, opened without following a symlink,
    read forwards from where the last read stopped (the first sight reads them from the start: the backfill), at most
    STEP_BYTES / STEP_SEC a step; lines without a needle are not parsed (sources/talk_records.wanted).

The rules (the research at the end of the plan, measured 10-20 on 1,192 transcripts):
  * one message = one row. The sender's tool_use is unique by its id; a send to a session gets ``toolUseResult.msg_id``,
    the same value the receiver's record carries as ``origin.msg_id``: that is the match (never the body, never the
    name). A message with a msg_id is ``m-<msg_id>`` from whichever side is seen first, so both sides land on one row.
    Receiver records written twice (Remote Control re-appends them: 27 in 24 h) and tool_use records written twice
    (45 in 24 h) change nothing the second time: the first record's time stays.
  * no msg_id (a parent's send to its subagent, a subagent's send to ``main``): the receiver's record is matched to
    the sender's row by the receiver, the sender (``senderTaskId``) and the exact body; a record nobody's send matches
    is held until the reading has caught up and it is HOLD_MS old, then becomes a receiver-only row ``r-…``.
    The record's own (receiver, uuid) is kept, so reading it again (a rebuild) never makes a second row.
  * "No agent named … is reachable" and is_error: ``undelivered``, shown with a mark, never matched to another's
    message.
  * a session is alive while a ``~/.claude/sessions/*.json`` names it. One that is not is marked gone (the time it was
    first seen gone; for one never seen alive, its transcript's last write); after the grace (config ``talkGraceSec``,
    the requester's ruling 10-20: 1 h) every conversation it is in is deleted, both sides' lists. Within the grace a
    session that comes back is simply alive again; one that comes back after its talks were deleted gets them back
    from the transcripts (every live session's files are read again from the start; the rules above make that safe).
  * unread (per robot and conversation): messages to that robot after what the page said it saw (``talk.seen``); a
    conversation first indexed while catching up starts as all read, so the first start does not badge the past.

Where it is kept: ``<viz state home>/talk.db`` (SQLite, 0600, its folder 0700): an index of the transcripts, never the
source for native SendMessage. The relays table additionally owns provider-neutral messages and their retry ids;
it survives transcript-index rebuilds. Deleting talk.db also deletes those messages. No path, body or name leaves
this module for a log.
The page's side of it (frames and requests) is talk_contract.json; ``TalkHub`` is the server's half.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from . import i18n, talk_contract
from .calls import peer_name
from .sources import session_files
from .sources.talk_records import observations, wanted
from . import quiet_fs

SCHEMA = 3
LIMITS = talk_contract.limits()
TEXT_MAX = LIMITS["textMax"]
NAME_MAX = LIMITS["nameMax"]
SUMMARY_MAX = LIMITS["summaryMax"]
PREVIEW_MAX = LIMITS["previewMax"]
LIST_MAX = LIMITS["listMax"]
PAGE_MAX = LIMITS["pageMax"]
OPS_MAX = LIMITS["opsMax"]
KEPT = LIMITS["keptPerConversation"]
GRACE_MS_DEFAULT = LIMITS["graceSecDefault"] * 1000
#: One step reads at most this much and works at most this long (the worker answers the page's requests between).
STEP_BYTES = 64 * 1_048_576
STEP_SEC = 0.3
CHUNK = 4 * 1_048_576
#: A receiver's record with no sender seen yet waits this long (the research: send -> read at most 65.8 s).
HOLD_MS = 300_000
#: The enqueue is matched to a send at most this long after it (the research: p90 14.9 s, max 72.3 s).
ARRIVE_MS = 300_000
AGENT_ID = re.compile(r"^a[0-9a-f]{6,40}$")
SID = re.compile(r"^[0-9a-fA-F-]{8,64}$")
_KEY_SAFE = re.compile(r"[^A-Za-z0-9_.:@-]")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:32]


def conv_id(a: str, b: str) -> str:
    lo, hi = sorted((a, b))
    return "t-" + hashlib.sha256(f"{lo}\n{hi}".encode()).hexdigest()[:16]


def _cut(text: str, n: int) -> tuple[str, bool]:
    return (text, False) if len(text) <= n else (text[:n], True)


def _preview(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:PREVIEW_MAX]
    return ""


def external_key(name: str) -> str:
    return "x:" + _KEY_SAFE.sub("_", name)[:180]


class Registry:
    """The live sessions as ~/.claude/sessions says: session id -> name; names, sockets and pids -> session id."""

    def __init__(self, rows: list[dict]) -> None:
        self.names: dict[str, str] = {}
        self.by_name: dict[str, str] = {}
        self.by_sock: dict[str, str] = {}
        self.by_pid: dict[int, str] = {}
        self.alive: set[str] = set()
        for row in rows:
            sid = row.get("sessionId")
            if not isinstance(sid, str) or not SID.match(sid):
                continue
            self.alive.add(sid)
            name = row.get("name")
            if isinstance(name, str) and name:
                self.names[sid] = name[:NAME_MAX]
                self.by_name[name] = sid
            sock = row.get("messagingSocketPath")
            if isinstance(sock, str) and sock:
                self.by_sock[sock] = sid
            pid = row.get("pid")
            if isinstance(pid, int) and not isinstance(pid, bool):
                self.by_pid[pid] = sid

    history: Callable[[str, str], str | None] | None = None   # (kind, value) -> a session id seen before

    def resolve(self, to: str) -> str | None:
        """A send's `to` -> a session id: the live registry first, then the names and sockets seen before."""
        kind, value = ("sock", to[4:]) if to.startswith("uds:") else ("name", peer_name(to))
        got = (self.by_sock if kind == "sock" else self.by_name).get(value)
        if got is None and self.history is not None:
            got = self.history(kind, value)
        return got


_DDL = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS parts(key TEXT PRIMARY KEY, sid TEXT, kind TEXT NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS convs(id TEXT PRIMARY KEY, a TEXT NOT NULL, b TEXT NOT NULL, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
  id TEXT PRIMARY KEY, conv TEXT NOT NULL, sender TEXT NOT NULL, receiver TEXT NOT NULL,
  sender_name TEXT NOT NULL, receiver_name TEXT NOT NULL, at INTEGER NOT NULL, delivered_at INTEGER, read_at INTEGER,
  state TEXT NOT NULL, text TEXT NOT NULL, cut INTEGER NOT NULL, hash TEXT NOT NULL, summary TEXT,
  seen_s INTEGER NOT NULL, seen_r INTEGER NOT NULL, via TEXT NOT NULL, merged INTEGER NOT NULL DEFAULT 0,
  msg_id TEXT, use_id TEXT);
CREATE INDEX IF NOT EXISTS messages_conv ON messages(conv, at, id);
CREATE INDEX IF NOT EXISTS messages_to ON messages(receiver, hash);
CREATE TABLE IF NOT EXISTS seen(owner TEXT NOT NULL, conv TEXT NOT NULL, upto INTEGER NOT NULL, PRIMARY KEY(owner, conv));
CREATE TABLE IF NOT EXISTS sends(use_id TEXT PRIMARY KEY, sid TEXT NOT NULL, sender TEXT NOT NULL, to_ TEXT NOT NULL,
  text TEXT NOT NULL, summary TEXT, kind TEXT, at INTEGER NOT NULL, done TEXT);
CREATE TABLE IF NOT EXISTS held(receiver TEXT NOT NULL, uuid TEXT NOT NULL, sid TEXT NOT NULL, info TEXT NOT NULL,
  at INTEGER NOT NULL, PRIMARY KEY(receiver, uuid));
CREATE TABLE IF NOT EXISTS recv_seen(receiver TEXT NOT NULL, uuid TEXT NOT NULL, sid TEXT NOT NULL, PRIMARY KEY(receiver, uuid));
CREATE TABLE IF NOT EXISTS arrivals(sid TEXT NOT NULL, hash TEXT NOT NULL, at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS arrivals_sid ON arrivals(sid, hash);
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, sid TEXT NOT NULL, agent TEXT, off INTEGER NOT NULL, ino INTEGER);
CREATE TABLE IF NOT EXISTS names(kind TEXT NOT NULL, value TEXT NOT NULL, sid TEXT NOT NULL, PRIMARY KEY(kind, value));
CREATE TABLE IF NOT EXISTS gone(sid TEXT PRIMARY KEY, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS removed(sid TEXT PRIMARY KEY, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS relays(id TEXT PRIMARY KEY, hash TEXT NOT NULL, result TEXT, sender TEXT, receiver TEXT, record TEXT);
"""


def open_db(path: Path) -> sqlite3.Connection:
    """The index at path (0600, its folder 0700), made when missing; an older schema is dropped and made again (the
    transcripts are the source)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("talk.db is not a regular file")
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    try:
        got = db.execute("SELECT v FROM meta WHERE k='schema'").fetchone()
    except sqlite3.Error:
        got = None
    if got is None or got[0] != str(SCHEMA):
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            if name == 'relays':
                continue                         # relay messages have no external transcript to rebuild from
            db.execute(f'DROP TABLE IF EXISTS "{name}"')
        db.executescript(_DDL)
        db.execute("INSERT OR REPLACE INTO meta VALUES('schema', ?)", (str(SCHEMA),))
    else:
        db.executescript(_DDL)
    return db


class TalkIndex:
    """The index and its rules. Every method runs in one thread (TalkHub's worker); nothing here touches the loop."""

    def __init__(self, db_path: Path, projects: Path, sessions_dir: Path, grace_ms: int = GRACE_MS_DEFAULT,
                 registry: Callable[[], list[dict]] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.db = open_db(db_path)
        self.projects = Path(projects)
        self.sessions_dir = Path(sessions_dir)
        self.grace_ms = int(grace_ms)
        self.read_registry = registry or (lambda: session_files.scan(self.sessions_dir))
        self.clock = clock
        self.reg = Registry([])
        self.caught_up = False
        self._live = False
        self._main_paths: dict[str, Path] = {}
        self._skip: set[str] = set()                 # files in the middle of a line too long to keep
        self._pending: set[str] = {r[0] for r in self.db.execute("SELECT use_id FROM sends WHERE done IS NULL")}
        self._changed_msgs: set[str] = set()
        self._changed_convs: set[str] = set()
        self._removed: list[tuple[str, str, str, str]] = []   # (conv, a, b, dead sid)
        self._seen_alive: set[str] = set()           # sessions seen alive by this run (their end is "now")
        for mid, encoded in self.db.execute('SELECT id,record FROM relays WHERE record IS NOT NULL').fetchall():
            if not self._exists('m-jui-' + mid):
                row = json.loads(encoded)
                for member in (row['sender'], row['receiver']):
                    self._session_part(member['id'], member['name'])
                self._insert('m-jui-' + mid, row['sender']['id'], row['receiver']['id'], row['at'], row['text'], row['at'],
                             state='sent' if row['result']['ok'] else 'undelivered', seen_s=1)

    # ------------------------------------------------------------------ one step
    def step(self, now: int, extra: list[dict] | None = None) -> dict:
        """Read the registry and what the transcripts added; apply it; mark and remove the dead. Returns
        {"ops": {owner: [op, ...]}, "badges": {owner: n}, "caughtUp": bool}."""
        self._changed_msgs, self._changed_convs, self._removed = set(), set(), []
        try:
            rows = self.read_registry()
        except OSError:
            rows = []
        self.reg = Registry([*rows, *(extra or [])])
        self.reg.history = self._history
        self._names()
        self._deaths(now)
        self._seen_alive |= self.reg.alive
        self._live = self.caught_up          # caught up before this step: what it reads is new
        obs = self._read(now)
        self.db.execute("BEGIN")
        try:
            self._apply(obs, now)
            self._settle(now)
            self._expire(now)
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"ops": self._ops(now), "badges": self.badges(), "caughtUp": self.caught_up}

    # ------------------------------------------------------------------ the living and the dead
    def _names(self) -> None:
        for sid, name in self.reg.names.items():
            self.db.execute("UPDATE parts SET name=? WHERE key=? AND name<>?", (name, sid, name))
        # the names and sockets seen, so a send to a session that has ended since still finds it
        self.db.executemany("INSERT OR REPLACE INTO names VALUES('name', ?, ?)", [(n, s) for n, s in self.reg.by_name.items()])
        self.db.executemany("INSERT OR REPLACE INTO names VALUES('sock', ?, ?)", [(k, s) for k, s in self.reg.by_sock.items()])

    def _history(self, kind: str, value: str) -> str | None:
        row = self.db.execute("SELECT sid FROM names WHERE kind=? AND value=?", (kind, value)).fetchone()
        return row[0] if row else None

    def _deaths(self, now: int) -> None:
        alive = self.reg.alive
        for (sid, ) in self.db.execute("SELECT sid FROM gone").fetchall():
            if sid in alive:
                self.db.execute("DELETE FROM gone WHERE sid=?", (sid,))
                self._touch_convs_of(sid)
        back = [sid for (sid,) in self.db.execute("SELECT sid FROM removed").fetchall() if sid in alive]
        if back:
            # its talks were deleted: read every live session's files again from the start (the rules make it safe)
            self.db.executemany("DELETE FROM removed WHERE sid=?", [(s,) for s in back])
            self.db.execute("DELETE FROM sends WHERE done='dead'")
            self.db.execute("UPDATE files SET off=0")
            self._skip.clear()
            self.caught_up = False
        known = {r[0] for r in self.db.execute("SELECT DISTINCT sid FROM parts WHERE sid IS NOT NULL")}
        gone = {r[0] for r in self.db.execute("SELECT sid FROM gone")}
        for sid in sorted(k for k in gone if k.startswith("x:")):      # a new message to or from it: kept longer
            last = self._last_at(sid)
            if last is not None:
                self.db.execute("UPDATE gone SET at=? WHERE sid=? AND at<?", (min(now, last), sid, min(now, last)))
        for sid in sorted(known - alive - gone):
            self.db.execute("INSERT OR IGNORE INTO gone VALUES(?, ?)", (sid, self._gone_since(sid, now)))
            self._touch_convs_of(sid)

    def _last_at(self, key: str) -> int | None:
        row = self.db.execute("SELECT MAX(at) FROM messages WHERE sender=? OR receiver=?", (key, key)).fetchone()
        return row[0] if row else None

    def _gone_since(self, sid: str, now: int) -> int:
        """When a session not in the registry ended: now when it was alive a moment ago (seen in this run); otherwise
        its transcript's last write (a session that ended while the server was down), never later than now. A peer
        not on this machine (``x:``, its liveness unknowable here) counts from its conversation's last message."""
        if sid.startswith("x:"):
            return min(now, self._last_at(sid) or now)
        if sid in self._seen_alive:
            return now
        path = self._main_path(sid)
        try:
            return min(now, int(os.stat(path).st_mtime * 1000)) if path else now
        except OSError:
            return now

    def _touch_convs_of(self, sid: str) -> None:
        for (cid,) in self.db.execute(
                "SELECT c.id FROM convs c JOIN parts p ON p.key IN (c.a, c.b) WHERE p.sid=?", (sid,)).fetchall():
            self._changed_convs.add(cid)

    def _expire(self, now: int) -> None:
        for sid, at in self.db.execute("SELECT sid, at FROM gone").fetchall():
            if now - at < self.grace_ms:
                continue
            self._remove_session(sid, now)

    def _remove_session(self, sid: str, now: int) -> None:
        keys = [r[0] for r in self.db.execute("SELECT key FROM parts WHERE sid=?", (sid,))]
        for key in keys:
            for cid, a, b in self.db.execute("SELECT id, a, b FROM convs WHERE a=? OR b=?", (key, key)).fetchall():
                self._removed.append((cid, a, b, key))
                # the other side's records of these messages are read again if this session comes back
                self.db.execute("DELETE FROM sends WHERE done IN (SELECT id FROM messages WHERE conv=?)", (cid,))
                self.db.execute("DELETE FROM messages WHERE conv=?", (cid,))
                self.db.execute("DELETE FROM seen WHERE conv=?", (cid,))
                self.db.execute("DELETE FROM convs WHERE id=?", (cid,))
                self._changed_convs.discard(cid)
        for table, col in (("held", "sid"), ("recv_seen", "sid"), ("sends", "sid"), ("arrivals", "sid")):
            self.db.execute(f"DELETE FROM {table} WHERE {col}=?", (sid,))
        self.db.execute("DELETE FROM parts WHERE sid=?", (sid,))
        self.db.execute('UPDATE relays SET record=NULL WHERE sender=? OR receiver=?', (sid, sid))
        # externals nobody talks to any more
        self.db.execute("DELETE FROM parts WHERE kind='external' AND key NOT IN (SELECT a FROM convs UNION SELECT b FROM convs)")
        self.db.execute("DELETE FROM gone WHERE sid=?", (sid,))
        if not sid.startswith("x:"):         # a peer not on this machine is never shut out: a new message brings it back
            self.db.execute("INSERT OR REPLACE INTO removed VALUES(?, ?)", (sid, now))
        self._pending = {r[0] for r in self.db.execute("SELECT use_id FROM sends WHERE done IS NULL")}

    def _dead(self, sid: str | None) -> bool:
        """A session whose talks were deleted and that has not come back: nothing about it is indexed again."""
        return bool(sid) and not sid.startswith("x:") and sid not in self.reg.alive and self.db.execute(
            "SELECT 1 FROM removed WHERE sid=?", (sid,)).fetchone() is not None

    # ------------------------------------------------------------------ the files
    def _main_path(self, sid: str) -> Path | None:
        path = self._main_paths.get(sid)
        if path is not None:
            return path
        try:
            found = [p for p in self.projects.glob(f"*/{sid}.jsonl") if quiet_fs.is_file(p) and not quiet_fs.is_symlink(p)]
        except OSError:
            found = []
        if found:
            self._main_paths[sid] = found[0]
            return found[0]
        return None

    def _files(self) -> list[tuple[Path, str, str | None]]:
        out = []
        watched = set(self.reg.alive) | {r[0] for r in self.db.execute("SELECT sid FROM gone") if not r[0].startswith("x:")}
        for sid in sorted(watched):
            main = self._main_path(sid)
            if main is None:
                continue
            out.append((main, sid, None))
            subs = main.parent / sid / "subagents"
            if quiet_fs.is_dir(subs) and not quiet_fs.is_symlink(subs):
                for p in sorted(subs.glob("**/agent-*.jsonl")):
                    aid = p.name[len("agent-"):-len(".jsonl")]
                    if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", aid) and not quiet_fs.is_symlink(p):
                        out.append((p, sid, aid))
        return out

    def _open(self, path: Path) -> int | None:
        try:
            if not path.parent.resolve().is_relative_to(self.projects.resolve()):
                return None
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except (OSError, ValueError):
            return None
        try:
            if stat.S_ISREG(os.fstat(fd).st_mode):
                return fd
        except OSError:
            pass
        os.close(fd)
        return None

    def _read(self, now: int) -> list[tuple[str, str | None, tuple]]:
        """New observations from the files, (sid, agent id or None, observation), in the order read."""
        out: list = []
        start, budget, behind = self.clock(), STEP_BYTES, False
        for path, sid, agent in self._files():
            key = str(path)
            row = self.db.execute("SELECT off, ino FROM files WHERE path=?", (key,)).fetchone()
            off, ino = (row if row else (0, None))
            fd = self._open(path)
            if fd is None:
                continue
            try:
                st = os.fstat(fd)
                if (ino is not None and ino != st.st_ino) or st.st_size < off:
                    off = 0                                    # a new file in its place: from the start
                    self._skip.discard(key)
                while off < st.st_size:
                    if budget <= 0 or self.clock() - start >= STEP_SEC:
                        behind = True
                        break
                    chunk = os.pread(fd, min(CHUNK, budget), off)
                    if not chunk:
                        break
                    budget -= len(chunk)
                    if key in self._skip:                      # the rest of a line too long to keep
                        cut = chunk.find(b"\n")
                        if cut < 0:
                            off += len(chunk)
                            continue
                        self._skip.discard(key)
                        off += cut + 1
                        continue
                    end = chunk.rfind(b"\n")
                    if end < 0:
                        if off + len(chunk) >= st.st_size:
                            break                              # an unfinished last line: next step
                        self._skip.add(key)                    # one line longer than CHUNK: not ours to parse
                        off += len(chunk)
                        continue
                    for line in chunk[:end].split(b"\n"):
                        if line and wanted(line, self._pending):
                            try:
                                rec = json.loads(line)
                            except (ValueError, RecursionError):   # a line nested too deep is skipped, not fatal
                                continue
                            try:
                                found = observations(rec)
                            except RecursionError:          # a message too deep to show as JSON: skipped
                                continue
                            for ob in found:
                                if ob[0] == "send":
                                    self._pending.add(ob[1])
                                out.append((sid, agent, ob))
                    off += end + 1
            finally:
                os.close(fd)
            self.db.execute("INSERT OR REPLACE INTO files VALUES(?, ?, ?, ?, ?)", (key, sid, agent, off, st.st_ino))
            if behind:
                break
        self.caught_up = not behind
        return out

    # ------------------------------------------------------------------ applying what was read
    def _apply(self, obs: list, now: int) -> None:
        # the senders' side first: a receiver's record read in the same step then finds its send
        order = {"send": 0, "result": 1, "recv": 2, "arrive": 3}
        for sid, agent, ob in sorted(obs, key=lambda o: order[o[2][0]]):
            if ob[0] == "send":
                self._on_send(sid, agent, ob, now)
            elif ob[0] == "result":
                self._on_result(ob, now)
            elif ob[0] == "recv":
                self._on_recv(sid, agent, ob[1], now)
            else:
                self._on_arrive(sid, ob[1], ob[2], now)

    def _part(self, key: str, sid: str | None, kind: str, name: str | None) -> None:
        row = self.db.execute("SELECT name FROM parts WHERE key=?", (key,)).fetchone()
        if row is None:
            self.db.execute("INSERT INTO parts VALUES(?, ?, ?, ?)", (key, sid, kind, (name or key)[:NAME_MAX]))
        elif name and kind == "session" and self.reg.names.get(key) and row[0] != self.reg.names[key]:
            self.db.execute("UPDATE parts SET name=? WHERE key=?", (self.reg.names[key], key))

    def _session_part(self, sid: str, fallback: str | None = None) -> str:
        self._part(sid, sid, "session", self.reg.names.get(sid) or fallback or i18n.tl("srv.talk.session", id=sid[:8]))
        return sid

    def _sub_part(self, aid: str, sid: str) -> str:
        self._part(aid, sid, "subagent", i18n.tl("srv.talk.subagent", id=aid[:9]))
        return aid

    def _sender_of_file(self, sid: str, agent: str | None) -> str:
        return self._sub_part(agent, sid) if agent else self._session_part(sid)

    def _conv(self, a: str, b: str, first_at: int, now: int) -> str:
        cid = conv_id(a, b)
        if self.db.execute("SELECT 1 FROM convs WHERE id=?", (cid,)).fetchone() is None:
            lo, hi = sorted((a, b))
            self.db.execute("INSERT INTO convs VALUES(?, ?, ?, ?)", (cid, lo, hi, now))
            # read up to now while catching up (the first start does not badge the past); after that, a conversation
            # starts unread from its first message
            upto = now if not self._live else min(now, first_at) - 1
            self.db.executemany("INSERT OR IGNORE INTO seen VALUES(?, ?, ?)", [(lo, cid, upto), (hi, cid, upto)])
        self._changed_convs.add(cid)
        return cid

    def _name_of(self, key: str) -> str:
        row = self.db.execute("SELECT name FROM parts WHERE key=?", (key,)).fetchone()
        return row[0] if row else key[:NAME_MAX]

    def _insert(self, mid: str, sender: str, receiver: str, at: int, text: str, now: int, **fields: Any) -> None:
        cid = self._conv(sender, receiver, at, now)
        body, cut = _cut(text, TEXT_MAX)
        row = {"id": mid, "conv": cid, "sender": sender, "receiver": receiver, "sender_name": self._name_of(sender),
               "receiver_name": self._name_of(receiver), "at": at, "delivered_at": None, "read_at": None,
               "state": "sent", "text": body, "cut": int(cut), "hash": _hash(text), "summary": None, "seen_s": 0,
               "seen_r": 0, "via": "session", "merged": 0, "msg_id": None, "use_id": None}
        row.update(fields)
        cols = ", ".join(row)
        self.db.execute(f"INSERT INTO messages({cols}) VALUES({', '.join('?' * len(row))})", tuple(row.values()))
        self._changed_msgs.add(mid)
        self._prune(cid)

    def _prune(self, cid: str) -> None:
        n = self.db.execute("SELECT COUNT(*) FROM messages WHERE conv=?", (cid,)).fetchone()[0]
        if n > KEPT:
            self.db.execute("UPDATE relays SET record=NULL WHERE 'm-jui-' || id IN "
                            "(SELECT id FROM messages WHERE conv=? ORDER BY at,id LIMIT ?)", (cid, n - KEPT))
            self.db.execute("DELETE FROM messages WHERE id IN (SELECT id FROM messages WHERE conv=? ORDER BY at, id LIMIT ?)",
                            (cid, n - KEPT))

    def _update(self, mid: str, **fields: Any) -> None:
        row = self.db.execute(f"SELECT {', '.join(fields)} FROM messages WHERE id=?", (mid,)).fetchone()
        if row is None:
            return
        change = {k: v for (k, v), old in zip(fields.items(), row) if v != old}
        if change:
            self.db.execute(f"UPDATE messages SET {', '.join(k + '=?' for k in change)} WHERE id=?", (*change.values(), mid))
            self._changed_msgs.add(mid)
            self._changed_convs.add(self.db.execute("SELECT conv FROM messages WHERE id=?", (mid,)).fetchone()[0])

    def _on_send(self, sid: str, agent: str | None, ob: tuple, now: int) -> None:
        _k, use_id, to, text, summary, rk, at = ob
        if self.db.execute("SELECT 1 FROM sends WHERE use_id=?", (use_id,)).fetchone():
            return                                         # the same tool_use written again
        sender = self._sender_of_file(sid, agent)
        self.db.execute("INSERT INTO sends VALUES(?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                        (use_id, sid, sender, to, text, summary, rk, at or now))

    def _receiver_for(self, sid: str, agent: str | None, to: str, rk: str | None) -> tuple[str, str]:
        """(receiver key, via) for a send's `to` as written in the file of (sid, agent)."""
        if to == "main" and agent:
            return self._session_part(sid), "parent"
        if rk == "agent" or AGENT_ID.match(to):
            return self._sub_part(to, sid), "subagent"
        target = self.reg.resolve(to)
        if target:
            return self._session_part(target), "session"
        name = peer_name(to) or to
        key = external_key(name)
        self._part(key, key, "external", name[:NAME_MAX])
        return key, "external"

    def _on_result(self, ob: tuple, now: int) -> None:
        _k, use_id, msg_id, outcome, at = ob
        row = self.db.execute("SELECT sid, sender, to_, text, summary, kind, at, done FROM sends WHERE use_id=?", (use_id,)).fetchone()
        if row is None or row[7] is not None:
            return
        sid, sender, to, text, summary, rk, sent_at, _done = row
        self._pending.discard(use_id)
        agent = sender if sender != sid else None
        if self._dead(sid):
            self.db.execute("UPDATE sends SET done='dead' WHERE use_id=?", (use_id,))
            return
        receiver, via = self._receiver_for(sid, agent, to, rk)
        if self._dead(self._sid_of(receiver)):
            self.db.execute("UPDATE sends SET done='dead' WHERE use_id=?", (use_id,))
            return
        summary = summary[:SUMMARY_MAX] if summary else None
        if outcome == "undelivered":
            mid = f"u-{use_id}"
            if not self._exists(mid):
                self._insert(mid, sender, receiver, sent_at, text, now, state="undelivered", summary=summary,
                             seen_s=1, via=via, use_id=use_id)
        elif msg_id:
            mid = f"m-{msg_id}"
            if self._exists(mid):                           # the receiver's side came first
                self._update(mid, at=sent_at, summary=summary, seen_s=1, use_id=use_id, msg_id=msg_id)
            else:
                self._insert(mid, sender, receiver, sent_at, text, now, state="delivered", summary=summary, seen_s=1,
                             via=via, msg_id=msg_id, use_id=use_id, delivered_at=at or sent_at)
                self._arrived(mid)
        else:
            mid = f"u-{use_id}"
            if not self._exists(mid):
                self._insert(mid, sender, receiver, sent_at, text, now, state="delivered", summary=summary, seen_s=1,
                             via=via, use_id=use_id, delivered_at=at or sent_at)
                self._arrived(mid)
                self._match_held(mid)
        self.db.execute("UPDATE sends SET done=? WHERE use_id=?", (mid, use_id))

    def _exists(self, mid: str) -> bool:
        return self.db.execute("SELECT 1 FROM messages WHERE id=?", (mid,)).fetchone() is not None

    def _sid_of(self, key: str) -> str | None:
        row = self.db.execute("SELECT sid FROM parts WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _read_mark(self, mid: str, at: int, merged: bool = False) -> None:
        row = self.db.execute("SELECT read_at, delivered_at, state FROM messages WHERE id=?", (mid,)).fetchone()
        if row is None or row[2] == "undelivered":
            return
        fields = {"seen_r": 1}
        if row[0] is None:                                  # the first record's time only
            fields.update(read_at=at, state="read")
            if row[1] is None or row[1] > at:
                fields["delivered_at"] = at
        if merged:
            fields["merged"] = 1
        self._update(mid, **fields)

    def _on_recv(self, sid: str, agent: str | None, info: dict, now: int) -> None:
        receiver = self._sender_of_file(sid, agent)
        at = info.get("at") or now
        uuid = info.get("uuid")
        if info.get("msg_id"):
            mid = f"m-{info['msg_id']}"
            if not self._exists(mid):
                sender_sid = self.reg.by_pid.get(info.get("pid")) if info.get("pid") else None
                if sender_sid is None and isinstance(info.get("sender_from"), str) and info["sender_from"].startswith("uds:"):
                    sender_sid = self.reg.by_sock.get(info["sender_from"][4:])
                if sender_sid is None and info.get("name"):
                    sender_sid = self.reg.by_name.get(info["name"])
                if self._dead(sender_sid) or self._dead(sid):
                    return
                if sender_sid and sender_sid != sid:
                    sender, via = self._session_part(sender_sid, info.get("name")), "session"
                else:
                    name = info.get("name") or i18n.tl("srv.peer.unnamed")
                    sender, via = external_key(name), "external"
                    self._part(sender, sender, "external", name)
                self._insert(mid, sender, receiver, at, info["body"], now, state="read", read_at=at, delivered_at=at,
                             seen_r=1, via=via, msg_id=info["msg_id"])
            else:
                self._read_mark(mid, at)
            for body in info.get("members") or []:
                self._member_read(receiver, body, at, mid)
            return
        if not uuid:
            return
        if self.db.execute("SELECT 1 FROM recv_seen WHERE receiver=? AND uuid=?", (receiver, uuid)).fetchone():
            return                                          # read again (a rebuild, or Remote Control's copy)
        mid = self._match(receiver, info)
        if mid:
            self._read_mark(mid, at)
            self.db.execute("INSERT OR IGNORE INTO recv_seen VALUES(?, ?, ?)", (receiver, uuid, sid))
        else:
            self.db.execute("INSERT OR IGNORE INTO held VALUES(?, ?, ?, ?, ?)",
                            (receiver, uuid, sid, json.dumps({**info, "agent": agent}, ensure_ascii=False), at))

    def _member_read(self, receiver: str, body: str, at: int, first: str) -> None:
        row = self.db.execute("SELECT id FROM messages WHERE receiver=? AND hash=? AND read_at IS NULL AND id<>? "
                              "AND state<>'undelivered' AND at<=? ORDER BY at LIMIT 1",
                              (receiver, _hash(body), first, at + 5_000)).fetchone()
        if row:
            self._read_mark(row[0], at, merged=True)
        self._update(first, merged=1)

    def _match(self, receiver: str, info: dict) -> str | None:
        """The unread send to this receiver this record reads (no msg_id: by the sender and the exact body)."""
        at = info.get("at") or 0
        task = info.get("task")
        rows = self.db.execute("SELECT id, sender, text, cut, hash FROM messages WHERE receiver=? AND read_at IS NULL "
                               "AND state<>'undelivered' AND msg_id IS NULL AND at<=? ORDER BY at, id",
                               (receiver, at + 5_000)).fetchall()
        for mid, sender, text, cut, h in rows:
            if task and sender != task:
                continue
            if "body" in info and info["body"] is not None:
                if h == _hash(info["body"]):
                    return mid
            elif info.get("wrapped") and not cut and text and text in info["wrapped"]:
                return mid
        return None

    def _match_held(self, mid: str) -> None:
        row = self.db.execute("SELECT receiver FROM messages WHERE id=?", (mid,)).fetchone()
        for receiver, uuid, sid, raw, at in self.db.execute("SELECT * FROM held WHERE receiver=?", (row[0],)).fetchall():
            info = json.loads(raw)
            if self._match(receiver, info) == mid:
                self._read_mark(mid, at)
                self.db.execute("DELETE FROM held WHERE receiver=? AND uuid=?", (receiver, uuid))
                self.db.execute("INSERT OR IGNORE INTO recv_seen VALUES(?, ?, ?)", (receiver, uuid, sid))
                return

    def _settle(self, now: int) -> None:
        """Held receiver records nobody's send matched, once the reading has caught up: receiver-only rows."""
        if not self.caught_up:
            return
        for receiver, uuid, sid, raw, at in self.db.execute("SELECT * FROM held WHERE at<=?", (now - HOLD_MS,)).fetchall():
            info = json.loads(raw)
            mid = self._match(receiver, info)
            if mid:
                self._read_mark(mid, at)
            elif not self._dead(sid):
                body = info.get("body") if info.get("body") is not None else info.get("wrapped") or ""
                if info.get("task"):
                    sender, via = self._sub_part(info["task"], sid), "parent"
                elif info.get("kind") == "coordinator":
                    sender, via = self._session_part(sid), "subagent"
                else:
                    name = info.get("name") or i18n.tl("srv.peer.unnamed")
                    sender, via = external_key(name), "external"
                    self._part(sender, sender, "external", name)
                rid = "r-" + _KEY_SAFE.sub("_", f"{receiver}:{uuid}")[:190]
                if not self._exists(rid):
                    self._insert(rid, sender, receiver, at, body, now, state="read", read_at=at, delivered_at=at,
                                 seen_r=1, via=via)
            self.db.execute("DELETE FROM held WHERE receiver=? AND uuid=?", (receiver, uuid))
            self.db.execute("INSERT OR IGNORE INTO recv_seen VALUES(?, ?, ?)", (receiver, uuid, sid))

    def _on_arrive(self, sid: str, body: str, at: int | None, now: int) -> None:
        if at is None:
            return
        h = _hash(body)
        row = self.db.execute("SELECT m.id, m.delivered_at FROM messages m JOIN parts p ON p.key=m.receiver WHERE p.sid=? "
                              "AND m.hash=? AND m.at<=? AND m.at>=? AND m.state<>'undelivered' ORDER BY m.at LIMIT 1",
                              (sid, h, at + 5_000, at - ARRIVE_MS)).fetchone()
        if row:
            if row[1] is None or at < row[1]:
                self._update(row[0], delivered_at=at)
        else:
            self.db.execute("INSERT INTO arrivals VALUES(?, ?, ?)", (sid, h, at))
            self.db.execute("DELETE FROM arrivals WHERE at<?", (at - 86_400_000,))

    def _arrived(self, mid: str) -> None:
        row = self.db.execute("SELECT m.hash, m.at, p.sid FROM messages m JOIN parts p ON p.key=m.receiver WHERE m.id=?", (mid,)).fetchone()
        if row is None or row[2] is None:
            return
        got = self.db.execute("SELECT rowid, at FROM arrivals WHERE sid=? AND hash=? AND at>=? AND at<=? ORDER BY at LIMIT 1",
                              (row[2], row[0], row[1] - 5_000, row[1] + ARRIVE_MS)).fetchone()
        if got:
            self.db.execute("DELETE FROM arrivals WHERE rowid=?", (got[0],))
            self._update(mid, delivered_at=got[1])

    # ------------------------------------------------------------------ what the page gets
    def _peer(self, key: str, now: int) -> dict:
        row = self.db.execute("SELECT sid, kind, name FROM parts WHERE key=?", (key,)).fetchone()
        sid, kind, name = row if row else (None, "external", key)
        gone = self.db.execute("SELECT at FROM gone WHERE sid=?", (sid,)).fetchone() if sid else None
        return {"key": key, "agentId": None if kind == "external" else key, "sessionId": None if kind == "external" else sid,
                "name": name[:NAME_MAX],
                "kind": kind, "alive": gone is None, "goneAt": gone[0] if gone else None,
                "removeAt": gone[0] + self.grace_ms if gone else None}

    def conversation(self, cid: str, owner: str, now: int) -> dict | None:
        row = self.db.execute("SELECT a, b FROM convs WHERE id=?", (cid,)).fetchone()
        if row is None or owner not in row:
            return None
        peer = row[1] if row[0] == owner else row[0]
        last = self.db.execute("SELECT text, at, sender FROM messages WHERE conv=? ORDER BY at DESC, id DESC LIMIT 1", (cid,)).fetchone()
        count = self.db.execute("SELECT COUNT(*) FROM messages WHERE conv=?", (cid,)).fetchone()[0]
        if last is None:
            return None
        return {"id": cid, "owner": owner, "peer": self._peer(peer, now), "lastAt": last[1], "preview": _preview(last[0]),
                "lastDir": "out" if last[2] == owner else "in", "unread": self.unread(owner, cid), "count": count}

    def unread(self, owner: str, cid: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM messages m JOIN seen s ON s.conv=m.conv AND s.owner=m.receiver "
                               "WHERE m.conv=? AND m.receiver=? AND m.at>s.upto", (cid, owner)).fetchone()[0]

    def badges(self) -> dict[str, int]:
        return {o: n for o, n in self.db.execute(
            "SELECT m.receiver, COUNT(*) FROM messages m JOIN seen s ON s.conv=m.conv AND s.owner=m.receiver "
            "WHERE m.at>s.upto GROUP BY m.receiver").fetchall() if n > 0}

    def conversations(self, owner: str, now: int) -> tuple[list[dict], bool]:
        rows = self.db.execute("SELECT c.id, MAX(m.at) AS last FROM convs c JOIN messages m ON m.conv=c.id "
                               "WHERE c.a=? OR c.b=? GROUP BY c.id ORDER BY last DESC, c.id LIMIT ?",
                               (owner, owner, LIST_MAX + 1)).fetchall()
        items = [c for c in (self.conversation(cid, owner, now) for cid, _l in rows[:LIST_MAX]) if c]
        return items, len(rows) > LIST_MAX

    def _message(self, row: tuple, owner: str) -> dict:
        (mid, cid, sender, receiver, sname, rname, at, dat, rat, state, text, cut, _h, summary, seen_s, seen_r, via,
         merged, msg_id, _use) = row
        return {"id": mid, "msgId": msg_id, "convId": cid, "dir": "out" if sender == owner else "in",
                "fromName": sname[:NAME_MAX], "toName": rname[:NAME_MAX], "at": at, "deliveredAt": dat, "readAt": rat,
                "state": state, "text": text, "cut": bool(cut), "summary": summary,
                "seen": "both" if seen_s and seen_r else "sender" if seen_s else "receiver", "via": via,
                "merged": bool(merged)}

    def messages(self, owner: str, cid: str, before: str | None = None, limit: int = PAGE_MAX) -> tuple[list[dict], bool] | None:
        conv = self.db.execute("SELECT a, b FROM convs WHERE id=?", (cid,)).fetchone()
        if conv is None or owner not in conv:
            return None
        limit = max(1, min(int(limit), PAGE_MAX))
        if before:
            pivot = self.db.execute("SELECT at, id FROM messages WHERE id=? AND conv=?", (before, cid)).fetchone()
            if pivot is None:
                return [], False
            rows = self.db.execute("SELECT * FROM messages WHERE conv=? AND (at<? OR (at=? AND id<?)) ORDER BY at DESC, id DESC LIMIT ?",
                                   (cid, pivot[0], pivot[0], pivot[1], limit + 1)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM messages WHERE conv=? ORDER BY at DESC, id DESC LIMIT ?", (cid, limit + 1)).fetchall()
        more = len(rows) > limit
        return [self._message(r, owner) for r in reversed(rows[:limit])], more

    def seen(self, owner: str, cid: str, upto: int, now: int) -> dict | None:
        """The page saw this conversation up to ``upto``: never moves back. Returns the owner's conversation row."""
        conv = self.db.execute("SELECT a, b FROM convs WHERE id=?", (cid,)).fetchone()
        if conv is None or owner not in conv:
            return None
        self.db.execute("UPDATE seen SET upto=MAX(upto, ?) WHERE owner=? AND conv=?", (min(int(upto), now), owner, cid))
        return self.conversation(cid, owner, now)

    def _ops(self, now: int) -> dict[str, list[dict]]:
        ops: dict[str, list[dict]] = {}
        for cid, a, b, dead in self._removed:
            for owner in (a, b):
                ops.setdefault(owner, []).append({"op": "remove", "convId": cid, "reason": "owner-ended" if owner == dead else "peer-ended"})
        for mid in sorted(self._changed_msgs):
            row = self.db.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
            if row is None:
                continue
            for owner in (row[2], row[3]):
                ops.setdefault(owner, []).append({"op": "message", "convId": row[1], "message": self._message(row, owner)})
        for cid in sorted(self._changed_convs):
            row = self.db.execute("SELECT a, b FROM convs WHERE id=?", (cid,)).fetchone()
            if row is None:
                continue
            for owner in row:
                conv = self.conversation(cid, owner, now)
                if conv:
                    ops.setdefault(owner, []).append({"op": "conv", "conv": conv})
        return ops

    def close(self) -> None:
        self.db.close()

    def reserve_relay(self, mid: str, digest: str) -> tuple[bool, dict | None]:
        """Persist before transport. An interrupted send is never blindly repeated after restart."""
        row = self.db.execute("SELECT hash,result FROM relays WHERE id=?", (mid,)).fetchone()
        if row:
            if row[0] != digest:
                raise ValueError('message id already used for different content')
            return False, json.loads(row[1]) if row[1] else None
        self.db.execute("INSERT INTO relays(id,hash) VALUES(?,?)", (mid, digest))
        return True, None

    def record_relay(self, mid: str, sender: dict, receiver: dict, text: str, now: int, result: dict) -> dict:
        self._changed_msgs, self._changed_convs, self._removed = set(), set(), []
        was_live, self._live = self._live, True  # a send made now is new, even while transcript backfill runs
        self.db.execute('BEGIN')
        try:
            for row in (sender, receiver):
                self._session_part(row['id'], row['name'])
                self.db.execute('DELETE FROM gone WHERE sid=?', (row['id'],))
            record = {'sender': sender, 'receiver': receiver, 'text': text, 'at': now, 'result': result}
            self.db.execute('UPDATE relays SET result=?,sender=?,receiver=?,record=? WHERE id=?',
                            (json.dumps(result), sender['id'], receiver['id'], json.dumps(record), mid))
            self._insert('m-jui-' + mid, sender['id'], receiver['id'], now, text, now,
                         state='sent' if result['ok'] else 'undelivered', seen_s=1)
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise
        finally:
            self._live = was_live
        return {'ops': self._ops(now), 'badges': self.badges()}


# ====================================================================== the server's half: on the event loop
class TalkHub:
    """Runs a TalkIndex in its own one-thread executor (every read and write of the index there, so the event loop is
    never held), steps it on the server's tick, and turns its ops into the contract's frames for the sockets that
    asked (talk.open), plus talk.badges for every socket. Requests from the page come in through ``handle``."""

    STEP_EVERY_MS = 2_000

    def __init__(self, make_index: Callable[[], TalkIndex], agents: Callable[[], dict] | None = None,
                 sessions: Callable[[], dict] | None = None) -> None:
        self._make_index = make_index
        self.index: TalkIndex | None = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jui-viz-talk")
        self.agents = agents or (lambda: {})
        self.sessions = sessions or (lambda: {})
        self.watch: dict[Any, str] = {}          # socket -> the robot whose list it shows
        self.frames: list[tuple[Any, dict]] = []  # (socket or None for every socket, frame) to send
        self.badges: dict[str, int] = {}
        self._job = None
        self._last = -10**12
        self.caught_up = False
        self.error: str | None = None
        self.closed = False
        self._session_rows: list[dict] = []

    async def run(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(self.pool, fn, *args)

    def _ensure(self) -> TalkIndex:
        if self.index is None:
            self.index = self._make_index()
        return self.index

    def _step(self, now: int) -> dict:
        return self._ensure().step(now, self._session_rows)

    def tick(self, now: int) -> bool:
        """On the event loop, never blocking: take a finished step's result; start the next one when due (every
        STEP_EVERY_MS, or at once while the reading is behind). Returns whether frames were queued."""
        queued = False
        if self.closed:
            return False
        job = self._job
        if job is not None:
            if not job.done():
                return False
            self._job = None
            try:
                got = job.result()
            except Exception as exc:  # noqa: BLE001 — a step that failed is tried again; the page keeps what it has
                self.error = type(exc).__name__
                got = None
            if got is not None:
                self.error = None
                self.caught_up = got["caughtUp"]
                queued = self._queue(got["ops"], got["badges"])
        if now - self._last >= self.STEP_EVERY_MS or not self.caught_up:
            self._session_rows = [{'sessionId': sid, 'name': s.get('title') or sid}
                                  for sid, s in list(self.sessions().items()) if s.get('status') != 'ended']
            self._last = now
            self._job = self.pool.submit(self._step, now)
        return queued

    def _decorate(self, item: dict) -> dict:
        """The peer as the page can use it: agentId only when that robot is on the page (so the header can switch to
        it), the session's title when it has a newer one."""
        peer = item["peer"]
        agents = self.agents()
        if peer["agentId"] is not None and peer["agentId"] not in agents:
            peer["agentId"] = None
        session = self.sessions().get(peer["key"]) if peer["kind"] == "session" else None
        if session and session.get("title"):
            peer["name"] = str(session["title"])[:NAME_MAX]
        return item

    def _queue(self, ops: dict, badges: dict) -> bool:
        queued = False
        for sock, owner in list(self.watch.items()):
            mine = ops.get(owner) or []
            for op in mine:
                if op["op"] == "conv":
                    self._decorate(op["conv"])
            for i in range(0, len(mine), OPS_MAX):
                self.frames.append((sock, {"type": "talk.update", "agentId": owner, "ops": mine[i:i + OPS_MAX]}))
                queued = True
        if self._set_badges(badges):
            queued = True
        return queued

    def _set_badges(self, badges: dict) -> bool:
        known = self.agents()
        counts = {k: int(v) for k, v in badges.items() if v > 0 and k in known}
        if counts == self.badges:
            return False
        self.badges = counts
        self.frames.append((None, self.badges_frame()))
        return True

    def badges_frame(self) -> dict:
        return {"type": "talk.badges", "counts": dict(self.badges)}

    def forget(self, sock) -> None:
        self.watch.pop(sock, None)

    async def flush(self, sockets) -> None:
        """Send the queued frames (push loop): one for a socket, or None for every authed socket."""
        frames, self.frames = self.frames, []
        for target, frame in frames:
            for sock in ([target] if target is not None else list(sockets)):
                if target is not None and sock not in sockets:
                    continue
                try:
                    await sock.send_json(frame)
                except (ConnectionResetError, RuntimeError):
                    self.watch.pop(sock, None)

    async def handle(self, sock, message: dict) -> None:
        """talk.open / talk.close / talk.get / talk.seen (talk_contract.json). Refusals are the server's ack."""
        kind, req_id = message.get("type"), message.get("reqId")

        async def refuse(error: str) -> None:
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": False, "error": error})

        if kind == "talk.close":
            self.watch.pop(sock, None)
            if req_id is not None:
                await sock.send_json({"type": "ack", "reqId": req_id, "ok": True})
            return
        problems = talk_contract.validate_request(message)   # a request only, never a server frame's type
        if problems:
            await refuse("bad request: " + problems[0][:200])
            return
        owner = message["agentId"]
        if owner not in self.agents():
            await refuse("no such robot")
            return
        now = int(time.time() * 1000)
        if kind == "talk.open":
            items, more = await self.run(lambda: self._ensure().conversations(owner, now))
            self.watch[sock] = owner
            await sock.send_json({"type": "talk.list", "reqId": req_id, "agentId": owner,
                                  "items": [self._decorate(i) for i in items], "more": more})
        elif kind == "talk.get":
            got = await self.run(lambda: self._ensure().messages(owner, message["convId"], message.get("before"),
                                                                message.get("limit", PAGE_MAX)))
            if got is None:
                await refuse("no such conversation for this robot")
                return
            await sock.send_json({"type": "talk.messages", "reqId": req_id, "agentId": owner, "convId": message["convId"],
                                  "items": got[0], "more": got[1]})
        elif kind == "talk.seen":
            def mark():
                index = self._ensure()
                return index.seen(owner, message["convId"], message["upTo"], now), index.badges()
            conv, badges = await self.run(mark)
            if conv is None:
                await refuse("no such conversation for this robot")
                return
            await sock.send_json({"type": "ack", "reqId": req_id, "ok": True})
            self._decorate(conv)
            for other, watched in list(self.watch.items()):
                if watched == owner:
                    self.frames.append((other, {"type": "talk.update", "agentId": owner, "ops": [{"op": "conv", "conv": conv}]}))
            self._set_badges(badges)          # sent by the push loop to every socket

    def close(self, wait: bool = True) -> None:
        """The index closed after the step under way. wait=False (the server stopping): queued, not waited for — a
        step still running must not hold a TERM (ticket 2026-10-21-jui-viz-serve-does-not-exit-on-term)."""
        self.closed = True
        index = self.index
        if index is not None:
            self.pool.submit(index.close)
        self.pool.shutdown(wait=wait, cancel_futures=False)
