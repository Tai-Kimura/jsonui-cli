"""Live-connection dump adapter (SQLAlchemy reflection → normalized JSON).

Optional dependency: install `jsonui-doc-cli[db]` (+ a driver extra like
[mysql] / [postgres]). SQLite works with the stdlib driver. Projects that
cannot or do not want to install drivers use a `dump_command` instead —
any command that prints the same normalized JSON (comparator.py docstring)
to stdout.

Connection URLs come from the environment only:
    JSONUI_CHECK_DB_URL_<NAME>   (e.g. JSONUI_CHECK_DB_URL_MAIN)
"""

from __future__ import annotations


class DumpAdapterError(Exception):
    pass


def _column_level_uniques(inspector, table_name: str,
                          already: list[list[str]]) -> list[list[str]]:
    """UNIQUE written on the column, which SQLite reports nowhere else.

    `email VARCHAR(255) NOT NULL UNIQUE` creates an implicit index named
    `sqlite_autoindex_<table>_<n>`. SQLAlchemy hides auto-indexes from
    `get_indexes()` and does not surface them from
    `get_unique_constraints()` either, so on SQLite a column-level UNIQUE
    is invisible — and a docs side that declares it reads as drift on
    every such column. MySQL and PostgreSQL both name the constraint, so
    they already come through the call above; asking for auto-indexes
    there would double-count, hence the dialect check.
    """
    if inspector.engine.dialect.name != "sqlite":
        return []
    try:
        auto = inspector.get_indexes(table_name, include_auto_indexes=True)
    except TypeError:
        # Older SQLAlchemy without the dialect kwarg: nothing to add rather
        # than a reflection failure.
        return []
    seen = {tuple(cols) for cols in already}
    found: list[list[str]] = []
    for ix in auto:
        if not str(ix.get("name") or "").startswith("sqlite_autoindex_"):
            continue
        cols = list(ix.get("column_names") or [])
        if not ix.get("unique") or not cols or tuple(cols) in seen:
            continue
        seen.add(tuple(cols))
        found.append(cols)
    return found


def dump_schema(url: str, dialect_hint: str | None = None) -> dict:
    try:
        from sqlalchemy import create_engine, inspect
    except ImportError:
        raise DumpAdapterError(
            "sqlalchemy is not installed. Either `pip install "
            "'jsonui-doc-cli[db]'` (plus a driver, e.g. [mysql]/[postgres]) "
            "or declare a `dump_command` that prints the normalized schema "
            "JSON to stdout (no extra dependencies needed)."
        )

    try:
        engine = create_engine(url)
        inspector = inspect(engine)
        dialect = engine.dialect.name
        tables: dict = {}
        for table_name in inspector.get_table_names():
            columns: dict = {}
            for col in inspector.get_columns(table_name):
                columns[col["name"]] = {
                    "type": str(col["type"]),
                    "nullable": bool(col.get("nullable", True)),
                    "default": (str(col["default"])
                                if col.get("default") is not None else None),
                    "auto_increment": bool(col.get("autoincrement") is True),
                }
            pk = inspector.get_pk_constraint(table_name) or {}
            pk_cols = list(pk.get("constrained_columns") or [])
            for c in pk_cols:
                if c in columns:
                    columns[c]["primary_key"] = True
                    # A primary key column cannot hold NULL — that is what a
                    # primary key is, in every dialect. SQLite reports the
                    # literal DDL instead, so `id INTEGER PRIMARY KEY` (the
                    # rowid alias, which genuinely rejects NULL) reflects as
                    # nullable and the docs' `NOT NULL` reads as drift.
                    columns[c]["nullable"] = False
            uniques = [
                list(uc.get("column_names") or [])
                for uc in inspector.get_unique_constraints(table_name)
            ]
            uniques.extend(_column_level_uniques(inspector, table_name, uniques))
            indexes = [
                {
                    "columns": list(ix.get("column_names") or []),
                    "unique": bool(ix.get("unique")),
                    "name": ix.get("name"),
                }
                for ix in inspector.get_indexes(table_name)
            ]
            fks = [
                {
                    "columns": list(fk.get("constrained_columns") or []),
                    "ref_table": fk.get("referred_table", ""),
                    "ref_columns": list(fk.get("referred_columns") or []),
                }
                for fk in inspector.get_foreign_keys(table_name)
            ]
            tables[table_name] = {
                "columns": columns,
                "primary_key": pk_cols,
                "uniques": uniques,
                "indexes": indexes,
                "foreign_keys": fks,
            }
        engine.dispose()
        return {
            "schemaVersion": 1,
            "dialect": dialect_hint or dialect,
            "tables": tables,
        }
    except DumpAdapterError:
        raise
    except Exception as exc:  # noqa: BLE001 — connection/reflection errors → exit 2
        raise DumpAdapterError(f"schema reflection failed: {exc}")
