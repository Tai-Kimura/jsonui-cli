"""Files attached to a prompt typed in the page (ticket 2026-10-20-jui-viz-prompt-attach-files-and-paste-images).

The page sends each file to POST /api/attach (the checks of /api/prompt, with this route's own size and type); the
server keeps it here and answers an id. POST /api/prompt then names the ids, and the prompt's text gets one line per
file with its absolute path, which the receiving session opens with Read.

The files are kept in one place only, ``<viz_home>/uploads/<session>/`` (0700), named by ``Attachments.folder``.
The receiving session's Read of it goes through its ordinary permission check (measured 10-20 10:39: a file outside
the working folder gives a PermissionRequest), which the viz permission board and notification show. viz never
changes the receiving session's settings or permission rules, and adds nothing that widens them (requester 10-20).

How a file is written and removed:

  * Names are made by the server (16 hex characters and an extension from a short list). The name the person gave is
    kept for display only and never becomes part of a path.
  * Every folder below the base is opened with O_NOFOLLOW | O_DIRECTORY and must be this user's and 0700; files are
    created relative to that folder's descriptor with O_CREAT | O_EXCL | O_NOFOLLOW, mode 0600.
  * Removal opens the session's folder the same way and unlinks each entry through that descriptor (unlink never
    follows a symlink), then removes the folder.
  * Limits: FILE_MAX per file, PER_PROMPT_MAX per prompt, SESSION_FILES_MAX and SESSION_BYTES_MAX per session.
  * A session's files are removed KEEP_MS after it ended (the talk view's hour). At start, folders under the private
    base that no running server knows and that are older than KEEP_MS are removed (sweep_private).
"""
from __future__ import annotations

import os
import re
import secrets
import stat
from pathlib import Path

from . import paths

FILE_MAX = 20 * 1024 * 1024
PER_PROMPT_MAX = 10
SESSION_FILES_MAX = 100
SESSION_BYTES_MAX = 200 * 1024 * 1024
KEEP_MS = 3_600_000
NAME_MAX = 120

PRIVATE_DIR = "uploads"

_SID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_ID = re.compile(r"[0-9a-f]{16}")

# extension -> media type. Anything else is kept as .bin (application/octet-stream).
EXTENSIONS = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
    "pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown", "csv": "text/csv", "log": "text/plain",
    "json": "application/json", "yaml": "text/plain", "yml": "text/plain", "xml": "text/plain", "html": "text/plain",
    "css": "text/plain", "js": "text/plain", "ts": "text/plain", "tsx": "text/plain", "py": "text/plain",
    "rb": "text/plain", "swift": "text/plain", "kt": "text/plain",
}
# the first bytes an image must start with to keep its image extension
_MAGIC = {
    "png": (b"\x89PNG\r\n\x1a\n",), "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"), "webp": (b"RIFF",), "pdf": (b"%PDF-",),
}
# an image pasted from the clipboard has no name of its own; its media type gives the extension
_MEDIA_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}


class Refused(Exception):
    """A file that is not kept: ``status`` is the HTTP status, the message says why."""

    def __init__(self, status: int, why: str):
        super().__init__(why)
        self.status = status


def display_name(name: object, media: str = "") -> str:
    """The name to show: the last part of what the page sent, without control characters, at most NAME_MAX."""
    text = name if isinstance(name, str) else ""
    text = re.split(r"[/\\]", text)[-1]
    text = "".join(ch for ch in text if ch.isprintable()).strip()
    if not text:
        text = f"貼り付けた画像.{_MEDIA_EXT[media]}" if media in _MEDIA_EXT else "添付"
    return text[:NAME_MAX]


def extension(name: str, media: str, head: bytes) -> str:
    """The stored file's extension: from the shown name when it is on the list (an image's only when its bytes start
    like one), else from the pasted image's media type, else bin."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in EXTENSIONS:
        ext = _MEDIA_EXT.get(media, "")
    if ext in _MAGIC and not head.startswith(_MAGIC[ext]):
        return "bin"
    return ext or "bin"


def _own_folder(fd: int) -> None:
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        raise Refused(409, "the attachment folder is not this user's folder")
    if stat.S_IMODE(st.st_mode) & 0o077:
        os.fchmod(fd, 0o700)


def _open_folder(parent_fd: int, name: str, create: bool) -> int:
    """``name`` under ``parent_fd``, never through a symlink, this user's and 0700; made when ``create``."""
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        _own_folder(fd)
    except BaseException:
        os.close(fd)
        raise
    return fd


