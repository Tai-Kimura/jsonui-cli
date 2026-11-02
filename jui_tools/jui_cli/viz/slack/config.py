"""<viz_home>/slack.json: the intake's config (design §7). Mode 0600, since it holds the keys.

A file readable by group or others is refused (the way ssh refuses a private key): the intake does not start and
the status says why; nothing is read from it. ``save`` always writes 0600 through a temporary file.
"""
from __future__ import annotations

import copy
import json
import os
import re
import stat
import tempfile
from pathlib import Path

from .. import paths

FILE_NAME = "slack.json"
#: api: the Web API on the schedule. connector: claude -p with the Slack connector. socket: Socket Mode pushes each
#: message as it is written (workspaces[].appToken), and the schedule still reads the Web API (workspaces[].token).
MODES = ("api", "connector", "socket")
#: The connector's warning as written into a new slack.json (the page shows srv.slack.modeNote, in its language).
MODE_NOTE = "With mode connector, the messages pass through Claude (Anthropic) before the filter"


def mode_note() -> str:
    from .. import i18n
    return i18n.tl("srv.slack.modeNote")

#: The connector's model (``claude -p --model``): only fetching, so the light one, the same as routers.HAIKU_MODEL.
#: "" leaves --model off (claude's own default).
CONNECTOR_MODEL = "claude-haiku-5-5"

DEFAULT: dict = {
    "orchestrationDir": "~/slack-orchestration",
    "schedule": {"everyHours": 24, "at": "09:00"},
    "source": {
        "mode": "api",
        "_modeNote": MODE_NOTE,
        "workspaces": [],
        "threadWatchDays": 14,
        "connectorModel": CONNECTOR_MODEL,
    },
    "filter": {"adapter": "builtin", "extraPatterns": []},
    "router": {
        "adapter": "haiku",
        "anthropicApiKey": "", "typesafeApiKey": "",
        "confidenceMin": 0.6,
        "prompt": {
            "instructions": "Decide which project this Slack message is about.",
            "projects": {},
            "chitchat": "Small talk, greetings, thanks and anything that asks for no work.",
        },
    },
    "taskPrompt": "",
}


class ConfigError(Exception):
    """The config cannot be used; the message is shown on the status."""


def path() -> Path:
    return paths.viz_home() / FILE_NAME


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load(file: Path | None = None) -> dict | None:
    """The config merged over DEFAULT, or None when there is no file. Raises ConfigError when it cannot be used."""
    file = file or path()
    try:
        st = file.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ConfigError(f"{file} is not a regular file")
    if st.st_mode & 0o077:
        raise ConfigError(f"{file} is readable by others (mode {stat.S_IMODE(st.st_mode):04o}); chmod 600 it")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{file}: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{file}: not a JSON object")
    cfg = _merge(DEFAULT, data)
    validate(cfg)
    return cfg


def validate(cfg: dict) -> None:
    src = cfg.get("source") or {}
    if src.get("mode") not in MODES:
        raise ConfigError("source.mode must be api, connector or socket")
    if not isinstance(src.get("workspaces"), list):
        raise ConfigError("source.workspaces must be a list")
    for ws in src["workspaces"]:
        if not isinstance(ws, dict) or not isinstance(ws.get("name"), str) or not ws["name"]:
            raise ConfigError("each workspace needs a name")
        if not safe_name(ws["name"]):
            raise ConfigError(f"workspace name {ws['name']!r}: letters, digits, '.', '_' and '-' only")
        for key in ("token", "appToken"):
            if key in ws and not isinstance(ws[key], str):
                raise ConfigError(f"workspace {ws['name']}: {key} must be a string")
        for ch in ws.get("channels") or []:
            if not isinstance(ch, str) or not safe_name(ch):
                raise ConfigError(f"channel {ch!r}: letters, digits, '.', '_' and '-' only")
    days = src.get("threadWatchDays")
    if not isinstance(days, (int, float)) or isinstance(days, bool) or days < 0:
        raise ConfigError("source.threadWatchDays must be a number >= 0")
    model = src.get("connectorModel")
    if not isinstance(model, str) or (model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@\[\]/-]*", model)):
        raise ConfigError("source.connectorModel must be a model name, or \"\" for claude's own default")
    sched = cfg.get("schedule") or {}
    every = sched.get("everyHours")
    if not isinstance(every, (int, float)) or isinstance(every, bool) or every < 0:
        raise ConfigError("schedule.everyHours must be a number >= 0 (0 = manual only)")
    if parse_at(sched.get("at")) is None:
        raise ConfigError("schedule.at must be HH:MM")
    router = cfg.get("router") or {}
    conf = router.get("confidenceMin")
    if not isinstance(conf, (int, float)) or isinstance(conf, bool) or not 0 <= conf <= 1:
        raise ConfigError("router.confidenceMin must be between 0 and 1")
    projects = ((router.get("prompt") or {}).get("projects"))
    if not isinstance(projects, dict):
        raise ConfigError("router.prompt.projects must be an object")
    for pid in projects:
        if not safe_name(pid) or pid in ("chitchat", "_unsorted", "inbox", "tasks"):
            raise ConfigError(f"project id {pid!r}: letters, digits, '.', '_' and '-', not a reserved name")
    if not isinstance((cfg.get("filter") or {}).get("extraPatterns"), list):
        raise ConfigError("filter.extraPatterns must be a list")


def safe_name(name: str) -> bool:
    return bool(name) and name not in (".", "..") and not name.startswith(".") and \
        all(c.isascii() and (c.isalnum() or c in "._-") for c in name)


def parse_at(value) -> tuple[int, int] | None:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return None
    try:
        h, m = int(value[:2]), int(value[3:])
    except ValueError:
        return None
    return (h, m) if 0 <= h < 24 and 0 <= m < 60 else None


def orchestration_dir(cfg: dict) -> Path:
    return Path(os.path.expanduser(str(cfg.get("orchestrationDir") or DEFAULT["orchestrationDir"])))


def save(cfg: dict, file: Path | None = None) -> Path:
    """Write cfg as 0600 (temporary file, then rename). The folder is made 0700 when it is new."""
    validate(_merge(DEFAULT, cfg))
    file = file or path()
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".slack-", suffix=".json", dir=str(file.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, file)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return file


def public_view(cfg: dict) -> dict:
    """The config with every key blanked to whether it is set: what the page and the status may show."""
    out = copy.deepcopy(cfg)
    for ws in (out.get("source") or {}).get("workspaces") or []:
        for key in ("token", "appToken"):
            if isinstance(ws, dict) and key in ws:
                ws[key] = bool(ws[key])
    router = out.get("router") or {}
    for key in ("anthropicApiKey", "typesafeApiKey"):
        if key in router:
            router[key] = bool(router[key])
    return out
