"""Path / schema filter for swagger codegen.

Implements the v2 path-filter plan: walk ``paths.*`` of a raw swagger dict,
keep endpoints matching ``include_paths`` minus ``exclude_paths``, follow
``$ref`` transitively through requestBody / responses / parameters and the
``components.{parameters, responses, requestBodies, headers}`` shared
definitions, then apply ``include_schemas`` (union) and ``exclude_schemas``
(set-difference). Returns the set of schema names to keep.

Lenient on polymorphism: ``oneOf`` / ``anyOf`` branches inside ``paths.*``
do **not** halt — every branch's $ref is collected. The strict halt for
``oneOf`` lives in :mod:`openapi_loader` and only fires when the construct
appears inside ``components.schemas.*``.

Glob semantics (v2 §2.3):

- ``*`` matches any string including ``/`` (no special ``**``)
- Patterns are case-sensitive on both paths and schema names
- Implementation uses ``fnmatch.translate`` for portability
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import translate
from typing import Any, Iterable


@dataclass(frozen=True)
class SchemaFilterConfig:
    """Resolved ``api.schemas.*`` block from ``jui.config.json``.

    ``[]`` (empty list) and missing key are treated as equivalent — both
    mean "filter not in effect for this dimension" (v2 §2.4).

    Attributes:
        include_paths: glob patterns; empty = no path restriction (all
            endpoints kept as the initial set before exclude_paths is applied)
        exclude_paths: glob patterns; matched endpoints are removed from
            the initial set
        include_schemas: schema-name glob patterns added to the set after
            path resolution (used for shared schemas not reachable from
            any included path)
        exclude_schemas: schema-name glob patterns; matching schemas are
            removed from the final set after all other steps
        skip_domain: schema-name glob patterns; consumed by the generator
            layer to decide which schemas skip Domain scaffold emission
            (OR-evaluated with per-schema ``x-jui-skip-domain``)
    """

    include_paths: tuple[str, ...] = ()
    exclude_paths: tuple[str, ...] = ()
    include_schemas: tuple[str, ...] = ()
    exclude_schemas: tuple[str, ...] = ()
    skip_domain: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "SchemaFilterConfig":
        """Build from a ``jui.config.json`` ``api.schemas`` block.

        Missing keys, ``None``, and ``[]`` all collapse to empty tuple
        (the "filter not in effect" sentinel). Non-list values are
        coerced to a single-element tuple so users can write
        ``"include_paths": "/api/*"`` as well as a list — minor
        ergonomic concession matching how config_manager handles
        scalar-or-list elsewhere.
        """
        if not isinstance(raw, dict):
            return cls()
        def _tuple(key: str) -> tuple[str, ...]:
            v = raw.get(key)
            if v is None or v == []:
                return ()
            if isinstance(v, str):
                return (v,)
            if isinstance(v, (list, tuple)):
                return tuple(str(x) for x in v if isinstance(x, (str,)))
            return ()
        return cls(
            include_paths=_tuple("include_paths"),
            exclude_paths=_tuple("exclude_paths"),
            include_schemas=_tuple("include_schemas"),
            exclude_schemas=_tuple("exclude_schemas"),
            skip_domain=_tuple("skip_domain"),
        )

    def is_active(self) -> bool:
        """True if any filter dimension is set.

        When False, the loader should bypass filtering entirely and treat
        every ``components.schemas.*`` entry as kept (backwards compatible
        with v3 Phase 1).
        """
        return any((
            self.include_paths,
            self.exclude_paths,
            self.include_schemas,
            self.exclude_schemas,
        ))


@dataclass(frozen=True)
class FilterResult:
    """Outcome of :func:`apply_filter`.

    Carries both the kept set and the excluded set so the caller can log
    the filtered-out names for the user (§2.5).

    ``skip_domain_matches`` is the resolved subset of ``kept`` that the
    Domain scaffold emitter should skip — pre-computed here so the
    generator layer doesn't have to repeat glob evaluation.
    """

    kept: frozenset[str]
    excluded: frozenset[str]
    skip_domain_matches: frozenset[str] = field(default_factory=frozenset)


def apply_filter(
    raw_swagger: dict[str, Any],
    config: SchemaFilterConfig,
) -> FilterResult:
    """Compute the schema set to keep for *raw_swagger* under *config*.

    Algorithm (v2 §2.1):

    1. Enumerate ``paths.*``
    2. Apply ``include_paths`` (initial set = all when empty) ∖ ``exclude_paths``
    3. Transitively resolve ``$ref`` from kept endpoints + shared components
    4. Union with ``include_schemas`` (and their transitive closure)
    5. Subtract ``exclude_schemas``
    6. Compute ``skip_domain`` matches from the final kept set

    When :meth:`SchemaFilterConfig.is_active` returns False, returns the
    complete ``components.schemas.*`` set unchanged (with ``skip_domain``
    glob still resolved against it).
    """
    schemas_root = _schemas_root(raw_swagger)
    all_schema_names = frozenset(schemas_root.keys())

    if not config.is_active():
        # No path/schema filter — keep everything. Domain skip still applies.
        kept = all_schema_names
        skip_dom = _glob_match_set(kept, config.skip_domain)
        return FilterResult(kept=kept, excluded=frozenset(), skip_domain_matches=skip_dom)

    # Step 1-2: enumerate paths and apply path-level glob filter.
    surviving_endpoints = _filter_endpoints(raw_swagger, config)

    # Step 3: transitively follow $ref from kept endpoints + shared components.
    seed_refs = _collect_endpoint_refs(surviving_endpoints, raw_swagger)
    reachable = _transitive_resolve(seed_refs, raw_swagger)

    # Step 4: union with include_schemas (and their transitive closure).
    if config.include_schemas:
        named = _glob_match_set(all_schema_names, config.include_schemas)
        named_closure = _transitive_resolve(named, raw_swagger)
        reachable = reachable | named_closure

    # Step 5: subtract exclude_schemas.
    if config.exclude_schemas:
        dropped = _glob_match_set(reachable, config.exclude_schemas)
        reachable = reachable - dropped

    # Restrict to names that actually exist in components.schemas.*. Refs
    # to components.parameters / responses / etc. were used for traversal
    # but only schema names are emit candidates.
    kept = frozenset(reachable & all_schema_names)
    excluded = all_schema_names - kept

    # Step 6: pre-compute Domain-skip set.
    skip_dom = _glob_match_set(kept, config.skip_domain)

    return FilterResult(kept=kept, excluded=excluded, skip_domain_matches=skip_dom)


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _schemas_root(raw: dict[str, Any]) -> dict[str, Any]:
    """Return ``components.schemas`` (OpenAPI 3) or ``definitions`` (Swagger 2.0)."""
    if "openapi" in raw:
        return (raw.get("components") or {}).get("schemas", {}) or {}
    if "swagger" in raw:
        return raw.get("definitions", {}) or {}
    return {}


def _filter_endpoints(
    raw: dict[str, Any],
    config: SchemaFilterConfig,
) -> list[dict[str, Any]]:
    """Return the list of endpoint operation objects that survive path filter.

    Each entry is a dict containing the operation body (``get`` / ``post``
    / etc.). Path-level parameters are included as a synthetic
    ``__path_parameters__`` key so the ref collector picks them up too.
    """
    paths = raw.get("paths") or {}
    if not isinstance(paths, dict):
        return []

    include_re = _compile_globs(config.include_paths) if config.include_paths else None
    exclude_re = _compile_globs(config.exclude_paths) if config.exclude_paths else None

    method_keys = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}
    surviving: list[dict[str, Any]] = []
    for path_str, path_item in paths.items():
        if not isinstance(path_str, str) or not isinstance(path_item, dict):
            continue
        if include_re is not None and not include_re.match(path_str):
            continue
        if exclude_re is not None and exclude_re.match(path_str):
            continue
        # Path-level shared parameters apply to every operation under this path.
        path_level_params = path_item.get("parameters") or []
        for method, op in path_item.items():
            if method not in method_keys or not isinstance(op, dict):
                continue
            entry = dict(op)
            if path_level_params:
                entry["__path_parameters__"] = path_level_params
            surviving.append(entry)
    return surviving


def _collect_endpoint_refs(
    endpoints: Iterable[dict[str, Any]],
    raw: dict[str, Any],
) -> set[str]:
    """Walk operation bodies to collect every ``$ref`` target name.

    Lenient on polymorphism (v2 §2.2): walks into ``oneOf`` / ``anyOf``
    / ``allOf`` branches without halting and adds each branch's $ref.
    """
    out: set[str] = set()
    for op in endpoints:
        # parameters (operation level + path level merged)
        for p in op.get("parameters") or []:
            _walk_refs(p, out)
        for p in op.get("__path_parameters__") or []:
            _walk_refs(p, out)
        # requestBody
        rb = op.get("requestBody")
        if isinstance(rb, dict):
            _walk_refs(rb, out)
        # responses
        responses = op.get("responses")
        if isinstance(responses, dict):
            for r in responses.values():
                _walk_refs(r, out)
    return out


_REF_PREFIXES = (
    "#/components/schemas/",
    "#/components/parameters/",
    "#/components/responses/",
    "#/components/requestBodies/",
    "#/components/headers/",
    # Swagger 2.0
    "#/definitions/",
    "#/parameters/",
    "#/responses/",
)


def _walk_refs(node: Any, out: set[str]) -> None:
    """Recursively collect ``$ref`` target tail names from *node*.

    Picks up refs into any of the OpenAPI 3 / Swagger 2 component
    namespaces — the transitive_resolve step decides what to do with
    each kind. Adding e.g. ``Foo`` from ``#/components/requestBodies/Foo``
    lets the resolver follow into ``components.requestBodies.Foo.content.*.schema``
    on the next iteration.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            for prefix in _REF_PREFIXES:
                if ref.startswith(prefix):
                    out.add(_qualify_ref(prefix, ref[len(prefix):]))
                    return
        for v in node.values():
            _walk_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_refs(v, out)


