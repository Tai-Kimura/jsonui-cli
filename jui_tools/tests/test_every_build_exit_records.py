"""Every way out of `jui build` records what the run wrote.

The four `return _halt(1)` sites cover the failures the function decides
on. They do not cover the ones it is handed. A §3.3 invariant is a raised
ValueError; a canonical-mark or parent-spec problem is a raised error that
`cli.py` catches and formats OUTSIDE this function. An exception leaves
through none of those four returns, so the run recorded nothing.

Measured on a real face before this was closed: a build printed its
formatted ERROR and then neither the manifest block nor the success line,
and three DTO files it had just rewritten kept a version two releases old.

"All four are wired" was true when it was reported, and the exits were
five. So this file counts them rather than checking the ones it thought of
— a fifth exit added later fails here instead of being discovered
downstream.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jui_cli.commands.build_cmd as build_cmd

SOURCE = Path(build_cmd.__file__).read_text(encoding="utf-8")


def _cmd_build_node() -> ast.FunctionDef:
    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.FunctionDef) and node.name == "cmd_build":
            return node
    raise AssertionError("cmd_build not found")


def _observe_line(fn: ast.FunctionDef) -> int:
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "observe"):
            return node.lineno
    raise AssertionError("the observation window is never opened")


class ExitCountTests(unittest.TestCase):
    def setUp(self):
        self.fn = _cmd_build_node()
        self.opened = _observe_line(self.fn)

    def test_every_return_after_the_window_opens_records(self):
        # One of two kinds of exit. See the sibling arm for the other.
        # `_halt` records; `return code` is inside `_halt`, after it has;
        # `return 0` is the success path, which records just above it.
        accepted = {"_halt", "code", "0"}
        exits = []
        for node in ast.walk(self.fn):
            if not isinstance(node, ast.Return) or node.lineno < self.opened:
                continue
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                shape = value.func.id
            elif isinstance(value, ast.Name):
                shape = value.id
            elif isinstance(value, ast.Constant):
                shape = str(value.value)
            else:
                shape = ast.dump(value) if value else "None"
            exits.append((node.lineno, shape))
            self.assertIn(
                shape, accepted,
                f"line {node.lineno} leaves cmd_build as `{shape}`, which "
                f"does not record what the run wrote",
            )
        # THIS NUMBER IS THE RETURNS, NOT THE EXITS. Counting returns is
        # what produced "all four are wired" while the exits were five, and
        # a reader who takes 6 for the total repeats it. The other kind of
        # exit is an exception; it has its own arm below, and the
        # behavioural arms in the next class are what actually establish
        # that it records.
        self.assertEqual(6, len(exits), exits)

    def test_the_body_is_guarded_against_the_exits_that_are_not_returns(self):
        # An exception is an exit too, and it was the one that was missed.
        guards = [n for n in ast.walk(self.fn)
                  if isinstance(n, ast.Try) and n.lineno > self.opened]
        catching = [
            h for g in guards for h in g.handlers
            if isinstance(h.type, ast.Name) and h.type.id == "BaseException"
        ]
        self.assertTrue(catching, "nothing catches an exception leaving the "
                                  "region where the window is open")


class ExceptionPathRecordsTests(unittest.TestCase):
    """The behaviour, not just the shape."""

    def setUp(self):
        self._cwd = Path.cwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "web" / "src" / "Layouts").mkdir(parents=True)
        gen = self.root / "web" / "src" / "generated"
        gen.mkdir(parents=True)
        (gen / "A.ts").write_text("before\n", encoding="utf-8")
        (self.root / "jui.config.json").write_text(json.dumps({
            "platforms": {"web": {"root": "web", "layoutsDir": "src/Layouts"}},
        }), encoding="utf-8")
        self.target = gen / "A.ts"

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _build_raising(self, exc):
        os.chdir(self.root)
        original = build_cmd._sync_api_models

        def raiser(*_a, **_k):
            self.target.write_text("written by this run\n", encoding="utf-8")
            raise exc("halted")

        build_cmd._sync_api_models = raiser
        raised, out = None, io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                build_cmd.cmd_build(argparse.Namespace(
                    clean=False, ios_only=False, android_only=False,
                    web_only=False, platform=None, lint_strings=False,
                    normalize_layouts=None))
        except BaseException as e:  # noqa: BLE001 - that is the point
            raised = e
        finally:
            build_cmd._sync_api_models = original
        manifest = self.root / ".jsonui-cli" / "generation-manifest.json"
        entries = (json.loads(manifest.read_text())["files"]
                   if manifest.exists() else {})
        return raised, entries, out.getvalue()

    def test_a_stage_that_raises_still_records_what_it_wrote(self):
        raised, entries, out = self._build_raising(ValueError)
        self.assertIsInstance(raised, ValueError)
        self.assertIn("web/src/generated/A.ts", entries)
        self.assertIn("generation manifest:", out)

    def test_the_error_class_the_face_actually_hit_is_covered(self):
        # Identified from code rather than from log order, which `> log
        # 2>&1` reorders: the message that face saw is printed only by
        # cli.py's handler, that handler catches only CanonicalMarkError
        # and ParentSpecDeclarationError, and both are raised out of the
        # spec extractor that build imports. So the exit was an exception,
        # and it bypassed all four `_halt` returns.
        from jui_cli.core.spec_extractor import CanonicalMarkError

        raised, entries, out = self._build_raising(CanonicalMarkError)
        self.assertIsInstance(raised, CanonicalMarkError)
        self.assertIn("web/src/generated/A.ts", entries)
        self.assertIn("generation manifest:", out)

    def test_the_failure_is_re_raised_unchanged(self):
        # Recording must not swallow or rewrite it: the caller formats
        # these, and a lane reads the message straight off a red run.
        raised, _entries, _out = self._build_raising(KeyboardInterrupt)
        self.assertIsInstance(raised, KeyboardInterrupt)
        self.assertEqual("halted", str(raised))

    def _build_returning_false(self):
        # The other half of the question, and the one the downstream probe
        # could not reach: it wrote no DTOs, so it never exercised whether
        # a content change is picked up on the halted path. The reported
        # face DID write three, and they were not recorded.
        os.chdir(self.root)
        original = build_cmd._sync_api_models

        def refuser(*_a, **_k):
            self.target.write_text("written by this run\n", encoding="utf-8")
            return False

        build_cmd._sync_api_models = refuser
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = build_cmd.cmd_build(argparse.Namespace(
                    clean=False, ios_only=False, android_only=False,
                    web_only=False, platform=None, lint_strings=False,
                    normalize_layouts=None))
        finally:
            build_cmd._sync_api_models = original
        manifest = self.root / ".jsonui-cli" / "generation-manifest.json"
        entries = (json.loads(manifest.read_text())["files"]
                   if manifest.exists() else {})
        return code, entries, out.getvalue()

    def test_a_stage_that_refuses_records_the_file_it_changed(self):
        code, entries, out = self._build_returning_false()
        self.assertEqual(1, code)
        self.assertIn("web/src/generated/A.ts", entries,
                      "the halted path took the exit but recorded nothing")
        self.assertIn("generation manifest:", out)
        self.assertNotIn("Build completed successfully", out)

    def test_the_refused_run_stamps_it_with_the_running_version(self):
        # Not the version it had before: this run produced those bytes.
        _code, entries, _out = self._build_returning_false()
        from jui_cli.version import toolchain_version

        self.assertEqual(toolchain_version(),
                         entries["web/src/generated/A.ts"]["version"])

    def test_the_success_line_is_not_printed_when_it_failed(self):
        _raised, _entries, out = self._build_raising(ValueError)
        self.assertNotIn("Build completed successfully", out)


if __name__ == "__main__":
    unittest.main()
