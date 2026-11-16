"""`@response.<path>` walks into a list, and says so when it will not.

FastAPI's validation handler answers with the text inside an array —
`{"detail": [{"msg": "…"}]}` — and the string a screen shows is always
`detail[0].msg`. The resolver walked dicts only, so the one response class
where "the screen shows what the server sent" is most worth stating was
the one class that could not state it.

The reporting lane fell back to a literal expectation. That still
discriminates — the passthrough regressing to a generic front-end string
turns it red — but it binds the contract to the mock body, which is the
thing `@response.` exists to avoid. Minor, not a blocker, and named as
such by the reporter.

TWO GATES, and the ticket named one. `jsonui-doc`'s spec validator refuses
the path on shape before generation ever reads a response body, with a
different message; fixing the resolver alone would have moved the refusal
rather than removed it. Measured before implementing:

    spec regex     response.detail.0.msg    rejected
    resolver       detail.0.msg             "the available keys are:
                                             (not an object)"

ONE SPELLING. `detail[0].msg` was offered as an equally acceptable
alternative and is refused by name instead: the rest of this vocabulary is
dotted, and a second spelling is a second thing every reader of a contract
has to know.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.branch_tests import (
    BranchTestGenerationError, _read_response_path,
)

# The reported body, shape for shape.
BODY = {
    "detail": [
        {"type": "too_short", "loc": ["body", "member_ids"],
         "msg": "at least two are required"},
        {"type": "missing", "loc": ["body", "name"], "msg": "required"},
    ],
    "error": {"message": "plain"},
}


def _read(path):
    return _read_response_path(BODY, path, "W", "k", "s")


def _refusal(path) -> str:
    with pytest.raises(BranchTestGenerationError) as raised:
        _read(path)
    return str(raised.value)


class TestItReachesTheValue:
    def test_the_reported_path_resolves(self):
        assert _read("detail.0.msg") == "at least two are required"

    def test_a_later_position_resolves(self):
        """One index working could be a hard-coded zero."""
        assert _read("detail.1.msg") == "required"

    def test_dict_paths_still_resolve(self):
        assert _read("error.message") == "plain"

    def test_a_dict_key_that_looks_like_an_index_still_resolves(self):
        """The list branch is tried first, so a body whose object happens to
        be keyed `"0"` must not be read as a position."""
        body = {"counts": {"0": "none", "1": "one"}}

        assert _read_response_path(body, "counts.0", "W", "k", "s") == "none"


class TestItSaysWhyWhenItWillNot:
    """The reporter asked for this specifically, and it is the half of the
    ticket that is about being stuck rather than about being blocked."""

    def test_landing_on_a_list_asks_for_an_index_and_shows_one(self):
        message = _refusal("detail.msg")

        assert "list of 2 item(s)" in message
        # The old message said "the available keys are: (not an object)",
        # which reads as "there are no candidates" when what it means is
        # "you are standing on a list".
        assert "not an object" in message
        assert "'detail.0.msg'" in message, message

    def test_brackets_are_answered_with_the_dotted_form(self):
        message = _refusal("detail[0].msg")

        assert "'detail.0.msg'" in message
        # And not by way of "no such key", which is true and useless.
        assert "available keys" not in message

    def test_an_index_past_the_end_says_how_many_there_are(self):
        message = _refusal("detail.9.msg")

        assert "2 item(s)" in message
        assert "past the end" in message

    def test_a_missing_key_still_lists_the_candidates(self):
        """The arm that was already right, kept: the list branch must not
        have taken over the message an object miss produces."""
        message = _refusal("nope.msg")

        assert "available keys are: detail, error" in message

    def test_walking_past_a_scalar_says_where_it_stopped(self):
        message = _refusal("error.message.deeper")

        assert "has a str at error.message" in message

    def test_a_whole_list_is_still_not_a_displayed_value(self):
        assert "is a list" in _refusal("detail")
