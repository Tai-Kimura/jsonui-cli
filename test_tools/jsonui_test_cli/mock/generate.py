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
import re
from dataclasses import dataclass, field
from pathlib import Path

from .openapi import OpenApiDoc, Operation, slugify
from .scope import PathScope


def mock_relpath(op: Operation) -> str:
    """Relative path (from mockDir) a freshly scaffolded mock is written to.

    A *naming convention*, not an identity. Files are matched by their
    `source` route — see `route_key` — because that is what the server routes
    on, and a project is free to name them however it likes.
    """
    return f"{slugify(op.tag)}/{op.operation_id}.mock.json"


#: Subdirectory of mockDir that `mock generate` owns outright.
GENERATED_DIR = "generated"

#: Filename of the editor schema every generated mock points `$schema` at.
#: A relative sibling is the one spelling an editor resolves with no project
#: configuration: the schema's `$id` is an identifier, not a fetchable address
#: (nothing serves it), and a repo-relative path would depend on where the
#: mockDir sits. Dot-prefixed because it is tool output living among authored
#: files.
EDITOR_SCHEMA_FILENAME = ".mock.schema.json"

#: Name the same schema ships under inside the package.
_BUNDLED_SCHEMA = "mock.schema.json"

#: The one spelling a mock's `$schema` may use. A copy is placed in *every*
#: directory that holds mocks, so the schema is always a sibling — which makes
#: `../.mock.schema.json` a reference to a file that is never written there.
#: Both spellings resolved to nothing while no copy existed anywhere, so the
#: split was invisible until the copies landed.
EDITOR_SCHEMA_REF = f"./{EDITOR_SCHEMA_FILENAME}"


def editor_schema_text() -> str:
    """The packaged editor schema, read the way `static/panel.html` is read.

    `static/*` ships as package-data (pyproject), so this resolves from a
    wheel or an editable install regardless of cwd. It is not read to
    validate anything — validation is the Python constants in
    `validation/mock.py` — so a broken install must degrade, never fail.
    """
    from importlib.resources import files
    return (files("jsonui_test_cli") / "static" / _BUNDLED_SCHEMA).read_text("utf-8")


def place_editor_schema(mock_dir: Path) -> list[str]:
    """Write the editor schema into every directory that holds mock files.

    Each mock says `"$schema": "./.mock.schema.json"`, so the copy has to sit
    beside the file naming it — at whatever depth, generated and hand-written
    alike. Placing one per directory is what keeps that single spelling true
    without the mock files having to know how deep they are, and without the
    generator computing `../..` chains.

    Returns the paths actually written (an unchanged copy is left alone, so a
    re-run reports nothing and touches no mtimes).
    """
    written: list[str] = []
    text = editor_schema_text()
    for directory in sorted({p.parent for p in mock_dir.rglob("*.mock.json")}):
        target = directory / EDITOR_SCHEMA_FILENAME
        try:
            if target.read_text(encoding="utf-8") == text:
                continue
        except (OSError, UnicodeDecodeError):
            pass
        target.write_text(text, encoding="utf-8")
        written.append(str(target.relative_to(mock_dir)))
    return written


def is_generated(rel) -> bool:
    """True for a path inside the generated tree (relative to mockDir)."""
    return Path(rel).parts[:1] == (GENERATED_DIR,)


def normalize_path_key(path: str) -> str:
    """Positional path normalization: /users/{user_id} -> /users/{}
    and trailing-slash insensitivity.

    A path template's variable *names* are not part of the URL it matches, and
    OpenAPI forbids two paths that differ only in them — so the name is
    documentation, and two spellings of one route have to compare equal.

    This is not a new rule: `builtin:openapi-diff` has paired doc-side and
    impl-side operations this way from the start
    (`jsonui_doc_cli/check/openapi_normalize.py`). The two tools are
    distributed independently and cannot import each other, so this is a
    second implementation of one decision — `test_normalize_path_key_parity`
    is what keeps it from becoming a second decision.
    """
    normalized = "/".join(
        "{}" if seg.startswith("{") and seg.endswith("}") else seg
        for seg in (path or "").split("/")
    )
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized


