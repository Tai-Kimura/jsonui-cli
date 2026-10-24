"""The demo's expected results in each language are the prototype's, in other words (ticket
2026-10-21-viz-english-screen-checks §11).

expect_demo.json was recorded from the prototype page, in Japanese; run.py compares the demo suites with it. Run in
English, 140 of those checks were red only for the words. expect_demo.<language>.json holds the same results in that
language's words, taken from a run of the port — so this test holds it to the recording: the same keys, the same
lengths, every number the same (the few that differ by layout are named below with why), every string with the same
numbers in it, and no Japanese left in a language that is not Japanese.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"
JA = re.compile(r"[぀-ヿ㐀-鿿！-｠]")
DIGITS = re.compile(r"\d")
#: numbers that are the layout of the words, not the prototype's behaviour: path -> why
LAYOUT = {
    re.compile(r"^phone/pop-(light|dark)/rows\[\d\]/h$"):
        "a project's chips are one row in Japanese and two in English at 390 px (ticket "
        "2026-10-24-viz-english-phone-chip-and-folder-wrap)",
}
LANGUAGE_FILES = sorted(E2E.glob("expect_demo.*.json"))


def walk(ja, other, path=""):
    """Every difference of shape or number between the two, as (path, what)."""
    if type(ja) is not type(other):
        yield path, f"type {type(ja).__name__} vs {type(other).__name__}"
    elif isinstance(ja, dict):
        if set(ja) != set(other):
            yield path, f"keys differ: {sorted(set(ja) ^ set(other))}"
        for key in ja.keys() & other.keys():
            yield from walk(ja[key], other[key], f"{path}/{key}" if path else key)
    elif isinstance(ja, list):
        if len(ja) != len(other):
            yield path, f"length {len(ja)} vs {len(other)}"
        for i, (a, b) in enumerate(zip(ja, other)):
            yield from walk(a, b, f"{path}[{i}]")
    elif isinstance(ja, str):
        # the digits in order: words joined with no space make "2" + "6 robots" read as 26, so digits, not numbers;
        # a string the suite cut to a length may cut a different number of them off the end
        a, b = DIGITS.findall(ja), DIGITS.findall(other)
        if a[:len(b)] != b[:len(a)]:
            yield path, f"digits differ: {ja!r} vs {other!r}"
    elif ja != other and not any(rx.match(path) for rx in LAYOUT):
        yield path, f"{ja!r} vs {other!r}"


def strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from strings(v, f"{path}/{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def test_there_is_an_english_file():
    assert E2E / "expect_demo.en.json" in LANGUAGE_FILES


@pytest.mark.parametrize("path", LANGUAGE_FILES, ids=lambda p: p.name)
def test_the_same_results_in_other_words(path):
    ja = json.loads((E2E / "expect_demo.json").read_text(encoding="utf-8"))
    other = json.loads(path.read_text(encoding="utf-8"))
    assert list(walk(ja, other)) == []


@pytest.mark.parametrize("path", LANGUAGE_FILES, ids=lambda p: p.name)
def test_no_japanese_left(path):
    left = [(p, s) for p, s in strings(json.loads(path.read_text(encoding="utf-8"))) if JA.search(s)]
    assert left == []


def test_the_layout_numbers_named_are_the_ones_that_differ():
    """Each name in LAYOUT is still a difference: one that is not would keep a number from being compared."""
    ja = json.loads((E2E / "expect_demo.json").read_text(encoding="utf-8"))
    en = json.loads((E2E / "expect_demo.en.json").read_text(encoding="utf-8"))
    diff = []

    def raw(a, b, p=""):
        if isinstance(a, dict):
            for k in a.keys() & b.keys():
                raw(a[k], b[k], f"{p}/{k}" if p else k)
        elif isinstance(a, list):
            for i, (x, y) in enumerate(zip(a, b)):
                raw(x, y, f"{p}[{i}]")
        elif not isinstance(a, str) and a != b:
            diff.append(p)
    raw(ja, en)
    assert all(any(rx.match(p) for p in diff) for rx in LAYOUT), diff


def test_run_py_picks_the_file_by_language():
    import sys
    sys.path.insert(0, str(E2E))
    try:
        from common import expect_demo_file
    finally:
        sys.path.remove(str(E2E))
    assert expect_demo_file("ja").name == expect_demo_file("").name == "expect_demo.json"
    assert expect_demo_file("en") == E2E / "expect_demo.en.json"
    assert "expect_demo_file(os.environ.get(\"JUI_VIZ_LANGUAGE\"" in (E2E / "run.py").read_text(encoding="utf-8")
