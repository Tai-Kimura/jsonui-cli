"""Settings for ``jui viz``: defaults, then ``<paths.viz_home()>/config.json``,
then command-line options (applied by the caller)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, fields

from . import paths


@dataclass
class VizConfig:
    port: int = 7788
    agentsPollSec: float = 3
    eventsKeep: int = 2000
    pushIntervalMs: int = 200
    toolInputMaxChars: int = 2000
    openBrowser: bool = False
    decideWaitSec: float = 30
    # --ask (AskUserQuestion): while it waits, the terminal shows no question at all (measured 10-18), so it waits
    # askWaitSec for someone to start answering on the page — every input on the card renews it — and never more than
    # askMaxSec in all, or askWaitSec when that is longer. 2.3.6 (requester 10-19: "時間をvizの設定で変えられるように
    # したら？ viz中心でやりたい時に1分は短い", "デフォルト3分にして"): 3 min, and chosen on the page from
    # ASK_WAIT_CHOICES (POST /api/ask-wait, saved here); 0 is "until answered" — still ended by the card's ターミナルで
    # 答える, by every page gone (presence, notifyPresenceSec) and by the session ending.
    askWaitSec: float = 180
    askMaxSec: float = 300
    # how long a page's "question notifications are on" lasts without being said again (POST /api/notify-presence):
    # while it lasts, a hook waits for an answer though no page is visible (the notification brings someone)
    notifyPresenceSec: float = 12
    # while a hook waits on a hidden page, the server asks the pages to say it again this often (a hidden tab's own
    # timers can be held back to once a minute; a message from the server still runs at once)
    askPingSec: float = 4
    # The talk view (talk.py): how long a conversation is kept after one of its two sessions ended (the requester's
    # ruling 10-20: one hour), so a session resumed within it keeps its talks.
    talkGraceSec: float = 3600


#: the page's choices for askWaitSec: 20 s, 1, 3, 10, 30 min, and 0 = until answered
ASK_WAIT_CHOICES = (20, 60, 180, 600, 1800, 0)

#: The timeout of the synchronous AskUserQuestion hook (forward.py --ask), in the installer's hooks
#: (hooks_installer.ASK_TIMEOUT_SEC) and the plugin's hooks.json alike: Claude Code cancels the hook there. Ticket
#: 2026-10-20 question-window-over-5-min: it was 600 s, under the 30 min and "until answered" choices. Claude Code's
#: hooks reference states no maximum for a command hook's timeout (default 600 s); measured on Claude Code 2.1.304
#: (10-20, the ticket's work note): a timeout of 1800 s and of 3600 s ends the hook at exactly that second, so the
#: value is used as written, not capped at 600.
ASK_HOOK_TIMEOUT_SEC = 86400
#: The hook's own margin: forward.py waits the server's limit + 5 s, and the server ends its wait before that.
ASK_HOOK_MARGIN_SEC = 60
#: "until answered" (askWaitSec 0) is bounded by the hook's timeout: the server gives the question back to the
#: terminal before Claude Code cancels the hook (23 h 59 min).
ASK_UNTIL_ANSWERED_SEC = ASK_HOOK_TIMEOUT_SEC - ASK_HOOK_MARGIN_SEC


def ask_hook_wait_sec(config: "VizConfig") -> float:
    """The longest the server waits for one question now — what forward.py --ask must wait (server.json
    askHookWaitSec, and the X-Jui-Viz-Wait-Sec it sends back): askWaitSec, or askMaxSec when longer (holds), and
    "until answered" (0) up to ASK_UNTIL_ANSWERED_SEC; never past the hook's timeout."""
    wait = float(config.askWaitSec)
    longest = ASK_UNTIL_ANSWERED_SEC if wait <= 0 else max(float(config.askMaxSec), wait)
    return float(min(longest, ASK_UNTIL_ANSWERED_SEC))


#: forward.py --ask waits askHookWaitSec + this (its socket timeout), so the hook needs that long before Claude Code
#: cancels it.
ASK_FORWARD_GRACE_SEC = 5


def ask_choices_cut_short(timeout: float, config: "VizConfig") -> list:
    """The page's choices that a --ask hook with this timeout cannot wait out (ticket 2026-10-20
    doctor-misses-old-plugin-ask-timeout): the server's askHookWaitSec for the choice + ASK_FORWARD_GRACE_SEC over
    the timeout. 600 s cuts 10 min (600 + 5), 30 min and "until answered"."""
    from dataclasses import replace

    return [c for c in ASK_WAIT_CHOICES
            if ask_hook_wait_sec(replace(config, askWaitSec=c)) + ASK_FORWARD_GRACE_SEC > float(timeout)]


def ask_choice_text(sec: float) -> str:
    """A choice as the page names it: 20 秒, 10 分, 答えるまで."""
    if sec <= 0:
        return "答えるまで"
    return f"{int(sec)} 秒" if sec < 60 else f"{sec / 60:g} 分"


def ask_server_info(config: "VizConfig") -> dict:
    """server.json's keys for forward.py --ask: askHookWaitSec is what it waits (askMaxSec stays for an older
    forward.py, which waits askMaxSec + 5)."""
    return {"askMaxSec": config.askMaxSec, "askHookWaitSec": ask_hook_wait_sec(config)}


def save_setting(key: str, value) -> None:
    """One key into config.json, the rest kept; written whole and moved into place. A config.json that is there but
    not a JSON object is not overwritten (ValueError): it is the person's file, and load_config already warns."""
    path = paths.config_json()
    data: dict = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config.json が JSON のオブジェクトではありません")
    data[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_config() -> VizConfig:
    """Defaults overlaid with config.json. A broken file warns once and is ignored."""
    config = VizConfig()
    path = paths.config_json()
    if not path.exists():
        return config
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON のオブジェクトではありません")
    except (OSError, ValueError) as exc:
        print(f"jui viz: {path} を読めないため既定値で続けます（{exc}）", file=sys.stderr)
        return config
    known = {f.name: f.type for f in fields(VizConfig)}
    for key, value in data.items():
        if key not in known:
            continue  # unknown keys are ignored, not an error
        default = getattr(config, key)
        # bool is an int subclass: check it first so "port": true is refused.
        if isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, (int, float)):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        else:
            ok = isinstance(value, type(default))
        if not ok:
            print(f"jui viz: config.json の {key} の型が違うため既定値 {default!r} を使います", file=sys.stderr)
            continue
        setattr(config, key, type(default)(value))
    return config
