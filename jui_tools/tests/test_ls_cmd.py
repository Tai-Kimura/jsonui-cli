"""Tests for `jui ls` + `jui g api --dry-run` (MCP discovery commands).

The CLI is exercised via :func:`cmd_ls` / :func:`cmd_generate` with a
synthesized ``argparse.Namespace`` so we don't have to spawn subprocesses.
``--json`` mode is the primary contract — MCP wrappers depend on the
exact shape — so most assertions check JSON output.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


def _write_config(project_root: Path, *, api_directory: str = "docs/api", api_schemas: dict | None = None) -> None:
    """Write a minimal ``jui.config.json`` under *project_root*."""
    config = {
        "project_name": "test",
        "spec_directory": "docs/screens/json",
        "layouts_directory": "docs/screens/layouts",
        "api_directory": api_directory,
        "platforms": {
            "ios": {"root": "ios-app"},
        },
    }
    if api_schemas is not None:
        config["api"] = {"schemas": api_schemas}
    (project_root / "jui.config.json").write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )


def _write_swagger(api_dir: Path, name: str, schemas: dict, paths: dict | None = None) -> Path:
    """Write a minimal swagger JSON file."""
    api_dir.mkdir(parents=True, exist_ok=True)
    body = {
        "openapi": "3.0.3",
        "info": {"title": f"Test {name}", "version": "1.0.0"},
        "paths": paths or {},
        "components": {"schemas": schemas},
    }
    path = api_dir / f"{name}.json"
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return path


@contextmanager
def _capture_stdout():
    """Capture stdout into a StringIO buffer."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        yield buf
    finally:
        sys.stdout = old


@contextmanager
def _in_project(project_root: Path):
    """Run a block with cwd at *project_root* (ConfigManager walks up from cwd)."""
    old = os.getcwd()
    os.chdir(project_root)
    try:
        yield
    finally:
        os.chdir(old)


class LsApiSpecsTests(unittest.TestCase):
    def test_no_api_directory_returns_empty(self):
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            args = argparse.Namespace(ls_target="api-specs", as_json=True)
            with _in_project(root), _capture_stdout() as buf:
                self.assertEqual(cmd_ls(args), 0)
            payload = json.loads(buf.getvalue())
            self.assertFalse(payload["exists"])
            self.assertEqual(payload["files"], [])

    def test_lists_swagger_metadata(self):
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            _write_swagger(
                root / "docs/api",
                "main",
                schemas={
                    "User": {"type": "object", "properties": {"id": {"type": "string"}}},
                    "Status": {"type": "string", "enum": ["a", "b"]},
                },
                paths={
                    "/api/u": {
                        "get": {"responses": {"200": {}}},
                        "post": {"responses": {"200": {}}},
                    },
                },
            )
            args = argparse.Namespace(ls_target="api-specs", as_json=True)
            with _in_project(root), _capture_stdout() as buf:
                self.assertEqual(cmd_ls(args), 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["exists"])
            self.assertEqual(len(payload["files"]), 1)
            entry = payload["files"][0]
            self.assertEqual(entry["title"], "Test main")
            self.assertEqual(entry["schema_count"], 1)
            self.assertEqual(entry["enum_count"], 1)
            self.assertEqual(entry["endpoint_count"], 2)
            self.assertFalse(entry["has_one_of"])
            self.assertFalse(entry["has_multi_file_ref"])

    def test_detects_one_of_flag(self):
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            _write_swagger(
                root / "docs/api",
                "poly",
                schemas={
                    "Result": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/A"},
                            {"$ref": "#/components/schemas/B"},
                        ],
                    },
                    "A": {"type": "object"},
                    "B": {"type": "object"},
                },
            )
            args = argparse.Namespace(ls_target="api-specs", as_json=True)
            with _in_project(root), _capture_stdout() as buf:
                cmd_ls(args)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["files"][0]["has_one_of"])

    def test_detects_multi_file_ref_flag(self):
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            _write_swagger(
                root / "docs/api",
                "split",
                schemas={
                    "Outer": {
                        "type": "object",
                        "properties": {
                            "inner": {"$ref": "./inner.yaml#/Inner"},
                        },
                    },
                },
            )
            args = argparse.Namespace(ls_target="api-specs", as_json=True)
            with _in_project(root), _capture_stdout() as buf:
                cmd_ls(args)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["files"][0]["has_multi_file_ref"])

    def test_human_readable_output_works(self):
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            _write_swagger(
                root / "docs/api",
                "main",
                schemas={"User": {"type": "object", "properties": {"id": {"type": "string"}}}},
            )
            args = argparse.Namespace(ls_target="api-specs", as_json=False)
            with _in_project(root), _capture_stdout() as buf:
                cmd_ls(args)
            output = buf.getvalue()
            self.assertIn("api_directory:", output)
            self.assertIn("Test main", output)
            self.assertIn("schemas=1", output)


