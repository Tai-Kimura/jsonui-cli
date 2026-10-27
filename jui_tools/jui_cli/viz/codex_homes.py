"""A Codex home of its own for each local model server (requester 10-27: 「モデル自由に選べるようにしたい」).

Why not ``codex --oss``: a terminal codex started with a local provider (``--oss``, ``-c model_provider=…`` or a
profile) does not attach to the app-server daemon — its launch configuration cannot be replayed on a shared server —
so viz never sees it (measured 10-27, Codex 0.164.0). A codex whose home names the provider as its default does
attach, and ``-m <model>`` alone keeps it attached: so each provider gets ``~/.codex-local/<provider>/`` with a
config.toml naming it, its own daemon (``CODEX_HOME=… codex app-server daemon start``), and the model is chosen on
each start. viz reads every such home's daemon beside ~/.codex's (sources/codex_app_server.py).

``ensure`` writes the home only when it has no config.toml: the provider, and the person's own ``[features]`` and
``[mcp_servers.*]`` copied from ~/.codex/config.toml (so jui-tools and the multi-agent switch work there too). A home
that exists is never rewritten. Nothing else of ~/.codex is copied: its sessions, sign-in and project trust stay there
(the first start in a project asks to trust it again).
"""
from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

from . import local_models

ROOT_NAME = ".codex-local"
MARK = "# made by jui viz codex-local ensure (the Codex home of a local model server; edit it freely)"
COPIED = ("features", "mcp_servers")
_BARE = re.compile(r"[A-Za-z0-9_-]+")


def root() -> Path:
    return Path.home() / ROOT_NAME


def home_of(provider: str) -> Path:
    if provider not in local_models.PROVIDER_IDS:
        raise ValueError(f"unknown provider: {provider}")
    return root() / provider


def homes() -> list[tuple[str, Path]]:
    """The providers whose home exists (a config.toml in it), in local_models.PROVIDERS' order."""
    out = []
    for pid, _, _ in local_models.PROVIDERS:
        home = root() / pid
        if (home / "config.toml").is_file():
            out.append((pid, home))
    return out


def _key(k: str) -> str:
    return k if _BARE.fullmatch(k) else json.dumps(k, ensure_ascii=False)


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)   # a TOML basic string: JSON's escapes are TOML's
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_value(x)}" for k, x in v.items()) + " }"
    raise ValueError(f"cannot write {type(v).__name__} as TOML")


def _table(path: list[str], data: dict, out: list[str]) -> None:
    plain = {k: v for k, v in data.items() if not isinstance(v, dict)}
    nested = {k: v for k, v in data.items() if isinstance(v, dict)}
    out.append("")
    out.append("[" + ".".join(_key(p) for p in path) + "]")
    out.extend(f"{_key(k)} = {_value(v)}" for k, v in plain.items())
    for k, v in nested.items():
        _table(path + [k], v, out)


def render(provider: str, main_config: dict) -> str:
    """config.toml for the provider's home: the provider, then the copied tables of the person's own config."""
    out = [MARK, f"model_provider = {_value(provider)}"]
    for name in COPIED:
        table = main_config.get(name)
        if isinstance(table, dict) and table:
            if name == "mcp_servers":
                for server, spec in table.items():
                    if isinstance(spec, dict):
                        _table([name, server], spec, out)
            else:
                _table([name], table, out)
    return "\n".join(out) + "\n"


def read_main_config(path: Path | None = None) -> dict:
    path = path or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def ensure(provider: str, main_config: dict | None = None) -> tuple[Path, bool]:
    """The provider's home, made when it has no config.toml. Returns (home, made now)."""
    home = home_of(provider)
    config = home / "config.toml"
    if config.exists():
        return home, False
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    text = render(provider, read_main_config() if main_config is None else main_config)
    fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    return home, True
