"""Codex rollout -> the existing history tab's rows, read on demand with the same byte/item caps.

Only response_item records are conversation: event_msg repeats them, turn_context and session_meta contain
instructions/settings, reasoning can contain private text. None of those are handed to the page.
The path comes from thread/resume, never from a browser, and must remain in that daemon's sessions directory.
"""
from __future__ import annotations

import json
import os
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
