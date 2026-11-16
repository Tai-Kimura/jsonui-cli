"""`jui sync_tool` says which tree it synced from, and what version that is.

The source is `--source` > `$JSONUI_CLI_PATH` > `~/.jsonui-cli`, and the
home copy is refreshed by the bootstrap. So a project pinning one version
and a home directory holding another produced the same line: a path, with
nothing about what was in it. A docs project shipped a tool tree stamped
1.8.6 while its pin said 1.8.5 and the contents were older than either —
35 paths apart, 10 of them specs that had never been vendored at all. The
stamp was accurate about itself; nothing said which tree it came from, so
comparing VERSION could not reveal it.

Which source is CORRECT is deliberately not decided here — a project may
pin on purpose, and CI setting the variable is the intended arrangement.
Saying which one was used is what the tool owes.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.sync_tool_cmd import (
    _describe_source,
    _resolve_source_root_and_reason,
    _source_version,
)


class SourceVersionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.pinned = self.root / "pinned"
        self.home = self.root / "home"
        for path, version in ((self.pinned, "1.8.5"), (self.home, "1.8.7")):
            path.mkdir()
            (path / "VERSION").write_text(version + "\n", encoding="utf-8")
        self._saved = os.environ.get("JSONUI_CLI_PATH")
        os.environ.pop("JSONUI_CLI_PATH", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JSONUI_CLI_PATH", None)
        else:
            os.environ["JSONUI_CLI_PATH"] = self._saved
        self._tmp.cleanup()

    def test_the_version_of_the_source_is_printed(self):
        self.assertIn("(1.8.5", _describe_source(self.pinned, "default"))

    def test_the_rule_that_chose_the_source_is_named(self):
        # Two trees, two versions: without the rule, the line cannot say
        # why this one won.
        os.environ["JSONUI_CLI_PATH"] = str(self.pinned)
        root, reason = _resolve_source_root_and_reason(None)
        line = _describe_source(root, reason)
        self.assertIn("1.8.5", line)
        self.assertIn("$JSONUI_CLI_PATH", line)

    def test_an_explicit_source_is_named_by_the_flag_that_sets_it(self):
        # `--source` is the argparse dest, not the flag. The line named the
        # dest, so it told a reader to pass an argument the parser rejects.
        root, reason = _resolve_source_root_and_reason(str(self.home))
        line = _describe_source(root, reason)
        self.assertIn("1.8.7", line)
        self.assertIn("--from", line)
        self.assertNotIn("--source", line)

    def test_the_named_flag_is_one_the_parser_accepts(self):
        # Pinning the name against the parser rather than against a string
        # I typed twice: the two drifted, and only running the command
        # showed it.
        import argparse

        from jui_cli.commands.sync_tool_cmd import register_sync_tool_command

        parser = argparse.ArgumentParser()
        register_sync_tool_command(parser.add_subparsers(dest="cmd"))
        _root, reason = _resolve_source_root_and_reason(str(self.home))
        sub = parser._subparsers._group_actions[0].choices["sync_tool"]
        flags = {opt for action in sub._actions
                 for opt in action.option_strings}
        self.assertIn(reason, flags,
                      f"the line names {reason}, which the parser does not "
                      f"accept: {sorted(flags)}")

    def test_the_default_names_itself_too(self):
        # This arm used to assert the opposite: no rule name when nothing
        # selected it, so the line would not imply a decision nobody made.
        # That concern survives — it is why the word is "default" and not
        # something like "chosen" — but omitting it made the line say two
        # things at once. An absent reason reads as "nothing selected this"
        # AND as "this version does not print reasons", and the second was
        # true of every release before 1.8.8, so a reader comparing the
        # line across versions could not separate them.
        line = _describe_source(self.home, "default")
        self.assertIn("1.8.7", line)
        self.assertIn("default", line)
        # What the original arm was actually protecting: the line must not
        # claim a rule that had no part in it.
        self.assertNotIn("$JSONUI_CLI_PATH", line)
        self.assertNotIn("--source", line)

    def test_every_route_names_itself(self):
        # The property, rather than three separate examples of it: whatever
        # picked the source, the line says so. Written this way, a fourth
        # route added later cannot quietly go silent.
        for reason in ("default", "$JSONUI_CLI_PATH", "--from"):
            with self.subTest(reason=reason):
                self.assertIn(reason, _describe_source(self.home, reason))

    def test_a_source_without_a_version_file_says_so(self):
        # Silence here would read as "same version", which is the failure
        # this whole line exists to end.
        bare = self.root / "bare"
        bare.mkdir()
        self.assertEqual("no VERSION file", _source_version(bare))
        self.assertIn("no VERSION file", _describe_source(bare, "default"))

    def test_a_missing_source_still_raises(self):
        # The rewrite that added the reason must not drop the check that
        # was there: a source that does not exist is an error, not a line.
        with self.assertRaises(FileNotFoundError):
            _resolve_source_root_and_reason(str(self.root / "nope"))


if __name__ == "__main__":
    unittest.main()
