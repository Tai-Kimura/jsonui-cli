"""The cost simulator's reply (plan docs/plans/2026-10-20-jui-viz-backend-load-and-cost-simulator.md, L-C): viz's side.

viz computes nothing: document_tools' infra.load (the load definitions, against the model), infra.room (the model),
infra.cost.pricebook (the room's price files > the fetched cache > the bundled table), infra.cost.engine (the month)
and infra.cost.view (the screens' shapes), reached as infra_docs reaches the model (core/document_tools_import). The
reads are the model's (inside the room, O_NOFOLLOW, capped, secret shapes refused). The last two months simulated
are kept, keyed by the room, the scenario and the files' sizes and times, so going from the month to a day does not
simulate again.

Blocking: the server runs it in its read pool.
"""
from __future__ import annotations

import os
import re
import threading
from collections import OrderedDict
from pathlib import Path

from . import i18n

ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
DATE = re.compile(r"^20[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
KEEP = 2
_KEPT: OrderedDict = OrderedDict()
_LOCK = threading.Lock()


def _mods():
    from ..core.document_tools_import import load_document_tools_module
    names = ("infra.load", "infra.room", "infra.cost.engine", "infra.cost.pricebook", "infra.cost.view")
    mods = [load_document_tools_module(n)[0] for n in names]
    return None if any(m is None for m in mods) else dict(zip(("load", "room", "engine", "pricebook", "view"), mods))


def _stamp(path: str) -> tuple | None:
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def _signature(root: Path, room, folders: list[str], cache: Path) -> tuple:
    """Every file the month depends on, by name, size and time (no content read): the room's jui.config.json (where the
    folders are), the model's, the load definitions' and the price files' folders, and the fetched prices' cache
    (<viz home>/cloud-prices, read by the price book too). A change to any of them simulates again."""
    out = [("config", _stamp(os.path.join(root, room.CONFIG_NAME)))]
    for folder in folders:
        for name, size in room._list_dir(root, folder) or []:
            out.append((folder, name, size, _stamp(os.path.join(root, folder, name))))
    if cache.is_dir():
        for f in sorted(cache.rglob("*.json")):
            if not f.is_symlink():
                out.append(("cache", str(f.relative_to(cache)), _stamp(str(f))))
    return tuple(out)


def _refuse(status: int, seq, reason: str, message: str) -> tuple[int, dict]:
    return status, {"ok": False, "seq": seq, "reason": reason, "message": message}


def _simulate(m: dict, root: Path, scenario_id: str | None):
    """(status, error reply) or (None, (the loads' reply, the chosen scenario, the model, the result, warnings))."""
    loads = m["load"].read(root)
    if not loads.get("ok"):
        return (404 if loads.get("reason") in ("no_infra", "not_a_room") else 422), loads
    scenarios = loads["scenarios"]
    if not scenarios:
        return 404, {"ok": False, "reason": "no_load", "message": f"no load definition in {loads['dir']}"}
    chosen = next((s for s in scenarios if s["id"] == scenario_id), None) if scenario_id else scenarios[0]
    if chosen is None:
        return 404, {"ok": False, "reason": "no_scenario", "message": "no such scenario"}
    model = m["room"].read(root)
    folders = [model["dir"], loads["dir"], m["room"].side_dir(root, "prices_dir")]
    key = (str(root), chosen["id"], _signature(root, m["room"], folders, m["pricebook"].cache_dir()))
    with _LOCK:
        kept = _KEPT.get(key)
        if kept is not None:
            _KEPT.move_to_end(key)
            return None, kept
    book, warnings = m["pricebook"].load(root)
    result = m["engine"].simulate(chosen, model, book)
    got = (loads, chosen, model, result, warnings)
    with _LOCK:
        _KEPT[key] = got
        while len(_KEPT) > KEEP:
            _KEPT.popitem(last=False)
    return None, got


def read(root: Path | str, seq=None, scenario: str | None = None, date: str | None = None,
         by: str = "provider") -> tuple[int, dict]:
    """(HTTP status, the page's reply). No date: {ok, seq, scenarios, scenario, month, problems, prices}; a date:
    {ok, seq, scenario, day}."""
    if scenario is not None and not (isinstance(scenario, str) and ID.match(scenario)):
        return _refuse(400, seq, "bad_request", "scenario is an id")
    if date is not None and not (isinstance(date, str) and DATE.match(date)):
        return _refuse(400, seq, "bad_request", "date is YYYY-MM-DD")
    if by not in ("provider", "node"):
        return _refuse(400, seq, "bad_request", "by is provider or node")
    m = _mods()
    if m is None:
        return _refuse(500, seq, "unreadable", i18n.tl("srv.cost.no_tools"))
    try:
        status, got = _simulate(m, Path(root), scenario)
    except m["room"].Refused as r:
        return _refuse(400, seq, r.reason, r.message)
    if status is not None:
        got = dict(got, seq=seq, ok=False)
        got.pop("scenarios", None)
        return status, got
    loads, chosen, model, result, warnings = got
    if date is not None:
        if not date.startswith(chosen["month"] + "-") or not any(h["date"] == date for h in chosen["hours"]):
            return _refuse(400, seq, "bad_request", "the date is not in the scenario's month")
        return 200, {"ok": True, "seq": seq, "scenario": chosen["id"], "day": m["view"].day_view(result, model, date)}
    problems = [p for p in loads["problems"] if p["severity"] in ("error", "warning")]
    return 200, {"ok": True, "seq": seq, "scenario": chosen["id"],
                 "scenarios": [{"id": s["id"], "label": s["label"], "file": s["file"], "month": s["month"],
                                "environment": s["environment"]} for s in loads["scenarios"]],
                 "month": m["view"].month_view(result, model, by),
                 "problems": {"count": len(problems), "first": [{k: p.get(k) for k in ("file", "path", "code", "message", "severity")}
                                                                 for p in problems[:20]]},
                 "prices": {"warnings": warnings[:20]}}


def forget() -> None:
    """Drop the kept months (tests)."""
    with _LOCK:
        _KEPT.clear()
