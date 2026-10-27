"""The models of the local servers Codex runs open models on (requester 10-27: 「モデル自由に選べるようにしたい」): LM Studio
and Ollama, the two `codex --oss --local-provider` knows. Read for the call dialog's Codex tab only, when the page asks
(POST /api/local-models) — never polled, never sent anywhere but 127.0.0.1.

Each server's OpenAI-compatible ``GET /v1/models`` ({"data": [{"id": …}, …]}) on its default port, the one Codex's
--oss uses for it (LM Studio 1234, Ollama 11434). A raw http.client connection: the HTTP(S)_PROXY of the environment
must never route 127.0.0.1. A server that does not answer is listed with ``ok: false``; a model id is kept only when it
is one printable line of at most MODEL_MAX characters (it goes into a command line, quoted by callcmd).
"""
from __future__ import annotations

import http.client
import json

#: (Codex's --local-provider id, the name shown, its default port)
PROVIDERS = (("lmstudio", "LM Studio", 1234), ("ollama", "Ollama", 11434))
PROVIDER_IDS = frozenset(p[0] for p in PROVIDERS)
MODEL_MAX = 200
MODELS_MAX = 200
BODY_MAX = 1_048_576
TIMEOUT_SEC = 1.5


def model_ok(model) -> bool:
    return (isinstance(model, str) and 0 < len(model) <= MODEL_MAX and model == model.strip()
            and not any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in model))


def parse(body: bytes) -> list[str] | None:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    out: list[str] = []
    for row in rows:
        model = row.get("id") if isinstance(row, dict) else None
        if model_ok(model) and model not in out:
            out.append(model)
        if len(out) >= MODELS_MAX:
            break
    return out


def fetch(port: int, timeout: float = TIMEOUT_SEC) -> list[str] | None:
    """The model ids one local server lists, or None when it does not answer as an OpenAI-compatible server."""
    conn = http.client.HTTPConnection("127.0.0.1", int(port), timeout=timeout)
    try:
        conn.request("GET", "/v1/models", headers={"Accept": "application/json"})
        res = conn.getresponse()
        if res.status != 200:
            return None
        return parse(res.read(BODY_MAX + 1)[:BODY_MAX])
    except (OSError, http.client.HTTPException, ValueError):
        return None
    finally:
        conn.close()


def listing(fetcher=fetch) -> list[dict]:
    """[{id, name, port, ok, models}] for each provider, in PROVIDERS' order. Blocking: run it off the event loop."""
    out = []
    for pid, name, port in PROVIDERS:
        models = fetcher(port)
        out.append({"id": pid, "name": name, "port": port, "ok": models is not None, "models": models or []})
    return out
