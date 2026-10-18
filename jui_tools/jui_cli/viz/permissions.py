"""Permission cards and the channel relay that answers them. Design: 08 §1–§3.

A card is born from the PermissionRequest hook (stage A: shown only). When
the session runs the jui-viz channel (stage B), Claude Code also sends the
same request over the channel with a ``request_id``; the card is linked to
it ONLY when the match is unambiguous — never by guess — and only a linked
card can be answered from the browser.

Life of a card:
  pending --browser answer--> sent --PostToolUse--> allow (browser)
     |                             \\--PermissionDenied--> deny (browser)
     |--PostToolUse / PermissionDenied first--> answered_in_terminal
     \\--Stop, SessionEnd, 10 min--> expired
"""
from __future__ import annotations

import itertools
import json
import re
import secrets

EXPIRE_MS = 10 * 60_000
LINK_WINDOW_MS = 15_000
HOOK_WAIT_MS = 2_000
CHANNEL_DEAD_MS = 60_000
PREVIEW_MAX = 2_000
#: The command / path a card shows in full. Longer than this, the browser is
#: given no buttons: a decision cannot be made on what it was not shown.
EXACT_MAX = 20_000
CONTENT_EXCERPT = 2_000
DEDUPE_MS = 3_000
SUMMARY_MAX = 160
#: Tools whose prompt is a question, not a permission (requester, 10-18: "選択肢なのに許可のボードが出る"). In the
#: VS Code extension (Claude Code 2.1.301) AskUserQuestion comes as a PermissionRequest once the --ask hook has given
#: up: an allow from the board answered nothing and read as "answered". No card, no relay: Claude Code asks as usual,
#: and the question card (questions.py) says where to answer.
NOT_PERMISSIONS = frozenset({"AskUserQuestion"})


def _clip(text, n: int) -> str:
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False) if text is not None else ""
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def exact_fields(tool_input: dict) -> tuple[dict, bool]:
    """What will run or be written, verbatim (no whitespace folding, no cut).

    The card once showed a 160-character summary when the 2,000-character JSON
    preview could not be parsed back: the tail of a 2,528-character command
    ("; rm -rf ~/…") was nowhere on it, and runs of spaces were folded, so
    'a     b' read 'a b' (independent review, 10-18). Returns the fields and
    whether all of them fit; a card that does not fit cannot be answered from
    the browser.
    """
    out: dict = {}
    fits = True
    for key in ("command", "file_path", "notebook_path", "url", "pattern", "old_string", "new_string"):
        value = tool_input.get(key)
        if isinstance(value, str):
            if len(value) > EXACT_MAX:
                fits = False
                out[key] = value[:EXACT_MAX]
            else:
                out[key] = value
    content = tool_input.get("content")
    if isinstance(content, str):
        out["content"] = content[:CONTENT_EXCERPT]
        if len(content) > CONTENT_EXCERPT:
            out["contentTruncated"] = len(content)
    return out, fits


def summary_for(tool: str, tool_input: dict) -> str:
    """What the request will do — for a command, the command itself.

    It was the description first ("run"), and the page asked for a decision
    without showing what would run (d2, 10-18). The description, written by
    the model, goes in its own field next to it.
    """
    if tool == "Bash":
        return _clip(tool_input.get("command") or tool_input.get("description") or "Bash", SUMMARY_MAX)
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if path:
        return _clip(f"{tool} {path}", SUMMARY_MAX)
    return _clip(tool, SUMMARY_MAX)


_ELIDED = re.compile(r"⋯ \d+ code points elided ⋯")


def _fold(text: str) -> str:
    return " ".join(text.split())


def preview_contains(preview: str, key: str) -> bool:
    """Is ``key`` (a command or path from the hook) in the channel's
    input_preview, as Claude Code relays it?

    Claude Code (v2.1.211+) folds every run of whitespace to one space, cuts a
    value over 3,500 code points to its start and end around
    "⋯ N code points elided ⋯", and the preview is JSON-shaped text, so quotes
    and backslashes inside a value arrive escaped. A plain substring test
    therefore missed commands with double spaces or quotes, and their cards
    could not be answered (found reading the channels reference, 10-18).
    Folded, in both spellings; a long key matches on its start and its end.
    """
    folded = _fold(preview)
    for form in (key, json.dumps(key, ensure_ascii=False)[1:-1]):
        f = _fold(form)
        if f in folded:
            return True
        if _ELIDED.search(preview) and len(f) > 400:
            head, tail = f[:200], f[-200:]
            if head in folded and tail in folded:
                return True
    return False


def _keys(tool: str, tool_input: dict) -> list[str]:
    """Strings an input_preview from the channel should contain for this card."""
    out = []
    for key in ("command", "file_path", "notebook_path", "url", "pattern"):
        v = tool_input.get(key)
        if isinstance(v, str) and v.strip():
            out.append(v.strip()[:200])
    return out


