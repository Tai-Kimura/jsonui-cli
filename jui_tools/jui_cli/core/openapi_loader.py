"""Load OpenAPI / Swagger 2.0 JSON / YAML files and extract :class:`SchemaIR`.

Entry point: :func:`load_swagger`. Reads ``*.json`` / ``*.yaml`` / ``*.yml``
files from a directory, filters to OpenAPI / Swagger artifacts via
:func:`is_swagger_file` / :func:`is_swagger_yaml_file`, parses each into a
:class:`SwaggerDocument`.

Input normalization (2026-07, Q8 / Q12 lift — plan
``2026-07-24-v1-unsupported/01``):

- YAML swagger is parsed (PyYAML, lazy import) and merged into the same
  pipeline as JSON. Canonical authoring format stays JSON; nothing is
  written back to disk.
- Relative cross-file ``$ref`` between files inside the api directory are
  resolved by a pre-parse merge layer (:class:`_CrossFileRefResolver`), so
  :func:`parse_swagger` — whose signature is frozen — never sees one.

Union support (2026-07, plan ``2026-07-24-v1-unsupported/02``):

- Schema-level ``oneOf`` + ``discriminator`` (top-level union envelope)
  parses into :class:`UnionDef`. When ``discriminator.mapping`` is absent
  the mapping is inferred from each variant's internal tag property
  (``const`` string or single-value string ``enum``); the inferred
  mapping is logged as a WARNING on stderr.
- Field-level ``oneOf`` + ``discriminator`` keeps requiring an explicit
  ``mapping`` (the tag lives in the parent's sibling property there —
  variant-internal tags are not the wire mechanism, so inference does
  not apply).

Format retention (2026-07, plan ``2026-07-24-v1-unsupported/03``):

- ``type: string`` schemas retain the ``date-time`` / ``uuid`` / ``binary``
  format hint on :attr:`FieldType.format`. The IR carries the hint
  unconditionally; whether generators map it to native types is the
  per-doc opt-in ``api.format_mapping`` decision.

§3.3 ERROR halt rules enforced here (raise :class:`OpenAPILoadError`):

- ``anyOf`` → halt (permanent — untagged unions have no portable native
  representation)
- ``oneOf`` without ``discriminator`` → halt
- union schema used as a variant of another union → halt (permanent)
- non-string / duplicate / missing variant tags when inferring a
  schema-level mapping → halt
- explicit mapping contradicting a variant's internal tag → halt
- URL ``$ref``, ``$ref`` escaping the api dir, non-schema pointers,
  cross-file ref cycles → halt
- YAML 1.1 implicit typing that diverges from JSON (Norway problem) → halt
- same doc under two suffixes (``foo.yaml`` + stale ``foo.json``) → halt
- same-name top-level schema with different bodies across docs → halt
- direct self-reference without collection indirection → halt (Q13)
- inline object name collision with top-level schema → halt (Q4 / B2)
- ``type: object`` with no ``$ref`` / ``properties`` / ``additionalProperties``
  → halt (§3.3)

Soft cases (warning only, NOT halt):

- ``additionalProperties: true`` / omitted → silently drop extra fields,
  DTO declares only enumerated properties (§3.3, §4)
"""
from __future__ import annotations

import copy
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

from .schema_filter import SchemaFilterConfig, apply_filter
from .schema_ir import (
    EnumDef,
    FieldDef,
    FieldType,
    OneOfRef,
    OneOfVariant,
    PrimitiveKind,
    SchemaDef,
    SwaggerDocument,
    UnionDef,
)


class OpenAPILoadError(Exception):
    """Raised when a swagger document violates §3.3 v1 constraints.

    Carries the source file + JSON pointer so the caller can show the user
    where the offending construct lives. ``code`` is a short tag used by
    ``_sync_api_models`` to surface a meaningful CLI error.
    """

    def __init__(self, code: str, message: str, *, source: str = "", pointer: str = ""):
        self.code = code
        self.source = source
        self.pointer = pointer
        suffix = []
        if source:
            suffix.append(source)
        if pointer:
            suffix.append(pointer)
        location = f" ({' '.join(suffix)})" if suffix else ""
        super().__init__(f"[{code}] {message}{location}")


def is_swagger_file(path: Path) -> bool:
    """Return True if *path* looks like an OpenAPI 3.x or Swagger 2.0 doc.

    Reads only the top-level keys via ``json.load`` — cheap enough to call
    on every ``*.json`` in ``api_directory`` during discovery.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return "openapi" in data or "swagger" in data


_YAML_SWAGGER_KEY_RE = re.compile(r"^(?:openapi|swagger)\s*:", re.MULTILINE)


def is_swagger_yaml_file(path: Path) -> bool:
    """Return True if a YAML *path* looks like an OpenAPI / Swagger doc.

    v1 cannot parse YAML (Q8), but we still need to tell apart a YAML swagger
    the user *intended* as a codegen input (→ the helpful "convert to JSON"
    halt) from an unrelated YAML artifact that merely shares the api
    directory (→ skip it, like a non-swagger ``*.json``). Decided by a cheap
    text scan for a top-level ``openapi:`` / ``swagger:`` key — no YAML parser
    dependency, mirroring :func:`is_swagger_file`'s top-level-key check.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    return bool(_YAML_SWAGGER_KEY_RE.search(text))


_PYYAML_HINT = (
    "PyYAML is required to read YAML swagger files but is not installed in "
    "this Python environment. Run `pip3 install pyyaml` and retry."
)


def _import_yaml():
    """Import PyYAML lazily.

    Kept lazy (and monkeypatchable for tests) because the rsync /
    ``jui sync_tool`` distribution path does not re-run ``pip install`` —
    a module-top import would break every existing consumer that never
    uses YAML.
    """
    try:
        import yaml
    except ImportError:
        return None
    return yaml


def _safe_load_yaml(path: Path) -> Any:
    """``yaml.safe_load`` with the loader's halt semantics.

    Raises ``pyyaml-missing`` when the dependency is absent and
    ``yaml-parse-error`` (with line/column when available) on malformed
    input. Type-coercion guards are the caller's job — a regex-prefiltered
    file that turns out not to be a swagger doc must be skipped without
    them (see :func:`load_swagger`).
    """
    yaml_mod = _import_yaml()
    if yaml_mod is None:
        raise OpenAPILoadError("pyyaml-missing", _PYYAML_HINT, source=str(path))
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml_mod.safe_load(f)
    except yaml_mod.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        loc = (
            f" at line {mark.line + 1}, column {mark.column + 1}"
            if mark is not None
            else ""
        )
        raise OpenAPILoadError(
            "yaml-parse-error",
            f"YAML parse failed{loc}: {e}",
            source=str(path),
        ) from e


