"""Tests for the builtin:db-schema checker (doc parser + pure comparator +
SQLite live integration when sqlalchemy is available)."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.check.db_schema.comparator import (
    base_type,
    compare_schemas,
)
from jsonui_doc_cli.check.db_schema.doc_parser import (
    parse_db_docs,
    parse_table_file,
)

try:
    import sqlalchemy  # noqa: F401
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


def users_doc(**overrides) -> dict:
    doc = {
        "openapi": "3.0.3",
        "info": {"title": "User", "x-table-name": "users"},
        "paths": {},
        "components": {"schemas": {
            "User": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "x-primary-key": True,
                           "x-auto-increment": True},
                    "email": {"type": "string", "maxLength": 255,
                              "x-unique": True},
                    "nickname": {"type": "string", "nullable": True},
                    "created_at": {"type": "string", "format": "date-time"},
                    "team_id": {"type": "integer",
                                "x-foreign-key": {"table": "teams",
                                                  "column": "id"}},
                },
                "x-indexes": [
                    {"columns": ["team_id", "email"], "unique": True},
                ],
            },
        }},
    }
    doc["components"]["schemas"]["User"].update(overrides)
    return doc


def actual_users(**col_overrides) -> dict:
    cols = {
        "id": {"type": "INTEGER", "nullable": False, "primary_key": True,
               "auto_increment": True},
        "email": {"type": "VARCHAR(255)", "nullable": False},
        "nickname": {"type": "VARCHAR(64)", "nullable": True},
        "created_at": {"type": "DATETIME", "nullable": False},
        "team_id": {"type": "INTEGER", "nullable": False},
    }
    cols.update(col_overrides)
    return {
        "schemaVersion": 1,
        "dialect": "mysql",
        "tables": {
            "users": {
                "columns": cols,
                "primary_key": ["id"],
                "uniques": [["email"], ["team_id", "email"]],
                "indexes": [],
                "foreign_keys": [{"columns": ["team_id"],
                                  "ref_table": "teams",
                                  "ref_columns": ["id"]}],
            },
            "alembic_version": {"columns": {}, "primary_key": [],
                                "uniques": [], "indexes": [],
                                "foreign_keys": []},
        },
    }


class DocParserTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, data: dict) -> Path:
        p = self.db_dir / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_parses_table_with_extensions(self):
        p = self.write("users.json", users_doc())
        table = parse_table_file(p)
        self.assertEqual(table.name, "users")
        self.assertTrue(table.columns["id"].primary_key)
        self.assertTrue(table.columns["email"].unique)
        self.assertTrue(table.columns["nickname"].nullable)
        self.assertEqual(table.columns["created_at"].openapi_format,
                         "date-time")
        self.assertEqual(table.columns["team_id"].foreign_key,
                         ("teams", "id"))
        self.assertEqual(len(table.indexes), 1)
        self.assertEqual(table.indexes[0].columns, ["team_id", "email"])
        self.assertTrue(table.indexes[0].unique)

    def test_skips_non_db_files(self):
        self.write("api.json", {"openapi": "3.0.0",
                                "paths": {"/x": {}},
                                "components": {"schemas": {}}})
        self.write("junk.json", {"hello": 1})
        self.assertEqual(parse_db_docs(self.db_dir), {})

    def test_table_name_fallback_snake_case(self):
        doc = users_doc()
        del doc["info"]["x-table-name"]
        p = self.write("users.json", doc)
        self.assertEqual(parse_table_file(p).name, "user")


class ComparatorTests(unittest.TestCase):
    def _doc_tables(self, doc=None):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "users.json"
            p.write_text(json.dumps(doc or users_doc()), encoding="utf-8")
            return {"users": parse_table_file(p)}

    def _statuses(self, results):
        return {r.status for r in results}

    def test_clean_match(self):
        results = compare_schemas(self._doc_tables(), actual_users(), "mysql")
        bad = [r for r in results if r.status != "ok"]
        self.assertEqual(bad, [], [f"{r.status}:{r.target} {r.expected}->"
                                   f"{r.actual}" for r in bad])

    def test_migration_tables_ignored(self):
        results = compare_schemas(self._doc_tables(), actual_users(), "mysql")
        self.assertFalse(any("alembic" in r.target for r in results))

    def test_nullable_drift(self):
        actual = actual_users(
            nickname={"type": "VARCHAR(64)", "nullable": False})
        results = compare_schemas(self._doc_tables(), actual, "mysql")
        hits = [r for r in results if r.target == "users.nickname"
                and r.status == "mismatch"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].expected, "NULL")
        self.assertEqual(hits[0].actual, "NOT NULL")

    def test_type_family_lenient_but_catches_real_drift(self):
        # BIGINT for integer is fine…
        ok = compare_schemas(
            self._doc_tables(),
            actual_users(id={"type": "BIGINT", "nullable": False,
                             "primary_key": True}),
            "mysql")
        self.assertFalse(any(r.status == "mismatch" and r.target == "users.id"
                             for r in ok))
        # …VARCHAR for integer is not
        bad = compare_schemas(
            self._doc_tables(),
            actual_users(team_id={"type": "VARCHAR(32)", "nullable": False}),
            "mysql")
        self.assertTrue(any(r.status == "mismatch"
                            and r.target == "users.team_id" for r in bad))

    def test_x_db_type_exact_match(self):
        doc = users_doc()
        doc["components"]["schemas"]["User"]["properties"]["email"][
            "x-db-type"] = "VARCHAR(320)"
        results = compare_schemas(self._doc_tables(doc), actual_users(),
                                  "mysql")
        hits = [r for r in results if r.target == "users.email"
                and r.status == "mismatch"]
        self.assertEqual(len(hits), 1)
        self.assertIn("VARCHAR(320)", hits[0].expected)

    def test_missing_column_bidirectional(self):
        doc = users_doc()
        doc["components"]["schemas"]["User"]["properties"]["doc_only"] = {
            "type": "string"}
        actual = actual_users(impl_only={"type": "TEXT", "nullable": True})
        results = compare_schemas(self._doc_tables(doc), actual, "mysql")
        statuses = {r.target: r.status for r in results}
        self.assertEqual(statuses.get("users.doc_only"), "missing_in_impl")
        self.assertEqual(statuses.get("users.impl_only"), "missing_in_doc")

    def test_composite_unique_detected_when_absent(self):
        actual = actual_users()
        actual["tables"]["users"]["uniques"] = [["email"]]  # drop composite
        results = compare_schemas(self._doc_tables(), actual, "mysql")
        hits = [r for r in results if r.target.startswith("users(")]
        self.assertEqual(len(hits), 1)
        self.assertIn("team_id, email", hits[0].expected)

    def test_fk_drift(self):
        actual = actual_users()
        actual["tables"]["users"]["foreign_keys"] = [{
            "columns": ["team_id"], "ref_table": "organizations",
            "ref_columns": ["id"]}]
        results = compare_schemas(self._doc_tables(), actual, "mysql")
        hits = [r for r in results if r.target == "users.team_id"]
        self.assertEqual(hits[0].actual, "FK → organizations.id")

    def test_composite_fk_matches_per_column_declarations(self):
        # A composite FK in the DB must satisfy per-column x-foreign-key
        # declarations positionally (bug: composite FKs were dropped from
        # the map, reporting 'no foreign key' for every member column).
        doc = users_doc()
        props = doc["components"]["schemas"]["User"]["properties"]
        props["email"]["x-foreign-key"] = {"table": "teams",
                                           "column": "email"}
        actual = actual_users()
        actual["tables"]["users"]["foreign_keys"] = [{
            "columns": ["team_id", "email"], "ref_table": "teams",
            "ref_columns": ["id", "email"]}]
        results = compare_schemas(self._doc_tables(doc), actual, "mysql")
        fk_hits = [r for r in results if r.status == "mismatch"
                   and "foreign key" in (r.actual or "")]
        self.assertEqual(fk_hits, [],
                         [f"{r.target}: {r.expected} -> {r.actual}"
                          for r in fk_hits])

    def test_unenforced_fk_skips_constraint_check(self):
        # x-foreign-key {enforced: false} declares a logical reference —
        # the DB is not expected to hold a constraint.
        doc = users_doc()
        doc["components"]["schemas"]["User"]["properties"]["team_id"][
            "x-foreign-key"] = {"table": "teams", "column": "id",
                                "enforced": False}
        actual = actual_users()
        actual["tables"]["users"]["foreign_keys"] = []
        results = compare_schemas(self._doc_tables(doc), actual, "mysql")
        hits = [r for r in results if r.target == "users.team_id"
                and r.status == "mismatch"]
        self.assertEqual(hits, [])
        # …while the default (enforced) declaration still requires one
        strict = compare_schemas(self._doc_tables(), actual, "mysql")
        self.assertTrue(any(r.target == "users.team_id"
                            and r.actual == "no foreign key"
                            for r in strict))

    def test_missing_table_bidirectional(self):
        actual = actual_users()
        actual["tables"]["surprises"] = {"columns": {}, "primary_key": [],
                                         "uniques": [], "indexes": [],
                                         "foreign_keys": []}
        del actual["tables"]["users"]
        results = compare_schemas(self._doc_tables(), actual, "mysql")
        statuses = {r.target: r.status for r in results}
        self.assertEqual(statuses.get("users"), "missing_in_impl")
        self.assertEqual(statuses.get("surprises"), "missing_in_doc")

    def test_base_type_extraction(self):
        self.assertEqual(base_type("VARCHAR(255)"), "VARCHAR")
        self.assertEqual(base_type("timestamp with time zone"), "TIMESTAMP")
        self.assertEqual(base_type("TINYINT(1)"), "TINYINT")


@unittest.skipUnless(HAS_SQLALCHEMY, "sqlalchemy not installed")
class SqliteLiveTests(unittest.TestCase):
    def test_reflection_roundtrip(self):
        from jsonui_doc_cli.check.db_schema.dump_sqlalchemy import dump_schema
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "t.db"
            con = sqlite3.connect(db_path)
            con.executescript(
                """
                CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE users (
                  id INTEGER PRIMARY KEY,
                  email VARCHAR(255) NOT NULL UNIQUE,
                  nickname VARCHAR(64),
                  created_at DATETIME NOT NULL,
                  team_id INTEGER NOT NULL REFERENCES teams(id)
                );
                CREATE UNIQUE INDEX uq_team_email ON users(team_id, email);
                """
            )
            con.close()
            actual = dump_schema(f"sqlite:///{db_path}")
            self.assertEqual(actual["dialect"], "sqlite")
            self.assertIn("users", actual["tables"])
            users = actual["tables"]["users"]
            self.assertFalse(users["columns"]["email"]["nullable"])
            self.assertTrue(users["columns"]["nickname"]["nullable"])
            self.assertEqual(users["primary_key"], ["id"])
            # composite unique index reflected
            self.assertTrue(any(
                ix["columns"] == ["team_id", "email"] and ix["unique"]
                for ix in users["indexes"]))

            # end-to-end vs docs (sqlite dialect)
            doc = users_doc()
            with tempfile.TemporaryDirectory() as tmp2:
                p = Path(tmp2) / "users.json"
                p.write_text(json.dumps(doc), encoding="utf-8")
                tables = {"users": parse_table_file(p)}
            results = compare_schemas(tables, actual, "sqlite",
                                      ignore_tables=["teams"])
            bad = [r for r in results if r.status not in ("ok",)]
            self.assertEqual(bad, [], [f"{r.status}:{r.target} "
                                       f"{r.expected}->{r.actual}"
                                       for r in bad])


if __name__ == "__main__":
    unittest.main()