class Attachments:
    """The attachments of every session this server knows: what is kept where, and when it goes."""

    def __init__(self, home: Path | None = None):
        self._home = home
        self.files: dict[str, dict[str, dict]] = {}
        self.ended: dict[str, int] = {}

    # -- where -------------------------------------------------------------------------------------------------------
    def folder(self, sid: str) -> tuple[Path, tuple[str, ...]] | None:
        """Where a session's files go: the base (opened as it is) and the folders under it (each opened without
        following a symlink). None for a session id that is not a plain name."""
        if not _SID.fullmatch(sid or ""):
            return None
        home = self._home if self._home is not None else paths.viz_home()
        return home, (PRIVATE_DIR, sid)

    def _open(self, sid: str, create: bool) -> int:
        where = self.folder(sid)
        if where is None:
            raise Refused(400, "not a session id")
        base, parts = where
        if create:
            base.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in parts:
                nxt = _open_folder(fd, part, create)
                os.close(fd)
                fd = nxt
        except BaseException:
            os.close(fd)
            raise
        return fd

    # -- keep --------------------------------------------------------------------------------------------------------
    def save(self, sid: str, name: object, media: str, data: bytes) -> dict:
        """Keep one file for ``sid``: its record {id, name, media, size, path}, or Refused."""
        if sid in self.ended:
            raise Refused(404, "this session has ended")
        if len(data) == 0:
            raise Refused(400, "empty file")
        if len(data) > FILE_MAX:
            raise Refused(413, "file too large")
        kept = self.files.get(sid, {})
        if len(kept) >= SESSION_FILES_MAX or sum(f["size"] for f in kept.values()) + len(data) > SESSION_BYTES_MAX:
            raise Refused(413, "too many attachments for this session")
        shown = display_name(name, media)
        ext = extension(shown, media, data[:16])
        fid = secrets.token_hex(8)
        stored = f"{fid}.{ext}"
        fd = self._open(sid, create=True)
        try:
            out = os.open(stored, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(out, view):]
            finally:
                os.close(out)
        finally:
            os.close(fd)
        base, parts = self.folder(sid)  # type: ignore[misc]
        record = {"id": fid, "name": shown, "media": EXTENSIONS.get(ext, "application/octet-stream"),
                  "size": len(data), "path": str(Path(base, *parts, stored)), "stored": stored}
        self.files.setdefault(sid, {})[fid] = record
        return record

    def take(self, sid: str, ids: object) -> list[dict]:
        """The records of ``ids`` for a prompt to ``sid`` (each kept for this session, still a plain file), or Refused."""
        if not isinstance(ids, list) or len(ids) > PER_PROMPT_MAX:
            raise Refused(400, f"attachments: a list of at most {PER_PROMPT_MAX}")
        kept = self.files.get(sid, {})
        out: list[dict] = []
        for fid in ids:
            if not isinstance(fid, str) or not _ID.fullmatch(fid) or fid not in kept:
                raise Refused(404, "no such attachment")
            out.append(kept[fid])
        if not out:
            return out
        fd = self._open(sid, create=False)
        try:
            for record in out:
                st = os.stat(record["stored"], dir_fd=fd, follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode) or st.st_size != record["size"]:
                    raise Refused(409, "an attachment changed after it was sent")
        except FileNotFoundError:
            raise Refused(404, "no such attachment") from None
        finally:
            os.close(fd)
        return out

    def remove(self, sid: str, fid: str) -> bool:
        """One file the person took off before sending (× on the page)."""
        record = self.files.get(sid, {}).pop(fid, None) if isinstance(fid, str) else None
        if record is None:
            return False
        try:
            fd = self._open(sid, create=False)
        except (OSError, Refused):
            return True
        try:
            os.unlink(record["stored"], dir_fd=fd)
        except FileNotFoundError:
            pass
        finally:
            os.close(fd)
        return True

    # -- go ----------------------------------------------------------------------------------------------------------
    def session_ended(self, sid: str, at: int) -> None:
        if sid in self.files:
            self.ended.setdefault(sid, at)

    def due(self, at: int) -> list[str]:
        """The sessions whose files are due to go (ended KEEP_MS ago)."""
        return [sid for sid, end in self.ended.items() if at - end >= KEEP_MS]

    def drop(self, sid: str) -> None:
        """Remove every file kept for ``sid`` and its folder; forget the session. Never follows a symlink."""
        where = self.folder(sid)
        try:
            if where is not None:
                remove_folder(*where)
        finally:
            self.files.pop(sid, None)
            self.ended.pop(sid, None)

    def sweep_private(self, now_s: float) -> list[str]:
        """At start: folders under the private base older than KEEP_MS (no server knows them now). Returns their names."""
        home = self._home if self._home is not None else paths.viz_home()
        try:
            fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
        except OSError:
            return []
        gone: list[str] = []
        try:
            try:
                ufd = _open_folder(fd, PRIVATE_DIR, create=False)
            except (OSError, Refused):
                return []
            try:
                with os.scandir(ufd) as it:
                    names = [(e.name, e.stat(follow_symlinks=False)) for e in it]
            finally:
                os.close(ufd)
            for name, st in names:
                if _SID.fullmatch(name) and stat.S_ISDIR(st.st_mode) and now_s - st.st_mtime >= KEEP_MS / 1000:
                    try:
                        remove_folder(home, (PRIVATE_DIR, name))
                        gone.append(name)
                    except (OSError, Refused):
                        pass
        finally:
            os.close(fd)
        return gone


def remove_folder(base: Path, parts: tuple[str, ...]) -> None:
    """Unlink every entry of base/parts through the folder's descriptor, then remove the folder. Each part is opened
    without following a symlink; a part that is a symlink is left alone (its target is never touched)."""
    try:
        fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        return
    chain = [fd]
    try:
        for part in parts:
            try:
                chain.append(_open_folder(chain[-1], part, create=False))
            except FileNotFoundError:
                return
            except OSError:   # ELOOP / ENOTDIR: a symlink or a file where the folder should be
                return
        leaf = chain[-1]
        with os.scandir(leaf) as it:
            names = [e.name for e in it]
        for name in names:
            try:
                os.unlink(name, dir_fd=leaf)
            except (IsADirectoryError, PermissionError, FileNotFoundError):
                pass   # a folder inside (never made by us): left, and so is ours
        try:
            os.rmdir(parts[-1], dir_fd=chain[-2])
        except OSError:
            pass
    finally:
        for f in reversed(chain):
            os.close(f)
