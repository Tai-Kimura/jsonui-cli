"""The estimated cost (USD) of one response, for the bill over its robot (ticket 2026-10-19-jui-viz-cost-bill-over-robot).

Two tables: the one shipped with viz (prices.json next to this file: the official pricing page's values, its URL and
the day they were checked) and the user's own (<viz home>/prices.json), which changes a model's prices, adds a model,
or takes one out (``null``). The user's table is read again when it changes (its mtime, size and inode), with no
restart, off the event loop (PriceBook.poll); a row that is not usable is left out on its own, with the reason, and
the rest still apply. `jui viz prices` and the page's 単価 sheet (POST /api/prices) write it through ``apply_op``.

What a response costs (``cost``): its four kinds of tokens from message.usage, each at the model's price — input,
cache writes (5-minute and 1-hour, from usage.cache_creation), cache reads, output (thinking is part of it). A model
not in the table, or a response whose price the table cannot say (a cache write with no 5m / 1h split, a speed or an
inference_geo the row has no price for), costs None: the page shows ? and the tokens, never an amount made up.
It is an estimate: on a subscription the bill is not per token at all, and server tools (web search) are left out.
"""
from __future__ import annotations

import json
import math
import os
import re
import stat
import time
from pathlib import Path

from . import paths

DEFAULT_PATH = Path(__file__).with_name("prices.json")
USER_MAX = 262_144
MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/\[\]-]{0,99}")
KINDS = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")
PRICE_MAX = 100_000.0     # USD per million tokens: anything above is a typo, not a price
CHECK_EVERY_S = 0.5


def user_path() -> Path:
    return paths.viz_home() / "prices.json"


