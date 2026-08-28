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

#: Parameter locations the client's transport layer supplies, not the caller.
#: Excluded from expansion — and the corpus shows why in the bluntest way: the
#: only two header parameters in it are `X-Client-Latitude` / `X-Client-Longitude`,
#: geo values a client injects, whose names are not identifiers in any target
#: language. Measured: zero header or cookie parameters in the other two
#: canons, so excluding them changes nothing already converted.
TRANSPORT_PARAM_LOCATIONS = frozenset({"header", "cookie"})

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

    `in` is filtered only for locations the transport layer fills
    (`TRANSPORT_PARAM_LOCATIONS`). A path parameter is an argument the caller
    supplies exactly like a query one, so `{venue_id}` becomes `venueId` in
    the generated signature. That means **renaming a path
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
        if p.get("in") in TRANSPORT_PARAM_LOCATIONS:
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


@dataclass(frozen=True)
class SpecCanonContext:
    """The canon and the naming convention, from ONE config.

    They used to be resolved separately, and a split tree pulled them apart:
    the API documents came from the repository-root config while the naming
    convention was looked for by walking up from the spec, which in that
    layout never reaches the app's config at all. Measured — expansion spelled
    parameters `camelCase` and the divergence check compared against the
    document's raw spelling **in the same run**, so a project that set the
    convention could not write a `canonicalDivergence` in either spelling.

    The same shape as the mockDir defect three days earlier: a declared config
    losing to a path walk. That one was fixed by making the declaration
    outrank the search; this reintroduced the search as the only path for a
    new setting. So the config that answers is the config the run loaded, and
    it answers both questions or neither.
    """

    index: dict
    convention: str | None = None
    config_path: object = None
    #: YAML documents that could not be read for want of PyYAML. Half an index
    #: is worse than none — every route living in those documents would be
    #: reported as missing — so the shortfall is carried to the caller rather
    #: than absorbed into a smaller index.
    missing_yaml: int = 0


