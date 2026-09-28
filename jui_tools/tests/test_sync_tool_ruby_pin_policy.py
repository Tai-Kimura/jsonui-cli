"""`jui sync_tool` does not force the tools' patch-level Ruby pin on a root.

The tools ship `.ruby-version` = 3.2.2 (the maintainer's patch level).
sync_tool used to copy it into every platform root and rewrite it on every
sync whenever the root's pin differed. Under rbenv an uninstalled pin makes
rbenv stop (`version ... is not installed`) before the tool's own Ruby-floor
ERROR can tell the user what to pin — and if the user followed that ERROR
anyway, the next sync overwrote their pin. tool_resolver already refuses to
force RBENV_VERSION to an uninstalled pin for the same reason.

Policy: an existing root pin is never rewritten (>= 3.2 kept silently,
below 3.2 named); with no pin, the tool's pin is written only when that
exact Ruby is installed under rbenv.
"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.sync_tool_cmd import _ruby_pin_meets_floor, _sync_one_tool


class RubyPinPolicyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.source = root / "src" / "sjui_tools"
        self.source.mkdir(parents=True)
        (self.source / ".ruby-version").write_text("3.2.2\n")
        (self.source / "VERSION").write_text("1.9.0\n")
        self.platform_root = root / "project"
        self.target = self.platform_root / "sjui_tools"
        self.platform_root.mkdir()
        self.pin = self.platform_root / ".ruby-version"
        self.rbenv_root = root / "rbenv"
        (self.rbenv_root / "versions").mkdir(parents=True)
        self._saved = os.environ.get("RBENV_ROOT")
        os.environ["RBENV_ROOT"] = str(self.rbenv_root)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("RBENV_ROOT", None)
        else:
            os.environ["RBENV_ROOT"] = self._saved
        self._tmp.cleanup()

    def _install(self, version: str) -> None:
        (self.rbenv_root / "versions" / version).mkdir()

    def _sync(self, *, dry_run: bool = False) -> tuple[dict[str, int], str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            counters = _sync_one_tool(self.source, self.target, self.platform_root,
                                      prune=False, dry_run=dry_run)
        return counters, out.getvalue()

    def test_a_pin_above_the_floor_is_kept(self):
        self._install("3.2.2")
        self.pin.write_text("3.3.1\n")
        counters, out = self._sync()
        self.assertEqual(self.pin.read_text(), "3.3.1\n")
        self.assertEqual(counters["ruby_pin"], 0)
        self.assertNotIn(".ruby-version", out)

    def test_an_uninstalled_pin_is_not_written(self):
        counters, out = self._sync()
        self.assertFalse(self.pin.exists())
        self.assertEqual(counters["ruby_pin"], 0)
        self.assertIn("not written", out)
        self.assertIn("3.2.2", out)

    def test_an_uninstalled_pin_is_not_written_in_dry_run_either(self):
        counters, out = self._sync(dry_run=True)
        self.assertFalse(self.pin.exists())
        self.assertEqual(counters["ruby_pin"], 0)
        self.assertIn("would not write", out)

    def test_a_pin_below_the_floor_is_named_not_rewritten(self):
        self._install("3.2.2")
        self.pin.write_text("2.6\n")
        counters, out = self._sync()
        self.assertEqual(self.pin.read_text(), "2.6\n")
        self.assertEqual(counters["ruby_pin"], 0)
        self.assertIn("'2.6'", out)
        self.assertIn("not rewritten", out)

    def test_an_installed_pin_is_written_where_none_exists(self):
        self._install("3.2.2")
        counters, _ = self._sync()
        self.assertEqual(self.pin.read_text(), "3.2.2\n")
        self.assertEqual(counters["ruby_pin"], 1)
        # and a second sync leaves it alone
        counters, _ = self._sync()
        self.assertEqual(counters["ruby_pin"], 0)

    def test_an_installed_pin_is_only_announced_in_dry_run(self):
        self._install("3.2.2")
        counters, out = self._sync(dry_run=True)
        self.assertFalse(self.pin.exists())
        self.assertEqual(counters["ruby_pin"], 1)
        self.assertIn("would write:  ../.ruby-version  (3.2.2)", out)

    def test_floor_parse(self):
        for pin in ("3.2", "3.2.0", "3.3.1", "ruby-3.4.0", "3.10.0", "4.0.0-preview1"):
            self.assertTrue(_ruby_pin_meets_floor(pin), pin)
        for pin in ("2.6", "2.7.8", "3.1.4", "ruby-3.1", "system", "jruby-9.4", ""):
            self.assertFalse(_ruby_pin_meets_floor(pin), pin)


if __name__ == "__main__":
    unittest.main()
