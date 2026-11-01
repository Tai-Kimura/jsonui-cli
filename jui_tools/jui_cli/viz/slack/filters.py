"""The filter adapters (design §1, §4, §7 追記): what reaches the router has no attached file and no secret.

The builtin adapter runs here, on the machine, and sends nothing anywhere: it drops the message's files (and the
legacy attachments, which carry unfurled text of their own) and masks every match of PATTERNS and of the config's
filter.extraPatterns as ``[REDACTED:<kind>]``.

Another adapter is a Python file (filter.adapter = its path) defining::

    def filter_message(record: dict) -> tuple[dict, dict]:
        # record: one inbox file {workspace, channel, ts, permalink, message: <the Slack message as fetched>, via}
        # returns ({"text": str, "user": str, "permalink": str}, {"removedFiles": int, "redactions": int})

It runs in a child ``python -I`` (adapters.run_file), so a crash, a hang or an exit stays there. Whatever goes wrong
— an exception, a timeout, a wrong shape — raises FilterError, and the intake keeps the message in inbox/ and routes
nothing (nothing unfiltered leaves the machine).
"""
from __future__ import annotations

import re

from . import adapters

REDACTED = "[REDACTED:{kind}]"

# (kind, pattern). Order matters: the specific shapes before the general ones (sk-ant- before sk-).
PATTERNS: list[tuple[str, str]] = [
    ("private-key", r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----(?:[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|[\s\S]*\Z)"),
    ("slack-token", r"\bxox[abposre]-[A-Za-z0-9-]{10,}"),
    ("slack-app-token", r"\bxapp-\d-[A-Za-z0-9-]{10,}"),
    ("slack-webhook", r"https://hooks\.slack\.com/(?:services|workflows|triggers)/[A-Za-z0-9/_-]+"),
    ("aws-access-key", r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b"),
    ("aws-secret-key", r"(?i)(?<=aws)[\w .-]{0,20}?(?:secret|private)[\w .-]{0,20}?[\s:=\"'：]{1,4}[A-Za-z0-9/+]{40}\b"),
    ("github-token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
    ("anthropic-key", r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    ("openai-key", r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    ("google-api-key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ("password", r"(?i)(?<![A-Za-z])(?:password|passwd|pass|pwd|passcode|secret|api[_ -]?key|access[_ -]?token|token|パスワード|暗証番号|パスコード)"
                 r"\s*(?:は|:|：|=|＝)\s*(?!\[REDACTED:)[!-~]{4,}"),   # an ASCII value of 4 or more: "パスワードは忘れずに" is no secret
    ("email", r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("phone", r"(?<![\d.])(?:\+\d{1,3}[- ]?\(?\d{1,4}\)?[- ]?\d{1,4}[- ]?\d{3,4}|0\d{1,4}-\d{1,4}-\d{3,4}|0[5789]0\d{8}|\(0\d{1,4}\)\s?\d{1,4}-\d{3,4})(?![\d.])"),
]


class FilterError(Exception):
    """The adapter failed; the message stays in inbox/."""


def compile_patterns(extra: list) -> list[tuple[str, re.Pattern]]:
    out = [(kind, re.compile(p)) for kind, p in PATTERNS]
    for i, item in enumerate(extra or []):
        if isinstance(item, str):
            kind, pattern = f"extra-{i + 1}", item
        elif isinstance(item, dict) and isinstance(item.get("pattern"), str):
            kind, pattern = str(item.get("name") or f"extra-{i + 1}"), item["pattern"]
        else:
            raise FilterError(f"filter.extraPatterns[{i}]: a string or {{name, pattern}}")
        try:
            out.append((kind, re.compile(pattern)))
        except re.error as exc:
            raise FilterError(f"filter.extraPatterns[{i}]: {exc}") from None
    return out


def redact(text: str, compiled: list[tuple[str, re.Pattern]]) -> tuple[str, int]:
    count = 0
    for kind, pattern in compiled:
        def sub(m: re.Match, _kind=kind) -> str:
            nonlocal count
            count += 1
            return REDACTED.format(kind=_kind)
        text = pattern.sub(sub, text)
    return text, count


def builtin(record: dict, extra: list | None = None) -> tuple[dict, dict]:
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    files = message.get("files") if isinstance(message.get("files"), list) else []
    compiled = compile_patterns(extra or [])
    text, n = redact(str(message.get("text") or ""), compiled)
    return ({"text": text, "user": str(message.get("user") or message.get("username") or message.get("bot_id") or ""),
             "permalink": str(record.get("permalink") or "")},
            {"removedFiles": len(files), "redactions": n})


def apply(record: dict, filter_cfg: dict, timeout: float = adapters.TIMEOUT_SEC) -> dict:
    """The filtered message in the shape of a projects/ file (router added later). Raises FilterError."""
    adapter = (filter_cfg or {}).get("adapter") or "builtin"
    if adapter == "builtin":
        try:
            msg, stats = builtin(record, filter_cfg.get("extraPatterns"))
        except FilterError:
            raise
        except Exception as exc:  # noqa: BLE001 — any failure keeps the message home
            raise FilterError(f"builtin: {type(exc).__name__}: {exc}") from None
    else:
        try:
            got = adapters.run_file(adapter, "filter_message", [record], timeout)
        except adapters.AdapterError as exc:
            raise FilterError(str(exc)) from None
        if not (isinstance(got, list) and len(got) == 2 and isinstance(got[0], dict) and isinstance(got[1], dict)):
            raise FilterError(f"{adapter}: filter_message must return (message dict, stats dict)")
        msg, stats = got
    if not isinstance(msg.get("text"), str):
        raise FilterError(f"{adapter}: the message has no text string")
    for key in ("removedFiles", "redactions"):
        value = stats.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise FilterError(f"{adapter}: {key} must be an int >= 0")
    return {
        "workspace": record.get("workspace"), "channel": record.get("channel"),
        "user": str(msg.get("user") or ""), "ts": record.get("ts"),
        "text": msg["text"], "permalink": str(msg.get("permalink") or ""),
        "removedFiles": stats["removedFiles"], "redactions": stats["redactions"],
    }
