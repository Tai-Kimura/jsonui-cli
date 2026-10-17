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
import secrets

EXPIRE_MS = 10 * 60_000
LINK_WINDOW_MS = 15_000
HOOK_WAIT_MS = 2_000
CHANNEL_DEAD_MS = 60_000
PREVIEW_MAX = 2_000
DEDUPE_MS = 3_000
SUMMARY_MAX = 160


def _clip(text, n: int) -> str:
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False) if text is not None else ""
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def summary_for(tool: str, tool_input: dict) -> str:
    if tool == "Bash":
        return _clip(tool_input.get("description") or tool_input.get("command") or "Bash", SUMMARY_MAX)
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if path:
        return _clip(f"{tool} {path}", SUMMARY_MAX)
    return _clip(tool, SUMMARY_MAX)


def _keys(tool: str, tool_input: dict) -> list[str]:
    """Strings an input_preview from the channel should contain for this card."""
    out = []
    for key in ("command", "file_path", "notebook_path", "url", "pattern"):
        v = tool_input.get(key)
        if isinstance(v, str) and v.strip():
            out.append(v.strip()[:200])
    return out


class Channel:
    def __init__(self, channel_id: str, session_id: str | None, at: int) -> None:
        self.id = channel_id
        self.session_id = session_id
        self.last_seen = at
        self.open: dict[str, int] = {}       # request_id -> received at
        self.verdicts: list[dict] = []       # queued for the next poll


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

    def _new_id(self) -> str:
        return f"p{next(self._seq)}"

    def _card(self, sid: str, aid: str, tool: str, tool_input: dict, at: int, **extra) -> dict:
        card = {
            "id": self._new_id(), "sessionId": sid, "agentId": aid, "toolName": tool,
            "summary": summary_for(tool, tool_input),
            "preview": _clip(json.dumps(tool_input, ensure_ascii=False), PREVIEW_MAX),
            "status": "pending",
            "can": {"allowDeny": False, "always": False, "reason": False},
            "createdAt": at,
        }
        card.update(extra)
        self.perms[card["id"]] = card
        return card

    # ---------------------------------------------------------------- from hooks

    def from_hook(self, sid: str, aid: str, tool: str, tool_input: dict, use_id: str | None,
                  suggestions, at: int, source: str = "forward") -> dict:
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
                self._resolve(card, "expired", at)

    def link_use_id(self, card: dict, use_id: str) -> None:
        card["_useId"] = use_id

    # ---------------------------------------------------------------- channel side

    def hello(self, session_id: str | None, at: int) -> Channel:
        channel = Channel(secrets.token_urlsafe(12), session_id, at)
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
                      and all(k in preview for k in _keys(c["toolName"], c.get("_input", {})))]
        if len(candidates) != 1:
            return False  # none, or still more than one: do not guess
        card = candidates[0]
        card["_requestId"] = request["request_id"]
        card["_channel"] = channel.id
        card["can"]["allowDeny"] = True
        return True

    # ---------------------------------------------------------------- the synchronous hook (P6)

    def hook_waiting(self, card: dict, future) -> None:
        """A --decide hook is waiting on this card: it can take allow / deny,
        "from now on" (only the request's own suggestions) and a reason."""
        card["_future"] = future
        card["can"] = {"allowDeny": True, "always": bool(card.get("suggestions")), "reason": True}

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