def _read_config(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return config if isinstance(config, dict) else None


def _follow_extends(root, cfg, config, _depth=0):
    """`extends` names the config that actually owns this tree.

    A face whose specs live in one tree and whose build config lives in
    another has nothing on the specs' ancestry that identifies the owning
    config — so the answer came from whichever directory the command happened
    to run in, and `jui build` (run from the app) and `jsonui-doc` (run from
    the repository root) read different configs for the same spec. Same
    declared-config-losing-to-a-search shape as mockDir and the parameter-case
    setting, one level further out: this time the search was over configs.

    So the stub config the specs' ancestry does reach names its owner, and the
    pointer is followed. Consumers were already writing that pointer in a
    `_note` for humans; this reads the same fact.
    """
    if _depth > 4:
        return root, cfg, config
    target = config.get("extends")
    if not isinstance(target, str) or not target:
        return root, cfg, config
    resolved = (root / target).resolve()
    if resolved.is_dir():
        resolved = resolved / "jui.config.json"
    if not resolved.is_file():
        return root, cfg, config
    extended = _read_config(resolved)
    if extended is None:
        return root, cfg, config
    # The named config replaces this one rather than layering under it: the
    # stub exists to point, and merging would put two answers back in play.
    return _follow_extends(resolved.parent, resolved, extended, _depth + 1)


def build_spec_canon_context(spec_path, *, config_path=None, extra_roots=()):
    """Resolve the canon and the convention together, preferring the run's config.

    Candidate order is explicit config, then the caller's roots (its working
    directory — the one `jui` itself resolves from), then the spec's ancestors.
    The first candidate holding OpenAPI documents answers both questions, so
    the two cannot come from different files.
    """
    candidates: list = []
    seen: set = set()

    def add(path):
        if path is None:
            return
        path = Path(path)
        if path.is_file():
            path = path.parent
        path = path.resolve()
        if path not in seen:
            seen.add(path)
            candidates.append(path)

    add(config_path)
    # The spec's own ancestry first, nearest outward: it identifies which face
    # the spec belongs to, which the working directory does not — that is only
    # where the command happened to be typed. Ordering it the other way made
    # `jui build` (run from the app) and `jsonui-doc` (run from the repository
    # root) read different configs for the same spec, in the same tree.
    #
    # This is only correct because a stub on that ancestry can name its owner
    # through `extends`. Without it the nearest config is whatever partial one
    # happens to sit there, which is why the working directory was tried first
    # in the version before this.
    if spec_path is not None:
        for parent in list(Path(spec_path).resolve().parents)[:8]:
            add(parent)
    for root in extra_roots:
        add(root)
        if root is not None:
            for parent in list(Path(root).resolve().parents)[:8]:
                add(parent)

    fallback_convention = None
    for root in candidates:
        cfg = root / "jui.config.json"
        if not cfg.is_file():
            continue
        config = _read_config(cfg)
        if config is None:
            continue
        root, cfg, config = _follow_extends(root, cfg, config)
        spec_cfg = config.get("spec")
        declared = (spec_cfg or {}).get("canonical_param_case") \
            if isinstance(spec_cfg, dict) else None
        if declared and fallback_convention is None:
            fallback_convention = declared

        api_dir = (root / config.get("api_directory", "docs/api")).resolve()
        documents, missing = load_documents(api_dir)
        if missing:
            return SpecCanonContext(index={}, convention=declared,
                                    config_path=cfg, missing_yaml=missing)
        index = index_documents(documents)
        if index:
            # This config answers both. Not "this config for the routes and
            # whichever other one happened to declare a convention".
            return SpecCanonContext(index=index, convention=declared,
                                    config_path=cfg)

    return SpecCanonContext(index={}, convention=fallback_convention,
                            config_path=None)


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
    for section in MARKABLE_SECTIONS:
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


#: dataFlow sections whose methods may name a transport. `viewModel` is not
#: one of them — the architecture rule is that a ViewModel never calls an API
#: directly, so an `endpoint` there implies a missing repository. The schema
#: nevertheless allows the same method shape everywhere, so a mark can be
#: written in a section that does not resolve it.
MARKABLE_SECTIONS = ("repositories", "useCases")
UNMARKABLE_SECTIONS = ("viewModel",)


def iter_misplaced_marks(spec_data):
    """`(label, method)` for marks written where nothing expands them.

    Silence here was worse than the empty list this module refuses to produce:
    the marker string survived as the value of `params`, validation said
    PASSED, and the author saw a spec that looked converted and was not.
    Reported by a lane that added a probe to its own spec to find out.
    """
    data_flow = (spec_data or {}).get("dataFlow")
    if not isinstance(data_flow, dict):
        return
    for section in UNMARKABLE_SECTIONS:
        holder = data_flow.get(section)
        if not isinstance(holder, dict):
            continue
        methods = holder.get("methods")
        if not isinstance(methods, list):
            continue
        for j, method in enumerate(methods):
            if not isinstance(method, dict):
                continue
            if (is_canonical_params(method.get("params"))
                    or is_canonical_return(method.get("returnType"))):
                yield f"dataFlow.{section}.methods[{j}]", method


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
    for label, _method in list(iter_misplaced_marks(spec_data)):
        errors.append((label, (
            f"'{CANONICAL_MARKER}' is not expanded here. A ViewModel method "
            "does not declare a transport — an endpoint belongs on a "
            "repository method, and the ViewModel calls that. Move the "
            "declaration, or write the value out.")))
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

# --------------------------------------------------------------------------- #
# declared divergence
# --------------------------------------------------------------------------- #

DIVERGENCE_KEY = "canonicalDivergence"
_DIVERGENCE_FIELDS = ("renamed", "omitted", "wrapped", "added", "reason")

#: `renamed` alone can only say "this argument has another name here", so the
#: only declarable divergence was a one-to-one correspondence. Measured on one
#: face: 7 of 37 hand-written declarations were that shape, and the other 30
#: — the longest ones, wrapping twenty to thirty body fields into a request
#: object — could not be declared at all. The feature's stated motivation was
#: that hand-written declarations take part in no check; most of that set was
#: still outside it.
#:
#: So three more shapes, each still checked against the operation:
#:   omitted  canonical arguments this method deliberately does not take —
#:            environment or build constants the caller never chooses
#:   wrapped  one written argument standing in for several canonical ones;
#:            a method with thirty parameters is a worse contract than a DTO
#:   added    written arguments the operation does not declare — multipart
#:            bodies, where the JSON expansion is empty by construction


def iter_divergence_declarations(spec_data):
    """`(label, method)` for every method declaring a divergence."""
    data_flow = (spec_data or {}).get("dataFlow")
    if not isinstance(data_flow, dict):
        return
    for section in MARKABLE_SECTIONS:
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
                if isinstance(method, dict) and method.get(DIVERGENCE_KEY):
                    yield f"dataFlow.{section}[{i}].methods[{j}]", method


def check_divergences(spec_data, index, convention=None):
    """`[(label, message)]` — a declared divergence that is not the real one.

    Written-out params are the way to say "this method deliberately differs
    from the canon", so a blanket warning on any difference would delete the
    only means of saying it: 115 declarations across the corpus would go red
    at once and a permanently-red check stops being read. The question is not
    whether there is a difference, it is whether the difference is the one
    that was declared.

    So the declaration is what turns checking on for a method. Without it,
    nothing changes — a project adopts this one method at a time. With it,
    the method is held to the declaration exactly:

    - a rename that no longer corresponds to a real difference is an error.
      This is the point of the feature: when the canon is renamed to match,
      the divergence disappears and the note describing it goes stale, and a
      stale note is how "we already dealt with that" survives the thing it
      was about.
    - a difference the declaration does not account for is an error. It
      subtracts, it does not exempt — an accidental drift hides best inside a
      method already known to differ.
    """
    errors = []
    for label, method in iter_divergence_declarations(spec_data):
        raw = method.get(DIVERGENCE_KEY)
        path = f"{label}.{DIVERGENCE_KEY}"

        if not isinstance(raw, dict):
            errors.append((path, f"{DIVERGENCE_KEY} must be an object"))
            continue
        for key in raw:
            if key not in _DIVERGENCE_FIELDS:
                errors.append((path, f"unknown {DIVERGENCE_KEY} key {key!r} "
                                     f"(expected: {', '.join(_DIVERGENCE_FIELDS)})"))
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            # The ledger records WHY, or it is a suppression dump.
            errors.append((path, f"{DIVERGENCE_KEY} needs a non-empty 'reason'"))
        renamed = raw.get("renamed") or {}
        if not isinstance(renamed, dict) or not all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in renamed.items()):
            errors.append((path, "'renamed' must be an object of "
                                 "canonical-name -> spec-name strings"))
            continue

        if is_canonical_params(method.get("params")):
            errors.append((path, (
                f"a method using '{CANONICAL_MARKER}' has no divergence to "
                "declare — the mark follows the canon by construction. Remove "
                f"the {DIVERGENCE_KEY}, or write the params out.")))
            continue

        operation, reason_code = lookup(index or {}, method.get("endpoint"))
        if operation is None:
            errors.append((path, f"{DIVERGENCE_KEY} cannot be checked: "
                                 + miss_reason(reason_code, method)))
            continue

        lists = {}
        for field in ("omitted", "added"):
            value = raw.get(field) or []
            if not isinstance(value, list) or not all(
                    isinstance(x, str) for x in value):
                errors.append((path, f"'{field}' must be a list of names"))
                value = []
            lists[field] = value
        wrapped = raw.get("wrapped") or {}
        if not isinstance(wrapped, dict) or not all(
                isinstance(k, str) and isinstance(v, list)
                and all(isinstance(x, str) for x in v)
                for k, v in wrapped.items()):
            errors.append((path, "'wrapped' must be an object of "
                                 "spec-argument -> [canonical names]"))
            wrapped = {}

        canonical = [p["name"] for p in operation.spec_params(convention)]
        declared = [p.get("name") for p in (method.get("params") or [])
                    if isinstance(p, dict) and p.get("name")]
        errors.extend(_divergence_errors(
            path, renamed, canonical, declared,
            omitted=lists["omitted"], wrapped=wrapped, added=lists["added"]))
    return errors


