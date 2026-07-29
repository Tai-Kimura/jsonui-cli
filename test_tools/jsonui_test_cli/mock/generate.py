"""Scaffold mock definition files from OpenAPI specs, and report drift (--check).

Layout::

    <mockDir>/<tag-slug>/<operationId>.mock.json             hand-written
    <mockDir>/generated/<tag-slug>/<operationId>.mock.json   generated

`generated/` is a pure function of the swagger: it is wiped and rewritten on
every `mock generate`, so a contract change shows up as a regeneration rather
than as a hand-merge, and the directory can be gitignored — what a repository
owes is the input (the swagger), not 188 placeholder bodies.

Anything outside `generated/` is hand-written and is never touched. `mock
serve` reads both and lets the hand-written side win, scenario by scenario:
a hand-written file carries only the scenarios its tests drive, and the
routine `error_403` / `empty` variants come from the generated side.

--check reports adds/removes/schema drift without writing. Findings on the
generated side are warnings (regenerating fixes them); findings on the
hand-written side are errors (a person has to decide).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .openapi import OpenApiDoc, Operation, slugify


def mock_relpath(op: Operation) -> str:
    """Relative path (from mockDir) a freshly scaffolded mock is written to.

    A *naming convention*, not an identity. Files are matched by their
    `source` route — see `route_key` — because that is what the server routes
    on, and a project is free to name them however it likes.
    """
    return f"{slugify(op.tag)}/{op.operation_id}.mock.json"


#: Subdirectory of mockDir that `mock generate` owns outright.
GENERATED_DIR = "generated"


def is_generated(rel) -> bool:
    """True for a path inside the generated tree (relative to mockDir)."""
    return Path(rel).parts[:1] == (GENERATED_DIR,)


def route_key(method, path) -> tuple:
    """The identity of a mock: the route it serves.

    `mock serve` resolves a request by `source.method` + `source.path` and
    only falls back to the filename for a display id. The checker used to
    identify mocks by filename instead, so a project that names its files
    after the path rather than the operationId had every mock reported as
    both MISSING and ORPHAN — and the body comparison, which only runs on
    files matched to an operation, never executed at all.
    """
    return ((method or "GET").upper(), path or "/")


def read_route(path: Path) -> tuple | None:
    """`route_key` of a mock file, or None when it is unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    src = data.get("source") or {}
    return route_key(src.get("method"), src.get("path"))


def index_existing(mock_dir: Path) -> dict:
    """`route_key -> relative path` for every mock file under `mock_dir`."""
    out: dict = {}
    if not mock_dir.exists():
        return out
    for path in sorted(mock_dir.rglob("*.mock.json")):
        key = read_route(path)
        if key is not None:
            out[key] = str(path.relative_to(mock_dir))
    return out


def build_mock_definition(doc: OpenApiDoc, op: Operation) -> dict:
    """Build a fresh mock definition (all scenarios) for one operation."""
    schema, content_type = doc.success_schema(op)
    success_code = _first_success_code(op)

    default_scenario: dict = {"status": success_code}
    if content_type and content_type != "application/json":
        # Non-JSON success response (PDF/CSV/ZIP/...): author supplies a file.
        default_scenario["contentType"] = content_type
        default_scenario["bodyFile"] = None
    elif schema is not None:
        default_scenario["body"] = doc.sample_for_schema(schema)
    elif content_type is None and success_code == 204:
        pass  # no body
    else:
        default_scenario["body"] = {}

    scenarios: dict = {"default": default_scenario}

    # An empty variant helps test empty-state UI when the body is a collection.
    body = default_scenario.get("body")
    if isinstance(body, dict):
        empty = _empty_variant(body)
        if empty is not None:
            scenarios["empty"] = {"status": success_code, "body": empty}
    elif isinstance(body, list):
        scenarios["empty"] = {"status": success_code, "body": []}

    # Synthesize error scenarios from declared 4xx/5xx responses.
    for code in doc.error_codes(op):
        err_schema, err_ct = _error_schema(doc, op, code)
        scen = {"status": int(code)}
        if err_ct == "application/json" and err_schema is not None:
            scen["body"] = doc.sample_for_schema(err_schema)
        else:
            scen["body"] = {"detail": f"HTTP {code}"}
        scenarios[f"error_{code}"] = scen

    return {
        "$schema": "./.mock.schema.json",
        "source": {
            "swagger": doc.source_path,
            "operationId": op.operation_id,
            "method": op.method,
            "path": op.path,
        },
        "activeScenario": "default",
        "scenarios": scenarios,
    }


