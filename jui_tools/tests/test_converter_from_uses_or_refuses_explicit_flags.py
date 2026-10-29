"""`jui g converter --from / --all`: an explicit flag is used, or refused out loud.

Those paths take the component's name and attributes from its spec. Until
jsonui-cli 2.3.29 every flag that said otherwise was dropped with no word
(ticket jui-generate-converter-from-ignores-explicit-no-container). Measured
on the command, each platform tool's argv captured:

    --from + --no-container / --container   the same run as with neither
    --from + --attributes / another name    the same run, the spec's
    --all  + --container / --no-container / --attributes / a name / --from
                                            every spec, as with neither

So `--from <spec> --no-container` scaffolded what the slots said, and the
author learnt only from the generated code that the leaf was not one.
`--force` / `--skip-existing` always crossed (pinned by
test_converter_spec_descriptions_and_force_reach_the_tools).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jui_cli.commands.generate_cmd import _cmd_generate_converter


class _Done:
    returncode = 0


def _project(root: Path) -> None:
    (root / "jui.config.json").write_text(json.dumps({
        "component_spec_directory": "docs/components/json",
        "platforms": {"ios": {"root": "ios"}, "android": {"root": "android"}, "web": {"root": "web"}},
    }), encoding="utf-8")
    specs = root / "docs" / "components" / "json"
    specs.mkdir(parents=True)
    # a leaf by its slots ("items": []), which --from deliberately does not
    # read as --no-container (_container_from_slots)
    (specs / "helpvideo.component.json").write_text(json.dumps({
        "metadata": {"name": "HelpVideo"},
        "props": {"items": [{"name": "src", "type": "String"}]},
        "slots": {"items": []},
    }), encoding="utf-8")
    (specs / "card.component.json").write_text(json.dumps({
        "metadata": {"name": "Card"},
        "props": {"items": []},
        "slots": {"items": [{"name": "content"}]},
    }), encoding="utf-8")


def _run(root: Path, **flags):
    """(rc, each tool's argv, what was printed)."""
    args = argparse.Namespace(name=flags.get("name"), from_spec=flags.get("from_spec"),
                              all_specs=flags.get("all_specs", False), attributes=flags.get("attributes"),
                              container=flags.get("container"), skip_existing=False, force=False)
    calls = []

    def fake_run(cmd, cwd=None, env=None):
        calls.append(cmd)
        return _Done()

    cwd = os.getcwd()
    os.chdir(root)
    out = io.StringIO()
    try:
        with patch("subprocess.run", side_effect=fake_run), contextlib.redirect_stdout(out):
            rc = _cmd_generate_converter(args)
    finally:
        os.chdir(cwd)
    return rc, calls, out.getvalue()


def _shapes(calls) -> set:
    return {("--container" in c, "--no-container" in c) for c in calls}


class ExplicitFlagsWithFrom(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _project(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_from_uses_an_explicit_no_container_and_container(self):
        rc, calls, _ = _run(self.root, from_spec="helpvideo.component.json", container=False)
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 3)  # each platform tool
        self.assertEqual(_shapes(calls), {(False, True)})
        # an explicit flag wins over the slots, either way
        rc, calls, _ = _run(self.root, from_spec="card.component.json", container=False)
        self.assertEqual(_shapes(calls), {(False, True)})
        rc, calls, _ = _run(self.root, from_spec="helpvideo.component.json", container=True)
        self.assertEqual(_shapes(calls), {(True, False)})

    def test_control_neither_flag_keeps_what_the_slots_give(self):
        _, calls, _ = _run(self.root, from_spec="helpvideo.component.json")
        self.assertEqual(_shapes(calls), {(False, False)})  # a leaf by slots: still neither flag
        _, calls, _ = _run(self.root, from_spec="card.component.json")
        self.assertEqual(_shapes(calls), {(True, False)})
        rc, calls, out = _run(self.root, from_spec="helpvideo.component.json", name="HelpVideo")
        self.assertEqual((rc, out.count("ERROR")), (0, 0))

    def test_from_refuses_attributes_and_another_name(self):
        for flags, said in (({"attributes": "x:Int"}, "--attributes is not used"),
                            ({"name": "Foo"}, "is the spec of 'HelpVideo', not 'Foo'")):
            rc, calls, out = _run(self.root, from_spec="helpvideo.component.json", **flags)
            self.assertEqual((rc, calls), (1, []), flags)
            self.assertIn("ERROR: ", out)
            self.assertIn(said, out)

    def test_all_refuses_a_shape_attributes_a_name_and_from(self):
        cases = (({"container": False}, "--no-container says one component's shape"),
                 ({"container": True}, "--container says one component's shape"),
                 ({"attributes": "x:Int"}, "--all takes the attributes from the spec's props"),
                 ({"name": "Foo"}, "the name 'Foo' is not used"),
                 ({"from_spec": "card.component.json"}, "--all and --from name different sets of specs"))
        for flags, said in cases:
            rc, calls, out = _run(self.root, all_specs=True, **flags)
            self.assertEqual((rc, calls), (1, []), flags)
            self.assertIn(said, out)

    def test_control_all_with_no_flag_runs_every_spec(self):
        rc, calls, out = _run(self.root, all_specs=True)
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 6)  # two specs x three tools
        self.assertNotIn("ERROR", out)


if __name__ == "__main__":
    unittest.main()
