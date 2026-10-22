"""Tool calls stopped by auto mode, shown on the board so the person can tell the session to go on (ticket
2026-10-20-jui-viz-auto-mode-denial-approve-from-page; requester: 「このケースの時に許可できる仕組み実装できない？」).

A denial reaches viz two ways, both kept to one card by the session and the tool_use_id:

  * the PermissionDenied hook (hooks reference: it fires only when auto mode denies a tool call; tool_name,
    tool_input, tool_use_id and reason), forwarded by the jui-viz plugin like every hook;
  * the session's transcript: the tool_result of that call, is_error, whose text starts with DENIED_PREFIX
    (sources/transcripts.denial_of), for a session whose hook did not come.

The card offers 「実行してよいと伝える」: after a confirmation on the page, the server sends prompt_text(card) to that
session as a prompt from the page (World.send_prompt, the path of POST /api/prompt). That is all viz does — the same
words the person would type. It never writes a permission rule or a setting, never answers the hook (no retry), and
whether the next try passes stays with Claude Code's own check. 「そのまま」 closes the card and sends nothing.
"""
from __future__ import annotations

import re

from . import i18n

#: The tool_result text of an auto mode denial, as seen in this machine's transcripts of 10-19 and 10-20 (11 records;
#: not documented; the dependency is in cc_watch's ledger, probe auto_mode_denial): "Permission for this action was
#: denied by the Claude Code auto mode classifier. Reason: <reason>. If you have other tasks ...". The reason was a
#: rule in square brackets ("[Merge Without Review]") or a sentence ("The server-side auto mode classifier judged this
#: action dangerous (it gave no explanation)"). Another form seen, "The server-side auto mode classifier gave no
#: verdict (error), ...", is a transient failure that says the action may be tried again: not a denial, no card.
DENIED_PREFIX = "Permission for this action was denied by the Claude Code auto mode classifier."
_RULE = re.compile(r"Reason: (\[[^\]\n]{1,120}\])")
_SENTENCE = re.compile(r"Reason: (.{1,200}?)(?:\. If you have other tasks|\.?\n|\.?$)", re.S)

INPUT_HEAD = 200
REASON_MAX = 160
CARDS_MAX = 50
#: how long a card that was answered (sent / dismissed) or whose session ended stays on the page; a sent card stays
#: until the receiver's next response shows under it and DONE_SHOW_MS more, and at most SENT_WAIT_MS
DONE_SHOW_MS = 60_000
SENT_WAIT_MS = 600_000
REPLY_HEAD = 300
#: the hook and the transcript of one call, when one of them has no tool_use_id: this close in time
SAME_CALL_MS = 30_000


def reason_of(text: str) -> str:
    """What follows "Reason: ": the rule in square brackets, or the sentence up to the text that comes after it; ''."""
    m = _RULE.search(text or "") or _SENTENCE.search(text or "")
    return " ".join(m.group(1).split())[:REASON_MAX] if m else ""


