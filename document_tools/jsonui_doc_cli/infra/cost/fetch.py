"""The prices fetched (plan L-B2): AWS's Price List offer files and Azure Retail Prices, both without a key, turned into
infra-prices.v0 files in the cache the price book reads (pricebook.cache_dir: <viz home>/cloud-prices), one file per
provider, offer (or Azure service) and region, with an index of where each came from and when.

On by default (the requester's ruling 1: 「外部通信既定でいいよ」), off by the setting. What is fetched:
  * AWS: the small offers the rules read (aws_offers.regional_spec without RDS; CloudFront once, global) for the
    setting's regions; RDS (30 MB) and EC2 (289 MB as CSV, read a line at a time) only when the setting's ``large``
    names them;
  * Azure: the services azure_prices.SPEC maps, one query per service and region, page by page.
The rules for going outside are viz's: https only, to these two hosts only (redirects too), a timeout, a size cap per
answer, only a User-Agent sent — the URL holds an offer code or a service name and a region, nothing of the model.
What is written is a price file like a person's: read back through prices.read_file (the schema, and the shapes of
secrets over every string) before it replaces the last one. A failure leaves the last file as it was (the last price
fetched stays in use) and says why in the index; one failure stops nothing else.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Iterable

from .. import prices as P
from . import aws_offers as AWS
from . import azure_prices as AZ

HOSTS = ("pricing.us-east-1.amazonaws.com", "prices.azure.com")
TIMEOUT_SEC = 20
MB = 1024 * 1024
LIMIT = {"offer": 16 * MB, "rds": 64 * MB, "azure_page": 2 * MB, "ec2_csv": 400 * MB}
AZURE_PAGES = 20
DEFAULT_REGIONS = {"aws": ("ap-northeast-1", "us-east-1"), "azure": ("japaneast", "eastus")}
LARGE = ("ec2", "rds")
SMALL_LEFT_OUT = ("AmazonRDS",)          # the regional spec's offers that are large: fetched only when chosen
INDEX = "index.json"
EVERY_MS = 24 * 3_600_000                # once a day
_REGION = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


# ---------------------------------------------------------------- the setting

def setting_of(raw) -> dict:
    """{"on", "regions": {provider: [...]}, "large": [...]} from what the config holds; anything unreadable is the
    default (on, the default regions, nothing large)."""
    raw = raw if isinstance(raw, dict) else {}
    regions = {}
    given = raw.get("regions") if isinstance(raw.get("regions"), dict) else {}
    for provider, default in DEFAULT_REGIONS.items():
        got = given.get(provider)
        ok = [r for r in got if isinstance(r, str) and _REGION.match(r)] if isinstance(got, list) else None
        regions[provider] = list(dict.fromkeys(ok)) if ok is not None else list(default)
    large = [x for x in raw.get("large", []) if x in LARGE] if isinstance(raw.get("large"), list) else []
    return {"on": raw.get("on") is not False, "regions": regions, "large": sorted(set(large))}


# ---------------------------------------------------------------- what to fetch

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def targets(setting: dict, provider: str | None = None, region: str | None = None) -> list[dict]:
    """Each file to fetch: provider, kind (offer / azure / ec2_csv), the url, the region, the cache path, the limit."""
    out = []
    aws_regions = [r for r in setting["regions"]["aws"] if region in (None, r)]
    offers: dict[str, list[dict]] = {}
    for s in AWS.regional_spec():
        offers.setdefault(s["offer"], []).append(s)
    for code, spec in offers.items():
        if code in SMALL_LEFT_OUT and "rds" not in setting["large"]:
            continue
        for r in aws_regions:
            out.append({"provider": "aws", "kind": "offer", "region": r, "spec": spec,
                        "url": AWS.OFFER_URL.format(offer=code, region=r), "path": f"aws/{_slug(code)}/{r}.json",
                        "limit": LIMIT["rds"] if code == "AmazonRDS" else LIMIT["offer"]})
    if region in (None, "global"):
        out.append({"provider": "aws", "kind": "offer", "region": "global", "spec": AWS.cloudfront_spec(),
                    "url": AWS.GLOBAL_OFFER_URL.format(offer="AmazonCloudFront"),
                    "path": "aws/amazoncloudfront/global.json", "limit": LIMIT["offer"]})
    if "ec2" in setting["large"]:
        for r in aws_regions:
            out.append({"provider": "aws", "kind": "ec2_csv", "region": r, "url": AWS.EC2_CSV_URL.format(region=r),
                        "path": f"aws/amazonec2/{r}.json", "limit": LIMIT["ec2_csv"]})
    for r in (r for r in setting["regions"]["azure"] if region in (None, r)):
        for svc in AZ.SERVICES:
            out.append({"provider": "azure", "kind": "azure", "region": r, "service": svc, "url": AZ.query_url(svc, r),
                        "path": f"azure/{_slug(svc)}/{r}.json", "limit": LIMIT["azure_page"]})
    return [t for t in out if provider in (None, t["provider"])]


# ---------------------------------------------------------------- going outside (viz's rules)

class Refused(ValueError):
    """A URL outside the rules, or an answer over its cap."""


def check_url(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in HOSTS or u.username or u.password or (u.port not in (None, 443)):
        raise Refused(f"not fetched: only https to {', '.join(HOSTS)} ({u.scheme}://{u.hostname})")
    return url


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """A redirect is checked before it is followed: a Location outside the rules is refused without asking it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(*lower: urllib.request.BaseHandler) -> urllib.request.OpenerDirector:
    """The opener every fetch uses; ``lower`` is the arms' stand-in for the network's own handlers."""
    return urllib.request.build_opener(_CheckedRedirects, *lower)


