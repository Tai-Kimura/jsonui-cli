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
            uniques = [
                list(uc.get("column_names") or [])
                for uc in inspector.get_unique_constraints(table_name)
            ]
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
