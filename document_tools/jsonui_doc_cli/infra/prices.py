"""The price files of the cost simulator (infra-prices.v0, plan docs/plans/2026-10-20-jui-viz-backend-load-and-cost-
simulator.md, L-A): one form for a person's files (<infra.dir>/prices, jui.config.json's infra.prices_dir), the prices
fetched and the bundled table. Which file wins and how a node finds its sku is the cost's (L-B); here a file is read
and its rows checked.

Per file (an error leaves the file out whole): JSON, the schema, the shapes of secrets. Per row (a warning, only that
row left out): neither price_usd nor tiers; tiers not starting at 0, not in order or overlapping; a row with the same
provider, service, sku, region, unit and effective date as an earlier one (the earlier is kept).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import model as M
from . import room as R

SCHEMA_PATH = Path(__file__).with_name("infra-prices.v0.schema.json")
KEY = ("provider", "service", "sku", "region", "unit", "effective")

_SCHEMA: list[dict] = []


def schema() -> dict:
    if not _SCHEMA:
        _SCHEMA.append(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    return _SCHEMA[0]


def units() -> list[str]:
    return list(schema()["$defs"]["unit"]["enum"])


def _p(file: str, path: str, code: str, message: str, severity: str = "error", say: tuple | None = None,
       **where) -> dict:
    """A problem; say: (its words' key, the values they name), for a line in another language (room.SIDE_JA)."""
    out = M._problem(file, path, code, message, severity)
    if say:
        out["detail"] = {"keyword": say[0], **say[1]}
    out.update({k: v for k, v in where.items() if v is not None})
    return out


def read_file(name: str, raw: bytes) -> tuple[dict | None, list[dict]]:
    """(the file's object, problems): JSON, the shapes of secrets, the schema. None when any is an error."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, [dict(_p(name, "/", "json", f"not JSON (line {exc.lineno}, column {exc.colno})", fn="read_file"),
                           line=exc.lineno)]
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        return None, [_p(name, "/", "json", f"not JSON ({type(exc).__name__})", fn="read_file")]
    root = schema()
    try:
        strings = list(M._walk_strings(data, "", root))
        found = M.check_schema(data, root=root)
    except RecursionError:
        return None, [_p(name, "/", "json", "nested too deeply to read", fn="read_file")]
    problems = [_p(name, path, f"secret.{kind}", f"holds the shape of a secret ({kind.replace('_', ' ')}): a price "
                   "file keeps no values", fn="read_file")
                for path, text in strings for kind in M.secret_findings(text)]
    problems += [_p(name, path, "schema", why, fn="check_schema") for path, why in found]
    return (None if problems else data), problems


def check_tiers(tiers: list[dict]) -> "M.Why | None":
    """Why the tiers cannot be used, or None: from 0 upward, each from where the last ended, only the last open."""
    if tiers[0]["from"] != 0:
        return M.Why("the first tier does not start at 0", "prices.row.tier_start")
    for k, t in enumerate(tiers):
        if "to" in t and t["to"] <= t["from"]:
            return M.Why(f"tier {k} ends at or before it starts", "prices.row.tier_end", k=k)
        if k + 1 < len(tiers):
            if "to" not in t:
                return M.Why(f"tier {k} has no end but is not the last", "prices.row.tier_open", k=k)
            if tiers[k + 1]["from"] != t["to"]:
                return M.Why(f"tier {k + 1} does not start where tier {k} ends", "prices.row.tier_gap", k=k, next=k + 1)
    return None


def check_row(name: str, i: int, row: dict) -> "M.Why | None":
    """Why a row cannot be used, or None."""
    if ("price_usd" in row) == ("tiers" in row):
        return M.Why("needs exactly one of price_usd and tiers", "prices.row.exactly_one")
    try:
        date.fromisoformat(row["effective"])
    except ValueError:
        return M.Why("effective is not a date of the calendar", "prices.row.effective")
    return check_tiers(row["tiers"]) if "tiers" in row else None


def rows(name: str, doc: dict) -> tuple[list[dict], list[dict]]:
    """The usable rows of one file (each with its file and index, to trace which price was used) and the warnings."""
    out, problems, seen = [], [], {}
    for i, row in enumerate(doc["prices"]):
        why = check_row(name, i, row)
        if why:
            problems.append(_p(name, f"/prices/{i}", "prices.row", why + ": this row is left out", "warning",
                               say=(why.keyword, why.detail), fn="check_row"))
            continue
        key = tuple(row[k] for k in KEY)
        if key in seen:
            problems.append(_p(name, f"/prices/{i}", "prices.duplicate", f"the same price as row {seen[key]}: that "
                               "one is kept", "warning", say=("prices.duplicate", {"row": seen[key]}), fn="rows"))
            continue
        seen[key] = i
        out.append(dict(row, file=name, index=i, per_units=row.get("per_units", 1)))
    return out, problems


def read(root: Path, words: R.Words = R.DEFAULT_WORDS) -> dict:
    """The room's price files: {ok, dir, files, prices, problems}, or {ok: False, reason, message, short}. Each
    problem has its line in ``words``' language (short)."""
    root = Path(root)
    folder = ""
    try:
        folder = R.side_dir(root, "prices_dir")
        files, problems = R.read_json_folder(root, folder)
    except R.Refused as r:
        return {"ok": False, "reason": r.reason, "message": r.message, "short": r.line(folder, words), "problems": []}
    used, prices = [], []
    for name, raw in files:
        doc, found = read_file(name, raw)
        problems += found
        if doc is None:
            continue
        got, found = rows(name, doc)
        problems += found
        prices += got
        used.append(name)
    for p in problems:
        p["short"] = R.short(p, folder, words)
    return {"ok": True, "dir": folder, "files": used, "prices": prices, "problems": problems}
