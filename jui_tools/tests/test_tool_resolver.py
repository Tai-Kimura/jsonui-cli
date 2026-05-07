"""Tests for jui_cli.core.tool_resolver."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.tool_resolver import build_tool_env, resolve_tool


class ResolveToolTest(unittest.TestCase):
    def test_prefers_project_local_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_path = root / "sjui_tools" / "bin" / "sjui"
            bin_path.parent.mkdir(parents=True)
            bin_path.write_text("#!/bin/sh\n")
            bin_path.chmod(0o755)

            self.assertEqual(resolve_tool("sjui", root), str(bin_path))

    def test_walks_up_to_find_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_path = root / "rjui_tools" / "bin" / "rjui"
            bin_path.parent.mkdir(parents=True)
            bin_path.write_text("#!/bin/sh\n")
            bin_path.chmod(0o755)

            nested = root / "a" / "b" / "c"
            nested.mkdir(parents=True)
            self.assertEqual(resolve_tool("rjui", nested), str(bin_path))

    def test_handles_jsonui_cli_sibling_layout(self):
        # `{cwd}/../jsonui-cli/sjui_tools/bin/sjui` structure used when the
        # CLI checkout lives as a sibling of the project.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_path = root / "jsonui-cli" / "kjui_tools" / "bin" / "kjui"
            bin_path.parent.mkdir(parents=True)
            bin_path.write_text("#!/bin/sh\n")
            bin_path.chmod(0o755)

            # cwd is a project directory inside `tmp` (not jsonui-cli itself)
            project = root / "project"
            project.mkdir()
            self.assertEqual(resolve_tool("kjui", project), str(bin_path))

    def test_falls_back_to_bare_name_when_no_local_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(resolve_tool("sjui", Path(tmp)), "sjui")


class BuildToolEnvTest(unittest.TestCase):
    def test_returns_none_when_no_tweaks_and_no_extra(self):
        # Bare-name resolved + no extras → env should be None so the
        # subprocess inherits the parent env unchanged.
        self.assertIsNone(build_tool_env("sjui", "sjui"))

    def test_includes_rbenv_version_from_local_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool_dir = root / "sjui_tools"
            bin_dir = tool_dir / "bin"
            bin_dir.mkdir(parents=True)
            bin_path = bin_dir / "sjui"
            bin_path.write_text("#!/bin/sh\n")
            (tool_dir / ".ruby-version").write_text("3.2.5\n")

            env = build_tool_env(str(bin_path), "sjui")
            self.assertIsNotNone(env)
            self.assertEqual(env.get("RBENV_VERSION"), "3.2.5")
            # Parent env is preserved
            self.assertIn("PATH", env)

    def test_merges_extra_env_on_top(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool_dir = root / "rjui_tools"
            bin_dir = tool_dir / "bin"
            bin_dir.mkdir(parents=True)
            bin_path = bin_dir / "rjui"
            bin_path.write_text("#!/bin/sh\n")
            (tool_dir / ".ruby-version").write_text("3.2.5\n")

            env = build_tool_env(
                str(bin_path), "rjui",
                extra={"JUI_SKIP_EXISTING": "1"},
            )
            self.assertEqual(env.get("RBENV_VERSION"), "3.2.5")
            self.assertEqual(env.get("JUI_SKIP_EXISTING"), "1")

    def test_returns_env_with_extras_even_when_bare_name(self):
        # No local install but caller passes extras — env must still be
        # built so the extras reach the subprocess.
        env = build_tool_env("sjui", "sjui", extra={"JUI_SKIP_EXISTING": "1"})
        self.assertIsNotNone(env)
        self.assertEqual(env.get("JUI_SKIP_EXISTING"), "1")


if __name__ == "__main__":
    unittest.main()
