"""One layout name never appears in two lists that disagree about it.

`jui verify` prints "Skipped (layout authored externally)" for a spec whose
layout is written by hand, and — further down — "spec(s) name a layout that
does not exist" for a name it cannot resolve. A spec with an unresolvable
`layoutFile` was in BOTH: listed above as an ordinary skip, reported below
as missing.

A consumer read the skip list as recognition — "it is in the list, so the
tool knows about it" — and stopped there. That is the reading two
contradictory lines invite: the reader resolves them by believing the first.
Their conclusion was that nothing checked the name at all, and it took a
measurement to find that something does.

The check itself is not new here and is not duplicated: `_check_spec_coverage`
already reconciles `layoutFile` against the layouts on disk. Only the skip
list changes, so that it stops claiming a name the same run is about to
report as absent.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class SkipListTests(unittest.TestCase):
    """The filter, at the level it is written: names, not rendering."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.layouts = self.root / "layouts"
        self.specs = self.root / "specs"
        self.layouts.mkdir()
        self.specs.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _coverage(self):
        from jui_cli.commands.verify_cmd import _check_spec_coverage
        return _check_spec_coverage(None, {}, self.specs, self.layouts)

    def _filtered(self, skipped_external):
        """The expression `verify` uses, exercised on its own inputs."""
        unresolved = {f"{n}.json" for n in self._coverage().missing_layouts}
        return [n for n in skipped_external
                if n.split(" -> ")[-1] not in unresolved]

    def test_an_unresolvable_name_is_not_listed_as_an_ordinary_skip(self):
        _write(self.layouts / "home.json", {"type": "View"})
        _write(self.specs / "home.spec.json", {
            "type": "screen_spec",
            "metadata": {"name": "home", "layoutFile": "home"}})
        _write(self.specs / "master.spec.json", {
            "type": "screen_spec",
            "metadata": {"name": "master", "layoutFile": "no_such_probe"}})

        self.assertEqual(["no_such_probe"], self._coverage().missing_layouts)
        self.assertEqual(
            [], self._filtered(["master -> no_such_probe.json"]))

    def test_a_layout_that_exists_is_still_listed(self):
        """The control. A filter that dropped everything would pass the test
        above and delete the section's whole purpose — the skip list exists
        so an externally authored layout is visibly accounted for."""
        _write(self.layouts / "home.json", {"type": "View"})
        _write(self.specs / "home.spec.json", {
            "type": "screen_spec",
            "metadata": {"name": "home", "layoutFile": "home"}})

        self.assertEqual([], self._coverage().missing_layouts)
        self.assertEqual(["home -> home.json"],
                         self._filtered(["home -> home.json"]))

    def test_the_two_are_separated_in_one_run(self):
        """Both together, because the defect was that one name reached both
        lists — a run with only one kind cannot show the separation."""
        _write(self.layouts / "home.json", {"type": "View"})
        _write(self.specs / "home.spec.json", {
            "type": "screen_spec",
            "metadata": {"name": "home", "layoutFile": "home"}})
        _write(self.specs / "master.spec.json", {
            "type": "screen_spec",
            "metadata": {"name": "master", "layoutFile": "no_such_probe"}})

        kept = self._filtered(["home -> home.json",
                               "master -> no_such_probe.json"])

        self.assertEqual(["home -> home.json"], kept)
        self.assertIn("no_such_probe", self._coverage().missing_layouts)


class ExitCodeTests(unittest.TestCase):
    """What the reporter measured as `exit 0`, explained rather than changed.

    `jui verify` alone reports; `--fail-on-diff` gates. On the reporting
    project `requireSpecPerScreen` is true, so the unresolvable name DOES
    fail the gated form — their exit 0 came from running the ungated one.
    Pinned so the relationship stays stated somewhere a reader can find it.
    """

    def test_the_coverage_gap_gates_only_when_both_are_declared(self):
        import inspect
        from jui_cli.commands import verify_cmd

        source = inspect.getsource(verify_cmd.cmd_verify)

        self.assertIn("require_coverage and coverage_gap", source)
        self.assertIn("args.fail_on_diff", source)
