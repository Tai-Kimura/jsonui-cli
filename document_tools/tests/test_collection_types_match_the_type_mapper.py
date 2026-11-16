"""jsonui-doc's collection reading answers as jui_tools' TypeMapper does.

jsonui-doc keeps its own copy (spec_doc/collection_types) because it runs
where jui_cli is not installed; the protocols are written from the
TypeMapper's. A spelling the two read differently would let the
initial-value check pass a value the generated code does not take, so every
shape both read is compared here, nested and optional ones included.
"""
from __future__ import annotations

import pytest

from jsonui_doc_cli.spec_doc.collection_types import collection_shape as doc_shape

from jui_cli.core import type_mapper  # noqa: E402 — the suite runs beside jui_tools

SPELLINGS = [
    "[String]", "[String]?", "[String?]", "[[Item]]", "[String: Int]", "[String: Int]?",
    "[String: Item?]", "[String: [Item]]", "[[String: Int]]", "[String: Any]",
    "Dictionary(String, String)", "Dictionary(String, String)?", "Dictionary(String, [Item])",
    "Dictionary(String, Map(String, Int))", "Map(String, Item)", "Map(String, Item)?",
    "Map(String, [Item])", "Array(Item)", "Array(Item)?", "List(Item)",
    "[(String) -> Void]", "[String: (Int) -> Void]",
    # not collections in the spec's shapes
    "String", "Int?", "Map<String, Item>", "List<Item>", "Record<string, Item>", "Item[]",
    "(String, Int)", "[]", "[: ]", "Dictionary(String)", "Array()", "[String: Int",
]


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_both_readings_agree(spelling):
    assert doc_shape(spelling) == type_mapper.collection_shape(spelling)


def test_the_comparison_is_not_empty():
    # The control: most of the spellings are collections, so agreement is
    # not two readings that both answer None.
    assert sum(doc_shape(s) is not None for s in SPELLINGS) >= 20
