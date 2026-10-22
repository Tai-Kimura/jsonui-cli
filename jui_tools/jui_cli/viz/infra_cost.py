"""The cost simulator's reply (plan docs/plans/2026-10-20-jui-viz-backend-load-and-cost-simulator.md, L-C): viz's side.

viz computes nothing: document_tools' infra.load (the load definitions, against the model), infra.room (the model),
infra.cost.pricebook (the room's price files > the fetched cache > the bundled table), infra.cost.engine (the month)
and infra.cost.view (the screens' shapes), reached as infra_docs reaches the model (core/document_tools_import). The
reads are the model's (inside the room, O_NOFOLLOW, capped, secret shapes refused). The last two months simulated
are kept, keyed by the room, the scenario and the files' sizes and times, so going from the month to a day does not
simulate again.

The account (engine.simulate_account): with two environments or more in the model and a scenario for each, the month
is the account's unless the page asks for one environment (the requester 10-21: 「合計で」), its environments priced
with one total (a free amount taken once). Each environment's
scenario is the chosen one for its own environment, else that environment's first of the chosen one's month; an
environment without one of that month is left out and named.

Blocking: the server runs it in its read pool.
"""
from __future__ import annotations

import os
import re
import threading
from collections import OrderedDict
from pathlib import Path

from . import i18n
from . import infra_words

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


def _refuse(status: int, seq, reason: str, message: str, short: str) -> tuple[int, dict]:
    """A refusal: its message (English, for a log) and its line in the page's language (short: what the page shows)."""
    return status, {"ok": False, "seq": seq, "reason": reason, "message": message, "short": short}


def account_scenarios(scenarios: list[dict], model: dict, chosen: dict) -> tuple[bool, list[dict], list[str]]:
    """(whether the account can be asked for, its scenarios in the model's environments' order, the environments left
    out): two environments or more, each with a scenario of some month; per environment the chosen scenario, else
    its first of the chosen one's month."""
    envs = [e["id"] for e in model.get("environments") or []]
    available = len(envs) > 1 and all(any(s["environment"] == e for s in scenarios) for e in envs)
    picked, missing = [], []
    for e in envs:
        s = chosen if chosen["environment"] == e else next(
            (x for x in scenarios if x["environment"] == e and x["month"] == chosen["month"]), None)
        (picked.append(s) if s else missing.append(e))
    return available, picked, missing


def _simulate(m: dict, root: Path, scenario_id: str | None, account: bool | None = None):
    """(status, error reply) or (None, (the loads' reply, the chosen scenario, the model, the result, warnings, the
    account: None, or (its scenarios, their results, the environments left out))). With account, the result is the
    chosen scenario's within the account's pricing; None: the account where it can be had."""
    loads = m["load"].read(root, words=infra_words.RoomWords(m["room"].LIMITS, m["room"].EXCLUDE_MAX))
    if not loads.get("ok"):
        return (404 if loads.get("reason") in ("no_infra", "not_a_room") else 422), loads
    scenarios = loads["scenarios"]
    if not scenarios:
        return 404, {"ok": False, "reason": "no_load", "message": f"no load definition in {loads['dir']}",
                     "short": i18n.tl("srv.cost.refused.no_load", folder=loads["dir"])}
    chosen = next((s for s in scenarios if s["id"] == scenario_id), None) if scenario_id else scenarios[0]
    if chosen is None:
        return 404, {"ok": False, "reason": "no_scenario", "message": "no such scenario",
                     "short": i18n.tl("srv.cost.refused.no_scenario")}
    model = m["room"].read(root)
    if account is None:
        account = account_scenarios(scenarios, model, chosen)[0]
    folders = [model["dir"], loads["dir"], m["room"].side_dir(root, "prices_dir")]
    key = (str(root), chosen["id"], account, _signature(root, m["room"], folders, m["pricebook"].cache_dir()))
    with _LOCK:
        kept = _KEPT.get(key)
        if kept is not None:
            _KEPT.move_to_end(key)
            return None, kept
    book, warnings = m["pricebook"].load(root, words=infra_words.RoomWords(m["room"].LIMITS, m["room"].EXCLUDE_MAX))
    acct = None
    if account:
        available, picked, missing = account_scenarios(scenarios, model, chosen)
        if not available:
            return 404, {"ok": False, "reason": "no_account",
                         "message": "the account needs two environments or more, each with a load definition",
                         "short": i18n.tl("srv.cost.refused.no_account")}
        results = m["engine"].simulate_account(picked, model, book)
        result = results[picked.index(chosen)]
        acct = (picked, results, missing)
    else:
        result = m["engine"].simulate(chosen, model, book)
    got = (loads, chosen, model, result, warnings, acct)
    words = infra_words.RoomWords(m["room"].LIMITS, m["room"].EXCLUDE_MAX)
    for w in result.warnings + [w for r in (acct[1] if acct else []) for w in r.warnings]:
        w["short"] = m["room"].cost_short(w, words)   # each warning's line in the page's language (room.COST_JA)
    with _LOCK:
        _KEPT[key] = got
        while len(_KEPT) > KEEP:
            _KEPT.popitem(last=False)
    return None, got


