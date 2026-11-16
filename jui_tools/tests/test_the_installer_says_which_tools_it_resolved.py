"""The installer had no arms at all, and it is what distributes everything.

🚨 WHY THIS FILE EXISTS. On 2026-09-09 a release was distributed with
`JSONUI_TOOLS="sjui,kjui,rjui,jui,test,doc" curl … | bash` — six names, mcp
deliberately absent. The MCP server was installed anyway, and it reset a
checkout whose tracked snapshot then reverted 21 versions. Two separate
mechanisms, both silent:

  1. The variable was set on `curl`. The `bash` on the other side of the pipe
     never saw it, so the installer ran with its default — and the default is
     `all`. The run succeeded, so the output gave no sign that the exclusion
     had not arrived. The README carried that exact form.
  2. `should_install` matched substrings, so `sjui` also selected `jui`. The
     README's own "install specific tools only" example installed a tool it
     did not name.

Nothing here executes an install. The resolution and validation happen before
the dependency check, so running with a PATH that has no `git` exercises them
and stops; `should_install` is extracted and RUN, so these are arms on
behaviour rather than on the text of the script.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO / "installer" / "bootstrap.sh"


def _run(env_extra: dict | None = None, args: list[str] | None = None):
    """Run the installer far enough to resolve tools, with no `git` on PATH."""
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ)
        env.pop("JSONUI_TOOLS", None)
        env["PATH"] = f"{d}:/usr/bin:/bin"
        env["HOME"] = d
        env.update(env_extra or {})
        return subprocess.run(
            ["bash", str(BOOTSTRAP), *(args or [])],
            capture_output=True, text=True, env=env, cwd=d, timeout=60)


def _should_install(tools: str, name: str) -> bool:
    """Run the real `should_install` with a given TOOLS.

    Extracted and EXECUTED rather than pattern-matched: an arm that reads the
    source for `grep -q` would also match the comment explaining why `grep -q`
    was wrong.
    """
    body = []
    keep = False
    for line in BOOTSTRAP.read_text(encoding="utf-8").splitlines():
        if line.startswith("should_install() {"):
            keep = True
        if keep:
            body.append(line)
        if keep and line == "}":
            break
    assert body, "should_install() not found in the installer"
    script = "\n".join(body) + f'\nTOOLS="{tools}"\nshould_install {name}\n'
    return subprocess.run(["bash", "-c", script], timeout=30).returncode == 0


class TheResolvedListIsPrinted(unittest.TestCase):
    """受入① — a list that did not arrive must not look like one that did."""

    def test_the_default_says_it_is_the_default(self):
        out = _run().stdout
        self.assertIn("tools: all", out)
        self.assertIn("was not set in this shell", out)

    def test_the_default_warns_that_all_includes_mcp(self):
        out = _run().stdout
        self.assertIn("INCLUDING the MCP server", out)

    def test_a_list_that_arrives_is_printed_with_its_source(self):
        out = _run({"JSONUI_TOOLS": "sjui,kjui"}).stdout
        self.assertIn("tools: sjui,kjui", out)
        self.assertIn("from JSONUI_TOOLS", out)

    def test_a_list_that_arrives_does_not_get_the_default_warning(self):
        # 陰性対照 for the two arms above: the explanation is for the case
        # where nothing arrived, and printing it always would make it noise.
        out = _run({"JSONUI_TOOLS": "sjui,kjui"}).stdout
        self.assertNotIn("was not set in this shell", out)

    def test_the_flag_is_named_as_the_source(self):
        out = _run(args=["--tools", "test doc"]).stdout
        self.assertIn("tools: test doc", out)
        self.assertIn("from --tools", out)


class AnUnknownNameIsRefused(unittest.TestCase):
    """受入④ — a typo must not quietly install a subset nobody asked for."""

    def test_it_stops(self):
        r = _run({"JSONUI_TOOLS": "sjui,zzz"})
        self.assertNotEqual(r.returncode, 0)

    def test_it_names_the_offending_word_and_the_known_set(self):
        out = _run({"JSONUI_TOOLS": "sjui,zzz"}).stdout + \
              _run({"JSONUI_TOOLS": "sjui,zzz"}).stderr
        self.assertIn("zzz", out)
        self.assertIn("Known:", out)

    def test_a_known_list_is_not_refused(self):
        # 陽性対照: without this, an installer that refused everything passes.
        r = _run({"JSONUI_TOOLS": "sjui,kjui"})
        self.assertNotIn("unknown tool", r.stdout + r.stderr)


class NamesAreMatchedWhole(unittest.TestCase):
    """受入① の残り半分 — the README example installed a tool it did not name."""

    def test_sjui_does_not_select_jui(self):
        self.assertFalse(_should_install("sjui kjui", "jui"))

    def test_sjui_selects_sjui(self):
        self.assertTrue(_should_install("sjui kjui", "sjui"))

    def test_commas_separate_too(self):
        self.assertTrue(_should_install("sjui,kjui", "kjui"))
        self.assertFalse(_should_install("sjui,kjui", "jui"))

    def test_all_selects_everything(self):
        for name in ("sjui", "kjui", "rjui", "jui", "test", "doc", "mcp"):
            self.assertTrue(_should_install("all", name), name)

    def test_a_six_name_list_without_mcp_does_not_select_mcp(self):
        # The exact list the 2026-09-09 distribution passed.
        self.assertFalse(
            _should_install("sjui,kjui,rjui,jui,test,doc", "mcp"))

    def test_a_name_outside_the_list_is_not_selected(self):
        # 陰性対照: an always-true matcher passes every arm above.
        self.assertFalse(_should_install("sjui kjui", "doc"))


class TheReadmeShowsAFormThatWorks(unittest.TestCase):
    """The trap is in the documented invocation, so the doc is part of the fix."""

    #: A variable assignment in front of `curl`. The value may be quoted and
    #: may CONTAIN SPACES — the first version of this pattern used `\S*` and
    #: therefore could not match `JSONUI_TOOLS="sjui kjui" curl … | bash`,
    #: which is the exact line that caused the incident. Measured 2026-09-10:
    #: the mutation was applied, the assert confirming it passed, and the
    #: pattern still returned zero. A detector with a hole at the shape it was
    #: built for reads as "clean".
    BROKEN_FORM = re.compile(
        r"""^[A-Z_]+=(?:"[^"]*"|'[^']*'|\S*)\s+curl\b.*\|\s*(?:bash|sh)\s*$""",
        re.M)

    def test_no_example_puts_the_variable_in_front_of_curl(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        bad = self.BROKEN_FORM.findall(readme)
        self.assertEqual(bad, [], f"broken form still documented: {bad}")

    def test_the_pattern_matches_the_shape_it_is_looking_for(self):
        # 陽性対照 ON THE PATTERN ITSELF. The arm above is a claim of absence,
        # and an absence claim is only as good as the predicate's ability to
        # find the thing when it IS there.
        for line in ('JSONUI_TOOLS="sjui kjui" curl -fsSL x | bash',
                     "JSONUI_TOOLS='a b' curl -fsSL x | sh",
                     "JSONUI_INSTALL_DIR=/opt curl -fsSL x | bash"):
            self.assertTrue(self.BROKEN_FORM.search(line), line)

    def test_the_pattern_does_not_match_the_working_form(self):
        # 陰性対照: a pattern that matched everything would pass the arm above.
        for line in ('curl -fsSL x | JSONUI_TOOLS="sjui kjui" bash',
                     "curl -fsSL x -o /tmp/b.sh && bash /tmp/b.sh --tools 'a'"):
            self.assertIsNone(self.BROKEN_FORM.search(line), line)

    def test_the_working_form_is_documented(self):
        # 陽性対照 for the absence arm: it also passes on a README with no
        # examples at all.
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("| JSONUI_TOOLS=", readme)


if __name__ == "__main__":
    unittest.main()
