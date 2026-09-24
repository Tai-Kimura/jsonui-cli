"""`jui g converter --from / --all` hands the spec's descriptions and `--force` to every tool.

Until 1.8.113 only `name:type` crossed from the component spec to the
platform tools, so every rewrite of attribute_definitions/<Name>.json
replaced the spec's `props.items[].description` with "<key> attribute"
(jui-g-converter-drops-spec-prop-descriptions). And `jui g converter` had no
`--force`, while 1.8.112's scaffold header told the reader "Only --force
replaces it" (sjui-kjui-converter-cli-reject-force-and-skip-existing).

These capture the command each tool is given. The tools' own handling —
parsing the options, writing the description — is pinned in each tool's
specs.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jui_cli.commands.generate_cmd import _cmd_generate_converter
from jui_cli.core.config_manager import ConfigManager


class _Done:
    returncode = 0


def _project(root: Path) -> None:
    (root / "jui.config.json").write_text(json.dumps({
        "component_spec_directory": "docs/components/json",
        "platforms": {"ios": {"root": "ios"}, "android": {"root": "android"},
                      "web": {"root": "web"}},
    }), encoding="utf-8")
    specs = root / "docs" / "components" / "json"
    specs.mkdir(parents=True)
    (specs / "meter.component.json").write_text(json.dumps({
        "metadata": {"name": "Meter"},
        "props": {"items": [
            {"name": "scale", "type": "Int", "description": "目盛りの数（0〜10）"},
            {"name": "reading", "type": "Int?", "description": "  "},   # blank: not sent
            {"name": "title", "type": "String"},                            # none: not sent
        ]},
        "stateManagement": {"exposedEvents": [
            {"name": "onSelect", "description": "a segment was tapped"}]},
    }, ensure_ascii=False), encoding="utf-8")


def _run(root: Path, **flags) -> list:
    args = argparse.Namespace(name=flags.get("name"), from_spec=flags.get("from_spec"),
                              all_specs=flags.get("all_specs", False),
                              attributes=flags.get("attributes"), container=False,
                              skip_existing=False, force=flags.get("force", False))
    calls = []

    def fake_run(cmd, cwd=None, env=None):
        calls.append(cmd)
        return _Done()

    import os
    cwd = os.getcwd()
    os.chdir(root)
    try:
        with patch("subprocess.run", side_effect=fake_run):
            rc = _cmd_generate_converter(args)
    finally:
        os.chdir(cwd)
    assert rc == 0, rc
    return calls


def _option(cmd: list, name: str):
    return cmd[cmd.index(name) + 1] if name in cmd else None


class SpecDescriptionsReachEveryTool(unittest.TestCase):
    def test_all_and_from_hand_the_descriptions_to_each_platform(self):
        for flags in ({"all_specs": True}, {"from_spec": "meter.component.json"}):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _project(root)
                calls = _run(root, **flags)
                self.assertEqual(3, len(calls), flags)
                for cmd in calls:
                    payload = _option(cmd, "--attribute-descriptions")
                    # ASCII whatever the locale: with LANG unset a raw UTF-8
                    # argument reaches Ruby as binary.
                    self.assertTrue(payload.isascii(), payload)
                    sent = json.loads(payload)
                    self.assertEqual({"scale": "目盛りの数（0〜10）", "onSelect": "a segment was tapped"},
                                     sent, (flags, cmd[0]))

    def test_the_direct_form_has_no_spec_and_sends_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)
            for cmd in _run(root, name="Probe", attributes="scale:Int"):
                self.assertNotIn("--attribute-descriptions", cmd)


class ForceReachesEveryTool(unittest.TestCase):
    def test_force_is_passed_on_and_absent_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _project(root)
            forced = _run(root, all_specs=True, force=True)
            plain = _run(root, all_specs=True)
        self.assertEqual(3, len(forced))   # all() would hold on none
        self.assertTrue(all("--force" in cmd for cmd in forced))
        self.assertFalse(any("--force" in cmd for cmd in plain))

    def test_the_parser_accepts_force(self):
        from jui_cli.commands.generate_cmd import register_generate_command  # noqa: PLC0415
        parser = argparse.ArgumentParser(prog="jui")
        register_generate_command(parser.add_subparsers(dest="command"))
        self.assertTrue(parser.parse_args(["g", "converter", "--all", "--force"]).force)
        self.assertFalse(parser.parse_args(["g", "converter", "--all"]).force)


if __name__ == "__main__":
    unittest.main()
