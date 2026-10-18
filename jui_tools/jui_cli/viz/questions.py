"""Question cards: AskUserQuestion answered from the browser (requester, 10-18).

"vizの許可の機能が許可じゃなくて選択肢の選択のパターンに対応してない。複数選択しあるパターンあるし自由記述もあるから全部対応させて"

AskUserQuestion needs no permission, so no PermissionRequest comes; its hook is PreToolUse. The documented
answer (code.claude.com hooks.md, "Tools that require user interaction"): permissionDecision "allow" with an
updatedInput that is the whole input — the questions as they came — plus ``answers``, keyed by the question's
text, valued by the chosen option's label; multiple choices are labels joined with commas.

Life of a card:
  pending --browser answer--> sent --PostToolUse--> answered (browser)
     |--PostToolUse first (the terminal answered)--> answered_in_terminal
     \\--Stop, SessionEnd, the hook gave up and the tool ran / 10 min--> expired

A card can be answered from the browser only while a synchronous hook (forward.py --ask) waits on it, and only
when everything it asks fits on the card (every question, header, label, description and preview in full).

Measured on a real interactive session (Claude Code 2.1.302, the requester's terminal, 10-18): while the hook waits,
the terminal shows NO question dialog — the person cannot answer there until the hook gives up — and the hook's
answer is used whenever it comes. So the wait is short unless someone is answering: askWaitSec from the hook's
arrival, renewed (hold) by every input on the card up to askMaxSec in all; "ターミナルで答える" on the card
(release) ends the wait at once with nothing printed, and the terminal's dialog then opens as usual.
"""
from __future__ import annotations

import itertools
import secrets

EXPIRE_MS = 10 * 60_000
#: Longer than this, a text is not shown in full, and the card gets no answer buttons: an answer cannot be chosen
#: on what was not shown (the permission cards' rule, permissions.EXACT_MAX).
TEXT_MAX = 4_000
#: The tool takes 1–4 questions (tools-reference.md); more is not a shape this card knows.
QUESTIONS_MAX = 4
OPTIONS_MAX = 8

# How a multiple choice and a free answer go into ``answers``. The docs say "join labels with commas" and say
# nothing of free text; ask-check.sh (b) and (c) measure both on a real session before these are relied on.
MULTI_SEP = ", "


def _text(value) -> str | None:
    return value if isinstance(value, str) else None


def read_questions(tool_input: dict) -> tuple[list[dict], bool]:
    """The questions verbatim (no folding, no cut beyond TEXT_MAX), and whether all of them fit on a card."""
    raw = tool_input.get("questions")
    fits = isinstance(raw, list) and 1 <= len(raw) <= QUESTIONS_MAX
    out: list[dict] = []
    for q in raw if isinstance(raw, list) else []:
        if not isinstance(q, dict) or not isinstance(q.get("question"), str) or not q["question"]:
            fits = False
            continue
        options = []
        raw_options = q.get("options") if isinstance(q.get("options"), list) else []
        if not raw_options or len(raw_options) > OPTIONS_MAX:
            fits = False
        for o in raw_options:
            if not isinstance(o, dict) or not isinstance(o.get("label"), str) or not o["label"]:
                fits = False
                continue
            option = {"label": o["label"]}
            for key in ("description", "preview"):
                if _text(o.get(key)) is not None:
                    option[key] = o[key]
            options.append(option)
        item = {"question": q["question"], "header": _text(q.get("header")) or "", "multiSelect": q.get("multiSelect") is True,
                "options": options}
        texts = [item["question"], item["header"], *(v for o in options for v in o.values())]
        if any(len(t) > TEXT_MAX for t in texts):
            fits = False
            item["question"] = item["question"][:TEXT_MAX]
            for o in options:
                for key, v in o.items():
                    o[key] = v[:TEXT_MAX]
        out.append(item)
    if len({q["question"] for q in out}) != len(out):
        fits = False   # answers are keyed by the question's text: two equal texts cannot both be answered
    return out, fits


def answer_strings(questions: list[dict], picks: dict) -> tuple[dict | None, str | None]:
    """The browser's picks -> ``answers`` (question text -> value), or an error.

    picks: question text -> {"labels": [label, …], "other": free text or ""}. Every question must be answered:
    one label or a free text for a single choice, at least one of them for a multiple choice; a label must be
    one of the question's options.
    """
    if not isinstance(picks, dict):
        return None, "answers must be an object"
    out = {}
    for q in questions:
        pick = picks.get(q["question"])
        if not isinstance(pick, dict):
            return None, f"no answer for {q['question']!r}"
        labels = pick.get("labels") or []
        other = pick.get("other") or ""
        if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels) or not isinstance(other, str):
            return None, "labels must be strings, other a string"
        known = [o["label"] for o in q["options"]]
        if any(x not in known for x in labels):
            return None, f"not an option of {q['question']!r}"
        labels = [x for x in known if x in labels]   # the options' order, each once
        other = other.strip()
        if q["multiSelect"]:
            if not labels and not other:
                return None, f"choose at least one for {q['question']!r}"
            out[q["question"]] = MULTI_SEP.join([*labels, *([other] if other else [])])
        else:
            if len(labels) + (1 if other else 0) != 1:
                return None, f"choose one for {q['question']!r}"
            out[q["question"]] = labels[0] if labels else other
    return out, None


