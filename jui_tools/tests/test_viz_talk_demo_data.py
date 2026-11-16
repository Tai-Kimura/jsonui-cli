"""The talk view's demo data (jui_cli/viz/web/js/31-talk-demo-data.js), what the demo page shows without a server.

Every frame conforms to talk_contract.json; the file is what tools/viz_e2e/talk_demo_gen.py writes (so it is changed
there, not by hand); the ids, unread counts and badges agree with each other; the robots are the demo's own; it is
in the demo bundle only, never the live one; it holds no code.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from jui_cli.viz import bundle
from jui_cli.viz import talk_contract as C
from jui_cli.viz.talk import conv_id

JT = Path(__file__).resolve().parents[1]
FILE = JT / "jui_cli" / "viz" / "web" / "js" / "31-talk-demo-data.js"
DEMO_ROBOTS = {"a0", "a3", "a5", "a2", "a7", "b4", "e6", "f2", "d8", "4f", "7c", "c9", "e1"}


LANGUAGES = ("en", "ja")
#: the one line of code: the set of the page's bundled words' language (I18N.words, web/js/05-i18n.js: ja-JP's is ja;
#: I18N.language for a page from before 2.3.22), English when it has none
PICK = "const TALK_DEMO = TALK_DEMO_BY_LANGUAGE[typeof I18N === 'object' ? (I18N.words || I18N.language) : 'en'] || TALK_DEMO_BY_LANGUAGE.en;"


def by_language() -> dict:
    text = FILE.read_text(encoding="utf-8")
    m = re.search(r"^const TALK_DEMO_BY_LANGUAGE = (\{.*\});\n// eslint-disable-next-line no-unused-vars\n"
                  + re.escape(PICK) + r"\n\Z", text, re.S | re.M)
    assert m, "the file is one const of JSON, then the line that picks the language"
    return json.loads(m.group(1))


def data(lang: str = "ja") -> dict:
    return by_language()[lang]


def test_one_set_per_language_with_the_same_shape():
    """Only the words differ: the same frames, ids, times, states and robots in every language; no Japanese in English."""
    sets = by_language()
    assert set(sets) == set(LANGUAGES)

    def shape(v):
        if isinstance(v, dict):
            return {k: (None if k in ("text", "preview", "summary", "name", "fromName", "toName") else shape(x)) for k, x in v.items()}
        return [shape(x) for x in v] if isinstance(v, list) else v
    assert shape(sets["en"]) == shape(sets["ja"])
    assert not re.search(r"[\u3040-\u30ff\u3400-\u9fff]", json.dumps(sets["en"], ensure_ascii=False))


def frames(d):
    yield d["badges"]
    yield from d["lists"].values()
    yield from d["messages"].values()
    yield from (s["frame"] for s in d["script"])


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_frame_conforms_to_the_contract(lang):
    d = data(lang)
    assert d["contractVersion"] == C.load()["version"]
    for f in frames(d):
        assert C.validate(f) == [], (f["type"], C.validate(f)[:3])


def test_the_file_is_what_the_generator_writes(tmp_path):
    out = tmp_path / "gen.js"
    subprocess.run([sys.executable, str(JT / "tools" / "viz_e2e" / "talk_demo_gen.py"), str(out)], check=True)
    assert out.read_text(encoding="utf-8") == FILE.read_text(encoding="utf-8")


@pytest.mark.parametrize("lang", LANGUAGES)
def test_ids_unread_and_badges_agree(lang):
    d = data(lang)
    for owner, listing in d["lists"].items():
        assert listing["agentId"] == owner
        for conv in listing["items"]:
            assert conv["id"] == conv_id(owner, conv["peer"]["key"]) and conv["owner"] == owner
            detail = d["messages"][f"{owner} {conv['id']}"]
            assert len(detail["items"]) == conv["count"]
            assert all(m["convId"] == conv["id"] for m in detail["items"])
            assert detail["items"][-1]["at"] == conv["lastAt"]
    totals = {o: sum(c["unread"] for c in l["items"]) for o, l in d["lists"].items()}
    assert d["badges"]["counts"] == {o: n for o, n in totals.items() if n}


@pytest.mark.parametrize("lang", LANGUAGES)
def test_it_shows_every_case_the_ui_draws(lang):
    d = data(lang)
    msgs = [m for f in d["messages"].values() for m in f["items"]]
    peers = [c["peer"] for c in d["lists"]["a0"]["items"]]
    assert {m["state"] for m in msgs} >= {"read", "delivered", "undelivered"}
    assert {m["via"] for m in msgs} >= {"session", "subagent", "parent", "external"}
    assert any(not p["alive"] and p["kind"] == "session" for p in peers)          # a peer that ended, in its grace
    assert any(p["kind"] == "external" and p["agentId"] is None for p in peers)   # outside this machine
    assert any(len(p["name"]) > 40 for p in peers)                                 # a name cut to one line
    assert any(len(m["text"]) > 250 and "\n" in m["text"] for m in msgs)           # folded
    assert any("<script>" in m["text"] for m in msgs)                              # drawn as text
    ops = {op["op"] for s in d["script"] if s["frame"]["type"] == "talk.update" for op in s["frame"]["ops"]}
    assert ops == {"message", "conv", "remove"}


@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_robots_are_the_demos_own(lang):
    d = data(lang)
    keys = {c["peer"]["key"] for l in d["lists"].values() for c in l["items"]} | set(d["lists"])
    assert {k for k in keys if not k.startswith("x:")} <= DEMO_ROBOTS



#: What a peer's name or a message may not hold: the demo is public sample data (the docsite's screenshots, every
#: `jui viz export-demo` page), and until 2.3.22 a peer carried a working session's name — its local folder, its role
#: and its train — and a message a real train (ticket 2026-10-24-viz-demo-talk-data-carries-a-real-session-name).
#: A role or a lane in either language, a train, a version (2.3.7, v2.3, 2.3), a home path. The product's own names
#: (jsonui-define, jsonui-test) are the demo's words; the agents repo's folder is not.
NOT_IN_THE_DEMO = re.compile(
    r"jsonui-agents|orchestrator|オーケストレーター|サポート|triage|トリアージ|担当|\btrains?\b|列車"
    r"|/Users/|~/|\bv?\d+\.\d+(?:\.\d+)?\b", re.I)
#: Every folder-like word (two or more parts joined by - or _) a name or a message holds: a closed list, so a project
#: folder written into the demo is red whatever it is called.
FOLDER_LIKE = re.compile(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+")
DEMO_WORDS = {"sign-up", "Sign-up", "cloud-reviewer", "doc_validate_spec", "jsonui-define", "jsonui-test"}
#: The demo's peers: the shop app's sessions, the cloud reviewer, and the subagent (named in the run's language).
DEMO_PEER = re.compile(r"shop-app-[a-z-]+|cloud-reviewer")


def leaks(text: str) -> list:
    """What in one name or message is not the demo's own: a stopped word, or a folder-like word off the list."""
    return [m.group(0) for m in NOT_IN_THE_DEMO.finditer(text)] + [
        w for w in FOLDER_LIKE.findall(text) if w not in DEMO_WORDS and not w.startswith("shop-app-")]


