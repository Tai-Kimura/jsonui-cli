"""Every tool's test tree is pruned from the distribution, and the population
that says "every" is derived from the repo rather than listed here.

🚨 WHY THIS FILE EXISTS. From the initial commit (2026-05-07) until 2026-09-11
`installer/bootstrap.sh` pruned `test_tools/tests` and nothing else of the
kind. `document_tools/tests` (83 files) and `jui_tools/tests` (116) shipped to
every machine for four months. Nothing detected it because the denylist had no
arm at all — measured: twelve test files mention `bootstrap`, none asserts what
it removes.

The omission read as deliberate. `test_tools` has four lines (`tests`,
`.pytest_cache`, `build`, `*.egg-info`) and `document_tools` has the last two,
so the pairing looked like a decision about which trees ship. It was not: the
introducing commit is "Initial commit" with an empty body, and no file in the
repository states a reason. It surfaced only because a conservation check on
the distribution (3119 present + 3 symlinks + 476 absent = 3598 tracked) forced
every absence to be attributed to a rule, and 476 could be attributed while 199
files sat on the other side with no rule behind them.

🔻 TWO ARMS, BECAUSE PRESENCE IS NOT EFFECT. The first reads the script's text
and asks whether a rule exists for each tree the repo has. The second RUNS the
prune block against a fake tree and asks whether the files are gone. A text
arm alone would pass on a rule that is misspelled, commented out, or placed
after the block that copies the tree away.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO / "installer" / "bootstrap.sh"

#: The one-level glob in the script that covers the Ruby tools' `spec/`.
SPEC_GLOB = "rm -rf */spec"


def _tool_test_trees() -> dict[str, list[str]]:
    """`{tool: [subdir, ...]}` for every `*_tools` package that has one.

    Derived, not listed. A seventh tool added later appears here on its own —
    which is the whole point: the four-month gap existed because the rule was
    written once, by hand, for the trees that existed that day.
    """
    out: dict[str, list[str]] = {}
    for entry in sorted(REPO.iterdir()):
        if not entry.is_dir() or not entry.name.endswith("_tools"):
            continue
        subs = [name for name in ("tests", "spec") if (entry / name).is_dir()]
        if subs:
            out[entry.name] = subs
    return out


def _prune_block(text: str) -> list[str]:
    """The prune lines, in order, ignoring comments and blanks.

    BOTH KINDS. This read `rm -rf ` alone, so `rm -f README.md` and
    `rm -f install.sh` — two tracked files, removed from every distribution
    since the beginning — were outside every arm here: deleting either line
    reddened nothing and shipped them. Two readers counting the distribution
    by hand landed exactly two short for the same reason, and this file is
    the third, which is the one that matters because it is the gate.

    `rm -f */.DS_Store` joins too and changes no count: nothing matching it
    is tracked. What widens is the RULE the arms see, not the population.
    """
    return [line.strip() for line in text.splitlines()
            if line.strip().startswith(("rm -rf ", "rm -f "))]


class ThePopulationIsDerived(unittest.TestCase):
    def test_the_repo_has_the_tools_this_file_assumes(self):
        """A control on the derivation itself.

        If `_tool_test_trees` returned nothing — a renamed directory, a changed
        suffix — every arm below would pass by iterating over an empty set.
        """
        trees = _tool_test_trees()
        self.assertGreaterEqual(
            len(trees), 4,
            f"derived only {len(trees)} tool trees; the population is empty or "
            f"the naming convention moved: {sorted(trees)}")
        self.assertIn("test_tools", trees)
        self.assertIn("document_tools", trees)


class EveryTestTreeIsPruned(unittest.TestCase):
    def test_each_derived_tree_has_a_rule(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        rules = _prune_block(text)
        unpruned = []
        for tool, subs in _tool_test_trees().items():
            for sub in subs:
                explicit = f"rm -rf {tool}/{sub}" in rules
                by_glob = sub == "spec" and SPEC_GLOB in rules
                if not (explicit or by_glob):
                    unpruned.append(f"{tool}/{sub}")
        self.assertEqual(
            [], unpruned,
            "these test trees have no prune rule, so they ship to every "
            f"machine: {unpruned}\n"
            f"(the Ruby tools are covered by {SPEC_GLOB!r}; the Python tools "
            "need a line each)")


class TheRuleActuallyRemovesTheTree(unittest.TestCase):
    """Run the prune lines, do not merely read them.

    The text arm cannot tell a rule that fires from one that is misspelled or
    unreachable. This builds a tree with one file per derived directory, runs
    the extracted `rm -rf` lines against it with the same shell the installer
    uses, and asserts the files are gone.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="prune_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _plant(self, trees: dict[str, list[str]]) -> list[Path]:
        planted = []
        for tool, subs in trees.items():
            for sub in subs:
                target = self.tmp / tool / sub / "planted.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x", encoding="utf-8")
                planted.append(target)
        return planted

    def _run_prune(self):
        rules = _prune_block(BOOTSTRAP.read_text(encoding="utf-8"))
        script = "set -e\n" + "\n".join(rules) + "\n"
        return subprocess.run(["bash", "-c", script], cwd=self.tmp,
                              capture_output=True, text=True)

    #: Tracked top-level files that serve the REPOSITORY and must not ship.
    #: Listed because nothing else distinguishes them — there is no flag on
    #: a file that says "this one is for contributors". Each is asserted to
    #: be tracked as well as pruned, so a rename cannot leave a stale name
    #: here passing against a file that no longer exists.
    REPO_ONLY_FILES = ("README.md", "install.sh")

    def test_the_repo_only_files_are_pruned(self):
        """`rm -f` is a prune rule too, and widening the reader was not enough.

        `_prune_block` read `rm -rf ` alone until 2026-09-11, so these two
        lines were outside every arm: deleting either shipped the file and
        reddened nothing. Widening the reader still changed no outcome —
        every assertion here was about the tool test trees — which is a
        predicate made wider with no effect, and reads as a fix in the log.
        This is the assertion that makes the widening load-bearing.
        """
        rules = _prune_block(BOOTSTRAP.read_text(encoding="utf-8"))
        tracked = subprocess.run(
            ["git", "ls-tree", "--name-only", "HEAD"], cwd=REPO,
            capture_output=True, text=True, check=True).stdout.split()
        for name in self.REPO_ONLY_FILES:
            self.assertIn(name, tracked,
                          f"{name} is not tracked — this list is stale")
            self.assertTrue(
                any(rule.split()[-1] == name for rule in rules),
                f"no prune rule removes {name}, so the distribution ships it")

    def test_the_planted_trees_are_gone(self):
        trees = _tool_test_trees()
        planted = self._plant(trees)
        self.assertTrue(planted, "planted nothing — the derivation is empty")
        proc = self._run_prune()
        self.assertEqual(0, proc.returncode, proc.stderr[:2000])
        survivors = [str(p.relative_to(self.tmp)) for p in planted if p.exists()]
        self.assertEqual(
            [], survivors,
            f"the prune block ran but left these behind: {survivors}")

    def test_a_tree_with_no_rule_survives(self):
        """The positive control for the arm above.

        Without this, `test_the_planted_trees_are_gone` would also pass against
        a prune block that deleted the whole working directory, or against one
        whose rules never matched anything because the plant failed.
        """
        decoy = self.tmp / "not_a_tool" / "tests" / "planted.txt"
        decoy.parent.mkdir(parents=True, exist_ok=True)
        decoy.write_text("x", encoding="utf-8")
        self._plant(_tool_test_trees())
        proc = self._run_prune()
        self.assertEqual(0, proc.returncode, proc.stderr[:2000])
        self.assertTrue(
            decoy.exists(),
            "a directory the denylist does not name was removed — the block is "
            "wider than the rules it is made of")
