"""End-to-end tests for `jsonui-doc check` (runner + builtin openapi-diff +
full-checker plugin protocol + exit codes)."""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.check.runner import (
    EXIT_ERROR,
    EXIT_MISMATCH,
    EXIT_OK,
    run_checks,
)
from jsonui_doc_cli.project_config import load_checks

DOC_SWAGGER = {
    "openapi": "3.0.3",
    "info": {"title": "Svc"},
    "paths": {
        "/api/ping": {"get": {"responses": {"200": {
            "content": {"application/json": {"schema": {
                "type": "object", "required": ["status"],
                "properties": {"status": {"type": "string"}}}}}}}}},
        "/api/gone": {"get": {"responses": {"200": {"description": "ok"}}}},
    },
}

IMPL_MATCHING = {
    "openapi": "3.1.0",
    "paths": {
        "/api/ping": {"get": {"responses": {
            "200": {"content": {"application/json": {"schema": {
                "type": "object", "required": ["status"], "title": "Ping",
                "properties": {"status": {"type": "string",
                                          "title": "Status"}}}}}},
            "422": {"description": "auto"},
        }}},
        "/api/gone": {"get": {"responses": {"200": {"description": "ok"}}}},
    },
}


class RunnerTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / ".jsonui" / "checks").mkdir(parents=True)
        (self.root / "docs" / "api" / "svc.json").write_text(
            json.dumps(DOC_SWAGGER), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def script(self, name: str, body: str) -> str:
        """Write an executable project script, return its relative path."""
        p = self.root / ".jsonui" / "checks" / name
        p.write_text(body, encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
        return f".jsonui/checks/{name}"

    def impl_script(self, spec: dict) -> str:
        return self.script(
            "impl_openapi.py",
            "import json\nprint(json.dumps(" + repr(spec) + "))\n",
        )

    def run_declared(self, checks: list[dict], **kw) -> int:
        decls = load_checks({"checks": checks}, self.root)
        return run_checks(decls, self.root, {}, **kw)


class OpenApiDiffE2ETests(RunnerTestBase):
    def test_clean_run_exit_0_and_report_saved(self):
        rel = self.impl_script(IMPL_MATCHING)
        code = self.run_declared([{
            "name": "api", "type": "builtin:openapi-diff",
            "impl_openapi_command": f"python3 {rel}",
        }])
        self.assertEqual(code, EXIT_OK)
        report = json.loads(
            (self.root / "docs" / "api" / ".check-report.json").read_text())
        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["summary"]["mismatch"], 0)

    def test_drift_exit_1(self):
        impl = json.loads(json.dumps(IMPL_MATCHING))
        del impl["paths"]["/api/gone"]  # real drift
        rel = self.impl_script(impl)
        code = self.run_declared([{
            "name": "api", "type": "builtin:openapi-diff",
            "impl_openapi_command": f"python3 {rel}",
        }])
        self.assertEqual(code, EXIT_MISMATCH)

    def test_broken_impl_command_exit_2(self):
        rel = self.script("broken.py", "import sys; sys.exit(3)\n")
        code = self.run_declared([{
            "name": "api", "type": "builtin:openapi-diff",
            "impl_openapi_command": f"python3 {rel}",
        }])
        self.assertEqual(code, EXIT_ERROR)

    def test_scope_generated_excludes_unfiltered_paths(self):
        impl = json.loads(json.dumps(IMPL_MATCHING))
        del impl["paths"]["/api/gone"]  # drift, but outside generated scope
        rel = self.impl_script(impl)
        decls = load_checks({
            "api": {"schemas": {"include_paths": ["/api/ping"]}},
            "checks": [{
                "name": "api", "type": "builtin:openapi-diff",
                "impl_openapi_command": f"python3 {rel}",
                "scope": "generated",
            }],
        }, self.root)
        code = run_checks(decls, self.root, {})
        self.assertEqual(code, EXIT_OK)


class FullCheckerPluginTests(RunnerTestBase):
    def _report(self, status="ok"):
        return {
            "schemaVersion": 1,
            "checker": "live",
            "executed_at": "2026-07-07T00:00:00+09:00",
            "target": {"kind": "custom", "name": "live-api"},
            "input_hashes": {},
            "results": [{"target": "GET /x", "status": status,
                         "confidence": "sampled"}],
        }

    def test_valid_plugin_output(self):
        rel = self.script(
            "live.py",
            "import json\nprint(json.dumps(" + repr(self._report()) + "))\n")
        code = self.run_declared([{
            "name": "live", "type": "checker",
            "command": f"python3 {rel}",
        }])
        self.assertEqual(code, EXIT_OK)
        saved = self.root / "docs" / ".check-report.live-api.json"
        self.assertTrue(saved.is_file())

    def test_plugin_mismatch_exit_1(self):
        rel = self.script(
            "live.py",
            "import json\nprint(json.dumps("
            + repr(self._report("mismatch")) + "))\n")
        code = self.run_declared([{
            "name": "live", "type": "checker", "command": f"python3 {rel}",
        }])
        self.assertEqual(code, EXIT_MISMATCH)

    def test_invalid_plugin_output_exit_2(self):
        bad = self._report()
        del bad["schemaVersion"]
        rel = self.script(
            "live.py",
            "import json\nprint(json.dumps(" + repr(bad) + "))\n")
        code = self.run_declared([{
            "name": "live", "type": "checker", "command": f"python3 {rel}",
        }])
        self.assertEqual(code, EXIT_ERROR)

    def test_timeout_exit_2(self):
        rel = self.script("slow.py", "import time\ntime.sleep(5)\n")
        code = self.run_declared([{
            "name": "live", "type": "checker", "command": f"python3 {rel}",
            "timeout_seconds": 1,
        }])
        self.assertEqual(code, EXIT_ERROR)


class FilterAndListTests(RunnerTestBase):
    def declare_two(self):
        rel = self.impl_script(IMPL_MATCHING)
        return [
            {"name": "api", "type": "builtin:openapi-diff",
             "impl_openapi_command": f"python3 {rel}"},
            {"name": "db-main", "type": "builtin:db-schema",
             "database": "main"},
        ]

    def test_list_runs_nothing(self):
        code = self.run_declared(self.declare_two(), list_only=True)
        self.assertEqual(code, EXIT_OK)
        self.assertFalse(
            (self.root / "docs" / "api" / ".check-report.json").exists())

    def test_filter_api_skips_db(self):
        # db check would exit 2 (no docs/db) — filtering to api avoids it
        code = self.run_declared(self.declare_two(), filter_expr="api")
        self.assertEqual(code, EXIT_OK)

    def test_unknown_filter_is_error(self):
        code = self.run_declared(self.declare_two(), filter_expr="nope")
        self.assertEqual(code, EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
