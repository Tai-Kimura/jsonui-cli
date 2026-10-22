"""The server room's words that come from document_tools, in the page's language (infra_words.py; ticket
2026-10-22-viz-en-document-tools-words-stay-japanese: a cost meter's name and the room's problem lines were Japanese on
the English page).

Every quantity of the load schema, every meter of METER_LABELS, every secret kind of SECRET_JA, every flow code of
FLOW_JA, every refusal and every said kind has its key, and the Japanese table's words are document_tools' own, letter
for letter: under ja, RoomWords and CostLabels give the lines room.Words and view.Labels give (so the Japanese page is
what it was). Under en, none of them has a Japanese letter. The keys are closed both ways: one whose code document_tools
no longer has is red too.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from jui_cli.core.document_tools_import import load_document_tools_module
from jui_cli.viz import i18n, infra_words
from tests.test_viz_bundle import web_text

room = load_document_tools_module("infra.room")[0]
view = load_document_tools_module("infra.cost.view")[0]
load = load_document_tools_module("infra.load")[0]

JAPANESE = re.compile(r"[぀-ヿ㐀-鿿！-｠]")
ROOM_SOURCE = Path(room.__file__).read_text(encoding="utf-8")
SAID = sorted(set(re.findall(r'say=\("(\w+)"', ROOM_SOURCE)))
REFUSED = sorted(r for r in room.REASONS if r != "invalid")   # invalid carries the problems, not a line of its own
FOLDER = "docs/infra"
WHERE = "docs/infra/model.json"


#: a detail of each keyword a schema problem says (model.check_schema: ticket 2026-10-22-infra-schema-errors-say-only-schema)
SCHEMA_DETAIL = {
    "maxLength": {"limit": 200, "length": 236}, "minLength": {"limit": 3, "length": 1}, "pattern": {"pattern": "^[a-z]+$"},
    "enum": {"allowed": "a, b"}, "const": {"allowed": "0"}, "type": {"want": ["string", "integer"], "found": "array"},
    "oneOf": {"n": 2, "fit": 2}, "required": {"field": "category"}, "additionalProperties": {"fields": "id, label"},
    "minimum": {"limit": 1}, "maximum": {"limit": 1000}, "exclusiveMinimum": {"limit": 0}, "finite": {},
    "minItems": {"limit": 1, "count": 0}, "maxItems": {"limit": 20, "count": 21}, "uniqueItems": {"first": 0, "second": 1},
    "propertyNames": {"pattern": "^[a-z]+$"}, "minProperties": {"limit": 1, "count": 0}, "maxProperties": {"limit": 50, "count": 51},
}
SCHEMA_DETAIL = {kw: {"keyword": kw, **d} for kw, d in SCHEMA_DETAIL.items()}


def _table(language: str) -> dict:
    return json.loads(web_text("i18n", f"{language}.json"))


@pytest.fixture
def language():
    before = i18n.active()

    def use(name: str) -> None:
        i18n.activate(i18n.load(name, use_env=False))
    yield use
    i18n.activate(before)


def _room_lines(words) -> dict[str, str]:
    """One line of each kind a room's read says, through ``words``."""
    lines = {
        "json_line": words.json_line(WHERE, 3), "json": words.json(WHERE), "schema": words.schema(WHERE, "/nodes/0"),
        "reference": words.reference(WHERE, "/edges/1", "edge.missing"),
        "spec_duplicate": words.spec_duplicate(WHERE, "/nodes/2/spec"),
        "model_too_big": words.model_too_big(FOLDER, "nodes"), "file_too_large": words.file_too_large(WHERE, 4),
        "unreadable": words.unreadable(WHERE), "not_regular": words.not_regular(WHERE, "fifo"),
        "icon": words.icon("/icons/service:aws/lambda"), "other": words.other(WHERE, "something.new", "a message"),
        "environment_outside": words.environment_outside(WHERE, "/nodes/0/environments"),
        "environment_none": words.environment_none(WHERE, "/nodes/0"), "spec_ha": words.spec_ha(WHERE, "/nodes/0/spec/0"),
    }
    lines.update({f"schema.{kw}": words.schema(WHERE, "/nodes/0/x", d) for kw, d in SCHEMA_DETAIL.items()})
    lines.update({f"schema.type.{t}": words.schema(WHERE, "/nodes/0/x", {"keyword": "type", "want": [t, "null"], "found": t})
                  for t in room.TYPE_JA})
    lines.update({f"exclude.{w}": words.exclude(room.CONFIG_NAME, "/infra/exclude/0", w) for w in room.EXCLUDE_JA})
    lines.update({f"secret.{k}": words.secret(WHERE, "/nodes/0/x", k) for k in room.SECRET_JA})
    lines.update({f"flow:{c}": words.flow(WHERE, "/flows/0", c) for c in room.FLOW_JA})
    lines.update({f"refused.{r}": words.refused(r, FOLDER) for r in REFUSED})
    values = {"mb": 1, "line": 7, "key": "icons", "folder": FOLDER}
    lines.update({f"said.{k}": words.said(k, **values) for k in SAID})
    return lines