def _open(url: str, timeout: float):
    resp = _opener().open(urllib.request.Request(check_url(url), headers={"User-Agent": "jui-viz"}),
                          timeout=timeout)   # noqa: S310 - checked: https to the two price hosts, each redirect too
    check_url(resp.geturl())                 # a second guard: where the answer came from
    return resp


def http_get(url: str, limit: int, timeout: float = TIMEOUT_SEC) -> bytes:
    """The answer's bytes, or Refused when it is more than ``limit``."""
    with _open(url, timeout) as resp:
        body = resp.read(limit + 1)
    if len(body) > limit:
        raise Refused(f"the answer is over {limit // MB} MB: {url}")
    return body


def http_lines(url: str, limit: int, timeout: float = TIMEOUT_SEC) -> Iterable[str]:
    """The answer's text lines, read as they come (EC2's CSV); Refused past ``limit`` bytes."""
    with _open(url, timeout) as resp:
        seen = 0
        for raw in resp:
            seen += len(raw)
            if seen > limit:
                raise Refused(f"the answer is over {limit // MB} MB: {url}")
            yield raw.decode("utf-8", "replace")


# ---------------------------------------------------------------- one file

def rows_of(t: dict, get: Callable[[str, int], bytes], lines: Callable[[str, int], Iterable[str]]) -> tuple[list[dict], list[str]]:
    """(rows, the spec lines not found) for one target. Raises on a failure (the caller records it)."""
    if t["kind"] == "offer":
        return AWS.rows_from_offer(json.loads(get(t["url"], t["limit"])), t["spec"], t["region"], t["url"])
    if t["kind"] == "ec2_csv":
        return AWS.rows_from_ec2_csv(lines(t["url"], t["limit"]), t["region"], t["url"])
    items, url, pages = [], t["url"], 0
    while url:
        if pages == AZURE_PAGES:
            raise Refused(f"more than {AZURE_PAGES} pages: {t['url']}")
        page = json.loads(get(check_url(url), t["limit"]))
        items += page.get("Items") or [] if isinstance(page, dict) else []
        url, pages = page.get("NextPageLink") if isinstance(page, dict) else None, pages + 1
    return AZ.rows_from_items(items, t["service"], t["region"], t["url"])


