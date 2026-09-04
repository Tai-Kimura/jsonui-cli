"""`SOURCE_DATE_EPOCH`: a receiver can pin the build clock and use `cmp`.

Filed as doc-html-embeds-wall-clock-so-receivers-cannot-verify-byte-invariance.

Every page embeds the moment it was written, so two identical runs rewrite
files whose content did not change — 217 of 369 measured on a consumer's site.
A claim like "only index.html moves" is then unfalsifiable downstream: the
receiver has no normaliser, so they cannot separate a real regeneration from a
clock tick.

These tests compare with plain `filecmp`, deliberately NOT the release script's
normaliser. A test that normalised the clock away would pass whether or not the
variable is honoured, which is the whole failure being fixed.
"""

from __future__ import annotations

import filecmp
import io
import json
import os
import re
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli.reproducible import (
    ENV,
    _warned,
    build_date,
    build_datetime,
    build_datetime_utc,
    build_local_datetime,
)
from jsonui_doc_cli.test_doc import generate_html_directory


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _project(root: Path) -> Path:
    tests = root / "tests"
    _write(tests / "screens" / "a.test.json", json.dumps({
        "type": "screen", "source": {"layout": "c.json"},
        "metadata": {"name": "A"}, "cases": [{"name": "c", "steps": []}]}))
    # Steps that name screens, so the flow actually yields a diagram. With
    # `"steps": []` the mermaid page is skipped entirely ("an empty result
    # means no flow produced a screen"), and its two timestamp exits were
    # never reached — measured: reverting them left every test green.
    _write(tests / "flows" / "f.test.json", json.dumps({
        "type": "flow", "metadata": {"name": "F"},
        "steps": [{"screen": "a", "action": "tap", "id": "go"},
                  {"screen": "b", "action": "waitFor", "id": "done", "timeout": 5000}]}))
    _write(tests / "screens" / "b.test.json", json.dumps({
        "type": "screen", "source": {"layout": "d.json"},
        "metadata": {"name": "B"}, "cases": [{"name": "c", "steps": []}]}))
    return tests


