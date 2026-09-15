"""A "this changes no code" claim must be derived, because reading it is wrong.

THE DEFECT THIS EXISTS FOR

Gates read grammar and tests. A sentence in a release notice saying a change is
documentation-only is believed, because reading the diff is tedious — and
because the obvious way to read it gives the wrong answer: a predicate that
skips `^[-+]\\s*#` still counts every changed DOCSTRING line as code, since a
docstring is not a `#` comment. A person skimming the same diff makes the same
mistake. Measured 2026-09-15 on v1.8.89..v1.8.90, where the claim held for
`parity.py` and NOT for the release as a whole — the version stamps are code,
and the tag body's opening sentence said otherwise.

So the classification is derived from the parsed tree with leading docstrings
removed, which also survives reformatting and moved comments.

⚠️ AND THE COMPARISON NEEDS ITS OWN CONTROL. Two files that cannot be read
compare equal, and so do two reads of the same blob — both would report "prose
only" from a dead instrument. Each is a separate, named outcome here.
"""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "check_prose_only.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_prose_only", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(repo), *args), capture_output=True, text=True, check=True
    ).stdout


class ProseOnlyIsDerivedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load()
        self.repo = Path(tempfile.mkdtemp())
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "t@example.invalid")
        _git(self.repo, "config", "user.name", "t")

    def _commit(self, files: dict[str, str], message: str) -> None:
        for name, body in files.items():
            (self.repo / name).write_text(body, encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", message)

    def _classify(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.module.main(["x", "v0", "HEAD", str(self.repo)])
        return buffer.getvalue()

    def test_a_rewritten_docstring_is_prose_even_with_a_hash_inside(self) -> None:
        """THE SHAPE A LINE-BASED READING GETS WRONG. The new docstring holds
        a `#` and quotes and spans several lines; none of that is code."""
        self._commit({"m.py": '"""Old."""\ndef f(a):\n    """Adds."""\n    return a + 1\n'}, "base")
        _git(self.repo, "tag", "v0")
        self._commit(
            {"m.py": '"""New, longer, with a # hash and "quotes" in it."""\n'
                     'def f(a):\n    """Adds one.\n\n    Several lines that a\n'
                     '    line reader calls code.\n    """\n    return a + 1\n'},
            "prose",
        )
        out = self._classify()
        self.assertIn("PROSE ONLY  m.py", out)
        self.assertIn("prose-only 1", out)

    def test_a_changed_expression_is_code(self) -> None:
        """The boundary. Without it the arm above would pass on a classifier
        that says PROSE ONLY for everything."""
        self._commit({"m.py": '"""D."""\ndef f(a):\n    return a + 1\n'}, "base")
        _git(self.repo, "tag", "v0")
        self._commit({"m.py": '"""D."""\ndef f(a):\n    return a + 2\n'}, "code")
        out = self._classify()
        self.assertIn("code moved  m.py", out)
        self.assertIn("prose-only 0", out)

    def test_an_unparseable_file_is_not_agreement(self) -> None:
        self._commit({"m.py": "def g(): return 1\n"}, "base")
        _git(self.repo, "tag", "v0")
        self._commit({"m.py": "def g(: return 1\n"}, "broken")
        out = self._classify()
        self.assertIn("NOT COMPARABLE", out)
        self.assertIn("does not parse", out)
        self.assertIn("prose-only 0", out)

    def test_identical_blobs_are_not_prose_only(self) -> None:
        """A file can be in the diff with its content unchanged (a mode
        change). Calling that "prose only" inflates the count with files
        nothing happened to."""
        self._commit({"m.py": "X = 1\n"}, "base")
        _git(self.repo, "tag", "v0")
        (self.repo / "m.py").chmod(0o755)
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "mode only")
        out = self._classify()
        self.assertIn("raw sources identical", out)
        self.assertIn("prose-only 0", out)

    def test_non_python_files_are_reported_not_dropped(self) -> None:
        """🔻 A count that quietly covered only part of the range would be
        worse than no count."""
        self._commit({"m.py": '"""D."""\nX = 1\n', "a.rb": "x = 1\n"}, "base")
        _git(self.repo, "tag", "v0")
        self._commit({"m.py": '"""E."""\nX = 1\n', "a.rb": "x = 2\n"}, "both")
        out = self._classify()
        self.assertIn("not checked  a.rb", out)
        self.assertIn("not checked (non-python) 1", out)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
