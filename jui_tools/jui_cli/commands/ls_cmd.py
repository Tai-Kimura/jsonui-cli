"""`jui ls` — discovery commands for swagger files and generated API models.

Two subcommands:

- ``jui ls api-specs`` — list every swagger / OpenAPI file under ``api_directory``
  with parsed metadata (title, version, schema count, endpoint count, presence
  of v1-halt constructs like ``oneOf`` or multi-file ``$ref``).
- ``jui ls api-models`` — list generated DTO + Domain scaffold files per
  platform, plus any orphan DTOs whose source schema no longer exists.

Both subcommands default to human-readable text output. Pass ``--json`` for a
machine-readable shape — this is what the ``jsonui-mcp-server`` wrappers use.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def register_ls_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``jui ls`` top-level command + its two subcommands."""
    ls_parser = subparsers.add_parser(
        "ls",
        help="List swagger files / generated API models (MCP discovery commands)",
    )
    ls_sub = ls_parser.add_subparsers(dest="ls_target")

    api_specs = ls_sub.add_parser(
        "api-specs",
        help="List swagger / OpenAPI files with parsed metadata",
    )
    api_specs.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON (used by MCP wrappers)",
    )

    api_models = ls_sub.add_parser(
        "api-models",
        help="List generated DTO + Domain scaffold files per platform",
    )
    api_models.add_argument(
        "--platform",
        choices=("ios", "android", "web"),
        help="Restrict to a single platform",
    )
    api_models.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON (used by MCP wrappers)",
    )


def cmd_ls(args: argparse.Namespace) -> int:
    """Dispatch to the right ``ls`` subcommand."""
    target = getattr(args, "ls_target", None)
    if target == "api-specs":
        return _cmd_ls_api_specs(args)
    if target == "api-models":
        return _cmd_ls_api_models(args)
    print("Usage: jui ls <api-specs|api-models> [options]")
    return 1


# --------------------------------------------------------------------------- #
# jui ls api-specs
# --------------------------------------------------------------------------- #


def _cmd_ls_api_specs(args: argparse.Namespace) -> int:
    """Enumerate swagger files + metadata."""
    from ..core.config_manager import ConfigManager
    from ..core.openapi_loader import is_swagger_file

    config_mgr = ConfigManager()
    if not config_mgr.exists():
        return _emit_error(args, "jui.config.json not found. Run 'jui init' first.")

    api_dir = config_mgr.api_directory
    payload: dict[str, Any] = {
        "api_directory": str(api_dir),
        "exists": api_dir.exists(),
        "files": [],
    }

    if not api_dir.exists():
        return _emit(args, payload)

    for json_path in sorted(api_dir.rglob("*.json")):
        if not is_swagger_file(json_path):
            continue
        entry = _swagger_metadata(json_path, config_mgr.project_root)
        payload["files"].append(entry)

    return _emit(args, payload, _format_api_specs)


