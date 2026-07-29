"""Request-side contract checking for `jsonui-test mock serve`.

The mock server answers from a fixed scenario without looking at what the app
sent, so a screen can omit every required field, send a mode *name* where the
contract wants a uuid, and pass an empty string for an id — and the E2E suite
stays green for months. That has happened; the real API returns 422 for all
three, and it surfaced only when someone tried to port the screen elsewhere.

This module gives the server the missing half: the request is compared against
the operation's `requestBody` and `parameters`, and violations are recorded.

**The request is still served.** A contract violation is not "this screen
should show an error" — it is "the implementation does not satisfy the
contract", and turning it into a 422 would rewrite the meaning of every test
that touches the endpoint and bury the cause under a cascade of red. So the
run continues and the violations surface as a summary with a non-zero exit at
the end, where they read as what they are.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .generate import route_key, validate_against_schema
from .openapi import OpenApiDoc


@dataclass
class RequestViolation:
    method: str
    path: str
    operation_id: str
    problems: list

    def __str__(self) -> str:
        head = f"{self.method} {self.path} ({self.operation_id})"
        return "\n".join([head] + [f"    {p}" for p in self.problems])


@dataclass
class ContractIndex:
    """Swagger operations, keyed the way the mock server routes."""

    #: route_key -> (doc, operation)
    operations: dict = field(default_factory=dict)

    @classmethod
    def load(cls, swagger_paths) -> "ContractIndex":
        index = cls()
        for swagger in swagger_paths or []:
            try:
                doc = OpenApiDoc.load(swagger)
            except (OSError, ValueError):
                continue
            if not doc.is_api_spec():
                continue
            for op in doc.operations():
                index.operations[route_key(op.method, op.path)] = (doc, op)
        return index

    def __bool__(self) -> bool:
        return bool(self.operations)

    def check(self, method: str, mock_path: str, query: dict, body) -> list:
        """Contract problems with one request, matched by its mock's route.

        `mock_path` is the endpoint's declared template (`/api/bars/{id}`),
        not the concrete URL — the server already resolved the route, so
        re-matching the literal path here would only reintroduce the
        identity mismatch this tool just got rid of.
        """
        entry = self.operations.get(route_key(method, mock_path))
        if entry is None:
            return []
        doc, op = entry
        problems: list = []
        problems += _check_parameters(doc, op, query)
        problems += _check_body(doc, op, body)
        return problems


def _params(op) -> list:
    raw = getattr(op, "parameters", None) or []
    return [p for p in raw if isinstance(p, dict)]


def _check_parameters(doc: OpenApiDoc, op, query: dict) -> list:
    """Required query parameters, and the types of the ones that are present.

    Path parameters are not checked: the server matched the route by regex,
    so a missing one could not have got here, and its raw value is a string
    whichever type the contract declares.
    """
    problems: list = []
    for param in _params(op):
        if param.get("in") != "query":
            continue
        name = param.get("name")
        if not name:
            continue
        values = query.get(name)
        if not values:
            if param.get("required"):
                problems.append(f"query '{name}': required by the contract, missing")
            continue
        schema = param.get("schema")
        if not isinstance(schema, dict):
            continue
        for value in values:
            problems += validate_against_schema(
                doc, schema, _coerce(schema, value), f"query '{name}'"
            )
    return problems


def _coerce(schema: dict, value: str):
    """Query values arrive as strings; read them as the declared type.

    A mistyped value is still caught — "abc" does not become an integer.
    """
    stype = schema.get("type")
    if stype == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if stype == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if stype == "boolean":
        if value in ("true", "false"):
            return value == "true"
    return value


def _check_body(doc: OpenApiDoc, op, body) -> list:
    request_body = getattr(op, "request_body", None)
    if not isinstance(request_body, dict):
        return []
    content = request_body.get("content") or {}
    schema = (content.get("application/json") or {}).get("schema")
    if schema is None:
        return []
    if body is None:
        if request_body.get("required"):
            return ["body: required by the contract, missing"]
        return []
    return validate_against_schema(doc, schema, body, "body")


class ContractLog:
    """Thread-safe record of contract violations seen during a run."""

    def __init__(self):
        self._lock = threading.Lock()
        self._violations: list = []

    def record(self, violation: RequestViolation):
        with self._lock:
            self._violations.append(violation)

    def all(self) -> list:
        with self._lock:
            return list(self._violations)

    def count(self) -> int:
        with self._lock:
            return len(self._violations)

    def since(self, index: int) -> list:
        with self._lock:
            return list(self._violations[index:])

    def summary(self, index: int = 0) -> list:
        """Report lines for the violations recorded after *index*.

        Deduplicated by route + problem: one broken screen hit in a loop
        would otherwise bury everything else.
        """
        seen: dict = {}
        for violation in self.since(index):
            key = (violation.method, violation.path, tuple(violation.problems))
            seen[key] = seen.get(key, 0) + violation_weight(violation)
        if not seen:
            return []
        lines = [
            f"{len(seen)} request contract violation(s) — the app sent something "
            "the API would reject:"
        ]
        for (method, path, problems), count in seen.items():
            times = f" (x{count})" if count > 1 else ""
            lines.append(f"  {method} {path}{times}")
            lines += [f"    {p}" for p in problems]
        lines.append(
            "Set mock.validateRequests=false in jui.config.json, or "
            '"skipRequestValidation": true on a scenario, to allow one.'
        )
        return lines


def violation_weight(_violation) -> int:
    return 1
