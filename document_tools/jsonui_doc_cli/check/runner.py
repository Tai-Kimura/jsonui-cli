"""Executes declared checkers (doc-contract-check plan 01 §1/§6).

Exit codes (check command only — the rest of jsonui-doc stays 0/1):
    0 = all clean
    1 = mismatches found
    2 = checker execution error (connection failure, timeout, invalid
        plugin output, ...) — distinct from "docs and impl disagree"

Security policy enforced here:
- Only config-declared commands run (project_config validates paths).
- Every command is printed before it runs (same content as --list).
- shell=False, cwd=project root, mandatory timeout.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ..project_config import CheckDecl
from .report import (
    CheckReport,
    ReportValidationError,
    report_from_dict,
    save_report,
)

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_ERROR = 2


class CheckExecutionError(Exception):
    """Raised by checkers for exit-2 conditions."""


def run_subprocess(argv: list[str], timeout_seconds: int,
                   cwd: Path) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        raise CheckExecutionError(
            f"command timed out after {timeout_seconds}s: {' '.join(argv)}"
        )
    except FileNotFoundError as exc:
        raise CheckExecutionError(f"command not found: {exc}")


def describe_decl(decl: CheckDecl) -> str:
    if decl.type == "builtin:openapi-diff":
        cmd = " ".join(decl.impl_openapi_command or [])
        return (f"{decl.name}  [builtin:openapi-diff]  "
                f"docs/api ⇔ `{cmd}`  (timeout {decl.timeout_seconds}s)")
    if decl.type == "builtin:db-schema":
        source = (f"`{' '.join(decl.dump_command)}`" if decl.dump_command
                  else f"live connection via $JSONUI_CHECK_DB_URL_"
                       f"{decl.database.upper()}")
        return (f"{decl.name}  [builtin:db-schema]  "
                f"docs/db({decl.database}) ⇔ {source}  "
                f"(timeout {decl.timeout_seconds}s)")
    if decl.type in ("builtin:infra-iac", "builtin:infra-code", "builtin:infra-load"):
        against = {"builtin:infra-iac": "IaC (compose, terraform, cloudformation, k8s, wrangler)",
                   "builtin:infra-code": "the code (evidence, SDK imports, env names)",
                   "builtin:infra-load": "the load definitions (the cost simulator)"}[decl.type]
        return (f"{decl.name}  [{decl.type}]  infra model ⇔ {against}"
                f"{'  gate' if decl.gate else '  (warnings only)'}")
    return (f"{decl.name}  [checker]  `{' '.join(decl.command or [])}`  "
            f"(timeout {decl.timeout_seconds}s)")


def matches_filter(decl: CheckDecl, expr: str | None) -> bool:
    if not expr:
        return True
    if ":" in expr:
        kind, _, target = expr.partition(":")
        if kind == "db":
            return decl.type == "builtin:db-schema" and decl.database == target
        return decl.name == expr
    if expr == "db":
        return decl.type == "builtin:db-schema"
    if expr == "api":
        return decl.type == "builtin:openapi-diff"
    if expr == "infra":
        return decl.type in ("builtin:infra-iac", "builtin:infra-code", "builtin:infra-load")
    return decl.name == expr


def _run_full_checker(decl: CheckDecl, project_root: Path) -> CheckReport:
    code, stdout, stderr = run_subprocess(
        decl.command, decl.timeout_seconds, project_root)
    if code not in (0, 1):
        raise CheckExecutionError(
            f"checker '{decl.name}' exited {code}: {stderr.strip()[:500]}"
        )
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CheckExecutionError(
            f"checker '{decl.name}' stdout is not valid JSON: {exc}"
        )
    try:
        return report_from_dict(data, source=f"checker '{decl.name}' output")
    except ReportValidationError as exc:
        raise CheckExecutionError(str(exc))


def run_one(decl: CheckDecl, project_root: Path,
            databases: dict) -> CheckReport:
    def _cmd(argv: list[str], timeout: int) -> tuple[int, str, str]:
        return run_subprocess(argv, timeout, project_root)

    if decl.type == "builtin:openapi-diff":
        from .openapi_diff import OpenApiDiffError, run_openapi_diff
        try:
            return run_openapi_diff(decl, project_root, _cmd)
        except OpenApiDiffError as exc:
            raise CheckExecutionError(str(exc))
    if decl.type in ("builtin:infra-iac", "builtin:infra-code", "builtin:infra-load"):
        from .infra_check import InfraCheckError, run_infra_code, run_infra_iac, run_infra_load
        run = {"builtin:infra-iac": run_infra_iac, "builtin:infra-code": run_infra_code,
               "builtin:infra-load": run_infra_load}[decl.type]
        try:
            return run(decl, project_root)
        except InfraCheckError as exc:
            raise CheckExecutionError(str(exc))
    if decl.type == "builtin:db-schema":
        from .db_schema import DbSchemaError, run_db_schema_check
        try:
            return run_db_schema_check(decl, project_root, databases, _cmd)
        except DbSchemaError as exc:
            raise CheckExecutionError(str(exc))
    return _run_full_checker(decl, project_root)


def run_checks(decls: list[CheckDecl], project_root: Path,
               databases: dict,
               filter_expr: str | None = None,
               list_only: bool = False,
               as_json: bool = False) -> int:
    """Run the selected checks. as_json: stdout is one JSON object (what ran, each check's status, counts, the
    results that are not ok, its report's path) and every line the terminal would show goes to stderr — each command
    is still printed before it runs."""
    say = (lambda *a: print(*a, file=sys.stderr)) if as_json else print
    selected = [d for d in decls if matches_filter(d, filter_expr)]
    if not selected:
        if decls:
            say(f"No declared check matches '{filter_expr}'. Declared:")
            for d in decls:
                say(f"  - {describe_decl(d)}")
        else:
            say("No checks declared in jui.config.json "
                "(add a top-level \"checks\" array).")
        code = EXIT_ERROR if filter_expr else EXIT_OK
        if as_json:
            _print_json(code, [], declared=[_decl_dict(d) for d in decls])
        return code

    if list_only:
        say("Declared checks that would run:")
        for d in selected:
            say(f"  - {describe_decl(d)}")
        if as_json:
            _print_json(EXIT_OK, [], selected=[_decl_dict(d) for d in selected])
        return EXIT_OK

    had_error = False
    had_mismatch = False
    entries = []
    for decl in selected:
        say(f"▶ {describe_decl(decl)}")
        try:
            report = run_one(decl, project_root, databases)
        except CheckExecutionError as exc:
            say(f"  ✗ execution error: {exc}")
            had_error = True
            entries.append({**_decl_dict(decl), "status": "error", "error": str(exc)})
            continue
        path = save_report(report, project_root)
        s = report.summary
        status = "✗ MISMATCH" if report.has_mismatch else "✓ ok"
        # Counts first, then what they are counts OF and out of how many.
        # `ok=136` alone cannot distinguish 136-of-136 from 136-of-236, and a
        # consumer lane was reduced to inferring the unit from the spelling
        # of `target` strings to build its own gate.
        coverage = ""
        if report.unit and report.declared is not None:
            coverage = (f"  [{report.compared}/{report.declared} "
                        f"{report.unit}")
            if report.excluded:
                coverage += f", {report.excluded} excluded by config"
            if report.coverage_residual:
                coverage += f", {report.coverage_residual} unaccounted"
            coverage += "]"
        say(
            f"  {status}  ok={s['ok']} mismatch={s['mismatch']} "
            f"missing_in_impl={s['missing_in_impl']} "
            f"missing_in_doc={s['missing_in_doc']} skipped={s['skipped']}"
            + (f" warning={s['warning']}" if s.get("warning") else "")
            + coverage
        )
        for item in report.results:
            if item.status == "ok":
                continue
            line = f"    [{item.status}] {item.target}"
            if item.expected is not None or item.actual is not None:
                line += f"  expected={item.expected!r} actual={item.actual!r}"
            if item.message:
                line += f"  — {item.message}"
            say(line)
        for w in report.warnings:
            say(f"    (warning) {w}")
        say(f"  report: {path}")
        if report.has_mismatch:
            had_mismatch = True
        entries.append({**_decl_dict(decl), "status": "mismatch" if report.has_mismatch else "ok",
                        "summary": s, "results": [r.to_dict() for r in report.results if r.status != "ok"],
                        "warnings": list(report.warnings), "report": str(path)})

    code = EXIT_ERROR if had_error else EXIT_MISMATCH if had_mismatch else EXIT_OK
    if as_json:
        _print_json(code, entries)
    return code


def _decl_dict(decl: CheckDecl) -> dict:
    return {"name": decl.name, "type": decl.type}


def _print_json(code: int, checks: list[dict], **extra) -> None:
    print(json.dumps({"ok": code == EXIT_OK, "exit": code, "checks": checks, **extra}, ensure_ascii=False, indent=2))