def _check_yaml_type_coercion(node: Any, *, source: str, pointer: str = "#") -> None:
    """Halt where YAML 1.1 implicit typing silently diverged from JSON.

    ``yaml.safe_load`` type-coerces unquoted scalars: ``NO`` → bool (the
    Norway problem), ``2026-07-24`` → ``datetime.date``, and allows
    non-string mapping keys — all of which would make "YAML input yields
    the same IR as JSON" silently false. Enum members and mapping keys are
    where coercion corrupts codegen, so those halt with quote-the-value
    guidance. Plain bools elsewhere (``nullable: true`` …) are legitimate
    JSON and pass through.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                raise OpenAPILoadError(
                    "yaml-type-coercion",
                    f"Mapping key {key!r} was implicitly typed as "
                    f"{type(key).__name__} by the YAML parser. Quote the "
                    f"key so it stays a string like in JSON.",
                    source=source,
                    pointer=pointer,
                )
            child_pointer = f"{pointer}/{key}"
            if key == "enum" and isinstance(value, list):
                for i, member in enumerate(value):
                    if isinstance(member, bool) or not isinstance(
                        member, (str, int, float, type(None))
                    ):
                        raise OpenAPILoadError(
                            "yaml-type-coercion",
                            f"Enum member {member!r} was implicitly typed "
                            f"as {type(member).__name__} by the YAML parser "
                            f"(YAML 1.1 coerces NO/yes/on/off to bool and "
                            f"date literals to dates). Quote the value "
                            f"(e.g. 'NO') to keep it a string.",
                            source=source,
                            pointer=f"{child_pointer}/{i}",
                        )
                continue
            _check_yaml_type_coercion(value, source=source, pointer=child_pointer)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _check_yaml_type_coercion(item, source=source, pointer=f"{pointer}/{i}")
    elif isinstance(node, (datetime.date, datetime.datetime)):
        raise OpenAPILoadError(
            "yaml-type-coercion",
            f"Value {node!r} was implicitly parsed as a date by the YAML "
            f"parser. Quote it (e.g. '2026-07-24') to keep it a string.",
            source=source,
            pointer=pointer,
        )


def _check_duplicate_swagger_basenames(paths: list[Path]) -> None:
    """Halt when the same swagger doc exists under two suffixes.

    ``foo.yaml`` next to ``foo.json`` is almost always a stale converted
    copy — silently regenerating outdated DTOs from it is the exact silent
    drift v1 is built to prevent, so "JSON wins + warn" was rejected in
    favor of an explicit halt.
    """
    groups: dict[tuple[str, str], list[Path]] = {}
    for p in paths:
        groups.setdefault((str(p.parent), p.stem), []).append(p)
    for (_, stem), group in sorted(groups.items()):
        if len(group) > 1:
            names = ", ".join(sorted(p.name for p in group))
            raise OpenAPILoadError(
                "duplicate-swagger-basename",
                f"Swagger doc {stem!r} exists more than once ({names}). "
                f"Keep exactly one — a stale converted copy would silently "
                f"regenerate outdated DTOs.",
                source=str(group[0].parent),
            )


def _normalize_schema_body(body: Any) -> str:
    """Canonical fingerprint of a raw schema body for cross-doc comparison.

    ``$ref`` strings are canonicalized to their terminal schema name
    because that is exactly the post-merge semantics: ``#/definitions/X``,
    ``#/components/schemas/X`` and ``./common.json#/components/schemas/X``
    all denote the merged top-level schema ``X``.
    """

    def canon(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                key: (
                    f"$ref:{value.rsplit('/', 1)[-1]}"
                    if key == "$ref" and isinstance(value, str)
                    else canon(value)
                )
                for key, value in node.items()
            }
        if isinstance(node, list):
            return [canon(item) for item in node]
        return node

    return json.dumps(canon(body), sort_keys=True, default=repr)


class _CrossFileRefResolver:
    """Resolve relative cross-file ``$ref`` before :func:`parse_swagger`.

    Operates strictly as a pre-parse merge layer: referenced schemas are
    deep-copied into the referencing document's own schema container and
    every cross-file ref string is rewritten to the local form, so
    :func:`parse_swagger` — whose signature is frozen because generator
    tests call it directly — never sees a cross-file ref.

    Supported: relative paths (with or without ``./``) between files
    inside the api directory, JSON or YAML targets, pointers into
    ``#/components/schemas/`` / ``#/definitions/``. Halted: URL refs
    (``multi-file-ref``), paths escaping the api directory
    (``ref-outside-api-dir``), non-schema pointers
    (``ref-non-schema-pointer``), cross-file cycles
    (``cross-file-ref-cycle`` — break them by co-locating the mutually
    recursive schemas in one file).

    The file cache is shared across documents of one :func:`load_swagger`
    run; merged bodies are deep copies, so cached raws stay pristine.
    """

    def __init__(self, api_directory: Path):
        self._api_dir = api_directory.resolve()
        self._file_cache: dict[Path, Any] = {}

    def merge_into(self, raw: dict[str, Any], doc_path: Path) -> dict[str, Any]:
        """Resolve every cross-file ref in *raw* in place.

        Returns the document's (possibly created) top-level schema
        container so the caller can run the cross-doc conflict check
        against raw bodies.
        """
        self._root_path = doc_path.resolve()
        if "swagger" in raw:
            container = raw.get("definitions")
            if not isinstance(container, dict):
                container = {}
                raw["definitions"] = container
            self._local_prefix = "#/definitions/"
        else:
            components = raw.get("components")
            if not isinstance(components, dict):
                components = {}
                raw["components"] = components
            container = components.get("schemas")
            if not isinstance(container, dict):
                container = {}
                components["schemas"] = container
            self._local_prefix = "#/components/schemas/"
        self._container = container
        self._merged: set[tuple[Path, str]] = set()
        self._walk(raw, base_file=self._root_path, stack=())
        return container

    def _walk(
        self, node: Any, *, base_file: Path, stack: tuple[tuple[Path, str], ...]
    ) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                node["$ref"] = self._resolve_ref(ref, base_file=base_file, stack=stack)
            # Snapshot: _ensure_merged inserts merged schemas into the root
            # container while we may be iterating that very dict. Newly
            # merged bodies are walked by their own _walk call, so skipping
            # them here is correct, not just safe.
            for key, value in list(node.items()):
                if key == "$ref":
                    continue
                self._walk(value, base_file=base_file, stack=stack)
        elif isinstance(node, list):
            for item in node:
                self._walk(item, base_file=base_file, stack=stack)

    def _resolve_ref(
        self, ref: str, *, base_file: Path, stack: tuple[tuple[Path, str], ...]
    ) -> str:
        at_root = base_file == self._root_path
        if ref.startswith("#"):
            if at_root:
                # Native local ref — parse_swagger's own rules apply.
                return ref
            # Local ref inside a merged external body points into the
            # external file's own container: pull the target in too and
            # rewrite to the root document's container prefix.
            name = self._schema_pointer_name(ref[1:], ref, base_file)
            self._ensure_merged(base_file, name, ref, stack)
            return self._local_prefix + name
        if ref.startswith(("http://", "https://")):
            raise OpenAPILoadError(
                "multi-file-ref",
                f"URL $ref not supported: {ref!r}. Vendor the referenced "
                f"schema into a file inside the api directory and use a "
                f"relative $ref.",
                source=str(base_file),
            )
        file_part, _, fragment = ref.partition("#")
        name = self._schema_pointer_name(fragment, ref, base_file)
        target = (base_file.parent / file_part).resolve()
        if not target.is_relative_to(self._api_dir):
            raise OpenAPILoadError(
                "ref-outside-api-dir",
                f"$ref {ref!r} escapes the api directory "
                f"({self._api_dir}). Move the referenced file under the "
                f"api directory.",
                source=str(base_file),
            )
        self._ensure_merged(target, name, ref, stack)
        return self._local_prefix + name

    @staticmethod
    def _schema_pointer_name(fragment: str, ref: str, base_file: Path) -> str:
        for prefix in ("/components/schemas/", "/definitions/"):
            if fragment.startswith(prefix):
                name = fragment[len(prefix):]
                if name and "/" not in name:
                    return name
        raise OpenAPILoadError(
            "ref-non-schema-pointer",
            f"$ref {ref!r} does not point at a top-level schema. "
            f"Cross-file refs must target #/components/schemas/<Name> or "
            f"#/definitions/<Name> — pointers into paths / parameters / "
            f"responses (or whole-file refs) are not supported.",
            source=str(base_file),
        )

    def _ensure_merged(
        self,
        file: Path,
        name: str,
        ref: str,
        stack: tuple[tuple[Path, str], ...],
    ) -> None:
        key = (file, name)
        if key in stack:
            chain = " -> ".join(f"{f.name}#{n}" for f, n in stack + (key,))
            raise OpenAPILoadError(
                "cross-file-ref-cycle",
                f"Cross-file $ref cycle: {chain}. Break the cycle by "
                f"moving the mutually recursive schemas into a single "
                f"file.",
                source=str(file),
            )
        if file == self._root_path:
            # Points back into the document being processed — nothing to
            # merge, but the target must exist.
            if name not in self._container:
                raise OpenAPILoadError(
                    "ref-not-found",
                    f"$ref {ref!r} points back at this document but no "
                    f"top-level schema named {name!r} exists.",
                    source=str(self._root_path),
                )
            return
        if key in self._merged:
            return
        raw = self._load_file(file, ref)
        body = self._lookup(raw, name)
        if body is None:
            raise OpenAPILoadError(
                "ref-not-found",
                f"$ref {ref!r}: no schema named {name!r} in {file.name}",
                source=str(file),
            )
        existing = self._container.get(name)
        if existing is not None:
            if _normalize_schema_body(existing) != _normalize_schema_body(body):
                raise OpenAPILoadError(
                    "cross-doc-schema-conflict",
                    f"$ref {ref!r} would merge schema {name!r} from "
                    f"{file.name}, but a different schema with that name "
                    f"already exists in this document's scope. Rename one "
                    f"of them or share a single definition.",
                    source=str(self._root_path),
                )
            self._merged.add(key)
            return
        body_copy = copy.deepcopy(body)
        self._container[name] = body_copy
        self._walk(body_copy, base_file=file, stack=stack + (key,))
        self._merged.add(key)

    def _load_file(self, path: Path, ref: str) -> Any:
        cached = self._file_cache.get(path)
        if cached is not None:
            return cached
        if not path.exists():
            raise OpenAPILoadError(
                "ref-not-found",
                f"$ref {ref!r}: referenced file does not exist",
                source=str(path),
            )
        if path.suffix in (".yaml", ".yml"):
            data = _safe_load_yaml(path)
            _check_yaml_type_coercion(data, source=str(path))
        else:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                raise OpenAPILoadError(
                    "json-parse-error",
                    f"$ref {ref!r}: referenced file is not valid JSON: {e}",
                    source=str(path),
                ) from e
        self._file_cache[path] = data
        return data

    @staticmethod
    def _lookup(raw: Any, name: str) -> Any:
        """Find *name* in a loaded file's schema containers (either style)."""
        if not isinstance(raw, dict):
            return None
        components = raw.get("components")
        if isinstance(components, dict):
            schemas = components.get("schemas")
            if isinstance(schemas, dict) and isinstance(schemas.get(name), dict):
                return schemas[name]
        definitions = raw.get("definitions")
        if isinstance(definitions, dict) and isinstance(definitions.get(name), dict):
            return definitions[name]
        return None


