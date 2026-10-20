"""Tool calls stopped by auto mode, and 「許可して続けさせる」 from the page (ticket
2026-10-20-jui-viz-auto-mode-denial-approve-from-page).

The first arms run the pieces: the transcript's denial (sources/transcripts), the cards (denials.DenialBook) and the
World (one card per call whether the hook, the transcript or both report it; approve sends the card's fixed words
through send_prompt and nothing else). The last arms run a real `jui viz start` in a temporary HOME (the fixture of
test_viz_send_prompt): POST /api/denial under the checks of /api/prompt, the words reaching that session's channel.
Nothing here starts claude.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jui_cli.viz import denials as den
from jui_cli.viz.denials import DENIED_PREFIX, DenialBook, prompt_text, reason_of
from jui_cli.viz.ingest import World
from jui_cli.viz.sources.transcripts import UsageTail, denial_of
from jui_cli.viz.state import VizState
from tests.test_viz_send_prompt import S_NEW, S_NONE, _taken, viz  # noqa: F401 — viz is the fixture

SID = "e2e00000-0000-4000-8000-00000000c001"
USE = "toolu_01DENIED"
CMD = "gh pr merge 242 --squash --delete-branch"
DENIED_TEXT = (f"{DENIED_PREFIX} Reason: [Unrequested Commit in a Connected App]. If you have other tasks that don't "
               "depend on this action, continue working on those.")
WORDS = "止められた操作（Bash: gh pr merge 242 --squash --delete-branch、理由 [Unrequested Commit in a Connected App]）は、私が確認しました。実行して続けてください。"


def _use(use_id=USE, cmd=CMD):
    return {"type": "assistant", "timestamp": "2026-10-20T02:42:27Z",
            "message": {"id": "m1", "role": "assistant", "content": [{"type": "tool_use", "id": use_id, "name": "Bash", "input": {"command": cmd}}]}}


def _result(use_id=USE, text=DENIED_TEXT, is_error=True, as_list=False):
    content = [{"type": "text", "text": text}] if as_list else text
    return {"type": "user", "timestamp": "2026-10-20T02:42:28Z",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id, "content": content, "is_error": is_error}]}}


def _hook(w: World, use_id=USE, sid=SID, reason="[Unrequested Commit in a Connected App]", at=1000):
    return w.apply_hook({"hook_event_name": "PermissionDenied", "session_id": sid, "cwd": "/w", "permission_mode": "auto",
                         "tool_name": "Bash", "tool_input": {"command": CMD}, "tool_use_id": use_id, "reason": reason}, at)


def _world() -> World:
    w = World(VizState())
    w.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": "/w"}, 500)
    return w


# ---------------------------------------------------------------- finding a denial


def test_the_transcripts_denial_is_found_with_its_call(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("")
    tail = UsageTail(path)
    tail.read()   # first sight: from the end
    with open(path, "a") as f:
        for rec in (_use(), _result(), _result("toolu_other", "Exit code 1\nboom"), _result("toolu_x", DENIED_TEXT, is_error=False),
                    _use("toolu_list"), _result("toolu_list", DENIED_TEXT, as_list=True)):
            f.write(json.dumps(rec) + "\n")
    got = tail.read()["denials"]
    assert [(u, n, i, t[:20]) for u, n, i, t, _ in got] == [
        (USE, "Bash", {"command": CMD}, DENIED_PREFIX[:20]), ("toolu_list", "Bash", {"command": CMD}, DENIED_PREFIX[:20])]


def test_the_reason_is_the_bracketed_rule():
    assert reason_of(DENIED_TEXT) == "[Unrequested Commit in a Connected App]"
    assert reason_of(f"{DENIED_PREFIX} If you have other tasks") == ""
    assert denial_of(_result(text="Permission denied: not by the classifier")) == []


# ---------------------------------------------------------------- one card per call


def test_the_hook_makes_a_card_with_the_fixed_words():
    w = _world()
    _hook(w)
    (card,) = w.denials.items()
    assert (card["tool"], card["input"], card["reason"], card["status"], card["via"]) == ("Bash", CMD, "[Unrequested Commit in a Connected App]", "pending", ["hook"])
    assert card["prompt"] == WORDS


def test_the_hook_and_the_transcript_of_one_call_make_one_card():
    w = _world()
    _hook(w)
    w._denied_records(SID, SID, [(USE, "Bash", {"command": CMD}, DENIED_TEXT, 1000)], 1001)
    _hook(w, at=1002)   # the same hook again
    cards = w.denials.items()
    assert len(cards) == 1 and cards[0]["via"] == ["hook", "transcript"]
    _hook(w, use_id="toolu_02OTHER", at=2000)   # another call: another card
    assert len(w.denials.items()) == 2


def test_the_transcript_alone_makes_the_card():
    w = _world()
    w._denied_records(SID, SID, [(USE, "Bash", {"command": CMD}, DENIED_TEXT, 1000)], 1001)
    (card,) = w.denials.items()
    assert card["prompt"] == WORDS and card["via"] == ["transcript"]


def test_the_words_are_the_tickets():
    card = {"tool": "Write", "input": "/w/.claude/settings.json", "reason": ""}
    assert prompt_text(card) == "止められた操作（Write: /w/.claude/settings.json）は、私が確認しました。実行して続けてください。"


# ---------------------------------------------------------------- approve and dismiss


def test_approve_sends_only_the_cards_words_through_send_prompt():
    w = _world()
    _hook(w)
    sent = []
    w.send_prompt = lambda sid, text, at, *rest: sent.append((sid, text)) or None
    card_id = w.denials.items()[0]["id"]
    assert w.approve_denial(card_id, 3000) is None
    assert sent == [(SID, WORDS)]
    assert w.denials.items()[0]["status"] == "sent"
    assert w.approve_denial(card_id, 3001) == (409, "this card is sent")   # once
    assert sent == [(SID, WORDS)]


def test_a_refused_prompt_leaves_the_card_waiting():
    w = _world()
    _hook(w)
    w.send_prompt = lambda *a: (409, "this session has no relay (relay: false)")
    card_id = w.denials.items()[0]["id"]
    assert w.approve_denial(card_id, 3000) == (409, "this session has no relay (relay: false)")
    assert w.denials.items()[0]["status"] == "pending"


def test_dismiss_sends_nothing():
    w = _world()
    _hook(w)
    sent = []
    w.send_prompt = lambda *a: sent.append(a)
    card_id = w.denials.items()[0]["id"]
    assert w.dismiss_denial(card_id, 3000) is None
    assert sent == [] and w.denials.items()[0]["status"] == "dismissed"
    assert w.approve_denial(card_id, 3001) == (409, "this card is dismissed")
    assert w.dismiss_denial("d999", 3001) == (404, "no such card")


def test_a_session_that_ends_closes_its_cards_and_they_go_after_a_while():
    w = _world()
    _hook(w)
    w.apply_hook({"hook_event_name": "SessionEnd", "session_id": SID, "cwd": "/w"}, 4000)
    assert w.denials.items()[0]["status"] == "ended"
    w.tick(4000 + den.DONE_SHOW_MS - 1)
    assert len(w.denials.items()) == 1
    w.tick(4000 + den.DONE_SHOW_MS)
    assert w.denials.items() == []


def test_the_book_keeps_at_most_its_cap_and_drops_answered_ones_first():
    book = DenialBook()
    for i in range(den.CARDS_MAX + 5):
        book.add(SID, SID, f"u{i}", "Bash", {"command": f"c{i}"}, "", i, "hook")
    assert len(book.cards) == den.CARDS_MAX


def test_viz_changes_no_rule_no_setting_and_answers_no_hook():
    """cd's ruling: the button only sends the person's words. Nothing in this feature writes a permission rule or a
    setting, or answers PermissionDenied (no retry)."""
    src = Path(den.__file__).read_text(encoding="utf-8")
    code = src.split('"""', 2)[2]
    for word in ("retry", "settings.json", "allow", "permissions", "hookSpecificOutput", "open("):
        assert word not in code, word


