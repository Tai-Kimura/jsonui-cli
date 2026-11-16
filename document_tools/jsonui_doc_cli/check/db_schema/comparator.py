"""Pure comparator: doc tables ⇔ normalized actual schema.

Normalized actual-schema JSON contract (produced by the SQLAlchemy dump
adapter OR any project `dump_command` — this shape is a public contract):

{
  "schemaVersion": 1,
  "dialect": "mysql",
  "tables": {
    "reservations": {
      "columns": {
        "id": {"type": "INT", "nullable": false, "primary_key": true,
                "auto_increment": true}
      },
      "primary_key": ["id"],
      "uniques": [["email"], ["location_id", "mode"]],
      "indexes": [{"columns": ["slot_id", "status"], "unique": false,
                    "name": "idx_x"}],
      "foreign_keys": [{"columns": ["user_id"], "ref_table": "users",
                          "ref_columns": ["id"]}]
    }
  }
}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..report import ResultItem
from .doc_parser import DocTable

# ORM / migration bookkeeping tables never documented (plan 02 §2)
DEFAULT_IGNORE_TABLES = [
    "alembic_version", "schema_migrations", "django_migrations",
    "flyway_schema_history", "ar_internal_metadata", "_prisma_migrations",
    "knex_migrations", "knex_migrations_lock", "typeorm_metadata",
    "migrations",
]

_FAMILIES_PATH = Path(__file__).parent / "type_families.json"
_families_cache: dict | None = None


def _families() -> dict:
    global _families_cache
    if _families_cache is None:
        _families_cache = json.loads(_FAMILIES_PATH.read_text(encoding="utf-8"))
    return _families_cache


def base_type(db_type: str) -> str:
    """'VARCHAR(255)' -> 'VARCHAR', 'timestamp with time zone' -> 'TIMESTAMP'."""
    m = re.match(r"\s*([A-Za-z0-9_-]+)", db_type or "")
    token = (m.group(1) if m else "").upper()
    # postgres reflection spells these out
    if token == "TIMESTAMP" or (db_type or "").upper().startswith("TIMESTAMP"):
        return "TIMESTAMP"
    if token == "DOUBLE":
        return "DOUBLE"
    return token


def _exact_norm(db_type: str) -> str:
    return re.sub(r"\s+", "", (db_type or "").upper())


def type_matches(col, actual_type: str, dialect: str) -> tuple[bool, str]:
    """Return (matches, expected_description)."""
    if col.db_type:
        # x-db-type opt-in → exact match
        expected = col.db_type
        return _exact_norm(actual_type) == _exact_norm(expected), expected
    fam = _families().get("mysql" if dialect == "mariadb" else dialect)
    if fam is None:
        return True, f"(no type table for dialect '{dialect}' — skipped)"
    actual_base = base_type(actual_type)
    if col.enum_values and col.enum_as_int:
        allowed = fam.get("_enum_int", [])
        return actual_base in allowed, f"integer enum code ({'/'.join(allowed)})"
    key = (f"{col.openapi_type}:{col.openapi_format}"
           if col.openapi_format else col.openapi_type)
    allowed = fam.get(key) or fam.get(col.openapi_type)
    if not allowed:
        return True, f"(no family for '{key}' — skipped)"
    label = key + " → " + "/".join(allowed[:4]) + ("…" if len(allowed) > 4 else "")
    return actual_base in allowed, label


def compare_schemas(
    doc_tables: dict[str, DocTable],
    actual: dict,
    dialect: str,
    ignore_tables: list[str] | None = None,
) -> list[ResultItem]:
    results: list[ResultItem] = []
    ignores = set(DEFAULT_IGNORE_TABLES) | set(ignore_tables or [])
    actual_tables: dict = actual.get("tables", {})

    for name in sorted(set(doc_tables) - set(actual_tables)):
        results.append(ResultItem(
            name, "missing_in_impl", "proof",
            message="table documented in docs/db but absent from the database"))
    for name in sorted(set(actual_tables) - set(doc_tables)):
        if name in ignores:
            continue
        results.append(ResultItem(
            name, "missing_in_doc", "proof",
            message="table exists in the database but is not documented"))

    for name in sorted(set(doc_tables) & set(actual_tables)):
        _compare_table(doc_tables[name], actual_tables[name], dialect, results)
    return results


def _column_uniques(actual_table: dict) -> set[str]:
    """Single-column unique constraint column names."""
    singles = set()
    for cols in actual_table.get("uniques", []):
        if len(cols) == 1:
            singles.add(cols[0])
    for idx in actual_table.get("indexes", []):
        if idx.get("unique") and len(idx.get("columns", [])) == 1:
            singles.add(idx["columns"][0])
    return singles


def _fk_map(actual_table: dict) -> dict[str, tuple[str, str]]:
    """Column → (ref_table, ref_column). Composite FKs are decomposed
    positionally so per-column x-foreign-key declarations still match."""
    fks: dict[str, tuple[str, str]] = {}
    for fk in actual_table.get("foreign_keys", []):
        ref_table = fk.get("ref_table", "")
        for col, ref in zip(fk.get("columns", []), fk.get("ref_columns", [])):
            fks[col] = (ref_table, ref)
    return fks


def _compare_table(doc: DocTable, actual_table: dict, dialect: str,
                   results: list[ResultItem]) -> None:
    actual_cols: dict = actual_table.get("columns", {})
    pk_cols = set(actual_table.get("primary_key", []))
    unique_cols = _column_uniques(actual_table)
    fk_map = _fk_map(actual_table)
    clean = True

    for col_name in sorted(set(doc.columns) - set(actual_cols)):
        results.append(ResultItem(
            f"{doc.name}.{col_name}", "missing_in_impl", "proof",
            message="column documented but absent from the database"))
        clean = False
    for col_name in sorted(set(actual_cols) - set(doc.columns)):
        results.append(ResultItem(
            f"{doc.name}.{col_name}", "missing_in_doc", "proof",
            actual=str(actual_cols[col_name].get("type", "")),
            message="column exists in the database but is not documented"))
        clean = False

    for col_name in sorted(set(doc.columns) & set(actual_cols)):
        col = doc.columns[col_name]
        act = actual_cols[col_name]
        target = f"{doc.name}.{col_name}"
        act_type = str(act.get("type", ""))

        ok_type, expected_desc = type_matches(col, act_type, dialect)
        if not ok_type:
            results.append(ResultItem(
                target, "mismatch", "proof",
                expected=expected_desc, actual=act_type,
                message="column type outside the accepted family"
                        if not col.db_type else "x-db-type exact match failed"))
            clean = False

        act_nullable = bool(act.get("nullable", False))
        if col.nullable != act_nullable:
            results.append(ResultItem(
                target, "mismatch", "proof",
                expected=f"{'NULL' if col.nullable else 'NOT NULL'}",
                actual=f"{'NULL' if act_nullable else 'NOT NULL'}"))
            clean = False

        act_pk = col_name in pk_cols or bool(act.get("primary_key", False))
        if col.primary_key != act_pk:
            results.append(ResultItem(
                target, "mismatch", "proof",
                expected=f"primary_key={col.primary_key}",
                actual=f"primary_key={act_pk}"))
            clean = False

        if col.unique and not (col_name in unique_cols or act_pk):
            results.append(ResultItem(
                target, "mismatch", "proof",
                expected="UNIQUE", actual="no unique constraint"))
            clean = False

        if col.foreign_key and col.fk_enforced:
            act_fk = fk_map.get(col_name)
            if act_fk is None:
                results.append(ResultItem(
                    target, "mismatch", "proof",
                    expected=f"FK → {col.foreign_key[0]}.{col.foreign_key[1]}",
                    actual="no foreign key"))
                clean = False
            elif (act_fk[0], act_fk[1]) != col.foreign_key:
                results.append(ResultItem(
                    target, "mismatch", "proof",
                    expected=f"FK → {col.foreign_key[0]}.{col.foreign_key[1]}",
                    actual=f"FK → {act_fk[0]}.{act_fk[1]}"))
                clean = False

    # Composite indexes (x-indexes) — matched by column sequence
    actual_index_sets = []
    for idx in actual_table.get("indexes", []):
        actual_index_sets.append((tuple(idx.get("columns", [])),
                                  bool(idx.get("unique"))))
    for cols in actual_table.get("uniques", []):
        actual_index_sets.append((tuple(cols), True))
    for want in doc.indexes:
        want_key = tuple(want.columns)
        hit = any(cols == want_key and (uniq or not want.unique)
                  for cols, uniq in actual_index_sets)
        if not hit:
            label = "UNIQUE index" if want.unique else "index"
            results.append(ResultItem(
                f"{doc.name}({', '.join(want.columns)})", "mismatch", "proof",
                expected=f"{label} on ({', '.join(want.columns)})",
                actual="not present in the database"))
            clean = False

    if clean:
        results.append(ResultItem(doc.name, "ok", "proof"))
