"""A load definition's and a price file's problems say what is wrong in the page's language, as the model's do
(ticket 2026-10-22-infra-schema-errors-say-only-schema: `jsonui-doc validate infra-load` / `infra-prices` and jui viz's
コスト printed the English message only, on the Japanese page too).

Every problem load.py and prices.py say has a words key (say=, or a price row's Why) with Japanese words
(room.SIDE_JA), and the words' slots are the values the site gives; the keys are closed both ways. Samples through
read() and the CLI: the line (short) is the Japanese words, letter for letter.
"""
from __future__ import annotations

import ast
import json
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


# ---------------------------------------------------------------- what the cost simulator says on its own

COST_SOURCES = [Path(L.__file__).parent / "cost" / "engine.py", Path(L.__file__).parent / "cost" / "pricebook.py",
                *sorted((Path(L.__file__).parent / "rules").glob("*.py"))]


def _cost_sites() -> tuple[dict[str, set[str]], list[str]]:
    """(words key -> the names of the values its sites give, every warning or notice site that gives no words): each
    _warn's message, each notice's (code, message) and each price book warning is an M.Why with a words key."""
    keys: dict[str, set[str]] = {}
    bare: list[str] = []
    for src in COST_SOURCES:
        tree = ast.parse(src.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "Why" and len(n.args) > 1:
                key = n.args[1]
                names = {k.arg for k in n.keywords}
                if isinstance(key, ast.Constant):
                    keys.setdefault(key.value, set()).update(names)
                else:   # "prices.free_dropped" + (".pool" if ...)
                    for c in ast.walk(key):
                        if isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.startswith("."):
                            keys.setdefault("prices.free_dropped" + c.value, set()).update(names)
                    keys.setdefault("prices.free_dropped", set()).update(names - {"pool"})
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_warn":
                msg = n.args[2]
                notice = isinstance(n.args[1], ast.Constant) and n.args[1].value == "run_node"   # a notice's: below
                if not notice and not (isinstance(msg, ast.Call) and getattr(msg.func, "attr", None) == "Why"):
                    bare.append(f"{src.name}:{n.lineno}")
            if isinstance(n, ast.FunctionDef) and n.name.endswith("_notice"):
                for r in ast.walk(n):
                    if isinstance(r, ast.Return) and isinstance(r.value, ast.List):
                        for t in r.value.elts:
                            m = t.elts[1]
                            if not (isinstance(m, ast.Call) and getattr(m.func, "attr", None) == "Why"):
                                bare.append(f"{src.name}:{r.lineno}")
            if isinstance(n, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == "keyword" for k in n.keys):
                i = [getattr(k, "value", None) for k in n.keys].index("keyword")
                if isinstance(n.values[i], ast.Constant):   # words.cost({"keyword": "prices.room_unused", ...})
                    keys.setdefault(n.values[i].value, set()).update(k.value for k in n.keys if k is not None and k.value != "keyword")
    return keys, bare


def test_every_cost_warning_has_words_and_the_list_is_closed():
    """A warning or notice the cost screen and cost infra show: a new one without words (or words no site says) is red."""
    keys, bare = _cost_sites()
    assert bare == []
    assert set(keys) == set(R.COST_JA)
    assert {k: _slots(w) - keys[k] for k, w in R.COST_JA.items() if _slots(w) - keys[k]} == {}


def test_every_cost_line_is_japanese_and_names_an_empty_service_or_region():
    lines = {k: R.DEFAULT_WORDS.cost({"keyword": k, **{f: "" for f in _slots(w)}}) for k, w in R.COST_JA.items()}
    assert {k: x for k, x in lines.items() if not re.search(r"[ぁ-ん]", x) or "{" in x} == {}
    assert lines["cost.no_price"].startswith("（service 無し）") and lines["cost.no_price"].endswith("（region 無し） にありません")


def test_a_rules_failure_says_its_exceptions_type_only():
    """The line names no value: an exception's text may hold one (a key, a path)."""
    from jsonui_doc_cli.infra.cost import engine as E
    out: list = []
    rule = type("Rule", (), {"id": "aws.x", "cost": lambda self, h: (_ for _ in ()).throw(KeyError("AKIA" + "ABCDEFGHIJKLMNOP"))})()
    assert E.meters_of(rule, {"id": "n"}, None, out, None) == []
    assert R.cost_short(out[0]) == "rule aws.x が失敗しました（KeyError）"


def test_cost_infra_prints_a_load_definitions_line(tmp_path):
    """cost infra: a load definition's problem is its Japanese line (the reply's short), not the English message."""
    fix = Path(__file__).resolve().parent / "fixtures" / "infra" / "aws-three-tier" / "docs" / "infra" / "load"
    doc = json.loads((fix / "ordinary.json").read_text(encoding="utf-8"))
    doc["loads"].append({"node": "nope", "quantities": {"requests": 1}})
    root = _room(tmp_path, {"ordinary.json": doc})
    r = subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "cost", "infra", str(root)], capture_output=True,
                       text=True, cwd=Path(__file__).resolve().parents[1], env={**__import__("os").environ, "JUI_VIZ_HOME": str(tmp_path / "viz")})
    line = f"/loads/{len(doc['loads']) - 1}/node が、モデルに無い node を指しています（この行は使いません）  [load.node_missing]"
    assert r.returncode == 0 and f"WARNING docs/infra/load/ordinary.json: {line}" in r.stdout, r.stdout + r.stderr


def test_cost_infra_prints_its_notes_in_japanese():
    """cost infra's notes (the engine's warnings: the reply's short) are the Japanese lines, not the English message."""
    fix = Path(__file__).resolve().parent / "fixtures" / "infra" / "aws-three-tier"
    r = subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "cost", "infra", str(fix)], capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parents[1], env={**__import__("os").environ, "JUI_VIZ_HOME": "/nonexistent"})
    notes = [ln for ln in r.stdout.splitlines() if ln.startswith("  note: ")]
    assert notes == ["  note: （service 無し） emails（email）の価格が、ap-northeast-1 にありません",
                     "  note: cloudwatch.alarm alarm（month）の価格が、（region 無し） にありません"], r.stdout + r.stderr
