"""The 応答の履歴 tab (requester, 10-18): the last turns of one robot's transcript, as the conversation reads.

"ロボットに合わせた時に会話履歴みたいな感じで" / "ツール呼び出しも畳んで出させようか" / "ちょっきんN件でいいよ".

What is read — only for the robot whose tab is open, only when the page asks (never in a slice, a snapshot, the
event log or an export):
  * the session's transcript (transcripts.candidates: under the projects folder, a regular ``.jsonl``, never
    through a symlink), or a subagent's own (the hook's ``agent_transcript_path``, else
    ``<session transcript's folder>/<session id>/subagents/agent-<agent id>.jsonl``), through the same check;
  * from the end backwards, CHUNK at a time, stopping at ITEMS_MAX items or BYTES_MAX bytes read — a transcript can
    be hundreds of MB with single lines of several MB (transcripts.py); ``bytes`` says how much was read.

What an item is (records of type ``user`` and ``assistant`` only; measured on the orchestrator's 6.8 MB transcript,
10-18: ``api-request-blob`` lines are the requests sent to the API — the same conversation again with the
system-reminders and the tool definitions — and are not shown, nor any other type):
  * ``user`` — the requester's words; ``peer`` — another session's message (<cross-session-message from-name=…>);
    ``channel`` — a channel's text the CLI put in (origin.kind "channel": a prompt sent from the viz page, 2.3.4);
    ``harness`` — text the harness put in the user's turn (harness_label: system-reminder, a subagent's hand-back,
    a task notification, a local command; or ``isMeta``), shown folded in its own colour;
  * a message that came while the session was working (an ``attachment`` of type ``queued_command``, 10-20): the
    same row its waiting form makes (channel, peer, the requester's words, the harness's text), at the time it came;
    one message is one row however many records say it (talk_records.delivery_key: msg_id, delivery_id, uuid);
  * ``assistant`` — the answer's text (Markdown, drawn by the page as text nodes only);
  * ``tool`` — a tool call: its name, input.description, IN (a command as it is, else the input's JSON) and OUT
    (the tool_result with the same tool_use_id), each cut at IO_MAX;
  * ``thought`` — a mark only (the thinking text is empty in the transcript: 30 of 30, measured 10-18);
  * ``image`` — where a picture is, never the picture (2.3.4, requester 10-19: "画像ファイルが履歴にある場合は
    サムネイル表示とクリックで拡大表示を実装してほしい"): ``img`` = {"off": the byte offset of its record's line in the
    transcript, "n": which image of that record, "type": its media type}. A tool's OUT has the same in ``imgs``. The
    page asks for the bytes one picture at a time (``image_at``, POST /api/history-image), only while the tab shows it;
    the base64 itself never goes into an item, a slice, a snapshot, the event log or an export.
  * a user text naming a picture file ("[Image: source: /path, …]", the harness's note next to a pasted picture)
    gets ``gone``: the files named there that no longer exist (a temporary folder emptied). The file itself is never
    read: the base64 in the transcript is the picture.
Every text is cut at TEXT_MAX. Nothing is written.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Callable

from .talk_records import delivery, delivery_key
from .transcripts import candidates

#: Items shown: a few turns back — the last answers and the calls between them — without a scroll of hundreds.
ITEMS_MAX = 40
#: One text: a long answer reads in full; a pasted file or a 2 MB tool output does not flood the panel.
TEXT_MAX = 6_000
#: A tool's IN and OUT: their head, as the VS Code extension's folded call shows.
IO_MAX = 1_500
CHUNK = 65_536
#: Read at most this much of a transcript per request (from its end).
BYTES_MAX = 4 * 1_048_576
#: A longer line (one huge tool result) is skipped, not parsed.
LINE_MAX = 1_048_576
COUNTED = frozenset({"user", "peer", "harness", "channel", "assistant", "tool"})
#: The pictures handed to the page: these media types only, each checked against the bytes' own signature.
IMAGE_TYPES = {"image/png": (b"\x89PNG\r\n\x1a\n",), "image/jpeg": (b"\xff\xd8\xff",), "image/gif": (b"GIF87a", b"GIF89a"),
               "image/webp": (b"RIFF",)}
#: One picture, decoded: larger ones are refused (413).
IMAGE_MAX = 10 * 1_048_576
#: The line a picture is read from: its base64 (4/3 of IMAGE_MAX) and the record around it.
IMAGE_LINE_MAX = 16 * 1_048_576
#: a file SendUserFile sent: its size cap (the tool's own) and the line of the call it is read from; files per call
SENT_FILE_MAX = 15 * 1_048_576
SENT_LINE_MAX = 4 * 1_048_576
SENT_FILES_MAX = 20
#: the names a sent picture can have (no SVG: it can hold a script)
SENT_IMAGE_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
_IMAGE_NOTE = re.compile(r"\[Image: source: ([^\],\n]+?)(?:,|\])")

# ---------------------------------------------------------------- text the harness put in the user's turn
# The one place this is decided (the task board's turn titles use it too). Matched at the start of the text.
_HARNESS = (
    ("<system-reminder>", "システムの注記"),
    ("[Subagent hand-back]", "サブエージェントの報告"),
    ("<task-notification>", "タスクの通知"),
    ("<command-name>", "コマンド"),
    ("<command-message>", "コマンド"),
    ("<local-command-stdout>", "コマンドの出力"),
    ("<local-command-stderr>", "コマンドの出力"),
    ("<local-command-caveat>", "コマンド"),
    ("Caveat: The messages below were generated by the user while running local commands", "コマンド"),
    ("[Request interrupted by user", "中断"),
    ("<user-prompt-submit-hook>", "フックの出力"),
)
_PEER = re.compile(r'<cross-session-message\b([^>]*)>(.*?)(?:</cross-session-message>|\Z)', re.S)
_PEER_INTRO = "Another Claude session sent a message:"


def harness_label(text) -> str | None:
    """What the harness wrote, when it is one of its texts (not the requester's words); else None."""
    if not isinstance(text, str):
        return None
    head = text.lstrip()
    for prefix, label in _HARNESS:
        if head.startswith(prefix):
            return label
    return None


def peer_of(text) -> tuple[str, str] | None:
    """(from-name, the message) when the text is another session's message, else None. peer_addr() gives the
    ``from="uds:…"`` address too."""
    if not isinstance(text, str):
        return None
    head = text.lstrip()
    if head.startswith(_PEER_INTRO):
        head = head[len(_PEER_INTRO):].lstrip()
    if not head.startswith("<cross-session-message"):
        return None
    m = _PEER.match(head)
    if not m:
        return None
    name = re.search(r'\bfrom-name="([^"]*)"', m.group(1)) or re.search(r'\bfrom="([^"]*)"', m.group(1))
    return (name.group(1) if name else "別のセッション"), m.group(2).strip()


def peer_addr(text) -> str | None:
    """The ``from`` address (``uds:/tmp/cc-socks/<pid>.sock``) of another session's message, else None."""
    head = text.lstrip() if isinstance(text, str) else ""
    m = re.search(r'<cross-session-message\b[^>]*\bfrom="(uds:[^"]{1,300})"', head[:2000])
    return m.group(1) if m else None


def _cut(text: str, n: int) -> tuple[str, bool]:
    return (text, False) if len(text) <= n else (text[:n], True)


def _at(rec: dict) -> int | None:
    ts = rec.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def gone_images(text: str) -> list[str]:
    """The picture files a user text names ("[Image: source: /path, …]") that do not exist any more."""
    out = []
    for m in _IMAGE_NOTE.finditer(text):
        path = m.group(1).strip()
        if path.startswith("/") and "\0" not in path and not os.path.lexists(path):
            out.append(path[:300])
    return out[:20]


def _text_item(text: str, at, meta: bool) -> dict:
    peer = peer_of(text)
    if peer:
        body, cut = _cut(peer[1], TEXT_MAX)
        item = {"kind": "peer", "from": peer[0][:200], "text": body, "cut": cut, "at": at}
        addr = peer_addr(text)
        if addr:
            item["fromAddr"] = addr   # the reply address: the sender found by its socket or its pid (2.3.6)
        return item
    label = harness_label(text) or ("ハーネスの文" if meta else None)
    body, cut = _cut(text, TEXT_MAX)
    if label:
        return {"kind": "harness", "label": label, "text": body, "cut": cut, "at": at}
    item = {"kind": "user", "text": body, "cut": cut, "at": at}
    gone = gone_images(text)
    if gone:
        item["gone"] = gone
    return item


def _image_blocks(content) -> list[dict]:
    """The image blocks of a user record's content, in the order ``n`` counts them: its own, then those inside its
    tool results (a Read of a picture)."""
    out = []
    for b in content if isinstance(content, list) else []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "image":
            out.append(b)
        elif b.get("type") == "tool_result" and isinstance(b.get("content"), list):
            out.extend(x for x in b["content"] if isinstance(x, dict) and x.get("type") == "image")
    return out


def _image_ref(block: dict, off, n: int) -> dict | None:
    """Where one picture is, or None when it is not one the page may ask for (not base64, a media type not allowed)."""
    src = block.get("source")
    if off is None or not isinstance(src, dict) or src.get("type") != "base64" or src.get("media_type") not in IMAGE_TYPES:
        return None
    if not isinstance(src.get("data"), str) or not _looks_like(src["media_type"], src["data"][:24]):
        return None                                      # its bytes are not what it says: nothing to ask for
    return {"off": off, "n": n, "type": src["media_type"]}


def _looks_like(media: str, head64: str) -> bool:
    """Whether the first bytes of a base64 picture start as its media type does (image_at checks the whole)."""
    try:
        head = base64.b64decode(head64[: len(head64) // 4 * 4], validate=True)
    except (binascii.Error, ValueError):
        return False
    return head.startswith(IMAGE_TYPES[media]) and (media != "image/webp" or head[8:12] == b"WEBP")


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
                parts.append(b["text"])
            elif isinstance(b, dict) and b.get("type") == "image":
                parts.append("[画像]")
            elif isinstance(b, dict) and b.get("type") == "tool_reference":
                parts.append(f"[{b.get('tool_name') or 'tool'}]")
        return "\n".join(parts)
    return ""


_CHANNEL_WRAP = re.compile(r"^\s*<channel\b[^>]*>\n?(.*?)\n?</channel>\s*$", re.S)


def _channel_item(rec: dict, content, at) -> dict:
    """A channel's text the CLI put in the session (a prompt from the viz page, 2.3.4). Measured 10-19 on a real
    receiver (a terminal session started with --channels plugin:jui-viz@jsonui): a ``user`` record with ``isMeta``,
    ``origin: {"kind": "channel", "server": "plugin:jui-viz:jui-viz"}``, ``promptSource: "system"`` and the content
    ``<channel source="plugin:jui-viz:jui-viz" sender="jui_viz_page">\\n<text>\\n</channel>``. The item carries the
    text inside the wrapper and the server's name."""
    if isinstance(content, list):
        content = "\n".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    text = content if isinstance(content, str) else ""
    m = _CHANNEL_WRAP.match(text)
    body, cut = _cut(m.group(1) if m else text, TEXT_MAX)
    server = rec["origin"].get("server")
    return {"kind": "channel", "server": server[:200] if isinstance(server, str) else "", "text": body, "cut": cut, "at": at}


def _queued_items(d: dict) -> list[dict]:
    """A message that came while the session was working (ticket 2026-10-20-jui-viz-history-misses-mid-turn-deliveries;
    requester: "届いてるのに応答の履歴に表示されない"): a queued_command attachment, read through talk_records.delivery
    (the one parse of ``origin``). It becomes the row its waiting form (a user record) makes: channel → the page's
    prompt without its <channel> wrapper; peer → "<name> から" with the body and the reply address; human → the
    requester's words; coordinator, task-notification and any other → the harness's text. Its time is the record's
    (when it arrived), not when the turn took it."""
    at, text = d["at"], d["prompt"] or ""
    if d["kind"] == "channel":
        return [_channel_item({"origin": d["origin"]}, text, at)] if text.strip() else []
    if d["kind"] == "peer":
        body = d["body"] if d["body"] is not None else (peer_of(text) or ("", text))[1]
        if not body.strip():
            return []
        cut_body, cut = _cut(body, TEXT_MAX)
        item = {"kind": "peer", "from": (d["name"] or d["task"] or (peer_of(text) or ("別のセッション",))[0])[:200],
                "text": cut_body, "cut": cut, "at": at}
        addr = d["from"] if d["from"] and d["from"].startswith("uds:") else peer_addr(text)
        if addr:
            item["fromAddr"] = addr[:304]
        return [item]
    if not text.strip():
        return []
    return [_text_item(text, at, d["kind"] != "human")]


def items_of(rec, results: dict, off: int | None = None) -> list[dict]:
    """The items of one record, in order. tool_result blocks go into ``results`` (tool_use_id -> OUT). ``off`` is the
    byte offset of the record's line in its transcript: a picture is named by it (and its place in the record)."""
    if isinstance(rec, dict) and rec.get("type") == "attachment":
        d = delivery(rec)
        return _queued_items(d) if d is not None and d["queued"] else []
    if not isinstance(rec, dict) or rec.get("type") not in ("user", "assistant"):
        return []
    msg = rec.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    at, out = _at(rec), []
    if rec["type"] == "user":
        if isinstance(rec.get("origin"), dict) and rec["origin"].get("kind") == "channel":
            return [_channel_item(rec, content, at)]
        if isinstance(content, str):
            return [_text_item(content, at, rec.get("isMeta") is True)] if content.strip() else []
        n = 0
        for b in content if isinstance(content, list) else []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and isinstance(b.get("text"), str) and b["text"].strip():
                out.append(_text_item(b["text"], at, rec.get("isMeta") is True))
            elif b.get("type") == "tool_result" and isinstance(b.get("tool_use_id"), str):
                text, cut = _cut(_result_text(b.get("content")), IO_MAX)
                got = {"out": text, "outCut": cut, "error": b.get("is_error") is True}
                imgs = []
                for x in _image_blocks([b]):
                    ref = _image_ref(x, off, n)
                    n += 1
                    if ref:
                        imgs.append(ref)
                if imgs:
                    got["imgs"] = imgs
                results[b["tool_use_id"]] = got
            elif b.get("type") == "image":
                item = {"kind": "image", "at": at}
                ref = _image_ref(b, off, n)
                n += 1
                if ref:
                    item["img"] = ref
                out.append(item)
        return out
    sent_n = 0
    for b in content if isinstance(content, list) else []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and isinstance(b.get("text"), str) and b["text"].strip():
            text, cut = _cut(b["text"], TEXT_MAX)
            out.append({"kind": "assistant", "text": text, "cut": cut, "at": at})
        elif b.get("type") == "tool_use":
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            raw = inp["command"] if isinstance(inp.get("command"), str) else json.dumps(inp, ensure_ascii=False, indent=1)
            text, cut = _cut(raw, IO_MAX)
            desc = inp.get("description") if isinstance(inp.get("description"), str) else ""
            item = {"kind": "tool", "id": str(b.get("id") or ""), "name": str(b.get("name") or "?")[:120],
                    "description": desc[:300], "in": text, "inCut": cut, "at": at}
            if item["name"] == "SendUserFile" and isinstance(inp.get("files"), list):
                # files the session sent to the person (ticket 2026-10-20-jui-viz-history-senduserfile-image-no-thumb):
                # their names, and which are pictures by name; the page asks for one by (off, n) — never by path
                files = [f for f in inp["files"] if isinstance(f, str)][:SENT_FILES_MAX]
                item["sent"] = [{"n": sent_n + i, "name": os.path.basename(f)[:200], "image": _sent_media(f) is not None, "off": off}
                                for i, f in enumerate(files)]
                sent_n += len(files)                          # n counts every call's files in the record, in order
                if isinstance(inp.get("caption"), str) and inp["caption"].strip():
                    item["caption"] = _cut(inp["caption"], 600)[0]
            if item["name"] in FILE_TOOLS and isinstance(inp.get(FILE_TOOLS[item["name"]]), str) and inp[FILE_TOOLS[item["name"]]]:
                # the file it names, by its name and the call's line (2.3.12): the page asks Finder for it by (off, id), never by path
                item["file"] = {"name": os.path.basename(inp[FILE_TOOLS[item["name"]]])[:200] or "?", "off": off}
            if item["name"] == "SendMessage" and isinstance(inp.get("to"), str):
                # the folded row says who it went to and what about (2.3.6): input.summary, else the message's first line
                first = next((ln.strip() for ln in str(inp.get("message") or "").splitlines() if ln.strip()), "")
                item["to"] = inp["to"][:200]
                item["summary"] = (inp["summary"] if isinstance(inp.get("summary"), str) and inp["summary"].strip() else first)[:300]
            out.append(item)
        elif b.get("type") in ("thinking", "redacted_thinking"):
            out.append({"kind": "thought", "at": at})     # a mark: its text is never sent
    return out


def safe_open(projects: Path, path: Path) -> int | None:
    """An fd on path when it is a regular .jsonl under the projects folder reached through no symlink, else None."""
    try:
        if path.suffix != ".jsonl" or not path.parent.resolve().is_relative_to(projects.resolve()):
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


def _line_at(fd: int, off, cap: int):
    """The JSON record whose line starts at byte off of the transcript open on fd: (None, rec), or (status, reason)."""
    if not isinstance(off, int) or isinstance(off, bool) or off < 0:
        return 404, "no such record"
    size = os.fstat(fd).st_size
    if off >= size or (off > 0 and os.pread(fd, 1, off - 1) != b"\n"):
        return 404, "no such record"
    line, pos = b"", off
    while True:
        chunk = os.pread(fd, min(1_048_576, cap + 1 - len(line)), pos)
        if not chunk:
            break
        cut = chunk.find(b"\n")
        if cut >= 0:
            line += chunk[:cut]
            break
        line += chunk
        pos += len(chunk)
        if len(line) > cap:
            return 413, "too large"
    try:
        return None, json.loads(line)
    except ValueError:
        return 404, "no such record"


def _sent_media(path: str) -> str | None:
    ext = path.rsplit(".", 1)[-1].lower() if "." in os.path.basename(path) else ""
    return SENT_IMAGE_EXT.get(ext)


def _sent_path(fd: int, off, n) -> tuple[int, str]:
    """The n-th path a SendUserFile call in the assistant record at byte off names, resolved as it is read: none with a
    ".." part, a relative one from the record's cwd. (200, path), else (status, reason). The one place this rule is
    (sent_file_at reads the picture, sent_reveal_at shows the file in Finder)."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        return 404, "no such file"
    status, rec = _line_at(fd, off, SENT_LINE_MAX)
    if status is not None:
        return status, rec
    msg = rec.get("message") if isinstance(rec, dict) and rec.get("type") == "assistant" else None
    files: list = []
    for b in msg.get("content") if isinstance(msg, dict) and isinstance(msg.get("content"), list) else []:
        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "SendUserFile":
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            files += [f for f in inp.get("files") or [] if isinstance(f, str)][:SENT_FILES_MAX]   # every call's, in order (items_of counts so)
    if n >= len(files):
        return 404, "no such file"
    return _resolve(files[n], rec)


def _resolve(path: str, rec: dict) -> tuple[int, str]:
    """A path a record names, as it is read or shown: none with a ".." part, a relative one from the record's cwd."""
    if ".." in Path(path).parts:
        return 403, "not this path"
    if not os.path.isabs(path):
        cwd = rec.get("cwd")
        if not isinstance(cwd, str) or not os.path.isabs(cwd):
            return 404, "no such file"
        path = os.path.join(cwd, path)
    return 200, path


# the tools whose input names one file, and the key it is under (2.3.12: the row shows it as a link to Finder)
FILE_TOOLS = {"Read": "file_path", "Edit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path"}


def _shown(path: str) -> tuple[int, str]:
    """A resolved path to show in Finder: a regular file, not a symlink last (lstat)."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return 404, "gone"
    except OSError:
        return 403, "not a file to show"
    if not stat.S_ISREG(st.st_mode):
        return 403, "not a file to show"           # a symlink, a folder, a device
    return 200, path


def tool_file_reveal_at(fd: int, off, use_id) -> tuple[int, str]:
    """The file a Read / Edit / Write / NotebookEdit call names (FILE_TOOLS), to show in Finder (2.3.12, the requester's
    「画像以外はファイル名出してリンクっぽく」 and the ruling of 10-21: the files the history shows): the tool_use with this
    id in the assistant record at byte off, its input's path, resolved as a sent file's is. (200, path), (404, "gone"),
    or (status, reason)."""
    if not isinstance(use_id, str) or not use_id:
        return 404, "no such call"
    status, rec = _line_at(fd, off, SENT_LINE_MAX)
    if status is not None:
        return status, rec
    msg = rec.get("message") if isinstance(rec, dict) and rec.get("type") == "assistant" else None
    for b in msg.get("content") if isinstance(msg, dict) and isinstance(msg.get("content"), list) else []:
        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") == use_id and b.get("name") in FILE_TOOLS:
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            path = inp.get(FILE_TOOLS[b["name"]])
            if not isinstance(path, str) or not path:
                return 404, "no such file"
            status, path = _resolve(path, rec)
            return (status, path) if status != 200 else _shown(path)
    return 404, "no such call"


def sent_reveal_at(fd: int, off, n) -> tuple[int, str]:
    """The path of the n-th file a SendUserFile call sent, to show in Finder (2.3.12, requester 10-21: 「画像以外はファイル
    名出してリンクっぽくして、押したらfinderでそのファイル選択してウィンドウ開く」): the same path as sent_file_at reads,
    any kind of file, a regular file only and not a symlink last (lstat). (200, path), (404, "gone"), or (status, reason)."""
    status, path = _sent_path(fd, off, n)
    return (status, path) if status != 200 else _shown(path)


def sent_file_at(fd: int, off, n) -> tuple[int, object]:
    """The n-th file a SendUserFile call in the assistant record at byte off sent (ticket 2026-10-20-jui-viz-history-
    senduserfile-image-no-thumb; the transcript holds only its path: measured 10-20, 11 of 11 files). Read from disk,
    only that path: none with a ".." part, the last part no symlink (O_NOFOLLOW), a relative one from the record's cwd;
    a regular file of at most SENT_FILE_MAX whose name and first bytes are both a picture's (no SVG).
    (200, (media, bytes)); (404, "gone") when it is no longer there; else (status, reason)."""
    status, path = _sent_path(fd, off, n)
    if status != 200:
        return status, path
    media = _sent_media(path)
    if media is None:
        return 415, "not a picture"
    try:
        out = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return 404, "gone"
    except OSError:
        return 403, "not a file to read"           # a symlink last (ELOOP), or not readable
    try:
        st = os.fstat(out)
        if not stat.S_ISREG(st.st_mode):
            return 403, "not a file to read"
        data = b""                                     # read up to SENT_FILE_MAX + 1: one byte more is "too large"
        while len(data) <= SENT_FILE_MAX:
            chunk = os.read(out, SENT_FILE_MAX + 1 - len(data))
            if not chunk:
                break
            data += chunk
    finally:
        os.close(out)
    if len(data) > SENT_FILE_MAX:
        return 413, "too large"
    if not data.startswith(IMAGE_TYPES[media]) or (media == "image/webp" and data[8:12] != b"WEBP"):
        return 415, "not a picture"
    return 200, (media, data)


def image_at(fd: int, off, n) -> tuple[int, str | bytes]:
    """The n-th picture of the record whose line starts at byte off of the transcript open on fd.

    (200, media type) with the bytes as a third value is returned as (200, (media, data)); otherwise (status, reason):
    404 when off is not the start of a line, the line is not a user record, or it has no n-th picture; 415 when the
    picture is not base64, its media type is not allowed, or its bytes do not start as that type does; 413 when the
    line or the decoded picture is over the cap. Only this transcript, only this line: nothing else is read."""
    if not isinstance(off, int) or isinstance(off, bool) or not isinstance(n, int) or isinstance(n, bool) or off < 0 or n < 0:
        return 404, "no such image"
    size = os.fstat(fd).st_size
    if off >= size or (off > 0 and os.pread(fd, 1, off - 1) != b"\n"):
        return 404, "no such image"
    line, pos = b"", off
    while True:
        chunk = os.pread(fd, min(1_048_576, IMAGE_LINE_MAX + 1 - len(line)), pos)
        if not chunk:
            break
        cut = chunk.find(b"\n")
        if cut >= 0:
            line += chunk[:cut]
            break
        line += chunk
        pos += len(chunk)
        if len(line) > IMAGE_LINE_MAX:
            return 413, "too large"
    try:
        rec = json.loads(line)
    except ValueError:
        return 404, "no such image"
    msg = rec.get("message") if isinstance(rec, dict) and rec.get("type") == "user" else None
    blocks = _image_blocks(msg.get("content") if isinstance(msg, dict) else None)
    if n >= len(blocks):
        return 404, "no such image"
    src = blocks[n].get("source")
    media = src.get("media_type") if isinstance(src, dict) else None
    if not isinstance(src, dict) or src.get("type") != "base64" or media not in IMAGE_TYPES or not isinstance(src.get("data"), str):
        return 415, "not an allowed image"
    if len(src["data"]) > (IMAGE_MAX * 4) // 3 + 8:
        return 413, "too large"
    try:
        data = base64.b64decode(src["data"], validate=True)
    except (binascii.Error, ValueError):
        return 415, "not an allowed image"
    if len(data) > IMAGE_MAX:
        return 413, "too large"
    if not data.startswith(IMAGE_TYPES[media]) or (media == "image/webp" and data[8:12] != b"WEBP"):
        return 415, "not an allowed image"
    return 200, (media, data)


def read_tail(fd: int, items_max: int = ITEMS_MAX, bytes_max: int = BYTES_MAX) -> dict:
    """The last items_max items of the transcript open on fd, oldest first, reading backwards from its end."""
    size = os.fstat(fd).st_size
    pos, buf, read, records, bad, skip_tail = size, b"", 0, 0, 0, False
    newest_first: list[dict] = []
    results: dict = {}
    counted, more = 0, False
    seen: set = set()
    delivered: dict = {}                                 # a delivered message's key -> the rows its record made
    while pos > 0 and read < bytes_max and counted < items_max:
        step = min(CHUNK, pos, bytes_max - read)
        pos -= step
        chunk = os.pread(fd, step, pos)
        read += len(chunk)
        data = chunk + buf
        lines = data.split(b"\n")
        starts, o = [], pos                              # where each line begins in the file (a picture is named by it)
        for ln in lines:
            starts.append(o)
            o += len(ln) + 1
        buf = lines.pop(0) if pos > 0 else b""          # the start of a line whose beginning is further back
        if pos > 0:
            starts.pop(0)
        if skip_tail and lines:
            lines.pop()                                  # the rest of a line too long to keep
            starts.pop()
            skip_tail = False
        if len(buf) > LINE_MAX:
            buf, skip_tail = b"", True
        for line, start in zip(reversed(lines), reversed(starts)):
            if not line or len(line) > LINE_MAX:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, RecursionError):
                bad += 1
                continue
            records += 1
            got = items_of(rec, results, start)
            # one delivered message is one row, however many records say it (talk_records.delivery_key): its waiting
            # form (a user record) and its working form (a queued_command) share the msg_id, and a copy written again
            # (Remote Control, a resume) keeps its uuid. The first record of it is the one kept, in its place: reading
            # backwards, a later copy's rows already taken are dropped when an earlier record of it comes.
            d = delivery(rec) if got else None
            dk = delivery_key(d) if d is not None else None
            if dk is not None:
                for old in delivered.pop(dk, []):
                    newest_first[:] = [i for i in newest_first if i is not old]
                    if old["kind"] in COUNTED:
                        counted -= 1
                delivered[dk] = got
            msg = rec.get("message") if isinstance(rec, dict) else None
            mid = msg.get("id") if isinstance(msg, dict) else None
            for item in reversed(got):
                # one message is written more than once (transcripts.py): the same block counts once
                key = (mid, json.dumps(item, sort_keys=True, ensure_ascii=False)) if mid else None
                if key is not None:
                    if key in seen:
                        continue
                    seen.add(key)
                newest_first.append(item)
                if item["kind"] in COUNTED:
                    counted += 1
            if counted >= items_max:
                more = more or line is not lines[0]   # older lines of this chunk left unread
                break
    items = list(reversed(newest_first))
    while len([i for i in items if i["kind"] in COUNTED]) > items_max:
        items.pop(0)
        more = True
    while items and items[0]["kind"] not in COUNTED:
        items.pop(0)                                     # a mark with nothing before it
    for item in items:
        if item["kind"] == "tool" and item["id"] in results:
            item.update(results[item["id"]])
    return {"items": items, "bytes": read, "size": size, "records": records, "bad": bad,
            "more": more or pos > 0}


def reader(projects: Path) -> Callable[..., dict | None]:
    """read(session_id, cwd, given, agent_id=None, agent_given=None) -> the tab's payload, or None (no transcript)."""
    projects = Path(projects)
    cache: dict = {}

    def paths(session_id, cwd, given, agent_id, agent_given) -> list[Path]:
        mains = candidates(projects, session_id, cwd, given)
        if not agent_id:
            return mains
        out = []
        if isinstance(agent_given, str) and agent_given.endswith(".jsonl"):
            out.append(Path(agent_given).expanduser())
        if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", agent_id):
            for main in mains:
                out.append(main.parent / session_id / "subagents" / f"agent-{agent_id}.jsonl")
        return out

    def read(session_id: str, cwd: str | None, given: str | None, agent_id: str | None = None,
             agent_given: str | None = None) -> dict | None:
        for path in paths(session_id, cwd, given, agent_id, agent_given):
            fd = safe_open(projects, path)
            if fd is None:
                continue
            try:
                st = os.fstat(fd)
                key = (str(path), st.st_size, st.st_mtime_ns)
                hit = cache.get(str(path))
                if hit and hit[0] == key:
                    return {**hit[1], "cached": True}
                got = read_tail(fd)
            finally:
                os.close(fd)
            if len(cache) >= 16:
                cache.pop(next(iter(cache)))
            cache[str(path)] = (key, got)
            return {**got, "cached": False}
        return None

    def image(session_id: str, cwd: str | None, given: str | None, agent_id: str | None, agent_given: str | None,
              off, n) -> tuple[int, object]:
        """One picture of the same transcript read() would read (image_at), or (404, ...) when there is none."""
        for path in paths(session_id, cwd, given, agent_id, agent_given):
            fd = safe_open(projects, path)
            if fd is None:
                continue
            try:
                return image_at(fd, off, n)
            finally:
                os.close(fd)
        return 404, "no transcript"

    def sent_file(session_id: str, cwd: str | None, given: str | None, agent_id: str | None, agent_given: str | None,
                  off, n) -> tuple[int, object]:
        """One file a SendUserFile call of the same transcript sent (sent_file_at)."""
        for path in paths(session_id, cwd, given, agent_id, agent_given):
            fd = safe_open(projects, path)
            if fd is None:
                continue
            try:
                return sent_file_at(fd, off, n)
            finally:
                os.close(fd)
        return 404, "no transcript"

    def sent_reveal(session_id: str, cwd: str | None, given: str | None, agent_id: str | None, agent_given: str | None,
                    off, n) -> tuple[int, str]:
        """The path of one file a SendUserFile call of the same transcript sent, to show in Finder (sent_reveal_at)."""
        for path in paths(session_id, cwd, given, agent_id, agent_given):
            fd = safe_open(projects, path)
            if fd is None:
                continue
            try:
                return sent_reveal_at(fd, off, n)
            finally:
                os.close(fd)
        return 404, "no transcript"

    def tool_reveal(session_id: str, cwd: str | None, given: str | None, agent_id: str | None, agent_given: str | None,
                    off, use_id) -> tuple[int, str]:
        """The file a file tool's call of the same transcript names, to show in Finder (tool_file_reveal_at)."""
        for path in paths(session_id, cwd, given, agent_id, agent_given):
            fd = safe_open(projects, path)
            if fd is None:
                continue
            try:
                return tool_file_reveal_at(fd, off, use_id)
            finally:
                os.close(fd)
        return 404, "no transcript"

    read.image = image
    read.sent_file = sent_file
    read.sent_reveal = sent_reveal
    read.tool_reveal = tool_reveal
    return read