class LsApiModelsTests(unittest.TestCase):
    def test_no_models_dir_returns_empty(self):
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            args = argparse.Namespace(ls_target="api-models", platform=None, as_json=True)
            with _in_project(root), _capture_stdout() as buf:
                cmd_ls(args)
            payload = json.loads(buf.getvalue())
            self.assertIn("ios", payload["platforms"])
            self.assertEqual(payload["platforms"]["ios"]["dto_files"], [])
            self.assertEqual(payload["platforms"]["ios"]["domain_scaffolds"], [])

    def test_lists_dto_and_domain(self):
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            # No swagger — orphan detection disabled
            ios_root = root / "ios-app"
            (ios_root / "Model" / "Generated").mkdir(parents=True)
            (ios_root / "Model" / "Generated" / "UserDto.swift").write_text("// dto", encoding="utf-8")
            (ios_root / "Model" / "Generated" / "BarDto.swift").write_text("// dto", encoding="utf-8")
            (ios_root / "Model" / "User.swift").write_text("// domain", encoding="utf-8")
            args = argparse.Namespace(ls_target="api-models", platform=None, as_json=True)
            with _in_project(root), _capture_stdout() as buf:
                cmd_ls(args)
            payload = json.loads(buf.getvalue())
            ios = payload["platforms"]["ios"]
            self.assertEqual(len(ios["dto_files"]), 2)
            self.assertEqual(len(ios["domain_scaffolds"]), 1)
            dto_schemas = sorted(d["schema_name"] for d in ios["dto_files"])
            self.assertEqual(dto_schemas, ["Bar", "User"])

    def test_detects_orphans_against_swagger(self):
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            _write_swagger(
                root / "docs/api",
                "main",
                schemas={"User": {"type": "object", "properties": {"id": {"type": "string"}}}},
            )
            ios_root = root / "ios-app"
            (ios_root / "Model" / "Generated").mkdir(parents=True)
            (ios_root / "Model" / "Generated" / "UserDto.swift").write_text("// kept", encoding="utf-8")
            (ios_root / "Model" / "Generated" / "OldStaleDto.swift").write_text("// orphan", encoding="utf-8")
            args = argparse.Namespace(ls_target="api-models", platform=None, as_json=True)
            with _in_project(root), _capture_stdout() as buf:
                cmd_ls(args)
            payload = json.loads(buf.getvalue())
            ios = payload["platforms"]["ios"]
            orphan_names = sorted(o["schema_name"] for o in ios["orphans"])
            self.assertEqual(orphan_names, ["OldStale"])

    def test_platform_filter_to_ios_only(self):
        """--platform ios surfaces only the iOS inventory (other platforms skipped)."""
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Project with all 3 platforms configured
            (root / "jui.config.json").write_text(
                json.dumps({
                    "project_name": "t",
                    "api_directory": "docs/api",
                    "platforms": {
                        "ios": {"root": "ios-app"},
                        "android": {"root": "android-app"},
                        "web": {"root": "web-app"},
                    },
                }),
                encoding="utf-8",
            )
            args = argparse.Namespace(ls_target="api-models", platform="ios", as_json=True)
            with _in_project(root), _capture_stdout() as buf:
                cmd_ls(args)
            payload = json.loads(buf.getvalue())
            self.assertEqual(list(payload["platforms"].keys()), ["ios"])

    def test_all_platforms_scanned_by_default(self):
        """No --platform flag → every configured platform with a planner appears."""
        from jui_cli.commands.ls_cmd import cmd_ls
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "jui.config.json").write_text(
                json.dumps({
                    "project_name": "t",
                    "api_directory": "docs/api",
                    "platforms": {
                        "ios": {"root": "ios-app"},
                        "android": {"root": "android-app"},
                        "web": {"root": "web-app"},
                    },
                }),
                encoding="utf-8",
            )
            args = argparse.Namespace(ls_target="api-models", platform=None, as_json=True)
            with _in_project(root), _capture_stdout() as buf:
                cmd_ls(args)
            payload = json.loads(buf.getvalue())
            self.assertEqual(
                sorted(payload["platforms"].keys()),
                ["android", "ios", "web"],
            )