def route_key(method, path) -> tuple:
    """The identity of a mock: the route it serves.

    `mock serve` resolves a request by `source.method` + `source.path` and
    only falls back to the filename for a display id. The checker used to
    identify mocks by filename instead, so a project that names its files
    after the path rather than the operationId had every mock reported as
    both MISSING and ORPHAN — and the body comparison, which only runs on
    files matched to an operation, never executed at all.

    Matched on the normalized path for the same reason: renaming a path
    variable in the swagger (an edit that changes no HTTP contract) detached
    every hand-written mock on that route, and a detached mock is not
    reported as wrong — it is reported as ORPHAN and its body stops being
    checked at all.
    """
    return ((method or "GET").upper(), normalize_path_key(path or "/"))


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
        "$schema": EDITOR_SCHEMA_REF,
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
    #: routes the project's path scope excludes — not scaffolded
    out_of_scope: list[str] = field(default_factory=list)
    #: editor schema copies written this run (see `place_editor_schema`)
    schemas: list[str] = field(default_factory=list)


def _clear_generated(gen_root: Path) -> None:
    """Empty the generated tree, leaving anything that is not a mock alone."""
    if not gen_root.is_dir():
        return
    for path in gen_root.rglob("*.mock.json"):
        path.unlink()
    # The placed editor schemas go with them: they are tool output, they are
    # rewritten right after, and leaving one behind would keep a tag directory
    # that no longer has any mocks from ever being pruned.
    for path in gen_root.rglob(EDITOR_SCHEMA_FILENAME):
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
    scope: PathScope | None = None,
) -> GenerateReport | "CheckReport":
    """Regenerate `<mockDir>/generated/`, or (check=True) diff without writing.

    Deterministic: the same swagger and the same tool version produce the same
    bytes, which is what lets `generated/` be gitignored and rebuilt on a
    fresh clone rather than committed.

    `scope` narrows the swagger to the endpoints the project declares it
    consumes. Endpoints outside it are neither scaffolded nor counted as
    missing: a shared swagger's other realms are not this project's debt.
    """
    mock_dir = Path(mock_dir)
    scope = scope or PathScope()
    if check:
        return _check(swagger_paths, mock_dir, strict=strict, scope=scope)

    created: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    out_of_scope: list[str] = []
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
            if not scope.covers(op.path):
                out_of_scope.append(f"{op.method} {op.path}")
                continue
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

    schemas = _place_editor_schema_quietly(mock_dir, warnings)
    return GenerateReport(created=created, skipped=skipped, warnings=warnings,
                          out_of_scope=sorted(out_of_scope), schemas=schemas)


def _place_editor_schema_quietly(mock_dir: Path, warnings: list) -> list:
    """Place the editor schema, downgrading any failure to a warning.

    The schema is an authoring aid; the mocks it sits next to are the work.
    A packaging fault or a read-only tree must not fail a generation that
    otherwise succeeded — it must say so and leave the mocks in place.
    """
    try:
        return place_editor_schema(mock_dir)
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        warnings.append(
            f"editor schema not placed ({exc}) — the mocks are fine, but the "
            f"`$schema` line in them will not resolve in an editor")
        return []


@dataclass
class UpdateReport:
    updated: list[str]    # files whose default scenario or source changed
    unchanged: list[str]
    skipped: list[str]    # in swagger, no mock file — `generate` creates those
    #: `rel -> [added paths]`, so the caller can say what it actually did.
    added: dict = field(default_factory=dict)
    #: Findings a merge cannot fix — wrong types, undeclared fields.
    needs_review: list = field(default_factory=list)
    #: editor schema copies written this run (see `place_editor_schema`)
    schemas: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def add_missing_required(doc: OpenApiDoc, schema, body, path: str = "",
                         _depth: int = 0, keep_absent=()) -> list:
    """Fill in required fields the body lacks. Never touches a value it finds.

    A repair, not a regeneration. The `default` scenario is where a project
    grows the data its tests read — `mock generate` only ever scaffolds
    `default`, so there is nowhere else for that data to live — and replacing
    it with schema samples turns `"R-2026-04871"` back into `"string"` and
    reds out every assertion on it.

    `keep_absent` are paths the scenario declares it omits ON PURPOSE
    (`contractViolations.missing`). Filling those in would repair away the
    very condition a negative scenario exists to reproduce, and the test
    reading it would keep passing while proving nothing.
    """
    added: list = []
    keep = [(text, _violation_matcher(text)) for text in keep_absent]
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
            child_path = f"{path}.{name}"
            if name not in body and name in properties:
                if any(rx.match(child_path) for _, rx in keep):
                    continue  # declared as an intentional omission
                body[name] = doc.sample_for_schema(properties[name])
                added.append(child_path)
        for name, child in properties.items():
            if name in body:
                added += add_missing_required(
                    doc, child, body[name], f"{path}.{name}", _depth + 1,
                    keep_absent)
    elif stype == "array" and isinstance(body, list):
        items = schema.get("items")
        if items is not None:
            for index, element in enumerate(body):
                added += add_missing_required(
                    doc, items, element, f"{path}[{index}]", _depth + 1,
                    keep_absent)
    return added


