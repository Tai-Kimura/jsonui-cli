"""A branch states the pre-state it starts from, whole.

`when data.*` takes scalars only; `baseline` takes any JSON but sat at the
METHOD. So a list-valued pre-state was fixed for every branch while the
scalars that agree with it moved per branch — and half-moved states are what
that shape builds. One project reached it three times:

  1. scalar override first, list seeded later — the two arranges collided
  2. list seeded first, the existing scalar not noticed — the reverse order
  3. both fields considered, one REJECTED as a substitute for the other, and
     only the other written

The third is why this is not an attention problem. That author wrote the
implementation's own dependency (`verifyEnabled = !submitting && !lockedOut`)
into their notes while deciding, and did not ask whether it should still hold
after the arrange. Three different routes to one shape is a property of the
vocabulary, not of the people.

Widening `when` to take lists does not close it: partial overriding is the
shape, so more types that can be partially overridden is more of it. A branch
now names the whole value of every key it touches.

WHAT THIS DOES NOT FIX, and the tests say so at the bottom: two names for one
state still have to be written together. "A row exists, so the empty view is
hidden" is application knowledge, and no library can hold it. This removes
the accident of two declarations colliding from different places; it does not
remove the need to describe a state completely.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from jsonui_test_cli.branch_tests import _arrange_state


def _arrange(contract_baseline=None, branch=None, conditions=None):
    contract = {"branches": []}
    if contract_baseline is not None:
        contract["baseline"] = contract_baseline
    return _arrange_state(contract, branch or {}, conditions or {})


class TestTheMerge:
    def test_a_branch_key_replaces_the_method_key(self):
        state, _ = _arrange(
            {"rows": [{"id": 1}], "listEmptyVisibility": "gone"},
            {"baseline": {"rows": []}})

        assert state == {"rows": [], "listEmptyVisibility": "gone"}

    def test_keys_the_branch_does_not_name_are_kept(self):
        state, _ = _arrange({"a": 1, "b": 2}, {"baseline": {"a": 9}})

        assert state == {"a": 9, "b": 2}

    def test_a_method_baseline_alone_still_arranges(self):
        """The control: the method-level baseline is unchanged behaviour and
        a branch that declares none has to keep getting it."""
        state, _ = _arrange({"a": 1}, {})

        assert state == {"a": 1}

    def test_a_branch_baseline_alone_arranges(self):
        state, _ = _arrange(None, {"baseline": {"a": 1}})

        assert state == {"a": 1}

    def test_the_replacement_is_whole_not_a_deep_merge(self):
        """The rule that carries the fix. Merging INTO a value would let a
        branch move part of a state again and leave the rest agreeing with
        the old one — the defect, rebuilt one level down."""
        state, _ = _arrange(
            {"filters": {"query": "abc", "page": 3}},
            {"baseline": {"filters": {"query": "xyz"}}})

        assert state == {"filters": {"query": "xyz"}}
        assert "page" not in state["filters"]

    def test_a_list_is_replaced_not_extended(self):
        state, _ = _arrange({"rows": [{"id": 1}, {"id": 2}]},
                            {"baseline": {"rows": [{"id": 9}]}})

        assert state == {"rows": [{"id": 9}]}


class TestTheOrder:
    def test_when_still_wins_over_the_branch_baseline(self):
        """`when` identifies the case; `baseline` builds the pre-state. The
        later-wins order is unchanged, so an existing contract that says
        both keeps meaning what it meant."""
        state, _ = _arrange({"flag": "a"},
                            {"baseline": {"flag": "b"},
                             "when": {"data.flag": "c"}})

        assert state == {"flag": "c"}

    def test_a_condition_witness_still_wins_over_the_branch_baseline(self):
        state, _ = _arrange(
            {"x": 1},
            {"baseline": {"x": 2}, "when": {"cond": "ready"}},
            {"ready": {"witness_true": {"x": 3}}})

        assert state == {"x": 3}

    def test_the_branch_baseline_wins_over_the_method_one(self):
        """The only new precedence, stated on its own so the chain above is
        pinned end to end: method < branch < witness < when."""
        state, _ = _arrange({"x": 1}, {"baseline": {"x": 2}})

        assert state == {"x": 2}


class TestSeededInternalState:
    def test_a_branch_baseline_may_seed_internal_state(self):
        """`state.` routes to the VM's own fields wherever it appears, so a
        branch baseline reaches them the same way the method's does — the
        third reported instance was on that side of the split."""
        _, seed = _arrange({"state.lockedOut": False},
                           {"baseline": {"state.lockedOut": True}})

        assert seed == {"lockedOut": True}

    def test_the_two_faces_stay_separate(self):
        state, seed = _arrange(
            None, {"baseline": {"state.lockedOut": True,
                                "verifyEnabled": False}})

        assert state == {"verifyEnabled": False}
        assert seed == {"lockedOut": True}


class TestWhatIsNotFixed:
    def test_an_incoherent_state_can_still_be_written_deliberately(self):
        """Stated as a test so the limit is not read as an oversight.

        A row present with the empty view visible is still expressible —
        the branch simply says both. What is gone is the ACCIDENT: two
        declarations in different places composing into a state neither
        author wrote. Telling coherent from incoherent needs application
        knowledge ("a row exists, so the empty view is hidden"), which is
        why the reporter withdrew their own third proposal and why nothing
        here tries to.
        """
        state, _ = _arrange(None, {"baseline": {
            "rows": [{"id": 1}], "listEmptyVisibility": "visible"}})

        assert state == {"rows": [{"id": 1}],
                         "listEmptyVisibility": "visible"}

    def test_but_the_whole_pre_state_is_now_readable_in_one_place(self):
        """The property that makes the remaining discipline workable: the
        state a branch arranges is what its own `baseline` says, with no
        second declaration elsewhere to reconcile against."""
        branch = {"baseline": {"rows": [], "listEmptyVisibility": "visible"}}

        state, _ = _arrange({"rows": [{"id": 1}],
                             "listEmptyVisibility": "gone"}, branch)

        assert state == branch["baseline"]
