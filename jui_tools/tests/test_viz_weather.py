"""The near weather (requester, 10-18: "天気はリアルな近所の天気を出したい"; ruling: only when turned on).

What must hold (the ticket's rules, fixed before the code):
- off by default, and then no connection leaves the server at all;
- the position is rounded to two decimals (about 1 km) before it is stored or sent; the unrounded one never is;
- one query every 30 minutes while on; a failure is the source's error, never the server's;
- turning it off removes the position and stops the queries;
- no coordinate in the slice (slices go into the snapshot and the export) nor in the doctor's status file.

The server-side arm counts connections with a sitecustomize in the real `jui viz serve` process: it records every
socket connect and every name lookup. Its control is the same server turned on against a stand-in for Open-Meteo on
127.0.0.1: that connection must show in the same record, so a record with nothing in it means "nothing connected",
not "the counter was not there".
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from aiohttp import ClientSession

from jui_cli.viz.sources import weather as W

JUI = Path(__file__).resolve().parents[1] / "bin" / "jui"
LAT, LON = 35.681236, 139.767125                # unrounded: must never be stored nor sent
RLAT, RLON = 35.68, 139.77
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")


# ---------------------------------------------------------------- the pieces

def test_coordinates_are_rounded_to_about_one_kilometre():
    assert W.round_coord(LAT, 90) == RLAT and W.round_coord(LON, 180) == RLON
    assert W.round_coord(-33.86785, 90) == -33.87
    for bad in (None, "35.6", True, float("nan"), 91, -181):
        assert W.round_coord(bad, 90 if bad != -181 else 180) is None


def test_the_setting_is_stored_rounded_and_removed_when_off(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"port": 7790, "askWaitSec": 25}))
    saved = W.save_setting(True, LAT, LON, cfg)
    assert saved == {"on": True, "lat": RLAT, "lon": RLON}
    text = cfg.read_text()
    assert "35.681" not in text and "139.767" not in text
    data = json.loads(text)
    assert data["port"] == 7790 and data["askWaitSec"] == 25                 # the other keys are kept
    assert data["weather"] == {"on": True, "lat": RLAT, "lon": RLON}
    assert oct(cfg.stat().st_mode & 0o777) == "0o600"
    assert W.save_setting(False, path=cfg) == {"on": False, "lat": None, "lon": None}
    assert json.loads(cfg.read_text())["weather"] == {"on": False}             # the position is gone
    with pytest.raises(ValueError):
        W.save_setting(True, "x", LON, cfg)


def test_a_hand_written_setting_is_read_rounded_and_on_only_with_both_coordinates(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"weather": {"on": True, "lat": LAT, "lon": LON}}))
    assert W.load_setting(cfg) == {"on": True, "lat": RLAT, "lon": RLON}
    cfg.write_text(json.dumps({"weather": {"on": True, "lat": LAT}}))
    assert W.load_setting(cfg) == {"on": False, "lat": None, "lon": None}
    cfg.write_text("not json")
    assert W.load_setting(cfg)["on"] is False


def test_the_query_carries_the_rounded_position_only(monkeypatch):
    monkeypatch.delenv(W.URL_ENV, raising=False)
    url = W.query_url(W.round_coord(LAT, 90), W.round_coord(LON, 180))
    assert url.startswith("https://api.open-meteo.com/v1/forecast?")
    assert "latitude=35.68&" in url and "longitude=139.77&" in url and "35.681" not in url
    monkeypatch.setenv(W.URL_ENV, "http://127.0.0.1:9/x")
    assert W.query_url(RLAT, RLON).startswith("https://api.open-meteo.com/")  # the stand-in needs the e2e build
    monkeypatch.setenv("JUI_VIZ_E2E", "1")
    assert W.query_url(RLAT, RLON).startswith("http://127.0.0.1:9/x?")


def test_weather_codes_map_to_six_kinds():
    want = {0: "clear", 1: "clear", 2: "cloudy", 3: "cloudy", 45: "fog", 48: "fog", 51: "rain", 61: "rain", 67: "rain",
            80: "rain", 82: "rain", 71: "snow", 77: "snow", 85: "snow", 86: "snow", 95: "thunder", 99: "thunder"}
    assert {c: W.kind_of(c) for c in want} == want
    assert W.kind_of(4) is None and W.kind_of(True) is None and W.kind_of("0") is None
    got = W.parse({"current": {"weather_code": 63, "temperature_2m": 12.4, "is_day": 0, "cloud_cover": 90}})
    assert got == {"kind": "rain", "isDay": False, "tempC": 12.4, "precipitation": None, "cloud": 90.0}
    with pytest.raises(ValueError):
        W.parse({"current": {"weather_code": 4}})


class _Clock:
    def __init__(self, t=1_800_000_000_000):
        self.t = t

    def __call__(self):
        return self.t


def _book(tmp_path, fetcher, clock):
    return W.WeatherBook(tmp_path / "config.json", tmp_path / "weather-status.json", fetcher=fetcher, now=clock)


def test_off_asks_nobody(tmp_path):
    calls = []
    clock = _Clock()
    book = _book(tmp_path, lambda lat, lon: calls.append((lat, lon)) or {}, clock)
    for _ in range(3):
        assert book.ask() is False
        clock.t += W.QUERY_EVERY_MS * 2
    assert calls == [] and book.view() == {"on": False} and book.source() == ("off", None)
    book.set(True, LAT, LON)
    book.set(False)
    clock.t += W.QUERY_EVERY_MS * 2
    assert book.ask() is False and calls == []                                # off again: still nobody


def test_on_asks_at_once_then_every_thirty_minutes_with_the_rounded_position(tmp_path):
    calls = []
    clock = _Clock()

    def fetcher(lat, lon):
        calls.append((lat, lon))
        return {"kind": "clear", "isDay": True, "tempC": 20.0, "precipitation": 0.0, "cloud": 5.0}
    book = _book(tmp_path, fetcher, clock)
    book.set(True, LAT, LON)
    assert book.ask() is True and calls == [(RLAT, RLON)]
    clock.t += W.QUERY_EVERY_MS - 1
    assert book.ask() is False and len(calls) == 1
    clock.t += 1
    assert book.ask() is True and len(calls) == 2
    view = book.view()
    assert view["kind"] == "clear" and view["at"] == clock.t and "lat" not in view and "lon" not in view
    assert "35.6" not in json.dumps(view) and "139.7" not in json.dumps(view)
    status = json.loads((tmp_path / "weather-status.json").read_text())
    assert status["on"] is True and status["lastOkAt"] == clock.t and "35.6" not in json.dumps(status)


def test_a_failure_keeps_the_last_answer_for_three_hours_then_the_season_alone(tmp_path):
    clock = _Clock()
    answers = [{"kind": "rain", "isDay": True, "tempC": 9.0, "precipitation": 1.2, "cloud": 100.0}]

    def fetcher(lat, lon):
        if answers:
            return answers.pop()
        raise OSError("network is unreachable")
    book = _book(tmp_path, fetcher, clock)
    book.set(True, LAT, LON)
    book.ask()
    first = clock.t
    clock.t += W.QUERY_EVERY_MS
    book.ask()
    assert book.source()[0] == "degraded" and "OSError" in book.source()[1]
    view = book.view()
    assert view["kind"] == "rain" and view["stale"] is True and view["at"] == first and "OSError" in view["error"]
    clock.t = first + W.STALE_AFTER_MS
    view = book.view()
    assert "kind" not in view and view["on"] is True                          # too old: the season alone
    status = json.loads((tmp_path / "weather-status.json").read_text())
    assert status["lastOkAt"] == first and "OSError" in status["lastError"]


def test_an_answer_that_comes_back_after_off_or_a_move_is_dropped(tmp_path):
    """reported 10-18: the query runs on an executor thread; turned off meanwhile, its answer used to land in last and the
    status file's lastOkAt."""
    clock = _Clock()
    book = None
    answer = {"kind": "clear", "isDay": True, "tempC": 20.0, "precipitation": 0.0, "cloud": 0.0}
    status = tmp_path / "weather-status.json"

    def turned_off_meanwhile(lat, lon):
        book.set(False)
        return answer
    book = _book(tmp_path, turned_off_meanwhile, clock)
    book.set(True, LAT, LON)
    assert book.ask() is False
    assert book.last is None and json.loads(status.read_text())["lastOkAt"] is None and book.view() == {"on": False}

    def failed_after_off(lat, lon):
        book.set(False)
        raise OSError("late")
    book.fetcher = failed_after_off
    book.set(True, LAT, LON)
    assert book.ask() is False and book.error is None and json.loads(status.read_text())["lastError"] is None

    def moved_meanwhile(lat, lon):
        book.set(True, 34.69, 135.5)
        return answer
    book.fetcher = moved_meanwhile
    book.set(True, LAT, LON)
    assert book.ask() is False and book.last is None and book.due()            # the new place is asked next
    book.fetcher = lambda lat, lon: answer
    assert book.ask() is True and book.last["kind"] == "clear" and json.loads(status.read_text())["lastOkAt"] == clock.t


