"""How a session's process was started, for "can a prompt from the page reach it" (2.3.4, requester's ruling 10-19:
「1で出す」 — only a terminal session started with the development-channels flag).

The CLI (2.1.302/2.1.303, read in its binary, 10-19) hands a channel's ``notifications/claude/channel`` to the
session only when that channel was named at launch:
  * ``--dangerously-load-development-channels <entries...>`` — any channel (a confirmation at every start), or
  * ``--channels <entries...>`` — only a plugin on the approved allowlist. jui-viz is not on the default one; managed
    settings can put it there — measured 10-19 with the requester: /Library/Application Support/ClaudeCode/
    managed-settings.json = {"channelsEnabled": true, "allowedChannelPlugins": [{"plugin": "jui-viz", "marketplace":
    "jsonui"}]} (allowedChannelPlugins replaces the default list), then ``claude --channels plugin:jui-viz@jsonui``
    started with no warning and a prompt from the page started a turn. Whether that file is there is not checked
    here (the CLI may read it from elsewhere, or from a server), so a --channels launch counts as reaching it.
Each entry is one argument, tagged ``plugin:<name>@<marketplace>`` or ``server:<name>`` (``server:`` only with the
development flag). A plugin's channel matches ``plugin:jui-viz@jsonui``; a server registered with ``claude mcp add``
(``jui viz relay install``) matches ``server:jui-viz``. Anything else is dropped silently by the CLI: its MCP log says
"not in --channels list for this session". An organisation account also needs ``channelsEnabled`` in managed
settings — not visible from here either.

Measured on this machine (10-19, read only): a terminal session's process has the argv the user typed (``claude``
and its flags); the VS Code extension runs ``…/native-binary/claude --output-format stream-json …`` and the desktop
app ``…/claude.app/Contents/MacOS/claude --output-format stream-json …``; neither can add the flag. The session file
(~/.claude/sessions/<pid>.json) names the same with ``entrypoint``: ``cli``, ``claude-vscode``, ``claude-desktop``.

The argv is read exactly: sysctl KERN_PROCARGS2 on macOS, /proc/<pid>/cmdline on Linux; ``ps -o args=`` split on
spaces only when neither is there. Nothing but the classification leaves this module (an argv can hold a prompt).
"""
from __future__ import annotations

import os
import subprocess
import sys

DEV_FLAG = "--dangerously-load-development-channels"
CHANNELS_FLAG = "--channels"
PLUGIN = "jui-viz"
MARKETPLACE = "jsonui"
SERVER = "jui-viz"
START_DEV = f"claude {DEV_FLAG} plugin:{PLUGIN}@{MARKETPLACE}"
START_DEV_SERVER = f"claude {DEV_FLAG} server:{SERVER}"
START_CHANNELS = f"claude {CHANNELS_FLAG} plugin:{PLUGIN}@{MARKETPLACE}"
MANAGED_SETTINGS = '{"channelsEnabled": true, "allowedChannelPlugins": [{"plugin": "jui-viz", "marketplace": "jsonui"}]}'
#: How to start a session that a prompt reaches, in the words doctor and the page use.
HOW_TO_START = (f"ターミナルで {START_DEV}（起動のたびに確認が出る。jui viz relay install で入れたなら server:{SERVER}）、"
                f"または managed settings（macOS: /Library/Application Support/ClaudeCode/managed-settings.json）に "
                f"{MANAGED_SETTINGS} を載せて {START_CHANNELS}（警告なし）。組織のアカウントは channelsEnabled が要る。"
                "VS Code 拡張とデスクトップアプリでは使えない")
IDE_ENTRYPOINTS = {"claude-vscode": "vscode", "claude-desktop": "desktop"}

#: Why a session can or cannot take a prompt. ok: the CLI hands the channel's text to it. maybe: named with
#: --channels, which works only if an organisation put jui-viz on its allowlist.
REASONS = {
    "dev": (True, "ターミナルで開発用 channel の指定つきで起動（届く）"),
    "channels": (True, "--channels で指定（managed settings の allowedChannelPlugins に jui-viz が載っていれば届く）"),
    "no-flag": (False, "起動に channel の指定が無い"),
    "other": (False, "起動の channel の指定に jui-viz が無い"),
    "form": (False, "起動の指定の形が、この channel のつながり方と合わない"),
    "server-channels": (False, "server: の指定は --channels では効かない（--dangerously-load-development-channels が要る）"),
    "vscode": (False, "VS Code 拡張のセッションは起動の指定を足せないので届かない"),
    "desktop": (False, "デスクトップアプリのセッションは起動の指定を足せないので届かない"),
    "unreadable": (False, "セッションのプロセスの起動の引数を読めない（届くか確かめられない）"),
}