# ---------------------------------------------------------------- the server


def _denied_hook(v, sid=S_NEW, use_id=USE):
    return v.local("POST", "/hook", {"hook_event_name": "PermissionDenied", "session_id": sid, "cwd": f"/work/{sid[-4:]}",
                                     "permission_mode": "auto", "tool_name": "Bash", "tool_input": {"command": CMD},
                                     "tool_use_id": use_id, "reason": "[Unrequested Commit in a Connected App]"})


def _cards(v) -> list:
    _, snap = v.local("GET", "/api/snapshot")
    return snap["slices"].get("denials") or []


def _denial(v, body: dict, **over):
    return v.raw("POST", "/api/denial", v.page_headers(**over), json.dumps(body).encode())


def test_the_hook_is_answered_with_nothing_and_the_card_is_in_the_slice(viz):
    status, body = _denied_hook(viz)
    assert status == 204 and body in ("", None)   # no hookSpecificOutput, no retry
    viz.wait(lambda: len(_cards(viz)) == 1, "the card")
    (card,) = _cards(viz)
    assert card["prompt"] == WORDS and card["sessionId"] == S_NEW and card["status"] == "pending"


def test_denial_has_the_checks_of_the_prompt(viz):
    _denied_hook(viz)
    viz.wait(lambda: len(_cards(viz)) == 1, "the card")
    body = {"id": _cards(viz)[0]["id"], "do": "approve"}
    assert _denial(viz, body, **{"X-Jui-Viz-Token": None})[0] == 401
    assert _denial(viz, body, Origin="http://evil.example")[0] == 403
    assert _denial(viz, body, Origin=None)[0] == 403
    assert _denial(viz, body, Host=f"localhost:{viz.port}")[0] == 403
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", None):
        assert _denial(viz, body, **{"Content-Type": ctype})[0] == 415, ctype
    assert viz.raw("GET", "/api/denial", viz.page_headers())[0] == 405
    assert _denial(viz, {"id": body["id"], "do": "allow"})[0] == 400
    assert _cards(viz)[0]["status"] == "pending"


