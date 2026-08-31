"""`resolveString` must return the text, and the runtime says so on the call.

The generated test emits `resolveString(h, "<bare key>")`; the harness that
implements it is consumer-owned, and the boundary carried a type but no
contract — what to RETURN was written nowhere. Measured in one project: of
12 harnesses, 9 returned the resolved text and 3 returned the key.

Two of those three had an empty key table, so `resolveString` was never
called: broken and green until that screen's first `@key` contract arrived.
That is why documenting alone does not close it, and why the check fires on
the CALL — a check with no dormant state. Two people on that project wrote
the two different forms, so the skeleton has to teach it as well; the
ticket offered the two remedies as alternatives, and the second observation
makes them both necessary.

The reason is ordered deliberately, in the runtime doc and in every
skeleton:

1. bindings are NOT resolved when a component renders — the value is
   emitted raw, so a data field holds resolved text
2. a field that can also carry a server message has no front-end key for
   that value

Two is sufficient, not the reason. Put first, it reads as "a field servers
never touch may return a key", which is wrong: the render path resolves
keys for no field at all.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli.branch_tests import generate_branch_tests

from test_branch_tests_generator import _contract, _project

PLATFORM = {
    "web": dict(kwargs={}, runtime="RUNTIME_TS"),
    "android": dict(kwargs={"platform": "android", "package": "com.acme.app"},
                    runtime="KOTLIN_RUNTIME"),
    "ios": dict(kwargs={"platform": "ios", "module": "Acme"},
                runtime="SWIFT_RUNTIME"),
}


@pytest.fixture(params=sorted(PLATFORM))
def platform(request):
    return request.param


@pytest.fixture
def project(tmp_path):
    return _project(tmp_path, _contract([
        {"when": {"api.createOrder": "conflict"},
         "then": {"data.screenState": "@order_error_generic"}},
    ]))


def _emitted(project, platform):
    report = generate_branch_tests("checkout", project_root=project,
                                   **PLATFORM[platform]["kwargs"])
    return report.test_file.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Whitespace-normalised, because these strings are wrapped comments and
    a line break must not decide whether an assertion holds."""
    return " ".join(text.split())


def _runtime(platform) -> str:
    return getattr(bt, PLATFORM[platform]["runtime"])


#: How each runtime opens the helper. Slicing from the first mention of the
#: name measured the INTERFACE entry on two platforms, which is a different
#: piece of text that happens to contain the same word.
_OPENERS = ("export function resolveString", "fun resolveString(h",
            "func resolveString(_ h")


def _helper(platform) -> str:
    """The helper's body — the check itself."""
    text = _runtime(platform)
    for opener in _OPENERS:
        if opener in text:
            return text[text.index(opener):]
    raise AssertionError(f"no resolveString helper in the {platform} runtime")


def _helper_doc(platform) -> str:
    """The comment ABOVE the helper. A slice starting at the signature
    cannot contain it, which is what made the first draft of these
    assertions look like the documentation was missing."""
    text = _runtime(platform)
    start = text.index("Resolve an '@key' expectation")
    for opener in _OPENERS:
        if opener in text:
            return text[start:text.index(opener)]
    raise AssertionError(f"no resolveString helper in the {platform} runtime")


def _skeleton(platform) -> str:
    """Where the contract is written for a HUMAN: the web skeleton carries
    it on the interface it generates, the other two on the shared
    `BranchHarness` interface in their runtime."""
    return bt.HARNESS_SKELETON if platform == "web" else _runtime(platform)


class TestTheCallGoesThroughTheCheck:
    def test_the_expectation_calls_the_runtime_helper(self, project, platform):
        """Not `h.resolveString(...)` directly — the helper is the check, so
        a call that bypasses it is a call with no contract."""
        content = _emitted(project, platform)

        assert "resolveString(h, " in content or "resolveString(h," in content
        assert "h.resolveString(" not in content

    def test_the_helper_exists_in_that_platform_runtime(self, platform):
        """The other half. Emitting a call to a helper the runtime does not
        define would fail at compile time in the consumer's project rather
        than here, which is the slowest place to find out."""
        runtime = _runtime(platform)

        assert re.search(r"(function|fun|func) resolveString", runtime)


