"""Phone calls: a SendMessage between two sessions on this machine (requester, 10-18).

The sender's PreToolUse(SendMessage) dials. Its ``to`` is a session's name (``jsonui-agents-for-claude-5b``, maybe
with `` [ref]``) or the ``uds:`` address a reply copies; ~/.claude/sessions/<pid>.json maps both to a session id,
so the receiver rings at once. The receiver's own transcript then says what happened to the message (measured
10-18 on 17 messages between two sessions, the sender's tool_use time against the receiver's records):

- ``queue-operation`` ``enqueue`` whose content is the ``<cross-session-message … from-name="<sender>">``: it
  arrived (0.5–5 s after the send). It rings even when the name did not resolve.
- the same message read: an ``isMeta`` user record (the receiver was idle: 6–12 ms after the enqueue) or
  ``queue-operation`` ``remove`` with reason ``absorbed_mid_turn`` (it was working: at its next tool boundary,
  8 s to 3 min 14 s later). Either one picks up.
- any other ``remove``: it hangs up.

A read counts only when its record was written at or after the message arrived (the enqueue record's time, or the
dial when no enqueue was seen): Remote Control re-appends a transcript's past isMeta records with their old times
when it attaches again (measured 10-18 by jsonuidocument-96: 2,473 copies in 24 transcripts, never a queue-operation),
and those must not pick up a call that is still unread. Both times are records of this machine's clock.

Only the sender's name is read from a message, never its text. A call that nobody picks up stops ringing after
RING_MAX_MS. A send whose receiver is not a session here (cloud, Remote Control, ``main``, a subagent's name)
moves the sender only, and stops UNREACHABLE_GRACE_MS after the tool ends without an enqueue.
"""
from __future__ import annotations

import re

RING_MAX_MS = 600_000          # 10 min: a busy receiver read one 3 min 14 s after it arrived (10-18)
UNREACHABLE_GRACE_MS = 6_000   # the enqueue came 0.5–5 s after the send, and transcripts are read every 2 s
ANSWERED_SHOW_MS = 4_000       # both robots on the line for a moment, then back to work
ENDED_SHOW_MS = 1_500
CALLS_KEPT = 50
PICK_UP_SLACK_MS = 2_000      # a call dialed with no enqueue seen yet: a read written a little before the dial still counts

_REF = re.compile(r"\s*\[[^\]]*\]\s*$")
_FROM_NAME = re.compile(r'<cross-session-message\b[^>]*?\bfrom-name="([^"]*)"')
OPEN = ("dialing", "ringing")


def peer_name(to: str) -> str:
    """``name [ref]`` -> ``name``."""
    return _REF.sub("", to).strip()


PREAMBLE_MAX = 120


def message_sender(text, preamble: bool = False) -> str | None:
    """The from-name of a text that IS a cross-session message (starts with the tag), else None.

    A tool result or a prompt that merely quotes one does not start with it. ``preamble``: the isMeta user record
    puts one line before the tag (``Another Claude session sent a message:``, measured 10-18 on 11 records); one
    short line without a ``<`` is allowed there, nothing more."""
    if not isinstance(text, str):
        return None
    head = text.lstrip()[:2000]
    if preamble and not head.startswith("<"):
        first, sep, rest = head.partition("\n")
        if sep and len(first) <= PREAMBLE_MAX and "<" not in first:
            head = rest.lstrip()
    if not head.startswith("<cross-session-message"):
        return None
    m = _FROM_NAME.match(head)
    return m.group(1) if m else None


def record_event(rec) -> tuple[str, str] | None:
    """('ring' | 'answer' | 'hangup', sender name) for a transcript record about a cross-session message."""
    if not isinstance(rec, dict):
        return None
    kind = rec.get("type")
    if kind == "queue-operation":
        name = message_sender(rec.get("content"))
        if name is None:
            return None
        op = rec.get("operation")
        if op == "enqueue":
            return "ring", name
        if op == "remove":
            return ("answer" if rec.get("reason") == "absorbed_mid_turn" else "hangup"), name
        return None
    if kind == "user" and rec.get("isMeta") is True:
        msg = rec.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            first = next((c for c in content if isinstance(c, dict) and c.get("type") == "text"), None)
            content = first.get("text") if first else None
        name = message_sender(content, preamble=True)
        return ("answer", name) if name is not None else None
    return None


