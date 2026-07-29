"""Scaffold mock definition files from OpenAPI specs, and report drift (--check).

Layout: <mockDir>/<tag-slug>/<operationId>.mock.json — one endpoint per file,
multiple scenarios inside. Regeneration SKIPS existing files (they are grown by
hand, like VM stubs), adding only new endpoints. --check reports adds/removes/
schema drift without writing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .openapi import OpenApiDoc, Operation, slugify


def mock_relpath(op: Operation) -> str:
    """Relative path (from mockDir) for an operation's mock file."""
    return f"{slugify(op.tag)}/{op.operation_id}.mock.json"


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
    created: list[str]
    skipped: list[str]
    warnings: list[str]


def generate(
    swagger_paths: list[str],
    mock_dir: str | Path,
    check: bool = False,
) -> GenerateReport | "CheckReport":
    """Scaffold (or, with check=True, diff) mock files for every operation."""
    mock_dir = Path(mock_dir)
    if check:
        return _check(swagger_paths, mock_dir)

    created: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []

    for swagger in swagger_paths:
        doc = OpenApiDoc.load(swagger)
        if not doc.is_api_spec():
            warnings.append(f"{swagger}: no paths (DB-model spec?) — skipped")
            continue
        for op in doc.operations():
            rel = mock_relpath(op)
            target = mock_dir / rel
            if op.id_was_synthesized:
                warnings.append(
                    f"{op.method} {op.path}: missing operationId -> synthesized '{op.operation_id}'"
                )
            if target.exists():
                skipped.append(rel)
                continue
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

    for swagger in swagger_paths:
        doc = OpenApiDoc.load(swagger)
        if not doc.is_api_spec():
            continue
        for op in doc.operations():
            rel = mock_relpath(op)
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


@dataclass
class BodyDrift:
    """One scenario whose body no longer matches the schema it came from."""

    rel: str
    scenario: str
    missing: list[str]  # swagger has, mock lacks
    extra: list[str]    # mock has, swagger lacks

    def __str__(self) -> str:
        lines = [f"{self.rel}  {self.scenario}"]
        if self.missing:
            lines.append(f"    swagger has, mock lacks: {', '.join(self.missing)}")
        if self.extra:
            lines.append(f"    mock has, swagger lacks: {', '.join(self.extra)}")
        return "\n".join(lines)


@dataclass
class CheckReport:
    missing: list[str]   # in swagger, no mock file
    orphaned: list[str]  # mock file, not in swagger
    drifted: list[str]   # path/method mismatch between mock source and swagger
    bodies: list        # scenario bodies that no longer match the schema
    unmatched: list[str]  # scenarios whose status is not declared — not compared

    @property
    def has_drift(self) -> bool:
        return bool(self.missing or self.orphaned or self.drifted or self.bodies)


def _check(swagger_paths: list[str], mock_dir: Path) -> CheckReport:
    expected: dict[str, tuple[OpenApiDoc, Operation]] = {}
    for swagger in swagger_paths:
        doc = OpenApiDoc.load(swagger)
        if not doc.is_api_spec():
            continue
        for op in doc.operations():
            expected[mock_relpath(op)] = (doc, op)

    existing = {
        str(p.relative_to(mock_dir))
        for p in mock_dir.rglob("*.mock.json")
    } if mock_dir.exists() else set()

    missing = sorted(set(expected) - existing)
    orphaned = sorted(existing - set(expected))

    drifted: list[str] = []
    bodies: list[BodyDrift] = []
    unmatched: list[str] = []
    for rel in sorted(set(expected) & existing):
        try:
            with open(mock_dir / rel, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            drifted.append(f"{rel}: unreadable")
            continue
        src = data.get("source", {})
        doc, op = expected[rel]
        if src.get("method") != op.method or src.get("path") != op.path:
            drifted.append(
                f"{rel}: source {src.get('method')} {src.get('path')} "
                f"!= swagger {op.method} {op.path}"
            )
        _check_bodies(doc, op, rel, data, bodies, unmatched)

    return CheckReport(
        missing=missing, orphaned=orphaned, drifted=drifted,
        bodies=bodies, unmatched=unmatched,
    )


def _check_bodies(
    doc: OpenApiDoc,
    op: Operation,
    rel: str,
    data: dict,
    bodies: list,
    unmatched: list[str],
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
            bodies.append(BodyDrift(rel, name, ["<body>"], []))
            continue

        want = key_paths(expected_body)
        got = key_paths(actual_body)
        # Neither side can describe the element shape of an array it holds
        # none of, so an empty array on either side excuses the other.
        want = _drop_under(want, empty_array_prefixes(actual_body))
        got = _drop_under(got, empty_array_prefixes(expected_body))
        if want != got:
            bodies.append(
                BodyDrift(rel, name, sorted(want - got), sorted(got - want))
            )
