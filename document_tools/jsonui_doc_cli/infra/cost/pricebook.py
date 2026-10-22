"""Which price a meter is charged at (plan, 依頼者の決め 3): a person's price files > the prices fetched (the cache)
> the bundled table, each in infra-prices.v0's form. A price is found by provider, service, sku, unit and region
("global" when the region has none of its own); among the rows of the first layer that has one, the latest whose
effective date is on or before the month's first day. The answer says where it came from (the layer, the file and the
row's index), so the display can show which price was used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .. import prices as P

LAYERS = ("user", "cache", "bundled")
BUNDLED_PATH = Path(__file__).with_name("bundled-prices.json")


def bundled_rows() -> list[dict]:
    """The bundled table's rows (checked against its schema like any price file)."""
    doc, problems = P.read_file(BUNDLED_PATH.name, BUNDLED_PATH.read_bytes())
    if doc is None:                  # a test keeps it valid; a broken one gives no price rather than a wrong one
        return []
    return P.rows(BUNDLED_PATH.name, doc)[0]


def cache_dir(env: dict | None = None) -> Path:
    """Where the fetched prices are kept: <viz home>/cloud-prices (viz home as jui viz finds it)."""
    env = os.environ if env is None else env
    home = env.get("JUI_VIZ_HOME") or (os.path.join(env["XDG_STATE_HOME"], "jui-viz") if env.get("XDG_STATE_HOME")
                                       else os.path.join(os.path.expanduser("~"), ".local", "state", "jui-viz"))
    return Path(home) / "cloud-prices"


def cache_rows(folder: Path) -> tuple[list[dict], list[str]]:
    """The fetched prices' rows (every *.json below the folder, read as a price file) and why any file was not used.
    Written by fetch.py (L-B2); an empty or missing folder is no price and no warning. A file the index does not say
    this version wrote (another version's reading of the answer, or one the index does not name) is not used: the
    bundled price stands in until the next fetch, which an upgrade makes due at once (fetch.due)."""
    from . import fetch as FE  # noqa: PLC0415
    rows, why = [], []
    if not folder.is_dir():
        return rows, why
    index = FE.read_index(folder)
    mine = {k for k, v in index.get("files", {}).items() if isinstance(v, dict) and v.get("writer") == FE.WRITER}
    others = 0
    for f in sorted(folder.rglob("*.json")):
        if f.is_symlink() or not f.is_file() or f.name.startswith(".") or (f.parent == folder and f.name == "index.json"):
            continue   # index.json: where each fetched file came from (fetch.py), not a price file
        rel = f.relative_to(folder).as_posix()
        if rel not in mine:
            others += 1
            continue
        doc, problems = P.read_file(f.name, f.read_bytes())
        if doc is None:
            why.append(f"{f.relative_to(folder)}: not used ({problems[0]['code']})")
            continue
        rows += P.rows(str(f.relative_to(folder)), doc)[0]
    if others:
        why.append(f"{others} fetched price file(s) were written by another jsonui-cli version (or the index does not "
                   f"name them): not used until fetched again by {FE.WRITER}; the bundled prices stand in")
    return rows, why


class Book:
    """The price rows by layer, and the lookup."""

    def __init__(self, user: list[dict] | None = None, cache: list[dict] | None = None,
                 bundled: list[dict] | None = None) -> None:
        self.layers = {"user": list(user or []), "cache": list(cache or []), "bundled": list(bundled or [])}
        self._index: dict[tuple, list[tuple[str, dict]]] = {}
        for layer in LAYERS:
            for row in self.layers[layer]:
                key = (row["provider"], row["service"], row["sku"], row["unit"])
                self._index.setdefault(key, []).append((layer, row))

    def find(self, provider: str, service: str, sku: str, unit: str, region: str, on: str) -> dict | None:
        """{layer, row} of the price to use, or None. The node's service, or its head before "." ("rds" for
        "rds.mysql") when no row names the whole of it."""
        for svc in dict.fromkeys([service, service.split(".", 1)[0]]):
            got = self._find(provider, svc, sku, unit, region, on)
            if got:
                return got
        return None

    def _find(self, provider, service, sku, unit, region, on):
        candidates = self._index.get((provider, service, sku, unit), [])
        for layer in LAYERS:
            for want in ([region, "global"] if region and region != "global" else ["global"]):
                rows = [r for lay, r in candidates if lay == layer and r["region"] == want and r["effective"] <= on]
                if rows:
                    return {"layer": layer, "row": max(rows, key=lambda r: r["effective"])}
        return None


def load(root: Path | None = None, env: dict | None = None, words=None) -> tuple[Book, list[str]]:
    """The book for a room: its price files (prices.read), the cache and the bundled table; and warnings. A price
    file's problem is its line in ``words``' language (prices.read's short; room.Words when None) and its code."""
    warnings: list[str] = []
    user: list[dict] = []
    if root is not None:
        got = P.read(Path(root), **({"words": words} if words is not None else {}))
        if got.get("ok"):
            user = got["prices"]
            warnings += [f"{p['short']} [{p['code']}]" for p in got["problems"]]
        else:
            warnings.append(f"the room's price files are not used ({got['reason']}): {got['message']}")
    cache, why = cache_rows(cache_dir(env))
    bundled = bundled_rows()
    return Book(user, cache, bundled), warnings + why + free_dropped(user, bundled)


def free_dropped(user: list[dict], bundled: list[dict]) -> list[str]:
    """A room's price row with no free amount where the bundled row of the same price has one: the room's row wins, so
    that free amount is not taken (an egress row written by hand drops the account's 100 GB a month; ticket
    2026-10-21-agents-skills-mcp-for-server-room §2 C2). One warning per price."""
    free = {}
    for row in bundled:
        if row.get("free"):
            free.setdefault((row["provider"], row["service"], row["sku"], row["unit"]), row["free"])
    out, seen = [], set()
    for row in user:
        key = (row["provider"], row["service"], row["sku"], row["unit"])
        if row.get("free") or key not in free or key in seen:
            continue
        seen.add(key)
        f = free[key]
        pool = f" from the account's pool {f['pool']}" if f.get("pool") else ""
        out.append(f"{row.get('file')} /prices/{row.get('index')}: {'/'.join(key[:3])} has no free amount, but the "
                   f"bundled price takes {f['amount']:g} {key[3]} a {f['period']}{pool} free; this row wins, so none is "
                   f"taken (write free on it to keep it) [prices.free_dropped]")
    return out


def ref(found: dict) -> dict:
    """The price's trace for a line: layer, file, index, source, effective, sku, region, unit, per_units."""
    row = found["row"]
    return {"layer": found["layer"], **{k: row.get(k) for k in ("file", "index", "source", "effective", "sku", "region",
                                                                 "unit", "per_units")}}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
