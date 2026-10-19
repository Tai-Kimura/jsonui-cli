"""The talk view's reading of a transcript record: what one record says about a SendMessage (the plan:
docs/plans/2026-10-20-jui-viz-talk-view.md, its research at the end; the shapes are Claude Code's own and are in the
dependency ledger with a probe each: talk-send-input, talk-msg-id, talk-origin, talk-envelope).

One record gives at most a few observations, each a plain tuple the index (viz/talk.py) applies:

* ``("send", use_id, to, text, summary, kind, at)`` — the sender's ``assistant`` tool_use ``SendMessage``: its id,
  ``input.to``, ``input.message`` (the body; a non-text message is shown as its JSON), ``input.summary``,
  ``input.recipient_kind`` (when the CLI wrote one).
* ``("result", use_id, msg_id, outcome, at)`` — the ``tool_result`` of a SendMessage in a ``user`` record: ``msg_id``
  from ``toolUseResult.msg_id`` (a send to a session); ``outcome`` "ok", or "undelivered" for ``is_error`` or the
  successful-looking "No agent named … is reachable" (measured: 13 in 24 h; never matched to anyone's message).
* ``("recv", info)`` — the receiver's record of a message it read: a ``user`` record (``isMeta``) or an ``attachment``
  of type ``queued_command``, whose ``origin`` is ``{"kind": "peer", …}`` (another session: ``msg_id``, ``from``,
  ``verifiedPeerPid``, ``name``, ``body``, maybe ``members`` when two sends were bundled; or a subagent's send to
  ``main``: ``senderTaskId``, ``from``, ``body``, no msg_id) or ``{"kind": "coordinator"}`` (the parent's send to this
  subagent: no body field; the queued_command's ``prompt`` is the body, a user record's text wraps it).
  A subagent's hand-back (``origin.handback``) is not a SendMessage and is skipped (the requester's settled answer:
  the Agent start and its last reply are not talks).
* ``("arrive", body, at)`` — ``queue-operation`` ``enqueue`` whose content is ``<cross-session-message …>`` or
  ``<agent-message …>``: the message arrived (no msg_id here: matched by the body, as the research found).

Nothing here keeps state or reads a file; a record of another shape gives nothing.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

SEND_TOOL = "SendMessage"
#: The "success" a send to a name that resolves to nobody returns (measured 10-19: not is_error).
NO_AGENT = re.compile(r"No agent named .{0,300}? is reachable", re.S)
_ENVELOPE = re.compile(r'^\s*<(cross-session-message|agent-message)\b[^>]*>\n?(.*?)\n?</\1>', re.S)

#: Lines worth parsing at all: a cheap byte test before json.loads (a transcript can be hundreds of MB).
NEEDLES = (b'"SendMessage"', b'"origin"', b'"enqueue"')
TOOL_RESULT_IDS = re.compile(rb'"tool_use_id"\s*:\s*"([^"]{1,200})"')


def epoch_ms(ts) -> int | None:
    if not isinstance(ts, str):
        return None
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return ""


def wanted(line: bytes, pending: set | frozenset) -> bool:
    """Whether a line can hold an observation (before parsing it). ``pending``: SendMessage tool_use ids whose
    result has not been seen."""
    if any(n in line for n in NEEDLES):
        return True
    if pending and b'"tool_result"' in line:
        return any(m.decode("utf-8", "replace") in pending for m in TOOL_RESULT_IDS.findall(line))
    return False


def _origin_info(origin: dict, at, uuid, text: str | None, prompt: str | None) -> dict | None:
    kind = origin.get("kind")
    if kind not in ("peer", "coordinator") or origin.get("handback"):
        return None
    info = {"kind": kind, "at": at, "uuid": uuid if isinstance(uuid, str) else None}
    if kind == "peer":
        body = origin.get("body")
        info.update(msg_id=origin["msg_id"] if isinstance(origin.get("msg_id"), str) else None,
                    body=body if isinstance(body, str) else None,
                    name=origin["name"] if isinstance(origin.get("name"), str) else None,
                    sender_from=origin["from"] if isinstance(origin.get("from"), str) else None,
                    pid=origin["verifiedPeerPid"] if isinstance(origin.get("verifiedPeerPid"), int) and not isinstance(origin.get("verifiedPeerPid"), bool) else None,
                    task=origin["senderTaskId"] if isinstance(origin.get("senderTaskId"), str) else None)
        members = origin.get("members")
        if isinstance(members, list):
            info["members"] = [m["body"] for m in members if isinstance(m, dict) and isinstance(m.get("body"), str)]
            if info["body"] is None and info["members"]:
                info["body"] = info["members"][0]
        if info["body"] is None:
            return None
    else:
        # the parent's send to this subagent: the queued prompt is the body; a user record wraps it in a line before
        # and after (measured 10-20: "The coordinator sent a message while you were working:" … ) — kept whole and
        # matched by containment, never parsed
        if prompt is not None:
            info["body"] = prompt
        elif text:
            info["wrapped"] = text
        else:
            return None
    return info


def observations(rec) -> list[tuple]:
    """What one transcript record says about SendMessage (the tuples above), oldest first."""
    if not isinstance(rec, dict):
        return []
    kind, at = rec.get("type"), epoch_ms(rec.get("timestamp"))
    out: list[tuple] = []
    if kind == "assistant":
        msg = rec.get("message")
        for b in msg.get("content") if isinstance(msg, dict) and isinstance(msg.get("content"), list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == SEND_TOOL and isinstance(b.get("id"), str):
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                to = inp.get("to")
                if not isinstance(to, str) or not to.strip():
                    continue
                if "message" not in inp:
                    continue          # a pure notify_when_idle subscription: no message was sent
                summary = inp.get("summary") if isinstance(inp.get("summary"), str) else None
                rk = inp.get("recipient_kind") if isinstance(inp.get("recipient_kind"), str) else None
                out.append(("send", b["id"], to.strip(), _text(inp.get("message")), summary, rk, at))
    elif kind == "user":
        msg = rec.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result" and isinstance(b.get("tool_use_id"), str):
                    tur = rec.get("toolUseResult")
                    msg_id = tur.get("msg_id") if isinstance(tur, dict) and isinstance(tur.get("msg_id"), str) else None
                    text = _content_text(b.get("content"))
                    bad = b.get("is_error") is True or (msg_id is None and NO_AGENT.search(text[:2000]) is not None)
                    out.append(("result", b["tool_use_id"], msg_id, "undelivered" if bad else "ok", at))
        origin = rec.get("origin")
        if isinstance(origin, dict):
            info = _origin_info(origin, at, rec.get("uuid"), _content_text(content), None)
            if info:
                out.append(("recv", info))
    elif kind == "attachment":
        att = rec.get("attachment")
        if isinstance(att, dict) and att.get("type") == "queued_command" and isinstance(att.get("origin"), dict):
            prompt = att.get("prompt") if isinstance(att.get("prompt"), str) else None
            info = _origin_info(att["origin"], at or epoch_ms(att.get("timestamp")), rec.get("uuid") or att.get("source_uuid"), None, prompt)
            if info:
                out.append(("recv", info))
    elif kind == "queue-operation" and rec.get("operation") == "enqueue" and isinstance(rec.get("content"), str):
        m = _ENVELOPE.match(rec["content"])
        if m:
            out.append(("arrive", m.group(2), at))
    return out
