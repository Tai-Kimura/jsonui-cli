"""Validation for *.mock.json definition files.

Handwritten (mirrors screen.py / flow.py); the CLI does not depend on jsonschema.
schemas/mock.schema.json is an editor/doc asset, not the validation mechanism.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import ValidationMessage, ValidationResult

VALID_MOCK_KEYS = ["$schema", "source", "activeScenario", "scenarios"]
VALID_SOURCE_KEYS = ["swagger", "operationId", "method", "path"]
VALID_SCENARIO_KEYS = ["status", "headers", "body", "delayMs", "contentType",
                       "bodyFile", "contractViolations"]
VALID_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


_MOCK_INDEX_CACHE: dict = {}


def find_mock_index(test_file_path):
    """Locate the tests/mocks dir for a test file and index {operationId: {scenarios}}.

    Discovery: honor mock.mockDir in the nearest jui.config.json walking up from the
    test file; otherwise look for a 'tests/mocks' (or 'mocks') dir along the ancestry.
    Returns None if no mock dir is found (existence checks are then skipped).
    """
    if test_file_path is None:
        return None
    start = Path(test_file_path).resolve().parent
    mock_dir = None
    for parent in [start, *start.parents]:
        config = parent / "jui.config.json"
        if config.exists():
            try:
                with open(config, "r", encoding="utf-8") as f:
                    rel = (json.load(f).get("mock", {}) or {}).get("mockDir")
                if rel:
                    cand = (parent / rel)
                    if cand.exists():
                        mock_dir = cand
                        break
            except (OSError, json.JSONDecodeError):
                pass
        for name in ("tests/mocks", "mocks"):
            cand = parent / name
            if cand.is_dir():
                mock_dir = cand
                break
        if mock_dir:
            break
    if mock_dir is None:
        return None

    key = str(mock_dir.resolve())
    if key in _MOCK_INDEX_CACHE:
        return _MOCK_INDEX_CACHE[key]

    index: dict[str, set] = {}
    for f in mock_dir.rglob("*.mock.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        op_id = (data.get("source", {}) or {}).get("operationId") or f.stem.replace(".mock", "")
        index[op_id] = set((data.get("scenarios", {}) or {}).keys())
    _MOCK_INDEX_CACHE[key] = index
    return index


def validate_mock_reference(mapping, path: str, result: ValidationResult, index):
    """Validate a {operationId: scenario} map (root `mocks` or a setMocks step)."""
    if not isinstance(mapping, dict):
        result.errors.append(ValidationMessage(
            path=path, message=f"'mocks' must be an object of operationId -> scenario, got: {type(mapping).__name__}"))
        return
    for op_id, scenario in mapping.items():
        if not isinstance(scenario, str):
            result.errors.append(ValidationMessage(
                path=f"{path}.{op_id}", message=f"scenario name must be a string, got: {type(scenario).__name__}"))
            continue
        if index is None:
            continue  # no mock dir discoverable; skip existence check
        if op_id not in index:
            result.errors.append(ValidationMessage(
                path=f"{path}.{op_id}", message=f"unknown mock operationId '{op_id}' (not in tests/mocks)"))
        elif scenario not in index[op_id]:
            result.errors.append(ValidationMessage(
                path=f"{path}.{op_id}",
                message=f"mock '{op_id}' has no scenario '{scenario}' (available: {sorted(index[op_id])})"))


class MockValidator:
    """Validates a single mock definition file."""

    def _check_schema_ref(self, data, path: str, result: ValidationResult):
        """The `$schema` reference must be the sibling spelling, or absent.

        `mock generate` places a copy of the schema in every directory that
        holds mocks, so the reference is a sibling everywhere. A `../` form
        points at a directory that never receives one — it resolves to
        nothing and the editor silently stops checking the file, which is
        indistinguishable from a file with no problems.

        Only the spelling is checked, never whether the file is there: a
        project is free to gitignore the placed copies, and a fresh CI
        checkout would then fail on every mock it has. The spelling is the
        tool's own convention, so it is decidable without the file and
        reaches zero regardless of that choice.
        """
        if "$schema" not in data:
            return  # generated mocks carry one; omitting it by hand is fine
        from ..mock.generate import EDITOR_SCHEMA_REF
        found = data["$schema"]
        if found == EDITOR_SCHEMA_REF:
            return
        result.errors.append(ValidationMessage(
            path=f"{path}.$schema",
            message=(f"'$schema' must be '{EDITOR_SCHEMA_REF}', got: {found!r}. "
                     "The schema is placed in every directory that holds mocks, "
                     "so the reference is always a sibling; another spelling "
                     "resolves to nothing and the editor stops checking this "
                     "file without saying so.")))

    def validate(self, data, path: str, result: ValidationResult):
        if not isinstance(data, dict):
            result.errors.append(ValidationMessage(path=path, message="Mock file must be a JSON object"))
            return

        for key in data:
            if key not in VALID_MOCK_KEYS:
                result.warnings.append(ValidationMessage(
                    path=path, message=f"Unknown mock key: {key}", level="warning"))

        self._check_schema_ref(data, path, result)

        source = data.get("source")
        if not isinstance(source, dict):
            result.errors.append(ValidationMessage(path=f"{path}.source", message="'source' is required and must be an object"))
        else:
            for key in source:
                if key not in VALID_SOURCE_KEYS:
                    result.warnings.append(ValidationMessage(
                        path=f"{path}.source", message=f"Unknown source key: {key}", level="warning"))
            method = source.get("method")
            if method and method.upper() not in VALID_METHODS:
                result.errors.append(ValidationMessage(
                    path=f"{path}.source.method", message=f"Invalid method: {method}"))
            if not source.get("path"):
                result.errors.append(ValidationMessage(
                    path=f"{path}.source.path", message="'source.path' is required for routing"))

        scenarios = data.get("scenarios")
        if not isinstance(scenarios, dict) or not scenarios:
            result.errors.append(ValidationMessage(
                path=f"{path}.scenarios", message="'scenarios' is required and must be a non-empty object"))
            return

        for name, scenario in scenarios.items():
            spath = f"{path}.scenarios.{name}"
            if not isinstance(scenario, dict):
                result.errors.append(ValidationMessage(path=spath, message="scenario must be an object"))
                continue
            for key in scenario:
                if key not in VALID_SCENARIO_KEYS:
                    result.warnings.append(ValidationMessage(
                        path=spath, message=f"Unknown scenario key: {key}", level="warning"))
            status = scenario.get("status")
            if not isinstance(status, int) or not (100 <= status <= 599):
                result.errors.append(ValidationMessage(
                    path=f"{spath}.status", message=f"'status' must be an HTTP status int, got: {status!r}"))
            if "delayMs" in scenario and not isinstance(scenario["delayMs"], (int, float)):
                result.errors.append(ValidationMessage(
                    path=f"{spath}.delayMs", message="'delayMs' must be a number"))

        active = data.get("activeScenario", "default")
        if active not in scenarios:
            result.errors.append(ValidationMessage(
                path=f"{path}.activeScenario",
                message=f"activeScenario '{active}' is not among scenarios: {list(scenarios.keys())}"))
