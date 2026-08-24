"""Tests for `jsonui-doc validate spec <directory>`.

`generate spec` has accepted a directory all along; validate refused with
Errno 21, so the standing "is the whole project still clean?" check had to
be a hand-written loop. Reported by a consumer lane after using exactly
such a loop to accept a release.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest import mock

from jsonui_doc_cli.cli import cmd_validate_spec


def _spec(name, *, broken=False):
    spec = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {
            "name": name,
            "displayName": name,
            "description": f"{name} screen.",
            "layoutFile": name.lower(),
        },
        "structure": {"components": [], "layout": {}},
    }
    if broken:
        spec["version"] = "nonsense"
    return spec


class ValidateSpecBatchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel, spec):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    def _run(self, target):
        out = StringIO()
        with mock.patch("sys.stdout", out):
            code = cmd_validate_spec(Namespace(file=str(target)))
        return code, out.getvalue()

    def test_directory_validates_every_spec_recursively(self):
        self._write("a.spec.json", _spec("Alpha"))
        self._write("nested/b.spec.json", _spec("Beta"))
        code, output = self._run(self.root)
        self.assertEqual(0, code)
        self.assertIn("PASSED (2 spec file(s))", output)

    def test_directory_fails_when_any_spec_fails(self):
        self._write("a.spec.json", _spec("Alpha"))
        self._write("b.spec.json", _spec("Beta", broken=True))
        code, output = self._run(self.root)
        self.assertEqual(1, code)
        self.assertIn("FAILED (1 of 2 spec file(s))", output)
        self.assertIn("b.spec.json", output)

    def test_directory_without_specs_is_an_error(self):
        (self.root / "empty").mkdir()
        code, _ = self._run(self.root / "empty")
        self.assertEqual(1, code)

    def test_single_file_path_still_works(self):
        path = self._write("a.spec.json", _spec("Alpha"))
        code, output = self._run(path)
        self.assertEqual(0, code)
        self.assertIn("Result: PASSED", output)
        self.assertNotIn("spec file(s)", output)

    def test_missing_path_is_reported(self):
        code, _ = self._run(self.root / "nope")
        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