#: Prompts waiting for one channel's next poll; more is refused (the page sends one at a time, after a confirmation).
PROMPTS_QUEUED_MAX = 5


class Channel:
    def __init__(self, channel_id: str, session_id: str | None, at: int, prompts: bool = False) -> None:
        self.id = channel_id
        self.session_id = session_id
        self.last_seen = at
        self.open: dict[str, int] = {}       # request_id -> received at
        self.verdicts: list[dict] = []       # queued for the next poll
        # Does this channel.py deliver prompts typed in the page (jui-viz 1.2.0+, its hello says so)? An older one
        # ignores them, so none is ever queued for it.
        self.prompts = prompts
        self.inbox: list[dict] = []          # prompts queued for the next poll (the text lives only here)


class PermissionBook:
    def __init__(self) -> None:
        self.perms: dict[str, dict] = {}
        self.channels: dict[str, Channel] = {}
        self._seq = itertools.count(1)
        self._waiting: list[dict] = []       # channel requests that came before their hook
        self.decisions: list[dict] = []      # who answered what, for the event log

    # ---------------------------------------------------------------- helpers

    def relay_sessions(self) -> set[str]:
        return {c.session_id for c in self.channels.values() if c.session_id}

    def prompt_sessions(self) -> set[str]:
        """Sessions whose channel can deliver a prompt typed in the page."""
        return {c.session_id for c in self.channels.values() if c.session_id and c.prompts}

    def prompt_channel(self, session_id: str) -> Channel | None:
        """The one channel a prompt for this session goes to: the most recently seen that can deliver it."""
        able = [c for c in self.channels.values() if c.session_id == session_id and c.prompts]
        return max(able, key=lambda c: c.last_seen) if able else None

    def _new_id(self) -> str:
        return f"p{next(self._seq)}"

    def _card(self, sid: str, aid: str, tool: str, tool_input: dict, at: int, **extra) -> dict:
        card = {
            "id": self._new_id(), "sessionId": sid, "agentId": aid, "toolName": tool,
            "summary": summary_for(tool, tool_input),
            **({"description": _clip(tool_input["description"], SUMMARY_MAX)}
               if isinstance(tool_input.get("description"), str) and tool_input["description"].strip() else {}),
            "preview": _clip(json.dumps(tool_input, ensure_ascii=False), PREVIEW_MAX),
            "exact": exact_fields(tool_input)[0],
            "status": "pending",
            "can": {"allowDeny": False, "always": False, "reason": False},
            "createdAt": at,
        }
        card.update(extra)
        self.perms[card["id"]] = card
        return card

    # ---------------------------------------------------------------- from hooks

    def from_hook(self, sid: str, aid: str, tool: str, tool_input: dict, use_id: str | None,
                  suggestions, at: int, source: str = "forward") -> dict | None:
        if tool in NOT_PERMISSIONS:
            return None
        # The async forward and the synchronous --decide hook both report the
        # same PermissionRequest: one card for the pair. Only for the pair — a
        # second report from the SAME source is a second request (two equal
        # --decide waits were merged once, and the first was left waiting
        # 30 s; independent review, 10-18).
        for card in self.perms.values():
            if (card["status"] == "pending" and card["sessionId"] == sid and card["agentId"] == aid
                    and card["toolName"] == tool and card.get("_input") == tool_input
                    and at - card["createdAt"] <= DEDUPE_MS and source not in card["_sources"]):
                card["_sources"].add(source)
                if use_id and "_useId" not in card:
                    card["_useId"] = use_id
                if suggestions is not None and "suggestions" not in card:
                    card["suggestions"] = suggestions
                return card
        card = self._card(sid, aid, tool, tool_input, at, _input=tool_input, _sources={source})
        if use_id:
            card["_useId"] = use_id
        if suggestions is not None:
            card["suggestions"] = suggestions
        # A channel request that arrived first, waiting for this card.
        for waiting in list(self._waiting):
            if self._try_link(waiting["channel"], waiting["request"], at, only=card):
                self._waiting.remove(waiting)
                break
        return card

    def _resolve(self, card: dict, status: str, at: int, by: str | None = None) -> None:
        future = card.pop("_future", None)
        if future is not None and not future.done():
            future.set_result({})  # the terminal (or an expiry) settled it: the hook prints nothing
        card["status"] = status
        card["decidedAt"] = at
        if by:
            card["decidedBy"] = by
        channel = self.channels.get(card.get("_channel", ""))
        rid = card.get("_requestId")
        if channel is not None and rid:
            channel.open.pop(rid, None)
            channel.verdicts = [v for v in channel.verdicts if v["request_id"] != rid]

    def tool_finished(self, sid: str, use_id: str | None, allowed: bool, at: int) -> dict | None:
        """PostToolUse (allowed) or PermissionDenied (not): settle the card it belongs to."""
        if not use_id:
            return None
        for card in self.perms.values():
            if card["sessionId"] == sid and card.get("_useId") == use_id and card["status"] in ("pending", "sent"):
                if card["status"] == "sent":
                    sent = card.get("sentBehavior")
                    self._resolve(card, "allow" if allowed else "deny", at, by="browser")
                    if (sent == "allow") != allowed:
                        card["decidedBy"] = "terminal"  # the terminal answered first, the other way
                else:
                    self._resolve(card, "answered_in_terminal", at, by="terminal")
                    card["terminalBehavior"] = "allow" if allowed else "deny"
                return card
        return None

    def session_stopped(self, sid: str, at: int) -> None:
        for card in self.perms.values():
            if card["sessionId"] == sid and card["status"] in ("pending", "sent"):
                # A refusal sends no PostToolUse and no PermissionDenied (live
                # check, 10-18), so a sent deny has nothing to settle it but
                # this Stop. Had the terminal allowed first, PostToolUse would
                # have settled the card before the turn ended.
                if card["status"] == "sent" and card.get("sentBehavior") == "deny":
                    self._resolve(card, "deny", at, by="browser")
                else:
                    self._resolve(card, "expired", at)

    def link_use_id(self, card: dict, use_id: str) -> None:
        card["_useId"] = use_id

    # ---------------------------------------------------------------- channel side

    def hello(self, session_id: str | None, at: int, prompts: bool = False) -> Channel:
        channel = Channel(secrets.token_urlsafe(12), session_id, at, prompts)
        self.channels[channel.id] = channel
        return channel

    def channel_request(self, channel_id: str, request: dict, at: int) -> bool:
        channel = self.channels.get(channel_id)
        if channel is None:
            return False
        rid = request.get("request_id")
        if not isinstance(rid, str) or not rid:
            return False
        channel.last_seen = at
        if request.get("tool_name") in NOT_PERMISSIONS:
            return True   # taken and never answered: no card, not even the relay-only one tick() would make
        channel.open[rid] = at
        if not self._try_link(channel, request, at):
            self._waiting.append({"channel": channel, "request": request, "at": at})
        return True

    def _try_link(self, channel: Channel, request: dict, at: int, only: dict | None = None) -> bool:
        tool = request.get("tool_name")
        preview = str(request.get("input_preview") or "")
        candidates = [
            c for c in ([only] if only else self.perms.values())
            if c["sessionId"] == channel.session_id and c["toolName"] == tool and c["status"] == "pending"
            and "_requestId" not in c and at - c["createdAt"] <= LINK_WINDOW_MS
        ]
        # Every candidate must agree with the preview, even a lone one: a lone
        # "ls" card once linked to an "rm -rf x" request and the browser's
        # allow for "ls" went to rm (independent review, 10-18). A card with
        # nothing to compare is not linked; it stays answerable in the terminal.
        candidates = [c for c in candidates if _keys(c["toolName"], c.get("_input", {}))
                      and all(preview_contains(preview, k) for k in _keys(c["toolName"], c.get("_input", {})))]
        if len(candidates) != 1:
            return False  # none, or still more than one: do not guess
        card = candidates[0]
        card["_requestId"] = request["request_id"]
        card["_channel"] = channel.id
        card["can"]["allowDeny"] = self._showable(card)
        return True

    # ---------------------------------------------------------------- the synchronous hook (P6)

    @staticmethod
    def _showable(card: dict) -> bool:
        """Can the page show everything the decision is about? (exact_fields fits)"""
        return "_input" not in card or exact_fields(card["_input"])[1]

    def hook_waiting(self, card: dict, future) -> None:
        """A --decide hook is waiting on this card: it can take allow / deny,
        "from now on" (only the request's own suggestions) and a reason —
        unless the card cannot show the whole command / path."""
        card["_future"] = future
        ok = self._showable(card)
        card["can"] = {"allowDeny": ok, "always": ok and bool(card.get("suggestions")), "reason": ok}
        if not ok:
            card["tooLongToShow"] = True

    def hook_gave_up(self, card: dict) -> None:
        card.pop("_future", None)
        linked = card.get("_requestId") and card.get("_channel") in self.channels
        card["can"] = {"allowDeny": bool(linked), "always": False, "reason": False}

    @staticmethod
    def hook_output(behavior: str, rules: list | None, reason: str | None) -> dict:
        decision: dict = {"behavior": behavior}
        if behavior == "allow" and rules:
            decision["updatedPermissions"] = rules
        if behavior == "deny" and reason:
            decision["message"] = reason
        return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}

    def decide(self, perm_id: str, behavior: str, at: int, always=None, reason=None) -> str | None:
        """Browser answer. Returns None when sent, or why it was refused.

        Through the waiting --decide hook when there is one (it carries
        "from now on" and a reason), else through the channel relay.
        """
        card = self.perms.get(perm_id)
        if card is None:
            return "unknown permission"
        if behavior not in ("allow", "deny"):
            return "behavior must be allow or deny"
        if card["status"] != "pending":
            return f"already {card['status']}"
        if not self._showable(card):
            return "the command is too long to show in full: answer in the terminal"
        future = card.get("_future")
        if future is not None and not future.done():
            rules = None
            if always:
                suggestions = card.get("suggestions") if isinstance(card.get("suggestions"), list) else []
                if behavior != "allow" or not suggestions:
                    return "from now on needs allow and this request's suggestions"
                if always is True:
                    rules = list(suggestions)
                elif isinstance(always, list) and all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(suggestions) for i in always) and always:
                    rules = [suggestions[i] for i in sorted(set(always))]
                else:
                    return "always must be true or a list of suggestion indexes"
            if reason is not None and (not isinstance(reason, str) or behavior != "deny"):
                return "a reason goes with deny, as text"
            text = reason.strip()[:1000] if isinstance(reason, str) and reason.strip() else None
            future.set_result(self.hook_output(behavior, rules, text))
            card.pop("_future", None)
            card["status"] = "sent"
            card["sentBehavior"] = behavior
            card["sentBy"] = "hook"
            if rules:
                card["sentRules"] = rules
            if text:
                card["sentReason"] = text
            self.decisions.append({"permId": perm_id, "behavior": behavior, "at": at, "sessionId": card["sessionId"],
                                   "always": bool(rules), "reason": bool(text)})
            return None
        if always or reason:
            return "from now on and reasons need the waiting hook, which this request does not have"
        channel = self.channels.get(card.get("_channel", ""))
        rid = card.get("_requestId")
        if channel is None or not rid or rid not in channel.open:
            return "this session has no relay for this request"
        channel.verdicts.append({"request_id": rid, "behavior": behavior})
        card["status"] = "sent"
        card["sentBehavior"] = behavior
        card["sentBy"] = "relay"
        self.decisions.append({"permId": perm_id, "behavior": behavior, "at": at, "sessionId": card["sessionId"]})
        return None

    def take_prompts(self, channel_id: str) -> list[dict]:
        """The prompts queued for this channel, handed over once (the server keeps no copy)."""
        channel = self.channels.get(channel_id)
        if channel is None:
            return []
        out, channel.inbox = channel.inbox, []
        return out

    def take_verdicts(self, channel_id: str, at: int) -> list[dict] | None:
        channel = self.channels.get(channel_id)
        if channel is None:
            return None
        channel.last_seen = at
        out, channel.verdicts = channel.verdicts, []
        return out

    # ---------------------------------------------------------------- time

    def tick(self, at: int) -> bool:
        """Expire, give up waiting, drop dead channels. True when something changed."""
        changed = False
        for waiting in list(self._waiting):
            if at - waiting["at"] >= HOOK_WAIT_MS:
                self._waiting.remove(waiting)
                req, channel = waiting["request"], waiting["channel"]
                if req["request_id"] in channel.open:
                    self._card(channel.session_id or "?", channel.session_id or "?", str(req.get("tool_name") or "?"), {}, at,
                               summary=_clip(req.get("description") or req.get("tool_name") or "", SUMMARY_MAX),
                               preview=_clip(req.get("input_preview") or "", PREVIEW_MAX),
                               _requestId=req["request_id"], _channel=channel.id, relayOnly=True,
                               can={"allowDeny": True, "always": False, "reason": False})
                    changed = True
        for card in self.perms.values():
            if card["status"] in ("pending", "sent") and at - card["createdAt"] >= EXPIRE_MS:
                self._resolve(card, "expired", at)
                changed = True
        for cid, channel in list(self.channels.items()):
            if at - channel.last_seen >= CHANNEL_DEAD_MS:
                del self.channels[cid]
                for card in self.perms.values():
                    if card.get("_channel") == cid and card["status"] == "pending":
                        card["can"]["allowDeny"] = False
                changed = True
        for pid in [p for p, c in self.perms.items() if c["status"] not in ("pending", "sent") and at - c.get("decidedAt", at) >= EXPIRE_MS]:
            del self.perms[pid]
            changed = True
        return changed

    def items(self) -> list[dict]:
        """The perms slice: private fields (leading underscore) stay on the server."""
        out = []
        for card in sorted(self.perms.values(), key=lambda c: c["createdAt"]):
            item = {k: v for k, v in card.items() if not k.startswith("_")}
            item["can"] = dict(card["can"])
            out.append(item)
        return out
