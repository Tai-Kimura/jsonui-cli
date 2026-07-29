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
    updated: list[str]    # files whose default scenario or source changed
    unchanged: list[str]
    skipped: list[str]    # in swagger, no mock file — `generate` creates those
    #: `rel -> [added paths]`, so the caller can say what it actually did.
    added: dict = field(default_factory=dict)
    #: Findings a merge cannot fix — wrong types, undeclared fields.
    needs_review: list = field(default_factory=list)


def add_missing_required(doc: OpenApiDoc, schema, body, path: str = "", _depth: int = 0) -> list:
    """Fill in required fields the body lacks. Never touches a value it finds.

    A repair, not a regeneration. The `default` scenario is where a project
    grows the data its tests read — `mock generate` only ever scaffolds
    `default`, so there is nowhere else for that data to live — and replacing
    it with schema samples turns `"R-2026-04871"` back into `"string"` and
    reds out every assertion on it.
    """
    added: list = []
    if _depth > 12:
        return added
    schema = doc.resolve_schema(schema, _depth)
    if not isinstance(schema, dict):
        return added

    stype = schema.get("type")
    if stype is None and "properties" in schema:
        stype = "object"
    if isinstance(stype, list):
        stype = next((t for t in stype if t != "null"), None)

    if stype == "object" and isinstance(body, dict):
        properties = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in body and name in properties:
                body[name] = doc.sample_for_schema(properties[name])
                added.append(f"{path}.{name}")
        for name, child in properties.items():
            if name in body:
                added += add_missing_required(
                    doc, child, body[name], f"{path}.{name}", _depth + 1)
    elif stype == "array" and isinstance(body, list):
        items = schema.get("items")
        if items is not None:
            for index, element in enumerate(body):
                added += add_missing_required(
                    doc, items, element, f"{path}[{index}]", _depth + 1)
    return added


def update_default(
    swagger_paths: list[str],
    mock_dir: str | Path,
    dry_run: bool = False,
) -> UpdateReport:
    """Repair the `default` scenario of each existing mock, in place.

    Adds the required fields the contract has and the body lacks, refreshes
    the `source` route, and **changes nothing else** — no existing value is
    overwritten and no field is removed. Other scenarios are not touched at
    all.

    Violations a merge cannot decide — a value of the wrong type, a field the
    contract does not have — are reported rather than guessed at.
    """
    mock_dir = Path(mock_dir)
    updated: list[str] = []
    unchanged: list[str] = []
    skipped: list[str] = []
    added: dict = {}
    needs_review: list = []
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

            # Only the ROUTE is regenerated. `swagger` records where the file
            # was authored from, and `operationId` is the key test files use
            # to select a scenario (`mocks: { "<operationId>": ... }`) — the
            # server routes by method+path and only reports a naming
            # difference, so renaming it here silently detaches every
            # reference to it while `scenario-set` still answers 200.
            source = dict(data.get("source") or {})
            source["method"] = fresh["source"]["method"]
            source["path"] = fresh["source"]["path"]
            source.setdefault("operationId", fresh["source"]["operationId"])
            source.setdefault("swagger", fresh["source"]["swagger"])
            data["source"] = source

            scenarios = data.get("scenarios")
            if isinstance(scenarios, dict):
                current = scenarios.get("default")
                if not isinstance(current, dict):
                    # Nothing to repair in place — scaffold the whole scenario.
                    scenarios["default"] = fresh["scenarios"]["default"]
                else:
                    fresh_default = fresh["scenarios"]["default"]
                    schema, content_type = _response_schema(
                        op, current.get("status", fresh_default.get("status")))
                    if "body" not in current and "body" in fresh_default:
                        current["body"] = fresh_default["body"]
                        report_added = ["<body>"]
                    elif (schema is not None
                          and content_type == "application/json"
                          and current.get("body") is not None):
                        report_added = add_missing_required(
                            doc, schema, current["body"])
                    else:
                        report_added = []
                    if report_added:
                        added[rel] = report_added
                    if schema is not None and current.get("body") is not None:
                        problems = validate_against_schema(
                            doc, schema, current["body"])
                        # Everything the merge just fixed is gone from this
                        # list; what remains needs a person.
                        if problems:
                            needs_review.append((rel, problems))

            if json.dumps(data, ensure_ascii=False, sort_keys=True) == before:
                unchanged.append(rel)
                continue
            if not dry_run:
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            updated.append(rel)

    return UpdateReport(updated=updated, unchanged=unchanged, skipped=skipped,
                        added=added, needs_review=needs_review)