def test_the_stop_list_sees_what_it_is_about():
    """Positive control, in the shape of the mutations that were green against the first version of this arm."""
    lane = "サポー" + "ト7"   # written split, so this file holds no session's name itself
    for text in ("オーケストレーターが範囲を決めました。", f"{lane} さん、決済の画面のテストは止まっていますか？",
                 "Is acme-store-api's payment test stuck?", "The v2.3 train's scope is set.", "2.3 の範囲を決めました。",
                 "The 2.3.7 scope is set.", "the orchestrator's call", "triage took it", "~/work/x", "/Users/x"):
        assert leaks(text), text
    for text in ("Added. doc_validate_spec is green.", "The sign-up screen is done", "subagent a3 (jsonui-define)",
                 "8 characters or more", "shop-app-payment"):
        assert not leaks(text), (text, leaks(text))


def names_and_texts(d):
    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ("name", "fromName", "toName", "text", "preview", "summary") and isinstance(x, str):
                    yield k, x
                else:
                    yield from walk(x)
        elif isinstance(v, list):
            for x in v:
                yield from walk(x)
    yield from walk(d)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_no_name_or_message_is_a_real_folder_session_or_train(lang):
    d = data(lang)
    found = list(names_and_texts(d))
    assert any(k == "name" for k, _ in found) and any(k == "text" for k, _ in found), "the walk saw no names or texts"
    leaked = sorted({(k, v[:80], tuple(leaks(v))) for k, v in found if leaks(v)})
    assert not leaked, f"a real folder, session, role or train in the demo: {leaked}"
    subagents = {c["peer"]["name"] for l in d["lists"].values() for c in l["items"] if c["peer"]["kind"] == "subagent"}
    foreign = sorted({v for k, v in found if k in ("name", "fromName", "toName")
                      and not DEMO_PEER.fullmatch(v) and v not in subagents})
    assert not foreign, f"a peer that is not the demo's own: {foreign}"

def test_in_the_demo_bundle_only_and_data_only():
    assert "31-talk-demo-data.js" in bundle.parts("demo", e2e=False)
    assert "31-talk-demo-data.js" not in bundle.parts("live", e2e=False)
    code = "\n".join(l for l in FILE.read_text(encoding="utf-8").splitlines() if not l.startswith("//"))
    assert code.startswith("const TALK_DEMO_BY_LANGUAGE = {") and code.endswith("\n" + PICK)
    assert "function" not in code and "=>" not in code
    assert "__dbg" not in FILE.read_text(encoding="utf-8")
