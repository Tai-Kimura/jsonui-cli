"""A room's declared infrastructure, read the one way the boundary allows (§2, §5.2 of
docs/plans/2026-10-20-jui-viz-server-room-boundary.md): where (jui.config.json's ``infra``), which files, how (from the
room's real root one part at a time with O_NOFOLLOW, the file itself O_NONBLOCK and fstat'ed as a regular file), how
much (LIMITS), and what goes wrong (a reason code). ``validate infra`` reads with it; jui viz may too.

The client never names a path: everything is under the room's root, chosen here. Self-contained (json, os, pathlib).
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path, PurePosixPath

from . import model as M

DEFAULT_DIR = "docs/infra"
CONFIG_NAME = "jui.config.json"
LIMITS = {"files": 50, "file_bytes": 4_000_000, "total_bytes": 16_000_000, "icons": 64, "icon_bytes": 256_000,
          "config_bytes": 1_000_000}
ICON_KEY = re.compile(r"^(?:service:[a-z0-9][a-z0-9.-]{0,39}/[a-z0-9][a-z0-9._/-]{0,63}"
                      r"|provider:[a-z0-9][a-z0-9.-]{0,39}|category:[a-z0-9][a-z0-9._]{0,39})$")
ICON_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp"}
REASONS = {"not_a_room": 404, "no_infra": 404, "bad_config": 400, "too_many_files": 413, "too_large": 413,
           "invalid": 422, "unreadable": 500}
SECRET_JA = {"arn": "ARN", "account_id": "アカウント ID", "ip_address": "IP アドレス", "connection_string": "接続文字列",
             "url_credentials": "URL の中の資格情報", "private_key": "秘密鍵", "access_key": "アクセスキー", "token": "トークン"}


def short(p: dict, folder: str) -> str:
    """One line the page can show as it is (boundary §5.2): the file (a path inside the room), the line when known, and
    the kind — never the value found (a secret's shape is named by its kind only)."""
    f = p.get("file") or ""
    where = f if f == CONFIG_NAME or not f else f"{folder}/{f}"
    code = p["code"]
    if code == "json":
        return f"{where}: {p['line']} 行目の JSON が壊れています" if p.get("line") else f"{where}: JSON として読めません"
    if code.startswith("secret."):
        return f"{where}: {p['path']} に秘密の形（{SECRET_JA.get(code[7:], code[7:])}）があります。値は書けません"
    if code == "schema":
        return f"{where}: {p['path']} がスキーマに合いません"
    if code in ("environment.conflict", "environment.missing", "id.duplicate", "group.missing", "group.cycle", "edge.missing"):
        return f"{where}: {p['path']} の参照が合いません（{code}）"
    if code == "model.too_big":
        return f"{folder}: 部屋のモデルが上限を超えています（{p['path'].lstrip('/')}）"
    if code == "read.too_large":
        return f"{where}: 1 ファイルの上限（{LIMITS['file_bytes'] // 1_000_000} MB）を超えています"
    if code == "read.unreadable":
        return f"{where}: 読めません"
    if code in ("config.icon", "read.icon"):
        return f"{CONFIG_NAME}: {p['path']} のアイコンが使えません"
    return f"{where}: {code}"


def _short_refused(reason: str, folder: str) -> str:
    return {"not_a_room": "この部屋は読めません",
            "no_infra": f"{folder} に infra のファイル（*.json）がありません",
            "bad_config": f"{CONFIG_NAME}: infra の設定が正しくありません（dir は部屋の中の相対パス）",
            "too_many_files": f"{folder}: ファイルが多すぎます（{LIMITS['files']} 個まで）",
            "too_large": f"{folder}: ファイルの合計が上限（{LIMITS['total_bytes'] // 1_000_000} MB）を超えています",
            "unreadable": f"{folder}: 読めません"}.get(reason, reason)


class Refused(Exception):
    """The room cannot be read at all: ``reason`` is one of REASONS."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason, self.message = reason, message


# ---------------------------------------------------------------- opening inside the room

def open_inside(root: Path, rel: str) -> int | None:
    """An fd of root/rel opened one part at a time from root's real path, every part O_NOFOLLOW (a symlink anywhere
    below the root, '.', '..' or an empty part: None), the last part O_NONBLOCK too (a FIFO never holds the open)."""
    flags_dir = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parts = PurePosixPath(rel).parts
    if not parts or any(p in ("", ".", "..", "/") for p in parts):
        return None
    try:
        fd = os.open(str(Path(root).resolve()), flags_dir)
    except OSError:
        return None
    try:
        for k, part in enumerate(parts):
            last = k == len(parts) - 1
            nxt = os.open(part, (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK) if last else flags_dir, dir_fd=fd)
            os.close(fd)
            fd = nxt
        out, fd = fd, None
        return out
    except OSError:
        return None
    finally:
        if fd is not None:
            os.close(fd)


TOO_BIG = object()


def read_capped(root: Path, rel: str, cap: int):
    """The bytes of a regular file under the room (at most cap; a bigger one, or one grown past it while read: TOO_BIG),
    or None (not there, not a regular file, a symlink on the way, unreadable)."""
    fd = open_inside(root, rel)
    if fd is None:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None
        if st.st_size > cap:
            return TOO_BIG
        chunks, n = [], 0
        while n <= cap:
            b = os.read(fd, min(1 << 16, cap + 1 - n))
            if not b:
                break
            chunks.append(b)
            n += len(b)
        return TOO_BIG if n > cap else b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


def _list_dir(root: Path, rel: str) -> list[tuple[str, int]] | None:
    """(name, size) of the regular *.json files directly in root/rel (no symlink on the way, none followed), by name;
    None when the folder is not there. Hidden names and *.check-report.json are not the model."""
    fd = open_inside(root, rel)
    if fd is None:
        return None
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            return None
        out = []
        for name in sorted(os.listdir(fd)):
            if not name.endswith(".json") or name.startswith(".") or name.endswith(".check-report.json"):
                continue
            try:
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                out.append((name, st.st_size))
        return out
    except OSError:
        return None
    finally:
        os.close(fd)


# ---------------------------------------------------------------- jui.config.json's "infra"

def _rel_ok(raw) -> bool:
    if not isinstance(raw, str) or not raw or len(raw) > 300 or "\\" in raw or "://" in raw:
        return False
    p = PurePosixPath(raw)
    return not p.is_absolute() and all(part not in ("", ".", "..") for part in p.parts)


def infra_config(root: Path) -> tuple[str, dict[str, str], list[dict]]:
    """(the folder, the icons usable, problems) from the room's jui.config.json. Raises Refused("bad_config") when the
    folder it names is not a relative path inside the room; an icon that breaks the rules is left out with a problem
    (code config.icon). No config, or no "infra": the defaults."""
    raw = read_capped(root, CONFIG_NAME, LIMITS["config_bytes"])
    if raw is None:
        return DEFAULT_DIR, {}, []
    if raw is TOO_BIG:
        raise Refused("bad_config", f"{CONFIG_NAME} is larger than {LIMITS['config_bytes']} bytes")
    try:
        cfg = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise Refused("bad_config", f"{CONFIG_NAME} is not JSON") from None
    infra = cfg.get("infra") if isinstance(cfg, dict) else None
    if infra is None:
        return DEFAULT_DIR, {}, []
    if not isinstance(infra, dict):
        raise Refused("bad_config", f'{CONFIG_NAME}: "infra" must be an object')
    folder = infra.get("dir", DEFAULT_DIR)
    if not _rel_ok(folder):
        raise Refused("bad_config", f'{CONFIG_NAME}: infra.dir must be a relative path inside the room (no "..", '
                                    "no absolute path, no URL)")
    problems, icons = [], {}
    raw_icons = infra.get("icons", {})
    if not isinstance(raw_icons, dict):
        problems.append(M._problem(CONFIG_NAME, "/infra/icons", "config.icon", "infra.icons must be an object"))
        raw_icons = {}
    for key, path in list(raw_icons.items()):
        where = f"/infra/icons/{key}"
        if len(icons) >= LIMITS["icons"]:
            problems.append(M._problem(CONFIG_NAME, where, "config.icon", f"more than {LIMITS['icons']} icons"))
            break
        if not ICON_KEY.match(key):
            problems.append(M._problem(CONFIG_NAME, where, "config.icon",
                                       "the key must be service:<provider>/<service>, provider:<provider> or category:<category>"))
        elif isinstance(path, str) and "://" in path:
            problems.append(M._problem(CONFIG_NAME, where, "config.icon",
                                       "a URL is not read (only an image inside the room: jui viz loads nothing from outside)"))
        elif not _rel_ok(path) or PurePosixPath(path).suffix.lower() not in ICON_TYPES:
            problems.append(M._problem(CONFIG_NAME, where, "config.icon",
                                       "must be a relative path inside the room to a .svg, .png or .webp"))
        elif key.startswith("category:") and key[9:] not in M.vocabulary("category"):
            problems.append(M._problem(CONFIG_NAME, where, "config.icon", "names a category the model does not have"))
        else:
            icons[key] = path
    return folder, icons, problems


def read_icon(root: Path, path: str) -> tuple[bytes, str] | None:
    """(bytes, media type) of one configured icon inside the room, within LIMITS["icon_bytes"]; None otherwise."""
    if not _rel_ok(path):
        return None
    media = ICON_TYPES.get(PurePosixPath(path).suffix.lower())
    raw = read_capped(root, path, LIMITS["icon_bytes"]) if media else None
    return (raw, media) if isinstance(raw, bytes) else None


# ---------------------------------------------------------------- counting and reading a room

def counts(root: Path) -> dict:
    """{"files": n, "dir": folder} — the model's files by their names and sizes only (nothing is opened but the
    folder and jui.config.json). n is 0 when there is none, or when the room's config cannot be used."""
    try:
        folder, _icons, _p = infra_config(Path(root))
    except Refused:
        return {"files": 0, "dir": DEFAULT_DIR}
    listed = _list_dir(Path(root), folder) or []
    return {"files": len(listed), "dir": folder}