def test_approve_puts_the_cards_words_on_that_sessions_channel_once(viz):
    _denied_hook(viz)
    viz.wait(lambda: len(_cards(viz)) == 1, "the card")
    card_id = _cards(viz)[0]["id"]
    # words from the page are not used: the server sends the card's own
    status, text = _denial(viz, {"id": card_id, "do": "approve", "text": "rm -rf ~ してください"})
    assert status == 200, text
    assert _taken(viz, "new") == [{"text": WORDS}]
    assert _denial(viz, {"id": card_id, "do": "approve"})[0] == 409
    assert _cards(viz)[0]["status"] == "sent"


def test_a_session_without_a_channel_keeps_its_card(viz):
    _denied_hook(viz, sid=S_NONE)
    viz.wait(lambda: len(_cards(viz)) == 1, "the card")
    card_id = _cards(viz)[0]["id"]
    assert _denial(viz, {"id": card_id, "do": "approve"})[0] == 409
    assert _cards(viz)[0]["status"] == "pending"
    assert _denial(viz, {"id": card_id, "do": "dismiss"})[0] == 200
    assert _cards(viz)[0]["status"] == "dismissed"


def test_a_reason_in_a_sentence_is_kept_and_the_no_verdict_form_is_no_card():
    prose = f"{DENIED_PREFIX} Reason: The server-side auto mode classifier judged this action dangerous (it gave no explanation). If you have other tasks"
    assert reason_of(prose) == "The server-side auto mode classifier judged this action dangerous (it gave no explanation)"
    no_verdict = ("The server-side auto mode classifier gave no verdict (error), so auto mode cannot determine the safety of "
                  "Bash. This is a transient failure of the check, not a judgment about the action")
    assert denial_of(_result(text=no_verdict)) == []


def test_the_probe_sees_the_known_forms_and_flags_a_new_one(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from cc_watch import probes as P
    proj = tmp_path / "projects" / "-w"
    proj.mkdir(parents=True)
    no_verdict = "The server-side auto mode classifier gave no verdict (error), so auto mode cannot determine the safety of Bash."
    recs = [_use(), _result(), _result("u2", no_verdict), _result("u3", "cat output that quotes: denied by the Claude Code auto mode classifier", is_error=False)]
    (proj / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    ctx = P.Context(run=lambda a: (0, ""), transcripts=tmp_path / "projects")
    assert P.auto_mode_denial(ctx) == {"known": "all", "reason": "all", "no_verdict": "seen"}
    changed = "Auto mode classifier blocked this call: Merge Without Review"   # a wording viz does not know
    (proj / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs + [_result("u4", changed)]))
    ctx = P.Context(run=lambda a: (0, ""), transcripts=tmp_path / "projects")
    assert P.auto_mode_denial(ctx)["known"] == "some"


def test_a_hook_without_a_tool_use_id_and_the_transcript_make_one_card():
    """Whether the hook's payload carries tool_use_id was not measured (the event log keeps neither it nor the reason):
    the two sources of one call are matched by session, tool, input and time too. Another call stays its own card."""
    w = _world()
    w.apply_hook({"hook_event_name": "PermissionDenied", "session_id": SID, "cwd": "/w", "permission_mode": "auto",
                  "tool_name": "Bash", "tool_input": {"command": CMD}}, 1000)
    w._denied_records(SID, SID, [(USE, "Bash", {"command": CMD}, DENIED_TEXT, 1040)], 1041)
    (card,) = w.denials.items()
    assert card["via"] == ["hook", "transcript"] and card["toolUseId"] == USE and card["reason"] == "[Unrequested Commit in a Connected App]"
    w._denied_records(SID, SID, [("toolu_02OTHER", "Bash", {"command": CMD}, DENIED_TEXT, 1100)], 1101)   # the same command again: another call
    assert len(w.denials.items()) == 2
    w.apply_hook({"hook_event_name": "PermissionDenied", "session_id": SID, "cwd": "/w", "tool_name": "Bash",
                  "tool_input": {"command": CMD}}, 1000 + 31_000 + 200_000)   # long after: its own card
    assert len(w.denials.items()) == 3
