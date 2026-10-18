"""Settings for ``jui viz``: defaults, then ``<paths.viz_home()>/config.json``,
then command-line options (applied by the caller)."""
from __future__ import annotations

import json
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
