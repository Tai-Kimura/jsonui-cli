"""The weather near this machine, for the building's outside (requester, 10-18: "天気はリアルな近所の天気を出したい").

Off by default, and then this module makes no connection at all: the requester's ruling was "設定で有効にしたときだけ",
and plan/02-architecture.md keeps viz offline otherwise. It is turned on from the page: the browser asks for the
position (the Geolocation permission dialog, only inside the switch's click), rounds it to two decimals (about 1 km)
and sends that; this module rounds again, so an unrounded coordinate is never stored nor sent.

Where things are:
  * the setting: ``config.json`` in viz_home, key ``weather`` = ``{"on": true, "lat": 35.68, "lon": 139.77}``. The
    other keys of the file are kept. Turning it off removes the coordinates.
  * the status for ``jui viz doctor``: ``weather-status.json`` in viz_home — on or off, the last success, the last
    failure. Never a coordinate.
  * the page sees the ``weather`` slice: on, the kind of weather, day or night, the temperature, when it was read.
    Never a coordinate either: slices go into the snapshot and the export.

The server asks Open-Meteo (no key) once every QUERY_EVERY_MS while on, and once at once when it is turned on. A
failure is the source's error only: the last answer is used for up to STALE_AFTER_MS, then the outside shows the
season alone.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from .. import paths

URL = "https://api.open-meteo.com/v1/forecast"
URL_ENV = "JUI_VIZ_WEATHER_URL"   # the e2e build only (JUI_VIZ_E2E=1): a stand-in for Open-Meteo on 127.0.0.1
CURRENT = "weather_code,temperature_2m,precipitation,cloud_cover,is_day"
QUERY_EVERY_MS = 30 * 60_000
STALE_AFTER_MS = 3 * 3_600_000
TIMEOUT_SEC = 5
DECIMALS = 2                      # about 1.1 km of latitude
KINDS = ("clear", "cloudy", "fog", "rain", "snow", "thunder")


def round_coord(value, limit: float) -> float | None:
    """A latitude (limit 90) or longitude (limit 180) rounded to DECIMALS, or None when it is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    if v != v or abs(v) > limit:
        return None
    return round(v, DECIMALS)


def kind_of(code) -> str | None:
    """A WMO weather code (Open-Meteo's weather_code) -> one of KINDS."""
    if isinstance(code, bool) or not isinstance(code, (int, float)):
        return None
    c = int(code)
    if c in (0, 1):
        return "clear"
    if c in (2, 3):
        return "cloudy"
    if c in (45, 48):
        return "fog"
    if 51 <= c <= 67 or 80 <= c <= 82:
        return "rain"
    if 71 <= c <= 77 or c in (85, 86):
        return "snow"
    if 95 <= c <= 99:
        return "thunder"
    return None


# ---------------------------------------------------------------- the setting (config.json)

