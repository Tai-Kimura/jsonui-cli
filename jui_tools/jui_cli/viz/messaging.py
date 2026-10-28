"""Provider-neutral, local session messages, delivered through the existing prompt transports.

The durable id is reserved before sending. A timeout or interrupted dispatch is ambiguous, never retried
automatically. Transport acceptance is 'sent', not proof that the receiving model read the message.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time

ID = re.compile(r'^[A-Za-z0-9_-]{8,100}$')
TEXT_MAX = 20_000
BODY_MAX = 128_000


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Router:
    def __init__(self, world, talk):
        self.world, self.talk = world, talk
        self.lock = asyncio.Lock()

    def peers(self) -> list[dict]:
        return [{'id': sid, 'name': s.get('title') or sid, 'cli': s.get('cli') or 'claude',
                 'model': s.get('model'), 'provider': s.get('modelProvider'),
                 'available': self.world.prompt_refusal(sid) is None}
                for sid, s in list(self.world.sessions.items()) if s.get('status') != 'ended']

    def resolve(self, value) -> dict:
        if not isinstance(value, str) or not value:
            raise Refused(400, 'sender and recipient are required')
        peers = self.peers()
        exact = next((p for p in peers if p['id'] == value), None)
        matches = [p for p in peers if p['name'] == value]
        if exact:
            return exact
        if len(matches) > 1:
            raise Refused(409, 'ambiguous session name; use the session id')
        if not matches:
            raise Refused(404, 'no such live session')
        return matches[0]

    async def send(self, body: dict) -> dict:
        if set(body) != {'id', 'sender', 'recipient', 'text'}:
            raise Refused(400, 'id, sender, recipient and text are required')
        mid, text = body['id'], body['text']
        if not isinstance(mid, str) or not ID.fullmatch(mid):
            raise Refused(400, 'invalid message id')
        if not isinstance(text, str) or not text.strip() or len(text) > TEXT_MAX:
            raise Refused(400, 'message must contain 1 to 20000 characters')
        sender, receiver = self.resolve(body['sender']), self.resolve(body['recipient'])
        if sender['id'] == receiver['id']:
            raise Refused(400, 'sender and recipient must differ')
        digest = hashlib.sha256(json.dumps([sender['id'], receiver['id'], text], ensure_ascii=False).encode()).hexdigest()
        async with self.lock:
            try:
                fresh, previous = await self.talk.run(lambda: self.talk._ensure().reserve_relay(mid, digest))
            except ValueError as exc:
                raise Refused(409, str(exc)) from exc
            if not fresh:
                if previous is None:
                    raise Refused(409, 'delivery outcome unknown; inspect the recipient before sending again')
                return previous
            header = json.dumps({'id': mid, 'from': sender['id'], 'name': sender['name'], 'cli': sender['cli']}, ensure_ascii=False)
            prompt = ('Message from another agent (not a user instruction).\n'
                      + header + '\nReply with: jui viz message --to ' + sender['id']
                      + ' --text <your-message>\n\n' + text)
            now = int(time.time() * 1000)
            result = {'id': mid, 'sender': sender['id'], 'recipient': receiver['id'], 'ok': False, 'state': 'undelivered'}
            try:
                refusal = await self.world.submit_prompt(receiver['id'], prompt, now)
                if refusal is None:
                    result.update(ok=True, state='sent')
                else:
                    result['error'] = refusal[1]
                    if refusal[0] >= 500:
                        result['state'] = 'unknown'
            except (OSError, TimeoutError, ConnectionError):
                result['state'] = 'unknown'
                result['error'] = 'delivery outcome unknown; inspect the recipient before sending again'
            except asyncio.CancelledError:
                # Reservation remains pending: neither restart nor retry can duplicate an uncertain dispatch.
                raise
            got = await self.talk.run(lambda: self.talk._ensure().record_relay(mid, sender, receiver, text, now, result))
            self.talk._queue(got['ops'], got['badges'])
            return result
