"""The cloud prices' daily fetch, viz's side (sources/cloud_prices.py; plan docs/plans/2026-10-20-jui-viz-backend-load-
and-cost-simulator.md, L-B2). The fetching is document_tools' (its own tests, test_infra_price_fetch.py); here a
fake runner stands for it, and nothing goes outside."""
from __future__ import annotations

import json

import pytest

from jui_cli.viz.sources import cloud_prices as C
from jui_cli.viz.state import SLICE_NAMES

DAY = 24 * 3_600_000


@pytest.fixture()
def mod():
    got = C.fetch_module()
    assert got is not None, "document_tools' infra.cost.fetch is reachable from a checkout"
    return got


def book(tmp_path, mod, setting=None, runner=None, now=lambda: 10 * DAY, started_long_ago=True):
    cfg = tmp_path / "config.json"
    if setting is not None:
        cfg.write_text(json.dumps({"weather": {"on": False}, "cloudPrices": setting}))
    calls = []

    def fake_run(setting, cache, at):
        calls.append((setting, at))
        index = {"version": 1, "lastRunAt": at, "files": {"azure/functions/japaneast.json": {
            "provider": "azure", "region": "japaneast", "source": "https://prices.azure.com/api/retail/prices?x",
            "fetchedAt": at, "effective": "2017-01-01", "rows": 2, "lastTryAt": at, "lastError": None}}}
        (cache).mkdir(parents=True, exist_ok=True)
        (cache / "index.json").write_text(json.dumps(index))
        return index
    b = C.CloudPricesBook(config_path=cfg, cache=tmp_path / "cloud-prices", status_path=tmp_path / "status.json",
                          mod=mod, runner=runner or fake_run, now=now)
    if started_long_ago:
        b.retry_at = 0   # the server's start delay is the next test's; the rest look at a server up for a while
    return b, calls


def test_on_by_default_and_fetched_at_once_when_nothing_was(tmp_path, mod):
    b, calls = book(tmp_path, mod)
    assert b.on and b.due()
    assert b.ask() and len(calls) == 1
    assert not b.due() and not b.ask()          # once a day
    view = b.view()
    assert view["on"] and view["lastOkAt"] == 10 * DAY and view["files"][0]["source"].startswith("https://prices.azure.com/")
    assert not any("price" in k for f in view["files"] for k in f)   # where from and when, never a price
    assert json.loads((tmp_path / "status.json").read_text())["lastOkAt"] == 10 * DAY
    assert b.source() == ("running", None)


def test_a_day_later_it_is_due_again(tmp_path, mod):
    now = {"t": 10 * DAY}
    b, calls = book(tmp_path, mod, now=lambda: now["t"])
    b.ask()
    now["t"] += DAY - 1
    assert not b.due()
    now["t"] += 1
    assert b.due() and b.ask() and len(calls) == 2


def test_off_by_the_setting_asks_nothing(tmp_path, mod):
    b, calls = book(tmp_path, mod, setting={"on": False})
    assert not b.on and not b.due() and not b.ask() and calls == []
    assert b.view() == {"on": False} and b.source() == ("off", None)


def test_the_setting_chooses_regions_and_large(tmp_path, mod):
    b, calls = book(tmp_path, mod, setting={"regions": {"aws": ["eu-west-1"], "azure": []}, "large": ["ec2"]})
    b.ask()
    assert calls[0][0]["regions"] == {"aws": ["eu-west-1"], "azure": []} and calls[0][0]["large"] == ["ec2"]


def test_a_run_that_cannot_start_is_the_sources_error_and_waits_an_hour(tmp_path, mod):
    def broken(setting, cache, at):
        raise OSError("disk full")
    now = {"t": 10 * DAY}
    b, _ = book(tmp_path, mod, runner=broken, now=lambda: now["t"])
    assert b.ask() and b.source()[0] == "degraded" and "disk full" in b.view()["error"]
    now["t"] += C.RETRY_MS - 1
    assert not b.due()
    now["t"] += 1
    assert b.due()


def test_failing_files_degrade_the_source(tmp_path, mod):
    def partly(setting, cache, at):
        return {"version": 1, "lastRunAt": at, "files": {"a.json": {"fetchedAt": 1, "lastError": "OSError: x"}}}
    b, _ = book(tmp_path, mod, runner=partly)
    b.ask()
    status, error = b.source()
    assert status == "degraded" and "1 件" in error


def test_save_on_keeps_the_other_keys(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"weather": {"on": True, "lat": 1.0, "lon": 2.0}, "cloudPrices": {"large": ["rds"]}}))
    C.save_on(False, cfg)
    data = json.loads(cfg.read_text())
    assert data["cloudPrices"] == {"large": ["rds"], "on": False} and data["weather"]["lat"] == 1.0


def test_the_cache_is_where_the_price_book_looks(tmp_path, monkeypatch, mod):
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path / "vh"))
    from jui_cli.core.document_tools_import import load_document_tools_module
    pricebook, _ = load_document_tools_module("infra.cost.pricebook")
    assert C.cache_dir() == pricebook.cache_dir()


def test_the_slice_is_named():
    assert "cloudPrices" in SLICE_NAMES


def test_without_document_tools_nothing_is_fetched(tmp_path):
    b = C.CloudPricesBook(config_path=tmp_path / "c.json", cache=tmp_path / "cp", status_path=tmp_path / "s.json",
                          mod=None, runner=None)
    b.mod = None
    b.setting = {"on": False, "unavailable": True}
    assert not b.due() and b.view() == {"on": False, "unavailable": True} and b.source()[0] == "stopped"


def test_the_first_run_waits_after_the_server_starts(tmp_path, mod):
    now = {"t": 5 * DAY}
    b, calls = book(tmp_path, mod, now=lambda: now["t"], started_long_ago=False)
    assert b.on and not b.due()                  # a server started for a moment goes nowhere
    now["t"] += C.FIRST_DELAY_MS - 1
    assert not b.due()
    now["t"] += 1
    assert b.due() and b.ask() and len(calls) == 1


def test_the_e2e_build_never_fetches(tmp_path, mod, monkeypatch):
    monkeypatch.setenv("JUI_VIZ_E2E", "1")
    b, calls = book(tmp_path, mod)
    assert not b.on and not b.ask() and calls == []