class TestTheCheckItself:
    """Asserted on the emitted source, since the runtimes are TS/Kotlin/Swift
    and this suite is Python. What is pinned is that each one rejects the
    two key shapes and says how to fix it — not the exact wording."""

    @pytest.mark.parametrize("platform", sorted(PLATFORM))
    def test_it_rejects_the_bare_key_and_a_prefixed_key(self, platform):
        helper = _helper(platform)

        assert "resolved === key" in helper or "resolved == key" in helper
        # `<anything>_<bare key>` — the documented table shape is
        # `<screen>_<key>`, and an arbitrary prefix is caught the same way.
        assert any(form in helper for form in (
            "endsWith(`_${key}`))",     # TS template literal
            'endsWith("_" + key)',      # Kotlin
            'hasSuffix("_" + key)',     # Swift
        )), helper[:300]

    @pytest.mark.parametrize("platform", sorted(PLATFORM))
    def test_it_only_rejects_identifier_shaped_values(self, platform):
        """A false positive here fails a correct project, so the rejection
        is narrowed to values that could be keys at all — real messages
        carry spaces or non-ASCII and cannot match.

        The PREDICATE is pinned, not the word `identifier`. The first draft
        asserted the name, and a mutation replacing the test with `true`
        left it green: it measured that a variable existed, not that it
        constrained anything.
        """
        helper = _helper(platform)

        assert any(form in helper for form in (
            "/^[A-Za-z0-9_]+$/.test(resolved)",              # TS
            "resolved.all { it.isLetterOrDigit() || it == '_' }",   # Kotlin
            "$0.isLetter || $0.isNumber || $0 == \"_\"",      # Swift
        )), helper[:400]

    @pytest.mark.parametrize("platform", sorted(PLATFORM))
    def test_the_failure_names_the_fix(self, platform):
        helper = _flat(_helper(platform))

        assert "strings KEY" in helper
        assert "resolved text" in helper


class TestTheReasonIsOrderedCorrectly:
    """The general reason before the sufficient one, everywhere it is written.

    Reversed, a reader concludes that a field which never carries server
    text may return a key. It may not: rendering resolves nothing.
    """

    @pytest.mark.parametrize("platform", sorted(PLATFORM))
    def test_the_runtime_doc_leads_with_the_render_path(self, platform):
        text = _flat(_helper_doc(platform))

        # "render" for the general reason, "server message" for the
        # sufficient one — tokens each side owns, so the assertion is about
        # the ORDER and not about a phrase surviving a rewrap.
        assert text.index("render") < text.index("server message")

    @pytest.mark.parametrize("platform", sorted(PLATFORM))
    def test_the_harness_doc_leads_with_the_render_path(self, platform):
        text = _flat(_skeleton(platform))

        # "render" for the general reason, "server message" for the
        # sufficient one — tokens each side owns, so the assertion is about
        # the ORDER and not about a phrase surviving a rewrap.
        assert text.index("render") < text.index("server message")

    @pytest.mark.parametrize("platform", sorted(PLATFORM))
    def test_the_harness_interface_states_the_return(self, platform):
        """Written where the harness author reads, not only in the runtime:
        two people on the reporting project wrote the two different forms,
        so a new harness has to be right before anything calls it."""
        assert "RETURN THE RESOLVED TEXT" in _skeleton(platform)


class TestTheSkeletonDefaultFails:
    """The default has to be the failing side, not a plausible return.

    The reporting lane measured 12/12 conforming today and still had one
    instance in their history: a harness left at a skeleton default that
    RETURNED THE KEY. A wrong default is dormant in exactly the way this
    ticket is about — it only shows once that screen gets an `@key`
    contract, and until then the project is green because everyone happened
    to have edited it.

    Measured on the current generator, all three platforms: no skeleton
    returns a key; each one throws until implemented. So this pins an
    invariant that already holds rather than changing behaviour — which is
    the useful form, since the failure it prevents is a default drifting
    back to something that looks helpful.
    """

    @pytest.mark.parametrize("platform", sorted(PLATFORM))
    def test_no_skeleton_hands_back_a_key(self, project, platform):
        skeleton = generate_branch_tests(
            "checkout", project_root=project,
            **PLATFORM[platform]["kwargs"]).harness_file.read_text("utf-8")

        assert "return full" not in skeleton
        assert any(word in skeleton for word in
                   ("throw ", "fatalError", "NotImplementedError"))

    @pytest.mark.parametrize("platform", sorted(PLATFORM))
    def test_the_unimplemented_harness_names_itself(self, project, platform):
        """A default that fails is only useful if the failure says which
        screen it came from — one project runs a dozen of these."""
        skeleton = generate_branch_tests(
            "checkout", project_root=project,
            **PLATFORM[platform]["kwargs"]).harness_file.read_text("utf-8")

        assert "not implemented yet" in skeleton
        assert "checkout" in skeleton