class GenerateApiDryRunTests(unittest.TestCase):
    def test_dry_run_emits_filter_summary(self):
        from jui_cli.commands.generate_cmd import cmd_generate
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root, api_schemas={"include_paths": ["/api/u"]})
            _write_swagger(
                root / "docs/api",
                "main",
                schemas={
                    "User": {"type": "object", "properties": {"id": {"type": "string"}}},
                    "Other": {"type": "object", "properties": {"x": {"type": "string"}}},
                },
                paths={
                    "/api/u": {
                        "get": {
                            "responses": {
                                "200": {
                                    "content": {
                                        "application/json": {
                                            "schema": {"$ref": "#/components/schemas/User"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            )
            args = argparse.Namespace(
                generate_type="api",
                dry_run=True,
                platform=None,
                as_json=True,
                # mirror flags expected by planners_for()
                ios_only=False,
                android_only=False,
                web_only=False,
            )
            with _in_project(root), _capture_stdout() as buf:
                self.assertEqual(cmd_generate(args), 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["filter_active"])
            self.assertEqual(len(payload["swagger_files"]), 1)
            sf = payload["swagger_files"][0]
            self.assertIn("User", sf["kept"])
            self.assertIn("Other", sf["filtered_out"])
            # iOS planner exists → expects writes proposed
            ios = payload["platforms"]["ios"]
            dto_paths = ios["would_write_dto"]
            self.assertTrue(any("UserDto.swift" in p for p in dto_paths))

    def test_dry_run_without_filter_keeps_all(self):
        from jui_cli.commands.generate_cmd import cmd_generate
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            _write_swagger(
                root / "docs/api",
                "main",
                schemas={
                    "User": {"type": "object", "properties": {"id": {"type": "string"}}},
                    "Other": {"type": "object", "properties": {"x": {"type": "string"}}},
                },
            )
            args = argparse.Namespace(
                generate_type="api",
                dry_run=True,
                platform=None,
                as_json=True,
                ios_only=False,
                android_only=False,
                web_only=False,
            )
            with _in_project(root), _capture_stdout() as buf:
                self.assertEqual(cmd_generate(args), 0)
            payload = json.loads(buf.getvalue())
            self.assertFalse(payload["filter_active"])
            sf = payload["swagger_files"][0]
            self.assertEqual(sorted(sf["kept"]), ["Other", "User"])
            self.assertEqual(sf["filtered_out"], [])

    def test_non_dry_run_returns_helpful_error(self):
        from jui_cli.commands.generate_cmd import cmd_generate
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            args = argparse.Namespace(
                generate_type="api",
                dry_run=False,
                platform=None,
                as_json=True,
                ios_only=False,
                android_only=False,
                web_only=False,
            )
            with _in_project(root), _capture_stdout() as buf:
                self.assertEqual(cmd_generate(args), 1)
            payload = json.loads(buf.getvalue())
            self.assertIn("dry-run", payload["error"])


if __name__ == "__main__":
    unittest.main()