def _divergence_errors(path, renamed, canonical, declared,
                       omitted=(), wrapped=None, added=()):
    out = []
    wrapped = wrapped or {}

    # Each clause has to still describe a real difference. A note that no
    # longer does is the case this whole feature exists for: the canon moves,
    # the divergence disappears, and the sentence explaining it outlives the
    # thing it was about.
    for name in omitted:
        if name not in canonical:
            out.append((path, (
                f"'omitted' names '{name}', which the operation does not "
                "declare — there is nothing here to leave out.")))
    for holder, covered in wrapped.items():
        if holder not in declared:
            out.append((path, (
                f"'wrapped' says '{holder}' stands in for other arguments, "
                "but this method has no such parameter.")))
        for name in covered:
            if name not in canonical:
                out.append((path, (
                    f"'wrapped' says '{holder}' covers '{name}', which the "
                    "operation does not declare.")))
    for name in added:
        if name in canonical:
            out.append((path, (
                f"'added' names '{name}', which the operation does declare — "
                "it is not an addition, so it is compared like any other "
                "argument.")))
        if name not in declared:
            out.append((path, (
                f"'added' names '{name}', which this method does not take.")))
    if out:
        return out

    canonical = [n for n in canonical
                 if n not in omitted
                 and not any(n in c for c in wrapped.values())]
    declared = [n for n in declared
                if n not in added and n not in wrapped]

    remaining = list(declared)
    expected = []
    for name in canonical:
        mapped = renamed.get(name, name)
        expected.append(mapped)
        if name in renamed and name in declared:
            out.append((path, (
                f"'renamed' says the canon's '{name}' appears here as "
                f"'{renamed[name]}', but '{name}' is what the params actually "
                "say — the divergence this describes is gone. Update the "
                "params, or drop the entry.")))

    for name in renamed:
        if name not in canonical:
            out.append((path, (
                f"'renamed' maps '{name}', which the operation does not "
                "declare — the canon no longer has that parameter, so this "
                "note describes a difference that cannot exist.")))

    if out:
        # The set difference below is a consequence of the entries already
        # reported, not a second finding. Emitting both makes one defect read
        # as two and buries the one that says what to change.
        return out

    missing = [n for n in expected if n not in remaining]
    extra = [n for n in remaining if n not in expected]
    if missing or extra:
        parts = []
        if missing:
            parts.append("does not declare " + ", ".join(repr(n) for n in missing))
        if extra:
            parts.append("adds " + ", ".join(repr(n) for n in extra))
        out.append((path, (
            "the declared divergence does not account for the whole "
            f"difference: after applying 'renamed', this method {' and '.join(parts)}. "
            "A declaration subtracts from the comparison, it does not exempt "
            "the method from it.")))
    return out


