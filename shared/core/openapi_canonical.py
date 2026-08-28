"""Resolution of `@canonical` references in a spec's dataFlow.

A spec method that names an `endpoint` is already pointing at an operation in
the API canon. Writing its `params` and `returnType` out by hand copies what
the canon already says: measured across four consumer faces, 320 declarations
name an endpoint, 318 resolve, and 205 of those (64%) carry a parameter list
that is derivable from the operation — 138 of them differing only in naming
convention (`venueId` where the canon says `venue_id`).

So the reference is spelled instead of the copy:

    { "name": "getBookmarks",
      "endpoint": "GET /api/user/bookmarks",
      "params": "@canonical" }

and where the canon cannot say it, or should not, the value is written
directly as before. The two mix in one list, which is the point — a method may
take everything the operation declares plus a client-side callback that no
OpenAPI document will ever contain:

    "params": ["@canonical", {"name": "onProgress", "type": "((Int) -> Void)?"}]

Absence is NOT the reference. `params` is already absent on five declarations
in the corpus and means "no parameters" there; a mark that has to be written
cannot be confused with a field nobody filled in.

`returnType` is deliberately not `@canonical`. A spec's return type is the
domain type and the canon's is the wire type, and they legitimately differ —
`[ItemSummary]` against `ItemSearchResponse`, `UserProfile` against
`UserProfileResponse`. Only `@canonical.wire`, which says "the wire type is
what I mean", lifts it.

This module is the single implementation. `jsonui-doc` validates specs and
`jui build` generates repository stubs from the same fields; resolving the
mark in each would be two answers to one question, and they would drift.
Loaded from the installed tool tree the same way `attribute_definitions.json`
is — see `load_openapi_canonical()` in either tool.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CANONICAL_MARKER = "@canonical"
CANONICAL_WIRE_MARKER = "@canonical.wire"

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

#: `GET /api/venues/{venue_id}` — the verb is not constrained to HTTP here.
#: Non-HTTP transports (RTDB, WebSocket, GraphQL) are declared the same way and
#: are legal; they simply never resolve, and asking for `@canonical` on one is
#: an error the caller reports rather than something this module guesses at.
ENDPOINT_RE = re.compile(r"^(\w+)\s+(\S+)$")

_PATH_VAR_RE = re.compile(r"\{[^}]*\}")
#: `:itemId` — a third notation, three declarations of it in the corpus.
_COLON_VAR_RE = re.compile(r"(?<=/):[A-Za-z_][A-Za-z0-9_]*")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<!^)(?=[A-Z])")


# --------------------------------------------------------------------------- #
# naming
# --------------------------------------------------------------------------- #

def to_snake(name: str) -> str:
    return _CAMEL_BOUNDARY_RE.sub("_", name).lower().replace("__", "_")


def to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest if p)


#: `spec.canonical_param_case` in jui.config.json. Defaults to `asIs` — the
#: canon's own spelling — because a default that renamed would rewrite 43% of
#: the corpus's parameter names the first time a project adopted the mark, and
#: those names are argument labels in three platforms' generated code.
#:
#: Deliberately NOT `api.platforms.web.case_convention`: that one names how a
#: TypeScript DTO spells its fields, and a spec parameter is platform-agnostic.
#: Same word, different question.
PARAM_CASE_CONVENTIONS = ("asIs", "camelCase", "snake_case")


def apply_case(name: str, convention: str | None) -> str:
    """Spell a canonical parameter name the way this project writes them.

    43% of the corpus differs from the canon by nothing but this, so it is the
    single biggest reason a declaration cannot use the mark as written.
    """
    if convention in ("camelCase", "camel"):
        return to_camel(name)
    if convention in ("snake_case", "snake"):
        return to_snake(name)
    return name


def names_match(a: str, b: str) -> bool:
    """Equality modulo naming convention, for reporting rather than resolving."""
    return a == b or to_snake(a) == to_snake(b)


# --------------------------------------------------------------------------- #
# the canon
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CanonicalParam:
    name: str
    type: str
    required: bool = False

    def as_spec_param(self, convention: str | None = None) -> dict:
        return {"name": apply_case(self.name, convention), "type": self.type}


@dataclass(frozen=True)
class CanonicalOperation:
    """One OpenAPI operation, reduced to what a spec declaration needs."""

    path: str                       # as written in the document
    method: str
    params: tuple = ()              # tuple[CanonicalParam, ...]
    wire_type: str = ""             # 200 response `$ref` name, "" if inline
    source: str = ""                # document that declared it
    #: Properties the body schema calls `required` while the body itself is
    #: optional. They resolve optional, correctly — a caller may omit the
    #: whole body, so nothing inside it can be unconditionally required — but
    #: the reason sits two levels away from the symptom.
    muted_required: tuple = ()

    def spec_params(self, convention: str | None = None) -> list:
        return [p.as_spec_param(convention) for p in self.params]


def normalize_path(path: str) -> str:
    """`/api/venues/{venue_id}` and `/api/venues/{venueId}` are one route.

    Path-variable *spelling* is a real finding — it is 71 of the differences
    on one face alone — but it is a finding about the declaration, not a
    reason to fail to match the operation it obviously names. `:itemId`
    collapses the same way; the corpus has three of those.
    """
    bare = path.split("?")[0].rstrip("/") or "/"
    return _COLON_VAR_RE.sub("{}", _PATH_VAR_RE.sub("{}", bare))


def _schema_type(schema: dict, schemas: dict, depth: int = 0) -> str:
    """OpenAPI schema -> the type vocabulary specs are written in.

    Matches what the corpus already uses (`String`, `Int?`, `[String]`,
    `[String: Any]`, and bare schema names) rather than introducing a third
    spelling that neither platform codegen would recognise.
    """
    if not isinstance(schema, dict) or depth > 6:
        return "[String: Any]"
    ref = schema.get("$ref")
    if ref:
        return ref.rsplit("/", 1)[-1]
    for combinator in ("allOf", "oneOf", "anyOf"):
        members = schema.get(combinator)
        if isinstance(members, list) and members:
            # A nullable member is spelled `anyOf: [X, null]` by several
            # generators; the non-null member is the type.
            for member in members:
                if isinstance(member, dict) and member.get("type") != "null":
                    return _schema_type(member, schemas, depth + 1)
    kind = schema.get("type")
    if kind == "array":
        return f"[{_schema_type(schema.get('items') or {}, schemas, depth + 1)}]"
    return {
        "string": "String",
        "integer": "Int",
        "number": "Double",
        "boolean": "Bool",
    }.get(kind, "[String: Any]")


def _deref(schema: dict, schemas: dict) -> dict:
    ref = (schema or {}).get("$ref")
    if ref:
        return schemas.get(ref.rsplit("/", 1)[-1], {}) or {}
    return schema or {}


def _operation_params(op: dict, schemas: dict) -> list:
    """Every declared argument, in document order.

    `in` is deliberately not filtered: a path parameter is an argument the
    caller supplies exactly like a query one, so `{venue_id}` becomes
    `venueId` in the generated signature. That means **renaming a path
    variable moves every referencing spec's signature**, which is not obvious
    — route matching normalizes path-variable spelling away, so the same
    rename is invisible to resolution while being load-bearing for expansion.
    Found by a consumer lane reading this function after being told the
    opposite.
    """
    params: list = []
    seen: set = set()
    for p in op.get("parameters") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        name = p["name"]
        if name in seen:
            continue
        seen.add(name)
        required = bool(p.get("required"))
        t = _schema_type(p.get("schema") or {}, schemas)
        params.append(CanonicalParam(name, t if required else f"{t}?", required))

    body = ((op.get("requestBody") or {}).get("content") or {})
    body_schema = _deref((body.get("application/json") or {}).get("schema") or {},
                         schemas)
    body_required = bool((op.get("requestBody") or {}).get("required"))
    required_props = set(body_schema.get("required") or [])
    for name, prop in (body_schema.get("properties") or {}).items():
        if name in seen:
            continue
        seen.add(name)
        required = body_required and name in required_props
        t = _schema_type(prop or {}, schemas)
        params.append(CanonicalParam(name, t if required else f"{t}?", required))
    return params


def _muted_required(op: dict, schemas: dict) -> list:
    """Body properties declared `required` under a body that is not required.

    `requestBody.required` says the body may be omitted; `schema.required`
    says which properties must be present *if it is*. A flat parameter list
    cannot express "all or none", so these resolve optional — which is right,
    and which reads exactly like the declaration was ignored.

    Zero occurrences across every consumer canon measured (three canons,
    81 + 76 + 119 request bodies). Carried anyway because the corpus being clean is not
    the net working, and because schema-level `required` is the form people
    reach for first.
    """
    rb = op.get("requestBody")
    if not isinstance(rb, dict) or rb.get("required"):
        return []
    schema = _deref(((rb.get("content") or {}).get("application/json") or {})
                    .get("schema") or {}, schemas)
    return sorted(schema.get("required") or [])


def _response_wire_type(op: dict) -> str:
    responses = op.get("responses") or {}
    for code in ("200", "201", "202"):
        content = ((responses.get(code) or {}).get("content") or {})
        schema = (content.get("application/json") or {}).get("schema") or {}
        ref = schema.get("$ref")
        if ref:
            return ref.rsplit("/", 1)[-1]
    return ""


def index_documents(documents) -> dict:
    """`{(normalized path, METHOD): CanonicalOperation}` from OpenAPI docs.

    `documents` is an iterable of `(source_label, parsed_document)`. Parsing is
    the caller's job because the two tools reach their documents differently —
    one from `api_directory`, one from the build config — and neither should
    have to grow the other's file-finding rules to share this.
    """
    index: dict = {}
    for source, doc in documents:
        if not isinstance(doc, dict):
            continue
        # An api_directory holds more than OpenAPI documents in practice
        # (generated HTML sidecars, fixtures, config). Indexing a file that
        # merely happens to have a `paths` key would put routes in the canon
        # that nothing published.
        if "openapi" not in doc and "swagger" not in doc:
            continue
        schemas = ((doc.get("components") or {}).get("schemas") or {})
        for path, ops in (doc.get("paths") or {}).items():
            if not isinstance(ops, dict):
                continue
            for verb, op in ops.items():
                if verb.upper() not in HTTP_METHODS or not isinstance(op, dict):
                    continue
                key = (normalize_path(path), verb.upper())
                # First document wins: re-indexing an operation would let the
                # order files happen to be read in decide the answer.
                if key in index:
                    continue
                index[key] = CanonicalOperation(
                    path=path,
                    method=verb.upper(),
                    params=tuple(_operation_params(op, schemas)),
                    wire_type=_response_wire_type(op),
                    source=source,
                    muted_required=tuple(_muted_required(op, schemas)),
                )
    return index


def load_documents(api_dir, *, want_yaml=True):
    """`(source, document)` pairs for every OpenAPI file under a directory.

    YAML needs PyYAML. Returning half an index would report every route that
    lives in a YAML document as missing, so the shortfall is reported to the
    caller instead of absorbed: `(pairs, missing_yaml_count)`.
    """
    api_dir = Path(api_dir)
    if not api_dir.is_dir():
        return [], 0
    pairs = []
    for p in sorted(api_dir.rglob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                pairs.append((str(p), json.load(f)))
        except (OSError, json.JSONDecodeError):
            continue
    yaml_docs = sorted(api_dir.rglob("*.yaml")) + sorted(api_dir.rglob("*.yml"))
    if not yaml_docs or not want_yaml:
        return pairs, 0
    try:
        import yaml
    except ImportError:
        return pairs, len(yaml_docs)
    for p in yaml_docs:
        try:
            with open(p, "r", encoding="utf-8") as f:
                pairs.append((str(p), yaml.safe_load(f)))
        except (OSError, Exception):  # noqa: B014 - yaml raises its own tree
            continue
    return pairs, 0


def find_api_directories(start, *, extra_roots=()):
    """`api_directory` candidates for a spec, nearest first.

    Driven by `jui.config.json` (`api_directory`, defaulting to `docs/api`),
    because that is the directory `jui` itself resolves and a second rule for
    "where the canon lives" would let the two tools read different documents
    and disagree about what a mark expands to.

    Two layouts exist and neither subsumes the other: a project whose config
    is an ancestor of its specs, and one whose specs sit in a `docs/` tree
    beside the config, where the specs' own ancestors carry partial configs
    that never mention `api_directory`. So the working directory is a second
    source rather than a guess — the first candidate that actually holds
    OpenAPI documents wins, and an unrelated directory never qualifies.
    """
    roots: list = []
    if start is not None:
        roots.extend(list(Path(start).resolve().parents)[:8])
    for extra in extra_roots:
        if extra is None:
            continue
        extra = Path(extra).resolve()
        roots.append(extra)
        roots.extend(list(extra.parents)[:8])

    out: list = []
    seen: set = set()
    for root in roots:
        config_path = root / "jui.config.json"
        if not config_path.is_file():
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(config, dict):
            continue
        api_dir = (root / config.get("api_directory", "docs/api")).resolve()
        if api_dir not in seen:
            seen.add(api_dir)
            out.append(api_dir)
    return out


def param_case_for(start, *, extra_roots=()):
    """`spec.canonical_param_case` from the nearest config that declares it."""
    roots: list = []
    if start is not None:
        roots.extend(list(Path(start).resolve().parents)[:8])
    for extra in extra_roots:
        if extra is not None:
            roots.append(Path(extra).resolve())
    for root in roots:
        config_path = root / "jui.config.json"
        if not config_path.is_file():
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            continue
        spec_cfg = config.get("spec")
        if isinstance(spec_cfg, dict) and spec_cfg.get("canonical_param_case"):
            return spec_cfg["canonical_param_case"]
    return None


def lookup(index: dict, endpoint: str):
    """`(operation, reason)` — reason is set only when there is no operation.

    Reasons are `malformed`, `non_http`, `path_missing`, `method_missing`, so
    a caller can word its own message; this module never decides whether a
    miss is an error, because it is one for `@canonical` and a warning for a
    hand-written declaration.
    """
    if not isinstance(endpoint, str) or not endpoint.strip():
        return None, "malformed"
    m = ENDPOINT_RE.match(endpoint.strip())
    if not m:
        return None, "malformed"
    verb = m.group(1).upper()
    if verb not in HTTP_METHODS:
        return None, "non_http"
    key = (normalize_path(m.group(2)), verb)
    if key in index:
        return index[key], ""
    if any(k[0] == key[0] for k in index):
        return None, "method_missing"
    return None, "path_missing"


# --------------------------------------------------------------------------- #
# the mark
# --------------------------------------------------------------------------- #

def is_canonical_params(declared) -> bool:
    """Does this `params` value ask for resolution at all?"""
    if declared == CANONICAL_MARKER:
        return True
    return (isinstance(declared, list)
            and any(x == CANONICAL_MARKER for x in declared))


def is_canonical_return(declared) -> bool:
    return declared == CANONICAL_WIRE_MARKER


@dataclass
class Resolution:
    """What the mark expanded to, what stopped it, and what to say about it."""

    params: list = field(default_factory=list)
    return_type: str = ""
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def resolve_params(declared, operation, convention=None) -> Resolution:
    """Expand `@canonical` in place, keeping hand-written entries around it.

    Order is the declaration's: the mark expands where it sits, so a method
    that wants its own argument first can put it first. Hand-written entries
    win on name collision — the whole reason the two mix in one list is that
    the author is saying something the canon does not.
    """
    res = Resolution()
    if not is_canonical_params(declared):
        res.params = list(declared) if isinstance(declared, list) else []
        return res
    if operation is None:
        res.errors.append(
            f"'{CANONICAL_MARKER}' needs an endpoint that resolves to an "
            "operation in the API canon")
        return res

    entries = declared if isinstance(declared, list) else [declared]
    written = {e.get("name") for e in entries
               if isinstance(e, dict) and e.get("name")}
    out: list = []
    for entry in entries:
        if entry == CANONICAL_MARKER:
            for p in operation.spec_params(convention):
                # A hand-written entry of the same name replaces it rather
                # than sitting beside it; two params with one name is not a
                # signature any platform will generate.
                if p["name"] in written or any(
                        names_match(p["name"], w) for w in written):
                    continue
                out.append(p)
        elif isinstance(entry, dict):
            out.append(entry)
        else:
            res.errors.append(
                f"unexpected params entry {entry!r}: expected an object or "
                f"'{CANONICAL_MARKER}'")
    res.params = out
    return res


def iter_marked_methods(spec_data):
    """`(label, method)` for every dataFlow method carrying a mark.

    The walk is here, not in each tool, for the same reason the index is: two
    walks would disagree the first time either learned about a section the
    other did not.
    """
    data_flow = (spec_data or {}).get("dataFlow")
    if not isinstance(data_flow, dict):
        return
    for section in ("repositories", "useCases"):
        items = data_flow.get(section)
        if not isinstance(items, list):
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            methods = item.get("methods")
            if not isinstance(methods, list):
                continue
            for j, method in enumerate(methods):
                if not isinstance(method, dict):
                    continue
                if (is_canonical_params(method.get("params"))
                        or is_canonical_return(method.get("returnType"))):
                    yield f"dataFlow.{section}[{i}].methods[{j}]", method


def miss_reason(reason: str, method: dict) -> str:
    """Why a mark could not resolve, worded for a person fixing the spec."""
    endpoint = method.get("endpoint")
    if not endpoint:
        return ("the method declares no 'endpoint', so there is no operation "
                "to read it from")
    if reason == "non_http":
        return (f"'{endpoint}' is not an HTTP route, and OpenAPI documents do "
                "not describe it — write the value directly")
    if reason == "malformed":
        return f"'{endpoint}' is not a '<METHOD> <path>' declaration"
    if reason == "method_missing":
        return (f"'{endpoint}' names a path the API canon declares, but not "
                "for that method")
    return (f"'{endpoint}' is not declared in any OpenAPI document under "
            "api_directory")


def resolve_spec_marks(spec_data, index, convention=None):
    """Expand every mark in `spec_data`, in place. Returns `[(label, msg)]`.

    Returns `(errors, warnings)`. In place and before anything else reads the
    document, so the doc site's HTML, every other spec check, and the
    repository stubs `jui build` writes all see one list. An unresolved mark is
    reported, never quietly dropped: dropping would generate a method with no
    arguments and no complaint.
    """
    errors, warnings = [], []
    for label, method in list(iter_marked_methods(spec_data)):
        operation, reason = lookup(index or {}, method.get("endpoint"))
        if operation is None:
            errors.append((label, f"'{CANONICAL_MARKER}' cannot be resolved: "
                                  + miss_reason(reason, method)))
            continue
        if is_canonical_params(method.get("params")):
            res = resolve_params(method.get("params"), operation, convention)
            errors.extend((f"{label}.params", e) for e in res.errors)
            if operation.muted_required:
                warnings.append((f"{label}.params", (
                    "the request body declares "
                    f"{', '.join(operation.muted_required)} as required, but "
                    "`requestBody.required` is not set — the caller may omit "
                    "the body entirely, so these expand optional. Set "
                    "`requestBody.required: true` in the API document if they "
                    "are meant to be mandatory arguments.")))
            if not res.errors:
                method["params"] = res.params
        if is_canonical_return(method.get("returnType")):
            res = resolve_return_type(method.get("returnType"), operation)
            errors.extend((f"{label}.returnType", e) for e in res.errors)
            if not res.errors:
                method["returnType"] = res.return_type
    return errors, warnings


def resolve_return_type(declared, operation) -> Resolution:
    res = Resolution()
    if not is_canonical_return(declared):
        res.return_type = declared if isinstance(declared, str) else ""
        return res
    if operation is None:
        res.errors.append(
            f"'{CANONICAL_WIRE_MARKER}' needs an endpoint that resolves to an "
            "operation in the API canon")
        return res
    if not operation.wire_type:
        res.errors.append(
            f"'{CANONICAL_WIRE_MARKER}' needs the operation's success response "
            "to name a schema; this one describes its body inline, so there is "
            "no name to lift — write the type directly")
        return res
    res.return_type = operation.wire_type
    return res
