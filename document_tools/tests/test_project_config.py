"""Tests for jsonui_doc_cli.project_config (checks/databases declarations)."""

import os
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.project_config import (
    CheckDecl,
    ProjectConfigError,
    find_jui_config,
    load_checks,
    load_databases,
    parse_command,
)


class ProjectConfigTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".jsonui" / "checks").mkdir(parents=True)
        (self.root / ".jsonui" / "checks" / "dump.sh").write_text("#!/bin/sh\n")

    def tearDown(self):
        self._tmp.cleanup()


class FindConfigTests(ProjectConfigTestBase):
    def test_walks_upward(self):
        (self.root / "jui.config.json").write_text("{}")
        nested = self.root / "a" / "b"
        nested.mkdir(parents=True)
        self.assertEqual(
            find_jui_config(nested),
            (self.root / "jui.config.json").resolve(),
        )

    def test_none_when_missing(self):
        self.assertIsNone(find_jui_config(self.root))


class ParseCommandTests(ProjectConfigTestBase):
    def test_project_script(self):
        argv = parse_command(".jsonui/checks/dump.sh --db main", self.root, "t")
        self.assertEqual(argv, [".jsonui/checks/dump.sh", "--db", "main"])

    def test_interpreter_with_script(self):
        argv = parse_command("python .jsonui/checks/dump.sh", self.root, "t")
        self.assertEqual(argv[0], "python")

    def test_interpreter_module_form(self):
        argv = parse_command("python -m app.export_openapi", self.root, "t")
        self.assertEqual(argv, ["python", "-m", "app.export_openapi"])

    def test_rejects_absolute_path(self):
        with self.assertRaises(ProjectConfigError):
            parse_command("/usr/bin/evil", self.root, "t")

    def test_rejects_dotdot(self):
        with self.assertRaises(ProjectConfigError):
            parse_command("../outside.sh", self.root, "t")

    def test_rejects_bad_module_name(self):
        with self.assertRaises(ProjectConfigError):
            parse_command("python -m 'os; import x'", self.root, "t")

    def test_rejects_symlink_escape(self):
        outside = Path(self._tmp.name).parent / "outside_target.sh"
        outside.write_text("#!/bin/sh\n")
        try:
            link = self.root / "link.sh"
            os.symlink(outside, link)
            with self.assertRaises(ProjectConfigError):
                parse_command("link.sh", self.root, "t")
        finally:
            outside.unlink(missing_ok=True)