def _check_cross_doc_schemas(
    doc: SwaggerDocument,
    schemas_root: dict[str, Any],
    registry: dict[str, tuple[str, str]],
) -> None:
    """Cross-doc same-name emission guard (new in the Q12 lift).

    Multiple docs referencing a shared ``common.json#Money`` all end up
    emitting a top-level ``Money`` — with one generated file path per
    schema name, the sync layer's dict used to silently last-win. Now:
    identical normalized bodies → allowed (the sync layer dedups,
    first doc wins); differing bodies → ``cross-doc-schema-conflict``.

    Inline-derived names are skipped (absent from *schemas_root*); the
    per-doc ``inline-name-collision`` rules already govern those.
    """
    emitted = (
        {s.name for s in doc.schemas}
        | {e.name for e in doc.enums}
        | {u.name for u in doc.unions}
    )
    for name in sorted(emitted):
        body = schemas_root.get(name)
        if body is None:
            continue
        normalized = _normalize_schema_body(body)
        prior = registry.get(name)
        if prior is None:
            registry[name] = (normalized, doc.source_path)
        elif prior[0] != normalized:
            raise OpenAPILoadError(
                "cross-doc-schema-conflict",
                f"Schema {name!r} is defined with different content in "
                f"{prior[1]} and {doc.source_path}. Generated model files "
                f"are keyed by schema name, so both docs would fight over "
                f"one file. Rename one of them, or extract the shared "
                f"shape into a single file and $ref it from both.",
                source=doc.source_path,
                pointer=f"#/components/schemas/{name}",
            )


def load_swagger(
    api_directory: Path,
    *,
    schema_filter: SchemaFilterConfig | None = None,
) -> list[SwaggerDocument]:
    """Discover and parse every swagger doc under *api_directory*.

    JSON and YAML swagger files are accepted (YAML since 2026-07 — Q8
    lift; parsed in memory, never converted on disk). Non-swagger files
    of either flavor are silently skipped. Relative cross-file ``$ref``
    between files inside *api_directory* are resolved by a pre-parse
    merge layer (Q12 lift) — see :class:`_CrossFileRefResolver`.

    Top-level schemas emitted by more than one document must have
    identical bodies (the sync layer dedups, first doc in sorted order
    wins); differing bodies halt with ``cross-doc-schema-conflict``.

    *schema_filter* is the optional v2 path/schema filter. When omitted
    or :meth:`SchemaFilterConfig.is_active` returns False, every
    ``components.schemas.*`` entry is processed (v3 Phase 1 behavior).

    Returns a list of :class:`SwaggerDocument`, one per source file, in
    sorted-path order. Generators iterate this list.
    """
    if not api_directory.exists():
        return []

    sources: list[tuple[Path, dict[str, Any]]] = []
    for yml in sorted(api_directory.rglob("*.yaml")) + sorted(api_directory.rglob("*.yml")):
        # An unrelated YAML artifact sharing the api dir (another
        # workstream's contract, a doc) must be skipped like a non-swagger
        # JSON — otherwise one stray file hard-halts `jui build` for every
        # subproject that doesn't even consume it.
        if not is_swagger_yaml_file(yml):
            continue
        data = _safe_load_yaml(yml)
        if not isinstance(data, dict) or not ("openapi" in data or "swagger" in data):
            # The cheap regex prefilter can false-match `openapi:` inside
            # a comment or block scalar. After a real parse, a document
            # without a top-level swagger key is not a codegen input.
            continue
        _check_yaml_type_coercion(data, source=str(yml))
        sources.append((yml, data))
    for json_path in sorted(api_directory.rglob("*.json")):
        if not is_swagger_file(json_path):
            continue
        with open(json_path, "r", encoding="utf-8") as f:
            sources.append((json_path, json.load(f)))

    _check_duplicate_swagger_basenames([p for p, _ in sources])
    sources.sort(key=lambda pair: str(pair[0]))

    resolver = _CrossFileRefResolver(api_directory)
    registry: dict[str, tuple[str, str]] = {}
    docs: list[SwaggerDocument] = []
    for path, raw in sources:
        schemas_root = resolver.merge_into(raw, path)
        doc = parse_swagger(raw, str(path), schema_filter=schema_filter)
        _check_cross_doc_schemas(doc, schemas_root, registry)
        docs.append(doc)
    return docs


def parse_swagger(
    raw: dict[str, Any],
    source_path: str,
    *,
    schema_filter: SchemaFilterConfig | None = None,
) -> SwaggerDocument:
    """Parse one swagger dict into a :class:`SwaggerDocument`.

    Splits ``components.schemas`` into ``EnumDef`` (standalone enums) and
    ``SchemaDef`` (object schemas). Inline object schemas are extracted as
    derived ``SchemaDef`` with a synthesized name.

    When *schema_filter* is active, the kept schema set is computed
    **before** parsing — schemas outside the kept set are skipped entirely
    (their content never reaches the per-schema parser, so their
    polymorphic / shapeless / cyclic constructs do not trigger halts).
    This matches the v2 plan §2.2 "filter is lenient, parser is strict"
    contract.
    """
    # Resolve the kept set up front. When no filter is supplied or it's
    # inactive, the resulting set covers every schema name so the loop
    # below is a no-op filter.
    if schema_filter is not None and schema_filter.is_active():
        filter_result = apply_filter(raw, schema_filter)
        kept_schema_names: set[str] | None = set(filter_result.kept)
        filtered_out = filter_result.excluded
        skip_domain_overrides = filter_result.skip_domain_matches
    else:
        kept_schema_names = None  # sentinel: "keep everything"
        filtered_out = frozenset()
        # skip_domain may still be active in isolation — apply it against
        # all schema names so the generator can honor per-app overrides
        # without filtering anything else.
        if schema_filter is not None and schema_filter.skip_domain:
            filter_result = apply_filter(raw, schema_filter)
            skip_domain_overrides = filter_result.skip_domain_matches
        else:
            skip_domain_overrides = frozenset()
    info = raw.get("info", {}) if isinstance(raw, dict) else {}
    title = info.get("title", "") if isinstance(info, dict) else ""
    version = info.get("version", "") if isinstance(info, dict) else ""

    components = raw.get("components", {}) if "openapi" in raw else {}
    if "swagger" in raw and "definitions" in raw:
        # Swagger 2.0: definitions live at top level instead of components.schemas
        schemas_root = raw.get("definitions", {})
    else:
        schemas_root = (components or {}).get("schemas", {})

    if not isinstance(schemas_root, dict):
        return SwaggerDocument(source_path=source_path, title=title, version=version,
                               schemas=[], enums=[])

    schema_names = set(schemas_root.keys())
    enums: list[EnumDef] = []
    schemas: list[SchemaDef] = []
    unions: list[UnionDef] = []
    # Inline object schemas extracted on the fly — appended to `schemas`
    # after the main loop so post-processing (cycle / collision) sees them.
    inline_schemas: list[SchemaDef] = []
    inline_names: set[str] = set()

    for name, body in schemas_root.items():
        if not isinstance(body, dict):
            continue
        body = _fold_const(body)
        # Skip filtered-out schemas before any parse work (lenient filter).
        if kept_schema_names is not None and name not in kept_schema_names:
            continue
        pointer = f"#/components/schemas/{name}"
        if _is_enum_only(body):
            enums.append(_parse_enum(name, body, source_path=source_path, pointer=pointer))
            continue

        # Schema-level oneOf → top-level discriminated union (UnionDef).
        # Checked before allOf resolution / polymorphic halts: a top-level
        # oneOf body is the union envelope itself, not an object schema.
        if "oneOf" in body:
            unions.append(
                _parse_schema_level_union(
                    name,
                    body,
                    schemas_root,
                    top_level_names=schema_names,
                    source_path=source_path,
                    pointer=pointer,
                )
            )
            continue

        merged = _resolve_all_of(body, schemas_root, source_path=source_path, pointer=pointer)
        _check_polymorphic(merged, source_path=source_path, pointer=pointer)

        # Wrapper path: top-level non-object schemas (``type: string`` /
        # ``type: array`` / etc.) are emitted as single-field wrapper DTOs
        # with custom single-value (en|de)coders. Detected before
        # ``_check_object_typed`` because that helper only fires on
        # ``type: object`` and would silently allow ``type: string`` to
        # fall through into ``_extract_fields`` which returns empty fields.
        if _is_wrapper_schema(merged):
            wrapper_schema, wrapper_extras, wrapper_enums = _parse_wrapper_schema(
                name,
                merged,
                schema_names,
                inline_names,
                schemas_root=schemas_root,
                source_path=source_path,
                pointer=pointer,
            )
            for derived in wrapper_extras:
                inline_schemas.append(derived)
                inline_names.add(derived.name)
            for enum_def in wrapper_enums:
                if enum_def.name not in {e.name for e in enums}:
                    enums.append(enum_def)
            schemas.append(wrapper_schema)
            continue

        _check_object_typed(merged, source_path=source_path, pointer=pointer)

        fields, extra_inline, extra_enums = _extract_fields(
            merged,
            parent_name=name,
            top_level_names=schema_names,
            inline_names=inline_names,
            schemas_root=schemas_root,
            source_path=source_path,
            parent_pointer=pointer,
        )
        for derived in extra_inline:
            inline_schemas.append(derived)
            inline_names.add(derived.name)
        for enum_def in extra_enums:
            if enum_def.name in {e.name for e in enums}:
                # Same derived name re-derived from another field — both
                # cases produce identical enum cases by construction, so
                # silently dedupe.
                continue
            enums.append(enum_def)

        schemas.append(
            SchemaDef(
                name=name,
                fields=fields,
                description=_str_or_none(merged.get("description")),
                deprecated=bool(merged.get("deprecated", False)),
                skip_domain=bool(merged.get("x-jui-skip-domain", False)),
                source_pointer=f"{source_path}{pointer}",
                is_strict=merged.get("additionalProperties") is False,
                # Conformance flags computed after we know all field types.
                is_equatable=_all_equatable(fields),
                is_hashable=_all_hashable(fields),
                is_sendable=_all_sendable(fields),
            )
        )

    schemas.extend(inline_schemas)

    # oneOf discriminator: validate that each parent carrying a one_of
    # field actually declares a sibling property matching
    # ``discriminator.propertyName``. Catches typos in swagger early.
    for schema in schemas:
        for f in schema.fields:
            if f.type.is_one_of_ref and f.type.one_of is not None:
                disc_prop = f.type.one_of.discriminator_property
                if not any(g.wire_name == disc_prop for g in schema.fields):
                    raise OpenAPILoadError(
                        "oneof-discriminator-sibling-missing",
                        f"Schema {schema.name!r} field {f.wire_name!r} uses "
                        f"discriminator.propertyName={disc_prop!r} but no "
                        f"sibling property with that name exists in the "
                        f"parent schema. Add the property or fix the "
                        f"discriminator name.",
                        source=source_path,
                        pointer=schema.source_pointer,
                    )

    # Cycle detection — only direct self-reference without collection
    # indirection. Collection-mediated cycles are explicitly allowed (§3.3 / Q13).
    for schema in schemas:
        if schema.has_direct_self_reference():
            raise OpenAPILoadError(
                "direct-self-reference",
                f"Schema '{schema.name}' has a direct self-reference field "
                f"(no collection indirection). Wrap the field in an array "
                f"or map, or split into a non-recursive shape. This halt is "
                f"permanent: a value type cannot contain itself by value on "
                f"any target platform — the collection-indirection "
                f"workaround is the supported design.",
                source=source_path,
                pointer=schema.source_pointer,
            )

    return SwaggerDocument(
        source_path=source_path,
        title=title,
        version=version,
        schemas=schemas,
        enums=enums,
        filtered_out=filtered_out,
        skip_domain_overrides=skip_domain_overrides,
        unions=unions,
    )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _str_or_none(v: Any) -> str | None:
    if isinstance(v, str) and v.strip():
        return v
    return None