def document(rows: list[dict], t: dict, at_ms: int) -> bytes:
    when = datetime.datetime.fromtimestamp(at_ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    doc = {"version": 0, "currency": "USD", "description": f"fetched {when} by jui viz from {t['provider']} ({t['region']})",
           "prices": rows}
    return (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def fetch_one(t: dict, cache: Path, at_ms: int, get=http_get, lines=http_lines) -> dict:
    """Fetch, read, check, write one file. -> its index entry for this try (ok or the error)."""
    entry = {"provider": t["provider"], "region": t["region"], "source": t["url"], "lastTryAt": at_ms}
    try:
        rows, missing = rows_of(t, get, lines)
    except Exception as exc:  # noqa: BLE001 - any failure is this file's, recorded; the rest go on
        return {**entry, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    if not rows:
        return {**entry, "ok": False, "error": "no price row in the answer", "missing": missing[:50]}
    data = document(rows, t, at_ms)
    doc, problems = P.read_file(Path(t["path"]).name, data)
    if doc is None:
        first = problems[0]
        return {**entry, "ok": False, "error": f"not written: {first['code']} at {first['path']}: {first['message']}"}
    _write(cache / t["path"], data)
    return {**entry, "ok": True, "fetchedAt": at_ms, "rows": len(rows), "missing": missing[:50],
            "effective": max(r["effective"] for r in rows)}


# ---------------------------------------------------------------- a run, and the index

def read_index(cache: Path) -> dict:
    try:
        data = json.loads((cache / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "files": {}}
    return data if isinstance(data, dict) and isinstance(data.get("files"), dict) else {"version": 1, "files": {}}


def merge(old: dict, rel: str, got: dict) -> dict:
    """A try's entry over the last one: a failure keeps the last success's fetchedAt, rows and effective."""
    prev = old.get(rel) or {}
    if got["ok"]:
        return {k: v for k, v in got.items() if k != "ok"} | {"lastError": None}
    keep = {k: prev[k] for k in ("fetchedAt", "rows", "effective", "missing") if k in prev}
    return {**keep, "provider": got["provider"], "region": got["region"], "source": got["source"],
            "lastTryAt": got["lastTryAt"], "lastError": got["error"]}


def run(setting: dict, cache: Path, at_ms: int, get=http_get, lines=http_lines,
        provider: str | None = None, region: str | None = None) -> dict:
    """Fetch every target (or those of one provider / region); write the files and the index. -> the index. at_ms is
    the caller's (this module reads no clock: document_tools' clock gate, jsonui_doc_cli.reproducible)."""
    index = read_index(cache)
    for t in targets(setting, provider, region):
        index["files"][t["path"]] = merge(index["files"], t["path"], fetch_one(t, cache, at_ms, get, lines))
    index["lastRunAt"] = at_ms
    _write(cache / INDEX, (json.dumps(index, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return index


def last_ok(index: dict) -> int | None:
    """When a file was last fetched (the newest), or None."""
    got = [e["fetchedAt"] for e in index.get("files", {}).values() if isinstance(e, dict) and e.get("fetchedAt")]
    return max(got) if got else None


def due(index: dict, now_ms: int) -> bool:
    """Once a day: a day after the last run (whatever it got), or now when there was none."""
    last = index.get("lastRunAt")
    return not isinstance(last, int) or now_ms - last >= EVERY_MS


def summary(index: dict) -> dict:
    """What the page shows (where each price came from and when): per file, its source, when fetched, its effective
    date, rows and the last error; the newest fetch and how many files fail."""
    files = [{"path": k, **{f: v.get(f) for f in ("provider", "region", "source", "fetchedAt", "effective", "rows",
                                                    "lastTryAt", "lastError")}}
             for k, v in sorted(index.get("files", {}).items()) if isinstance(v, dict)]
    return {"lastOkAt": last_ok(index), "lastRunAt": index.get("lastRunAt"), "files": files,
            "failing": sum(1 for f in files if f["lastError"])}
