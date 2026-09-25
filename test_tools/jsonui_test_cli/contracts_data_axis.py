"""The data axis of contracts coverage: which view-model states the rows reach.

Design §2.1 / §6.1 (P2.5). A separate section, REPORT ONLY — it never moves an
exit code. Its unit is (screen, field, value), and it is bounded by the layout:
a state counts only where the screen's layout can show it.

- Bool: a field declared Bool (`stateManagement.uiVariables` or
  `dataFlow.viewModel.vars`) whose name is a binding ROOT in the layout
  (`layout_facts`), with the values true and false.
- enum: each `stateManagement.states[].values[]` whose `visibleElements` are
  all ids the layout has.
- For each unit, two columns: ARRANGED — a row's `when` sets it (`data.X` or
  a seed `state.X`); PRODUCED — a row's `then` asserts it (`data.X`).

What it could not bind is named, never dropped: Bool fields the layout does
not bind, `visibleElements` ids the layout does not have (spec and layout
out of step, which no gate saw before), screens whose layout is not linked
or has an include that does not resolve, and cell layouts (another scope).

The layout is read by `jui_cli.core.layout_facts` and nothing else here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

BOOL_TYPES = {"bool", "boolean"}


def layout_dirs(root: Path, config: dict) -> tuple:
    """(layouts, styles) directories the project's config names — the same
    defaults `jui` applies (config_manager.DEFAULT_CONFIG)."""
    from .branch_tests import _prefer_sibling_jui_cli

    _prefer_sibling_jui_cli()
    from jui_cli.core.config_manager import DEFAULT_CONFIG

    layouts = config.get("layouts_directory") or DEFAULT_CONFIG["layouts_directory"]
    styles = config.get("styles_directory") or DEFAULT_CONFIG["styles_directory"]
    return (root / layouts).resolve(), (root / styles).resolve()


@dataclass
class ScreenData:
    evaluated: bool = False
    reason: str | None = None
    #: [{field, value, arranged, produced}] in declaration order.
    units: list = field(default_factory=list)
    bool_not_in_layout: int = 0
    visible_ids_not_in_layout: int = 0
    unresolved_includes: int = 0
    cells: int = 0

    @property
    def counts(self) -> dict:
        arranged = sum(1 for u in self.units if u["arranged"])
        produced = sum(1 for u in self.units if u["produced"])
        neither = sum(1 for u in self.units if not u["arranged"] and not u["produced"])
        return {"units": len(self.units), "fields": len({u["field"] for u in self.units}),
                "arranged": arranged, "produced": produced, "neither": neither}

    def to_json(self) -> dict:
        return {"evaluated": self.evaluated, "reason": self.reason, **self.counts,
                "units_detail": list(self.units),
                "bool_not_in_layout": self.bool_not_in_layout,
                "visible_ids_not_in_layout": self.visible_ids_not_in_layout,
                "unresolved_includes": self.unresolved_includes, "cells": self.cells}


def _bool_fields(spec: dict) -> list:
    names = []
    state = spec.get("stateManagement") if isinstance(spec.get("stateManagement"), dict) else {}
    view_model = ((spec.get("dataFlow") or {}).get("viewModel") or {}) \
        if isinstance(spec.get("dataFlow"), dict) else {}
    for entry in (state.get("uiVariables") or []) + (view_model.get("vars") or []):
        if (isinstance(entry, dict) and isinstance(entry.get("name"), str)
                and str(entry.get("type", "")).strip().lower() in BOOL_TYPES
                and entry["name"] not in names):
            names.append(entry["name"])
    return names


def _states(spec: dict) -> list:
    state = spec.get("stateManagement") if isinstance(spec.get("stateManagement"), dict) else {}
    return [s for s in (state.get("states") or []) if isinstance(s, dict)
            and isinstance(s.get("name"), str)]


def _set_by(rows: list) -> tuple:
    """(arranged, produced): {(field, value)} the rows' when/seed and then name."""
    arranged, produced = set(), set()
    for branch in rows:
        when = branch.get("when") if isinstance(branch.get("when"), dict) else {}
        then = branch.get("then") if isinstance(branch.get("then"), dict) else {}
        for key, value in when.items():
            for prefix in ("data.", "state."):
                if isinstance(key, str) and key.startswith(prefix) and _hashable(value):
                    arranged.add((key[len(prefix):], value))
        for key, value in then.items():
            if isinstance(key, str) and key.startswith("data.") and _hashable(value):
                produced.add((key[len("data."):], value))
    return arranged, produced