def _is_wrapper_schema(body: dict[str, Any]) -> bool:
    """True when a top-level schema body is a non-object primitive/array.

    These wire as bare values (``"hello"``, ``[1, 2, 3]``) — not JSON
    objects — so codegen has to emit a single-field wrapper with a
    custom single-value (en|de)coder rather than the normal object DTO.

    ``type: string|integer`` + ``enum`` is excluded because the
    enum-only branch handles it earlier in :func:`parse_swagger`. Bodies
    that have ``properties`` are excluded too (an object that happens
    to declare a ``type:`` is just a normal object).
    """
    t = body.get("type")
    if t not in ("string", "integer", "number", "boolean", "array"):
        return False
    if body.get("properties"):
        return False
    if t in ("string", "integer") and "enum" in body:
        return False
    return True


def _parse_wrapper_schema(
    name: str,
    body: dict[str, Any],
    top_level_names: set[str],
    inline_names: set[str],
    *,
    schemas_root: dict[str, Any],
    source_path: str,
    pointer: str,
) -> tuple[SchemaDef, list[SchemaDef], list[EnumDef]]:
    """Build a single-field wrapper :class:`SchemaDef` for a non-object schema.

    Reuses :func:`_field_type` to resolve primitives / arrays / inline
    derived schemas — anything the regular object path can emit. The
    synthesized field is named ``"items"`` for arrays and ``"value"`` for
    everything else; this is the property consumer code will see on the
    generated DTO (``dto.value`` / ``dto.items``).
    """
    wrapped_type, extra_inline, extra_enums = _field_type(
        body,
        parent_name=name,
        field_name="value",
        top_level_names=top_level_names,
        inline_names=inline_names,
        schemas_root=schemas_root,
        source_path=source_path,
        pointer=pointer,
    )
    field_name = "items" if wrapped_type.is_array else "value"
    field = FieldDef(
        wire_name=field_name,
        type=wrapped_type,
        required=True,
        description=None,
        deprecated=False,
        default=None,
        has_default=False,
    )
    fields = [field]
    schema = SchemaDef(
        name=name,
        fields=fields,
        description=_str_or_none(body.get("description")),
        deprecated=bool(body.get("deprecated", False)),
        skip_domain=bool(body.get("x-jui-skip-domain", False)),
        source_pointer=f"{source_path}{pointer}",
        is_strict=False,
        is_equatable=_all_equatable(fields),
        is_hashable=_all_hashable(fields),
        is_sendable=_all_sendable(fields),
        is_wrapper=True,
        wrapped_type=wrapped_type,
        wrapper_field_name=field_name,
    )
    return schema, list(extra_inline), list(extra_enums)


# Exact-type map (bool checked by identity before int via type(), so
# ``const: true`` infers boolean, not integer).
_CONST_INFERRED_TYPES = {str: "string", bool: "boolean",
                         int: "integer", float: "number"}


def _fold_const(body: dict[str, Any]) -> dict[str, Any]:
    """OpenAPI 3.1 ``const: X`` is the single-value constraint 3.0 spells
    ``enum: [X]``.

    openapi-diff already treats the two spellings as canonically equal
    (its normalizer folds const before comparing), so a docs author who
    writes const gets no drift finding — the IR has to derive the same
    types for both spellings or the checker's ruling and the generated
    DTOs disagree. Folding BEFORE classification gives const every enum
    behavior for free: same derived enum names, same standalone EnumDef,
    same (ignored) treatment on types with no enum support. A bare 3.1
    const (no ``type``) infers its type from the value instead of halting
    with an error that never mentions const. A co-declared enum is
    superseded — const is the narrower constraint. Values with no scalar
    type (null, arrays) are left alone for the existing halts.

    Returns a shallow copy; never mutates the caller's schema dict (the
    discriminator tag reader looks at the raw document).
    """
    if "const" not in body:
        return body
    value = body["const"]
    inferred = _CONST_INFERRED_TYPES.get(type(value))
    if inferred is None:
        return body
    folded = {k: v for k, v in body.items() if k != "const"}
    folded["enum"] = [value]
    folded.setdefault("type", inferred)
    return folded


def _is_enum_only(body: dict[str, Any]) -> bool:
    """True if *body* is a standalone enum (no nested properties).

    Heuristic: has ``enum`` AND has a primitive ``type`` (``string`` /
    ``integer``) AND has no ``properties``. Schemas like
    ``{"type": "string", "enum": [...]}`` qualify.
    """
    if "enum" not in body:
        return False
    if body.get("type") not in ("string", "integer"):
        return False
    if "properties" in body:
        return False
    return True


def _parse_enum(
    name: str,
    body: dict[str, Any],
    *,
    source_path: str,
    pointer: str,
) -> EnumDef:
    """Parse a standalone enum schema into :class:`EnumDef`.

    Honors ``x-enum-varnames`` (a non-standard but widely used extension)
    for case name overrides. Falls back to raw values (strings) or
    ``value_<N>`` for integers.
    """
    raw_values = body.get("enum", []) or []
    if not isinstance(raw_values, list):
        raise OpenAPILoadError(
            "invalid-enum",
            f"Enum '{name}' must be a list",
            source=source_path,
            pointer=pointer,
        )
    type_str = body.get("type")
    if type_str == "string":
        kind = PrimitiveKind.STRING
        string_values = [str(v) for v in raw_values]
        integer_values: list[int] = []
        default_case_names = string_values
    elif type_str == "integer":
        kind = PrimitiveKind.INTEGER
        try:
            integer_values = [int(v) for v in raw_values]
        except (TypeError, ValueError) as e:
            raise OpenAPILoadError(
                "invalid-enum",
                f"Integer enum '{name}' contains non-integer value: {e}",
                source=source_path,
                pointer=pointer,
            ) from e
        string_values = []
        default_case_names = [f"value_{v}" for v in integer_values]
    else:
        raise OpenAPILoadError(
            "invalid-enum",
            f"Enum '{name}' must declare type: string or type: integer "
            f"(got: {type_str})",
            source=source_path,
            pointer=pointer,
        )

    varnames = body.get("x-enum-varnames")
    if isinstance(varnames, list) and len(varnames) == len(raw_values):
        case_names = [str(v) for v in varnames]
    else:
        case_names = list(default_case_names)

    return EnumDef(
        name=name,
        kind=kind,
        case_names=case_names,
        string_values=string_values,
        integer_values=integer_values,
        description=_str_or_none(body.get("description")),
        deprecated=bool(body.get("deprecated", False)),
    )