def _cost_lines(words) -> dict[str, str]:
    lines = {f"q.{q}": words.quantity(q, d["label"]) for q, d in load.quantities().items()}
    lines.update({f"meter.{m}": words.meter(m) for m in view.METER_LABELS})
    lines.update({"model": words.model(words.quantity("input_tokens", "入力トークン"), "sonnet"), "others": words.others(4)})
    return lines


def test_every_word_document_tools_says_has_its_key_and_the_japanese_is_its_own():
    ja, en = _table("ja"), _table("en")
    want = {f"srv.cost.q.{q}": d["label"] for q, d in load.quantities().items()}
    want.update({f"srv.cost.meter.{m.replace('-', '_')}": w for m, w in view.METER_LABELS.items()})
    want.update({f"srv.room.secret.{k}": w for k, w in room.SECRET_JA.items()})
    want.update({f"srv.room.{c}": w for c, w in room.FLOW_JA.items()})
    assert {k: ja.get(k) for k in want if ja.get(k) != want[k]} == {}
    assert sorted(k for k in want if k not in en) == []


def test_the_keys_are_closed_both_ways():
    """A key whose quantity, meter, kind or code document_tools no longer has is red (it would hide a new one)."""
    ja = _table("ja")
    have = {f"srv.cost.q.{q}" for q in load.quantities()} | {f"srv.cost.meter.{m.replace('-', '_')}" for m in view.METER_LABELS}
    have |= {f"srv.room.secret.{k}" for k in room.SECRET_JA} | {f"srv.room.{c}" for c in room.FLOW_JA}
    have |= {f"srv.room.refused.{r}" for r in REFUSED} | {f"srv.room.said.{k}" for k in SAID}
    have |= {f"srv.room.exclude.{w}" for w in room.EXCLUDE_JA}
    have |= {f"srv.room.schema.{kw}" for kw in room.SCHEMA_JA} | {f"srv.room.type.{t}" for t in room.TYPE_JA} | {"srv.room.type.or"}
    families = ("srv.cost.q.", "srv.cost.meter.", "srv.room.secret.", "srv.room.flow.", "srv.room.refused.", "srv.room.said.",
                "srv.room.exclude.", "srv.room.schema.", "srv.room.type.")
    assert sorted(k for k in ja if k.startswith(families) and k not in have) == []
    assert sorted(k for k in have if k not in ja) == []
    assert (set(infra_words.QUANTITY), set(infra_words.METER), set(infra_words.SECRET), set(infra_words.FLOW),
            set(infra_words.REFUSED), set(infra_words.SAID), set(infra_words.EXCLUDE), set(infra_words.SCHEMA),
            set(infra_words.TYPE)) == (
        set(load.quantities()), set(view.METER_LABELS), set(room.SECRET_JA), set(room.FLOW_JA), set(REFUSED), set(SAID),
        set(room.EXCLUDE_JA), set(room.SCHEMA_JA), set(room.TYPE_JA))
    assert set(SCHEMA_DETAIL) == set(room.SCHEMA_JA)


def test_under_ja_the_lines_are_document_tools_own_letter_for_letter(language):
    language("ja")
    assert _room_lines(infra_words.RoomWords(room.LIMITS, room.EXCLUDE_MAX)) == _room_lines(room.DEFAULT_WORDS)
    assert _cost_lines(infra_words.CostLabels()) == _cost_lines(view.DEFAULT_LABELS)


def test_under_en_no_line_has_a_japanese_letter(language):
    language("en")
    lines = {**_room_lines(infra_words.RoomWords(room.LIMITS, room.EXCLUDE_MAX)), **_cost_lines(infra_words.CostLabels())}
    assert {k: v for k, v in lines.items() if JAPANESE.search(v)} == {}
    assert {k: v for k, v in lines.items() if "{" in v and k != "said.infra_object"} == {}   # every slot filled


def test_the_arm_finds_the_two_the_ticket_names(language):
    """document_tools' own words under en: the meter and the room's line are Japanese — what the page showed."""
    language("en")
    lines = {**_room_lines(room.DEFAULT_WORDS), **_cost_lines(view.DEFAULT_LABELS)}
    found = {k for k, v in lines.items() if JAPANESE.search(v)}
    assert {"meter.instance", "q.requests", "secret.token", "flow:flow.node.missing", "refused.no_infra"} <= found


def test_the_words_reach_reads_and_screens(tmp_path, language):
    """infra_docs reads the room with RoomWords; a refusal's line (short, what the page shows) is the table's."""
    from jui_cli.viz import infra_docs
    language("en")
    (tmp_path / "jui.config.json").write_text('{"infra": {"dir": "docs/infra"}}', encoding="utf-8")
    (tmp_path / "docs" / "infra").mkdir(parents=True)
    status, got = infra_docs.read(tmp_path)
    assert (status, got["ok"], got["reason"]) == (404, False, "no_infra")
    assert got["short"] == "No infra files (*.json) in docs/infra"