def _argv_darwin(pid: int) -> list[str] | None:
    import ctypes
    import ctypes.util

    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    mib = (ctypes.c_int * 3)(1, 49, int(pid))   # CTL_KERN, KERN_PROCARGS2
    size = ctypes.c_size_t(0)
    if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or size.value < 4:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
        return None
    raw = buf.raw[: size.value]
    argc = int.from_bytes(raw[:4], sys.byteorder)
    rest = raw[4:]
    end = rest.find(b"\0")                      # the executable's path
    if end < 0:
        return None
    i = end
    while i < len(rest) and rest[i] == 0:       # padding
        i += 1
    parts = rest[i:].split(b"\0")
    if argc < 1 or len(parts) < argc:
        return None
    return [p.decode("utf-8", "replace") for p in parts[:argc]]


def read_argv(pid) -> list[str] | None:
    """The process's argv exactly, or None when it cannot be read (gone, another user's, no way to read it)."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid < 2:
        return None
    try:
        if sys.platform == "darwin":
            return _argv_darwin(pid)
        if os.path.exists(f"/proc/{pid}/cmdline"):
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                data = f.read()
            return [p.decode("utf-8", "replace") for p in data.split(b"\0") if p] or None
        out = subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True, timeout=3)
        return out.stdout.split() if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def channel_entries(argv: list[str]) -> dict[str, list[str]]:
    """{"dev": [...], "channels": [...]}: the values of the two flags, as the CLI's option parser takes them (a
    variadic option: every following argument up to the next option; or one value after "=")."""
    out: dict[str, list[str]] = {"dev": [], "channels": []}
    key = None
    for arg in argv[1:]:
        if arg == "--":
            key = None
            continue
        if arg.startswith("-"):
            key = None
            for flag, name in ((DEV_FLAG, "dev"), (CHANNELS_FLAG, "channels")):
                if arg == flag:
                    key = name
                elif arg.startswith(flag + "="):
                    out[name].append(arg[len(flag) + 1:])
            continue
        if key is not None:
            out[key].append(arg)
    return out


def _names(entry: str, via: str | None) -> bool:
    """Does this entry name the jui-viz channel as it is connected (via: "plugin", "mcp", or None = not known)?"""
    if entry.startswith("plugin:"):
        name, _, market = entry[7:].partition("@")
        return name == PLUGIN and market == MARKETPLACE and via in (None, "plugin")
    if entry.startswith("server:"):
        return entry[7:] == SERVER and via in (None, "mcp")
    return False


def _mentions(entry: str) -> bool:
    return entry.startswith(f"plugin:{PLUGIN}@") or entry == f"server:{SERVER}"


def classify(argv: list[str] | None, entrypoint: str | None = None, via: str | None = None) -> str:
    """A key of REASONS for one session: its process argv, its session file's entrypoint, and how its jui-viz
    channel is connected (channel.py says in its hello)."""
    if entrypoint in IDE_ENTRYPOINTS:
        return IDE_ENTRYPOINTS[entrypoint]
    if argv is None:
        return "unreadable"
    if "stream-json" in argv and "--output-format" in argv:
        return "vscode" if any("vscode" in a for a in argv[:1]) else "desktop"
    entries = channel_entries(argv)
    if any(_names(e, via) for e in entries["dev"]):
        return "dev"
    if any(_names(e, via) for e in entries["channels"] if e.startswith("plugin:")):
        return "channels"
    if any(e.startswith("server:") and _names(e, via) for e in entries["channels"]):
        return "server-channels"
    if any(_mentions(e) for e in entries["dev"] + entries["channels"]):
        return "form"
    if entries["dev"] or entries["channels"]:
        return "other"
    return "no-flag"
