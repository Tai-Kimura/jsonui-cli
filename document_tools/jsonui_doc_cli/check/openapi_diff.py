"""builtin:openapi-diff — docs/api swagger ⇔ implementation-declared OpenAPI.

Comparison policy (plan 03 + review §3-1):
- paths × methods: bidirectional (missing_in_impl / missing_in_doc),
  impl-side framework paths ignored via globs.
- parameters / requestBody: name, required-ness, type.
- 2xx responses: compared per declared status code, deep schema diff,
  and 2xx code sets compared in BOTH directions (an impl-only 201 matters
  for DTO generation).
- 4xx/5xx responses: doc → impl presence check ONLY. Impl-side extras
  (e.g. FastAPI auto-422) are never reported.
- path parameter names: positional match; name difference is a warning.
- schema names: warning-level only (DTO generation uses doc-side names).

confidence is "proof" — but this proves agreement with the *declared*
implementation schema, not with live responses. The message string on the
summary row says so; renderers must too.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path

from .openapi_normalize import (
    DEFAULT_IGNORE_PATHS,
    DEFAULT_IGNORE_RESPONSE_CODES,
    NormOperation,
    NormSpec,
    normalize_spec,
)
from .report import CheckReport, ResultItem, compute_input_hashes


class OpenApiDiffError(Exception):
    """Checker-level execution failure (exit 2 territory)."""


def _is_swagger(data: dict) -> bool:
    return isinstance(data, dict) and ("openapi" in data or "swagger" in data)


def load_doc_side(api_dir: Path) -> tuple[NormSpec, list[Path]]:
    """Load and merge every swagger file under docs/api (recursive)."""
    merged = NormSpec()
    files: list[Path] = []
    for f in sorted(api_dir.rglob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OpenApiDiffError(f"failed to read {f}: {exc}")
        if not _is_swagger(data):
            continue
        files.append(f)
        one = normalize_spec(data, label=f.name)
        merged.schema_names |= one.schema_names
        merged.warnings += one.warnings
        for key, op in one.operations.items():
            if key in merged.operations:
                merged.warnings.append(
                    f"{f.name}: {key[1]} {op.path} already declared in another "
                    "doc file — first declaration wins"
                )
                continue
            merged.operations[key] = op
    if not files:
        raise OpenApiDiffError(f"no swagger files found under {api_dir}")
    return merged, files


def parse_impl_side(stdout: str) -> NormSpec:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise OpenApiDiffError(
            f"impl_openapi_command did not output valid JSON: {exc}"
        )
    if not _is_swagger(data):
        raise OpenApiDiffError(
            "impl_openapi_command output is not an OpenAPI document "
            "(no 'openapi'/'swagger' key)"
        )
    return normalize_spec(data, label="impl")


def _path_ignored(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def _in_generated_scope(path: str, include_globs: list[str],
                        exclude_globs: list[str]) -> bool:
    """Same semantics as jui's SchemaFilterConfig for endpoint paths:
    empty include list = all endpoints; excludes subtract."""
    if include_globs and not any(fnmatch.fnmatch(path, g)
                                 for g in include_globs):
        return False
    return not any(fnmatch.fnmatch(path, g) for g in exclude_globs)


def _schema_diffs(expected, actual, at: str) -> list[tuple[str, str, str]]:
    """Recursive structural diff of two normalized schemas.
    Returns (location, expected-summary, actual-summary) triples."""
    if expected == actual:
        return []
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return [(at, _summ(expected), _summ(actual))]

    diffs: list[tuple[str, str, str]] = []
    e_type, a_type = expected.get("type"), actual.get("type")
    if e_type != a_type:
        diffs.append((f"{at}.type", str(e_type), str(a_type)))
        return diffs  # type changed — deeper comparison is noise
    if bool(expected.get("nullable")) != bool(actual.get("nullable")):
        diffs.append((f"{at}.nullable",
                      str(bool(expected.get("nullable"))),
                      str(bool(actual.get("nullable")))))
    if "enum" in expected or "enum" in actual:
        e_enum = set(map(str, expected.get("enum", [])))
        a_enum = set(map(str, actual.get("enum", [])))
        if e_enum != a_enum:
            added = sorted(a_enum - e_enum)
            removed = sorted(e_enum - a_enum)
            parts = []
            if removed:
                parts.append(f"impl lacks: {removed}")
            if added:
                parts.append(f"impl adds: {added}")
            diffs.append((f"{at}.enum", ", ".join(sorted(e_enum)),
                          "; ".join(parts)))
    e_req = set(expected.get("required", []))
    a_req = set(actual.get("required", []))
    if e_req != a_req:
        diffs.append((f"{at}.required", str(sorted(e_req)), str(sorted(a_req))))

    e_props = expected.get("properties", {})
    a_props = actual.get("properties", {})
    for name in sorted(set(e_props) | set(a_props)):
        loc = f"{at}.{name}"
        if name not in a_props:
            diffs.append((loc, _summ(e_props[name]), "(missing)"))
        elif name not in e_props:
            diffs.append((loc, "(not in doc)", _summ(a_props[name])))
        else:
            diffs.extend(_schema_diffs(e_props[name], a_props[name], loc))

    if "items" in expected or "items" in actual:
        diffs.extend(_schema_diffs(expected.get("items", {}),
                                   actual.get("items", {}), f"{at}[]"))

    # string format matters (date-time / uuid / binary drive DTO types)
    if expected.get("format") != actual.get("format"):
        diffs.append((f"{at}.format", str(expected.get("format")),
                      str(actual.get("format"))))
    return diffs


def _summ(schema) -> str:
    if not isinstance(schema, dict):
        return str(schema)
    t = schema.get("type", "object" if "properties" in schema else "?")
    if schema.get("nullable"):
        t = f"{t}?"
    if "enum" in schema:
        t += f" enum{schema['enum']}"
    if t == "array" and isinstance(schema.get("items"), dict):
        t = f"array<{_summ(schema['items'])}>"
    return str(t)


def _compare_operation(doc_op: NormOperation, impl_op: NormOperation,
                       ignore_codes: set[str],
                       results: list[ResultItem],
                       warnings: list[str]) -> bool:
    """Compare one operation; append mismatches. Returns True if clean."""
    label = f"{doc_op.method} {doc_op.path}"
    clean = True

    if doc_op.param_names != impl_op.param_names:
        warnings.append(
            f"{label}: path parameter names differ "
            f"(doc {doc_op.param_names} / impl {impl_op.param_names})"
        )

    # parameters (query/header/path/cookie)
    for key in sorted(set(doc_op.parameters) | set(impl_op.parameters)):
        p_in, p_name = key
        # positional path params already covered by the name warning above
        if p_in == "path" and (key in doc_op.parameters) != (key in impl_op.parameters):
            continue
        t = f"{label} param {p_in}:{p_name}"
        if key not in impl_op.parameters:
            results.append(ResultItem(t, "missing_in_impl", "proof",
                                      expected=_summ(doc_op.parameters[key]["schema"])))
            clean = False
            continue
        if key not in doc_op.parameters:
            results.append(ResultItem(t, "missing_in_doc", "proof",
                                      actual=_summ(impl_op.parameters[key]["schema"])))
            clean = False
            continue
        d, i = doc_op.parameters[key], impl_op.parameters[key]
        if d["required"] != i["required"]:
            results.append(ResultItem(
                t, "mismatch", "proof",
                expected=f"required={d['required']}",
                actual=f"required={i['required']}"))
            clean = False
        # Optionality of a parameter is the `required` flag above; `nullable`
        # on a parameter schema is FastAPI's Optional[...] encoding and has
        # no wire meaning in a query string — comparing it only makes noise.
        d_schema = {k: v for k, v in (d["schema"] or {}).items()
                    if k != "nullable"}
        i_schema = {k: v for k, v in (i["schema"] or {}).items()
                    if k != "nullable"}
        for loc, exp, act in _schema_diffs(d_schema, i_schema, "schema"):
            results.append(ResultItem(f"{t} {loc}", "mismatch", "proof",
                                      expected=exp, actual=act))
            clean = False

    # requestBody
    if doc_op.request_body or impl_op.request_body:
        t = f"{label} requestBody"
        if doc_op.request_body and not impl_op.request_body:
            results.append(ResultItem(t, "missing_in_impl", "proof"))
            clean = False
        elif impl_op.request_body and not doc_op.request_body:
            results.append(ResultItem(t, "missing_in_doc", "proof",
                                      actual=_summ(impl_op.request_body["schema"])))
            clean = False
        else:
            d, i = doc_op.request_body, impl_op.request_body
            if d["required"] != i["required"]:
                results.append(ResultItem(
                    t, "mismatch", "proof",
                    expected=f"required={d['required']}",
                    actual=f"required={i['required']}"))
                clean = False
            for loc, exp, act in _schema_diffs(
                    d["schema"] or {}, i["schema"] or {}, "body"):
                results.append(ResultItem(f"{t} {loc}", "mismatch", "proof",
                                          expected=exp, actual=act))
                clean = False

    # responses
    doc_2xx = {c for c in doc_op.responses if c.startswith("2")}
    impl_2xx = {c for c in impl_op.responses if c.startswith("2")}
    for code in sorted(doc_2xx | impl_2xx):
        if code in ignore_codes:
            continue
        t = f"{label} → {code}"
        if code not in impl_op.responses:
            results.append(ResultItem(t, "missing_in_impl", "proof"))
            clean = False
            continue
        if code not in doc_op.responses:
            results.append(ResultItem(
                t, "missing_in_doc", "proof",
                actual=_summ(impl_op.responses[code]),
                message="impl declares an extra 2xx status"))
            clean = False
            continue
        doc_s = doc_op.responses[code] or {}
        impl_s = impl_op.responses[code] or {}
        # An empty schema means "shape not declared" (FastAPI without
        # response_model emits {}). Field-by-field diff against nothing is
        # noise — report one honest `skipped` per operation instead.
        if doc_s and not impl_s:
            results.append(ResultItem(
                t, "skipped", "proof",
                expected=_summ(doc_s),
                message="implementation does not declare a response schema "
                        "(e.g. FastAPI response_model missing) — cannot verify"))
            continue
        if impl_s and not doc_s:
            results.append(ResultItem(
                t, "skipped", "proof",
                actual=_summ(impl_s),
                message="doc does not declare a response schema — cannot verify"))
            continue
        for loc, exp, act in _schema_diffs(doc_s, impl_s, "body"):
            results.append(ResultItem(f"{t} {loc}", "mismatch", "proof",
                                      expected=exp, actual=act))
            clean = False

    # 4xx/5xx: doc → impl presence only (impl extras like auto-422 ignored)
    for code in sorted(c for c in doc_op.responses
                       if not c.startswith("2") and c not in ignore_codes):
        if code not in impl_op.responses:
            results.append(ResultItem(
                f"{label} → {code}", "missing_in_impl", "proof",
                message="error response declared in doc but not in impl"))
            clean = False

    return clean


def diff_specs(doc: NormSpec, impl: NormSpec,
               ignore_paths: list[str],
               ignore_codes: set[str]) -> tuple[list[ResultItem], list[str]]:
    results: list[ResultItem] = []
    warnings: list[str] = list(doc.warnings) + list(impl.warnings)

    doc_keys = set(doc.operations)
    impl_keys = set(impl.operations)

    for key in sorted(doc_keys - impl_keys):
        op = doc.operations[key]
        results.append(ResultItem(f"{op.method} {op.path}",
                                  "missing_in_impl", "proof",
                                  message="endpoint declared in docs/api but "
                                          "absent from implementation OpenAPI"))
    for key in sorted(impl_keys - doc_keys):
        op = impl.operations[key]
        if _path_ignored(op.path, ignore_paths):
            continue
        results.append(ResultItem(f"{op.method} {op.path}",
                                  "missing_in_doc", "proof",
                                  message="endpoint exists in implementation "
                                          "but is not documented"))

    for key in sorted(doc_keys & impl_keys):
        doc_op, impl_op = doc.operations[key], impl.operations[key]
        if _compare_operation(doc_op, impl_op, ignore_codes, results, warnings):
            results.append(ResultItem(f"{doc_op.method} {doc_op.path}",
                                      "ok", "proof"))

    missing_names = sorted(doc.schema_names - impl.schema_names)
    if missing_names:
        warnings.append(
            "schema names in docs/api not present in impl components "
            f"(warning only — structures are compared after $ref resolution): "
            f"{missing_names[:20]}"
        )
    return results, warnings


def run_openapi_diff(decl, project_root: Path, run_command) -> CheckReport:
    """Execute the builtin:openapi-diff checker.

    `run_command(argv, timeout_seconds) -> (exit_code, stdout, stderr)` is
    injected by the runner (keeps subprocess policy in one place)."""
    api_dir = project_root / "docs" / "api"
    if not api_dir.is_dir():
        raise OpenApiDiffError(f"docs/api not found under {project_root}")
    doc_spec, doc_files = load_doc_side(api_dir)

    code, stdout, stderr = run_command(decl.impl_openapi_command,
                                       decl.timeout_seconds)
    if code != 0:
        raise OpenApiDiffError(
            f"impl_openapi_command exited {code}: {stderr.strip()[:500]}"
        )
    impl_spec = parse_impl_side(stdout)

    ignore_paths = DEFAULT_IGNORE_PATHS + list(decl.ignore_paths)
    ignore_codes = DEFAULT_IGNORE_RESPONSE_CODES | set(decl.ignore_response_codes)

    # scope=generated: restrict both sides to the endpoints that feed DTO
    # generation (api.schemas include_paths/exclude_paths from jui.config.json)
    scope_note = None
    if decl.scope == "generated" and decl.api_path_filters:
        include_globs, exclude_globs = decl.api_path_filters
        before = len(doc_spec.operations) + len(impl_spec.operations)
        for spec in (doc_spec, impl_spec):
            spec.operations = {
                key: op for key, op in spec.operations.items()
                if _in_generated_scope(op.path, include_globs, exclude_globs)
            }
        after = len(doc_spec.operations) + len(impl_spec.operations)
        scope_note = (
            f"scope=generated: comparing only DTO-generation endpoints "
            f"(api.schemas path filters; {before - after} operations "
            "excluded from comparison)"
        )

    results, warnings = diff_specs(doc_spec, impl_spec, ignore_paths, ignore_codes)
    if scope_note:
        warnings.insert(0, scope_note)

    warnings.append(
        "This check compares the implementation's DECLARED OpenAPI schema; "
        "it does not verify live responses."
    )
    return CheckReport(
        checker=decl.name,
        target_kind="api",
        target_name="api",
        target_extra={"impl_command": " ".join(decl.impl_openapi_command)},
        input_hashes=compute_input_hashes(doc_files, project_root),
        results=results,
        warnings=warnings,
    )