def _resolve_all_of(
    body: dict[str, Any],
    schemas_root: dict[str, Any],
    *,
    source_path: str,
    pointer: str,
) -> dict[str, Any]:
    """Flatten ``allOf`` into a merged single-schema dict.

    Later items override earlier ones for ``properties`` (right-bias matches
    common OpenAPI tool behavior). ``required`` lists are unioned.
    """
    if "allOf" not in body:
        return body
    parts = body.get("allOf")
    if not isinstance(parts, list):
        return body

    merged: dict[str, Any] = {k: v for k, v in body.items() if k != "allOf"}
    merged_props: dict[str, Any] = dict(merged.get("properties") or {})
    merged_required: list[str] = list(merged.get("required") or [])

    for i, part in enumerate(parts):
        if isinstance(part, dict) and "$ref" in part:
            ref = part["$ref"]
            resolved = _resolve_ref_inline(
                ref, schemas_root,
                source_path=source_path,
                pointer=f"{pointer}/allOf/{i}",
            )
        else:
            resolved = part if isinstance(part, dict) else {}
        if not isinstance(resolved, dict):
            continue
        for k, v in (resolved.get("properties") or {}).items():
            merged_props[k] = v
        for r in (resolved.get("required") or []):
            if r not in merged_required:
                merged_required.append(r)

    merged["properties"] = merged_props
    merged["required"] = merged_required
    return merged


def _resolve_ref_inline(
    ref: str,
    schemas_root: dict[str, Any],
    *,
    source_path: str,
    pointer: str,
) -> dict[str, Any]:
    """Resolve a same-file ``$ref`` to its target dict.

    Multi-file refs (``./other.yaml#/Foo``) and URL refs halt — silent
    partial codegen is worse than explicit fail (§9.3, Q12).
    """
    _check_ref_local(ref, source_path=source_path, pointer=pointer)
    # Strip the leading "#/components/schemas/" (OpenAPI 3) or
    # "#/definitions/" (Swagger 2.0) prefix to get the bare name.
    if ref.startswith("#/components/schemas/"):
        name = ref[len("#/components/schemas/"):]
    elif ref.startswith("#/definitions/"):
        name = ref[len("#/definitions/"):]
    else:
        raise OpenAPILoadError(
            "unsupported-ref",
            f"Unsupported $ref shape: {ref!r}",
            source=source_path,
            pointer=pointer,
        )
    target = schemas_root.get(name)
    if not isinstance(target, dict):
        raise OpenAPILoadError(
            "ref-not-found",
            f"$ref target '{name}' not found in components.schemas",
            source=source_path,
            pointer=pointer,
        )
    return target


def _check_ref_local(ref: str, *, source_path: str, pointer: str) -> None:
    """Halt on multi-file / URL refs. Used by every ref resolution path."""
    if not isinstance(ref, str):
        raise OpenAPILoadError(
            "invalid-ref",
            "$ref must be a string",
            source=source_path,
            pointer=pointer,
        )
    if ref.startswith("#"):
        return
    # Anything with a file path component or scheme is multi-file/URL.
    # Cross-file refs between files inside the api directory are resolved
    # by the pre-parse merge layer in load_swagger, so by the time parsing
    # runs, one surviving here is either a URL ref or a parse_swagger call
    # that bypassed load_swagger.
    if ref.startswith(("http://", "https://", "./", "../", "/")) or ".yaml" in ref or ".yml" in ref or ".json" in ref:
        raise OpenAPILoadError(
            "multi-file-ref",
            f"Unresolved cross-file / URL $ref: {ref!r}. URL refs are not "
            f"supported — cross-file refs work only between files inside "
            f"the api directory (resolved when loading the directory).",
            source=source_path,
            pointer=pointer,
        )
    raise OpenAPILoadError(
        "unsupported-ref",
        f"Unrecognized $ref shape: {ref!r}",
        source=source_path,
        pointer=pointer,
    )


def _collect_one_of_ref_names(
    body: dict[str, Any],
    *,
    top_level_names: set[str],
    schemas_root: dict[str, Any],
    union_name: str | None,
    source_path: str,
    pointer: str,
) -> list[str]:
    """Validate a ``oneOf`` list and return variant names in declared order.

    Shared by the field-level and schema-level union parsers. Halts on:

    - non-list / empty ``oneOf``
    - inline (non-``$ref``) variants
    - refs that don't resolve to a top-level schema
    - variants that are themselves union schemas (their raw body carries
      ``oneOf`` / ``anyOf``) — ``union-variant-not-supported``, permanent:
      a union schema has no tag property of its own, so it cannot be
      selected by a discriminator value
    """
    one_of = body.get("oneOf")
    if not isinstance(one_of, list) or not one_of:
        raise OpenAPILoadError(
            "invalid-oneof",
            "'oneOf' must be a non-empty list of $ref objects",
            source=source_path,
            pointer=pointer,
        )
    names: list[str] = []
    for i, entry in enumerate(one_of):
        if not isinstance(entry, dict) or "$ref" not in entry or len(entry) != 1:
            raise OpenAPILoadError(
                "invalid-oneof",
                "Each oneOf entry must be a `$ref` object — inline variants "
                "are not supported in v1.",
                source=source_path,
                pointer=f"{pointer}/oneOf/{i}",
            )
        ref = entry["$ref"]
        _check_ref_local(ref, source_path=source_path, pointer=f"{pointer}/oneOf/{i}")
        ref_name = ref.rsplit("/", 1)[-1]
        if ref_name not in top_level_names:
            raise OpenAPILoadError(
                "oneof-variant-not-found",
                f"oneOf variant {ref_name!r} is not a top-level schema. "
                f"Inline / nested variants are not supported in v1.",
                source=source_path,
                pointer=f"{pointer}/oneOf/{i}",
            )
        variant_body = schemas_root.get(ref_name)
        if isinstance(variant_body, dict) and (
            "oneOf" in variant_body or "anyOf" in variant_body
        ):
            where = f"of union {union_name!r}" if union_name else "of this oneOf"
            raise OpenAPILoadError(
                "union-variant-not-supported",
                f"Schema {ref_name!r} is itself a union and cannot be a "
                f"variant {where}. A union schema carries no discriminator "
                f"tag property of its own, so nesting unions is structurally "
                f"unsupported (permanent). Flatten its variants into this "
                f"oneOf instead.",
                source=source_path,
                pointer=f"{pointer}/oneOf/{i}",
            )
        names.append(ref_name)
    return names


def _variant_tag_values(
    variant_name: str,
    disc_prop: str,
    schemas_root: dict[str, Any],
    *,
    source_path: str,
    pointer: str,
) -> tuple[list[str] | None, bool]:
    """Read a variant's internal tag declaration.

    Returns ``(values, non_string)`` where *values* is the list of string
    tag values the variant declares for *disc_prop* (via ``const`` or
    ``enum``), ``None`` when the variant declares no fixed tag value, and
    *non_string* is True when a fixed tag exists but is not a string
    (integer const/enum etc. — the OpenAPI mapping key space is strings,
    so non-string tags halt at the caller).

    ``allOf`` on the variant is resolved first so tags inherited from a
    base schema are visible.
    """
    body = schemas_root.get(variant_name)
    if not isinstance(body, dict):
        return None, False
    merged = _resolve_all_of(
        body, schemas_root, source_path=source_path, pointer=pointer
    )
    properties = merged.get("properties")
    if not isinstance(properties, dict):
        return None, False
    tag_body = properties.get(disc_prop)
    if not isinstance(tag_body, dict):
        return None, False
    if "const" in tag_body:
        value = tag_body["const"]
        if isinstance(value, str) and not isinstance(value, bool):
            return [value], False
        return None, True
    enum_values = tag_body.get("enum")
    if isinstance(enum_values, list) and enum_values:
        if all(
            isinstance(v, str) and not isinstance(v, bool) for v in enum_values
        ):
            return [str(v) for v in enum_values], False
        return None, True
    return None, False


