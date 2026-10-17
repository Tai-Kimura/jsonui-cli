"""Scenario files for fake_server.py: what the server would send, line by line (JSON lines).

Each line is one of
    {"t": 1.5, "msg": {"type": "slices", "changed": {"sessions": [...]}}}   a message (rev is filled in)
    {"t": 1.5, "msg": {"type": "events", "items": [...]}}
    {"t": 2.0, "msg": {"type": "notice", "level": "warn", "text": "..."}}
    {"mark": "name"}                                                     a point the tests can jump to
    {"sheets": {"<specId>": {...cards}}}                                 what spec.sheet answers (plan 09 §6)

`t` (seconds from the start) is used only by --autoplay; the tests step with POST /_fake/step?to=<mark>,
which sends everything before that mark and then the block it starts.
The scenario keeps the slices it has sent, so a browser that connects (or reconnects) gets the same snapshot the
real server would give, plus the last events.
"""

from __future__ import annotations

import asyncio
import copy
import json
import pathlib

EVENT_BACKLOG = 200


class Scenario:
    def __init__(self, items: list[dict]):
        self.items = items
        self.position = 0
        self.rev = 0
        self.slices: dict[str, list] = {}
        self.events: list[dict] = []
        self.sheets: dict[str, dict] = {}
        for item in items:
            self.sheets.update(item.get("sheets", {}))
        self.items = [i for i in items if "sheets" not in i]

    @classmethod
    def load(cls, path: pathlib.Path) -> "Scenario":
        items = []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                items.append(json.loads(line))
            except ValueError as e:
                raise ValueError(f"{path}:{n}: {e}") from None
        return cls(items)

    def state(self):
        return self.rev, copy.deepcopy(self.slices)

    def backlog(self):
        return [{"type": "events", "items": self.events[-EVENT_BACKLOG:]}] if self.events else []

    def _apply(self, msg: dict) -> dict:
        msg = copy.deepcopy(msg)
        if msg.get("type") == "slices":
            self.rev += 1
            msg["rev"] = self.rev
            for k, v in msg.get("changed", {}).items():
                self.slices[k] = v
        elif msg.get("type") == "events":
            self.events.extend(msg.get("items", []))
        elif msg.get("type") == "snapshot":
            self.rev += 1
            msg["rev"] = self.rev
            self.slices = copy.deepcopy(msg.get("slices", {}))
        return msg

    async def advance(self, send, to: str | None = None, n: int = 0) -> int:
        """``to``: send everything up to the mark ``to``, then the block that follows it (up to the next mark), so
        a mark names what it starts. ``n``: send the next ``n`` messages. Returns how many were sent."""
        sent = 0
        if to is not None:
            found = False
            while self.position < len(self.items):
                item = self.items[self.position]
                self.position += 1
                if "mark" in item:
                    if found:
                        self.position -= 1   # the next block stays for the next step
                        break
                    found = item["mark"] == to
                    continue
                await send(self._apply(item["msg"]))
                sent += 1
            return sent
        while self.position < len(self.items) and (not n or sent < n):
            item = self.items[self.position]
            self.position += 1
            if "mark" in item:
                continue
            await send(self._apply(item["msg"]))
            sent += 1
        return sent

    def decide(self, perm_id: str, behavior: str, always=None, reason=None):
        """perm.decide as the P5/P6 server answers it (permissions.py decide): a pending perm becomes 'sent'.
        "from now on" (always: true or suggestion indexes) needs allow and the waiting hook (can.always);
        a reason needs deny and the hook (can.reason). Returns (slices message, None) or (None, error)."""
        perms = self.slices.get("perms") or []
        for p in perms:
            if p.get("id") != perm_id:
                continue
            if p.get("status") != "pending":
                return None, f"already {p.get('status')}"
            can, sugg = p.get("can") or {}, p.get("suggestions") or []
            rules = None
            if always:
                if behavior != "allow" or not can.get("always") or not sugg:
                    return None, "from now on needs allow and this request's suggestions"
                if always is True:
                    rules = list(sugg)
                elif isinstance(always, list) and always and all(isinstance(i, int) and 0 <= i < len(sugg) for i in always):
                    rules = [sugg[i] for i in sorted(set(always))]
                else:
                    return None, "always must be true or a list of suggestion indexes"
            if reason is not None and (behavior != "deny" or not can.get("reason")):
                return None, "a reason goes with deny, as text"
            p.update(status="sent", sentBehavior=behavior, sentBy="hook" if can.get("reason") else "relay")
            if rules:
                p["sentRules"] = rules
            if reason:
                p["sentReason"] = reason
            return self._apply({"type": "slices", "changed": {"perms": perms}}), None
        return None, "unknown permission"

    async def play(self, send):
        """Send every item at its `t` (seconds from now)."""
        loop = asyncio.get_running_loop()
        start = loop.time()
        while self.position < len(self.items):
            item = self.items[self.position]
            if "mark" in item:
                self.position += 1
                continue
            delay = start + float(item.get("t", 0)) - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            self.position += 1
            await send(self._apply(item["msg"]))
