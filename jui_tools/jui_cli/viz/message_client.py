"""Local client for agents of any provider. Never uses proxy environment variables or follows redirects."""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import uuid

from .channel import read_server, session_id_of


def own_session(chain: list | None = None) -> str | None:
    """This session's id: the environment's, else ~/.claude/sessions' entry of a process up the chain. ``chain``
    collects the pids walked (for whoami, when no entry names any of them)."""
    for key in ('CODEX_THREAD_ID', 'CLAUDE_SESSION_ID'):
        value = os.environ.get(key)
        if value:
            return value
    pid = os.getppid()
    for _ in range(12):
        if chain is not None:
            chain.append(pid)
        sid = session_id_of(pid)
        if sid:
            return sid
        try:
            got = subprocess.run(['ps', '-o', 'ppid=', '-p', str(pid)], capture_output=True, text=True, timeout=2)
            parent = int(got.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            break
        if parent <= 1 or parent == pid:
            break
        pid = parent
    return None


def request(path: str, body: dict) -> dict:
    info = read_server()
    if not info or not isinstance(info.get('token'), str) or not 0 < info['port'] < 65536:
        raise ValueError('jui viz is not running')
    origin = f"http://127.0.0.1:{info['port']}"
    conn = http.client.HTTPConnection('127.0.0.1', info['port'], timeout=40)
    try:
        conn.request('POST', '/api/messages/' + path, json.dumps(body, ensure_ascii=False).encode(),
                     {'Content-Type': 'application/json', 'Origin': origin, 'X-Jui-Viz-Token': info['token']})
        response = conn.getresponse()
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError('message server response is too large')
        if response.status != 200:
            raise ValueError(f'{response.status}: ' + raw.decode('utf-8', 'replace').strip())
        return json.loads(raw)
    finally:
        conn.close()


def server_session(chain: list) -> str | None:
    """No ~/.claude/sessions entry names this session (the ENOSPC night lost entries): the server is asked which
    session these processes are, as its hooks named their claude pid. None when it knows none of them, or is older
    than the question (404 either way), so the answer is as it was."""
    if not chain:
        return None
    try:
        sid = request('whoami', {'pids': chain[:32]}).get('sessionId')
    except (OSError, ValueError, http.client.HTTPException):
        return None
    return sid if isinstance(sid, str) and sid else None


def command(args) -> int:
    import sys
    message_id = None
    try:
        if args.viz_cmd == 'peers':
            result = request('peers', {})
        else:
            chain: list = []
            sender = args.sender or own_session(chain) or server_session(chain)
            if not sender:
                raise ValueError('cannot identify this session; use --from <session-id>')
            message_id = args.message_id or str(uuid.uuid4())
            result = request('send', {'id': message_id, 'sender': sender,
                                      'recipient': args.recipient, 'text': args.text})
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('ok', True) else 1
    except (OSError, ValueError, http.client.HTTPException) as exc:
        print('jui viz message: ' + str(exc), file=sys.stderr)
        if message_id:
            print('message id: ' + message_id + ' (reuse --id to check this same request)', file=sys.stderr)
        return 1
