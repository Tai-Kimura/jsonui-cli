"""An include's ids in camelCase, spelled as codegen spells them.

shared/core/camel_case_vectors.json holds what sjui/kjui's include_expander.rb
answer (their specs hold them to it). The normalizer is jui_tools' one
snake->camel for ids — layout facts, verify and the hotloader read ids
through it, and the layout generator names data after ids with it — so it
answers the same table. It kept an upper-case part where Ruby's `capitalize`
lowers it: `verify_2FA_form` was `verify2FAForm` here and `verify2faForm` in
the generated screen.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jui_cli.core.normalizer import include_expander as ie
from jui_cli.generators import layout_generator
from jui_cli.hotloader import include_expander as hot

VECTORS = json.loads((Path(__file__).resolve().parents[2] / "shared/core/camel_case_vectors.json")
                     .read_text(encoding="utf-8"))
PREFIX = VECTORS["prefix"]
CASES = VECTORS["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["input"] for c in CASES])
def test_the_normalizer_answers_the_table(case):
    x = case["input"]
    assert (ie._to_camel_case(x), ie._combine_with_prefix(PREFIX, x), ie._combine_with_prefix(None, x)) \
        == (case["camel"], case["combined"], case["unprefixed"])


@pytest.mark.parametrize("case", CASES, ids=[c["input"] for c in CASES])
def test_an_includes_prefix_is_derived_the_way_codegen_derives_it(case):
    """process_includes: an include's id under an outer prefix is combined,
    with none it is camelCased, and without an id the outer prefix stays."""
    x = case["input"]
    assert ie._derive_prefix(PREFIX, x) == case["combined"]
    assert ie._derive_prefix(None, x) == case["camel"]
    assert ie._derive_prefix(PREFIX, None) == PREFIX


def test_one_function_answers_for_every_reader():
    assert layout_generator._snake_to_camel is ie._to_camel_case
    assert hot._to_camel_case is ie._to_camel_case
    assert hot._combine_with_prefix is ie._combine_with_prefix


def _keeps_the_rest(s: str) -> str:
    """The normalizer before this table: each later part's rest kept."""
    if "_" not in s:
        return s
    parts = s.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:] if p)


def test_control_the_table_tells_the_two_spellings_apart():
    """The rows where keeping the rest and capitalize disagree are in the
    table — without them it would pass the defect it exists to catch."""
    differ = sorted(c["input"] for c in CASES if _keeps_the_rest(c["input"]) != c["camel"])
    assert differ == ["clear_URL_button", "info_URL", "verify_2FA_form"], differ
