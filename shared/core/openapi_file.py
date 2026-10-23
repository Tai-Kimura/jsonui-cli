"""One OpenAPI document read from disk, JSON or YAML — the rule every tool's reader follows (ticket
2026-10-23-jsonui-test-mock-generate-yaml-traceback: `jsonui-test mock generate --swagger api.yaml` ended in a
JSONDecodeError traceback, and five other readers skipped a YAML document without a word).

  * `.json` is read as JSON; `.yaml` / `.yml` as YAML with PyYAML (a safe load); any other name as JSON, then as
    YAML when that fails and PyYAML is there. A YAML document gives what the same document in JSON gives: an
    unquoted date or time (`2024-01-01`, `2024-01-01T10:00:00Z`) stays a string — YAML 1.1's safe load makes it a
    date, which no writer of JSON takes (it ended `mock generate` half way through a file) — and a mapping key is a
    string as JSON writes it (`200:` → "200", `true:` → "true"; an unquoted status code ended `mock generate` in a
    traceback). Every reader of the family takes this (jui build's loader, the canonical index, jsonui-test,
    jsonui-doc, the viz rack), so one document is read one way.
  * A document that cannot be read raises OpenApiFileError with one line that names the file and why — never a
    traceback. Without PyYAML a YAML document says: `<file>: a YAML OpenAPI document needs PyYAML (pip3 install
    pyyaml), or give its JSON form`.
  * `documents(folder)` lists the files a folder of documents holds, the three extensions, in a stable order.

Imports nothing beyond the standard library at load time; PyYAML is imported when a YAML document is read.
"""

from __future__ import annotations

import json
from pathlib import Path

EXTENSIONS = (".json", ".yaml", ".yml")
YAML_EXTENSIONS = (".yaml", ".yml")
NEEDS_PYYAML = "{path}: a YAML OpenAPI document needs PyYAML (pip3 install pyyaml), or give its JSON form"


class OpenApiFileError(Exception):
    """A document that could not be read; str() is the one line to show."""


def is_yaml(path) -> bool:
    return Path(path).suffix.lower() in YAML_EXTENSIONS


def has_pyyaml() -> bool:
    try:
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True


def _first_line(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return text[0] if text else type(exc).__name__


_LOADER: list = []


def _loader(yaml):
    """yaml.SafeLoader without the timestamp resolver: dates and times stay the strings JSON would hold."""
    if not _LOADER:
        class JsonTypesLoader(yaml.SafeLoader):
            pass

        JsonTypesLoader.yaml_implicit_resolvers = {
            first: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
            for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
        }
        _LOADER.append(JsonTypesLoader)
    return _LOADER[0]


def _json_key(key) -> str:
    """A mapping key as JSON writes it."""
    if isinstance(key, str):
        return key
    if key is None or isinstance(key, (bool, int, float)):
        return json.dumps(key)
    return str(key)


def as_json_data(node):
    """A loaded YAML node in JSON's data model: every mapping key a string (JSON writes 200 as "200")."""
    if isinstance(node, dict):
        return {_json_key(k): as_json_data(v) for k, v in node.items()}
    if isinstance(node, list):
        return [as_json_data(v) for v in node]
    return node


def load_yaml(text: str, yaml):
    """The one YAML load of the family: no timestamp resolver, keys as JSON writes them. yaml.YAMLError on bad text."""
    return as_json_data(yaml.load(text, Loader=_loader(yaml)))  # noqa: S506 — a SafeLoader with one resolver less


def _yaml(path: Path, text: str):
    try:
        import yaml
    except ImportError:
        raise OpenApiFileError(NEEDS_PYYAML.format(path=path)) from None
    try:
        return load_yaml(text, yaml)
    except yaml.YAMLError as exc:
        raise OpenApiFileError(f"{path}: not readable as YAML: {_first_line(exc)}") from None


def read(path) -> object:
    """The document's data; OpenApiFileError when it cannot be read."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise OpenApiFileError(f"{p}: no such file") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise OpenApiFileError(f"{p}: cannot be read: {_first_line(exc)}") from None
    return parse(text, p)


def parse(text: str, path) -> object:
    """A document's text already read (path names it: its extension decides JSON or YAML, as read() does)."""
    p = Path(path)
    if is_yaml(p):
        return _yaml(p, text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if p.suffix.lower() != ".json" and has_pyyaml():
            try:
                return _yaml(p, text)
            except OpenApiFileError:
                pass
        raise OpenApiFileError(f"{p}: not readable as JSON: {_first_line(exc)}") from None


def documents(folder) -> list[Path]:
    """The .json / .yaml / .yml files under folder (recursively), sorted; [] when it is not a folder."""
    d = Path(folder)
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS)
