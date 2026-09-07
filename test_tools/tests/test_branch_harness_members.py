"""The three platforms' harnesses declare the same members.

Reported 2026-09-07: the web harness alone had no way to press a callback.
Consumers reached for `readField("onX")` instead, which returns the ViewModel
METHOD rather than the arrow the data store holds — unbound it throws, and
bound with `.call(vm)` it passes while the registered arrow never runs. Two
independent consumers hit it before either reported it, and one had already
invented the binding workaround.

The asymmetry is the root: three harnesses are read side by side, and a
member missing from one reads as "this platform cannot do that".
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import branch_tests as bt


def _members(block: str) -> set[str]:
    """Member names declared in one harness interface/protocol block."""
    return set(re.findall(r"^\s*(?:val |var |fun |func )?(\w+)\s*[(:]",
                          block, re.M))


#: Where each platform DECLARES the harness contract — and they do not
#: match. Kotlin and Swift declare it in the @generated runtime, so a member
#: added there reaches every existing consumer on the next regeneration. Web
#: declares it in the CONSUMER-OWNED skeleton, which is never overwritten.
#:
#: That asymmetry is why the reported defect could only happen on web, and
#: why a note naming stale harnesses is the only thing that reaches the
#: projects already carrying one. Recorded here rather than in prose because
#: reading `HARNESS_SKELETON` three times is the mistake this file exists to
#: prevent.
_DECLARED_IN = {
    "ts": "HARNESS_SKELETON",          # consumer-owned
    "kotlin": "KOTLIN_RUNTIME",        # @generated
    "swift": "SWIFT_RUNTIME",          # @generated
}


def _harness_blocks() -> dict[str, str]:
    """The three declaration blocks, keyed by the language that emits them."""
    out = {}
    for label, const in _DECLARED_IN.items():
        source = getattr(bt, const)
        m = re.search(r"(?:interface|protocol)\s+BranchHarness\s*\{", source)
        assert m, f"no BranchHarness declaration in the {label} skeleton"
        depth, i, start = 0, m.end() - 1, None
        while i < len(source):
            if source[i] == "{":
                depth += 1
                if start is None:
                    start = i + 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[label] = source[start:i]
    return out


class TestMemberParity:
    def test_all_three_declare_the_pressing_and_settling_members(self):
        blocks = _harness_blocks()
        for label, block in blocks.items():
            members = _members(block)
            assert "invoke" in members, f"{label} has no invoke: {sorted(members)}"
            assert "settle" in members, f"{label} has no settle: {sorted(members)}"

    def test_the_three_member_sets_agree(self):
        """The contract, stated as the thing that broke.

        Asserted as set equality rather than "invoke is present" so the next
        member added to one platform cannot quietly go missing on another —
        which is the whole defect, one member later.
        """
        blocks = _harness_blocks()
        sets = {k: _members(v) for k, v in blocks.items()}
        assert sets["ts"] == sets["kotlin"] == sets["swift"], sets


class TestTheRuntimeOwnsTheSemantics:
    """`invoke` delegates to the runtime rather than being re-implemented.

    The obvious hand-written version falls back to the ViewModel when the
    store has no such key, which reintroduces exactly the defect: the caller
    gets the method, and the arrow never runs.
    """

    def _body(self) -> str:
        m = re.search(r"export function invokeFromStore\((.|\n)*?\n\}",
                      bt.RUNTIME_TS)
        assert m, "invokeFromStore is not exported by the runtime"
        return m.group(0)

    def test_it_reads_the_data_store_not_the_view_model(self):
        body = self._body()
        assert "data[name]" in body
        # The fallback that would undo the fix. Named so the failure says why.
        assert "vm" not in body, (
            "invokeFromStore consults the ViewModel; that is the reported "
            "defect wearing this function's name")

    def test_an_unbound_name_throws_with_the_name_in_it(self):
        body = self._body()
        assert "is not bound in the data store" in body
        assert "throw new Error" in body

    def test_the_read_surface_warns_about_callback_names(self):
        """The docstring gap the report singled out.

        `setState` already warned at length about the ViewModel-first order.
        `readField` had one line and no warning, so the same priority looked
        safe on the read path — the report's author read it that way.
        """
        m = re.search(r"readField\(name: string\): unknown;", bt.HARNESS_SKELETON)
        assert m
        doc = bt.HARNESS_SKELETON[max(0, m.start() - 700):m.start()]
        assert "invoke" in doc
        assert "METHOD" in doc


class TestTheToolNamesWhatTheFixCannotReach:
    """The harness is consumer-owned, so shipping this does not fix anyone.

    An existing harness is never overwritten. The projects that hit the
    defect are exactly the ones that already have harnesses, so the release
    reaches them only if they port it by hand — and a release note is not a
    mechanism. The tool says the file name.
    """

    def test_an_existing_harness_without_invoke_is_named(self, tmp_path):
        harness = tmp_path / "some_screen.ts"
        harness.write_text(
            "export interface BranchHarness {\n"
            "  readField(name: string): unknown;\n}\n", encoding="utf-8")
        assert bt._harness_predates_invoke(harness, created=False) is True

    def test_a_harness_that_has_it_is_not_named(self, tmp_path):
        """The control. A note that fires on a current harness is noise, and
        the ios false positives here already showed what noise costs."""
        harness = tmp_path / "some_screen.ts"
        harness.write_text(
            "export interface BranchHarness {\n"
            "  invoke(name: string, ...args: unknown[]): unknown;\n}\n",
            encoding="utf-8")
        assert bt._harness_predates_invoke(harness, created=False) is False

    def test_a_freshly_written_skeleton_is_not_named(self, tmp_path):
        """It has the member by construction. Reporting it would put the note
        on every first generation, which is the same as hiding it."""
        harness = tmp_path / "some_screen.ts"
        harness.write_text(bt.HARNESS_SKELETON % {
            "screen": "some_screen", "screen_const": "SOME_SCREEN"},
            encoding="utf-8")
        assert bt._harness_predates_invoke(harness, created=True) is False

    def test_the_skeleton_it_writes_would_not_be_named(self, tmp_path):
        """The two halves have to agree: if a fresh skeleton did not satisfy
        the predicate, every project would be told to port from a template
        that lacks the member."""
        harness = tmp_path / "some_screen.ts"
        harness.write_text(bt.HARNESS_SKELETON % {
            "screen": "some_screen", "screen_const": "SOME_SCREEN"},
            encoding="utf-8")
        assert bt._harness_predates_invoke(harness, created=False) is False

    def test_an_unreadable_harness_is_named_rather_than_assumed_current(
            self, tmp_path):
        harness = tmp_path / "some_screen.ts"
        harness.write_bytes(b"\xff\xfe\x00binary")
        assert bt._harness_predates_invoke(harness, created=False) is True


class TestThePerRowCaseIsNamed:
    """Measured on a consumer face 2026-09-07, after `invoke` shipped.

    A porting reader met `branch-harness: '<name>' is not bound in the data
    store` on a per-row callback and read it as a broken `invoke`. It is not:
    `initializeEventHandlers` registers the screen's own handler names and
    nothing else, so a closure built per row — with a row id closed over —
    was never a store entry. Throwing is the contract.

    A doc line, so it is pinned as text; there is no behaviour to assert.
    """

    @staticmethod
    def _flat(text: str) -> str:
        """Comment prose with its wrapping removed.

        A doc line is wrapped by the `*` prefix, and a source string is
        wrapped by the editor, so the sentence a reader sees is never
        contiguous in the file. Matching the raw text finds a phrase only
        when the line breaks happen to fall elsewhere — which is an
        assertion that passes or fails on formatting, not on content. Two of
        these were written here before this helper existed, and both were
        wrong in the direction that FAILS, which is the harmless one.
        """
        return " ".join(text.replace("*", " ").split()).lower()

    def test_the_read_and_press_docs_both_say_it(self):
        flat = self._flat(bt.HARNESS_SKELETON)
        # Both doc blocks: a reader arrives at either one — the one who
        # reached for readField, and the one who called invoke and got the
        # throw.
        assert flat.count("per-row closure") >= 1
        assert "row id baked into it" in flat
        assert "call the viewmodel method" in flat

    # The NOTE's copy of this sentence is asserted where the CLI actually
    # runs (test_branch_tests_check.py), not by scraping cli.py: the two
    # call sites wrap the sentence at different points and adjacent string
    # literals put quotes inside it, so a source match tests the formatting.
    # The rendered line is what a reader is handed.