def _hashable(value) -> bool:
    return isinstance(value, (str, bool, int, float)) or value is None


def screen_data(spec: dict, facts, rows: list) -> ScreenData:
    """The data axis of one screen on one platform. *facts* is its
    `LayoutFacts` for the platform; *rows* the branches active there."""
    data = ScreenData(reason=facts.reason, cells=facts.cells,
                      unresolved_includes=len(facts.unresolved_includes))
    if not facts.evaluated:
        return data
    data.evaluated = True
    arranged, produced = _set_by(rows)
    for name in _bool_fields(spec):
        if name not in facts.binding_roots:
            data.bool_not_in_layout += 1
            continue
        for value in (True, False):
            data.units.append({"field": name, "value": value, "kind": "bool",
                               "arranged": (name, value) in arranged,
                               "produced": (name, value) in produced})
    for state in _states(spec):
        for entry in state.get("values") or []:
            if not isinstance(entry, dict) or not isinstance(entry.get("value"), str):
                continue
            ids = [i for i in (entry.get("visibleElements") or []) if isinstance(i, str)]
            missing = [i for i in ids if i not in facts.ids]
            data.visible_ids_not_in_layout += len(missing)
            if not ids or missing:
                continue
            key = (state["name"], entry["value"])
            data.units.append({"field": state["name"], "value": entry["value"], "kind": "enum",
                               "arranged": key in arranged, "produced": key in produced})
    return data


#: Keys of the block's data totals, in print order.
TOTAL_KEYS = ("units", "fields", "arranged", "produced", "neither",
              "screens_evaluated", "layout_not_linked", "layout_missing",
              "unresolved_include", "bool_not_in_layout", "visible_ids_not_in_layout", "cells")


def block_totals(screens: list) -> dict:
    """Summed over the block's active screens that carry a data result."""
    totals = dict.fromkeys(TOTAL_KEYS, 0)
    for s in screens:
        d = getattr(s, "data", None)
        if d is None:
            continue
        for key, value in d.counts.items():
            totals[key] += value
        totals["screens_evaluated"] += int(d.evaluated)
        totals["layout_not_linked"] += int(d.reason == "layout not linked")
        totals["layout_missing"] += int(d.reason in ("layout file missing", "layout file unreadable"))
        totals["unresolved_include"] += int(bool(d.unresolved_includes))
        totals["bool_not_in_layout"] += d.bool_not_in_layout
        totals["visible_ids_not_in_layout"] += d.visible_ids_not_in_layout
        totals["cells"] += d.cells
    return totals


def coarse(screens: list) -> bool:
    """The kill criterion's switch (§6.1): when a MAJORITY of the block's
    active screens carry more data units than statuses required, the text
    reports fields instead of values (the values stay in --json)."""
    active = [s for s in screens if getattr(s, "data", None) is not None]
    if not active:
        return False
    heavy = sum(1 for s in active if len(s.data.units) > s.statuses_required)
    return heavy * 2 > len(active)


def text_line(platform: str, screens: list) -> str:
    t = block_totals(screens)
    unit = (f"fields {t['fields']} (coarse: most screens carry more data units than "
            f"statuses required — values in --json)") if coarse(screens) else f"units {t['units']}"
    active = sum(1 for s in screens if getattr(s, "data", None) is not None)
    return (f"[platform={platform}] data (report only) {unit} · arranged {t['arranged']} · "
            f"produced {t['produced']} · neither {t['neither']} · screens evaluated "
            f"{t['screens_evaluated']} of {active} (layout not linked {t['layout_not_linked']} · "
            f"layout missing {t['layout_missing']} · unresolved include "
            f"{t['unresolved_include']}) · Bool not in layout {t['bool_not_in_layout']} · "
            f"visibleElements not in layout {t['visible_ids_not_in_layout']} · cells not bound "
            f"{t['cells']}")
