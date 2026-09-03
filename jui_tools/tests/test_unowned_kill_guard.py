"""The guard hunts a PROPERTY, and the spellings are only its approximation.

`dev-guide/ci/check-unowned-kills.py` refuses code that signals a process the
tool did not start. That property is not decidable from source, so the check
is a list of spellings that have meant it in practice — and the list has
already had to grow once, which is why it is tested rather than trusted.

The first version (jsonui-cli 1.8.21) matched `pkill|killall`, the spelling
that had just been removed from `rjui hotload stop`. Consumers then found
four lines of the same harm keyed on a port:

    lsof -nP -iTCP:$PORT -sTCP:LISTEN -t | xargs kill

silent under that guard, and silent again in an audit that asked every lane
about "name-matching kills" and collected zeroes — the question named a
spelling, so the answers were about that spelling.

Every spelling below is planted and asserted to FIRE, because a guard that
cannot fire is the failure this family keeps producing: the 1.8.21 guard's
first draft used `\\b`, which git's POSIX matcher does not implement as a
word boundary, and it matched nothing at all including a planted call.

The controls matter as much. Killing a pid you recorded yourself is the
shape that knows what it owns, and the rule exists to leave it available.
"""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "dev-guide" / "ci" / "check-unowned-kills.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_unowned_kills", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


class TheSpellingsFire(unittest.TestCase):
    """Each is a real shape, and each must be caught. Add to this list the
    day another spelling turns up — that is the maintenance this check
    expects, and the docstring says so where a reader will find it."""

    CASES = {
        "name, the original": 'system("pkill -f \'rjui.*watch\'")',
        "name, killall": "killall node",
        "port, fuser": "fuser -k 8790/tcp",
        "port, the consumer's line": "lsof -nP -iTCP:$PORT -sTCP:LISTEN -t | xargs kill",
        "port, command substitution": "kill $(lsof -ti:8790)",
        "port, backticks": "kill `lsof -ti:3000`",
        "name, via pgrep": "kill $(pgrep -f mock)",
        "ps pipeline": 'ps aux | grep mock | awk "{print $2}" | xargs kill',
        "xargs on its own line": "  | xargs kill -9",
    }

    def test_every_known_spelling_is_flagged(self):
        for label, line in self.CASES.items():
            with self.subTest(label):
                self.assertIsNotNone(guard.flag(line), f"{label}: {line}")

    def test_the_reason_says_what_is_wrong_not_just_that_it_matched(self):
        # A reader who hits this in CI has to know why the line is refused,
        # or the only available fix is to reword until the check is quiet.
        self.assertIn("NAME", guard.flag("killall node"))
        self.assertIn("PORT", guard.flag("fuser -k 8790/tcp"))
        self.assertIn("LOOKUP", guard.flag("kill $(lsof -ti:8790)"))


class OwningThePidPasses(unittest.TestCase):
    """The point of the rule is that this stays available."""

    CASES = (
        'kill "$MY_PID"',
        'kill -TERM "$pid"',
        "kill $(cat run.pid)",
        "Process.kill('TERM', pid)",
        "os.kill(self.pid, signal.SIGTERM)",
        'subprocess.run(["kill", str(proc.pid)])',
    )

    def test_a_pid_you_recorded_is_not_flagged(self):
        for line in self.CASES:
            with self.subTest(line):
                self.assertIsNone(guard.flag(line), line)

    def test_a_comment_may_name_the_forbidden_thing(self):
        # Or the rule forbids its own explanation — every removal of one of
        # these leaves a comment saying why it is gone.
        for line in ("# pkill -f is exactly what we do not do",
                     "// killall would end another lane's work",
                     "   * lsof … | xargs kill was the consumer's line"):
            with self.subTest(line):
                self.assertIsNone(guard.flag(line), line)


class TheScanFindsItInATree(unittest.TestCase):
    """Not only the regex: `git ls-files`, the file kinds, the self-exclusion
    and the exit code are what actually runs in CI."""

    def _repo(self, tmp: Path):
        subprocess.run(["git", "init", "-q", str(tmp)], check=True)
        subprocess.run(["git", "-C", str(tmp), "config", "user.email", "t@e.st"], check=True)
        subprocess.run(["git", "-C", str(tmp), "config", "user.name", "t"], check=True)

    def test_a_planted_line_in_a_tracked_shell_script_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._repo(tmp)
            (tmp / "run.sh").write_text("#!/bin/sh\nlsof -ti:8790 | xargs kill\n")
            subprocess.run(["git", "-C", str(tmp), "add", "run.sh"], check=True)
            hits = guard.scan(tmp)
            self.assertEqual(len(hits), 1, hits)
            self.assertEqual(hits[0][0], "run.sh")
            self.assertEqual(hits[0][1], 2)
            self.assertIn("LOOKUP", hits[0][3])

    def test_an_untracked_file_is_not_scanned(self):
        # The rule is about what this repo ships, and `git ls-files` is the
        # denominator. A scratch script in the working tree is not shipped.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._repo(tmp)
            (tmp / "scratch.sh").write_text("killall node\n")
            self.assertEqual(guard.scan(tmp), [])

    def test_an_npm_script_is_scanned(self):
        # The consumer lines that prompted this lived in this kind of place.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._repo(tmp)
            (tmp / "package.json").write_text(
                '{\n  "scripts": {\n    "stop": "lsof -ti:8790 | xargs kill"\n  }\n}\n')
            subprocess.run(["git", "-C", str(tmp), "add", "package.json"], check=True)
            self.assertEqual(len(guard.scan(tmp)), 1)

    def test_the_guard_excludes_itself_and_says_why(self):
        # It must name the spellings it hunts, so it matches itself by
        # construction; this file is what checks it instead.
        self.assertIn("dev-guide/ci/check-unowned-kills.py", guard.SELF_EXCLUDED)
        self.assertIn("jui_tools/tests/test_unowned_kill_guard.py", guard.SELF_EXCLUDED)
        self.assertIn("excludes itself", guard.__doc__.lower().replace("this file excludes itself",
                                                                      "excludes itself"))

    def test_the_repository_it_guards_is_clean(self):
        # The live measurement, not a fixture: if someone adds one of these
        # to this repo, this reddens with the file and line.
        self.assertEqual(guard.scan(REPO_ROOT), [])


if __name__ == "__main__":
    unittest.main()
