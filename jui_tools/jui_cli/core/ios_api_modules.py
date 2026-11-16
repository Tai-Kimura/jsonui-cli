"""``api.platforms.ios.modules`` — iOS DTOs written into a Swift module of their own.

Ticket jui-api-model-ios-dto-cannot-be-shared-with-framework-target. An app that shares code with an App Extension
keeps that code in a framework, and the framework cannot see the app's ``internal`` DTOs. Each entry names the
schemas (glob, the same matching as ``api.schemas.include_schemas``) that go to that module, where its files go, and
how visible they are::

    "api": {"platforms": {"ios": {"modules": [
      {"module": "EventCore", "include_schemas": ["Event*"],
       "model_dir": "../EventCore/Model", "dto_subdir": "Generated", "access_level": "public"}
    ]}}}

``module``, ``include_schemas`` and ``model_dir`` are required; ``dto_subdir`` defaults to ``"Generated"`` and
``access_level`` to ``"public"``. ``model_dir`` is relative to the app's source directory, like the app's own.

The key sits under ``api.platforms.ios``, beside the other per-platform settings, so Android and web never read it,
and the platform-neutral ``api.schemas`` filter is unchanged: it still decides WHAT is generated, this decides only
WHERE on iOS.

The rules:

- A schema the patterns name goes to that module, and is no longer written in the app's directory. Inline types
  (``{Parent}{Field}`` or ``x-jui-name``) go wherever their parent goes.
- A module's type may refer only to types in the same module (a framework cannot see the app), so a ``$ref`` that
  leaves it halts with ``module-ref-outside``; the fix is a pattern in that module's ``include_schemas``. The types
  are never moved there silently: a shared type moving into a framework is a decision the project makes.
- An app type that refers to a module's type gets ``import <module>``.
- A name may go to one place only (``module-name-collision``), and two places may not share a directory, because
  each one's ``dto_subdir`` is pruned of everything it does not expect (``module-dir-overlap``).
- Domain scaffolds stay in the app's model directory (they are the app's code); a new one imports the module.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Iterable

from .openapi_loader import OpenAPILoadError
from .schema_ir import FieldType, SwaggerDocument

_SWIFT_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ACCESS_LEVELS = ("public", "internal")
_KEY = "api.platforms.ios.modules"


@dataclass(frozen=True)
class IosModule:
    module: str
    include_schemas: tuple[str, ...]
    model_dir: str
    dto_subdir: str = "Generated"
    access_level: str = "public"
    index: int = 0

    @property
    def where(self) -> str:
        return f"{_KEY}[{self.index}] (module {self.module!r})"


def _config_error(message: str) -> OpenAPILoadError:
    return OpenAPILoadError("ios-modules-config", message, source="jui.config.json")


def modules_from_config(raw: Any) -> list[IosModule]:
    """Read ``api.platforms.ios.modules``. Missing or ``[]``: no modules (the output is what it was without the key)."""
    if raw is None or raw == []:
        return []
    if not isinstance(raw, list):
        raise _config_error(f"{_KEY} must be a list of objects; got {type(raw).__name__}.")
    out: list[IosModule] = []
    names: set[str] = set()
    for i, entry in enumerate(raw):
        where = f"{_KEY}[{i}]"
        if not isinstance(entry, dict):
            raise _config_error(f"{where} must be an object; got {type(entry).__name__}.")
        unknown = sorted(set(entry) - {"module", "include_schemas", "model_dir", "dto_subdir", "access_level"})
        if unknown:
            raise _config_error(f"{where} has unknown key(s) {unknown}; the keys are module, include_schemas, "
                                f"model_dir, dto_subdir, access_level.")
        module = entry.get("module")
        if not isinstance(module, str) or not _SWIFT_IDENT.match(module):
            raise _config_error(f"{where}.module must be the Swift module's name (the name `import` takes); "
                                f"got {module!r}.")
        if module in names:
            raise _config_error(f"{where}.module {module!r} is named twice; put its patterns in one entry.")
        names.add(module)
        patterns = entry.get("include_schemas")
        if isinstance(patterns, str):
            patterns = [patterns]
        if (not isinstance(patterns, list) or not patterns
                or not all(isinstance(p, str) and p for p in patterns)):
            raise _config_error(f"{where}.include_schemas must be a non-empty list of schema-name patterns "
                                f"(e.g. [\"Event*\"]); got {entry.get('include_schemas')!r}.")
        model_dir = entry.get("model_dir")
        if not isinstance(model_dir, str) or not model_dir.strip():
            raise _config_error(f"{where}.model_dir must be a directory relative to the app's source directory; "
                                f"got {model_dir!r}.")
        dto_subdir = entry.get("dto_subdir", "Generated")
        if not isinstance(dto_subdir, str) or not dto_subdir.strip():
            raise _config_error(f"{where}.dto_subdir must be a directory name; got {dto_subdir!r}.")
        access = entry.get("access_level", "public")
        if access not in _ACCESS_LEVELS:
            raise _config_error(f"{where}.access_level must be one of {list(_ACCESS_LEVELS)}; got {access!r}.")
        out.append(IosModule(module=module, include_schemas=tuple(patterns), model_dir=model_dir,
                             dto_subdir=dto_subdir, access_level=access, index=i))
    return out


def _type_refs(ftype: FieldType | None, acc: set[str]) -> set[str]:
    if ftype is None:
        return acc
    if ftype.ref_name:
        acc.add(ftype.ref_name)
    _type_refs(ftype.element, acc)
    _type_refs(ftype.alias_map, acc)
    if ftype.one_of is not None:
        acc.update(v.ref_name for v in ftype.one_of.variants)
    return acc


def item_refs(docs: Iterable[SwaggerDocument]) -> dict[str, set[str]]:
    """Every generated name (schema, union, enum) → the names its Swift file refers to."""
    refs: dict[str, set[str]] = {}
    for doc in docs:
        for schema in doc.schemas:
            acc = refs.setdefault(schema.name, set())
            for f in schema.fields:
                _type_refs(f.type, acc)
            _type_refs(schema.wrapped_type, acc)
        for union in doc.unions:
            refs.setdefault(union.name, set()).update(v.ref_name for v in union.variants)
        for enum in doc.enums:
            refs.setdefault(enum.name, set())
    for name in refs:
        refs[name].discard(name)
    return refs


def _top_level_names(doc: SwaggerDocument) -> set[str]:
    """``components.schemas`` (or Swagger 2 ``definitions``) keys: the names a pattern can pick. Everything else the
    loader generated is an inline type, which follows its parent."""
    try:
        raw = json.loads(Path(doc.source_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {s.name for s in doc.schemas} | {e.name for e in doc.enums} | {u.name for u in doc.unions}
    if "openapi" in raw:
        return set(((raw.get("components") or {}).get("schemas") or {}).keys())
    return set((raw.get("definitions") or {}).keys())


def assign(modules: list[IosModule], docs: list[SwaggerDocument]) -> dict[str, IosModule]:
    """Which module each generated name goes to (absent: the app). Halts on a reference that leaves a module and on
    a name two modules both take; warns once per module whose patterns match nothing."""
    if not modules:
        return {}
    refs = item_refs(docs)
    top: set[str] = set()
    for doc in docs:
        top |= _top_level_names(doc)
    picked: dict[str, IosModule] = {}
    for mod in modules:
        matched = sorted(n for n in refs if n in top and any(fnmatchcase(n, p) for p in mod.include_schemas))
        if not matched:
            print(f"  WARNING [api-model]: {mod.where}: include_schemas {list(mod.include_schemas)} matches no "
                  f"generated schema, so nothing is written to {mod.model_dir}. Check the patterns against "
                  f"components.schemas (names are case-sensitive) and the api.schemas filter.", file=sys.stderr)
        for name in matched:
            other = picked.get(name)
            if other is not None and other is not mod:
                raise OpenAPILoadError(
                    "module-name-collision",
                    f"schema {name!r} is picked by both {other.where} and {mod.where}; a type can live in one "
                    f"module only (two would give the app two types of one name). Narrow one of the patterns.")
            picked[name] = mod
    # Inline types follow their parent, transitively (an inline object can hold an inline enum).
    changed = True
    while changed:
        changed = False
        for name, mod in list(picked.items()):
            for r in sorted(refs.get(name, ())):
                if r in top or r not in refs:
                    continue
                owner = picked.get(r)
                if owner is None:
                    picked[r] = mod
                    changed = True
                elif owner is not mod:
                    raise OpenAPILoadError(
                        "module-name-collision",
                        f"inline type {r!r} is reached from {owner.where} and from {mod.where}; a type can live in "
                        f"one module only. Give one of them its own name (x-jui-name) or extract it to "
                        f"components.schemas and pick it in one module.")
    for name in sorted(picked):
        mod = picked[name]
        for r in sorted(refs.get(name, ())):
            if r in refs and picked.get(r) is not mod:
                dest = picked[r].where if r in picked else "the app"
                raise OpenAPILoadError(
                    "module-ref-outside",
                    f"{name!r} goes to {mod.where} but refers to {r!r}, which goes to {dest}; a type in a module "
                    f"cannot see the app's types. Add {r!r} (or a pattern matching it) to that module's "
                    f"include_schemas.")
    return picked


def check_dirs(app_dto_dir: Path, app_sources_root: Path, module_dirs: dict[str, tuple[IosModule, Path]]) -> None:
    """Halt when two places share a DTO directory (each one prunes its directory of what it does not expect, so
    they would delete each other's files); warn when a module's directory is inside the app's sources."""
    seen: dict[Path, str] = {app_dto_dir.resolve(): "the app (api.platforms.ios model_dir/dto_subdir)"}
    for mod, dto_dir in module_dirs.values():
        key = dto_dir.resolve()
        if key in seen:
            raise OpenAPILoadError(
                "module-dir-overlap",
                f"{mod.where} writes to {dto_dir}, which {seen[key]} also writes to; each place prunes its "
                f"directory of every file it did not write, so they would delete each other's DTOs. Give the "
                f"module its own model_dir or dto_subdir.")
        seen[key] = mod.where
        if key.is_relative_to(app_sources_root.resolve()):
            print(f"  WARNING [api-model]: {mod.where}: model_dir {mod.model_dir} is inside the app's source "
                  f"directory {app_sources_root}, so a synchronized Xcode folder compiles these files into the app "
                  f"target as well as into {mod.module}, and the app sees each type twice. Exclude the folder from "
                  f"the app target, or put model_dir outside the app's sources.", file=sys.stderr)


def warn_scaffolds_without_import(scaffolds: dict[str, tuple[IosModule, Path]]) -> None:
    """Existing Domain scaffolds (the app's code, never rewritten) that wrap a DTO now in a module and do not import
    it: they stop compiling. One line per module."""
    missing: dict[str, tuple[IosModule, list[str], Path]] = {}
    for name, (mod, path) in sorted(scaffolds.items()):
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if re.search(rf"^\s*(@\w+\s+)*import\s+{re.escape(mod.module)}\b", text, re.M):
            continue
        entry = missing.setdefault(mod.module, (mod, [], path.parent))
        entry[1].append(name)
    for module, (mod, names, folder) in missing.items():
        shown = ", ".join(names[:8]) + (f", ... (+{len(names) - 8} more)" if len(names) > 8 else "")
        print(f"  WARNING [api-model]: {len(names)} Domain scaffold(s) in {folder} wrap a DTO that {mod.where} now "
              f"holds and do not `import {module}`, so they no longer compile: {shown}. Add `import {module}` to "
              f"each (or move them into the module).", file=sys.stderr)