# ---------------------------------------------------------------- the real server

SITECUSTOMIZE = '''
import os, socket
_log = os.environ["JUI_TEST_NET_LOG"]
def _w(line):
    with open(_log, "a") as f:
        f.write(line + "\\n")
_w(f"loaded {os.getpid()}")
_connect = socket.socket.connect
def connect(self, address):
    _w(f"connect {address!r}")
    return _connect(self, address)
socket.socket.connect = connect
_gai = socket.getaddrinfo
def getaddrinfo(host, *a, **k):
    _w(f"resolve {host!r}")
    return _gai(host, *a, **k)
socket.getaddrinfo = getaddrinfo
# This file shadows the interpreter's own sitecustomize (Homebrew's adds its site-packages: without it the server
# cannot import aiohttp, e1 10-18). Find the one it hid, later on sys.path, and run it as it would have run.
import importlib.util, sys
_here = os.path.dirname(os.path.abspath(__file__))
for _d in sys.path:
    _p = os.path.join(os.path.abspath(_d or "."), "sitecustomize.py")
    if os.path.dirname(_p) != _here and os.path.isfile(_p):
        _spec = importlib.util.spec_from_file_location("_hidden_sitecustomize", _p)
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))
        break
'''
LOOPBACK = ("127.0.0.1", "::1", "localhost")


