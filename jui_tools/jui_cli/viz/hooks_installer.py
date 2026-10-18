"""Merge the jui viz hooks into ~/.claude/settings.json, and take them out again.

The user's settings file is shared with everything else they run, so:
  * only handlers whose command names ``jui_cli/viz/forward.py`` are ours —
    no other clue (order, position) is trusted;
  * a file that is not JSON is never written;
  * the original bytes are backed up first (10 kept), the write is atomic
    (temp file + os.replace) and keeps the file's mode, and a change made by
    someone else between our read and our write makes us read again (once);
  * uninstall removes our handlers and our env entry, and nothing else. It
    never restores a backup: that would drop what was written since.
"""
from __future__ import annotations

import copy
import difflib
import json
import os
import shlex
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

MARKER = "jui_cli/viz/forward.py"
EVENTS = (
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "PostToolUseFailure", "PermissionRequest", "PermissionDenied", "Notification",
    "SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted", "Stop",
    "StopFailure", "CwdChanged", "PreCompact", "PostCompact",
)
TOOL_EVENTS = frozenset({"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionDenied"})
PROGRESS_ENV = "JSONUI_TEST_PROGRESS_DIR"
BACKUPS_KEPT = 10


class SettingsError(Exception):
    """The settings file cannot be handled safely; nothing was written."""


@dataclass
class Result:
    changed: bool
    events: list[str] = field(default_factory=list)
    backup: Path | None = None
    diff: str = ""
    warnings: list[str] = field(default_factory=list)


def forward_path() -> Path:
    return Path(__file__).resolve().with_name("forward.py")


def progress_dir() -> Path:
    return paths.progress_dir()


def legacy_progress_values() -> set[str]:
    """Values of our env entry an earlier install wrote: the progress folder inside the install folder.

    Ours to replace (install) and to remove (uninstall); any other value is the user's.
    """
    return {str(paths.legacy_progress_dir())}


def our_handler(python: str | None = None, forward: Path | None = None) -> dict:
    python = python or sys.executable
    forward = forward or forward_path()
    return {
        "type": "command",
        "command": f"{shlex.quote(python)} -I -S {shlex.quote(str(forward))}",
        "async": True,
        "timeout": 5,
    }


def _is_forward(arg: str) -> bool:
    return arg == MARKER or arg.endswith("/" + MARKER)


def _is_python(exe: str) -> bool:
    return os.path.basename(exe).startswith("python")


#: The synchronous PermissionRequest hook (P6) is cut off by Claude Code
#: after this many seconds; the server answers within decideWaitSec (30 by
#: default), so this must stay well above it.
DECIDE_TIMEOUT_SEC = 60


def our_decide_handler(python: str | None = None, forward: Path | None = None) -> dict:
    """Not async: Claude Code waits for its answer — and, measured, shows the
    terminal dialog meanwhile and takes whichever answer comes first."""
    python = python or sys.executable
    forward = forward or forward_path()
    return {
        "type": "command",
        "command": f"{shlex.quote(python)} -I -S {shlex.quote(str(forward))} --decide",
        "timeout": DECIDE_TIMEOUT_SEC,
    }


def is_ours(handler) -> bool:
    """A python running forward.py — not merely a command that mentions its path.

    A substring match once removed a user's ``audit --watch …/jui_cli/viz/forward.py``
    (independent review, 10-18).
    """
    if not isinstance(handler, dict):
        return False
    command = handler.get("command")
    if not isinstance(command, str):
        return False
    args = handler.get("args")
    if isinstance(args, list):
        argv = [command, *[str(a) for a in args]]
    else:
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
    return bool(argv) and _is_python(argv[0]) and any(_is_forward(a) for a in argv[1:])


# ---------------------------------------------------------------- pure transforms


def strip_ours(settings: dict) -> tuple[dict, bool]:
    """A copy without our handlers. Containers we emptied go too; others stay as found."""
    out = copy.deepcopy(settings)
    hooks = out.get("hooks")
    if not isinstance(hooks, dict):
        return out, False
    removed_any = False
    for event in list(hooks.keys()):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept_groups = []
        emptied_here = False
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                kept_groups.append(group)
                continue
            kept = [h for h in group["hooks"] if not is_ours(h)]
            if len(kept) == len(group["hooks"]):
                kept_groups.append(group)
                continue
            removed_any = emptied_here = True
            if kept:
                kept_groups.append(dict(group, hooks=kept))
        if emptied_here:
            if kept_groups:
                hooks[event] = kept_groups
            else:
                del hooks[event]
    if removed_any and not hooks:
        del out["hooks"]
    return out, removed_any


