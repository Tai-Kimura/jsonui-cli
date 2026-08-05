"""Tests for jui_cli.core.tool_resolver."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    @patch("jui_cli.core.tool_resolver._rbenv_version_installed", return_value=True)
    def test_includes_rbenv_version_when_pinned_version_installed(self, _mock):
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

    @patch("jui_cli.core.tool_resolver._rbenv_version_installed", return_value=False)
    def test_omits_rbenv_version_when_pinned_version_not_installed(self, _mock):
        # The bundled `.ruby-version` pins the maintainer's dev Ruby. When the
        # consumer doesn't have that exact patch installed, RBENV_VERSION must
        # NOT be forced (else `jui build` hard-fails "version not installed");
        # rbenv falls back to the consumer's own Ruby. Regression:
        # jui-build-forces-uninstalled-rbenv-version-from-bundled-ruby-version.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool_dir = root / "rjui_tools"
            bin_dir = tool_dir / "bin"
            bin_dir.mkdir(parents=True)
            bin_path = bin_dir / "rjui"
            bin_path.write_text("#!/bin/sh\n")
            (tool_dir / ".ruby-version").write_text("3.2.2\n")

            # No extras and no RBENV_VERSION → env is None (inherit parent).
            self.assertIsNone(build_tool_env(str(bin_path), "rjui"))

    @patch("jui_cli.core.tool_resolver._rbenv_version_installed", return_value=False)
    def test_extra_applies_even_when_pinned_version_not_installed(self, _mock):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool_dir = root / "rjui_tools"
            bin_dir = tool_dir / "bin"
            bin_dir.mkdir(parents=True)
            bin_path = bin_dir / "rjui"
            bin_path.write_text("#!/bin/sh\n")
            (tool_dir / ".ruby-version").write_text("3.2.2\n")

            # Cleared, because the assertion below is about what the
            # resolver PUT there and `build_tool_env` returns
            # `{**os.environ, **overrides}`. Run from a shell that exports
            # RBENV_VERSION — which is how you drive kjui's bundler — the
            # variable is in the result no matter what the resolver decided,
            # and the test fails while the code is behaving correctly. An
            # assertion about absence means nothing when the surroundings
            # can supply the thing.
            with patch.dict(os.environ, {}, clear=True):
                env = build_tool_env(
                    str(bin_path), "rjui", extra={"JUI_SKIP_EXISTING": "1"}
                )
            self.assertIsNotNone(env)
            self.assertNotIn("RBENV_VERSION", env)
            self.assertEqual(env.get("JUI_SKIP_EXISTING"), "1")

    @patch("jui_cli.core.tool_resolver._rbenv_version_installed", return_value=False)
    def test_an_inherited_rbenv_version_is_passed_through_untouched(self, _mock):
        """Omitting the pin means the parent's Ruby wins, not that it vanishes.

        The other half of the same contract: when the pinned version is not
        installed the resolver declines to force one, and whatever the shell
        already had must reach the child unchanged. Testing only the absence
        case leaves this unpinned, and it is the behaviour people actually
        depend on.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "rjui_tools" / "bin"
            bin_dir.mkdir(parents=True)
            bin_path = bin_dir / "rjui"
            bin_path.write_text("#!/bin/sh\n")
            (root / "rjui_tools" / ".ruby-version").write_text("3.2.2\n")

            with patch.dict(os.environ, {"RBENV_VERSION": "3.2.9"}, clear=True):
                env = build_tool_env(
                    str(bin_path), "rjui", extra={"JUI_SKIP_EXISTING": "1"}
                )
            self.assertEqual(env.get("RBENV_VERSION"), "3.2.9")

    @patch("jui_cli.core.tool_resolver._rbenv_version_installed", return_value=True)
    def test_merges_extra_env_on_top(self, _mock):
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


class RbenvVersionInstalledTest(unittest.TestCase):
    def test_detects_installed_version_under_rbenv_root(self):
        from jui_cli.core.tool_resolver import _rbenv_version_installed

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "versions" / "3.2.2").mkdir(parents=True)
            with patch.dict(os.environ, {"RBENV_ROOT": tmp}):
                self.assertTrue(_rbenv_version_installed("3.2.2"))
                self.assertFalse(_rbenv_version_installed("3.3.0"))


if __name__ == "__main__":
    unittest.main()