class _OpenMeteo:
    """A stand-in for Open-Meteo on 127.0.0.1: records each query, answers rain (or 500 when told)."""

    def __init__(self, status=200):
        self.queries: list[str] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                outer.queries.append(self.path)
                body = json.dumps({"current": {"weather_code": 63, "temperature_2m": 11.5, "is_day": 1,
                                               "precipitation": 0.8, "cloud_cover": 100}}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass
        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(tmp_path: Path, port: int, extra_env: dict | None = None) -> tuple[subprocess.Popen, Path]:
    site = tmp_path / "site"
    site.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(SITECUSTOMIZE)
    log = tmp_path / "net.log"
    env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env.update(HOME=str(tmp_path), PYTHONUNBUFFERED="1", PYTHONPATH=str(site), JUI_TEST_NET_LOG=str(log), **(extra_env or {}))
    proc = subprocess.Popen([sys.executable, str(JUI), "viz", "serve", "--port", str(port), "--no-agents-poll"],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    server_json = tmp_path / ".local" / "state" / "jui-viz" / "server.json"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not server_json.exists():
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    if not server_json.exists():
        proc.kill()
        out, err = proc.communicate()
        raise AssertionError(f"serve did not start: {out}\n{err}")
    return proc, log


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()  # our own child
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    proc.communicate()


def _outbound(log: Path, pid: int) -> tuple[list[str], list[str]]:
    """(lines of the server process, the ones that left this machine)."""
    lines, mine = log.read_text().splitlines() if log.exists() else [], []
    # each process writes "loaded <pid>" first; keep the server's own lines (children of it load the hook too)
    current = None
    for line in lines:
        if line.startswith("loaded "):
            current = int(line.split()[1])
            continue
        if current == pid:
            mine.append(line)
    away = [x for x in mine if not any(f"'{h}'" in x for h in LOOPBACK) and not x.startswith("resolve None")]
    return mine, away


async def _ws(port: int, token: str, *messages: dict) -> list[dict]:
    """Auth, then each message; returns the acks (and the last snapshot's weather slice as {'weather': …})."""
    out = []
    async with ClientSession() as s:
        async with s.ws_connect(f"http://127.0.0.1:{port}/ws", headers={"Origin": f"http://127.0.0.1:{port}"}) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "token": token})
            for msg in messages:
                await ws.send_json(msg)
                while True:
                    got = await ws.receive_json(timeout=10)
                    if got.get("type") == "snapshot":
                        out.append({"weather": got.get("slices", {}).get("weather")})
                    if got.get("type") == "ack" and got.get("reqId") == msg.get("reqId"):
                        out.append(got)
                        break
    return out


def _token(tmp_path: Path) -> str:
    return json.loads((tmp_path / ".local" / "state" / "jui-viz" / "server.json").read_text())["token"]