class LoadChecksTests(ProjectConfigTestBase):
    def test_full_declaration_set(self):
        config = {
            "checks": [
                {"name": "db-main", "type": "builtin:db-schema", "database": "main"},
                {
                    "name": "api",
                    "type": "builtin:openapi-diff",
                    "impl_openapi_command": "python -m app.export_openapi",
                    "ignore_paths": ["/internal/*"],
                },
                {
                    "name": "api-live",
                    "type": "checker",
                    "command": ".jsonui/checks/dump.sh",
                    "timeout_seconds": 120,
                },
            ]
        }
        decls = load_checks(config, self.root)
        self.assertEqual([d.name for d in decls], ["db-main", "api", "api-live"])
        self.assertEqual(decls[0].database, "main")
        self.assertEqual(decls[1].impl_openapi_command,
                         ["python", "-m", "app.export_openapi"])
        self.assertEqual(decls[1].ignore_paths, ["/internal/*"])
        self.assertEqual(decls[2].timeout_seconds, 120)

    def test_default_timeout(self):
        decls = load_checks(
            {"checks": [{"name": "db", "type": "builtin:db-schema"}]}, self.root
        )
        self.assertEqual(decls[0].timeout_seconds, 60)
        self.assertEqual(decls[0].database, "default")

    def test_unknown_type_rejected(self):
        with self.assertRaises(ProjectConfigError):
            load_checks({"checks": [{"name": "x", "type": "builtin:nope"}]}, self.root)

    def test_duplicate_name_rejected(self):
        cfg = {"checks": [
            {"name": "db", "type": "builtin:db-schema"},
            {"name": "db", "type": "builtin:db-schema"},
        ]}
        with self.assertRaises(ProjectConfigError):
            load_checks(cfg, self.root)

    def test_credentials_in_config_rejected(self):
        cfg = {"checks": [{
            "name": "db", "type": "builtin:db-schema",
            "url": "mysql://root:pw@localhost/db",
        }]}
        with self.assertRaises(ProjectConfigError) as ctx:
            load_checks(cfg, self.root)
        self.assertIn("environment variables", str(ctx.exception))

    def test_openapi_diff_requires_command(self):
        with self.assertRaises(ProjectConfigError):
            load_checks(
                {"checks": [{"name": "api", "type": "builtin:openapi-diff"}]},
                self.root,
            )

    def test_missing_checks_key_is_empty(self):
        self.assertEqual(load_checks({}, self.root), [])

    def _openapi(self, **extra):
        return {"checks": [{
            "name": "api", "type": "builtin:openapi-diff",
            "impl_openapi_command": "python -m app.export_openapi",
            **extra,
        }]}

    def test_comparison_key_severity_declarations(self):
        decls = load_checks(
            self._openapi(ignore_schema_keys=["nullable"],
                          downgrade_to_warning=["format"]),
            self.root)
        self.assertEqual(decls[0].ignore_schema_keys, ["nullable"])
        self.assertEqual(decls[0].downgrade_to_warning, ["format"])

    def test_comparison_key_severity_defaults_empty(self):
        decls = load_checks(self._openapi(), self.root)
        self.assertEqual(decls[0].ignore_schema_keys, [])
        self.assertEqual(decls[0].downgrade_to_warning, [])

    def test_unknown_comparison_key_rejected(self):
        # A typo'd key would otherwise suppress nothing while the project
        # believed the noise was handled.
        with self.assertRaises(ProjectConfigError) as ctx:
            load_checks(self._openapi(downgrade_to_warning=["formats"]),
                        self.root)
        self.assertIn("unknown comparison key", str(ctx.exception))

    def test_field_path_in_comparison_keys_rejected(self):
        with self.assertRaises(ProjectConfigError) as ctx:
            load_checks(self._openapi(ignore_schema_keys=["/api/health"]),
                        self.root)
        self.assertIn("ignore_paths", str(ctx.exception))

    def test_same_key_in_both_lists_rejected(self):
        with self.assertRaises(ProjectConfigError) as ctx:
            load_checks(self._openapi(ignore_schema_keys=["format"],
                                      downgrade_to_warning=["format"]),
                        self.root)
        self.assertIn("BOTH", str(ctx.exception))

    def test_argv_list_command_names_the_type_given(self):
        with self.assertRaises(ProjectConfigError) as ctx:
            load_checks(
                {"checks": [{"name": "api", "type": "builtin:openapi-diff",
                             "impl_openapi_command": ["python", "-m", "app"]}]},
                self.root)
        self.assertIn("got list", str(ctx.exception))


class LoadDatabasesTests(unittest.TestCase):
    def test_databases_block(self):
        dbs = load_databases({"databases": {
            "main": {"dialect": "mysql", "version": "8.0"},
            "fs": {"dialect": "firestore"},
        }})
        self.assertEqual(dbs["main"].dialect, "mysql")
        self.assertEqual(dbs["main"].version, "8.0")
        self.assertEqual(dbs["fs"].dialect, "firestore")

    def test_legacy_single_db(self):
        dbs = load_databases({"db": {"dialect": "postgresql"}})
        self.assertEqual(list(dbs), ["default"])
        self.assertEqual(dbs["default"].dialect, "postgresql")

    def test_empty(self):
        self.assertEqual(load_databases({}), {})

    def test_invalid_shape(self):
        with self.assertRaises(ProjectConfigError):
            load_databases({"databases": {"main": {"version": "8"}}})


if __name__ == "__main__":
    unittest.main()