def _first_success_code(op: Operation) -> int:
    for code in sorted(op.responses.keys()):
        if code.startswith("2"):
            return int(code)
    return 200


def _error_schema(doc: OpenApiDoc, op: Operation, code: str):
    return _response_schema(op, code)


def _response_schema(op: Operation, code):
    """(schema, content_type) for one declared status code, or (None, None).

    Falls back to the `default` response, which OpenAPI allows in place of an
    explicit code.
    """
    resp = op.responses.get(str(code))
    if resp is None:
        resp = op.responses.get("default")
    resp = resp or {}
    content = resp.get("content") or {}
    if "application/json" in content:
        return content["application/json"].get("schema"), "application/json"
    if content:
        ctype = next(iter(content.keys()))
        return content[ctype].get("schema"), ctype
    return None, None


def _empty_variant(body: dict):
    """If the body has a top-level array field, return a copy with it emptied."""
    for key, value in body.items():
        if isinstance(value, list):
            clone = dict(body)
            clone[key] = []
            return clone
    return None


@dataclass
class GenerateReport:
    created: list[str]     # written into generated/
    skipped: list[str]     # a hand-written mock already serves that route
    warnings: list[str]


def _clear_generated(gen_root: Path) -> None:
    """Empty the generated tree, leaving anything that is not a mock alone."""
    if not gen_root.is_dir():
        return
    for path in gen_root.rglob("*.mock.json"):
        path.unlink()
    # Prune the directories that emptied out, deepest first.
    for path in sorted(gen_root.rglob("*"), key=lambda p: -len(p.parts)):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def generate(
    swagger_paths: list[str],
    mock_dir: str | Path,
    check: bool = False,
    strict: bool = False,
) -> GenerateReport | "CheckReport":
    """Regenerate `<mockDir>/generated/`, or (check=True) diff without writing.

    Deterministic: the same swagger and the same tool version produce the same
    bytes, which is what lets `generated/` be gitignored and rebuilt on a
    fresh clone rather than committed.
    """
    mock_dir = Path(mock_dir)
    if check:
        return _check(swagger_paths, mock_dir, strict=strict)

    created: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    # Hand-written mocks are recognised by the route they serve, not by
    # filename, so a project's own naming keeps working and generation never
    # produces a duplicate of one.
    hand_written = {
        key: rel for key, rel in index_existing(mock_dir).items()
        if not is_generated(rel)
    }

    gen_root = mock_dir / GENERATED_DIR
    _clear_generated(gen_root)

    for swagger in swagger_paths:
        doc = OpenApiDoc.load(swagger)
        if not doc.is_api_spec():
            warnings.append(f"{swagger}: no paths (DB-model spec?) — skipped")
            continue
        for op in doc.operations():
            if op.id_was_synthesized:
                warnings.append(
                    f"{op.method} {op.path}: missing operationId -> synthesized '{op.operation_id}'"
                )
            covered = hand_written.get(route_key(op.method, op.path))
            if covered is not None:
                skipped.append(covered)
                continue
            rel = f"{GENERATED_DIR}/{mock_relpath(op)}"
            target = mock_dir / rel
            definition = build_mock_definition(doc, op)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(definition, f, ensure_ascii=False, indent=2)
                f.write("\n")
            created.append(rel)

    return GenerateReport(created=created, skipped=skipped, warnings=warnings)