def update_default(
    swagger_paths: list[str],
    mock_dir: str | Path,
    dry_run: bool = False,
    scope: PathScope | None = None,
) -> UpdateReport:
    """Repair the `default` scenario of each existing mock, in place.

    Adds the required fields the contract has and the body lacks, refreshes
    the `source` route, and **changes nothing else** — no existing value is
    overwritten and no field is removed. Other scenarios are not touched at
    all.

    Violations a merge cannot decide — a value of the wrong type, a field the
    contract does not have — are reported rather than guessed at.

    `scope` keeps endpoints the project does not consume out of `skipped`,
    which otherwise reads as "you are missing these mocks".
    """
    mock_dir = Path(mock_dir)
    scope = scope or PathScope()
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
            key = route_key(op.method, op.path)
            rel = existing.get(key) or mock_relpath(op)
            target = mock_dir / rel
            if not target.exists():
                # Out of scope and absent is the correct state, not a gap.
                if scope.covers(op.path):
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
                        declared = ViolationDeclaration.parse(
                            current.get("contractViolations"))
                        report_added = add_missing_required(
                            doc, schema, current["body"],
                            keep_absent=(declared.paths["missing"]
                                         if declared is not None else ()))
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

    # `--update-default` is the other half of the same command, and it is the
    # one a project runs after hand-writing a mock in a new directory — the
    # directory `generate` has no reason to revisit.
    warnings: list = []
    schemas = [] if dry_run else _place_editor_schema_quietly(mock_dir, warnings)
    return UpdateReport(updated=updated, unchanged=unchanged, skipped=skipped,
                        added=added, needs_review=needs_review,
                        schemas=schemas, warnings=warnings)


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


#: Categories of `contractViolations`, named after the `BodyDrift` field each
#: one subtracts from.
_VIOLATION_CATEGORIES = ("missing", "extra", "violations")


@dataclass
class ViolationDeclaration:
    """A scenario's declared, intentional contract violations.

    Some scenarios exist BECAUSE the body breaks the contract: a mock that
    omits a required field is how a test proves the client fails closed
    when the server omits it. Without a way to say so, those scenarios
    read as drift, the check never reaches zero, and a check that cannot
    reach zero stops being read — the same reasoning `BodyDrift.optional`
    already carries, applied to a violation the author put there on
    purpose.

    Declaring is deliberately narrow: name the paths, not the scenario. An
    undeclared violation in the same scenario still fails, because a
    negative scenario is exactly where an accidental drift hides best.
    """

    paths: dict          # category -> tuple[str, ...] as written
    reason: str
    errors: list = field(default_factory=list)   # malformed declaration

    @classmethod
    def parse(cls, raw) -> "ViolationDeclaration | None":
        if raw is None:
            return None
        errors: list = []
        paths: dict = {c: () for c in _VIOLATION_CATEGORIES}
        reason = ""
        if not isinstance(raw, dict):
            return cls(paths, "", ["contractViolations must be an object"])
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            # The ledger records WHY, or it is a suppression dump. A
            # violation nobody can explain is usually one nobody fixed.
            errors.append("contractViolations needs a non-empty 'reason'")
            reason = ""
        for key, value in raw.items():
            if key == "reason":
                continue
            if key not in _VIOLATION_CATEGORIES:
                errors.append(
                    f"unknown contractViolations key {key!r} "
                    f"(expected: {', '.join(_VIOLATION_CATEGORIES)}, reason)")
                continue
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or not all(
                    isinstance(p, str) for p in value):
                errors.append(f"contractViolations.{key} must be a list of paths")
                continue
            paths[key] = tuple(value)
        if not any(paths.values()) and not errors:
            errors.append(
                "contractViolations declares no paths — remove it, or name "
                "the paths this scenario violates on purpose")
        return cls(paths, reason.strip(), errors)


