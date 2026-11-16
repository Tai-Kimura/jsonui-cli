"""`jui viz statusline install / uninstall / status`: the statusLine that hands the usage limits to jui viz.

Written to ~/.claude/settings.json only when the user runs install, through the same careful writer as the
hooks (hooks_installer._apply: JSON only, the original bytes backed up, an atomic write that keeps the mode,
a racing writer read again). A statusLine the user already had is never replaced: ours wraps it — its
command goes into ours (``--wrap <base64 of the whole statusLine>``), statusline.py runs it and prints its
output unchanged, and uninstall puts that exact object back. Only a statusLine whose command names
``jui_cli/viz/statusline.py`` is ours.
"""
from __future__ import annotations

import base64
import json
import shlex
import sys
from pathlib import Path

from . import hooks_installer as hi
from . import paths

MARKER = "jui_cli/viz/statusline.py"
KEEP = ("padding", "refreshInterval")   # the user's settings of the line itself stay as they were


def script_path() -> Path:
    return Path(__file__).resolve().with_name("statusline.py")


def _words(command) -> list[str]:
    try:
        return shlex.split(command) if isinstance(command, str) else []
    except ValueError:
        return []


def is_ours(line) -> bool:
    if not isinstance(line, dict):
        return False
    return any(w == MARKER or w.endswith("/" + MARKER) for w in _words(line.get("command")))


def wrapped_of(line) -> dict | None:
    """The statusLine ours wraps, or None."""
    words = _words(line.get("command")) if isinstance(line, dict) else []
    if "--wrap" not in words or words.index("--wrap") + 1 >= len(words):
        return None
    try:
        original = json.loads(base64.b64decode(words[words.index("--wrap") + 1].encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return original if isinstance(original, dict) else None


def our_line(original: dict | None = None, python: str | None = None) -> dict:
    command = f"{shlex.quote(python or sys.executable)} -I -S {shlex.quote(str(script_path()))}"
    line = {"type": "command", "command": command}
    if original:
        packed = base64.b64encode(json.dumps(original, ensure_ascii=False).encode("utf-8")).decode("ascii")
        line["command"] = f"{command} --wrap {packed}"
        line.update({k: original[k] for k in KEEP if k in original})
    return line


def install(dry_run: bool = False, python: str | None = None) -> hi.Result:
    def transform(data: dict):
        current = data.get("statusLine")
        if is_ours(current):
            return data, []
        new = dict(data)
        new["statusLine"] = our_line(current if isinstance(current, dict) else None, python)
        return new, []
    return hi._apply(transform, dry_run)


def uninstall(dry_run: bool = False) -> hi.Result:
    def transform(data: dict):
        current = data.get("statusLine")
        if not is_ours(current):
            return data, []
        new = dict(data)
        original = wrapped_of(current)
        if original is not None:
            new["statusLine"] = original
        else:
            new.pop("statusLine", None)
        return new, []
    return hi._apply(transform, dry_run)


def status() -> dict:
    path = paths.claude_settings()
    try:
        _, data, _ = hi._read(hi._target())
    except hi.SettingsError as exc:
        return {"readable": False, "error": str(exc), "path": str(path)}
    line = data.get("statusLine")
    original = wrapped_of(line) if is_ours(line) else None
    return {"readable": True, "path": str(path), "installed": is_ours(line),
            "wraps": original.get("command") if original else None,
            "other": bool(line) and not is_ours(line)}