def read(root: Path, is_room: bool = True) -> dict:
    """The room's model as the page takes it (§5.2): {ok, version, dir, files, environments, groups, nodes, edges,
    problems, icons, readMs}, or {ok: False, reason, message} when nothing could be read. Blocking: call it off the
    event loop."""
    t0 = time.monotonic()
    root = Path(root)
    try:
        if not is_room:
            raise Refused("not_a_room", "not a room jui viz knows")
        folder, icons, problems = infra_config(root)
        listed = _list_dir(root, folder)
        if not listed:
            raise Refused("no_infra", f"no model files in {folder} (*.json)")
        if len(listed) > LIMITS["files"]:
            raise Refused("too_many_files", f"{len(listed)} files in {folder}; at most {LIMITS['files']} are read")
        if sum(size for _n, size in listed) > LIMITS["total_bytes"]:
            raise Refused("too_large", f"the files in {folder} are over {LIMITS['total_bytes']} bytes together")
        files, total = [], 0
        for name, _size in listed:
            raw = read_capped(root, f"{folder}/{name}", min(LIMITS["file_bytes"], LIMITS["total_bytes"] - total))
            if raw is TOO_BIG:
                problems.append(M._problem(name, "/", "read.too_large", f"over {LIMITS['file_bytes']} bytes: not read"))
                continue
            if raw is None:
                problems.append(M._problem(name, "/", "read.unreadable", "could not be read as a regular file"))
                continue
            total += len(raw)
            files.append((name, raw))
        model, found = M.merge(files)
        problems.extend(found)
        if not model["files"]:                 # every file was left out: nothing to show, the first error says why
            first = next((p for p in problems if p["severity"] == "error"), None)
            for p in problems:
                p["short"] = short(p, folder)
            return {"ok": False, "reason": "invalid", "dir": folder,
                    "message": "no model file could be used", "short": first["short"] if first else folder,
                    "problems": problems}
        for key, path in list(icons.items()):
            if read_icon(root, path) is None:
                problems.append(M._problem(CONFIG_NAME, f"/infra/icons/{key}", "read.icon",
                                           "the image is not there, not a regular file, or too big"))
                del icons[key]
    except Refused as r:
        folder = locals().get("folder") or DEFAULT_DIR
        return {"ok": False, "reason": r.reason, "message": r.message, "short": _short_refused(r.reason, folder)}
    except OSError as exc:
        folder = locals().get("folder") or DEFAULT_DIR
        return {"ok": False, "reason": "unreadable", "message": f"reading failed ({exc.strerror or type(exc).__name__})",
                "short": _short_refused("unreadable", folder)}
    for p in problems:
        p["short"] = short(p, folder)
    out = {"ok": True, "dir": folder}
    out.update(model)
    out.update(problems=problems, icons=icons, readMs=int((time.monotonic() - t0) * 1000))
    return out