def test_off_by_default_the_server_connects_to_nobody(tmp_path):
    port = _free_port()
    proc, log = _serve(tmp_path, port)
    try:
        time.sleep(4)                                                       # several ticks of every loop
        got = asyncio.run(_ws(port, _token(tmp_path), {"type": "snapshot.get", "reqId": "s1"}))
    finally:
        _stop(proc)
    mine, away = _outbound(log, proc.pid)
    assert log.exists() and f"loaded {proc.pid}" in log.read_text()          # the counter was in the server
    assert away == [], away
    assert got[0]["weather"] == {"on": False}
    status = json.loads((tmp_path / ".local" / "state" / "jui-viz" / "weather-status.json").read_text())
    assert status["on"] is False and status["lastTryAt"] is None


def test_turned_on_it_asks_once_with_the_rounded_position_and_off_stops_it(tmp_path):
    meteo = _OpenMeteo()
    port = _free_port()
    proc, log = _serve(tmp_path, port, {"JUI_VIZ_E2E": "1", W.URL_ENV: f"http://127.0.0.1:{meteo.port}/v1/forecast"})
    cfg = tmp_path / ".local" / "state" / "jui-viz" / "config.json"
    try:
        token = _token(tmp_path)
        acks = asyncio.run(_ws(port, token, {"type": "weather.set", "reqId": "w1", "on": True, "lat": LAT, "lon": LON}))
        assert acks[-1]["ok"] is True
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not meteo.queries:
            time.sleep(0.1)
        assert len(meteo.queries) == 1
        q = meteo.queries[0]
        assert "latitude=35.68&" in q and "longitude=139.77&" in q and "35.681" not in q and "139.767" not in q
        assert "35.681" not in cfg.read_text() and json.loads(cfg.read_text())["weather"]["lat"] == RLAT
        time.sleep(1.5)
        snap = asyncio.run(_ws(port, token, {"type": "snapshot.get", "reqId": "s1"}))[0]["weather"]
        assert snap["on"] is True and snap["kind"] == "rain" and snap["tempC"] == 11.5
        assert "lat" not in snap and "35.6" not in json.dumps(snap)
        time.sleep(2)
        assert len(meteo.queries) == 1                                        # not again before 30 minutes
        acks = asyncio.run(_ws(port, token, {"type": "weather.set", "reqId": "w2", "on": False}))
        assert acks[-1]["ok"] is True
        assert json.loads(cfg.read_text())["weather"] == {"on": False}
        time.sleep(2)
        assert len(meteo.queries) == 1
    finally:
        _stop(proc)
        meteo.close()
    mine, away = _outbound(log, proc.pid)
    assert any(f"'127.0.0.1', {meteo.port}" in x for x in mine), mine        # the control: the counter saw the query
    assert away == [], away


def test_a_failing_answer_is_the_sources_error_and_the_server_stays_up(tmp_path):
    meteo = _OpenMeteo(status=500)
    port = _free_port()
    proc, _ = _serve(tmp_path, port, {"JUI_VIZ_E2E": "1", W.URL_ENV: f"http://127.0.0.1:{meteo.port}/v1/forecast"})
    try:
        token = _token(tmp_path)
        asyncio.run(_ws(port, token, {"type": "weather.set", "reqId": "w1", "on": True, "lat": LAT, "lon": LON}))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not meteo.queries:
            time.sleep(0.1)
        time.sleep(1.5)
        assert proc.poll() is None
        snap = asyncio.run(_ws(port, token, {"type": "snapshot.get", "reqId": "s1"}))[0]["weather"]
        assert snap["on"] is True and "kind" not in snap and "HTTPError" in snap["error"]
        status = json.loads((tmp_path / ".local" / "state" / "jui-viz" / "weather-status.json").read_text())
        assert status["lastOkAt"] is None and "HTTPError" in status["lastError"]
    finally:
        _stop(proc)
        meteo.close()


def test_doctor_says_whether_it_is_on_and_when_it_last_worked(tmp_path, monkeypatch):
    for k in ISOLATE:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    from jui_cli.commands import viz_cmd
    line = next(c for c in viz_cmd._doctor_checks() if c["name"] == "weather")
    assert line["ok"] is True and "オフ" in line["detail"]
    W.save_setting(True, LAT, LON)
    W._write_json(W.status_json(), {"on": True, "lastOkAt": None, "lastTryAt": 1, "lastError": "天気を取れません（OSError: x）"})
    line = next(c for c in viz_cmd._doctor_checks() if c["name"] == "weather")
    assert line["ok"] is False and "オン" in line["detail"] and "OSError" in line["detail"] and "35.6" not in line["detail"]