class _Env(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.get(ENV)
        _warned.clear()

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = self._prev
        _warned.clear()


def _tick() -> None:
    """Wait for the wall-clock second to change.

    Without this the two runs finish inside one second, the embedded
    `%H:%M:%S` is the same string either way, and the byte comparison passes
    on an UNFIXED generator — measured: reverting one exit left this test
    green and only the "1970 is in the page" assertion failed. A test whose
    subject is a clock has to cross the clock's resolution, or it is agreeing
    with itself.
    """
    start = int(time.time())
    while int(time.time()) == start:
        time.sleep(0.02)


class TestPinnedBuildsAreByteIdentical(_Env):
    def test_the_comparison_can_detect_a_moving_clock(self):
        """The control for the test below.

        If two unpinned runs separated by a second tick came out identical,
        the comparison would be measuring nothing and the pinned run's
        agreement would prove nothing either.
        """
        os.environ.pop(ENV, None)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests = _project(root)
            a, b = root / "out_a", root / "out_b"
            generate_html_directory(tests, a, "control")
            _tick()
            generate_html_directory(tests, b, "control")
            names = [str(p.relative_to(a)) for p in a.rglob("*") if p.is_file()]
            _, mismatch, _ = filecmp.cmpfiles(a, b, names, shallow=False)
            self.assertTrue(mismatch, "unpinned runs agreed — the comparison is blind")

    def test_two_runs_with_the_variable_set_produce_identical_bytes(self):
        os.environ[ENV] = "0"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests = _project(root)
            a, b = root / "out_a", root / "out_b"
            generate_html_directory(tests, a, "sde")
            _tick()          # the control above proves this is what makes it bite
            generate_html_directory(tests, b, "sde")

            produced = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
            self.assertTrue(produced, "fixture generated nothing, so this asserts nothing")
            self.assertIn(Path("diagram.html"), produced,
                          "the mermaid page is not in the corpus, so its exits are untested")
            match, mismatch, errors = filecmp.cmpfiles(
                a, b, [str(p) for p in produced], shallow=False)
            self.assertEqual(mismatch, [], f"{len(mismatch)} of {len(produced)} files moved")
            self.assertEqual(errors, [])
            self.assertEqual(len(match), len(produced))

    def test_the_pinned_instant_is_what_lands_in_the_page(self):
        # Guards against "identical twice" being achieved by some other
        # accident: the bytes must carry the pinned time, not merely agree.
        os.environ[ENV] = "0"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            generate_html_directory(_project(root), out, "sde")
            pages = [p for p in out.rglob("*.html")
                     if "Generated" in p.read_text(encoding="utf-8")]
            self.assertTrue(pages, "no page carried a Generated stamp")
            for page in pages:
                self.assertIn("1970-01-01", page.read_text(encoding="utf-8"))


class TestUnsetKeepsTheWallClock(_Env):
    def test_without_the_variable_the_stamp_is_the_current_time(self):
        os.environ.pop(ENV, None)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            generate_html_directory(_project(root), out, "plain")
            stamps = []
            for page in out.rglob("*.html"):
                stamps += re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                                     page.read_text(encoding="utf-8"))
            self.assertTrue(stamps, "no timestamp found, so this asserts nothing")
            now = datetime.now()
            for stamp in stamps:
                delta = abs((datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S") - now).total_seconds())
                self.assertLess(delta, 300, f"{stamp} is not the current time")

    def test_every_accessor_falls_back_when_unset(self):
        os.environ.pop(ENV, None)
        this_year = datetime.now().year
        self.assertEqual(build_datetime().year, this_year)
        self.assertEqual(build_datetime_utc().year, this_year)
        self.assertEqual(build_local_datetime().year, this_year)
        self.assertEqual(build_date().year, this_year)


class TestAMalformedValueIsAnnouncedAndIgnored(_Env):
    def test_a_non_integer_warns_once_and_uses_the_wall_clock(self):
        os.environ[ENV] = "yesterday"
        buf = io.StringIO()
        with redirect_stdout(buf):
            first = build_datetime()
            build_datetime()   # a second exit must not warn again
            build_date()
        out = buf.getvalue()
        self.assertEqual(out.count("WARNING [doc]:"), 1, out)
        self.assertIn("SOURCE_DATE_EPOCH is not an integer", out)
        self.assertEqual(first.year, datetime.now().year)

    def test_an_empty_value_is_not_an_error(self):
        os.environ[ENV] = ""
        buf = io.StringIO()
        with redirect_stdout(buf):
            stamp = build_datetime()
        self.assertEqual(buf.getvalue(), "")
        self.assertEqual(stamp.year, datetime.now().year)


#: The wall-clock exits that must STAY on the wall clock, with the reason.
#: Everything else in the package has to go through `reproducible`.
_ALLOWED_RAW_CLOCK = {
    # A retry ETA shown to a person. Pinning it would print an ETA that is
    # not when the retry happens — a wrong answer, not a reproducible one.
    ("figma/api_client.py", "datetime.now"),
    # Elapsed time: a difference of two readings, never written to a file.
    ("test_doc/generator.py", "time.time"),
}

_CLOCK_SPELLINGS = ("datetime.now", "datetime.utcnow", "date.today",
                    "time.time(", "time.localtime", "time.gmtime")


class TestNoExitBypassesTheHelper(unittest.TestCase):
    """Every wall-clock exit is either routed or on the allowlist.

    The behavioural tests above reach four of the rewritten exits; the rest
    live on code paths this fixture does not generate. Without this, those
    could be reverted with the suite still green — measured while writing it:
    reverting `unit.py` and the markdown generator left all seven passing.

    A grep-shaped test is weaker than exercising the path, and it is what is
    available for every exit at once. It fails loudly when a new exit appears,
    which is the case that actually recurs — the fix is to route it, or to add
    it here WITH the reason it must not be routed.
    """

    def test_only_the_allowlisted_exits_read_the_clock_directly(self):
        pkg = Path(__file__).resolve().parent.parent / "jsonui_doc_cli"
        self.assertTrue(pkg.is_dir(), pkg)
        found = set()
        for path in pkg.rglob("*.py"):
            if path.name == "reproducible.py":
                continue
            text = path.read_text(encoding="utf-8")
            for spelling in _CLOCK_SPELLINGS:
                if spelling in text:
                    found.add((path.relative_to(pkg).as_posix(), spelling.rstrip("(")))
        self.assertTrue(found, "no clock spelling found anywhere, so this asserts nothing")
        unexpected = found - _ALLOWED_RAW_CLOCK
        self.assertEqual(
            unexpected, set(),
            "these read the wall clock directly; route them through "
            "jsonui_doc_cli.reproducible or allowlist them with a reason: "
            f"{sorted(unexpected)}")

    def test_the_allowlist_still_describes_reality(self):
        # An allowlist entry whose code moved away becomes a false reassurance
        # that something is being tolerated when it is simply gone.
        pkg = Path(__file__).resolve().parent.parent / "jsonui_doc_cli"
        for rel, spelling in _ALLOWED_RAW_CLOCK:
            text = (pkg / rel).read_text(encoding="utf-8")
            self.assertIn(spelling, text, f"{rel} no longer contains {spelling}")


if __name__ == "__main__":
    unittest.main()