def _qualify_ref(prefix: str, tail: str) -> str:
    """Prefix the bare ref name with a namespace tag so resolver knows
    where to look. ``schemas/User`` vs ``parameters/PageSize`` vs ...

    Schemas are the only kind we ultimately emit, but the others are
    needed as traversal intermediates.
    """
    # Normalize OpenAPI 3 + Swagger 2 to the same internal tag set.
    if prefix in ("#/components/schemas/", "#/definitions/"):
        return f"schemas/{tail}"
    if prefix in ("#/components/parameters/", "#/parameters/"):
        return f"parameters/{tail}"
    if prefix in ("#/components/responses/", "#/responses/"):
        return f"responses/{tail}"
    if prefix == "#/components/requestBodies/":
        return f"requestBodies/{tail}"
    if prefix == "#/components/headers/":
        return f"headers/{tail}"
    return f"schemas/{tail}"  # fallback


def _transitive_resolve(
    seed: set[str] | frozenset[str],
    raw: dict[str, Any],
) -> set[str]:
    """Expand *seed* by following every ``$ref`` reachable from each member.

    Iterates to a fixed point. Cycles are handled by tracking visited
    names — the same v3 plan §3.3 mechanism that already protects
    parse_swagger from infinite loops.

    Input *seed* may contain plain schema names (no namespace tag) — those
    are auto-tagged as ``schemas/<name>``. This makes
    :func:`apply_filter`'s ``include_schemas`` step easy to wire in.
    """
    # Normalize seed: bare names become schemas/<name>; tagged names pass through.
    queue: list[str] = []
    for item in seed:
        if "/" in item:
            queue.append(item)
        else:
            queue.append(f"schemas/{item}")

    visited: set[str] = set()
    out_schemas: set[str] = set()

    components = (raw.get("components") or {}) if "openapi" in raw else {}
    swagger2_root = raw  # Swagger 2.0 puts components at the root

    while queue:
        tagged = queue.pop()
        if tagged in visited:
            continue
        visited.add(tagged)
        kind, _, name = tagged.partition("/")

        # Resolve the node body for this kind.
        node = _lookup_component(kind, name, components, swagger2_root, raw)
        if node is None:
            continue

        if kind == "schemas":
            out_schemas.add(name)

        # Walk the node's own refs to seed the next iteration.
        nested: set[str] = set()
        _walk_refs(node, nested)
        for ref in nested:
            if ref not in visited:
                queue.append(ref)

    return out_schemas