@dataclass
class UpdateReport:
    updated: list[str]    # files whose default body (or source) was refreshed
    unchanged: list[str]
    skipped: list[str]    # in swagger, no mock file — `generate` creates those


def update_default(swagger_paths: list[str], mock_dir: str | Path) -> UpdateReport:
    """Refresh the generated parts of existing mocks, keeping the hand-grown ones.

    Only the `default` scenario body and the `source` block are rewritten.
    Every other scenario is left byte-for-byte alone: those carry the data the
    tests drive (`real_id`, `rich_flavor`, `empty`, …) and regenerating them
    from the schema would replace deliberate fixtures with placeholders.
    """
    mock_dir = Path(mock_dir)
    updated: list[str] = []
    unchanged: list[str] = []
    skipped: list[str] = []
    existing = index_existing(mock_dir)

    for swagger in swagger_paths:
        doc = OpenApiDoc.load(swagger)
        if not doc.is_api_spec():
            continue
        for op in doc.operations():
            # Located by route, so a project's own file naming is honoured.
            rel = existing.get(route_key(op.method, op.path)) or mock_relpath(op)
            target = mock_dir / rel
            if not target.exists():
                skipped.append(rel)
                continue
            try:
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                skipped.append(rel)
                continue

            fresh = build_mock_definition(doc, op)
            before = json.dumps(data, ensure_ascii=False, sort_keys=True)

            # `swagger` records where the file was authored from and is not
            # drift — rewriting it would churn every mock the moment someone
            # runs this from a different directory.
            source = dict(fresh["source"])
            existing_swagger = (data.get("source") or {}).get("swagger")
            if existing_swagger is not None:
                source["swagger"] = existing_swagger
            data["source"] = source
            scenarios = data.get("scenarios")
            if isinstance(scenarios, dict) and isinstance(scenarios.get("default"), dict):
                fresh_default = fresh["scenarios"]["default"]
                current = scenarios["default"]
                for key in ("status", "body", "contentType", "bodyFile"):
                    if key in fresh_default:
                        current[key] = fresh_default[key]
                    else:
                        current.pop(key, None)
            elif isinstance(scenarios, dict):
                scenarios["default"] = fresh["scenarios"]["default"]

            if json.dumps(data, ensure_ascii=False, sort_keys=True) == before:
                unchanged.append(rel)
                continue
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            updated.append(rel)

    return UpdateReport(updated=updated, unchanged=unchanged, skipped=skipped)


def key_paths(value, prefix: str = "") -> set:
    """Every dotted key path in a JSON value, descending through arrays.

    An array contributes its elements' paths under a `[]` segment, unioned:
    the shape comes from one item schema, so a stale mock's elements all
    carry the same stale shape. A key present in some elements but not others
    is therefore reported as present — an inconsistency this check does not
    try to find.
    """
    out: set = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            out.add(path)
            out |= key_paths(child, path)
    elif isinstance(value, list):
        for item in value:
            out |= key_paths(item, f"{prefix}[]")
    return out


