"""The `resolveString` text has one source, and all three runtimes read it.

Three consecutive blockers came out of maintaining the same diagnostic as
three hand-written literals, and two of them were produced by the fix for
the one before:

- `f43b8fb1` — the Kotlin copy's `\\"` collapsed inside a non-raw Python
  triple-quoted string; the emitted Kotlin did not compile, and every
  Android branch test in the reporting project ran zero tests.
- `89efcda1` — the web copy spelled a resolver call, which
  `jui lint-strings` read as a real reference. Kotlin and Swift had
  already been worded without one: the three had drifted.
- `73a5e32a` — a reword of the web copy dropped the `+` between two
  adjacent literals. Python joins those; `tsc` reported TS1005.

The properties those left behind (balanced quotes, no adjacent literals,
no generator-language comment) are nets under the old shape and stay where
they are. What is asserted HERE is the shape itself: that a reword has one
place to land.

THE ASSERTION IS IDENTITY, not resemblance. Each runtime must contain the
constant as this module renders it for that language — byte for byte. A
copy left hand-written cannot satisfy that unless it is already identical,
so "one word in the shared constant changes all three outputs" follows: the
render changes, and every runtime still has to contain it.

That deduction is the whole point, so it is worth stating plainly: a test
that only asserted a PHRASE appears in all three would pass on three
hand-written copies, which is exactly the state this replaced.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from jsonui_test_cli import branch_runtime_prose as prose
from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli.branch_tests import generate_branch_tests

from test_branch_tests_generator import BASIC, _project

PLATFORM = {
    "web": dict(kwargs={}, language="ts"),
    "android": dict(kwargs={"platform": "android", "package": "com.acme.app"},
                    language="kotlin"),
    "ios": dict(kwargs={"platform": "ios", "module": "Acme"},
                language="swift"),
}


@pytest.fixture(params=sorted(PLATFORM))
def platform(request):
    return request.param


def _runtime_file(tmp_path, platform) -> str:
    root = _project(tmp_path / platform, BASIC)
    report = generate_branch_tests("checkout", root,
                                   **PLATFORM[platform]["kwargs"])
    return report.runtime_file.read_text(encoding="utf-8")


def _language(platform) -> str:
    return PLATFORM[platform]["language"]


class TestEveryRuntimeReadsTheOneSource:
    def test_the_diagnostic_is_the_rendered_constant(self, tmp_path, platform):
        rendered = prose.message(prose.RESOLVE_STRING_FAILURE,
                                 _language(platform), indent=6)

        # A rendering that came back empty or one line long would make the
        # containment below true of almost anything.
        assert rendered.count("\n") >= 3
        assert rendered in _runtime_file(tmp_path, platform)

    def test_the_runtime_doc_is_the_rendered_constant(self, tmp_path, platform):
        rendered = prose.doc(prose.RESOLVE_STRING_RUNTIME_DOC,
                             _language(platform), indent=0)

        assert rendered.count("\n") >= 10
        assert rendered in _runtime_file(tmp_path, platform)

    def test_the_harness_doc_is_the_rendered_constant(self, platform):
        """Compared against the constants rather than an emitted file: the
        web skeleton's worked example carries `%(screen_const)s`, which is
        substituted on the way out, and re-deriving that substitution here
        would be asserting against this test's own copy of it."""
        language = _language(platform)
        rendered = prose.harness_doc(
            language, summary=bt._HARNESS_SUMMARY[language], indent=2,
            sample=bt._TS_HARNESS_SAMPLE if language == "ts" else ())
        carrier = (bt.HARNESS_SKELETON if language == "ts"
                   else bt.KOTLIN_RUNTIME if language == "kotlin"
                   else bt.SWIFT_RUNTIME)

        assert rendered.count("\n") >= 8
        assert rendered in carrier

    def test_no_marker_survives_into_an_emitted_runtime(self, tmp_path,
                                                        platform):
        """A marker reads as an ordinary `//` comment in all three
        languages, so an unspliced one would ship a runtime with no
        diagnostic and compile cleanly while doing it."""
        assert "<<resolve-string" not in _runtime_file(tmp_path, platform)


class TestTheSpliceRefusesRatherThanNoOps:
    def test_a_missing_marker_raises(self):
        """`str.replace` on a marker that is not there returns the template
        unchanged. That is the one outcome this must not have."""
        with pytest.raises(AssertionError, match="nowhere to go"):
            bt._splice("no marker here", "//<<resolve-string doc>>", "x")

    def test_a_percent_in_the_prose_survives_a_percent_formatted_template(self):
        """The Kotlin runtime is `%`-formatted after splicing. No prose
        carries a `%` today; this is so that a reword which adds one does
        not break Kotlin emission somewhere else entirely."""
        template = bt._splice("//<<resolve-string doc>>\n%(package)s",
                              "//<<resolve-string doc>>", "100% of them",
                              percent_literal=True)

        assert template % {"package": "com.acme"} == "100% of them\ncom.acme"

    def test_the_emitted_kotlin_has_no_doubled_percent(self, tmp_path):
        assert "%%" not in _runtime_file(tmp_path, "android")


class TestTheRenderingIsFaithful:
    """Wrapping must not change the sentence, and joining must not lose it."""

    @pytest.mark.parametrize("language", prose.LANGUAGES)
    @pytest.mark.parametrize("width", [24, 40, 76, 200])
    def test_the_chunks_concatenate_back_to_the_source(self, language, width):
        """The emitter joins chunks with `+`, so the runtime's message is
        the concatenation. If wrapping dropped or doubled a space, the
        message would differ from the prose by an amount no assertion on a
        phrase would notice."""
        for part in prose.RESOLVE_STRING_FAILURE:
            if isinstance(part, prose.Value):
                continue
            assert "".join(prose._chunks(part, language, width)) == part

    @pytest.mark.parametrize("language", prose.LANGUAGES)
    def test_wrapping_never_splits_an_escape_sequence(self, language):
        """Chunks are measured on the escaped form but cut on the
        unescaped one, so a `\\"` cannot be halved. Asserted at a width
        narrow enough that a naive emitter would land a cut inside one."""
        rendered = prose.message(prose.RESOLVE_STRING_FAILURE, language,
                                 indent=6, width=30)

        for line in rendered.splitlines():
            assert not line.rstrip(" +").endswith("\\")

    @pytest.mark.parametrize("language", prose.LANGUAGES)
    def test_every_line_but_the_last_carries_the_join(self, language):
        """`73a5e32a` as a structural guarantee rather than as a net: the
        emitter cannot produce two adjacent literals, because it appends
        the operator to every line it is not finishing on."""
        lines = prose.message(prose.RESOLVE_STRING_FAILURE, language,
                              indent=6, width=34).splitlines()

        assert len(lines) > 1
        assert all(line.endswith(" +") for line in lines[:-1])
        assert not lines[-1].endswith("+")

    @pytest.mark.parametrize("language", prose.LANGUAGES)
    def test_a_quote_in_the_prose_is_escaped_for_every_language(self, language):
        """`f43b8fb1` as a computation rather than as typing. The quotes
        around the two values live in the prose; each language's literal
        rule is applied to them here."""
        rendered = prose.message(('say "hi"',), language, indent=0)

        assert rendered == '"say \\"hi\\""'

    def test_kotlin_also_escapes_a_dollar(self):
        """Kotlin reads `$` inside a plain literal as a template
        expression; TypeScript and Swift do not. The languages differ, so
        the escaper does — the prose does not have to know."""
        assert prose.message(("$5",), "kotlin", indent=0) == '"\\$5"'
        assert prose.message(("$5",), "swift", indent=0) == '"$5"'