class CallBook:
    def __init__(self) -> None:
        self.calls: dict[str, dict] = {}
        self._n = 0

    def _new(self, at: int, **fields) -> dict:
        self._n += 1
        call = {"id": fields.pop("id", None) or f"call-{self._n}", "state": "dialing", "startedAt": at, **fields}
        self.calls[call["id"]] = call
        for old in sorted(self.calls, key=lambda k: self.calls[k]["startedAt"])[:-CALLS_KEPT]:
            del self.calls[old]
        return call

    def dial(self, use_id: str | None, from_agent: str, from_session: str, from_name: str | None,
             to_name: str, to_session: str | None, at: int) -> dict:
        call = self._new(at, id=f"call-{use_id}" if use_id else None, **{
            "from": from_agent, "fromSession": from_session, "fromName": from_name, "toName": to_name,
            "toSession": to_session})
        if to_session:
            call["state"], call["ringAt"] = "ringing", at
        return call

    def sent(self, use_id: str | None, failed: bool, at: int) -> bool:
        """The sender's PostToolUse / PostToolUseFailure."""
        call = self.calls.get(f"call-{use_id}") if use_id else None
        if call is None or call["state"] not in OPEN:
            return False
        if failed:
            self._end(call, "failed", at)
            return True
        call["sentAt"] = at
        return False

    def _end(self, call: dict, state: str, at: int) -> None:
        call["state"], call["endedAt"] = state, at
        call["hideAt"] = at + (ANSWERED_SHOW_MS if state == "answered" else ENDED_SHOW_MS)

    def _open_to(self, to_session: str, from_name: str, newest: bool, written: int | None = None) -> dict | None:
        """An open call from that sender that this receiver can be the end of (and, for a read written at
        ``written``, one that had arrived by then)."""
        found = [c for c in self.calls.values() if c["state"] in OPEN
                 and (c.get("toSession") in (None, to_session))
                 and (c.get("fromName") == from_name if c.get("fromName") else c.get("toSession") == to_session)
                 and (written is None or written >= (c.get("arrived") or c["startedAt"] - PICK_UP_SLACK_MS))]
        if not found:
            return None
        found.sort(key=lambda c: c["startedAt"])
        return found[-1] if newest else found[0]

    def ring(self, to_session: str, from_name: str, from_session: str | None, from_agent: str | None, at: int,
             written: int | None = None) -> bool:
        call = self._open_to(to_session, from_name, newest=True)
        if call is None:   # the sender's hook was not seen (a hookless sender): the receiver rings anyway
            call = self._new(at, **{"from": from_agent, "fromSession": from_session, "fromName": from_name,
                                    "toName": None, "toSession": to_session})
        changed = call.get("toSession") != to_session or call["state"] != "ringing" or not call.get("arrived")
        call["toSession"], call["arrived"] = to_session, written or at
        if call["state"] == "dialing":
            call["state"], call["ringAt"] = "ringing", at
        return changed

    def pick_up(self, to_session: str, from_name: str, at: int, written: int | None = None) -> bool:
        call = self._open_to(to_session, from_name, newest=False, written=written)
        if call is None:
            return False
        call["toSession"], call["read"] = to_session, written or at
        self._end(call, "answered", at)
        return True

    def hang_up(self, to_session: str, from_name: str, at: int) -> bool:
        call = self._open_to(to_session, from_name, newest=False)
        if call is None:
            return False
        self._end(call, "hungUp", at)
        return True

    def session_ended(self, sid: str, at: int) -> bool:
        changed = False
        for call in self.calls.values():
            if call["state"] in OPEN and sid in (call.get("toSession"), call.get("fromSession")):
                self._end(call, "missed" if sid == call.get("toSession") else "hungUp", at)
                changed = True
        return changed

    def tick(self, at: int) -> bool:
        changed = False
        for cid, call in list(self.calls.items()):
            if call["state"] == "ringing" and at - call["ringAt"] >= RING_MAX_MS:
                self._end(call, "missed", at)
                changed = True
            elif call["state"] == "dialing" and call.get("sentAt") and at - call["sentAt"] >= UNREACHABLE_GRACE_MS:
                self._end(call, "unreachable", at)
                changed = True
            elif call.get("hideAt") and at >= call["hideAt"]:
                del self.calls[cid]
                changed = True
        return changed

    def items(self) -> list[dict]:
        return sorted((dict(c) for c in self.calls.values()), key=lambda c: (c["startedAt"], c["id"]))