# --------------------------------------------------------------------------- #
# cross-spec agreement
# --------------------------------------------------------------------------- #

def iter_declared_methods(spec_data):
    """`(section, owner, method)` for every dataFlow method with an owner."""
    data_flow = (spec_data or {}).get("dataFlow")
    if not isinstance(data_flow, dict):
        return
    for section in MARKABLE_SECTIONS:
        items = data_flow.get(section)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            for method in item.get("methods") or []:
                if isinstance(method, dict) and method.get("name"):
                    yield section, item["name"], method


def _signature(method) -> tuple:
    params = method.get("params")
    if isinstance(params, str):
        shape = ("raw", params)
    elif isinstance(params, list):
        shape = tuple(
            p if isinstance(p, str)
            else (p.get("name"), p.get("type"))
            for p in params
        )
    else:
        shape = ()
    return (shape, method.get("returnType") or "", method.get("endpoint") or "")


def cross_spec_disagreements(specs):
    """`[(owner.method, [(source, description), ...])]` for split declarations.

    `specs` is `(source_label, spec_data)` pairs.

    One repository method declared by several screens is normal — a shared
    component is used by several screens, and the rule is that every screen
    using it declares what it calls, so the method's usage can be read off the
    specs. What is not normal is those declarations disagreeing: the method has
    one implementation, so at most one of them describes it.

    Both consumer lanes that looked found defects of exactly this shape by
    hand — a method declared by four specs with one of them missing its
    arguments, and four more where one of a pair had lost a parameter. Neither
    is visible from one spec, which is why no per-file check could ever have
    caught them.

    Compared, deliberately, before `@canonical` expands: two specs that both
    write `"@canonical"` agree by construction, and a spec that writes the
    expansion out by hand while its sibling references it is a difference in
    how they are maintained, not in what they say. Reporting that would make
    the check fire on the mixed state every project passes through while
    converting.
    """
    seen: dict = {}
    for source, spec in specs:
        for _section, owner, method in iter_declared_methods(spec or {}):
            platforms = method.get("platforms") or []
            if not isinstance(platforms, list):
                platforms = []
            # A method scoped to one platform is not in disagreement with the
            # same name scoped to another: `UIImage` against `Bitmap`, `Void`
            # against `Unit`, `inout` against plain. Measured on the corpus —
            # ignoring `platforms` produced four findings and all four were
            # this, which would have been the whole of the check's output on
            # the face that had no real disagreement left.
            key = (f"{owner}.{method['name']}",
                   tuple(sorted(str(p) for p in platforms)))
            seen.setdefault(key, []).append((source, _signature(method)))

    out = []
    for (name, platforms), entries in sorted(seen.items()):
        shapes = {sig for _src, sig in entries}
        if len(shapes) < 2:
            continue
        label = f"{name} [{'/'.join(platforms)}]" if platforms else name
        out.append((label, [(src, _describe(sig)) for src, sig in entries]))
    return out


def _describe(sig) -> str:
    shape, return_type, endpoint = sig
    if shape and shape[0] == "raw":
        params = shape[1]
    else:
        params = ", ".join(
            p if isinstance(p, str) else f"{p[0]}: {p[1]}" for p in shape)
    head = f"({params}) -> {return_type or '?'}"
    return f"{head}   [{endpoint}]" if endpoint else head