def _violation_matcher(declared: str):
    """Compile one declared path.

    `[]` matches any index at that level so a violation shared by every
    element of an array is one line; `[0]` still pins a single element.
    """
    parts = declared.split("[]")
    return re.compile("".join(
        re.escape(part) + (r"\[\d+\]" if index < len(parts) - 1 else "")
        for index, part in enumerate(parts)
    ) + r"\Z")


def _subtract_declared(found: "BodyFindings", decl: "ViolationDeclaration | None"):
    """Split findings into (still reported, declared paths that matched).

    A `violations` entry reads ``<path>: <what is wrong>``; the declared
    path is matched against the path half, so a declaration names a place,
    never a message the checker is free to reword.
    """
    if decl is None:
        return found, set()
    matchers = {
        category: [(text, _violation_matcher(text)) for text in decl.paths[category]]
        for category in _VIOLATION_CATEGORIES
    }
    used: set = set()
    kept = BodyFindings(optional=list(found.optional))
    for category in _VIOLATION_CATEGORIES:
        for entry in getattr(found, category):
            subject = entry.split(":", 1)[0] if category == "violations" else entry
            hit = next(
                (text for text, rx in matchers[category] if rx.match(subject)), None)
            if hit is None:
                getattr(kept, category).append(entry)
            else:
                used.add((category, hit))
    return kept, used


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
    #: Problems with the scenario's own `contractViolations` block: a
    #: declaration with no reason, a malformed one, or one that no longer
    #: matches anything. The last is the important one — when a declared
    #: violation stops happening, a negative scenario has quietly become a
    #: positive one and the test that reads it is no longer testing what it
    #: says. That has to be acted on, so these count as violations.
    declaration: list = field(default_factory=list)

    @property
    def is_note_only(self) -> bool:
        """True when nothing here is a contract violation."""
        return not (self.missing or self.extra or self.violations
                    or self.declaration)

    def __str__(self) -> str:
        lines = [f"{self.rel}  {self.scenario}"]
        if self.missing:
            lines.append(f"    missing (required): {', '.join(self.missing)}")
        if self.extra:
            lines.append(f"    mock has, swagger lacks: {', '.join(self.extra)}")
        for violation in self.violations:
            lines.append(f"    {violation}")
        for problem in self.declaration:
            lines.append(f"    {problem}")
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
    #: Mocks for routes the swagger declares but this project's scope excludes.
    #: Reported so an unused file is visible, never failed: the mirror image of
    #: the noise this scoping exists to remove.
    out_of_scope: list[str] = field(default_factory=list)
    #: How many swagger endpoints the scope filtered out, for the summary line.
    scope_excluded: int = 0
    #: Human-readable scope, echoed when it is in effect.
    scope_note: str = ""
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