def empty_array_prefixes(value, prefix: str = "") -> set:
    """`[]`-terminated prefixes where *value* holds an empty array.

    An empty array is a legitimate instance of an array schema — the
    generator emits exactly that for its own `empty` scenario — so the
    element shape underneath it cannot be, and must not be, required.
    """
    out: set = set()
    if isinstance(value, dict):
        for key, child in value.items():
            out |= empty_array_prefixes(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        if not value:
            out.add(f"{prefix}[]")
        else:
            for item in value:
                out |= empty_array_prefixes(item, f"{prefix}[]")
    return out


def _drop_under(paths: set, prefixes: set) -> set:
    return {p for p in paths if not any(p.startswith(pref) for pref in prefixes)}


def required_paths(doc: OpenApiDoc, schema, path: str = "", _depth: int = 0) -> set:
    """Dotted paths a schema marks `required`, in `key_paths` notation."""
    out: set = set()
    if _depth > 12:
        return out
    schema = doc.resolve_schema(schema, _depth)
    if not isinstance(schema, dict):
        return out

    stype = schema.get("type")
    if stype is None and "properties" in schema:
        stype = "object"
    if isinstance(stype, list):
        stype = next((t for t in stype if t != "null"), None)

    if stype == "object":
        required = set(schema.get("required") or [])
        for name, child in (schema.get("properties") or {}).items():
            child_path = f"{path}.{name}"
            if name in required:
                out.add(child_path)
            out |= required_paths(doc, child, child_path, _depth + 1)
    elif stype == "array":
        items = schema.get("items")
        if items is not None:
            out |= required_paths(doc, items, f"{path}[]", _depth + 1)
    return out


def _ancestors(path: str) -> list:
    """Ancestor paths of *path*, shallowest first, in both `.a` and `.a[]` form."""
    out = []
    cur = path
    while True:
        index = cur.rfind(".")
        if index <= 0:
            break
        cur = cur[:index]
        out.append(cur)
        if cur.endswith("[]"):
            out.append(cur[:-2])
    return list(reversed(out))


def split_missing(missing: set, required: set) -> tuple:
    """`(required_missing, optional_missing)`.

    A path under an omitted OPTIONAL parent is optional too, however the
    schema marks it: leaving out `price_plan` legitimately leaves out
    `price_plan.id`, and reporting the child as a contract violation would be
    wrong. Classification therefore follows the shallowest omitted ancestor.
    """
    missing_set = set(missing)
    req: list = []
    opt: list = []
    for path in missing:
        anchor = path
        for ancestor in _ancestors(path):
            if ancestor in missing_set:
                anchor = ancestor
                break
        (req if anchor in required else opt).append(path)
    return sorted(req), sorted(opt)


@dataclass
class BodyDrift:
    """One scenario whose body no longer matches the schema it came from."""

    rel: str
    scenario: str
    missing: list[str]  # required by the contract, mock lacks
    extra: list[str]    # mock has, swagger lacks
    violations: list = field(default_factory=list)  # right keys, invalid values
    #: Optional fields the mock simply does not spell out. A note, not drift:
    #: omitting an optional field is a valid instance of the schema, and
    #: filling them in to silence the check is actively harmful — a
    #: mechanical merge puts null into non-nullable slots and manufactures
    #: real violations.
    optional: list = field(default_factory=list)
    #: A finding in generated/ is a warning — regenerating fixes it. One in a
    #: hand-written mock is an error: a person has to decide what it should be.
    generated: bool = False

    @property
    def is_note_only(self) -> bool:
        """True when nothing here is a contract violation."""
        return not (self.missing or self.extra or self.violations)

    def __str__(self) -> str:
        lines = [f"{self.rel}  {self.scenario}"]
        if self.missing:
            lines.append(f"    missing (required): {', '.join(self.missing)}")
        if self.extra:
            lines.append(f"    mock has, swagger lacks: {', '.join(self.extra)}")
        for violation in self.violations:
            lines.append(f"    {violation}")
        if self.optional:
            lines.append(f"    missing (optional): {', '.join(self.optional)}")
        return "\n".join(lines)


@dataclass
class CheckReport:
    missing: list[str]   # in swagger, no mock file
    orphaned: list[str]  # mock file, not in swagger
    drifted: list[str]   # unreadable mock files
    bodies: list        # scenario bodies that no longer match the schema
    unmatched: list[str]  # scenarios whose status is not declared — not compared
    misnamed: list[str] = field(default_factory=list)  # right route, other filename
    #: Findings in generated/: reported, but they do not fail the check.
    warnings: list[str] = field(default_factory=list)
    #: When set, a scenario that only omits optional fields counts as drift.
    strict: bool = False

    @property
    def errors(self) -> list:
        """Findings a person has to act on.

        Not every entry in `bodies` is one: a scenario that merely does not
        spell out some optional fields is recorded so it is visible, but a
        check that fails on it is a check that gets switched off — and then
        the real violations it also reports go with it.
        """
        return [b for b in self.bodies
                if not b.generated and (self.strict or not b.is_note_only)]

    @property
    def has_drift(self) -> bool:
        return bool(self.missing or self.orphaned or self.drifted or self.errors)


def _check(swagger_paths: list[str], mock_dir: Path, strict: bool = False) -> CheckReport:
    expected: dict[tuple, tuple[OpenApiDoc, Operation]] = {}
    for swagger in swagger_paths:
        doc = OpenApiDoc.load(swagger)
        if not doc.is_api_spec():
            continue
        for op in doc.operations():
            expected[route_key(op.method, op.path)] = (doc, op)

    drifted: list[str] = []
    existing: dict = {}
    op_ids: dict = {}
    if mock_dir.exists():
        for path in sorted(mock_dir.rglob("*.mock.json")):
            rel = str(path.relative_to(mock_dir))
            key = read_route(path)
            if key is None:
                drifted.append(f"{rel}: unreadable")
                continue
            existing[key] = rel
            try:
                with open(path, "r", encoding="utf-8") as f:
                    op_id = (json.load(f).get("source") or {}).get("operationId")
            except (OSError, json.JSONDecodeError):
                op_id = None
            if op_id:
                op_ids.setdefault(op_id, key)

    missing_keys = [k for k in expected if k not in existing]
    orphan_keys = [k for k in existing if k not in expected]

    # An endpoint whose path changed upstream would otherwise read as one
    # deleted mock plus one new one. Pairing them by operationId keeps the
    # old, more actionable message.
    paired: set = set()
    for key in sorted(missing_keys):
        _doc, op = expected[key]
        was = op_ids.get(op.operation_id)
        if was is not None and was in set(orphan_keys):
            drifted.append(
                f"{existing[was]}: source {was[0]} {was[1]} "
                f"!= swagger {key[0]} {key[1]}"
            )
            paired.add(key)
            paired.add(was)

    warnings: list[str] = []
    missing = sorted(
        f"{mock_relpath(expected[k][1])} ({k[0]} {k[1]})"
        for k in missing_keys if k not in paired
    )
    # A stale entry in generated/ is fixed by regenerating, so it is reported
    # rather than failed. One outside it needs a decision.
    orphaned = sorted(
        f"{existing[k]} ({k[0]} {k[1]})"
        for k in orphan_keys if k not in paired and not is_generated(existing[k])
    )
    warnings += sorted(
        f"{existing[k]} ({k[0]} {k[1]}) — stale generated mock, regenerate"
        for k in orphan_keys if k not in paired and is_generated(existing[k])
    )

    bodies: list[BodyDrift] = []
    unmatched: list[str] = []
    misnamed: list[str] = []
    for key in sorted(set(expected) & set(existing)):
        rel = existing[key]
        doc, op = expected[key]
        # Naming is a convention, not identity — reported so a rename is
        # visible, never as drift. Generated files always follow it.
        if not is_generated(rel) and rel != mock_relpath(op):
            misnamed.append(f"{rel} (scaffolding would name it {mock_relpath(op)})")
        try:
            with open(mock_dir / rel, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            drifted.append(f"{rel}: unreadable")
            continue
        _check_bodies(doc, op, rel, data, bodies, unmatched,
                      generated=is_generated(rel))

    return CheckReport(
        missing=missing, orphaned=orphaned, drifted=drifted,
        bodies=bodies, unmatched=unmatched, misnamed=misnamed,
        warnings=warnings, strict=strict,
    )


def _check_bodies(
    doc: OpenApiDoc,
    op: Operation,
    rel: str,
    data: dict,
    bodies: list,
    unmatched: list[str],
    generated: bool = False,
) -> None:
    """Compare every scenario body against the schema for its status code.

    Scenarios are matched by their declared `status`, never by name: a
    scenario called `not_found` is an error shape because it says 404, and a
    name-based rule mangles exactly those.
    """
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict):
        return

    for name, scenario in scenarios.items():
        if not isinstance(scenario, dict):
            continue
        status = scenario.get("status")
        if status is None:
            unmatched.append(f"{rel}  {name}: no status")
            continue
        if str(status) not in op.responses and "default" not in op.responses:
            # A deliberate edge case the spec does not describe — reported so
            # it is visible, but not drift: there is nothing to compare to.
            unmatched.append(f"{rel}  {name}: status {status} not declared")
            continue

        schema, content_type = _response_schema(op, status)
        if content_type is not None and content_type != "application/json":
            continue  # binary/file response — the author supplies the fixture
        if schema is None:
            continue  # no declared body (204 and friends)

        expected_body = doc.sample_for_schema(schema)
        actual_body = scenario.get("body")
        if actual_body is None:
            bodies.append(BodyDrift(rel, name, ["<body>"], [], generated=generated))
            continue

        want = key_paths(expected_body)
        got = key_paths(actual_body)
        # Neither side can describe the element shape of an array it holds
        # none of, so an empty array on either side excuses the other.
        want = _drop_under(want, empty_array_prefixes(actual_body))
        got = _drop_under(got, empty_array_prefixes(expected_body))
        violations = validate_against_schema(doc, schema, actual_body)
        missing_required, missing_optional = split_missing(
            want - got, required_paths(doc, schema)
        )
        if missing_required or missing_optional or want != got or violations:
            bodies.append(
                BodyDrift(
                    rel, name, sorted(missing_required), sorted(got - want),
                    violations=violations, generated=generated,
                    optional=sorted(missing_optional),
                )
            )


#: JSON types a schema `type` accepts, for the shape check below.
_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def validate_against_schema(doc: OpenApiDoc, schema, value, path: str = "", _depth: int = 0) -> list:
    """Schema violations in *value*: wrong types, missing `required`, bad enums.

    The key-set comparison above answers "does this mock still have the same
    shape". This answers "is it a valid instance" — a mock with `name: 42`
    where the contract says `string` has the right keys and is still a lie the
    tests will happily believe.

    Deliberately partial: `oneOf`/`anyOf` resolve to their first branch (the
    same simplification `sample_for_schema` makes), and unconstrained schemas
    pass. Reporting a real violation matters more than proving full
    conformance.
    """
    out: list = []
    if _depth > 12:
        return out
    schema = doc.resolve_schema(schema, _depth)
    if not isinstance(schema, dict):
        return out

    if value is None:
        # `nullable` is OpenAPI 3.0; 3.1 spells it as a `null` type member.
        types = schema.get("type")
        types = types if isinstance(types, list) else [types]
        if schema.get("nullable") or "null" in types:
            return out
        if schema.get("type") is not None:
            out.append(f"{path or '.'}: null, contract says {schema['type']}")
        return out

    stype = schema.get("type")
    if stype is None and "properties" in schema:
        stype = "object"
    if isinstance(stype, list):
        stype = next((t for t in stype if t != "null"), None)

    check = _TYPE_CHECKS.get(stype)
    if check is not None and not check(value):
        out.append(f"{path or '.'}: {type(value).__name__}, contract says {stype}")
        return out  # a wrong container makes everything under it noise

    enum = schema.get("enum")
    if isinstance(enum, list) and enum and value not in enum:
        out.append(f"{path or '.'}: {value!r} is not one of {enum}")

    if stype == "object":
        properties = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in value:
                out.append(f"{path}.{name}: required by the contract, missing")
        for name, child in value.items():
            if name in properties:
                out += validate_against_schema(
                    doc, properties[name], child, f"{path}.{name}", _depth + 1
                )
    elif stype == "array":
        items = schema.get("items")
        if items is not None:
            for index, item in enumerate(value):
                out += validate_against_schema(
                    doc, items, item, f"{path}[{index}]", _depth + 1
                )
    return out
