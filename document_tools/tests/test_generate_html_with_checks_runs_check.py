"""`jsonui-doc generate html --with-checks` runs `check` first, with the check
command's own defaults (ticket mcp-doc-generate-html-timeout-leaves-partial-
output, found 2026-11-15). Through jsonui-cli 2.5.40 it handed `cmd_check` a
hand-written Namespace that `check` had outgrown (`--json`), and every
--with-checks run — the MCP tool doc_generate_html's `with_checks` among them —
stopped at once on "'Namespace' object has no attribute 'json'".
"""
from __future__ import annotations

import argparse
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from jsonui_doc_cli import cli


def _html_args(root: Path, **extra) -> argparse.Namespace:
    base = dict(input=str(root / "tests"), output=str(root / "html"), title="T", docs=None, figma=None,
                app=None, layouts_dir=None, config=None, with_checks=True, allow_partial=False)
    base.update(extra)
    return argparse.Namespace(**base)


class GenerateHtmlWithChecksTest(unittest.TestCase):
    def test_check_gets_every_argument_the_check_command_defines(self):
        seen = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(cli, "cmd_check", side_effect=lambda a: seen.append(a) or 0), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            cli.cmd_generate_html(_html_args(Path(d)))
        self.assertEqual(len(seen), 1)
        defaults = vars(cli._add_check_arguments(argparse.ArgumentParser(add_help=False)).parse_args([]))
        self.assertIn("json", defaults)
        self.assertEqual(vars(seen[0]), defaults)

    def test_a_with_checks_run_reaches_generation(self):
        # A project declaring no checks, and no input: check runs (and reads
        # every argument it has), and the run goes on to generation, which
        # names the missing input. Through 2.5.40 it raised on `args.json`.
        err = io.StringIO()
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / "jui.config.json").write_text('{"checks": []}\n', encoding="utf-8")
            os.chdir(root)
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(err):
                    rc = cli.cmd_generate_html(_html_args(root))
            finally:
                os.chdir(cwd)
        self.assertEqual(rc, 1)
        self.assertIn("Input directory not found", err.getvalue())


if __name__ == "__main__":
    unittest.main()