def _parse_schema_level_union(
    name: str,
    body: dict[str, Any],
    schemas_root: dict[str, Any],
    *,
    top_level_names: set[str],
    source_path: str,
    pointer: str,
) -> UnionDef:
    """Parse a top-level ``oneOf`` schema into :class:`UnionDef`.

    Two mapping paths:

    - explicit ``discriminator.mapping`` — validated like the field-level
      parser, plus the ``discriminator-tag-conflict`` cross-check: when a
      variant internally declares the tag property with fixed values
      (const / enum), the mapped value must be among them
    - no mapping — inferred from each variant's internal tag property.
      Every variant must declare the tag as a ``const`` string or a
      single-value string enum; duplicates, non-string tags, and
      tag-less variants halt. The inferred mapping is printed as a
      WARNING on **stderr** (never stdout — the loader also runs inside
      MCP servers whose stdout is a protocol channel).
    """
    if "anyOf" in body:
        # Reuse the canonical anyOf freeze message.
        _check_polymorphic(body, source_path=source_path, pointer=pointer)
    if "discriminator" not in body:
        # Canonical 'oneOf without discriminator' halt.
        _check_polymorphic(body, source_path=source_path, pointer=pointer)
    if isinstance(body.get("properties"), dict) and body["properties"]:
        raise OpenAPILoadError(
            "invalid-oneof",
            f"Schema {name!r} mixes top-level 'oneOf' with 'properties'. "
            f"A schema-level union must be a pure envelope — move the "
            f"shared properties into the variants (or an allOf base they "
            f"share).",
            source=source_path,
            pointer=pointer,
        )
    disc = body.get("discriminator")
    if not isinstance(disc, dict):
        raise OpenAPILoadError(
            "invalid-discriminator",
            "'discriminator' must be a dict with 'propertyName'",
            source=source_path,
            pointer=pointer,
        )
    prop_name = disc.get("propertyName")
    if not isinstance(prop_name, str) or not prop_name.strip():
        raise OpenAPILoadError(
            "invalid-discriminator",
            "'discriminator.propertyName' must be a non-empty string",
            source=source_path,
            pointer=pointer,
        )

    variant_names = _collect_one_of_ref_names(
        body,
        top_level_names=top_level_names,
        schemas_root=schemas_root,
        union_name=name,
        source_path=source_path,
        pointer=pointer,
    )

    mapping = disc.get("mapping")
    if mapping is not None and not isinstance(mapping, dict):
        raise OpenAPILoadError(
            "invalid-discriminator",
            "'discriminator.mapping' must be a dict when present",
            source=source_path,
            pointer=pointer,
        )

    if mapping:
        variants = _union_variants_from_mapping(
            name,
            mapping,
            variant_names,
            disc_prop=prop_name,
            top_level_names=top_level_names,
            schemas_root=schemas_root,
            source_path=source_path,
            pointer=pointer,
        )
        inferred = False
    else:
        variants = _infer_union_variants(
            name,
            variant_names,
            disc_prop=prop_name,
            schemas_root=schemas_root,
            source_path=source_path,
            pointer=pointer,
        )
        inferred = True
        rendered = ", ".join(
            f"{v.discriminator_value} -> {v.ref_name}" for v in variants
        )
        print(
            f"  WARNING [api-model]: inferred discriminator mapping for "
            f"schema {name!r}: {rendered}. Add an explicit "
            f"discriminator.mapping to pin it.",
            file=sys.stderr,
        )

    return UnionDef(
        name=name,
        discriminator_property=prop_name,
        variants=tuple(variants),
        mapping_inferred=inferred,
        description=_str_or_none(body.get("description")),
        deprecated=bool(body.get("deprecated", False)),
        skip_domain=bool(body.get("x-jui-skip-domain", False)),
        source_pointer=f"{source_path}{pointer}",
    )


def _union_variants_from_mapping(
    union_name: str,
    mapping: dict[str, Any],
    variant_names: list[str],
    *,
    disc_prop: str,
    top_level_names: set[str],
    schemas_root: dict[str, Any],
    source_path: str,
    pointer: str,
) -> list[OneOfVariant]:
    """Validate an explicit schema-level mapping → ordered variants.

    Mirrors the field-level rules (string keys, local refs to top-level
    schemas, oneOf ↔ mapping set equality) and adds the
    ``discriminator-tag-conflict`` cross-check against variant-internal
    tags.
    """
    variants: list[OneOfVariant] = []
    mapped_refs: set[str] = set()
    for disc_value, ref in mapping.items():
        if not isinstance(disc_value, str) or not disc_value.strip():
            raise OpenAPILoadError(
                "invalid-discriminator",
                "discriminator.mapping keys must be non-empty strings",
                source=source_path,
                pointer=pointer,
            )
        if not isinstance(ref, str):
            raise OpenAPILoadError(
                "invalid-discriminator",
                f"discriminator.mapping[{disc_value!r}] must be a $ref string",
                source=source_path,
                pointer=pointer,
            )
        _check_ref_local(ref, source_path=source_path, pointer=pointer)
        ref_name = ref.rsplit("/", 1)[-1]
        if ref_name not in top_level_names:
            raise OpenAPILoadError(
                "oneof-variant-not-found",
                f"discriminator.mapping[{disc_value!r}] → {ref_name!r} is "
                f"not a top-level schema",
                source=source_path,
                pointer=pointer,
            )
        if ref_name not in variant_names:
            raise OpenAPILoadError(
                "discriminator-mapping-mismatch",
                f"discriminator.mapping[{disc_value!r}] points to {ref_name!r} "
                f"but this schema is not listed in the oneOf array. Add it "
                f"to oneOf or remove the mapping entry.",
                source=source_path,
                pointer=pointer,
            )
        tag_values, non_string = _variant_tag_values(
            ref_name, disc_prop, schemas_root,
            source_path=source_path, pointer=pointer,
        )
        if non_string:
            raise OpenAPILoadError(
                "discriminator-tag-conflict",
                f"Union {union_name!r}: variant {ref_name!r} declares "
                f"{disc_prop!r} with a non-string const/enum, but "
                f"discriminator values are strings (OpenAPI mapping keys "
                f"and platform switch dispatch are string-typed). Make the "
                f"tag a string.",
                source=source_path,
                pointer=pointer,
            )
        if tag_values is not None and disc_value not in tag_values:
            raise OpenAPILoadError(
                "discriminator-tag-conflict",
                f"Union {union_name!r}: discriminator.mapping says "
                f"{disc_value!r} → {ref_name!r}, but {ref_name!r} declares "
                f"{disc_prop!r} as {tag_values!r}. The mapped value must be "
                f"one of the variant's own tag values — fix the mapping or "
                f"the variant schema.",
                source=source_path,
                pointer=pointer,
            )
        variants.append(OneOfVariant(disc_value, ref_name))
        mapped_refs.add(ref_name)

    unmapped = set(variant_names) - mapped_refs
    if unmapped:
        raise OpenAPILoadError(
            "discriminator-mapping-mismatch",
            "oneOf variants are missing from discriminator.mapping: "
            + ", ".join(sorted(unmapped))
            + ". Add explicit mapping entries for each variant.",
            source=source_path,
            pointer=pointer,
        )
    return variants


def _infer_union_variants(
    union_name: str,
    variant_names: list[str],
    *,
    disc_prop: str,
    schemas_root: dict[str, Any],
    source_path: str,
    pointer: str,
) -> list[OneOfVariant]:
    """Infer the mapping from each variant's internal tag (oneOf order)."""
    variants: list[OneOfVariant] = []
    seen: dict[str, str] = {}
    for ref_name in variant_names:
        tag_values, non_string = _variant_tag_values(
            ref_name, disc_prop, schemas_root,
            source_path=source_path, pointer=pointer,
        )
        if non_string:
            raise OpenAPILoadError(
                "invalid-discriminator",
                f"Cannot infer discriminator.mapping for union "
                f"{union_name!r}: variant {ref_name!r} declares "
                f"{disc_prop!r} with a non-string const/enum. Tags must be "
                f"strings (OpenAPI mapping keys and platform switch "
                f"dispatch are string-typed).",
                source=source_path,
                pointer=pointer,
            )
        if tag_values is None:
            raise OpenAPILoadError(
                "invalid-discriminator",
                f"Cannot infer discriminator.mapping for union "
                f"{union_name!r}: variant {ref_name!r} does not declare "
                f"property {disc_prop!r} as a const string or string enum. "
                f"Declare the tag on the variant, or add an explicit "
                f"discriminator.mapping.",
                source=source_path,
                pointer=pointer,
            )
        if len(tag_values) != 1:
            raise OpenAPILoadError(
                "invalid-discriminator",
                f"Cannot infer discriminator.mapping for union "
                f"{union_name!r}: variant {ref_name!r} declares "
                f"{disc_prop!r} with {len(tag_values)} enum values "
                f"{tag_values!r} — inference needs exactly one value per "
                f"variant. Add an explicit discriminator.mapping.",
                source=source_path,
                pointer=pointer,
            )
        value = tag_values[0]
        if value in seen:
            raise OpenAPILoadError(
                "invalid-discriminator",
                f"Cannot infer discriminator.mapping for union "
                f"{union_name!r}: tag value {value!r} is declared by both "
                f"{seen[value]!r} and {ref_name!r}. Tag values must be "
                f"unique across variants.",
                source=source_path,
                pointer=pointer,
            )
        seen[value] = ref_name
        variants.append(OneOfVariant(value, ref_name))
    return variants