def test_the_four_codes_that_had_no_words_reach_the_english_page(tmp_path, language, monkeypatch):
    """Through infra_docs (what the page reads), under en: config.exclude (too_many with its limit), environment.outside,
    environment.none and spec.ha each say their case, and a code with no words yet keeps its message and its code
    (ticket 2026-10-22-doc-validate-infra-config-exclude-prints-only-its-code)."""
    from jui_cli.viz import infra_docs
    language("en")
    model = {"version": 0, "environments": [{"id": "prod", "kind": "production"}, {"id": "dev", "kind": "development"}],
             "groups": [{"id": "g", "kind": "logical", "environments": ["prod"]}],
             "nodes": [{"id": "a", "category": "compute.vm", "group": "g", "environments": ["dev"]},
                       {"id": "db", "category": "database.relational", "spec": [{"key": "deployment", "value": "Multi-AZ"}]}]}
    (tmp_path / "docs" / "infra").mkdir(parents=True)
    (tmp_path / "docs" / "infra" / "main.json").write_text(json.dumps(model), encoding="utf-8")
    (tmp_path / "kept").mkdir()
    exclude = ["kept"] * (room.EXCLUDE_MAX + 1)
    (tmp_path / "jui.config.json").write_text(json.dumps({"infra": {"exclude": exclude}}), encoding="utf-8")
    new = {"file": room.CONFIG_NAME, "path": "/infra", "code": "something.new", "message": "a new message",
           "severity": "warning"}
    real = room.exclude_problems
    monkeypatch.setattr(room, "exclude_problems", lambda root, infra: real(root, infra) + [dict(new)])
    status, got = infra_docs.read(tmp_path)
    assert status == 200 and got["ok"], got
    short = {p["code"]: p["short"] for p in got["problems"]}
    assert sorted(short) == ["config.exclude", "environment.none", "environment.outside", "something.new", "spec.ha"]
    assert {c: s for c, s in short.items() if s.endswith(f": {c}") or JAPANESE.search(s)} == {}
    assert f"more than {room.EXCLUDE_MAX} folders" in short["config.exclude"]
    assert short["something.new"] == "jui.config.json: a new message (something.new)"


def _japanese(o, at="") -> set:
    """Where a reply has Japanese letters, by path."""
    if isinstance(o, dict):
        return set().union(*(_japanese(v, f"{at}.{k}") for k, v in o.items())) if o else set()
    if isinstance(o, list):
        return set().union(*(_japanese(v, f"{at}[]") for v in o)) if o else set()
    return {at} if isinstance(o, str) and JAPANESE.search(o) else set()


def test_the_cost_screens_say_only_the_rooms_own_words_in_japanese(tmp_path, language):
    """infra_cost passes CostLabels to the month, the day and the account: under en, Japanese is left only where the
    room wrote it (a scenario's or a node's label) — not a meter's name, a quantity's, nor the others."""
    from jui_cli.viz import infra_cost as C
    from tests.test_viz_infra_cost import _with_staging
    from tests.test_viz_infra_docs import _room
    language("en")
    C.forget()
    try:
        root = _with_staging(_room(tmp_path, "aws-three-tier"))
        found = set()
        for kw in ({}, {"by": "node"}, {"scenario": "sale", "date": "2026-11-27"}, {"account": True},
                   {"scenario": "staging", "date": "2026-11-02", "account": True}):
            status, got = C.read(root, seq=1, **kw)
            assert status == 200, (kw, got)
            found |= _japanese(got)
    finally:
        C.forget()
    assert found <= {".scenarios[].label", ".month.scenarios[].label", ".month.keys[].label", ".day.nodes[].label"}, found


@pytest.mark.parametrize("lang, want", [
    ("ja", "docs/infra/main.json: /flows/0/description は 200 文字までです（今 236 文字）"),
    ("en", "docs/infra/main.json: /flows/0/description is at most 200 characters (it has 236)")])
def test_a_schema_problem_says_what_is_wrong_on_the_page(tmp_path, language, lang, want):
    """Through infra_docs (what the page reads): a flow's description of 236 characters names the limit and the length
    in the page's language, not "does not fit the schema" alone (ticket 2026-10-22-infra-schema-errors-say-only-schema)."""
    from jui_cli.viz import infra_docs
    language(lang)
    model = {"version": 0, "nodes": [{"id": "api", "category": "compute.container"}],
             "flows": [{"id": "f", "start": "api", "steps": [{"node": "api"}], "description": "x" * 236}]}
    (tmp_path / "docs" / "infra").mkdir(parents=True)
    (tmp_path / "docs" / "infra" / "main.json").write_text(json.dumps(model), encoding="utf-8")
    _status, got = infra_docs.read(tmp_path)
    assert [p["short"] for p in got["problems"]] == [want], got
