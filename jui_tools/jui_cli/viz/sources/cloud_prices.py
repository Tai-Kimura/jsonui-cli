"""The cloud prices the cost simulator reads, fetched once a day (plan docs/plans/2026-10-20-jui-viz-backend-load-and-
cost-simulator.md, L-B2; the requester's ruling 1: 「外部通信既定でいいよ」, on by default, off by the setting).

The fetching itself is document_tools' ``infra.cost.fetch`` (reached as the server room's reader is, through
core/document_tools_import): AWS's offer files and Azure Retail Prices, no key, https to those two hosts only, each
answer capped, written as infra-prices.v0 files under <viz home>/cloud-prices with an index of where each came from
and when. This module is viz's side of it, in weather.py's shape:
  * the setting: ``config.json`` in viz_home, key ``cloudPrices`` = ``{"on": false}`` to turn it off; ``regions``
    (``{"aws": [...], "azure": [...]}``) and ``large`` (``["ec2", "rds"]``) to choose more. Absent: on, the defaults;
  * once a day the server fetches (in a thread of its own: a slow answer never holds it, nor its stopping); the first
    run waits FIRST_DELAY_MS after the server starts, for the load and the hosts' sake (a server started for a moment,
    a quick look, does not download); the e2e build (JUI_VIZ_E2E=1) never fetches. Where viz may connect by default is
    a closed list, the price hosts only, and its gate holds with no delay at all (tests/test_viz_weather.py);
  * the status for ``jui viz doctor``: ``cloud-prices-status.json`` in viz_home;
  * the page sees the ``cloudPrices`` slice: on, when the prices were last fetched, and per file its source, when it
    was fetched, its effective date and its last error — the "where from, and when" the cost view shows.
A failure leaves the last files as they are: the price book goes on with the last prices fetched.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from .. import i18n, paths
from . import weather as W   # config.json's reading and writing (one place for the file's form)

KEY = "cloudPrices"
RETRY_MS = 3_600_000             # a run that could not start at all is tried again in an hour
FIRST_DELAY_MS = 10 * 60_000     # after the server starts (the price book uses the last fetch or the bundled table)
DELAY_ENV = "JUI_VIZ_CLOUD_PRICES_DELAY_MS"   # the outbound gate's server starts with 0 (tests/test_viz_weather.py)


def first_delay_ms() -> int:
    raw = os.environ.get(DELAY_ENV, "")
    return int(raw) if raw.isdigit() else FIRST_DELAY_MS


def fetch_module():
    """document_tools' infra.cost.fetch, or None when document_tools cannot be reached."""
    from ...core.document_tools_import import load_document_tools_module
    mod, _where = load_document_tools_module("infra.cost.fetch")
    return mod


def cache_dir() -> Path:
    """<viz home>/cloud-prices: where the price book looks (infra/cost/pricebook.cache_dir)."""
    return paths.viz_home() / "cloud-prices"


def status_json() -> Path:
    return paths.viz_home() / "cloud-prices-status.json"


def load_setting(path: Path | None = None, mod=None) -> dict:
    mod = mod or fetch_module()
    raw = W._read_config(path or paths.config_json()).get(KEY)
    if mod is None:
        return {"on": False, "regions": {}, "large": [], "unavailable": True}
    got = mod.setting_of(raw)
    if os.environ.get("JUI_VIZ_E2E") == "1":
        got = {**got, "on": False, "e2e": True}   # the browser tests' server goes nowhere
    return got


def save_on(on: bool, path: Path | None = None) -> None:
    """Turn the fetching on or off; the other keys (regions, large) are kept."""
    path = path or paths.config_json()
    data = W._read_config(path)
    entry = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
    entry["on"] = bool(on)
    data[KEY] = entry
    W._write_json(path, data)


class CloudPricesBook:
    """The setting, the index and when to fetch next. ``runner`` and ``now`` are replaceable for the arms."""

    def __init__(self, config_path: Path | None = None, cache: Path | None = None, status_path: Path | None = None,
                 mod=None, runner: Callable | None = None, now: Callable[[], int] | None = None) -> None:
        self.mod = mod or fetch_module()
        self.config_path, self.cache, self.status_path = config_path, cache or cache_dir(), status_path
        self.now = now or (lambda: int(time.time() * 1000))
        self.runner = runner or (self.mod.run if self.mod else None)
        self.setting = load_setting(config_path, self.mod) if self.mod else {"on": False, "unavailable": True}
        self.index = self.mod.read_index(self.cache) if self.mod else {"files": {}}
        self.error: str | None = None
        self.retry_at = self.now() + first_delay_ms()
        self._write_status()

    @property
    def on(self) -> bool:
        return bool(self.setting.get("on")) and self.mod is not None

    def due(self) -> bool:
        return self.on and self.now() >= self.retry_at and self.mod.due(self.index, self.now())

    def ask(self) -> bool:
        """One run when it is due (call from an executor: it blocks while it fetches). True when it ran."""
        if not self.due():
            return False
        at = self.now()
        try:
            self.index, self.error = self.runner(self.setting, self.cache, at), None
        except Exception as exc:  # noqa: BLE001 - the run could not start (the disk, document_tools): the source's error
            self.error, self.retry_at = f"{type(exc).__name__}: {str(exc)[:160]}", at + RETRY_MS
        self._write_status()
        return True

    def view(self) -> dict:
        """The cloudPrices slice: never a price, only where the prices came from and when."""
        if not self.on:
            return {"on": False, **({"unavailable": True} if self.mod is None else {})}
        out = {"on": True, **self.mod.summary(self.index)}
        if self.error:
            out["error"] = self.error
        return out

    def source(self) -> tuple[str, str | None]:
        """(status, error) for the server slice's sources."""
        if self.mod is None:
            return "stopped", i18n.tl("srv.prices.no_tools")
        if not self.on:
            return "off", None
        failing = self.mod.summary(self.index)["failing"]
        if self.error:
            return "degraded", self.error
        if failing:
            return "degraded", i18n.tl("srv.prices.failing", n=failing)
        return "running", None

    def _write_status(self) -> None:
        summary = self.mod.summary(self.index) if self.mod else {}
        try:
            W._write_json(self.status_path or status_json(), {
                "on": self.on, "lastOkAt": summary.get("lastOkAt"), "lastRunAt": summary.get("lastRunAt"),
                "failing": summary.get("failing"), "lastError": self.error})
        except OSError:
            pass
