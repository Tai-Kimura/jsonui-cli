"""A load definition's and a price file's problems say what is wrong in the page's language, as the model's do
(ticket 2026-10-22-infra-schema-errors-say-only-schema: `jsonui-doc validate infra-load` / `infra-prices` and jui viz's
コスト printed the English message only, on the Japanese page too).

Every problem load.py and prices.py say has a words key (say=, or a price row's Why) with Japanese words
(room.SIDE_JA), and the words' slots are the values the site gives; the keys are closed both ways. Samples through
read() and the CLI: the line (short) is the Japanese words, letter for letter.
"""
from __future__ import annotations

import ast
import re
import string
import subprocess
import sys
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra import prices as P
from jsonui_doc_cli.infra import room as R
from test_infra_load import PRICE, _room, _scenario

SOURCES = [Path(L.__file__), Path(P.__file__)]


def _sites() -> dict[str, set[str]]:
    """words key -> the names of the values its sites give (say=(key, {...}), or a price row's M.Why(text, key, **v))."""
    out: dict[str, set[str]] = {}
    for src in SOURCES:
        for n in ast.walk(ast.parse(src.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.Call):
                continue
            for k in n.keywords:
                if k.arg == "say" and isinstance(k.value, ast.Tuple) and isinstance(k.value.elts[0], ast.Constant):
                    d = k.value.elts[1]
                    out.setdefault(k.value.elts[0].value, set()).update(x.value for x in d.keys if isinstance(d, ast.Dict))
            if isinstance(n.func, ast.Attribute) and n.func.attr == "Why" and len(n.args) > 1:
                out.setdefault(n.args[1].value, set()).update(k.arg for k in n.keywords)
    return out


def _slots(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_problem_has_words_and_the_keys_are_closed():
    assert set(_sites()) == set(R.SIDE_JA)


def test_each_words_slot_is_a_value_its_sites_give():
    sites = _sites()
    assert {k: _slots(w) - sites[k] for k, w in R.SIDE_JA.items() if _slots(w) - sites[k]} == {}


@pytest.mark.parametrize("change,line", [
    ({"tiers": [{"from": 0, "price_usd": 1}]}, "には、price_usd と tiers のどちらか 1 つが要ります（この行は使いません）"),
    ({"price_usd": None, "tiers": [{"from": 1, "price_usd": 1}]}, "の最初の tier が 0 から始まりません（この行は使いません）"),
    ({"price_usd": None, "tiers": [{"from": 0, "to": 10, "price_usd": 1}, {"from": 11, "price_usd": 1}]},
     "の tier 1 が、tier 0 の終わる所から始まりません（この行は使いません）"),
    ({"price_usd": None, "tiers": [{"from": 0, "price_usd": 1}, {"from": 10, "price_usd": 1}]},
     "の tier 0 は、終わりが無いのに最後ではありません（この行は使いません）"),
    ({"price_usd": None, "tiers": [{"from": 0, "to": 10, "price_usd": 1}, {"from": 10, "to": 5, "price_usd": 1}]},
     "の tier 1 は、始まる所か、それより前で終わります（この行は使いません）"),
    ({"effective": "2026-02-30"}, "の effective は、暦にある日付ではありません（この行は使いません）"),
])
def test_a_price_rows_line(tmp_path, change, line):
    row = {k: v for k, v in {**PRICE, **change}.items() if v is not None}
    got = P.read(_room(tmp_path, prices={"p.json": {"version": 0, "prices": [row]}}))
    assert [p["short"] for p in got["problems"]] == [f"docs/infra/prices/p.json: /prices/0 {line}"]


def test_a_duplicate_prices_line(tmp_path):
    got = P.read(_room(tmp_path, prices={"p.json": {"version": 0, "prices": [PRICE, dict(PRICE, price_usd=1)]}}))
    assert [p["short"] for p in got["problems"]] == ["docs/infra/prices/p.json: /prices/1 は、行 0 と同じ価格です（先の行を使います）"]


@pytest.mark.parametrize("extra,line", [
    ({"timezone": "Mars/Base"}, "/timezone は、この機械が知らない timezone です"),
    ({"holidays": ["2026-12-01"]}, "/holidays/0 は、2026-11 の月の日付ではありません"),
    ({"environment": "nowhere"}, "/environment は、モデルの環境ではありません（最初の環境を使います）"),
    ({"loads": [{"node": "nope", "quantities": {"requests": 1}}]},
     "/loads/0/node が、モデルに無い node を指しています（この行は使いません）"),
])
def test_a_load_definitions_line(tmp_path, extra, line):
    got = L.read(_room(tmp_path, {"s.json": _scenario(**extra)}))
    assert [p["short"] for p in got["problems"]] == [f"docs/infra/load/s.json: {line}"], got["problems"]


def test_every_line_read_gives_is_filled(tmp_path):
    """Whatever read() finds, its line has no slot left and is in Japanese (not the English message)."""
    doc = _scenario(timezone="Mars/Base", holidays=["2026-12-01"])   # two errors: the file is left out (no row is read)
    got = L.read(_room(tmp_path, {"s.json": doc}, {"p.json": {"version": 0, "prices": [PRICE, PRICE]}}))
    prices = P.read(tmp_path / "room")
    lines = [p["short"] for p in got["problems"] + prices["problems"]]
    assert len(lines) == 3 and not [x for x in lines if "{" in x or not re.search(r"[ぁ-ん]", x)], lines


def test_validate_infra_load_and_prices_print_the_lines(tmp_path):
    root = _room(tmp_path, {"s.json": _scenario(timezone="Mars/Base")}, {"p.json": {"version": 0, "prices": [PRICE, PRICE]}})
    run = lambda what: subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "validate", what, str(root)],  # noqa: E731
                                      capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    load, prices = run("infra-load"), run("infra-prices")
    assert "ERROR docs/infra/load/s.json: /timezone は、この機械が知らない timezone です  [load.timezone]" in load.stdout, load.stdout + load.stderr
    assert "WARNING docs/infra/prices/p.json: /prices/1 は、行 0 と同じ価格です（先の行を使います）  [prices.duplicate]" in prices.stdout, prices.stdout + prices.stderr