class QuestionBook:
    def __init__(self) -> None:
        self.cards: dict[str, dict] = {}
        self._seq = itertools.count(1)
        self._by_use: dict[str, str] = {}

    def _new_id(self) -> str:
        return f"q{next(self._seq)}-{secrets.token_hex(3)}"

    def from_hook(self, sid: str, aid: str, tool_input: dict, use_id: str | None, at: int) -> dict:
        """PreToolUse of AskUserQuestion (the async forward and --ask both bring it): one card per tool use."""
        if use_id and use_id in self._by_use and self._by_use[use_id] in self.cards:
            return self.cards[self._by_use[use_id]]
        questions, fits = read_questions(tool_input)
        card = {"id": self._new_id(), "sessionId": sid, "agentId": aid, "useId": use_id, "createdAt": at,
                "status": "pending", "questions": questions, "tooLongToShow": not fits, "hookWaiting": False,
                "_input": tool_input}
        self.cards[card["id"]] = card
        if use_id:
            self._by_use[use_id] = card["id"]
        return card

    def hook_waiting(self, card: dict, future, until: int, latest: int) -> None:
        """A hook waits on the card until ``until`` (ms), which holds can move up to ``latest``."""
        card["_future"] = future
        card["hookWaiting"] = not card["tooLongToShow"]
        card["waitUntil"], card["_latest"] = until, latest

    def hold(self, card_id: str, at: int, wait_ms: int) -> str | None:
        """Someone is answering on the page: the hook waits wait_ms more (never past its latest)."""
        card = self.cards.get(card_id)
        if card is None or card["status"] != "pending" or not card.get("hookWaiting"):
            return "no hook is waiting for this question"
        card["waitUntil"] = max(card["waitUntil"], min(card["_latest"], at + wait_ms))
        return None

    def release(self, card_id: str) -> str | None:
        """ターミナルで答える: the hook stops waiting and prints nothing, so the terminal's dialog opens."""
        card = self.cards.get(card_id)
        future = card.get("_future") if card else None
        if future is None or future.done():
            return "no hook is waiting for this question"
        future.set_result({})
        card["released"] = True
        self.hook_gave_up(card)
        return None

    def hook_gave_up(self, card: dict) -> None:
        card.pop("_future", None)
        card["hookWaiting"] = False
        card.pop("waitUntil", None)

    @staticmethod
    def hook_output(card: dict, answers: dict) -> dict:
        """PreToolUse's answer: allow, and the whole input with the answers added ("allow" alone is not enough)."""
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                       "updatedInput": {**card["_input"], "answers": answers}}}

    def answer(self, card_id: str, picks: dict, at: int) -> str | None:
        card = self.cards.get(card_id)
        if card is None:
            return "unknown question"
        if card["status"] != "pending":
            return f"already {card['status']}"
        if card["tooLongToShow"]:
            return "this question is not shown in full here: answer it in the terminal"
        future = card.get("_future")
        if future is None or future.done():
            return "no hook is waiting for this question: answer it in the terminal"
        answers, error = answer_strings(card["questions"], picks)
        if error:
            return error
        card["status"], card["sentAt"], card["sentAnswers"] = "sent", at, answers
        future.set_result(self.hook_output(card, answers))
        self.hook_gave_up(card)
        return None

    def tool_finished(self, sid: str, use_id: str | None, tool_input: dict, at: int) -> dict | None:
        """PostToolUse of AskUserQuestion: the browser's answer went through, or the terminal answered first."""
        card = self.cards.get(self._by_use.get(use_id or "", ""))
        if card is None or card["sessionId"] != sid or card["status"] not in ("pending", "sent"):
            return None
        card["status"] = "answered" if card["status"] == "sent" else "answered_in_terminal"
        card["doneAt"] = at
        got = tool_input.get("answers") if isinstance(tool_input, dict) else None
        if isinstance(got, dict):
            card["gotAnswers"] = {str(k): str(v) for k, v in got.items()}
        future = card.get("_future")
        if future is not None and not future.done():
            future.set_result({})
        self.hook_gave_up(card)
        return card

    def session_stopped(self, sid: str, at: int) -> bool:
        changed = False
        for card in self.cards.values():
            if card["sessionId"] == sid and card["status"] in ("pending", "sent"):
                card["status"], card["doneAt"] = "expired", at
                future = card.get("_future")
                if future is not None and not future.done():
                    future.set_result({})
                self.hook_gave_up(card)
                changed = True
        return changed

    def tick(self, at: int) -> bool:
        changed = False
        for card in list(self.cards.values()):
            if card["status"] == "pending" and at - card["createdAt"] >= EXPIRE_MS and not card.get("_future"):
                card["status"], card["doneAt"] = "expired", at
                changed = True
            if card["status"] != "pending" and at - card.get("doneAt", at) >= EXPIRE_MS:
                self._by_use.pop(card.get("useId") or "", None)
                del self.cards[card["id"]]
                changed = True
        return changed

    def items(self) -> list[dict]:
        keep = ("id", "sessionId", "agentId", "createdAt", "status", "questions", "tooLongToShow", "hookWaiting",
                "waitUntil", "released", "sentAt", "sentAnswers", "doneAt", "gotAnswers")
        return [{k: c[k] for k in keep if k in c} for c in sorted(self.cards.values(), key=lambda c: c["createdAt"])]