def _check(swagger_paths: list[str], mock_dir: Path, strict: bool = False,
           scope: PathScope | None = None) -> CheckReport:
    scope = scope or PathScope()
    expected: dict[tuple, tuple[OpenApiDoc, Operation]] = {}
    #: normalized key -> the spelling that side wrote, for messages
    shown_swagger: dict[tuple, str] = {}
    shown_mock: dict[tuple, str] = {}
    excluded: dict[tuple, Operation] = {}
    for swagger in swagger_paths:
        doc = OpenApiDoc.load(swagger)
        if not doc.is_api_spec():
            continue
        for op in doc.operations():
            key = route_key(op.method, op.path)
            # Routes are matched normalized, but every message shows the
            # spelling its own side actually wrote: a report that answers
            # `/api/items/{}` sends the reader looking for a path that is in
            # neither file.
            shown_swagger[key] = f"{key[0]} {op.path}"
            if scope.covers(op.path):
                expected[key] = (doc, op)
            else:
                excluded[key] = op

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
                    source = (json.load(f).get("source") or {})
            except (OSError, json.JSONDecodeError):
                source = {}
            shown_mock[key] = f"{key[0]} {source.get('path') or key[1]}"
            op_id = source.get("operationId")
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
                f"{existing[was]}: source {shown_mock[was]} "
                f"!= swagger {shown_swagger[key]}"
            )
            paired.add(key)
            paired.add(was)

    warnings: list[str] = []
    missing = sorted(
        f"{mock_relpath(expected[k][1])} ({shown_swagger[k]})"
        for k in missing_keys if k not in paired
    )
    # A mock for a route the scope excludes is not an orphan — the swagger
    # still declares it, the project just does not consume it. Saying so
    # separately keeps ORPHAN meaning "no such endpoint any more", and lets
    # the file read as deletable without turning the gate red for it.
    out_of_scope = sorted(
        f"{existing[k]} ({shown_mock[k]})"
        for k in orphan_keys if k not in paired and k in excluded
    )
    orphan_keys = [k for k in orphan_keys if k not in excluded]

    # A stale entry in generated/ is fixed by regenerating, so it is reported
    # rather than failed. One outside it needs a decision.
    orphaned = sorted(
        f"{existing[k]} ({shown_mock[k]})"
        for k in orphan_keys if k not in paired and not is_generated(existing[k])
    )
    warnings += sorted(
        f"{existing[k]} ({shown_mock[k]}) — stale generated mock, regenerate"
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
        warnings=warnings, out_of_scope=out_of_scope,
        scope_excluded=len(excluded),
        scope_note=scope.describe() if scope.is_active() else "",
        strict=strict,
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
        decl = ViolationDeclaration.parse(scenario.get("contractViolations"))
        decl_problems = list(decl.errors) if decl is not None else []
        if decl is not None and generated:
            # `generated/` is rewritten wholesale from the swagger, so a
            # declaration here is deleted the next time anyone regenerates
            # — silently, and the scenario goes red again with no trace of
            # what was decided. Say so where it can still be moved.
            decl_problems.append(
                "contractViolations in a generated/ mock is deleted on the "
                "next regeneration — declare it on the hand-written mock "
                "that overlays this route")
        status = scenario.get("status")
        if status is None:
            unmatched.append(f"{rel}  {name}: no status")
            continue
        if str(status) not in op.responses and "default" not in op.responses:
            # A deliberate edge case the spec does not describe — reported so
            # it is visible, but not drift: there is nothing to compare to.
            unmatched.append(f"{rel}  {name}: status {status} not declared")
            _report_declaration_only(rel, name, decl_problems, bodies, generated)
            continue

        schema, content_type = _response_schema(op, status)
        if content_type is not None and content_type != "application/json":
            _report_declaration_only(rel, name, decl_problems, bodies, generated)
            continue  # binary/file response — the author supplies the fixture
        if schema is None:
            _report_declaration_only(rel, name, decl_problems, bodies, generated)
            continue  # no declared body (204 and friends)

        actual_body = scenario.get("body")
        if actual_body is None:
            bodies.append(BodyDrift(rel, name, ["<body>"], [], generated=generated,
                                    declaration=decl_problems))
            continue

        found = compare_to_schema(doc, schema, actual_body)
        found, used = _subtract_declared(found, decl)
        if decl is not None and not decl.errors:
            # A declaration that matches nothing is the dangerous half: the
            # body now satisfies the contract, so the scenario no longer
            # exercises the defence it was written for.
            decl_problems += [
                f"contractViolations.{category} declares {text!r}, which this "
                f"scenario no longer violates — the negative case it was "
                f"written for is gone; remove the line or restore the case"
                for category in _VIOLATION_CATEGORIES
                for text in decl.paths[category]
                if (category, text) not in used
            ]
        if (found.missing or found.optional or found.extra or found.violations
                or decl_problems):
            bodies.append(
                BodyDrift(
                    rel, name, sorted(found.missing), sorted(found.extra),
                    violations=found.violations, generated=generated,
                    optional=sorted(found.optional),
                    declaration=decl_problems,
                )
            )


def _report_declaration_only(rel: str, name: str, problems: list,
                             bodies: list, generated: bool) -> None:
    """Surface declaration problems on a scenario whose body is not compared.

    Nothing here is subtracted from, so a declaration on such a scenario is
    always wrong — but staying silent would let it rot unseen."""
    if problems:
        bodies.append(BodyDrift(rel, name, [], [], generated=generated,
                                declaration=list(problems)))


def validate_against_schema(doc: OpenApiDoc, schema, value, path: str = "") -> list:
    """Violations only — wrong types, absent `required`, bad enum members.

    The repair path uses this to report what it could not merge; the check
    path wants the notes too and calls `compare_to_schema` directly.
    """
    found = compare_to_schema(doc, schema, value, path)
    return found.violations + [
        f"{p}: required by the contract, missing" for p in sorted(found.missing)
    ]