def _parse_one_of_discriminator(
    body: dict[str, Any],
    *,
    top_level_names: set[str],
    schemas_root: dict[str, Any],
    source_path: str,
    pointer: str,
) -> OneOfRef:
    """Parse ``{ oneOf: [...], discriminator: { propertyName, mapping } }``.

    Validates everything the v1 contract requires:

    - ``discriminator`` is a dict with non-empty ``propertyName`` (string)
    - ``mapping`` is a non-empty dict (explicit mapping stays required at
      field level — the tag is the parent's sibling property there, so
      variant-internal tag inference does not apply)
    - every mapping value is a same-file ``$ref`` to a top-level schema
    - every ``oneOf`` entry is itself a ``$ref`` (inline variants not
      supported)
    - no variant is itself a union schema (``union-variant-not-supported``)
    - the set of variants in ``oneOf`` matches the set of mapped refs

    Returns an :class:`OneOfRef` with variants in **mapping order** so
    generators emit deterministic ``case`` / ``when`` branches.
    """
    disc = body.get("discriminator")
    if not isinstance(disc, dict):
        raise OpenAPILoadError(
            "invalid-discriminator",
            "'discriminator' must be a dict with 'propertyName' and 'mapping'",
            source=source_path,
            pointer=pointer,
        )
    prop_name = disc.get("propertyName")
    if not isinstance(prop_name, str) or not prop_name.strip():
        raise OpenAPILoadError(
            "invalid-discriminator",
            "'discriminator.propertyName' must be a non-empty string",
            source=source_path,
            pointer=pointer,
        )
    mapping = disc.get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        raise OpenAPILoadError(
            "invalid-discriminator",
            "'discriminator.mapping' is required for a field-level oneOf "
            "(explicit map of discriminator value → variant $ref). Mapping "
            "inference from variant-internal tags applies only to "
            "schema-level unions, where the tag lives inside the payload.",
            source=source_path,
            pointer=pointer,
        )

    one_of_refs = _collect_one_of_ref_names(
        body,
        top_level_names=top_level_names,
        schemas_root=schemas_root,
        union_name=None,
        source_path=source_path,
        pointer=pointer,
    )

    # Parse mapping in declared order; validate each ref + cross-check.
    variants: list[OneOfVariant] = []
    mapped_refs: set[str] = set()
    for disc_value, ref in mapping.items():
        if not isinstance(disc_value, str) or not disc_value.strip():
            raise OpenAPILoadError(
                "invalid-discriminator",
                "discriminator.mapping keys must be non-empty strings",
                source=source_path,
                pointer=pointer,
            )
        if not isinstance(ref, str):
            raise OpenAPILoadError(
                "invalid-discriminator",
                f"discriminator.mapping[{disc_value!r}] must be a $ref string",
                source=source_path,
                pointer=pointer,
            )
        _check_ref_local(ref, source_path=source_path, pointer=pointer)
        ref_name = ref.rsplit("/", 1)[-1]
        if ref_name not in top_level_names:
            raise OpenAPILoadError(
                "oneof-variant-not-found",
                f"discriminator.mapping[{disc_value!r}] → {ref_name!r} is "
                f"not a top-level schema",
                source=source_path,
                pointer=pointer,
            )
        if ref_name not in one_of_refs:
            raise OpenAPILoadError(
                "discriminator-mapping-mismatch",
                f"discriminator.mapping[{disc_value!r}] points to {ref_name!r} "
                f"but this schema is not listed in the oneOf array. Add it "
                f"to oneOf or remove the mapping entry.",
                source=source_path,
                pointer=pointer,
            )
        variants.append(OneOfVariant(disc_value, ref_name))
        mapped_refs.add(ref_name)

    # Every oneOf entry must have a mapping (otherwise it's unreachable).
    unmapped = set(one_of_refs) - mapped_refs
    if unmapped:
        raise OpenAPILoadError(
            "discriminator-mapping-mismatch",
            "oneOf variants are missing from discriminator.mapping: "
            + ", ".join(sorted(unmapped))
            + ". Add explicit mapping entries for each variant.",
            source=source_path,
            pointer=pointer,
        )

    return OneOfRef(
        discriminator_property=prop_name,
        variants=tuple(variants),
    )


def _check_polymorphic(
    body: dict[str, Any],
    *,
    source_path: str,
    pointer: str,
    at_field_level: bool = False,
) -> None:
    """Halt on unsupported polymorphism.

    Allowed:
    - ``oneOf`` **with** ``discriminator`` — at field level (explicit
      mapping required, parsed in :func:`_field_type`) and at schema
      level (parsed into :class:`UnionDef` before this check runs, so a
      schema-level oneOf never reaches here)

    Halted (both permanent — see the freeze declarations in plan
    ``2026-07-24-v1-unsupported/02``):
    - ``anyOf`` — untagged union; there is no portable native
      representation across Swift / Kotlin / TypeScript
    - ``oneOf`` without ``discriminator`` — no way to dispatch
    - ``discriminator`` without ``oneOf`` — meaningless alone
    """
    if "anyOf" in body:
        raise OpenAPILoadError(
            "polymorphic-not-supported",
            "'anyOf' (untagged union) is not supported, permanently: "
            "there is no portable native representation across Swift / "
            "Kotlin / TypeScript codegen. Restructure the schema as "
            "'oneOf' with a discriminator tag instead.",
            source=source_path,
            pointer=pointer,
        )
    if "oneOf" in body and "discriminator" not in body:
        raise OpenAPILoadError(
            "polymorphic-not-supported",
            "'oneOf' without 'discriminator' is not supported. "
            "Add a discriminator block: at field level also provide an "
            "explicit mapping plus the sibling tag property; at schema "
            "level the mapping can be inferred when every variant declares "
            "the tag property as a const string or single-value string enum.",
            source=source_path,
            pointer=pointer,
        )
    if "discriminator" in body and "oneOf" not in body:
        raise OpenAPILoadError(
            "polymorphic-not-supported",
            "'discriminator' without 'oneOf' is meaningless. "
            "Either remove the discriminator or add a oneOf list of variants.",
            source=source_path,
            pointer=pointer,
        )


def _check_object_typed(body: dict[str, Any], *, source_path: str, pointer: str) -> None:
    """Halt on ``type: object`` schemas with no type information (§3.3).

    Only fires at the top-level schema body. Inline objects are checked
    individually when their parent field is parsed.
    """
    if body.get("type") != "object":
        return
    has_props = isinstance(body.get("properties"), dict) and body["properties"]
    has_typed_addl = isinstance(body.get("additionalProperties"), dict)
    addl_value = body.get("additionalProperties")
    has_strict_or_open = isinstance(addl_value, bool) or addl_value is None
    if has_props or has_typed_addl or "allOf" in body or "$ref" in body:
        return
    # additionalProperties: true / false / omitted with NO properties → schema
    # is shapeless; we'd emit an empty struct with no fields. Halt instead so
    # the user fixes the schema.
    if has_strict_or_open and not has_props:
        raise OpenAPILoadError(
            "object-without-type",
            "Schema declares 'type: object' but has no $ref / properties / "
            "typed additionalProperties. Add explicit field declarations or "
            "wait for v2 (which may treat this as `Map<String, Any>`).",
            source=source_path,
            pointer=pointer,
        )


def _extract_fields(
    body: dict[str, Any],
    *,
    parent_name: str,
    top_level_names: set[str],
    inline_names: set[str],
    schemas_root: dict[str, Any],
    source_path: str,
    parent_pointer: str,
) -> tuple[list[FieldDef], list[SchemaDef], list[EnumDef]]:
    """Extract :class:`FieldDef` list + inline-derived schemas + inline enums.

    Walks ``properties`` in declaration order. For each property:

    - ``$ref`` → object/enum reference (resolution decided at IR consumption
      time since we don't yet know if the target is enum or object)
    - field-level ``allOf: [{$ref}]`` (common nullable/default-wrapping
      idiom in OpenAPI 3) → unwrapped to the ref'd type
    - inline ``type: object`` with ``properties`` → derive a child schema
      named ``{ParentName}{FieldPascal}``, halt on collision with top-level
    - inline ``type: string | integer`` + ``enum`` → derive a top-level
      enum named the same way, append to ``extra_enums``
    - ``array`` / typed-map / primitives → straightforward
    """
    properties = body.get("properties") or {}
    required_set = set(body.get("required") or [])
    fields: list[FieldDef] = []
    extra_inline: list[SchemaDef] = []
    extra_enums: list[EnumDef] = []

    if not isinstance(properties, dict):
        return fields, extra_inline, extra_enums

    for prop_name, prop_body in properties.items():
        if not isinstance(prop_body, dict):
            continue
        prop_pointer = f"{parent_pointer}/properties/{prop_name}"
        ftype, derived, enums = _field_type(
            prop_body,
            parent_name=parent_name,
            field_name=prop_name,
            top_level_names=top_level_names,
            inline_names=inline_names,
            schemas_root=schemas_root,
            source_path=source_path,
            pointer=prop_pointer,
        )
        extra_inline.extend(derived)
        extra_enums.extend(enums)
        is_required = prop_name in required_set
        ftype_with_null = FieldType(
            **{**ftype.__dict__, "nullable": (not is_required) or bool(prop_body.get("nullable"))}
        )
        fields.append(
            FieldDef(
                wire_name=prop_name,
                type=ftype_with_null,
                required=is_required,
                description=_str_or_none(prop_body.get("description")),
                deprecated=bool(prop_body.get("deprecated", False)),
                default=prop_body.get("default") if "default" in prop_body else None,
                has_default="default" in prop_body,
            )
        )
    return fields, extra_inline, extra_enums