def add_ours(settings: dict, handler: dict, decide_handler: dict | None = None) -> dict:
    out, _ = strip_ours(settings)
    hooks = out.get("hooks")
    if hooks is None:
        hooks = out["hooks"] = {}
    if not isinstance(hooks, dict):
        raise SettingsError("settings.json の hooks がオブジェクトではありません。直してから再実行してください")
    for event in EVENTS:
        groups = hooks.get(event)
        if groups is None:
            groups = hooks[event] = []
        if not isinstance(groups, list):
            raise SettingsError(f"settings.json の hooks.{event} が配列ではありません。直してから再実行してください")
        group = {"matcher": "*", "hooks": [handler]} if event in TOOL_EVENTS else {"hooks": [handler]}
        groups.append(group)
        if event == "PermissionRequest" and decide_handler is not None:
            groups.append({"matcher": "*", "hooks": [decide_handler]})
    return out


def add_env(settings: dict, value: str) -> tuple[dict, str | None]:
    """Set our env entry unless the user already set it to something else."""
    out = copy.deepcopy(settings)
    env = out.get("env")
    if env is not None and not isinstance(env, dict):
        return out, "settings.json の env がオブジェクトではないため、テストの進捗の場所を入れませんでした"
    current = (env or {}).get(PROGRESS_ENV)
    if current is not None and current != value and current not in legacy_progress_values():
        return out, f"env の {PROGRESS_ENV} に別の値が入っているため上書きしません（テストの進捗は取れません）"
    out.setdefault("env", {})[PROGRESS_ENV] = value
    return out, None


def strip_env(settings: dict, value: str) -> dict:
    out = copy.deepcopy(settings)
    env = out.get("env")
    if isinstance(env, dict) and (env.get(PROGRESS_ENV) == value or env.get(PROGRESS_ENV) in legacy_progress_values()):
        del env[PROGRESS_ENV]
        if not env:
            del out["env"]
    return out


# ---------------------------------------------------------------- file handling


def _target() -> Path:
    path = paths.claude_settings()
    return path.resolve() if path.is_symlink() else path


def _read(path: Path) -> tuple[bytes | None, dict, tuple | None]:
    if not path.exists():
        return None, {}, None
    # Stat before AND after reading: a write landing between the read and a
    # single stat would be taken as what we read, and lost (review, 10-18).
    for _ in range(3):
        st = path.stat()
        before = (st.st_mtime_ns, st.st_size)
        raw = path.read_bytes()
        st = path.stat()
        if (st.st_mtime_ns, st.st_size) == before:
            break
    else:
        raise SettingsError("settings.json が読んでいる間に変わり続けたため中止しました。少し待って再実行してください")
    try:
        data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (UnicodeDecodeError, ValueError):
        raise SettingsError("settings.json が JSON として読めません。直してから再実行してください")
    if not isinstance(data, dict):
        raise SettingsError("settings.json の中身がオブジェクトではありません。直してから再実行してください")
    return raw, data, before


def _dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _backup(raw: bytes) -> Path:
    folder = paths.backups_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = folder / f"settings.json.{stamp}.bak"
    n = 1
    while target.exists():
        n += 1
        target = folder / f"settings.json.{stamp}-{n}.bak"
    target.write_bytes(raw)
    os.chmod(target, 0o600)
    olds = sorted(folder.glob("settings.json.*.bak"), key=lambda p: p.stat().st_mtime_ns)
    for old in olds[:-BACKUPS_KEPT]:
        old.unlink()
    return target


