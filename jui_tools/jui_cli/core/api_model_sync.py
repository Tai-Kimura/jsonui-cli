"""Shared driver for swagger → DTO + Domain emission across platforms.

Called from:

- ``build_cmd._sync_api_models`` — writes files to disk, prunes orphan DTOs
- ``verify_cmd`` — in-memory regen for drift detection (writes nothing)

Per platform implementation status (Phase 1):

- iOS: full DTO + enum + Domain scaffold
- Android / Web: deferred to Phase 2 / 3 — `_sync_api_models` silently skips
  these platforms until the per-platform generator lands

The split keeps file I/O concerns out of the generators (which stay pure
string emitters with unit-testable methods) and lets verify_cmd reuse the
same regen pipeline without touching disk.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .config_manager import ConfigManager
from .openapi_loader import OpenAPILoadError, load_swagger
from .schema_filter import SchemaFilterConfig
from .schema_ir import SchemaDef, SwaggerDocument


@dataclass(frozen=True)
class SyncPlan:
    """In-memory description of what would be written.

    Used by verify_cmd to compare expected output against disk without
    actually writing. ``build_cmd`` consumes the same plan and persists it.

    ``domain_patchers`` carries optional in-place mutators for Domain
    scaffold files that already exist on disk — used by the Android
    kotlinx pipeline to retroactively inject ``@Serializable(with = ...)``
    + the delegating ``KSerializer`` block onto pre-existing wrappers
    that were emitted before the kotlinx Serializer feature landed.
    Each callable returns True iff it actually changed the file.
    """

    platform: str
    expected_files: dict[Path, str]  # absolute path → expected source
    domain_scaffolds: dict[Path, str]  # absolute path → scaffold source (write only if absent)
    domain_patchers: dict[Path, Callable[[], bool]] = field(default_factory=dict)


def plan_android(
    config_mgr: ConfigManager,
    pconfig: dict,
    docs: list[SwaggerDocument],
) -> SyncPlan:
    """Build the Android write plan without touching disk.

    Resolves ``kjui.config.json#source_directory`` + ``package_name`` so
    DTO + Domain files land in the package layout the existing kjui
    ViewModel / Repository / data classes already use.

    Resolution rules (fixes bug ``jui-android-api-model-generator-wrong-
    source-dir-and-base-package``):

    - Kotlin files live under ``<source_directory>/kotlin/`` (or
      ``/java/`` fallback) — kjui's ``source_directory`` points at the
      source-set root, not the language sub-source-set
    - The consumer's ``package_name`` (e.g. ``com.acme.mobile``)
      is read from ``kjui.config.json`` and used as the FQN base
    - ``api.platforms.android.model_package`` is treated as either:
        * a full FQN (contains a ``.``) — used verbatim
        * a bare subpackage name — prefixed with ``package_name``
    - ``dto_subpackage`` is always appended to ``model_package`` to form
      the DTO package
    """
    from ..generators.android_api_model_generator import (
        AndroidApiModelGenerator,
        AndroidApiPlatformConfig,
        _patch_kotlinx_domain,
    )

    platform_root = config_mgr.project_root / pconfig["root"]
    sources_root, base_package = _resolve_android_sources_and_package(platform_root)
    api_cfg = config_mgr.api_platform_config("android")

    raw_model_pkg = api_cfg["model_package"]
    if "." in raw_model_pkg:
        domain_package = raw_model_pkg
    else:
        domain_package = f"{base_package}.{raw_model_pkg}"
    dto_package = f"{domain_package}.{api_cfg['dto_subpackage']}"

    gen = AndroidApiModelGenerator(
        AndroidApiPlatformConfig(
            sources_root=sources_root,
            domain_package=domain_package,
            dto_package=dto_package,
            serializer=api_cfg["serializer"],
        )
    )

    expected: dict[Path, str] = {}
    scaffolds: dict[Path, str] = {}
    patchers: dict[Path, Callable[[], bool]] = {}
    is_kotlinx = api_cfg["serializer"] == "kotlinx"
    for doc in docs:
        for schema in doc.schemas:
            expected[gen.dto_path(schema.name)] = gen.generate_dto_source(schema, doc)
            if not doc.should_skip_domain(schema):
                dpath = gen.domain_path(schema.name)
                scaffolds[dpath] = gen.generate_domain_source(schema)
                # kotlinx Domain wrappers need the @Serializable annotation
                # and a delegating KSerializer block. Hand a patcher to
                # ``apply_plan`` so existing scaffolds (emitted before
                # this feature landed) get retroactively patched on the
                # next ``jui build``.
                if is_kotlinx:
                    patchers[dpath] = (
                        lambda p=dpath, n=schema.name: _patch_kotlinx_domain(p, n)
                    )
        for enum in doc.enums:
            expected[gen.enum_path(enum.name)] = gen.generate_enum_source(enum, doc)
    return SyncPlan(
        platform="android",
        expected_files=expected,
        domain_scaffolds=scaffolds,
        domain_patchers=patchers,
    )


def plan_web(
    config_mgr: ConfigManager,
    pconfig: dict,
    docs: list[SwaggerDocument],
) -> SyncPlan:
    """Build the Web write plan without touching disk."""
    from ..generators.web_api_model_generator import (
        WebApiModelGenerator,
        WebApiPlatformConfig,
    )

    platform_root = config_mgr.project_root / pconfig["root"]
    sources_root = _resolve_web_sources_root(platform_root)
    api_cfg = config_mgr.api_platform_config("web")
    gen = WebApiModelGenerator(
        WebApiPlatformConfig(
            sources_root=sources_root,
            model_dir=api_cfg["model_dir"],
            dto_subdir=api_cfg["dto_subdir"],
            case_convention=api_cfg["case_convention"],
        )
    )

    expected: dict[Path, str] = {}
    scaffolds: dict[Path, str] = {}
    for doc in docs:
        for schema in doc.schemas:
            expected[gen.dto_path(schema.name)] = gen.generate_dto_source(schema, doc)
            if not doc.should_skip_domain(schema):
                scaffolds[gen.domain_path(schema.name)] = gen.generate_domain_source(schema)
        for enum in doc.enums:
            expected[gen.enum_path(enum.name)] = gen.generate_enum_source(enum, doc)
    return SyncPlan(platform="web", expected_files=expected, domain_scaffolds=scaffolds)


def plan_ios(
    config_mgr: ConfigManager,
    pconfig: dict,
    docs: list[SwaggerDocument],
) -> SyncPlan:
    """Build the iOS write plan without touching disk.

    Resolves ``sjui.config.json#source_directory`` so the output lands in
    the same root the existing IosGenerator uses for ViewModel/Repository.
    """
    from ..generators.ios_api_model_generator import (
        IosApiModelGenerator,
        IosApiPlatformConfig,
    )

    platform_root = config_mgr.project_root / pconfig["root"]
    sources_root = _resolve_ios_sources_root(platform_root)
    api_cfg = config_mgr.api_platform_config("ios")
    gen = IosApiModelGenerator(
        IosApiPlatformConfig(
            sources_root=sources_root,
            model_dir=api_cfg["model_dir"],
            dto_subdir=api_cfg["dto_subdir"],
        )
    )

    expected: dict[Path, str] = {}
    scaffolds: dict[Path, str] = {}
    for doc in docs:
        for schema in doc.schemas:
            expected[gen.dto_path(schema.name)] = gen.generate_dto_source(schema, doc)
            # OR-evaluate per-schema x-jui-skip-domain (schema.skip_domain)
            # and per-app api.schemas.skip_domain (doc.skip_domain_overrides).
            # v2 plan §2.6.
            if not doc.should_skip_domain(schema):
                scaffolds[gen.domain_path(schema.name)] = gen.generate_domain_source(schema)
        for enum in doc.enums:
            expected[gen.enum_path(enum.name)] = gen.generate_enum_source(enum, doc)
    return SyncPlan(platform="ios", expected_files=expected, domain_scaffolds=scaffolds)


def collect_docs(config_mgr: ConfigManager) -> list[SwaggerDocument]:
    """Discover and parse all swagger files. Caller handles ``OpenAPILoadError``.

    Applies the ``api.schemas`` filter (v2 Phase 1.5) from the config —
    when no filter dimension is set, behavior matches v3 Phase 1
    (every ``components.schemas.*`` entry parsed).
    """
    api_dir = config_mgr.api_directory
    schema_filter = SchemaFilterConfig.from_dict(config_mgr.api_schemas_config())
    return load_swagger(api_dir, schema_filter=schema_filter)


def apply_plan(plan: SyncPlan, *, prune_orphans: bool) -> tuple[int, int, int]:
    """Persist *plan* to disk. Returns ``(dto_written, scaffold_written, pruned)``.

    Idempotent: ``atomic_write_text`` skips writes when on-disk content
    matches. Domain scaffold writes are skipped when the file already
    exists (preserving user edits).

    Orphan prune scans the DTO subdirectory and deletes any ``*.swift``
    that isn't in ``plan.expected_files``. Domain scaffolds are never
    pruned (user-owned).
    """
    from .impl_updater import atomic_write_text

    dto_written = 0
    scaffold_written = 0

    for path, source in plan.expected_files.items():
        if atomic_write_text(path, source):
            dto_written += 1

    for path, source in plan.domain_scaffolds.items():
        if path.exists():
            # Run the per-path patcher (if any) — used by kotlinx Android
            # to retroactively add ``@Serializable`` + the delegating
            # ``KSerializer`` block to wrappers emitted before that
            # feature landed. Patchers are idempotent; subsequent builds
            # over an already-patched file return False.
            patcher = plan.domain_patchers.get(path)
            if patcher is not None and patcher():
                scaffold_written += 1
            continue
        if atomic_write_text(path, source):
            scaffold_written += 1

    pruned = 0
    if prune_orphans and plan.expected_files:
        # Group expected DTOs by directory so we only scan dirs we own.
        dto_dirs = {p.parent for p in plan.expected_files}
        expected_set = set(plan.expected_files)
        for dto_dir in dto_dirs:
            if not dto_dir.exists():
                continue
            for existing in dto_dir.iterdir():
                if not existing.is_file():
                    continue
                if existing.suffix not in {".swift", ".kt", ".ts"}:
                    continue
                if existing in expected_set:
                    continue
                existing.unlink()
                pruned += 1

    return dto_written, scaffold_written, pruned


def diff_plan(plan: SyncPlan) -> list[str]:
    """Return human-readable drift descriptions for verify_cmd.

    Each entry is one line describing a file that differs from disk. An
    empty list means "no drift".
    """
    drift: list[str] = []
    for path, expected in plan.expected_files.items():
        if not path.exists():
            drift.append(f"MISSING  {path}")
            continue
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError as e:
            drift.append(f"UNREADABLE {path}: {e}")
            continue
        if actual != expected:
            drift.append(f"MODIFIED {path}")
    return drift


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _resolve_ios_sources_root(platform_root: Path) -> Path:
    """Mirror ``IosGenerator._resolve_source_base`` so API models land in
    the same root as ViewModel/Repository.

    Reads ``<platform_root>/sjui.config.json#source_directory``. Falls
    back to ``platform_root`` itself when the config is missing — matches
    the behavior of the existing iOS generator.
    """
    sjui_config = platform_root / "sjui.config.json"
    if sjui_config.exists():
        try:
            with open(sjui_config, "r", encoding="utf-8") as f:
                data = json.load(f)
            source_dir = data.get("source_directory", "")
            if source_dir:
                return platform_root / source_dir
        except (OSError, json.JSONDecodeError):
            pass
    return platform_root


def _resolve_android_sources_and_package(platform_root: Path) -> tuple[Path, str]:
    """Mirror ``AndroidGenerator`` for source dir + base package resolution.

    Reads ``<platform_root>/kjui.config.json``:

    - ``source_directory`` — source-set root, default ``app/src/main``
      (kjui convention; Kotlin files live in the ``kotlin/`` sub-source-set
      under it, matching ``data_directory: "kotlin/<pkg>/data"`` etc.)
    - ``package_name`` — base FQN, default ``com.example.app``

    The returned ``sources_root`` is ``<source_directory>/kotlin/`` (with
    ``java/`` fallback when ``kotlin/`` doesn't exist). The Kotlin sub-
    source-set must be part of the path because the Kotlin compiler maps
    file location to package via ``kotlin/<pkg-path>/<File>.kt``; without
    it, generated DTOs would land outside the source set and not be
    compiled.

    Bug history: this function previously used ``source_directory``
    verbatim and hardcoded ``com.example.app``, dropping the
    ``kotlin/`` sub-source-set and overriding the consumer's
    ``package_name``. See report
    ``2026-05-27-jui-android-api-model-generator-wrong-source-dir-and-base-package.md``.
    """
    kjui_config = platform_root / "kjui.config.json"
    source_directory = "app/src/main"
    base_package = "com.example.app"
    if kjui_config.exists():
        try:
            with open(kjui_config, "r", encoding="utf-8") as f:
                data = json.load(f)
            source_directory = data.get("source_directory", source_directory)
            base_package = (
                data.get("package_name")
                or data.get("base_package")
                or data.get("package")
                or base_package
            )
        except (OSError, json.JSONDecodeError):
            pass
    sources_root = platform_root / source_directory / "kotlin"
    if not sources_root.exists():
        alt_java = platform_root / source_directory / "java"
        if alt_java.exists():
            sources_root = alt_java
    return sources_root, base_package


def _resolve_web_sources_root(platform_root: Path) -> Path:
    """Web: source root is the directory holding ``src/`` (default the
    platform_root itself, since ``model_dir`` is already config-controlled).

    Reads ``<platform_root>/rjui.config.json#source_directory`` when present
    so projects with non-standard layouts (e.g. ``app/src``) still work.
    """
    rjui_config = platform_root / "rjui.config.json"
    if rjui_config.exists():
        try:
            with open(rjui_config, "r", encoding="utf-8") as f:
                data = json.load(f)
            source_dir = data.get("source_directory", "")
            if source_dir:
                return platform_root / source_dir
        except (OSError, json.JSONDecodeError):
            pass
    return platform_root / "src"


# --------------------------------------------------------------------------- #
# Generator dispatch
# --------------------------------------------------------------------------- #


_PLATFORM_PLANNERS = {
    "ios": plan_ios,
    "android": plan_android,
    "web": plan_web,
}


def planners_for(args: argparse.Namespace) -> list[str]:
    """Return the platforms to plan against, honoring ``--ios-only`` etc.

    Mirrors the gating logic in ``build_cmd._distribute_*`` so the API
    model sync respects the same flags.
    """
    if getattr(args, "ios_only", False):
        return ["ios"]
    if getattr(args, "android_only", False):
        return ["android"]
    if getattr(args, "web_only", False):
        return ["web"]
    return list(_PLATFORM_PLANNERS.keys())


def has_planner(platform: str) -> bool:
    """True if *platform* has a Phase 1-ready planner."""
    return platform in _PLATFORM_PLANNERS


def plan_for(
    platform: str,
    config_mgr: ConfigManager,
    pconfig: dict,
    docs: list[SwaggerDocument],
) -> SyncPlan:
    """Dispatch to the right ``plan_*`` for *platform*.

    Raises ``KeyError`` for unsupported platforms — call :func:`has_planner`
    first when iterating across multiple platforms.
    """
    return _PLATFORM_PLANNERS[platform](config_mgr, pconfig, docs)
