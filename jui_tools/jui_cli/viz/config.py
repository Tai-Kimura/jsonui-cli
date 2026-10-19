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


#: the page's choices for askWaitSec: 20 s, 1, 3, 10, 30 min, and 0 = until answered
ASK_WAIT_CHOICES = (20, 60, 180, 600, 1800, 0)


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