def _field_type(
    body: dict[str, Any],
    *,
    parent_name: str,
    field_name: str,
    top_level_names: set[str],
    inline_names: set[str],
    schemas_root: dict[str, Any],
    source_path: str,
    pointer: str,
) -> tuple[FieldType, list[SchemaDef], list[EnumDef]]:
    """Resolve a single property's type to :class:`FieldType`.

    Returns the type + any inline-derived schemas + any inline-derived enums
    (transitively, since nested inline objects can themselves contain inline
    objects/enums).
    """
    body = _fold_const(body)
    _check_polymorphic(body, source_path=source_path, pointer=pointer, at_field_level=True)

    # 1pre. ``oneOf`` + ``discriminator`` with explicit ``mapping`` →
    # discriminated union. The parent schema's field becomes a tagged enum;
    # generators emit a custom Codable / KSerializer / discriminated union
    # type and dispatch on the sibling property named in ``discriminator``.
    if "oneOf" in body and "discriminator" in body:
        one_of = _parse_one_of_discriminator(
            body,
            top_level_names=top_level_names,
            schemas_root=schemas_root,
            source_path=source_path,
            pointer=pointer,
        )
        return (
            FieldType(is_one_of_ref=True, one_of=one_of),
            [],
            [],
        )

    # 1a. Field-level ``allOf: [{$ref: X}]`` is the OpenAPI 3 idiom for adding
    # nullable / default / description to a $ref'd type. Unwrap it to the
    # underlying ref so the field is just a reference.
    if isinstance(body.get("allOf"), list) and len(body["allOf"]) == 1:
        only = body["allOf"][0]
        if isinstance(only, dict) and "$ref" in only and len(only) == 1:
            ref = only["$ref"]
            _check_ref_local(ref, source_path=source_path, pointer=pointer)
            ref_name = ref.rsplit("/", 1)[-1]
            return (
                FieldType(is_object_ref=True, ref_name=ref_name),
                [],
                [],
            )

    # 1. $ref → another schema
    if "$ref" in body:
        ref = body["$ref"]
        _check_ref_local(ref, source_path=source_path, pointer=pointer)
        ref_name = ref.rsplit("/", 1)[-1]
        return (
            FieldType(is_object_ref=True, ref_name=ref_name),
            [],
            [],
        )

    type_str = body.get("type")

    # 2. array<T>
    if type_str == "array":
        items = body.get("items")
        if not isinstance(items, dict):
            raise OpenAPILoadError(
                "invalid-array",
                f"'array' field '{field_name}' is missing 'items'",
                source=source_path,
                pointer=pointer,
            )
        element_type, derived, derived_enums = _field_type(
            items,
            parent_name=parent_name,
            field_name=field_name + "_item",
            top_level_names=top_level_names,
            inline_names=inline_names,
            schemas_root=schemas_root,
            source_path=source_path,
            pointer=f"{pointer}/items",
        )
        return (
            FieldType(is_array=True, element=element_type),
            derived,
            derived_enums,
        )

    # 3. object
    if type_str == "object" or "properties" in body or "additionalProperties" in body:
        # 3a. typed additionalProperties → map
        addl = body.get("additionalProperties")
        if isinstance(addl, dict):
            value_type, derived, derived_enums = _field_type(
                addl,
                parent_name=parent_name,
                field_name=field_name + "_value",
                top_level_names=top_level_names,
                inline_names=inline_names,
                schemas_root=schemas_root,
                source_path=source_path,
                pointer=f"{pointer}/additionalProperties",
            )
            return (
                FieldType(is_map=True, element=value_type),
                derived,
                derived_enums,
            )

        # 3b. inline object with properties → derive a child schema
        if isinstance(body.get("properties"), dict) and body["properties"]:
            derived_name = body.get("x-jui-name") or f"{parent_name}{_pascal(field_name)}"
            if derived_name in top_level_names:
                raise OpenAPILoadError(
                    "inline-name-collision",
                    f"Inline object at {pointer} would be named '{derived_name}' "
                    f"but a top-level schema with that name already exists. "
                    f"Set 'x-jui-name' on the inline schema or extract it to "
                    f"components.schemas.",
                    source=source_path,
                    pointer=pointer,
                )
            if derived_name in inline_names:
                raise OpenAPILoadError(
                    "inline-name-collision",
                    f"Inline object at {pointer} resolves to '{derived_name}' "
                    f"but the same name was already derived elsewhere. "
                    f"Set 'x-jui-name' to disambiguate.",
                    source=source_path,
                    pointer=pointer,
                )
            inline_fields, transitive, transitive_enums = _extract_fields(
                body,
                parent_name=derived_name,
                top_level_names=top_level_names,
                inline_names=inline_names | {derived_name},
                schemas_root=schemas_root,
                source_path=source_path,
                parent_pointer=pointer,
            )
            derived_schema = SchemaDef(
                name=derived_name,
                fields=inline_fields,
                description=_str_or_none(body.get("description")),
                deprecated=bool(body.get("deprecated", False)),
                skip_domain=bool(body.get("x-jui-skip-domain", False)),
                source_pointer=f"{source_path}{pointer}",
                is_strict=body.get("additionalProperties") is False,
                is_equatable=_all_equatable(inline_fields),
                is_hashable=_all_hashable(inline_fields),
                is_sendable=_all_sendable(inline_fields),
            )
            return (
                FieldType(is_object_ref=True, ref_name=derived_name),
                [derived_schema] + transitive,
                transitive_enums,
            )

        # 3c. additionalProperties: true / false / omitted on an inline object
        # → silently drop extras, but field has no shape → halt
        if not body.get("properties"):
            raise OpenAPILoadError(
                "object-without-type",
                f"Inline object at {pointer} has no 'properties' and no "
                f"typed 'additionalProperties'. Add field declarations or "
                f"use $ref.",
                source=source_path,
                pointer=pointer,
            )

    # 4. inline enum (string or integer) — derive a top-level enum named
    # ``{ParentName}{FieldPascal}`` (or ``x-jui-name`` override). Matches the
    # inline-object treatment.
    if type_str in ("string", "integer") and "enum" in body:
        derived_name = body.get("x-jui-name") or f"{parent_name}{_pascal(field_name)}"
        if derived_name in top_level_names:
            raise OpenAPILoadError(
                "inline-name-collision",
                f"Inline enum at {pointer} would be named '{derived_name}' "
                f"but a top-level schema with that name already exists. "
                f"Set 'x-jui-name' on the inline enum or extract it to "
                f"components.schemas.",
                source=source_path,
                pointer=pointer,
            )
        enum_def = _parse_enum(derived_name, body, source_path=source_path, pointer=pointer)
        return (
            FieldType(is_enum_ref=True, ref_name=derived_name),
            [],
            [enum_def],
        )

    # 5. primitives
    if type_str == "string":
        # Retain the recognized string format hints (plan 03). Unrecognized
        # formats (email, hostname, custom …) stay plain STRING with no
        # side channel — v1 maps only the three unambiguous ones.
        fmt = body.get("format")
        retained_fmt = fmt if fmt in _RETAINED_STRING_FORMATS else None
        return (
            FieldType(
                is_primitive=True,
                primitive=PrimitiveKind.STRING,
                format=retained_fmt,
            ),
            [],
            [],
        )
    if type_str == "boolean":
        return (
            FieldType(is_primitive=True, primitive=PrimitiveKind.BOOLEAN),
            [],
            [],
        )
    if type_str == "integer":
        fmt = body.get("format")
        if fmt == "int32":
            kind = PrimitiveKind.INTEGER_32
        elif fmt == "int64":
            kind = PrimitiveKind.INTEGER_64
        else:
            kind = PrimitiveKind.INTEGER
        return FieldType(is_primitive=True, primitive=kind), [], []
    if type_str == "number":
        fmt = body.get("format")
        if fmt == "float":
            return FieldType(is_primitive=True, primitive=PrimitiveKind.FLOAT), [], []
        return FieldType(is_primitive=True, primitive=PrimitiveKind.DOUBLE), [], []

    raise OpenAPILoadError(
        "unknown-type",
        f"Field at {pointer} has unrecognized type {type_str!r}",
        source=source_path,
        pointer=pointer,
    )


# String formats retained on FieldType.format (plan 03 — format-aware
# mapping). Kept to the three formats whose native mapping is unambiguous
# on every platform; everything else is intentionally discarded.
_RETAINED_STRING_FORMATS = ("date-time", "uuid", "binary")


_PASCAL_RE = re.compile(r"(?:^|[_\s-])([a-z0-9])")
_TRAILING_CASE_RE = re.compile(r"[^A-Za-z0-9]+")


def _pascal(s: str) -> str:
    """Convert wire name (snake_case / kebab-case / camelCase) to PascalCase.

    Examples:
        ``display_name`` → ``DisplayName``
        ``user-id`` → ``UserId``
        ``displayName`` → ``DisplayName``
    """
    if not s:
        return s
    cleaned = _TRAILING_CASE_RE.sub("_", s)
    parts = [p for p in cleaned.split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _all_equatable(fields: list[FieldDef]) -> bool:
    """All field types support equality (no ``Any`` leakage).

    In v1 we halt on oneOf/anyOf, so ``Any`` shouldn't actually appear.
    Kept as a flag for future-proofing when v2 adds polymorphic types.
    """
    return True


def _all_hashable(fields: list[FieldDef]) -> bool:
    """All field types are hashable.

    Typed maps break Hashable on Swift (``[String: T]`` is Hashable only
    when ``T: Hashable`` — usually true for primitive values, but we
    conservatively drop Hashable when any field is a map to avoid an
    obscure compile error in consumer code).
    """
    for f in fields:
        if f.type.is_map:
            return False
        if f.type.is_array and f.type.element and f.type.element.is_map:
            return False
    return True


def _all_sendable(fields: list[FieldDef]) -> bool:
    """All field types are Sendable.

    In v1, every emitted type is a value type or a primitive, so this is
    trivially True. The flag exists so a future v2 introducing class-typed
    DTOs can downgrade conformance per schema.
    """
    return True
