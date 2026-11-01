"""The router adapters (design §1, §3, §6, §7): one filtered message -> {adapter, choice, confidence}.

The choices are the config's project ids and "chitchat". Each adapter turns router.prompt
({instructions, projects: {id: description}, chitchat}) into its own request:
  haiku  the Anthropic Messages API; the prompt is the system prompt, the answer a forced tool call whose choice is
         an enum of the ids (router.anthropicApiKey, model router.haikuModel or HAIKU_MODEL)
  jev    TypeSafe's System One (POST https://api.typesafe.ai/v1/systemone, model jev-latest): one Choice question,
         instructions = router.prompt.instructions, criteria = the projects' descriptions and chitchat's
  a path a Python file defining ``route(message: dict, prompt: dict) -> {"choice": str, "confidence": float}``,
         run in a child python -I (adapters.run_file)

Only the filtered message is sent (text, user, workspace, channel). Every HTTP call goes through ``post``, which a
test replaces; nothing here calls the network at import.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import adapters

CHITCHAT = "chitchat"
HAIKU_MODEL = "claude-haiku-5-5"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
HTTP_TIMEOUT_SEC = 60.0
CHOICES_MAX = 255   # System One's Choice limit


class RouterError(Exception):
    """The router could not answer; the message stays in inbox/ and is tried again later."""


def post(url: str, headers: dict, body: dict, timeout: float = HTTP_TIMEOUT_SEC) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed https URLs
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RouterError(f"{url}: HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RouterError(f"{url}: {exc}") from None


def choices(prompt: dict) -> dict[str, str]:
    projects = {str(k): str(v) for k, v in ((prompt or {}).get("projects") or {}).items()}
    projects[CHITCHAT] = str((prompt or {}).get("chitchat") or "")
    if len(projects) > CHOICES_MAX:
        raise RouterError(f"{len(projects)} choices; at most {CHOICES_MAX}")
    return projects


def message_text(message: dict) -> str:
    return (f"workspace: {message.get('workspace')}\nchannel: {message.get('channel')}\n"
            f"user: {message.get('user')}\n\n{message.get('text') or ''}")


def haiku(message: dict, router_cfg: dict) -> dict:
    key = router_cfg.get("anthropicApiKey") or ""
    if not key:
        raise RouterError("router.anthropicApiKey is empty")
    prompt = router_cfg.get("prompt") or {}
    options = choices(prompt)
    system = "\n".join([str(prompt.get("instructions") or ""), "", "Choices:"] +
                       [f"- {cid}: {desc}" for cid, desc in options.items()] +
                       ["", "Answer with the route tool: the one choice that fits, and how sure you are (0 to 1)."])
    body = {
        "model": router_cfg.get("haikuModel") or HAIKU_MODEL,
        "max_tokens": 200,
        "system": system,
        "messages": [{"role": "user", "content": message_text(message)}],
        "tools": [{"name": "route", "description": "Where this message goes.",
                   "input_schema": {"type": "object", "required": ["choice", "confidence"], "properties": {
                       "choice": {"type": "string", "enum": list(options)},
                       "confidence": {"type": "number", "minimum": 0, "maximum": 1}}}}],
        "tool_choice": {"type": "tool", "name": "route"},
    }
    got = post(ANTHROPIC_URL, {"x-api-key": key, "anthropic-version": "2023-06-01"}, body)
    for block in got.get("content") or [] if isinstance(got, dict) else []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
            return {"choice": block["input"].get("choice"), "confidence": block["input"].get("confidence")}
    raise RouterError("haiku: no route tool call in the answer")


def jev(message: dict, router_cfg: dict) -> dict:
    key = router_cfg.get("typesafeApiKey") or ""
    if not key:
        raise RouterError("router.typesafeApiKey is empty")
    prompt = router_cfg.get("prompt") or {}
    body = {
        "model": router_cfg.get("jevModel") or JEV_MODEL,
        "state": message_text(message),
        "questions": {"route": {"type": "choice", "instructions": str(prompt.get("instructions") or ""),
                                "criteria": choices(prompt)}},
    }
    got = post(JEV_URL, {"Authorization": f"Bearer {key}"}, body)
    answer = ((got or {}).get("answers") or {}).get("route") if isinstance(got, dict) else None
    if not isinstance(answer, dict):
        raise RouterError("jev: no answer to the route question")
    return {"choice": answer.get("choice"), "confidence": answer.get("confidence")}


def route(message: dict, router_cfg: dict, timeout: float = adapters.TIMEOUT_SEC) -> dict:
    """{adapter, choice, confidence}; choice is a project id, "chitchat", or anything else the adapter said
    (the intake puts an unknown choice in _unsorted/). Raises RouterError."""
    name = router_cfg.get("adapter") or "haiku"
    sent = {k: message.get(k) for k in ("workspace", "channel", "user", "ts", "text")}
    if name == "haiku":
        got = haiku(sent, router_cfg)
    elif name == "jev":
        got = jev(sent, router_cfg)
    else:
        try:
            got = adapters.run_file(name, "route", [sent, router_cfg.get("prompt") or {}], timeout)
        except adapters.AdapterError as exc:
            raise RouterError(str(exc)) from None
    if not isinstance(got, dict) or not isinstance(got.get("choice"), str):
        raise RouterError(f"{name}: no choice in the answer")
    conf = got.get("confidence")
    if not isinstance(conf, (int, float)) or isinstance(conf, bool):
        raise RouterError(f"{name}: no confidence in the answer")
    label = name if name in ("haiku", "jev") else "path"
    return {"adapter": label, "choice": got["choice"], "confidence": max(0.0, min(1.0, float(conf)))}
