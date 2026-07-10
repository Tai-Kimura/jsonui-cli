"""Tests for `jui g converter` platform fan-out and env wiring.

`_run_converter_direct` is the shared subprocess driver used by
`jui g converter <name>`, `--from <spec>`, and `--all`. These tests cover:

- `--skip-existing` → exports `JUI_SKIP_EXISTING=1` so the per-platform
  generators bypass their "Overwrite? (y/n)" prompt.
- Project-local `{tool}_tools/bin/{tool}` installations are resolved
  (regression of `jui-auto-converter-bare-sjui-path`).
- `FileNotFoundError` from a missing tool surfaces as a per-platform
  failure rather than crashing the caller.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import argparse
import contextlib
import os

from jui_cli.commands.generate_cmd import _cmd_generate_converter, _run_converter_direct
from jui_cli.core.config_manager import ConfigManager


def _fixture_project(root: Path) -> ConfigManager:
    (root / "jui.config.json").write_text(json.dumps({
        "component_spec_directory": "docs/components/json",
        "platforms": {
            "ios": {"root": "ios"},
            "android": {"root": "android"},
            "web": {"root": "web"},
        },
    }))
    return ConfigManager(root / "jui.config.json")


class _StubCompletedProcess:
    def __init__(self, returncode=0):
        self.returncode = returncode


class RunConverterDirectTest(unittest.TestCase):
    def test_sets_jui_skip_existing_when_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_mgr = _fixture_project(root)
            platforms = {"web": {"root": "web"}}

            captured = {}

            def fake_run(cmd, cwd=None, env=None):
                captured["env"] = env
                return _StubCompletedProcess(0)

            with patch("subprocess.run", side_effect=fake_run):
                rc = _run_converter_direct(
                    "MyCard", None, False, platforms, config_mgr,
                    skip_existing=True,
                )
            self.assertEqual(rc, 0)
            self.assertIsNotNone(captured["env"])
            self.assertEqual(captured["env"].get("JUI_SKIP_EXISTING"), "1")

    def test_env_is_none_when_skip_existing_is_false_and_bare_tool(self):
        # No local install + no extras → env=None so subprocess inherits
        # the parent env unchanged.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_mgr = _fixture_project(root)
            platforms = {"web": {"root": "web"}}

            captured = {}

            def fake_run(cmd, cwd=None, env=None):
                captured["env"] = env
                return _StubCompletedProcess(0)

            with patch("subprocess.run", side_effect=fake_run):
                _run_converter_direct(
                    "MyCard", None, False, platforms, config_mgr,
                )
            self.assertIsNone(captured["env"])

    def test_resolves_project_local_tool_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_mgr = _fixture_project(root)
            web_root = root / "web"
            rjui_bin = web_root / "rjui_tools" / "bin" / "rjui"
            rjui_bin.parent.mkdir(parents=True)
            rjui_bin.write_text("#!/bin/sh\nexit 0\n")
            rjui_bin.chmod(0o755)

            captured = {}

            def fake_run(cmd, cwd=None, env=None):
                captured["cmd"] = list(cmd)
                return _StubCompletedProcess(0)

            with patch("subprocess.run", side_effect=fake_run):
                _run_converter_direct(
                    "MyCard", None, False,
                    {"web": {"root": "web"}}, config_mgr,
                    skip_existing=True,
                )

            self.assertEqual(captured["cmd"][0], str(rjui_bin))

    def test_falls_back_to_bare_name_when_not_found_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_mgr = _fixture_project(root)

            captured = {}

            def fake_run(cmd, cwd=None, env=None):
                captured["cmd"] = list(cmd)
                return _StubCompletedProcess(0)

            with patch("subprocess.run", side_effect=fake_run):
                _run_converter_direct(
                    "MyCard", None, False,
                    {"web": {"root": "web"}}, config_mgr,
                )

            self.assertEqual(captured["cmd"][0], "rjui")

    def test_missing_tool_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_mgr = _fixture_project(root)

            def fake_run(cmd, cwd=None, env=None):
                raise FileNotFoundError(2, "No such file or directory: 'rjui'")

            with patch("subprocess.run", side_effect=fake_run):
                rc = _run_converter_direct(
                    "MyCard", None, False,
                    {"web": {"root": "web"}}, config_mgr,
                    skip_existing=True,
                )

            self.assertEqual(rc, 1)


@contextlib.contextmanager
def _chdir(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _converter_args(**overrides) -> argparse.Namespace:
    defaults = dict(
        name=None, from_spec=None, all_specs=False,
        attributes=None, container=False, skip_existing=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class CmdGenerateConverterTest(unittest.TestCase):
    """Regression of `jui-generate-converter-silent-noop-without-platforms`."""

    def _project(self, root: Path, platforms: dict) -> None:
        (root / "jui.config.json").write_text(json.dumps({
            "component_spec_directory": "docs/components/json",
            "platforms": platforms,
        }))
        spec_dir = root / "docs" / "components" / "json"
        spec_dir.mkdir(parents=True)
        (spec_dir / "mycard.component.json").write_text(json.dumps({
            "metadata": {"name": "MyCard"},
            "props": {"items": [{"name": "title", "type": "string"}]},
        }))

    def test_empty_platforms_errors_instead_of_silent_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, {})
            with _chdir(root):
                rc = _cmd_generate_converter(
                    _converter_args(from_spec="mycard.component.json"))
            self.assertEqual(rc, 1)

    def test_only_unsupported_platform_keys_also_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, {"flutter": {"root": "app"}})
            with _chdir(root):
                rc = _cmd_generate_converter(
                    _converter_args(name="MyCard"))
            self.assertEqual(rc, 1)

    def test_from_spec_accepts_direct_path(self):
        # A cwd-relative path used to be joined onto component_spec_directory,
        # producing a doubled path that never exists.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, {"web": {"root": "web"}})
            calls = []

            def fake_run(cmd, cwd=None, env=None):
                calls.append(list(cmd))
                return _StubCompletedProcess(0)

            with _chdir(root), patch("subprocess.run", side_effect=fake_run):
                rc = _cmd_generate_converter(_converter_args(
                    from_spec="docs/components/json/mycard.component.json"))
            self.assertEqual(rc, 0)
            self.assertEqual(len(calls), 1)

    def test_from_spec_bare_filename_still_resolves_in_spec_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._project(root, {"web": {"root": "web"}})
            calls = []

            def fake_run(cmd, cwd=None, env=None):
                calls.append(list(cmd))
                return _StubCompletedProcess(0)

            with _chdir(root), patch("subprocess.run", side_effect=fake_run):
                rc = _cmd_generate_converter(_converter_args(
                    from_spec="mycard.component.json"))
            self.assertEqual(rc, 0)
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
