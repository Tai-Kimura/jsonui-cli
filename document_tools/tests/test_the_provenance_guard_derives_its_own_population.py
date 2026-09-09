"""The provenance guard has to find packages its author did not think of.

🚨 WHY THIS FILE EXISTS. The previous guard was written BY someone who had
just been burned by a sibling package resolving to the installed release, and
it still guarded one package out of three. A hand-written population carries
the author's blind spot into the detector built to find that blind spot —
`jui_cli` was resolving to `~/.jsonui-cli/jui_tools` (an editable install
pointing at the distributed copy) the whole time the guard was reporting that
provenance had been checked.

So the arms here are not about `jsonui_test_cli`. They are about whether the
population is DERIVED: whether a package nobody named is covered, and whether
the guard says out loud what it skipped.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conftest import (  # noqa: E402
    REPO,
    path_entry_for,
    provenance,
    reproduction_line,
    scope_lines,
    tool_packages,
)


class ThePopulationComesFromTheTree(unittest.TestCase):
    """⑤ — a package added tomorrow is covered without editing the guard."""

    def _tree(self, root: Path, *rel: str) -> None:
        for r in rel:
            p = root / r
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("")

    def test_a_tool_nobody_named_is_picked_up(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._tree(
                root,
                "alpha_tools/alpha_cli/__init__.py",
                "beta_tools/beta_cli/__init__.py",
            )
            checked, skipped = tool_packages(root)
            # Neither name appears anywhere in the guard's source.
            self.assertEqual(checked, ["alpha_cli", "beta_cli"])
            self.assertEqual(skipped, [])

    def test_the_suite_directory_is_skipped_and_says_so(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._tree(
                root,
                "alpha_tools/alpha_cli/__init__.py",
                "alpha_tools/tests/__init__.py",
            )
            checked, skipped = tool_packages(root)
            self.assertEqual(checked, ["alpha_cli"])
            # 🔻 The skip is RETURNED, not swallowed. A guard that narrows its
            # own population without reporting it looks exactly like a guard
            # that found nothing wrong.
            self.assertEqual(skipped, ["tests"])

    def test_a_directory_that_is_not_a_package_is_not_a_tool(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "alpha_tools" / "not_a_package").mkdir(parents=True)
            (root / "alpha_tools" / "alpha_cli").mkdir(parents=True)
            (root / "alpha_tools" / "alpha_cli" / "__init__.py").write_text("")
            checked, _ = tool_packages(root)
            self.assertEqual(checked, ["alpha_cli"])

    def test_this_checkouts_three_tools_are_all_in_the_population(self):
        checked, skipped = tool_packages(REPO)
        # ① and ② together: the package this suite tests, the sibling the old
        # guard named, and the one it missed.
        for name in ("jsonui_doc_cli", "jsonui_test_cli", "jui_cli"):
            self.assertIn(name, checked)
        self.assertIn("tests", skipped)


class TheVerdictHasThreeStates(unittest.TestCase):
    """④ — 'absent', 'another tree' and 'ok' are different answers."""

    def test_a_package_outside_the_given_root_is_out(self):
        rows = provenance(Path("/nonexistent-root-for-this-arm"), ["pytest"])
        (name, verdict, detail), = rows
        self.assertEqual((name, verdict), ("pytest", "out"))
        # The PATH is reported, not just the word. 'stale', 'absent' and
        # 'a different tree' all read the same without it.
        self.assertTrue(detail.endswith(".py"), detail)

    def test_a_package_that_does_not_exist_is_absent_not_out(self):
        rows = provenance(REPO, ["zz_no_such_package_zz"])
        (_, verdict, _), = rows
        self.assertEqual(verdict, "absent")

    def test_a_package_inside_the_root_is_in(self):
        rows = provenance(REPO, ["jsonui_doc_cli"])
        (_, verdict, detail), = rows
        self.assertEqual(verdict, "in")
        self.assertIn(str(REPO), detail)


class TheGuardNamesItsOwnScope(unittest.TestCase):
    """③ — the run says which packages were examined, and which were not."""

    def test_the_scope_line_counts_both_checked_and_skipped(self):
        lines = scope_lines(REPO)
        checked, skipped = tool_packages(REPO)
        self.assertIn(
            f"({len(checked)} checked, {len(skipped)} skipped)", lines[0])

    def test_every_checked_package_gets_a_line_with_its_path(self):
        lines = "\n".join(scope_lines(REPO))
        for name in tool_packages(REPO)[0]:
            self.assertIn(name, lines)
        self.assertIn(str(REPO), lines)

    def test_the_skipped_directory_is_named_with_its_reason(self):
        lines = "\n".join(scope_lines(REPO))
        self.assertIn("suite directory, not a tool", lines)


class TheReproductionNamesTheDirectory(unittest.TestCase):
    """⑥ — `PYTHONPATH` alone does not reproduce a run; `cwd` is the other half."""

    def test_the_command_changes_directory_first(self):
        line = reproduction_line(REPO, ["jui_cli"])
        self.assertTrue(line.startswith("cd "), line)
        self.assertIn("document_tools", line.split("&&")[0])

    def test_the_command_puts_the_strays_own_directory_on_the_path(self):
        line = reproduction_line(REPO, ["jui_cli"])
        self.assertIn(str(REPO / "jui_tools"), line)

    def test_the_path_entry_is_the_tools_directory_not_the_package(self):
        entry = path_entry_for(REPO, "jsonui_doc_cli")
        self.assertEqual(entry, REPO / "document_tools")

    def test_an_unknown_name_has_no_path_entry(self):
        self.assertIsNone(path_entry_for(REPO, "zz_no_such_package_zz"))


if __name__ == "__main__":
    unittest.main()
