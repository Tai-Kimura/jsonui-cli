"""A schema problem says what is wrong, by the keyword it breaks (ticket 2026-10-22-infra-schema-errors-say-only-schema):
the line `jsonui-doc validate infra` prints (and jui viz's server room shows) was "<path> がスキーマに合いません" whatever
the keyword, with no limit, no length or count found, no allowed form.

One sample per keyword check_schema says: its Why carries the keyword and the numbers, the Japanese line says them,
and neither carries the value found (each sample's value holds a marker that must not come back). Every keyword
check_schema can say has its words (a new one with none is red). oneOf, minProperties and minLength are checked
(before, `"input_tokens": "lots"` passed and the cost reader raised ValueError).
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra import room as R

MS, LS = M.schema(), L.schema()
MARK = "zq"   # in every string sample's value: never in a line or a message
TOKENS = LS["$defs"]["quantities"]["properties"]["input_tokens"]
BY_SKU = TOKENS["oneOf"][1]["properties"]["by_sku"]

#: keyword: (part of the schema, its root, the value, what the Japanese line says after the path)
SAMPLES = {
    "maxLength": (MS["$defs"]["text"], MS, MARK * 118, "は 200 文字までです（今 236 文字）"),
    "minLength": ({"type": "string", "minLength": 3}, MS, MARK[0], "は 3 文字以上です（今 1 文字）"),
    "pattern": (MS["$defs"]["id"], MS, "Bad " + MARK, "の形が違います（書ける形: ^[a-z0-9][a-z0-9._-]{0,63}$）"),
    "enum": (MS["$defs"]["environment"]["properties"]["kind"], MS, MARK,
             "は production, staging, development, preview, local, other のどれかです"),
    "const": (MS["properties"]["version"], MS, 1, "は 0 です"),
    "type": (MS["$defs"]["text"], MS, 5, "は文字列です（今は整数）"),
    "oneOf": ({"oneOf": [{"type": "number"}, {"type": "integer"}]}, MS, 3,
              "が 2 通りの形のうち 2 通りに合います（1 つだけに合うこと）"),
    "required": (MS["$defs"]["node"], MS, {"id": "api"}, "がありません（書かなければならない欄です）"),
    "additionalProperties": (MS["$defs"]["environment"], MS, {"id": "prod", MARK: 1},
                             "は書けない欄です（ここに書ける欄: id, label, kind）"),
    "minimum": (MS["$defs"]["node"]["properties"]["count"], MS, 0, "は 1 以上です（今の値は 1 より小さい）"),
    "maximum": (MS["$defs"]["node"]["properties"]["count"], MS, 1001, "は 1000 以下です（今の値は 1000 より大きい）"),
    "exclusiveMinimum": ({"type": "number", "exclusiveMinimum": 0}, MS, 0, "は 0 より大きい数です（今の値は 0 以下）"),
    "finite": ({"type": "number"}, MS, float("nan"), "は有限の数です（NaN・Infinity は書けません）"),
    "minItems": (MS["$defs"]["envRefs"], MS, [], "は 1 個以上です（今 0 個）"),
    "maxItems": (MS["properties"]["environments"], MS, [{"id": f"e{i}"} for i in range(21)], "は 20 個までです（今 21 個）"),
    "uniqueItems": (MS["$defs"]["envRefs"], MS, ["a", MARK, MARK], "に同じ物が 2 度あります（1 番目と 2 番目、0 から数えて）"),
    "propertyNames": (LS["properties"]["profiles"], LS, {"Bad " + MARK: {"hourly": [1] * 24}},
                      "の名前の形が違います（書ける形: ^[a-z0-9][a-z0-9._-]{0,63}$）"),
    "minProperties": (BY_SKU, LS, {}, "は 1 個以上です（今 0 個）"),
    "maxProperties": (LS["properties"]["profiles"], LS, {f"p{i}": {"hourly": [1] * 24} for i in range(51)},
                      "は 50 個までです（今 51 個）"),
}


def _first(kw: str):
    node, root, value, _ = SAMPLES[kw]
    found = M.check_schema(value, node, "/x", root)
    assert found, kw
    return found[0]


def test_every_keyword_check_schema_says_has_a_sample_and_words():
    tree = ast.parse(Path(M.__file__).read_text(encoding="utf-8"))
    said = {c.args[1].value for c in ast.walk(tree)
            if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "Why" and len(c.args) > 1}
    assert said == set(SAMPLES) == set(R.SCHEMA_JA)


@pytest.mark.parametrize("kw", sorted(SAMPLES))
def test_the_line_says_what_is_wrong(kw):
    path, why = _first(kw)
    assert isinstance(why, M.Why) and why.keyword == kw
    p = M._problem("main.json", path, "schema", why)
    assert p["detail"]["keyword"] == kw and json.loads(json.dumps(p)) == p
    line = R.short(p, "docs/infra")
    assert line == f"docs/infra/main.json: {p['path']} {SAMPLES[kw][3]}"
    assert "スキーマに合いません" not in line
    assert MARK not in line and MARK not in p["message"] and MARK not in json.dumps(p["detail"])


def test_the_english_message_says_the_numbers_too():
    assert _first("maxLength")[1] == "longer than 200 characters (it has 236)"
    assert _first("minItems")[1] == "needs at least 1 item(s) (it has 0)"
    assert _first("maxItems")[1] == "more than 20 items (it has 21)"
    assert _first("type")[1] == "must be a string (it is an integer)"
    assert _first("uniqueItems")[1] == "has the same item twice (items 1 and 2)"
    assert _first("additionalProperties")[1] == "is not a field of the infra model v0 (the fields here: id, label, kind)"


def test_the_tickets_case_through_validate_infra(tmp_path):
    """A flow's description of 236 characters: the line validate infra prints names the limit and the length."""
    model = {"version": 0, "nodes": [{"id": "api", "category": "compute.container"}],
             "flows": [{"id": "f", "start": "api", "steps": [{"node": "api"}], "description": "あ" * 236}]}
    (tmp_path / "docs" / "infra").mkdir(parents=True)
    (tmp_path / "docs" / "infra" / "main.json").write_text(json.dumps(model), encoding="utf-8")
    got = R.read(tmp_path)
    assert [p["short"] for p in got["problems"]] == ["docs/infra/main.json: /flows/0/description は 200 文字までです（今 236 文字）"]
    r = subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "validate", "infra", str(tmp_path)],
                       capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert r.returncode == 1 and "/flows/0/description は 200 文字までです（今 236 文字）  [schema]" in r.stdout, r.stdout + r.stderr


def test_a_token_quantity_is_one_of_its_forms():
    """oneOf: a string fits neither form (a flow, by_sku); by_sku needs one model (minProperties)."""
    assert M.check_schema(3, TOKENS, "/q", LS) == []
    assert M.check_schema({"by_sku": {"sonnet": 3}}, TOKENS, "/q", LS) == []
    assert M.check_schema("lots", TOKENS, "/q", LS) == [("/q", "must be a number or an object (it is a string)")]
    assert [w.keyword for _, w in M.check_schema({"by_sku": {}}, TOKENS, "/q", LS)] == ["minProperties"]
    assert [w.keyword for _, w in M.check_schema({"by_sku": {"sonnet": -1}}, TOKENS, "/q", LS)] == ["minimum"]