def _price(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= PRICE_MAX


def check_row(row) -> str | None:
    """Why a row of the user's table cannot be used, or None. The five prices are required; nothing else is read."""
    if not isinstance(row, dict):
        return "an object with the five prices (or null to take the model out) is required"
    for k in KINDS:
        if k not in row:
            return f"{k} is missing"
        if not _price(row[k]):
            return f"{k} must be a number from 0 to {int(PRICE_MAX)} (USD per million tokens)"
    return None


def _clean(row: dict) -> dict:
    return {k: float(row[k]) for k in KINDS}


def load_default(path: Path = DEFAULT_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"source": data.get("source"), "checked": data.get("checked"), "models": data["models"]}


def _read_user(path: Path):
    """(bytes, signature) of the user's table; (None, None) when there is none; ("error", reason) when it cannot be
    read. Opened with O_NOFOLLOW | O_NONBLOCK and fstat'ed (a regular file, at most USER_MAX): a FIFO or a symlink put
    there never holds the reader."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return "error", f"cannot open ({exc.strerror or type(exc).__name__})"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return "error", "not a regular file"
        if st.st_size > USER_MAX:
            return "error", f"larger than {USER_MAX} bytes"
        chunks, n = [], 0
        while n <= USER_MAX:
            b = os.read(fd, min(1 << 16, USER_MAX + 1 - n))
            if not b:
                break
            chunks.append(b)
            n += len(b)
        if n > USER_MAX:
            return "error", f"larger than {USER_MAX} bytes"
        return b"".join(chunks), (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError as exc:
        return "error", f"cannot read ({exc.strerror or type(exc).__name__})"
    finally:
        os.close(fd)


def signature(path: Path):
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def parse_user(raw: bytes) -> tuple[dict, list[str], bool]:
    """(the usable rows {model: row or None}, one reason per row left out, whether the file as a whole was read).
    A row that is not usable is left out alone; the others apply."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return {}, [f"the file is not JSON ({type(exc).__name__}): nothing in it is used"], False
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        return {}, ['the file needs {"models": {...}}: nothing in it is used'], False
    rows: dict = {}
    errors: list[str] = []
    for model, row in models.items():
        if not MODEL_RE.fullmatch(model):
            errors.append(f"{model[:60]!r}: not a model name")
            continue
        if row is None:
            rows[model] = None
            continue
        why = check_row(row)
        if why:
            errors.append(f"{model}: {why}")
            continue
        rows[model] = _clean(row)
    return rows, errors, True


def merge(default: dict, user_rows: dict) -> dict:
    """The table in use: the shipped rows, then the user's (a row replaces the model's, None takes it out)."""
    table = dict(default["models"])
    for model, row in user_rows.items():
        if row is None:
            table.pop(model, None)
        else:
            table[model] = row
    return table


def _n(u: dict, k: str) -> int | None:
    v = u.get(k, 0)
    if v is None:
        return 0
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def tokens_of(usage) -> dict | None:
    """The four kinds (cache writes split 5m / 1h when the record says so) from message.usage, or None."""
    if not isinstance(usage, dict):
        return None
    got = {k: _n(usage, k) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
    if any(v is None for v in got.values()):
        return None
    split = usage.get("cache_creation")
    w5 = w1 = None
    if isinstance(split, dict):
        w5, w1 = _n(split, "ephemeral_5m_input_tokens"), _n(split, "ephemeral_1h_input_tokens")
    return {"input": got["input_tokens"], "cache_write": got["cache_creation_input_tokens"],
            "cache_write_5m": w5, "cache_write_1h": w1, "cache_read": got["cache_read_input_tokens"],
            "output": got["output_tokens"]}


def cost(table: dict, model, usage) -> tuple[float | None, str | None]:
    """(USD, None) for one response, or (None, why) when the table cannot price it."""
    t = tokens_of(usage)
    if t is None:
        return None, "usage unreadable"
    row = table.get(model) if isinstance(model, str) else None
    if row is None:
        return None, "model not in the table"
    w5, w1 = t["cache_write_5m"], t["cache_write_1h"]
    if w5 is None or w1 is None:
        if t["cache_write"]:
            return None, "cache writes with no 5m / 1h split"
        w5 = w1 = 0
    prompt = t["input"] + t["cache_write"] + t["cache_read"]
    long = row.get("long")
    p = {k: row[k] for k in KINDS}
    if isinstance(long, dict) and isinstance(long.get("over"), int) and prompt > long["over"]:
        p = {k: long[k] for k in KINDS}
    speed = usage.get("speed")
    if speed not in (None, "standard"):
        fast = row.get("fast")
        if speed != "fast" or not isinstance(fast, dict):
            return None, f"no price for speed {speed!r}"
        k = fast["input"] / p["input"] if p["input"] else 0
        p = {"input": fast["input"], "output": fast["output"], "cache_write_5m": p["cache_write_5m"] * k,
             "cache_write_1h": p["cache_write_1h"] * k, "cache_read": p["cache_read"] * k}
    geo = usage.get("inference_geo")
    mult = 1.0
    if geo not in (None, "global", "", "not_available"):
        if geo != "us" or not _price(row.get("us")):
            return None, f"no price for inference_geo {geo!r}"
        mult = float(row["us"])
    usd = (t["input"] * p["input"] + w5 * p["cache_write_5m"] + w1 * p["cache_write_1h"]
           + t["cache_read"] * p["cache_read"] + t["output"] * p["output"]) / 1_000_000 * mult
    return usd, None


def total_tokens(usage) -> int:
    t = tokens_of(usage) or {}
    return sum(t.get(k) or 0 for k in ("input", "cache_write", "cache_read", "output"))


class PriceBook:
    """The table in use, read again when the user's file changes. ``poll(pool)`` is the event loop's: it only looks
    at a finished read and hands the next one to ``pool`` (stat, open, read, parse happen there)."""

    def __init__(self, default_path: Path = DEFAULT_PATH, user: Path | None = None) -> None:
        self.default = load_default(default_path)
        self.user = user
        self.user_rows: dict = {}
        self.errors: list[str] = []
        self.table = merge(self.default, {})
        self.sig = None
        self.rev = 0
        self._job = None
        self._checked = 0.0

    def path(self) -> Path:
        return self.user if self.user is not None else user_path()

    def _load(self):
        """Read the user's table if it changed since the last read: (signature, rows, errors), or None when it did not.
        Reads only — the worker's; the result is applied by the caller's thread (_apply), so the table, its rows and
        its errors always change together where the event loop reads them."""
        path = self.path()
        sig = signature(path)
        if sig == self.sig and sig is not None:
            return None
        raw, got = _read_user(path)
        if raw is None:
            rows, errors = {}, []
        elif raw == "error":
            rows, errors = {}, [f"{path.name}: {got}: the shipped table is used"]
        else:
            rows, errors, _ok = parse_user(raw)
            sig = got
        if sig == self.sig and rows == self.user_rows and errors == self.errors:
            return None
        return sig, rows, errors

    def _apply(self, loaded) -> bool:
        if loaded is None:
            return False
        self.sig, self.user_rows, self.errors = loaded
        self.table = merge(self.default, self.user_rows)
        self.rev += 1
        return True

    def read_now(self) -> bool:
        """Read and apply on this thread (the CLI, the watch's probe). True when the table changed."""
        return self._apply(self._load())

    def poll(self, pool) -> bool:
        """True when a read finished with a changed table (the slice is due). Never reads on the caller's thread:
        the read goes to ``pool``, and its result is applied here, on the next call."""
        changed = False
        job = self._job
        if job is not None:
            if not job.done():
                return False
            self._job = None
            try:
                changed = self._apply(job.result())
            except Exception:  # noqa: BLE001 — a read that failed is tried again
                changed = False
        now = time.monotonic()
        if now - self._checked >= CHECK_EVERY_S:
            self._checked = now
            self._job = pool.submit(self._load)
        return changed

    def recheck(self) -> None:
        """A write just happened: look again on the next poll."""
        self._checked = 0.0

    def rows(self) -> list[dict]:
        """Every model the page's sheet lists: where its price comes from (default / user / changed / removed)."""
        out = []
        for model in sorted(set(self.default["models"]) | set(self.user_rows)):
            d = self.default["models"].get(model)
            u = self.user_rows.get(model, ...)
            if u is ...:
                origin, row = "default", d
            elif u is None:
                origin, row = "removed", d
            else:
                origin, row = ("changed" if d is not None else "user"), u
            item = {"model": model, "origin": origin}
            if row is not None:
                item.update({k: row[k] for k in KINDS})
                for extra in ("long", "fast", "us"):
                    if origin in ("default", "removed") and extra in row:
                        item[extra] = row[extra]
            out.append(item)
        return out


# ---------------------------------------------------------------- writing the user's table (the CLI and the page)

OPS = ("set", "remove", "reset")


def apply_op(path: Path, op: str, model: str, row=None, default: dict | None = None) -> tuple[bool, str]:
    """Change the user's table: set (add a model, or change one's prices), remove (a model the user added is taken
    out of the file; a shipped one is taken out with null), reset (the model's line is taken out of the file: the
    shipped price again). (ok, message). A table that is not JSON is not overwritten: it may be the user's own work."""
    default = load_default() if default is None else default
    if op not in OPS:
        return False, f"op must be one of {', '.join(OPS)}"
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        return False, "not a model name"
    raw, got = _read_user(path)
    if raw == "error":
        return False, f"{path}: {got}"
    if raw is None:
        data = {"models": {}}
    else:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return False, f"{path} is not JSON: fix or remove it first (nothing was changed)"
        if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
            return False, f'{path} needs {{"models": {{...}}}}: fix or remove it first (nothing was changed)'
    models = data["models"]
    shipped = model in default["models"]
    if op == "set":
        why = check_row(row)
        if why:
            return False, why
        models[model] = _clean(row)
        msg = f"{model}: set"
    elif op == "remove":
        if shipped:
            models[model] = None
        elif model in models:
            del models[model]
        else:
            return False, f"{model} is in neither table"
        msg = f"{model}: removed"
    else:
        if model not in models:
            return False, f"{model} has no line of its own (it already uses the shipped price)" if shipped else f"{model} is in neither table"
        del models[model]
        msg = f"{model}: back to the shipped price" if shipped else f"{model}: removed"
    data.setdefault("about", "jui viz: your own prices (USD per million tokens). They override and add to the shipped "
                             "table; null takes a model out. `jui viz prices` or the page's 単価 sheet edit it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".prices.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)
    return True, msg