def _swagger_metadata(path: Path, project_root: Path) -> dict[str, Any]:
    """Extract lightweight metadata from one swagger file.

    Does not invoke the full ``parse_swagger`` (which would halt on §3.3
    invariants like ``oneOf``). Instead it counts top-level constructs and
    flags the v1-halt patterns so consumers see *which* files would halt
    before running ``jui build``.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {
            "path": _rel(path, project_root),
            "absolute_path": str(path),
            "error": f"{type(e).__name__}: {e}",
        }

    info = raw.get("info") or {}
    title = info.get("title", "") if isinstance(info, dict) else ""
    version = info.get("version", "") if isinstance(info, dict) else ""

    if "openapi" in raw:
        schemas_root = (raw.get("components") or {}).get("schemas") or {}
    elif "swagger" in raw:
        schemas_root = raw.get("definitions") or {}
    else:
        schemas_root = {}

    paths_root = raw.get("paths") or {}
    method_keys = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}
    endpoint_count = 0
    if isinstance(paths_root, dict):
        for path_item in paths_root.values():
            if isinstance(path_item, dict):
                for k in path_item:
                    if k in method_keys:
                        endpoint_count += 1

    schema_count = 0
    enum_count = 0
    if isinstance(schemas_root, dict):
        for body in schemas_root.values():
            if not isinstance(body, dict):
                continue
            if "enum" in body and body.get("type") in ("string", "integer") and "properties" not in body:
                enum_count += 1
            else:
                schema_count += 1

    has_one_of = _contains_keys(raw, ("oneOf", "anyOf", "discriminator"))
    has_multi_file_ref = _has_multi_file_ref(raw)

    return {
        "path": _rel(path, project_root),
        "absolute_path": str(path),
        "title": title,
        "version": version,
        "schema_count": schema_count,
        "enum_count": enum_count,
        "endpoint_count": endpoint_count,
        "has_one_of": has_one_of,
        "has_multi_file_ref": has_multi_file_ref,
    }


def _contains_keys(node: Any, keys: tuple[str, ...]) -> bool:
    """Recursively check whether *node* contains any of *keys*."""
    if isinstance(node, dict):
        for k in node:
            if k in keys:
                return True
        return any(_contains_keys(v, keys) for v in node.values())
    if isinstance(node, list):
        return any(_contains_keys(v, keys) for v in node)
    return False


def _has_multi_file_ref(node: Any) -> bool:
    """True if any ``$ref`` points outside the same document.

    Mirrors the loader's ``_check_ref_local`` rejection set so the
    metadata flag is consistent with what would actually halt at build.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            if (
                ref.startswith(("http://", "https://", "./", "../", "/"))
                or ".yaml" in ref
                or ".yml" in ref
                or ".json" in ref
            ):
                return True
        return any(_has_multi_file_ref(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_multi_file_ref(v) for v in node)
    return False


def _format_api_specs(payload: dict[str, Any]) -> str:
    """Render the ``api-specs`` payload as human-readable text."""
    lines = [f"api_directory: {payload['api_directory']}"]
    if not payload.get("exists"):
        lines.append("  (directory does not exist)")
        return "\n".join(lines)
    if not payload["files"]:
        lines.append("  (no swagger files found)")
        return "\n".join(lines)
    for entry in payload["files"]:
        if "error" in entry:
            lines.append(f"  {entry['path']} — ERROR: {entry['error']}")
            continue
        flags = []
        if entry.get("has_one_of"):
            flags.append("oneOf")
        if entry.get("has_multi_file_ref"):
            flags.append("multi-file-ref")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        lines.append(
            f"  {entry['path']} — {entry['title']} v{entry['version']}"
        )
        lines.append(
            f"    schemas={entry['schema_count']}, "
            f"enums={entry['enum_count']}, "
            f"endpoints={entry['endpoint_count']}{flag_str}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# jui ls api-models
# --------------------------------------------------------------------------- #


def _cmd_ls_api_models(args: argparse.Namespace) -> int:
    """Enumerate generated DTO + Domain files per platform.

    Cross-references against the current swagger to flag orphan DTOs
    (file exists but the schema is gone).
    """
    from ..core.api_model_sync import collect_docs, has_planner
    from ..core.config_manager import ConfigManager
    from ..core.openapi_loader import OpenAPILoadError

    config_mgr = ConfigManager()
    if not config_mgr.exists():
        return _emit_error(args, "jui.config.json not found. Run 'jui init' first.")

    project_root = config_mgr.project_root
    config = config_mgr.load()
    platforms = config.get("platforms") or {}
    target_platform = getattr(args, "platform", None)

    # Compute expected schema names for orphan detection.
    expected_names: set[str] = set()
    swagger_error: str | None = None
    try:
        docs = collect_docs(config_mgr)
        for doc in docs:
            for schema in doc.schemas:
                expected_names.add(schema.name)
            for enum in doc.enums:
                expected_names.add(enum.name)
    except OpenAPILoadError as e:
        swagger_error = str(e)

    payload: dict[str, Any] = {
        "platforms": {},
        "swagger_error": swagger_error,
    }

    for platform, pconfig in platforms.items():
        if target_platform and platform != target_platform:
            continue
        if not has_planner(platform):
            continue
        per_platform = _scan_platform(platform, pconfig, config_mgr, expected_names)
        payload["platforms"][platform] = per_platform

    return _emit(args, payload, _format_api_models)


def _scan_platform(
    platform: str,
    pconfig: dict[str, Any],
    config_mgr,
    expected_names: set[str],
) -> dict[str, Any]:
    """Walk the per-platform model_dir and return the file inventory.

    Per-platform layout differs:

    - iOS: ``<sources>/Model/Generated/*Dto.swift`` (DTO) + ``<sources>/Model/*.swift`` (Domain)
    - Android: ``<sources>/<pkg>/model/generated/*Dto.kt`` (DTO) + ``<sources>/<pkg>/model/*.kt`` (Domain)
    - Web: ``<sources>/models/generated/*Dto.ts`` (DTO) + ``<sources>/models/*.ts`` (Domain)
    """
    api_cfg = config_mgr.api_platform_config(platform)
    project_root = config_mgr.project_root
    platform_root = project_root / pconfig["root"]

    if platform == "ios":
        from ..core.api_model_sync import _resolve_ios_sources_root  # type: ignore
        sources_root = _resolve_ios_sources_root(platform_root)
        model_dir = sources_root / api_cfg["model_dir"]
        dto_dir = model_dir / api_cfg["dto_subdir"]
        suffix = ".swift"
    elif platform == "android":
        from ..core.api_model_sync import _resolve_android_sources_and_package  # type: ignore
        sources_root, base_package = _resolve_android_sources_and_package(platform_root)
        # Mirror plan_android: model_package is either full FQN (has ``.``)
        # or a bare subpackage to prepend with base_package.
        raw_model_pkg = api_cfg["model_package"]
        domain_package = raw_model_pkg if "." in raw_model_pkg else f"{base_package}.{raw_model_pkg}"
        dto_package = f"{domain_package}.{api_cfg['dto_subpackage']}"
        model_dir = sources_root / Path(*domain_package.split("."))
        dto_dir = sources_root / Path(*dto_package.split("."))
        suffix = ".kt"
    elif platform == "web":
        from ..core.api_model_sync import _resolve_web_sources_root  # type: ignore
        sources_root = _resolve_web_sources_root(platform_root)
        model_dir = sources_root / api_cfg["model_dir"]
        dto_dir = model_dir / api_cfg["dto_subdir"]
        suffix = ".ts"
    else:
        model_dir = platform_root
        dto_dir = platform_root
        suffix = ".txt"

    dto_files: list[dict[str, Any]] = []
    domain_files: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []

    if dto_dir.exists():
        for f in sorted(dto_dir.glob(f"*{suffix}")):
            stem = f.stem  # e.g. UserDto
            schema_name = stem[:-3] if stem.endswith("Dto") else stem  # UserDto -> User
            entry = {
                "path": _rel(f, project_root),
                "schema_name": schema_name,
                "kind": "dto" if stem.endswith("Dto") else "enum",
            }
            dto_files.append(entry)
            if expected_names and schema_name not in expected_names:
                orphans.append({**entry, "reason": "schema not in current swagger"})

    if model_dir.exists():
        for f in sorted(model_dir.glob(f"*{suffix}")):
            if dto_dir.exists() and dto_dir in f.parents:
                continue  # skip files under Generated/
            domain_files.append({
                "path": _rel(f, project_root),
                "schema_name": f.stem,
            })

    return {
        "model_dir": str(model_dir.relative_to(project_root)) if model_dir.is_relative_to(project_root) else str(model_dir),
        "dto_dir": str(dto_dir.relative_to(project_root)) if dto_dir.is_relative_to(project_root) else str(dto_dir),
        "dto_files": dto_files,
        "domain_scaffolds": domain_files,
        "orphans": orphans,
    }


def _format_api_models(payload: dict[str, Any]) -> str:
    """Render the ``api-models`` payload as human-readable text."""
    lines: list[str] = []
    if payload.get("swagger_error"):
        lines.append(f"WARNING: swagger load error — {payload['swagger_error']}")
        lines.append("  (orphan detection disabled)")
        lines.append("")
    if not payload["platforms"]:
        lines.append("(no platforms have an API model generator yet)")
        return "\n".join(lines)
    for platform, info in payload["platforms"].items():
        lines.append(f"=== {platform} ===")
        lines.append(f"  model_dir: {info['model_dir']}")
        lines.append(f"  dto_dir:   {info['dto_dir']}")
        lines.append(f"  DTOs: {len(info['dto_files'])}")
        for d in info["dto_files"]:
            lines.append(f"    {d['path']} ({d['kind']}: {d['schema_name']})")
        lines.append(f"  Domain scaffolds: {len(info['domain_scaffolds'])}")
        for d in info["domain_scaffolds"]:
            lines.append(f"    {d['path']}")
        if info["orphans"]:
            lines.append(f"  Orphans: {len(info['orphans'])}")
            for o in info["orphans"]:
                lines.append(f"    {o['path']} — {o['reason']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _rel(path: Path, root: Path) -> str:
    """Return *path* relative to *root* when possible, otherwise absolute."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _emit(
    args: argparse.Namespace,
    payload: dict[str, Any],
    text_formatter=None,
) -> int:
    """Print *payload* as JSON when ``--json`` is set, else human text."""
    if getattr(args, "as_json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif text_formatter:
        print(text_formatter(payload))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _emit_error(args: argparse.Namespace, message: str) -> int:
    """Print an error consistent with the chosen output format."""
    if getattr(args, "as_json", False):
        print(json.dumps({"error": message}, indent=2, ensure_ascii=False))
    else:
        print(f"ERROR: {message}")
    return 1
