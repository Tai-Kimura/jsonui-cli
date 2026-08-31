"""builtin:db-schema checker entry point."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..report import CheckReport, compute_input_hashes
from .comparator import compare_schemas
from .doc_parser import parse_db_docs


class DbSchemaError(Exception):
    pass


def _resolve_db_dir(project_root: Path, database: str) -> Path:
    base = project_root / "docs" / "db"
    if database and database != "default":
        candidate = base / database
        if candidate.is_dir():
            return candidate
        raise DbSchemaError(
            f"docs/db/{database}/ not found — multi-DB layout expects one "
            "directory per database"
        )
    return base


def _validate_normalized(data, source: str) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("tables"), dict):
        raise DbSchemaError(
            f"{source}: normalized schema JSON must be an object with a "
            "'tables' object (see comparator.py docstring for the contract)"
        )
    return data


def run_db_schema_check(decl, project_root: Path, databases: dict,
                        run_command) -> CheckReport:
    db_dir = _resolve_db_dir(project_root, decl.database)
    if not db_dir.is_dir():
        raise DbSchemaError(f"{db_dir} not found")

    doc_tables = parse_db_docs(db_dir)
    if not doc_tables:
        raise DbSchemaError(f"no DB model JSON files found in {db_dir}")

    db_decl = databases.get(decl.database)

    # Actual schema: dump_command (zero-dependency path) or live connection
    if decl.dump_command:
        code, stdout, stderr = run_command(decl.dump_command,
                                           decl.timeout_seconds)
        if code != 0:
            raise DbSchemaError(
                f"dump_command exited {code}: {stderr.strip()[:500]}")
        try:
            actual = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise DbSchemaError(f"dump_command output is not valid JSON: {exc}")
        actual = _validate_normalized(actual, "dump_command")
        dialect = actual.get("dialect") or (db_decl.dialect if db_decl else "")
    else:
        env_key = f"JSONUI_CHECK_DB_URL_{decl.database.upper()}"
        url = os.environ.get(env_key)
        if not url:
            raise DbSchemaError(
                f"set {env_key} to the database URL (connection info never "
                "goes in config), or declare a dump_command"
            )
        from .dump_sqlalchemy import DumpAdapterError, dump_schema
        try:
            actual = dump_schema(url, db_decl.dialect if db_decl else None)
        except DumpAdapterError as exc:
            raise DbSchemaError(str(exc))
        dialect = actual.get("dialect", "")

    if not dialect:
        raise DbSchemaError(
            f"dialect unknown for database '{decl.database}' — declare it in "
            "jui.config.json databases section"
        )
    # normalize dialect aliases (mariadb → mysql family table)
    dialect = {"mariadb": "mysql", "postgres": "postgresql"}.get(
        dialect.lower(), dialect.lower())

    results = compare_schemas(
        doc_tables, actual, dialect, ignore_tables=decl.ignore_tables)

    input_files = sorted({t.source_file for t in doc_tables.values()})
    # `ignore_tables` only suppresses tables found in the database that the
    # docs do not describe; a documented table is always compared. So the
    # doc-side denominator and the compared count coincide here, and saying
    # so is the point — a reader cannot otherwise tell that this checker has
    # no partial-coverage mode.
    return CheckReport(
        checker=decl.name,
        target_kind="db",
        target_name=decl.database,
        target_extra={"dialect": dialect},
        input_hashes=compute_input_hashes(input_files, project_root),
        results=results,
        unit="table",
        declared=len(doc_tables),
        compared=len(doc_tables),
        excluded=0,
        inputs={"dialect": dialect,
                "doc_files": sorted(
                    str(p.resolve().relative_to(project_root.resolve()))
                    if p.resolve().is_relative_to(project_root.resolve())
                    else str(p)
                    for p in input_files)},
    )
