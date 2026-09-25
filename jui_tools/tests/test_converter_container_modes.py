"""`jui g converter` carries the container mode to every platform tool.

Three states, as each tool parses them: --container, --no-container (a leaf:
the build refuses a layout that gives it children), or neither (the tool's
default, a content slot drawn when children are given). Until 1.8.121 jui
had no --no-container, so a leaf could not be scaffolded through jui at all.
`--from` still reads an empty `slots.items` as the default in 1.8.121 (see
_container_from_slots for the measurement). Ticket
sjui-leaf-custom-component-cannot-reject-children.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jui_cli.commands.generate_cmd import (
    _cmd_generate_converter,
    _container_from_slots,
    _run_converter_direct,
    register_generate_command,
)
from jui_cli.core.config_manager import ConfigManager

from tests.test_run_converter_direct import _chdir, _converter_args, _StubCompletedProcess

PLATFORMS = {"ios": {"root": "ios"}, "android": {"root": "android"}, "web": {"root": "web"}}
FLAGS = {"--container", "--no-container"}


def _run(container) -> list[list[str]]:
    calls = []

    def fake_run(cmd, cwd=None, env=None):
        calls.append(list(cmd))
        return _StubCompletedProcess(0)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "jui.config.json").write_text(json.dumps({"platforms": PLATFORMS}))
        with patch("subprocess.run", side_effect=fake_run):
            rc = _run_converter_direct("Card", None, container, PLATFORMS,
                                       ConfigManager(root / "jui.config.json"))
    assert rc == 0
    return calls


class ContainerFlagTest(unittest.TestCase):
    def test_each_state_reaches_all_three_tools(self):
        for container, expected in ((True, ["--container"]), (False, ["--no-container"]), (None, [])):
            calls = _run(container)
            self.assertEqual(len(calls), 3)
            for cmd in calls:
                self.assertEqual([a for a in cmd if a in FLAGS], expected, (container, cmd))

    def test_the_parser_reads_three_states(self):
        parser = argparse.ArgumentParser()
        register_generate_command(parser.add_subparsers(dest="command"))
        read = lambda *extra: parser.parse_args(["generate", "converter", "Card", *extra]).container
        self.assertIsNone(read())
        self.assertIs(read("--container"), True)
        self.assertIs(read("--no-container"), False)


class SlotsDeclareTheModeTest(unittest.TestCase):
    def test_the_mapping(self):
        self.assertIs(_container_from_slots({"items": [{"name": "content"}]}), True)
        # Not yet a leaf in 1.8.121 — measured to break a face's Android build.
        self.assertIsNone(_container_from_slots({"items": [], "notes": "a leaf"}))
        self.assertIsNone(_container_from_slots(None))
        self.assertIsNone(_container_from_slots({}))
        self.assertIsNone(_container_from_slots({"notes": "no items key"}))

    def test_from_spec_passes_the_default_for_an_empty_slots_list(self):
        cases = {"leaf": ({"items": []}, []),
                 "box": ({"items": [{"name": "content"}]}, ["--container"]),
                 "silent": (None, [])}
        for stem, (slots, expected) in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "jui.config.json").write_text(json.dumps({
                    "component_spec_directory": "docs/components/json",
                    "platforms": {"web": {"root": "web"}},
                }))
                spec_dir = root / "docs" / "components" / "json"
                spec_dir.mkdir(parents=True)
                spec = {"metadata": {"name": "Card"}, "props": {"items": []}}
                if slots is not None:
                    spec["slots"] = slots
                (spec_dir / f"{stem}.component.json").write_text(json.dumps(spec))
                calls = []

                def fake_run(cmd, cwd=None, env=None):
                    calls.append(list(cmd))
                    return _StubCompletedProcess(0)

                with _chdir(root), patch("subprocess.run", side_effect=fake_run):
                    rc = _cmd_generate_converter(_converter_args(from_spec=f"{stem}.component.json"))
                self.assertEqual(rc, 0)
                self.assertEqual([a for a in calls[0] if a in FLAGS], expected, stem)


if __name__ == "__main__":
    unittest.main()
