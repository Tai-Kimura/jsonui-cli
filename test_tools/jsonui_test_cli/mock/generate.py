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
    resp = op.responses.get(code) or {}
    content = resp.get("content") or {}
    if "application/json" in content:
        return content["application/json"].get("schema"), "application/json"
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
class CheckReport:
    missing: list[str]   # in swagger, no mock file
    orphaned: list[str]  # mock file, not in swagger
    drifted: list[str]   # path/method mismatch between mock source and swagger

    @property
    def has_drift(self) -> bool:
        return bool(self.missing or self.orphaned or self.drifted)


def _check(swagger_paths: list[str], mock_dir: Path) -> CheckReport:
    expected: dict[str, Operation] = {}
    for swagger in swagger_paths:
        doc = OpenApiDoc.load(swagger)
        if not doc.is_api_spec():
            continue
        for op in doc.operations():
            expected[mock_relpath(op)] = op

    existing = {
        str(p.relative_to(mock_dir))
        for p in mock_dir.rglob("*.mock.json")
    } if mock_dir.exists() else set()

    missing = sorted(set(expected) - existing)
    orphaned = sorted(existing - set(expected))

    drifted: list[str] = []
    for rel in sorted(set(expected) & existing):
        try:
            with open(mock_dir / rel, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            drifted.append(f"{rel}: unreadable")
            continue
        src = data.get("source", {})
        op = expected[rel]
        if src.get("method") != op.method or src.get("path") != op.path:
            drifted.append(
                f"{rel}: source {src.get('method')} {src.get('path')} "
                f"!= swagger {op.method} {op.path}"
            )

    return CheckReport(missing=missing, orphaned=orphaned, drifted=drifted)
