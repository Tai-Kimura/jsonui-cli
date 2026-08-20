"""Reader for the `checks` / `databases` sections of jui.config.json.

Deliberately self-contained: does NOT import jui_tools (the sys.path bridge
has a known failure mode — see docs/bugs history). Only json + pathlib.

Security contract (doc-contract-check plan 01 §6):
- Only commands declared in config are ever executed.
- Command scripts must live inside the project root (no absolute paths,
  no `..`, symlink escapes rejected via resolve()).
- Credentials must not appear in config — connection info comes from
  environment variables at check time.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = "jui.config.json"

KNOWN_CHECK_TYPES = {"builtin:db-schema", "builtin:openapi-diff", "checker"}

# Interpreters allowed as the first token of a declared command. The script
# they run must still be a project-internal path (or a `-m` module resolved
# from the project root cwd).
_ALLOWED_INTERPRETERS = {"python", "python3", "ruby", "node", "sh", "bash"}

_MODULE_RE = re.compile(r"[A-Za-z_]\w*(\.\w+)*$")
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]*$")

# Keys that smell like credentials/connection info — hard error, never warn.
_FORBIDDEN_DECL_KEYS = {
    "url", "dsn", "password", "user", "username",
    "connection", "connection_string", "connection_url", "host", "port",
}


class ProjectConfigError(Exception):
    """Invalid checks/databases declaration."""


@dataclass
class CheckDecl:
    name: str
    type: str
    timeout_seconds: int = 60
    # builtin:db-schema
    database: str = "default"
    dump_command: list[str] | None = None
    ignore_tables: list[str] = field(default_factory=list)
    # builtin:openapi-diff
    impl_openapi_command: list[str] | None = None
    ignore_paths: list[str] = field(default_factory=list)
    ignore_response_codes: list[str] = field(default_factory=list)
    # Per-comparison-key severity. A key names one schema comparison
    # (`format`, `nullable`, `enum`, `required`, `type`), NOT a field path.
    # ignore_schema_keys drops the comparison; downgrade_to_warning keeps the
    # finding with its expected/actual detail but stops it gating CI. Both
    # exist because a doc that is deliberately STRICTER than the impl
    # (`format: uuid` over FastAPI's bare `str`) is not drift the project
    # intends to fix — and silencing it by loosening the doc, or by tightening
    # the impl (which changes what the API accepts), corrupts the thing being
    # checked instead of the tool doing the checking.
    ignore_schema_keys: list[str] = field(default_factory=list)
    downgrade_to_warning: list[str] = field(default_factory=list)
    scope: str = "all"           # "all" | "generated" (honor api.schemas paths)
    api_path_filters: tuple = ()  # (include_globs, exclude_globs) when scope=generated
    # checker (full-checker plugin)
    command: list[str] | None = None
    # Raw declaration for display (`check --list`)
    raw: dict = field(default_factory=dict)


@dataclass
class DbDecl:
    name: str
    dialect: str
    version: str | None = None


def find_jui_config(start_dir: Path) -> Path | None:
    """Walk upward from start_dir looking for jui.config.json."""
    current = start_dir.resolve()
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_config_dict(config_path: Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ProjectConfigError(f"{config_path}: top level must be an object")
    return data


def _validate_project_path(raw: str, project_root: Path, context: str) -> None:
    if raw.startswith("-"):
        raise ProjectConfigError(f"{context}: '{raw}' looks like a flag, not a path")
    p = Path(raw)
    if p.is_absolute():
        raise ProjectConfigError(f"{context}: absolute paths are not allowed ('{raw}')")
    if ".." in p.parts:
        raise ProjectConfigError(f"{context}: '..' is not allowed ('{raw}')")
    resolved = (project_root / p).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        raise ProjectConfigError(
            f"{context}: '{raw}' resolves outside the project root (symlink escape?)"
        )


def parse_command(raw: str, project_root: Path, context: str) -> list[str]:
    """Validate a declared command string and return its argv list.

    Accepted forms:
    - `<project-relative-script> [args...]`
    - `<interpreter> <project-relative-script> [args...]`
    - `<interpreter> -m <dotted.module> [args...]`  (module resolved from
      the project-root cwd — still project code)

    The returned list is passed to subprocess with shell=False, so shell
    metacharacters in args are inert.
    """
    if not isinstance(raw, str):
        # Naming the type given: an argv list is the intuitive guess here, and
        # the old message ("must be a non-empty string") read as if the value
        # were empty rather than the wrong shape.
        raise ProjectConfigError(
            f"{context}: command must be a string, got {type(raw).__name__}"
            + (" — pass one command line, not an argv list"
               if isinstance(raw, (list, tuple)) else "")
        )
    if not raw.strip():
        raise ProjectConfigError(f"{context}: command must be a non-empty string")
    tokens = shlex.split(raw)
    head = tokens[0]
    if head in _ALLOWED_INTERPRETERS:
        if len(tokens) >= 3 and tokens[1] == "-m":
            if not _MODULE_RE.match(tokens[2]):
                raise ProjectConfigError(
                    f"{context}: invalid module name '{tokens[2]}' after -m"
                )
            return tokens
        if len(tokens) >= 2:
            _validate_project_path(tokens[1], project_root, context)
            return tokens
        raise ProjectConfigError(
            f"{context}: interpreter '{head}' needs a project script or -m module"
        )
    _validate_project_path(head, project_root, context)
    return tokens


def _str_list(value, context: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise ProjectConfigError(f"{context}: must be a list of strings")
    return value


# The schema comparisons openapi-diff performs. Closed set on purpose: a
# typo'd key would otherwise silently widen nothing and the project would
# believe it had suppressed noise it is still gating on.
SCHEMA_COMPARISON_KEYS = ("type", "nullable", "enum", "required", "format")


def _schema_keys(value, context: str) -> list[str]:
    keys = _str_list(value, context)
    unknown = [k for k in keys if k not in SCHEMA_COMPARISON_KEYS]
    if unknown:
        raise ProjectConfigError(
            f"{context}: unknown comparison key(s) {unknown} "
            f"(available: {', '.join(SCHEMA_COMPARISON_KEYS)}). "
            "These name schema comparisons, not field paths — use "
            "ignore_paths for endpoints."
        )
    return keys


def load_checks(config: dict, project_root: Path) -> list[CheckDecl]:
    raw_checks = config.get("checks", [])
    if not isinstance(raw_checks, list):
        raise ProjectConfigError("'checks' must be an array")
    decls: list[CheckDecl] = []
    seen_names: set[str] = set()
    for i, raw in enumerate(raw_checks):
        ctx = f"checks[{i}]"
        if not isinstance(raw, dict):
            raise ProjectConfigError(f"{ctx}: must be an object")
        forbidden = _FORBIDDEN_DECL_KEYS.intersection(raw.keys())
        if forbidden:
            raise ProjectConfigError(
                f"{ctx}: credentials/connection info must not be in config "
                f"(found: {sorted(forbidden)}). Use environment variables."
            )
        name = raw.get("name")
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise ProjectConfigError(f"{ctx}: 'name' must match {_NAME_RE.pattern}")
        if name in seen_names:
            raise ProjectConfigError(f"{ctx}: duplicate check name '{name}'")
        seen_names.add(name)
        ctype = raw.get("type")
        if ctype not in KNOWN_CHECK_TYPES:
            raise ProjectConfigError(
                f"{ctx} ('{name}'): unknown type '{ctype}' "
                f"(known: {sorted(KNOWN_CHECK_TYPES)})"
            )
        timeout = raw.get("timeout_seconds", 60)
        if not isinstance(timeout, int) or not (1 <= timeout <= 3600):
            raise ProjectConfigError(
                f"{ctx} ('{name}'): timeout_seconds must be an int in [1, 3600]"
            )
        decl = CheckDecl(name=name, type=ctype, timeout_seconds=timeout, raw=dict(raw))

        if ctype == "builtin:db-schema":
            database = raw.get("database", "default")
            if not isinstance(database, str) or not database:
                raise ProjectConfigError(f"{ctx} ('{name}'): 'database' must be a string")
            decl.database = database
            if "dump_command" in raw:
                decl.dump_command = parse_command(
                    raw["dump_command"], project_root, f"{ctx}.dump_command"
                )
            decl.ignore_tables = _str_list(
                raw.get("ignore_tables"), f"{ctx}.ignore_tables"
            )
        elif ctype == "builtin:openapi-diff":
            if "impl_openapi_command" not in raw:
                raise ProjectConfigError(
                    f"{ctx} ('{name}'): 'impl_openapi_command' is required"
                )
            decl.impl_openapi_command = parse_command(
                raw["impl_openapi_command"], project_root, f"{ctx}.impl_openapi_command"
            )
            decl.ignore_paths = _str_list(raw.get("ignore_paths"), f"{ctx}.ignore_paths")
            decl.ignore_response_codes = [
                str(c) for c in raw.get("ignore_response_codes", [])
            ]
            decl.ignore_schema_keys = _schema_keys(
                raw.get("ignore_schema_keys"), f"{ctx}.ignore_schema_keys"
            )
            decl.downgrade_to_warning = _schema_keys(
                raw.get("downgrade_to_warning"), f"{ctx}.downgrade_to_warning"
            )
            both = set(decl.ignore_schema_keys) & set(decl.downgrade_to_warning)
            if both:
                raise ProjectConfigError(
                    f"{ctx} ('{name}'): {sorted(both)} listed in BOTH "
                    "ignore_schema_keys and downgrade_to_warning — a dropped "
                    "comparison cannot also be reported"
                )
            scope = raw.get("scope", "all")
            if scope not in ("all", "generated"):
                raise ProjectConfigError(
                    f"{ctx} ('{name}'): scope must be 'all' or 'generated'"
                )
            decl.scope = scope
            if scope == "generated":
                # honor the DTO-generation path filters (jui.config.json
                # api.schemas.include_paths / exclude_paths) — front teams
                # only want the drift that affects their generated models
                api_cfg = config.get("api", {})
                schemas_cfg = api_cfg.get("schemas", {}) if isinstance(api_cfg, dict) else {}
                inc = schemas_cfg.get("include_paths", [])
                exc = schemas_cfg.get("exclude_paths", [])
                inc = [inc] if isinstance(inc, str) else list(inc or [])
                exc = [exc] if isinstance(exc, str) else list(exc or [])
                decl.api_path_filters = (inc, exc)
        elif ctype == "checker":
            if "command" not in raw:
                raise ProjectConfigError(f"{ctx} ('{name}'): 'command' is required")
            decl.command = parse_command(raw["command"], project_root, f"{ctx}.command")

        decls.append(decl)
    return decls


def load_databases(config: dict) -> dict[str, DbDecl]:
    """Parse `databases: {name: {dialect, version}}` with the legacy
    single-DB `db: {dialect}` fallback (plan 04 §2)."""
    result: dict[str, DbDecl] = {}
    raw_dbs = config.get("databases")
    if raw_dbs is not None:
        if not isinstance(raw_dbs, dict):
            raise ProjectConfigError("'databases' must be an object")
        for name, decl in raw_dbs.items():
            if not isinstance(decl, dict) or not isinstance(decl.get("dialect"), str):
                raise ProjectConfigError(
                    f"databases.{name}: must be an object with a 'dialect' string"
                )
            result[name] = DbDecl(
                name=name,
                dialect=decl["dialect"],
                version=decl.get("version"),
            )
        return result
    legacy = config.get("db")
    if isinstance(legacy, dict) and isinstance(legacy.get("dialect"), str):
        result["default"] = DbDecl(
            name="default", dialect=legacy["dialect"], version=legacy.get("version")
        )
    return result
