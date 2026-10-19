"""The call button (2.3.5, requester 10-19: "ロボット呼び出しボタンを部屋に置いて、そのボタン押したらそのプロジェクトで新規
セッション呼び出すためのスクリプトコピーできるダイアログ出してほしい。…担当名付きでセッション起動するスクリプトを出せる？").

The page shows a command to copy; viz never runs it and starts no process. The command:

    cd <project root> && claude <channels flag> plugin:jui-viz@jsonui --name=<name> <prompt>

* the channels flag: ``--channels`` when the managed settings approve the plugin (channelsEnabled true and jui-viz@jsonui
  in allowedChannelPlugins), else ``--dangerously-load-development-channels`` — session-recovery's channels_flag
  (common.sh), read only. It takes several values, so it comes first and an option follows it at once.
* the name: one argument ``--name=<name>``. A name is one line of text; one that begins with "-" stays the option's value
  (after "=", never a separate word an option parser could take for an option).
* the prompt: session-recovery's fresh-start preface with the name, then the role text when there is one. It always
  begins with the preface, so never with "-".

Quoting (session-recovery's sh_quote, made strict for a command that is pasted into a terminal): a word of only
``A-Za-z0-9_./:@%+=,-`` stays bare; anything else goes in single quotes, a ``'`` as ``'\\''``, and every control
character (C0, DEL, C1) and every character past ASCII as ``$'\\xHH…'`` (its UTF-8 bytes): the line is plain printable
ASCII. A pasted CR or ESC must not reach the terminal raw; and an interactive bash 3.2 in the C locale reads each byte
of UTF-8 text as a Meta key (readline's convert-meta), so a Japanese name pasted as is turned into editing commands and
broke the quoting (measured, 2.3.5 e2e). macOS's bash 3.2 knows ``\\x`` but not ``\\u`` in ``$'…'``. NUL cannot be
in an argument at all: refused.
"""
from __future__ import annotations

import json
import os
import re

PLUGIN = "jui-viz@jsonui"
MANAGED_SETTINGS = "/Library/Application Support/ClaudeCode/managed-settings.json"
NAME_MAX = 64
ROLE_MAX = 4000
PREFACE = "このセッションの担当は次のとおりです（jui viz の呼び出しボタンより）。"
_BARE = re.compile(r"[A-Za-z0-9_./:@%+=,-]+")


def _control(ch: str) -> bool:
    o = ord(ch)
    return o < 0x20 or 0x7F <= o <= 0x9F


def sh_quote(s: str) -> str:
    """s as one shell word for zsh and bash (pasted at a prompt or run with -c). NUL: ValueError."""
    if "\0" in s:
        raise ValueError("NUL")
    if s == "":
        return "''"
    if _BARE.fullmatch(s):
        return s
    out, esc = [], []   # esc: a run of characters written as $'\xHH…' (one segment, not one per character)
    for ch in s:
        if _control(ch) or ord(ch) > 0x7E:
            esc.append(ch)
            continue
        if esc:
            out.append("'$'" + "".join(f"\\x{b:02x}" for b in "".join(esc).encode("utf-8")) + "''")
            esc = []
        out.append("'\\''" if ch == "'" else ch)
    if esc:
        out.append("'$'" + "".join(f"\\x{b:02x}" for b in "".join(esc).encode("utf-8")) + "''")
    return "'" + "".join(out) + "'"


def channels_flag(path: str | None = None) -> str:
    """--channels when the managed settings approve jui-viz@jsonui, else --dangerously-load-development-channels.
    Read only; a missing, unreadable or malformed file is "not approved"."""
    path = path or os.environ.get("JUI_VIZ_MANAGED_SETTINGS") or MANAGED_SETTINGS
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    allowed = data.get("allowedChannelPlugins") if isinstance(data, dict) else None
    ok = isinstance(data, dict) and data.get("channelsEnabled") is True and isinstance(allowed, list) and any(
        a == PLUGIN or (isinstance(a, dict) and a.get("plugin") == "jui-viz" and a.get("marketplace") == "jsonui")
        for a in allowed)
    return "--channels" if ok else "--dangerously-load-development-channels"


def check(name, role) -> str | None:
    """Why the inputs cannot make a command (Japanese, for the dialog), or None."""
    if not isinstance(name, str) or not isinstance(role, str):
        return "担当名と役割の文は文字列で"
    if "\0" in name or "\0" in role:
        return "NUL 文字は使えません"
    if not name.strip():
        return "担当名を入れてください"
    if len(name) > NAME_MAX:
        return f"担当名は {NAME_MAX} 文字まで"
    if any(_control(ch) for ch in name):
        return "担当名は 1 行で（改行・タブなどの制御文字は使えません）"
    if len(role) > ROLE_MAX:
        return f"役割の文は {ROLE_MAX} 文字まで"
    return None


def prompt_of(name: str, role: str) -> str:
    return f"{PREFACE}\nセッション名: {name}" + (f"\n{role}" if role.strip() else "")


def argv_of(name: str, role: str, flag: str) -> list[str]:
    """The CLI's arguments after its name, as the shell hands them over."""
    return [flag, f"plugin:{PLUGIN}", f"--name={name}", prompt_of(name, role)]


def command(root: str, name: str, role: str, flag: str) -> str:
    """The line to paste. root: the project's absolute folder."""
    why = check(name, role)
    if why:
        raise ValueError(why)
    return f"cd {sh_quote(root)} && claude " + " ".join(sh_quote(a) for a in argv_of(name, role, flag))