def read(root: Path | str, seq=None, scenario: str | None = None, date: str | None = None,
         by: str = "provider", account: bool | None = None) -> tuple[int, dict]:
    """(HTTP status, the page's reply). No date: {ok, seq, scenarios, scenario, month, problems, prices, account:
    {available, on, scenarios?, missing?}}; a date: {ok, seq, scenario, day} (with account, the chosen scenario's day
    priced within the account). account: true, false (one environment) or None (the account where it can be had)."""
    if account is not None and not isinstance(account, bool):
        return _refuse(400, seq, "bad_request", "account is true, false or null", i18n.tl("srv.cost.refused.account"))
    if scenario is not None and not (isinstance(scenario, str) and ID.match(scenario)):
        return _refuse(400, seq, "bad_request", "scenario is an id", i18n.tl("srv.cost.refused.scenario"))
    if date is not None and not (isinstance(date, str) and DATE.match(date)):
        return _refuse(400, seq, "bad_request", "date is YYYY-MM-DD", i18n.tl("srv.cost.refused.date"))
    if by not in ("provider", "node"):
        return _refuse(400, seq, "bad_request", "by is provider or node", i18n.tl("srv.cost.refused.by"))
    m = _mods()
    if m is None:
        return _refuse(500, seq, "unreadable", i18n.tl("srv.cost.no_tools"), i18n.tl("srv.cost.no_tools"))
    try:
        status, got = _simulate(m, Path(root), scenario, account)
    except m["room"].Refused as r:
        return _refuse(400, seq, r.reason, r.message, r.line("", infra_words.RoomWords(m["room"].LIMITS, m["room"].EXCLUDE_MAX)))
    if status is not None:
        got = dict(got, seq=seq, ok=False)
        got.pop("scenarios", None)
        return status, got
    loads, chosen, model, result, warnings, acct = got
    if date is not None:
        if not date.startswith(chosen["month"] + "-") or not any(h["date"] == date for h in chosen["hours"]):
            return _refuse(400, seq, "bad_request", "the date is not in the scenario's month",
                           i18n.tl("srv.cost.refused.date_month"))
        return 200, {"ok": True, "seq": seq, "scenario": chosen["id"], "day": m["view"].day_view(result, model, date, words=infra_words.CostLabels())}
    problems = [p for p in loads["problems"] if p["severity"] in ("error", "warning")]
    return 200, {"ok": True, "seq": seq, "scenario": chosen["id"],
                 "scenarios": [{"id": s["id"], "label": s["label"], "file": s["file"], "month": s["month"],
                                "environment": s["environment"]} for s in loads["scenarios"]],
                 "month": m["view"].account_view(list(zip(acct[0], acct[1])), model, words=infra_words.CostLabels()) if acct
                 else m["view"].month_view(result, model, by, words=infra_words.CostLabels()),
                 "account": {"available": account_scenarios(loads["scenarios"], model, chosen)[0], "on": bool(acct),
                             **({"scenarios": [s["id"] for s in acct[0]], "missing": acct[2]} if acct else {})},
                 "problems": {"count": len(problems), "first": [{k: p.get(k) for k in ("file", "path", "code", "message", "short", "severity")}
                                                                 for p in problems[:20]]},
                 "prices": {"warnings": warnings[:20]}}


def forget() -> None:
    """Drop the kept months (tests)."""
    with _LOCK:
        _KEPT.clear()