@dataclass
class BodyFindings:
    """What one body is, measured against its schema."""

    violations: list = field(default_factory=list)  # wrong type / enum / null
    missing: list = field(default_factory=list)     # required, absent
    optional: list = field(default_factory=list)    # optional, absent
    extra: list = field(default_factory=list)       # not in the contract

    def merge(self, other: "BodyFindings") -> "BodyFindings":
        self.violations += other.violations
        self.missing += other.missing
        self.optional += other.optional
        self.extra += other.extra
        return self


#: JSON types a schema `type` accepts.
_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def compare_to_schema(doc: OpenApiDoc, schema, value, path: str = "",
                      _depth: int = 0) -> BodyFindings:
    """Walk a body and its schema together.

    Together, not as two flattened key sets. A set difference has to pick one
    representative shape for a whole array, which produced two false
    positives: a `nullable` array holding `null` was asked for its element
    shape, and one empty element made the OTHER elements' fields read as
    undeclared. Descending per element with an indexed path removes the class
    — and says which element is at fault.
    """
    out = BodyFindings()
    if _depth > 12:
        return out
    schema = doc.resolve_schema(schema, _depth)
    if not isinstance(schema, dict):
        return out

    types = schema.get("type")
    type_list = types if isinstance(types, list) else [types]
    if value is None:
        # `nullable` is OpenAPI 3.0; 3.1 spells it as a `null` type member.
        # Either way there is no substructure to compare — an absent array is
        # not an array of absent elements.
        if schema.get("nullable") or "null" in type_list or types is None:
            return out
        out.violations.append(f"{path or '.'}: null, contract says {types}")
        return out

    stype = types
    if stype is None and "properties" in schema:
        stype = "object"
    if isinstance(stype, list):
        stype = next((t for t in stype if t != "null"), None)

    check = _TYPE_CHECKS.get(stype)
    if check is not None and not check(value):
        out.violations.append(
            f"{path or '.'}: {type(value).__name__}, contract says {stype}")
        return out  # a wrong container makes everything under it noise

    enum = schema.get("enum")
    if isinstance(enum, list) and enum and value not in enum:
        out.violations.append(f"{path or '.'}: {value!r} is not one of {enum}")

    if stype == "object":
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        additional = schema.get("additionalProperties")
        for name, child in properties.items():
            child_path = f"{path}.{name}"
            if name in value:
                out.merge(compare_to_schema(doc, child, value[name], child_path, _depth + 1))
            elif name in required:
                out.missing.append(child_path)
            else:
                out.optional.append(child_path)
        if properties and additional is not True and not isinstance(additional, dict):
            for name in value:
                if name not in properties:
                    out.extra.append(f"{path}.{name}")
    elif stype == "array":
        items = schema.get("items")
        if items is not None:
            for index, element in enumerate(value):
                out.merge(compare_to_schema(
                    doc, items, element, f"{path}[{index}]", _depth + 1))
    return out


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

        actual_body = scenario.get("body")
        if actual_body is None:
            bodies.append(BodyDrift(rel, name, ["<body>"], [], generated=generated))
            continue

        found = compare_to_schema(doc, schema, actual_body)
        if found.missing or found.optional or found.extra or found.violations:
            bodies.append(
                BodyDrift(
                    rel, name, sorted(found.missing), sorted(found.extra),
                    violations=found.violations, generated=generated,
                    optional=sorted(found.optional),
                )
            )


def validate_against_schema(doc: OpenApiDoc, schema, value, path: str = "") -> list:
    """Violations only — wrong types, absent `required`, bad enum members.

    The repair path uses this to report what it could not merge; the check
    path wants the notes too and calls `compare_to_schema` directly.
    """
    found = compare_to_schema(doc, schema, value, path)
    return found.violations + [
        f"{p}: required by the contract, missing" for p in sorted(found.missing)
    ]


