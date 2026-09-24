"""The data axis of contracts coverage (design §6.1, P2.5) — report only.

Units are (screen, field, value), bounded by the layout `jui_cli.core.layout_facts`
reads: a Bool field only where the layout binds it, an enum value only where
the layout holds every element it shows. For each unit, whether a row ARRANGES
it (when / seed) and whether a row asserts it is PRODUCED (then). What could
not be bound is counted and named. The section moves no exit code.

On the coverage suite's own project, given a layout: the arms below pin each
column, each denominator, the exit left alone, and the coarse switch (the kill
criterion) at its boundary.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonui_test_cli import contracts_coverage as cc
from jsonui_test_cli import contracts_data_axis as da
from tests import test_contracts_coverage as tcc


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _screen_with_state(rows=None) -> dict:
    spec = tcc._screen()
    spec["metadata"]["layoutFile"] = "detail"
    spec["stateManagement"] = {
        "uiVariables": [{"name": "isBusy", "type": "Bool", "description": "d"},
                        {"name": "isHiddenFlag", "type": "Bool", "description": "d"},
                        {"name": "title", "type": "String", "description": "d"}],
        "states": [{"name": "mode", "values": [
            {"value": "view", "description": "d", "visibleElements": ["summary"]},
            {"value": "edit", "description": "d", "visibleElements": ["editor", "save_button"]},
            {"value": "gone", "description": "d", "visibleElements": ["nowhere"]},
            {"value": "bare", "description": "d"}]}]}
    if rows is not None:
        spec["branchContracts"]["methods"]["approve"]["branches"] = rows
    return spec


LAYOUT = {"type": "View", "id": "root", "child": [
    {"type": "Label", "id": "summary", "text": "@{title}", "hidden": "@{!isBusy}"},
    {"type": "View", "id": "editor"}, {"type": "Button", "id": "save_button"},
    {"type": "Collection", "id": "rows", "cellClasses": [{"className": "RowCell"}]}]}


def _project(tmp_path, spec, layout=LAYOUT):
    root = tcc._project(tmp_path, spec)
    if layout is not None:
        _write(root / "docs/screens/layouts/detail.json", layout)
    return root


ROWS = [
    {"when": {"api.setApproval": "default", "data.isBusy": True},
     "then": {"data.mode": "view", "data.status": "approved"}},
    {"when": {"api.setApproval": "error_409", "state.mode": "edit"},
     "then": {"data.isBusy": False, "data.banner": "conflict"}},
]


def _data(report, platform="web"):
    return tcc._screen_result(report, platform).data


class TestTheUnitsAndTheirColumns:
    def test_bool_and_enum_bound_by_the_layout(self, tmp_path):
        report = cc.run_coverage(_project(tmp_path, _screen_with_state(ROWS)))
        d = _data(report)
        assert d.evaluated, d.reason
        units = {(u["field"], u["value"]): (u["arranged"], u["produced"]) for u in d.units}
        assert units == {
            ("isBusy", True): (True, False), ("isBusy", False): (False, True),
            ("mode", "view"): (False, True), ("mode", "edit"): (True, False)}
        assert d.counts == {"units": 4, "fields": 2, "arranged": 2, "produced": 2, "neither": 0}

    def test_what_the_layout_cannot_show_is_counted_not_dropped(self, tmp_path):
        d = _data(cc.run_coverage(_project(tmp_path, _screen_with_state(ROWS))))
        # isHiddenFlag is Bool and bound nowhere; "gone" names an id the layout lacks.
        assert (d.bool_not_in_layout, d.visible_ids_not_in_layout, d.cells) == (1, 1, 1)

    def test_a_screen_without_a_linked_layout_is_not_evaluated(self, tmp_path):
        spec = _screen_with_state(ROWS)
        del spec["metadata"]["layoutFile"]
        d = _data(cc.run_coverage(_project(tmp_path, spec)))
        assert (d.evaluated, d.reason, d.units) == (False, "layout not linked", [])

    def test_an_unresolved_include_stops_the_screen(self, tmp_path):
        layout = copy.deepcopy(LAYOUT)
        layout["child"].append({"include": "missing_part", "id": "part"})
        d = _data(cc.run_coverage(_project(tmp_path, _screen_with_state(ROWS), layout)))
        assert (d.evaluated, d.unresolved_includes) == (False, 1)
        assert d.reason == "unresolved include: missing_part"


class TestReportOnly:
    def test_the_exit_and_every_count_are_the_same_with_and_without_the_layout(self, tmp_path):
        spec = _screen_with_state(ROWS)
        without = cc.run_coverage(_project(tmp_path / "a", spec, layout=None))
        with_ = cc.run_coverage(_project(tmp_path / "b", spec))
        assert without.exit == with_.exit
        for platform in ("web", "ios"):
            assert tcc._counts(tcc._screen_result(without, platform)) == \
                tcc._counts(tcc._screen_result(with_, platform))
        assert _data(without).reason == "layout file missing"

    def test_text_and_json_carry_it(self, tmp_path):
        report = cc.run_coverage(_project(tmp_path, _screen_with_state(ROWS)))
        text = "\n".join(cc.format_text(report))
        assert ("[platform=web] data (report only) units 4 · arranged 2 · produced 2 · "
                "neither 0 · screens evaluated 1 of 1") in text
        js = cc.to_json(report)
        web = next(p for p in js["platforms"] if p["platform"] == "web")
        assert web["data_totals"]["units"] == 4 and web["data_coarse"] is False
        assert web["screens"][0]["data"]["units_detail"][0]["field"] == "isBusy"


class TestTheCoarseSwitch:
    """The kill criterion (§6.1): the text reports fields, not values, when a
    MAJORITY of the block's screens carry more data units than statuses."""

    class _S:
        def __init__(self, units, required):
            self.data = da.ScreenData(evaluated=True,
                                      units=[{"field": f"f{i // 2}", "value": i % 2 == 0,
                                              "arranged": False, "produced": False}
                                             for i in range(units)])
            self.statuses_required = required

    def test_a_majority_turns_it_on(self):
        screens = [self._S(10, 2), self._S(10, 2), self._S(1, 5)]
        assert da.coarse(screens)
        # fields per screen, summed: 5 + 5 + 1 (the values stay in --json)
        assert "fields 11 (coarse" in da.text_line("web", screens)

    def test_exactly_half_does_not(self):
        assert not da.coarse([self._S(10, 2), self._S(1, 5)])

    def test_equal_is_not_more(self):
        assert not da.coarse([self._S(4, 4), self._S(4, 4), self._S(1, 5)])
