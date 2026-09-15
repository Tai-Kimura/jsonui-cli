"""`what_moved.py` must not call a prose change a version stamp.

THE DEFECT THIS EXISTS FOR

The release notice's "what moved" section is derived by
`dev-guide/release/what_moved.py`, which classifies a file as STAMPS when
every line of its diff looks like a version literal. The test was
``^[+-].*(?<![\\w.])v?\\d+\\.\\d+\\.\\d+(?![\\w.])`` — `.*` puts the literal
anywhere on the line, so a line that merely MENTIONS a version satisfied it.

Measured 2026-09-15 on v1.8.84..v1.8.85. The SSoT's only changed line is a
`description` sentence containing "NOT a v10.22.0 regression" — a LIBRARY
version, quoted in prose — so the one-line diff was "all stamp lines" and
`shared/core/attribute_definitions.json`, the widest surface this script has,
was going to be announced as a version stamp. The vendored table carrying the
same sentence went with it.

⚠️ That is the script's OWN docstring defect arriving from the other side. It
exists because notices kept saying "stamps only" — true-sounding sentences
whose denominator is wrong — and it had become one.

🔻 THE FIX IS A DERIVATION, NOT A LONGER REGEX. The versions that count are
the ones this range actually bumps, read from `VERSION` at the two refs. A
range that bumps nothing has no stamp lines at all, which is the safe
direction: the failure being replaced is a file called a stamp when it is not.
"""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "dev-guide" / "release" / "what_moved.py"


def _load():
    spec = importlib.util.spec_from_file_location("what_moved", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(repo), *args), capture_output=True, text=True, check=True
    ).stdout


class AVersionMentionedInProseIsNotAStampTests(unittest.TestCase):
    """Built on a throwaway repository, so the arms describe the CLASSIFIER
    rather than whatever this release happens to contain."""

    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp())
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "t@example.invalid")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "VERSION").write_text("1.0.0\n")
        (self.repo / "shared").mkdir()
        # 🔻 BOTH SIDES OF THE MODIFIED LINE CARRY THE FOREIGN VERSION, and
        # that is not incidental — it is the only shape that reproduces. A
        # modification yields a `-` line and a `+` line, `stamp_only` requires
        # ALL of them to match, so a fixture whose OLD line has no version
        # passes under the defective predicate too and the arm measures
        # nothing. Measured on the real diff: 2 of 2 lines matched, because
        # the sentence being extended ALREADY said "NOT a v10.22.0
        # regression". The arm was written the easy way first and stayed
        # green when the fix was mutated away.
        (self.repo / "shared" / "core.json").write_text(
            '{"note": "NOT a v10.22.0 regression"}\n'
        )
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "base")
        _git(self.repo, "tag", "v1.0.0")

        self.module = _load()
        self.module.REPO = self.repo  # _run() reads this for `git -C`

    def _bump_and(self, extra: str | None = None) -> None:
        (self.repo / "VERSION").write_text("1.0.1\n")
        if extra is not None:
            (self.repo / "shared" / "core.json").write_text(extra)
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "bump")

    def test_prose_naming_another_products_version_is_not_a_stamp(self) -> None:
        """THE TICKETED SHAPE, reduced to one line."""
        self._bump_and('{"note": "NOT a v10.22.0 regression. SCOPE: added prose"}\n')
        self.assertFalse(
            self.module.stamp_only("v1.0.0", "HEAD", "shared/core.json"),
            "a sentence that mentions some other product's version is prose",
        )

    def test_the_file_that_actually_carries_the_bump_is_a_stamp(self) -> None:
        """The boundary. Without this, the arm above would pass on a
        classifier that simply never says STAMPS."""
        self._bump_and()
        self.assertTrue(self.module.stamp_only("v1.0.0", "HEAD", "VERSION"))

    def test_a_line_carrying_the_new_version_anywhere_still_counts(self) -> None:
        """The sibling pin is spelled `...git@vX.Y.Z#subdirectory=`, so the
        literal genuinely does sit mid-line for real stamps."""
        (self.repo / "pin.toml").write_text(
            '"jsonui-test-cli @ git+https://example.invalid/x.git@v1.0.0#subdirectory=t",\n'
        )
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "pin")
        _git(self.repo, "tag", "-f", "v1.0.0")
        (self.repo / "pin.toml").write_text(
            '"jsonui-test-cli @ git+https://example.invalid/x.git@v1.0.1#subdirectory=t",\n'
        )
        self._bump_and()
        self.assertTrue(self.module.stamp_only("v1.0.0", "HEAD", "pin.toml"))

    def test_a_range_that_bumps_nothing_has_no_stamp_lines(self) -> None:
        """The safe direction, stated as an arm: with no bump to point at,
        nothing is a stamp and every file falls through to its real surface."""
        (self.repo / "shared" / "core.json").write_text('{"note": "see v9.9.9"}\n')
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "no bump")
        matcher = self.module.stamp_line_matcher("v1.0.0", "HEAD")
        self.assertFalse(matcher("+  see v9.9.9"))
        self.assertFalse(self.module.stamp_only("v1.0.0", "HEAD", "shared/core.json"))


class EveryPathInThisRepoResolvesToASurfaceTests(unittest.TestCase):
    """The script exits 1 on an unclassified path, which is the right
    behaviour and also means a new top-level artifact silently blocks the
    notice until someone names its surface. Run it against the real range so
    that discovery happens here rather than mid-release."""

    def test_the_last_released_range_classifies_cleanly(self) -> None:
        module = _load()
        tags = subprocess.run(
            ("git", "-C", str(REPO_ROOT), "tag", "--list", "v*", "--sort=-v:refname"),
            capture_output=True, text=True,
        ).stdout.split()
        if len(tags) < 1:
            self.skipTest("no release tags in this checkout")
        import io
        import contextlib

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = module.main(tags[0], "HEAD")
        self.assertEqual(
            rc, 0, f"unclassified path(s) between {tags[0]} and HEAD:\n{buffer.getvalue()}"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