def input_head(tool: str, tool_input) -> str:
    """What the call would have done, short: a command, a path, a URL, else the input's first values."""
    if not isinstance(tool_input, dict):
        return ""
    for key in ("command", "file_path", "notebook_path", "url", "pattern", "query"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return _clip(value)
    parts = [f"{k}={v}" for k, v in tool_input.items() if isinstance(v, (str, int, float)) and not isinstance(v, bool)]
    return _clip(", ".join(parts))


def _clip(text: str, n: int = INPUT_HEAD) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


#: the first line of the words: where they come from, said as it is (never that the sender was verified)
def source_line() -> str:
    return i18n.tl("srv.denial.source")


def prompt_text(card: dict) -> str:
    """The words 「実行してよいと伝える」 sends (the orchestrator's ruling 10-20 15:30: the receiver may answer in the terminal, and
    that is right — its care with a channel's words is not to be talked around). Where they come from; the call that
    was stopped and the reason, each taken from the card as it is; the person's judgement; and the way left open to
    ask for a confirmation in the terminal. What viz claims is that the person's judgement reaches the receiver
    unmistaken, not that the receiver goes on."""
    what = f"{card['tool']}: {card['input']}" if card["input"] else card["tool"]
    why = card["reason"] or i18n.tl("srv.denial.no_reason")
    return "\n".join([
        source_line(),
        i18n.tl("srv.denial.what", what=what),
        i18n.tl("srv.denial.why", why=why),
        i18n.tl("srv.denial.judged"),
        i18n.tl("srv.denial.again"),
    ])


class DenialBook:
    def __init__(self) -> None:
        self.cards: dict[str, dict] = {}
        self._seq = 0

    @staticmethod
    def key(sid: str, use_id: str | None, tool: str, head: str, at: int) -> str:
        return f"{sid}|{use_id}" if use_id else f"{sid}|{tool}|{head}|{at // 1000}"

    def add(self, sid: str, agent_id: str, use_id: str | None, tool: str, tool_input, reason: str, at: int, via: str) -> bool:
        """One denial. The same call again (the hook and the transcript, or either twice) only notes how it came.
        Returns whether the page has something new."""
        head = input_head(tool, tool_input) if not isinstance(tool_input, str) else _clip(tool_input)
        key = self.key(sid, use_id, tool, head, at)
        card = self.cards.get(key) or self._same_call(sid, use_id, tool, head, at)
        if card is not None:
            if use_id and not card["toolUseId"]:
                card["toolUseId"] = use_id
            changed = via not in card["via"]
            if changed:
                card["via"].append(via)
            if not card["reason"] and reason:
                card["reason"], changed = reason[:REASON_MAX], True
            if not card["input"] and head:
                card["input"], changed = head, True
            return changed
        self._seq += 1
        self.cards[key] = {"id": f"d{self._seq}", "key": key, "sessionId": sid, "agentId": agent_id, "toolUseId": use_id,
                           "tool": tool or "?", "input": head, "reason": (reason or "")[:REASON_MAX], "at": at,
                           "status": "pending", "via": [via], "doneAt": None, "reply": None, "replyAt": None}
        while len(self.cards) > CARDS_MAX:
            oldest = min(self.cards.values(), key=lambda c: (c["status"] == "pending", c["at"]))
            del self.cards[oldest["key"]]
        return True

    def _same_call(self, sid: str, use_id: str | None, tool: str, head: str, at: int) -> dict | None:
        """The card of the same call from the other source when one of the two has no tool_use_id: the same session,
        tool and input, within SAME_CALL_MS. Measured 10-20 13:12: the hook came 0.04 s after the transcript's record
        with the same tool_input; whether its payload carries tool_use_id was not seen (the event log keeps neither
        it nor the reason), so the two are matched without it too."""
        for card in self.cards.values():
            if card["sessionId"] != sid or card["tool"] != (tool or "?") or card["input"] != head:
                continue
            if use_id and card["toolUseId"] and card["toolUseId"] != use_id:
                continue
            if abs(card["at"] - at) <= SAME_CALL_MS:
                return card
        return None

    def find(self, card_id: str) -> dict | None:
        return next((c for c in self.cards.values() if c["id"] == card_id), None)

    def settle(self, card_id: str, status: str, at: int) -> dict | None:
        """sent / dismissed: only a pending card changes. Returns the card, or None."""
        card = self.find(card_id)
        if card is None or card["status"] != "pending":
            return None
        card["status"], card["doneAt"] = status, at
        return card

    def session_ended(self, sid: str, at: int) -> bool:
        changed = False
        for card in self.cards.values():
            if card["sessionId"] == sid and card["status"] == "pending":
                card["status"], card["doneAt"], changed = "ended", at, True
        return changed

    def reply(self, sid: str, replies, at: int) -> bool:
        """The receiver's next response after the words were sent (sources/transcripts: its assistant texts with their
        times): its head goes under each sent card of that session that has none yet."""
        changed = False
        for card in self.cards.values():
            if card["sessionId"] != sid or card["status"] != "sent" or card.get("reply") is not None:
                continue
            nxt = next(((when, text) for when, text in replies or [] if when is not None and when >= card["doneAt"] and text.strip()), None)
            if nxt:
                head = " ".join(nxt[1].split())
                card["reply"] = head if len(head) <= REPLY_HEAD else head[: REPLY_HEAD - 1] + "…"
                card["replyAt"] = at
                changed = True
        return changed

    def _gone(self, c: dict, at: int) -> bool:
        if c["status"] == "pending":
            return False
        if c["status"] == "sent" and c.get("reply") is None:
            return at - (c["doneAt"] or at) >= SENT_WAIT_MS
        return at - (c.get("replyAt") or c["doneAt"] or at) >= DONE_SHOW_MS

    def tick(self, at: int) -> bool:
        gone = [k for k, c in self.cards.items() if self._gone(c, at)]
        for k in gone:
            del self.cards[k]
        return bool(gone)

    def items(self) -> list[dict]:
        """The slice: each card with the exact words its button would send."""
        out = []
        # Oldest first, by the second: the transcript's records are timed to the second and the hook to the millisecond,
        # so within one second the cards keep the order they were made in (ticket 2026-10-23-viz-denial-cards-order-flips-within-a-second)
        for c in sorted(self.cards.values(), key=lambda c: (c["at"] // 1000, int(c["id"][1:]))):
            row = {k: v for k, v in c.items() if k != "key"}
            row["via"] = list(c["via"])
            row["prompt"] = prompt_text(c)
            out.append(row)
        return out