def _read_config(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    """Temp file + os.replace, mode 0600 (the files in viz_home are the user's own)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def load_setting(path: Path | None = None) -> dict:
    """{"on": bool, "lat": float | None, "lon": float | None} from config.json; on only with both coordinates."""
    raw = _read_config(path or paths.config_json()).get("weather")
    raw = raw if isinstance(raw, dict) else {}
    lat, lon = round_coord(raw.get("lat"), 90), round_coord(raw.get("lon"), 180)
    on = raw.get("on") is True and lat is not None and lon is not None
    return {"on": on, "lat": lat if on else None, "lon": lon if on else None}


def save_setting(on: bool, lat=None, lon=None, path: Path | None = None) -> dict:
    """Turn it on (rounded coordinates) or off (the coordinates removed). Returns what was saved."""
    path = path or paths.config_json()
    data = _read_config(path)
    if on:
        rlat, rlon = round_coord(lat, 90), round_coord(lon, 180)
        if rlat is None or rlon is None:
            raise ValueError("緯度と経度が数ではありません")
        data["weather"] = {"on": True, "lat": rlat, "lon": rlon}
    else:
        data["weather"] = {"on": False}
    _write_json(path, data)
    return load_setting(path)


def status_json() -> Path:
    return paths.viz_home() / "weather-status.json"


def read_status(path: Path | None = None) -> dict:
    data = _read_config(path or status_json())
    return data


# ---------------------------------------------------------------- one query

def query_url(lat: float, lon: float) -> str:
    base = URL
    override = os.environ.get(URL_ENV, "")
    if override and os.environ.get("JUI_VIZ_E2E") == "1":
        base = override
    params = {"latitude": f"{lat:.{DECIMALS}f}", "longitude": f"{lon:.{DECIMALS}f}", "current": CURRENT}
    return f"{base}?{urllib.parse.urlencode(params)}"


def fetch(lat: float, lon: float, timeout: float = TIMEOUT_SEC) -> dict:
    """Ask Open-Meteo once. Raises on a network error, a bad status or an answer without a known weather code."""
    req = urllib.request.Request(query_url(lat, lon), headers={"User-Agent": "jui-viz"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - a fixed https URL (or the e2e stand-in)
        body = json.loads(resp.read(65_536).decode("utf-8"))
    return parse(body)


def parse(body) -> dict:
    cur = body.get("current") if isinstance(body, dict) else None
    if not isinstance(cur, dict):
        raise ValueError("応答に current がありません")
    kind = kind_of(cur.get("weather_code"))
    if kind is None:
        raise ValueError(f"知らない天気のコード {cur.get('weather_code')!r}")
    num = lambda v: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None  # noqa: E731
    return {"kind": kind, "isDay": cur.get("is_day") != 0, "tempC": num(cur.get("temperature_2m")),
            "precipitation": num(cur.get("precipitation")), "cloud": num(cur.get("cloud_cover"))}


# ---------------------------------------------------------------- the server's side

class WeatherBook:
    """The setting, the last answer and when to ask next. ``fetcher`` and ``now`` are replaceable for the arms."""

    def __init__(self, config_path: Path | None = None, status_path: Path | None = None,
                 fetcher: Callable[[float, float], dict] = fetch, now: Callable[[], int] | None = None) -> None:
        self.config_path, self.status_path = config_path, status_path
        self.fetcher = fetcher
        self.now = now or (lambda: int(time.time() * 1000))
        self.setting = load_setting(config_path)
        self.last: dict | None = None        # the last answer, with "at" (when it was read)
        self.error: str | None = None
        self.next_at = 0                     # 0: ask at the next chance
        self.tried = 0
        self._write_status()

    @property
    def on(self) -> bool:
        return self.setting["on"]

    def set(self, on: bool, lat=None, lon=None) -> dict:
        """From the page's switch. On: rounded coordinates saved, asked at once. Off: removed, never asked."""
        self.setting = save_setting(on, lat, lon, self.config_path)
        self.last, self.error, self.next_at = None, None, 0
        self._write_status()
        return self.setting

    def due(self) -> bool:
        return self.on and self.now() >= self.next_at

    def ask(self) -> bool:
        """One query when it is due (call from an executor: it blocks for up to TIMEOUT_SEC). True when it changed."""
        if not self.due():
            return False
        lat, lon = self.setting["lat"], self.setting["lon"]
        at = self.now()
        self.tried, self.next_at = at, at + QUERY_EVERY_MS
        try:
            got = self.fetcher(lat, lon)
        except Exception as exc:  # noqa: BLE001 - any failure is the source's error, never the server's
            self.error = f"天気を取れません（{type(exc).__name__}: {str(exc)[:120]}）"
        else:
            self.last, self.error = {**got, "at": at}, None
        self._write_status()
        return True

    def view(self) -> dict:
        """The weather slice: never a coordinate."""
        if not self.on:
            return {"on": False}
        last = self.last if self.last and self.now() - self.last["at"] < STALE_AFTER_MS else None
        out = {"on": True, "error": self.error} if self.error else {"on": True}
        if last:
            out.update(kind=last["kind"], isDay=last["isDay"], tempC=last["tempC"], at=last["at"],
                       stale=self.error is not None)
        return out

    def source(self) -> tuple[str, str | None]:
        """(status, error) for the server slice's sources."""
        if not self.on:
            return "off", None
        if self.error:
            return "degraded", self.error
        return "running", None

    def _write_status(self) -> None:
        try:
            _write_json(self.status_path or status_json(), {
                "on": self.on, "lastOkAt": self.last["at"] if self.last else None,
                "lastTryAt": self.tried or None, "lastError": self.error})
        except OSError:
            pass
