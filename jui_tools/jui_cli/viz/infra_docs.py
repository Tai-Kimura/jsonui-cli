"""The server room's model (ticket 2026-10-20-jui-viz-server-room, part B): viz's side of the boundary part A wrote
(docs/plans/2026-10-20-jui-viz-server-room-boundary.md, §5.2 and §8).

One reader for every room, document_tools' ``infra.room`` (reached as the spec documents' Mermaid builder is, through
core/document_tools_import): the room's jui.config.json ``infra`` (dir, icons), the *.json in that folder, each part
opened with O_NOFOLLOW, capped, merged and validated by ``infra.model.merge`` — a file that holds a secret-shaped value
is left out whole, references are checked, providers resolved, crossing edges marked, ``fold`` given its defaults.
viz keeps no rule of its own about the model: it counts, reads when the room's door is pressed, and gives the page
the result with the page's own ``seq`` (a reply to an older press is the page's to drop).

Blocking reads: the callers run them off the event loop (the count in the ingest's worker, the read and the icon in
the server's read pool).
"""
from __future__ import annotations

from pathlib import Path

from . import i18n
from . import infra_words

DEFAULT_DIR = "docs/infra"


def _room():
    from ..core.document_tools_import import load_document_tools_module
    mod, _where = load_document_tools_module("infra.room")
    return mod


def counts(root: Path | str, cache: dict | None = None) -> dict:
    """{"files": n, "dir": folder}: what the room's door needs; only the folder and jui.config.json are opened."""
    room = _room()
    if room is None:
        return {"files": 0, "dir": DEFAULT_DIR}
    got = room.counts(Path(root))
    if cache is not None:
        cache["counts"] = dict(got)
    return got


def read(root: Path | str, seq=None) -> tuple[int, dict]:
    """(HTTP status, the page's reply): §5.2's {ok: true, …, seq} or {ok: false, seq, reason, message}."""
    room = _room()
    if room is None:
        return 500, {"ok": False, "seq": seq, "reason": "unreadable",
                     "message": i18n.tl("srv.infra.no_tools")}
    out = room.read(Path(root), words=infra_words.RoomWords(room.LIMITS))   # its lines in the page's language
    out["seq"] = seq
    return (200 if out.get("ok") else room.REASONS.get(out.get("reason"), 500)), out


def icon(root: Path | str, key: str) -> tuple[bytes, str] | None:
    """The bytes and media type of the icon the room's settings give this key, or None (not configured, a URL, out of
    the room, not an image the boundary allows, too big)."""
    room = _room()
    if room is None or not isinstance(key, str):
        return None
    try:
        _folder, icons, _problems = room.infra_config(Path(root))
    except room.Refused:
        return None
    path = icons.get(key)
    return room.read_icon(Path(root), path) if path else None