def _lookup_component(
    kind: str,
    name: str,
    components: dict[str, Any],
    swagger2_root: dict[str, Any],
    raw: dict[str, Any],
) -> Any:
    """Return the component dict for ``<kind>/<name>`` or None.

    OpenAPI 3 reads from ``components.<kind>s``; Swagger 2.0 from the
    top-level keys (``definitions``, ``parameters``, ``responses``).
    """
    if kind == "schemas":
        if "openapi" in raw:
            return (components.get("schemas") or {}).get(name)
        return (swagger2_root.get("definitions") or {}).get(name)
    if kind == "parameters":
        if "openapi" in raw:
            return (components.get("parameters") or {}).get(name)
        return (swagger2_root.get("parameters") or {}).get(name)
    if kind == "responses":
        if "openapi" in raw:
            return (components.get("responses") or {}).get(name)
        return (swagger2_root.get("responses") or {}).get(name)
    if kind == "requestBodies":
        return (components.get("requestBodies") or {}).get(name)
    if kind == "headers":
        return (components.get("headers") or {}).get(name)
    return None


# --------------------------------------------------------------------------- #
# Glob helpers
# --------------------------------------------------------------------------- #


def _compile_globs(patterns: Iterable[str]) -> re.Pattern[str]:
    """Compile *patterns* into a single case-sensitive regex.

    ``*`` matches any characters including ``/`` (per v2 §2.3) — this is
    achieved by feeding the pattern through ``fnmatch.translate`` and
    leveraging Python's default behavior where ``*`` becomes ``.*`` in
    the translated regex.
    """
    parts = [translate(p) for p in patterns]
    combined = "|".join(parts) if parts else "(?!.*)"  # never-match if empty
    return re.compile(combined)


def _glob_match_set(
    candidates: Iterable[str],
    patterns: Iterable[str],
) -> frozenset[str]:
    """Return the subset of *candidates* matching at least one *patterns* glob.

    Empty *patterns* yields an empty result — the caller decides whether
    that means "do nothing" (skip_domain / exclude) or "match all" (the
    latter shape isn't used here, by design).
    """
    plist = tuple(patterns)
    if not plist:
        return frozenset()
    regex = _compile_globs(plist)
    return frozenset(c for c in candidates if regex.match(c))
