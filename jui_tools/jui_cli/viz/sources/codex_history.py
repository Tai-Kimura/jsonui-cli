"""Codex rollout -> the existing history tab's rows, read on demand with the same byte/item caps.

Only response_item records are conversation: event_msg repeats them, turn_context and session_meta contain
instructions/settings, reasoning can contain private text. None of those are handed to the page. A subagent's
agent_message to its parent is a row as another session's message is.
The path comes from thread/resume, never from a browser, and must remain in that daemon's sessions directory.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import history


def items_of(rec, results: dict, off=None) -> list[dict]:
    if not isinstance(rec, dict) or rec.get("type") != "response_item":
        return []
    p = rec.get("payload")
    if not isinstance(p, dict):
        return []
    kind, at = p.get("type"), history._at(rec)
    if kind == "message" and p.get("role") in ("user", "assistant"):
        content = p.get("content")
        text = "\n".join(b["text"] for b in content if isinstance(b, dict)
                         and b.get("type") in ("input_text", "output_text", "text") and isinstance(b.get("text"), str)) if isinstance(content, list) else ""
        if not text.strip():
            return []
        if p["role"] == "user":
            return [history._text_item(text, at, False)]
        body, cut = history._cut(text, history.TEXT_MAX)
        return [{"kind": "assistant", "text": body, "cut": cut, "at": at}]
    if kind == "agent_message":
        return _agent_message(p, at)
    call_id = p.get("call_id")
    if not isinstance(call_id, str) or not call_id:
        return []
    if kind in ("function_call_output", "custom_tool_call_output"):
        output = p.get("output", "")
        raw = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        body, cut = history._cut(raw, history.IO_MAX)
        # Reading backwards: keep the newest output when a rollout repeats it.
        results.setdefault(call_id, {"out": body, "outCut": cut})
    elif kind in ("function_call", "custom_tool_call"):
        raw = p.get("arguments" if kind == "function_call" else "input", "")
        raw = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
        body, cut = history._cut(raw, history.IO_MAX)
        return [{"kind": "tool", "id": call_id, "name": str(p.get("name") or "tool")[:120],
                 "description": "", "in": body, "inCut": cut, "at": at}]
    return []


_AGENT_HEAD = re.compile(r"^Message Type: [^\n]*\n(?:[A-Za-z ]+: [^\n]*\n)*?Payload:\n", re.S)


def _agent_message(p: dict, at) -> list[dict]:
    """A subagent's message to its parent (ticket 2026-10-29-viz-history-misses-messages-shown-in-terminal, H: measured
    10-29, 42 in 77 rollouts; ``author`` "/root/<task>", ``recipient`` "/root", the text "Message Type: …\nTask name: …
    \nSender: …\nPayload:\n<the message>"): the row another session's message makes, from its author, the message
    without the header. An ``encrypted_content`` block is never shown; a message with no readable text gives nothing."""
    content = p.get("content")
    text = "\n".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") in ("input_text", "output_text", "text")
                     and isinstance(b.get("text"), str)) if isinstance(content, list) else ""
    body = _AGENT_HEAD.sub("", text, count=1).strip()
    if not body:
        return []
    author = p.get("author") if isinstance(p.get("author"), str) and p["author"].strip() else "?"
    cut_body, cut = history._cut(body, history.TEXT_MAX)
    return [{"kind": "peer", "from": author[:200], "text": cut_body, "cut": cut, "at": at}]


def read(home: Path, given: str, end=None, stop=None) -> dict | None:
    path = Path(given)
    root = home / "sessions"
    fd = history.safe_open(root, path)
    if fd is None:
        return None
    try:
        return history.read_tail(fd, end=end, stop=stop, parse_items=items_of)
    except OSError:
        return None
    finally:
        os.close(fd)