def _write(path: Path, text: str, mode: int | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.jui-viz-{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fchmod(fd, mode if mode is not None else 0o600)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _apply(transform, dry_run: bool) -> Result:
    """Read, transform, and write if the result differs. Retries once on a racing writer."""
    path = _target()
    for attempt in range(2):
        raw, data, stamp = _read(path)
        new, warnings = transform(data)
        changed = new != data or raw is None and new != {}
        diff = "".join(difflib.unified_diff(
            _dump(data).splitlines(keepends=True) if raw is not None else [],
            _dump(new).splitlines(keepends=True),
            fromfile=str(path), tofile=str(path) + "（変更後）",
        ))
        result = Result(changed=changed, diff=diff, warnings=warnings)
        if dry_run or not changed:
            return result
        mode = path.stat().st_mode & 0o777 if raw is not None else None
        if raw is not None:
            st = path.stat()
            if (st.st_mtime_ns, st.st_size) != stamp:
                continue  # someone wrote between our read and now: read again
            result.backup = _backup(raw)
        _write(path, _dump(new), mode)
        return result
    raise SettingsError("settings.json が書き込みの直前に別の手で変わり続けたため中止しました。少し待って再実行してください")


PLUGIN_PREFIX = "jui-viz@"


def plugin_enabled(data: dict | None = None) -> str | None:
    """The enabledPlugins key of the jui-viz plugin when it is enabled, else None.

    The plugin (plugins/jui-viz, `/plugin install jui-viz@jsonui`) carries the
    same hooks; installing these as well would forward every event twice.
    """
    if data is None:
        try:
            _, data, _ = _read(_target())
        except SettingsError:
            return None
    enabled = data.get("enabledPlugins") if isinstance(data.get("enabledPlugins"), dict) else {}
    for key, on in enabled.items():
        if isinstance(key, str) and key.startswith(PLUGIN_PREFIX) and on is True:
            return key
    return None


def install(dry_run: bool = False, python: str | None = None) -> Result:
    handler = our_handler(python)
    decide_handler = our_decide_handler(python)
    value = str(progress_dir())

    def transform(data: dict):
        plugin = plugin_enabled(data)
        if plugin:
            raise SettingsError(f"プラグイン {plugin} が有効なので、フックは入れません（二重に転送されます）。"
                                "プラグインを使わない場合は /plugin で無効にしてから再実行してください")
        new = add_ours(data, handler, decide_handler)
        new, warning = add_env(new, value)
        return new, [w for w in (warning,) if w] + _disabled_warning(new)

    result = _apply(transform, dry_run)
    result.events = list(EVENTS)
    return result


def uninstall(dry_run: bool = False) -> Result:
    value = str(progress_dir())

    def transform(data: dict):
        new, _ = strip_ours(data)
        return strip_env(new, value), []

    return _apply(transform, dry_run)


def _disabled_warning(data: dict) -> list[str]:
    return ["フックが全体で無効になっています（disableAllHooks: true）"] if data.get("disableAllHooks") is True else []


def status() -> dict:
    path = _target()
    try:
        _, data, _ = _read(path)
    except SettingsError as exc:
        return {"readable": False, "error": str(exc), "events": {}}
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    events: dict[str, bool] = {}
    commands: list[str] = []
    others = False
    for event in EVENTS:
        found = False
        for group in hooks.get(event, []) if isinstance(hooks.get(event), list) else []:
            for h in group.get("hooks", []) if isinstance(group, dict) else []:
                if is_ours(h):
                    found = True
                    commands.append(str(h.get("command", "")))
                else:
                    others = True
        events[event] = found
    broken = []
    for command in set(commands):
        try:
            argv = shlex.split(command)
        except ValueError:
            broken.append(command)
            continue
        exe = argv[0] if argv else ""
        script = next((a for a in argv if a.endswith("forward.py")), "")
        if not (exe and Path(exe).exists() and script and Path(script).exists()):
            broken.append(command)
    decide = any(is_ours(h) and "--decide" in str(h.get("command", ""))
                 for g in (hooks.get("PermissionRequest") or []) if isinstance(g, dict)
                 for h in (g.get("hooks") or []))
    env = data.get("env") if isinstance(data.get("env"), dict) else {}
    return {
        "plugin": plugin_enabled(data),
        "decide": decide,
        "readable": True,
        "path": str(path),
        "events": events,
        "installed": sum(events.values()),
        "broken": broken,
        "otherHooks": others or any(e not in EVENTS for e in hooks),
        "disableAllHooks": data.get("disableAllHooks") is True,
        "progressEnv": env.get(PROGRESS_ENV),
    }
