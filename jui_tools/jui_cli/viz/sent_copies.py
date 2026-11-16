"""Pictures a session sent with SendUserFile, copied when the call is made (ticket 2026-10-23-viz-sent-pictures-gone-
when-the-file-moves; requester: 「画像見えない / claude codeのアプリからなら見えるからバグだと思う」).

The transcript holds only a sent file's path (measured 10-20, 11 of 11). The app keeps its own copy when the file is
sent; the 応答の履歴 read the path only when a thumbnail came into view, so a file moved or removed after it was sent
showed 消えました. Now the server copies each picture of the call when its hook comes (PreToolUse, and PostToolUse when
the first did not), and the history shows that copy — what was sent, as the app shows it. A call seen without a hook
(a session without the plugin) is copied the first time the history reads its file while it is still there.

How a copy is kept:

  * ``<viz_home>/sent/`` (0700, this user's, opened without following a symlink), one file per picture named by the
    call's tool_use id and the file's place in that call: ``<id>-<i>.<png|jpg|gif|webp>``. Written to a temporary name
    with O_CREAT | O_EXCL | O_NOFOLLOW, mode 0600, then renamed; an existing copy is never written again.
  * Only a picture is copied, read by the history's own rule (sources/history.read_sent_picture): its name and its first
    bytes a picture's, a regular file, the last part no symlink, at most SENT_FILE_MAX (SendUserFile's own cap).
  * A picture that could not be copied leaves ``<id>-<i>.why`` with one word (too-large, not-picture, gone, unreadable):
    when the file is gone later, the history says why there is no copy.
  * At most STORE_MAX in all and nothing older than AGE_MAX_S: the oldest go first, after each copy.
"""
from __future__ import annotations

import os
import re
import secrets
import stat
import threading
import time
from pathlib import Path

from . import paths
from .attachments import Refused, _open_folder
from .sources.history import SENT_FILE_MAX, _sent_media, read_sent_picture, resolve_in

DIR = "sent"
STORE_MAX = 512 * 1024 * 1024
AGE_MAX_S = 30 * 24 * 3600
WHY = ("too-large", "not-picture", "gone", "unreadable")
_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
_USE = re.compile(r"[A-Za-z0-9_-]{1,100}")
_NAME = re.compile(r"[A-Za-z0-9_-]{1,100}-\d{1,2}\.(?:png|jpg|gif|webp|why)")


def _why(status: int, reason: object) -> str:
    """The word a picture that was not copied leaves (WHY), from read_sent_picture's answer."""
    if status == 404:
        return "gone"
    if status == 413:
        return "too-large"
    if status == 415:
        return "not-picture"
    return "unreadable"


class SentCopies:
    """The copies of the pictures sessions sent: taken when the call is made, read by the history."""

    def __init__(self, home: Path | None = None):
        self._home = home
        self._lock = threading.Lock()

    def _open(self, create: bool) -> int:
        home = self._home if self._home is not None else paths.viz_home()
        if create:
            home.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
        try:
            return _open_folder(fd, DIR, create)
        finally:
            os.close(fd)

    @staticmethod
    def _key(use: object, i: object) -> str | None:
        if not isinstance(use, str) or not _USE.fullmatch(use) or not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < 100:
            return None
        return f"{use}-{i}"

    # -- keep --------------------------------------------------------------------------------------------------------
    def take(self, use: object, files: list, cwd: object, now_s: float | None = None) -> list[str]:
        """The pictures of one call (its tool_use id, its files as the input names them, the hook's cwd): each copied
        unless it is already; one that is not a picture by name is left alone. Returns what each became."""
        out = []
        for i, f in enumerate(files):
            key = self._key(use, i)
            if key is None or not isinstance(f, str) or _sent_media(f) is None:
                out.append("skipped")
                continue
            status, path = resolve_in(f, cwd)
            got = read_sent_picture(path) if status == 200 else (status, path)
            out.append(self._store(key, *got))
        self.prune(time.time() if now_s is None else now_s)
        return out

    def keep(self, use: object, i: object, media: str, data: bytes) -> str:
        """A picture the history has just read from its path (a call seen without a hook): copied unless it is already."""
        key = self._key(use, i)
        return "skipped" if key is None else self._store(key, 200, (media, data))

    def _store(self, key: str, status: int, got: object) -> str:
        with self._lock:
            try:
                fd = self._open(create=True)
            except (OSError, Refused):
                return "unreadable"
            try:
                if any(self._exists(fd, f"{key}.{ext}") for ext in (*_EXT.values(), "why")):
                    return "kept"
                if status == 200:
                    media, data = got
                    name, body = f"{key}.{_EXT[media]}", data
                else:
                    name, body = f"{key}.why", _why(status, got).encode()
                tmp = f".{key}.{secrets.token_hex(4)}.tmp"
                out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                try:
                    view = memoryview(body)
                    while view:
                        view = view[os.write(out, view):]
                finally:
                    os.close(out)
                os.rename(tmp, name, src_dir_fd=fd, dst_dir_fd=fd)
                return "copied" if status == 200 else body.decode()
            except OSError:
                return "unreadable"
            finally:
                os.close(fd)

    @staticmethod
    def _exists(fd: int, name: str) -> bool:
        try:
            os.stat(name, dir_fd=fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    # -- read --------------------------------------------------------------------------------------------------------
    def read(self, use: object, i: object) -> tuple[int, object]:
        """(200, (media, bytes)) of the copy; (404, why) when there is none — why is a WHY word or ""."""
        key = self._key(use, i)
        if key is None:
            return 404, ""
        try:
            fd = self._open(create=False)
        except (OSError, Refused):
            return 404, ""
        try:
            for media, ext in _EXT.items():
                try:
                    f = os.open(f"{key}.{ext}", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    continue
                except OSError:
                    return 404, "unreadable"
                try:
                    st = os.fstat(f)
                    if not stat.S_ISREG(st.st_mode) or st.st_size > SENT_FILE_MAX:
                        return 404, "unreadable"
                    data = b""
                    while len(data) < st.st_size:
                        chunk = os.read(f, st.st_size - len(data))
                        if not chunk:
                            break
                        data += chunk
                finally:
                    os.close(f)
                return 200, (media, data)
            try:
                f = os.open(f"{key}.why", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError:
                return 404, ""
            try:
                word = os.read(f, 32).decode(errors="replace")
            finally:
                os.close(f)
            return 404, word if word in WHY else ""
        finally:
            os.close(fd)

    # -- go ----------------------------------------------------------------------------------------------------------
    def prune(self, now_s: float) -> list[str]:
        """Copies older than AGE_MAX_S, then the oldest until the rest is within STORE_MAX. Returns the names removed."""
        with self._lock:
            try:
                fd = self._open(create=False)
            except (OSError, Refused):
                return []
            gone: list[str] = []
            try:
                with os.scandir(fd) as it:
                    rows = [(e.name, e.stat(follow_symlinks=False)) for e in it]
                rows = sorted(((st.st_mtime, name, st.st_size) for name, st in rows
                               if stat.S_ISREG(st.st_mode) and (_NAME.fullmatch(name) or name.endswith(".tmp"))), reverse=True)
                total = 0
                for mtime, name, size in rows:                  # the newest first: they stay while there is room
                    stale = name.endswith(".tmp") and now_s - mtime > 3600
                    if stale or now_s - mtime > AGE_MAX_S or total + size > STORE_MAX:
                        try:
                            os.unlink(name, dir_fd=fd)
                            gone.append(name)
                        except OSError:
                            pass
                    elif not name.endswith(".tmp"):
                        total += size
            finally:
                os.close(fd)
            return gone
