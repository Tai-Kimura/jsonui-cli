"""Price rows (infra-prices.v0) from Google Cloud's Cloud Billing Catalog API (https://cloudbilling.googleapis.com/v1,
an API key). Two parts, kept apart so the key is held by one of them only:

  * ``download``: the person who refreshes the bundled table runs
        JSONUI_GCP_BILLING_API_KEY=<key> python -m jsonui_doc_cli.infra.cost.gcp_prices <folder>
    and the services list and each target service's SKUs land in <folder>/gcp/ as the API answered (the key is not
    in them). The key is read from that environment variable and from nothing else (no keychain, no settings file,
    no gcloud credentials); it travels in the X-Goog-Api-Key header, never in a URL, and no message, log line or
    exception carries it (``redact``; an error is raised anew, not chained to the one that may hold the request).
    With no key, nothing is downloaded and the run says so.
  * ``rows_from_skus``: a pure function over the downloaded SKUs, which build_bundled calls with SPEC.

SPEC maps a SKU (a pattern on its description, the region it is listed in) to the sku the cost rules ask for. It was
written from the catalog as the API answered it on 2026-10-21 (asia-northeast1, us-east1; the operations of Cloud
Storage, DNS, GKE's cluster fee and Cloud Run's requests are listed under "global"). The catalog counts GiB, the price
rows GB: a GiB-month row is read as a GB-month (7% apart; the row's note says GiB).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

API = "https://cloudbilling.googleapis.com/v1"
KEY_ENV = "JSONUI_GCP_BILLING_API_KEY"
REGIONS = ("asia-northeast1", "us-east1")
NO_KEY = (f"gcp: {KEY_ENV} is not set — no GCP prices are downloaded (set it to a key restricted to the Cloud "
          f"Billing API to make them)")
TIMEOUT_SEC = 30
PAGES = 50
#: The services the rules read, by the catalog's display name.
SERVICES = ("Compute Engine", "Cloud SQL", "Cloud Run", "Cloud Storage", "Cloud Memorystore for Redis",
            "Cloud Run Functions", "Cloud Pub/Sub", "Secret Manager", "Cloud Key Management Service (KMS)",
            "Cloud DNS", "Networking", "Cloud Firestore", "Artifact Registry", "Kubernetes Engine")


def api_key(environ=None) -> str | None:
    """The key, from the environment variable only; None when it is unset or blank."""
    value = (os.environ if environ is None else environ).get(KEY_ENV, "")
    return value.strip() or None


def redact(text: str, key: str | None) -> str:
    """``text`` with every occurrence of the key replaced (a key in an echoed URL or header included)."""
    text = str(text)
    if key:
        text = text.replace(key, "***").replace(urllib.parse.quote(key, safe=""), "***")
    return text


class FetchError(RuntimeError):
    """A download failed; the message holds no key."""


def _get(url: str, key: str, opener: Callable = urllib.request.urlopen) -> dict:
    req = urllib.request.Request(url, headers={"X-Goog-Api-Key": key, "User-Agent": "jsonui-cli"})
    try:
        with opener(req, timeout=TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:   # noqa: BLE001 — every failure is re-raised with the key taken out
        raise FetchError(redact(f"{url}: {type(e).__name__}: {e}", key)) from None


def _pages(url: str, key: str, field: str, opener: Callable) -> list[dict]:
    out, token = [], ""
    for _ in range(PAGES):
        page = _get(url + (f"&pageToken={urllib.parse.quote(token)}" if token else ""), key, opener)
        out += page.get(field) or []
        token = page.get("nextPageToken") or ""
        if not token:
            return out
    raise FetchError(f"{url}: more than {PAGES} pages")


def download(folder: Path, environ=None, opener: Callable = urllib.request.urlopen,
             services: tuple[str, ...] = SERVICES, log=print) -> int:
    """Write <folder>/gcp/services.json and one <service id>.json of SKUs per target service. 0: done, or no key
    (said); 1: a failure (said, without the key)."""
    key = api_key(environ)
    if key is None:
        log(NO_KEY)
        return 0
    out = Path(folder) / "gcp"
    out.mkdir(parents=True, exist_ok=True)
    try:
        listed = _pages(f"{API}/services?pageSize=5000", key, "services", opener)
        by_name = {s.get("displayName"): s.get("serviceId") for s in listed}
        (out / "services.json").write_text(json.dumps(listed, indent=1), encoding="utf-8")
        for name in services:
            sid = by_name.get(name)
            if not sid:
                log(f"gcp: {name}: not in the services list")
                continue
            skus = _pages(f"{API}/services/{sid}/skus?currencyCode=USD&pageSize=5000", key, "skus", opener)
            (out / f"{sid}.json").write_text(json.dumps(skus, indent=1), encoding="utf-8")
            log(f"gcp: {name}: {len(skus)} skus")
    except FetchError as e:
        log(f"gcp: {e}")
        return 1
    return 0


# ---------------------------------------------------------------- rows

def G(service, description, service_name, sku, unit, usage_unit, family=None, group=None, per_units=1, scale=1.0,
      note=None, listed_in=None):
    """One line of the spec: the catalog's service display name, a pattern on the SKU's description, the price row's
    service / sku / unit, the pricing expression's usageUnit it is read in (another is not guessed), and scale (the
    rows' unit over the catalog's: a GiB-second SKU read as GB-hour is 3600). listed_in: "global" for a SKU the
    catalog lists under no region (the row is then the global one)."""
    return {"service": service, "description": re.compile(description), "service_name": service_name, "sku": sku,
            "unit": unit, "usage_unit": usage_unit, "family": family, "group": group, "per_units": per_units,
            "scale": scale, "note": note, "listed_in": listed_in}


RUN, CE, SQL, GCS = "Cloud Run", "Compute Engine", "Cloud SQL", "Cloud Storage"
GLOBAL = "global"
SPEC: list[dict] = [
    # Cloud Run, request-based billing: per vCPU-second and GiB-second, read by the hour; requests (2 million a month
    # free: the catalog's first step). The vCPU and memory grant the page states is not in the catalog: not counted.
    G(RUN, r"^Services CPU \(Request-based billing\)$", "run", "vcpu", "vCPU-hour", "s", scale=3600,
      note="request-based billing (the free vCPU grant is not counted)"),
    G(RUN, r"^Services Memory \(Request-based billing\)$", "run", "memory", "GB-hour", "GiBy.s", scale=3600,
      note="request-based billing, per GiB (the free memory grant is not counted)"),
    G(RUN, r"^Requests$", "run", "requests", "request", "count", per_units=1_000_000, listed_in=GLOBAL,
      note="the first 2 million a month are the catalog's free step"),
    G(RUN, r"^Jobs CPU in ", "run.job", "vcpu", "vCPU-hour", "s", scale=3600),
    G(RUN, r"^Jobs Memory in ", "run.job", "memory", "GB-hour", "GiBy.s", scale=3600, note="per GiB"),
    # Cloud Run functions: memory time is the formula's compute (GB-second), invocations its requests
    G("Cloud Run Functions", r"^Cloud Run functions Memory \(Request-based billing\) in ", "functions", "compute",
      "GB-second", "GiBy.s", note="per GiB-second"),
    G("Cloud Run Functions", r"^Cloud Run Functions Invocations$", "functions", "requests", "request", "count",
      per_units=1_000_000, listed_in=GLOBAL, note="the first 2 million a month are the catalog's free step"),
    # Compute Engine: an instance is its vCPUs and its RAM (gcp/gce reads the type); the boot disk is Balanced PD
    G(CE, r"^E2 Instance Core running in ", "gce", "e2:vcpu", "vCPU-hour", "h"),
    G(CE, r"^E2 Instance Ram running in ", "gce", "e2:ram", "GB-hour", "GiBy.h", note="per GiB"),
    G(CE, r"^N2 Instance Core running in ", "gce", "n2:vcpu", "vCPU-hour", "h"),
    G(CE, r"^N2 Instance Ram running in ", "gce", "n2:ram", "GB-hour", "GiBy.h", note="per GiB"),
    G(CE, r"^Balanced PD Capacity( in |$)", "gce", "storage", "GB-month", "GiBy.mo", note="Balanced PD, per GiB"),
    G(CE, r"^Balanced PD Capacity( in |$)", "pd", "storage", "GB-month", "GiBy.mo", note="Balanced PD, per GiB"),
    # internet egress from the region (premium tier), to its own continent: the formulas' data-transfer egress
    G(CE, r"^Network Internet Data Transfer Out from (Tokyo to Apac\(Excluding Korea and Indonesia\)|Americas to "
      r"Americas)$", "data-transfer", "egress", "GB", "GiBy",
      note="premium tier, to the region's own continent, per GiB"),
    # Cloud SQL (MySQL and PostgreSQL are the same price): zonal, and regional (HA) on the :multi-az skus
    G(SQL, r"^Cloud SQL for MySQL: Zonal - vCPU in ", "cloudsql", "vcpu", "vCPU-hour", "h"),
    G(SQL, r"^Cloud SQL for MySQL: Zonal - RAM in ", "cloudsql", "ram", "GB-hour", "GiBy.h", note="per GiB"),
    G(SQL, r"^Cloud SQL for MySQL: Regional - vCPU in ", "cloudsql", "vcpu:multi-az", "vCPU-hour", "h",
      note="regional (high availability)"),
    G(SQL, r"^Cloud SQL for MySQL: Regional - RAM in ", "cloudsql", "ram:multi-az", "GB-hour", "GiBy.h",
      note="regional (high availability), per GiB"),
    G(SQL, r"^Cloud SQL for MySQL: Zonal - Standard storage in ", "cloudsql", "storage", "GB-month", "GiBy.mo",
      note="SSD, per GiB"),
    G(SQL, r"^Cloud SQL for MySQL: Regional - Standard storage in ", "cloudsql", "storage:multi-az", "GB-month",
      "GiBy.mo", note="SSD, regional, per GiB"),
    # Memorystore for Redis: GiB-hours by tier and capacity band (gcp/memorystore reads both)
    G("Cloud Memorystore for Redis", r"^Redis Capacity Basic M1 ", "memorystore", "basic:m1", "GB-hour", "GiBy.h",
      note="Basic, 1-4 GiB"),
    G("Cloud Memorystore for Redis", r"^Redis Capacity Basic M2 ", "memorystore", "basic:m2", "GB-hour", "GiBy.h",
      note="Basic, 5-10 GiB"),
    G("Cloud Memorystore for Redis", r"^Redis Capacity Standard M1 ", "memorystore", "standard:m1", "GB-hour",
      "GiBy.h", note="Standard (replicated), 1-4 GiB"),
    G("Cloud Memorystore for Redis", r"^Redis Capacity Standard M2 ", "memorystore", "standard:m2", "GB-hour",
      "GiBy.h", note="Standard (replicated), 5-10 GiB"),
    # Cloud Storage, Standard class in one region
    G(GCS, r"^Standard Storage (?!.*(Dual|Multi))", "gcs", "storage", "GB-month", "GiBy.mo", note="Standard, regional"),
    G(GCS, r"^Regional Standard Class A Operations$", "gcs", "put", "request", "count", per_units=10_000,
      listed_in=GLOBAL),
    G(GCS, r"^Regional Standard Class B Operations$", "gcs", "get", "request", "count", per_units=10_000,
      listed_in=GLOBAL),
    # Secret Manager (6 secret versions and 10,000 accesses a month free: the catalog's first steps), Cloud KMS
    G("Secret Manager", r"^Secret version replica storage$", "secretmanager", "secret", "secret", "mo"),
    G("Secret Manager", r"^Secret access operations$", "secretmanager", "api", "request", "count", per_units=10_000),
    G("Cloud Key Management Service (KMS)", r"^Active software symmetric key versions$", "kms", "key", "month", "mo"),
    G("Cloud Key Management Service (KMS)", r"^Cryptographic operations with a software symmetric key$", "kms",
      "api", "request", "count", per_units=10_000),
    # Cloud DNS, GKE's cluster fee, Artifact Registry
    G("Cloud DNS", r"^ManagedZone$", "clouddns", "zone", "month", "mo", listed_in=GLOBAL),
    G("Cloud DNS", r"^DNS Query \(port 53\)$", "clouddns", "queries", "request", "count", per_units=1_000_000,
      listed_in=GLOBAL),
    G("Kubernetes Engine", r"^Zonal Kubernetes Clusters$", "gke", "cluster", "instance-hour", "h", listed_in=GLOBAL,
      note="cluster management fee (the monthly free credit per billing account is not counted)"),
    G("Artifact Registry", r"^Artifact Registry Storage$", "artifactregistry", "storage", "GB-month", "GiBy.mo",
      listed_in=GLOBAL, note="the first 0.5 GiB is the catalog's free step"),
]


def _money(m: dict) -> float:
    return int(m.get("units") or 0) + int(m.get("nanos") or 0) / 1e9


def _round(x: float) -> float:
    return float(f"{x:.10g}")


def price_row(sku: dict, spec: dict, region: str, source: str) -> tuple[dict | None, str | None]:
    info = (sku.get("pricingInfo") or [{}])[0]
    expr = info.get("pricingExpression") or {}
    if expr.get("usageUnit") != spec["usage_unit"]:
        return None, f"usageUnit {expr.get('usageUnit')!r} is not {spec['usage_unit']!r}"
    rates = sorted(expr.get("tieredRates") or [], key=lambda r: float(r.get("startUsageAmount") or 0))
    if not rates:
        return None, "no tiered rates"
    k = spec["per_units"] * spec["scale"]
    row = {"provider": "gcp", "service": spec["service_name"], "sku": spec["sku"], "region": region,
           "unit": spec["unit"], "effective": str(info.get("effectiveTime") or "")[:10], "source": source}
    if spec["per_units"] != 1:
        row["per_units"] = spec["per_units"]
    if len(rates) == 1 and float(rates[0].get("startUsageAmount") or 0) == 0:
        row["price_usd"] = _round(_money(rates[0].get("unitPrice") or {}) * k)
    else:
        row["tiers"] = []
        for i, r in enumerate(rates):
            t = {"from": float(r.get("startUsageAmount") or 0) / spec["scale"],
                 "price_usd": _round(_money(r.get("unitPrice") or {}) * k)}
            if i + 1 < len(rates):
                t["to"] = float(rates[i + 1].get("startUsageAmount") or 0) / spec["scale"]
            row["tiers"].append(t)
    if spec["note"]:
        row["note"] = spec["note"][:200]
    return row, None


def rows_from_skus(skus: list[dict], service_id: str, display_name: str, region: str,
                   spec: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    """(price rows, the spec lines of this service no SKU matched, with why) for one service's SKUs in one region:
    on-demand only, the SKU's serviceRegions holding the region."""
    out, missing = [], []
    source = f"{API}/services/{service_id}/skus"
    for s in (s for s in (SPEC if spec is None else spec) if s["service"] == display_name):
        if s.get("listed_in") == GLOBAL and region != GLOBAL or s.get("listed_in") != GLOBAL and region == GLOBAL:
            continue
        hits = [k for k in skus if isinstance(k, dict)
                and (k.get("category") or {}).get("usageType") == "OnDemand"
                and region in (k.get("serviceRegions") or [])
                and s["description"].search(k.get("description") or "")
                and (s["family"] is None or (k.get("category") or {}).get("resourceFamily") == s["family"])
                and (s["group"] is None or (k.get("category") or {}).get("resourceGroup") == s["group"])]
        if not hits:
            missing.append(f"{s['service_name']} {s['sku']} ({display_name} / {s['description'].pattern}): no sku")
            continue
        prices = {json.dumps((k.get("pricingInfo") or [{}])[0].get("pricingExpression"), sort_keys=True) for k in hits}
        if len(prices) > 1:   # two SKUs the pattern reaches, priced apart: not guessed
            missing.append(f"{s['service_name']} {s['sku']} ({s['description'].pattern}): {len(hits)} skus, "
                           f"{len(prices)} prices: {sorted(k.get('description') for k in hits)[:3]}")
            continue
        row, why = price_row(hits[0], s, region, source)
        if row is None:
            missing.append(f"{s['service_name']} {s['sku']} ({s['description'].pattern}): {why}")
            continue
        out.append(row)
    return out, missing


def rows_from_folder(folder: Path, regions: tuple[str, ...] = REGIONS + (GLOBAL,),
                     spec: list[dict] | None = None) -> tuple[list[dict], list[str], str | None]:
    """(rows, missing, why there are none) from <folder>/gcp as download wrote it; no key is read here."""
    base = Path(folder) / "gcp"
    if not (base / "services.json").is_file():
        return [], [], (f"gcp: not downloaded ({base}/services.json missing) — run gcp_prices with {KEY_ENV} set to "
                        f"make GCP rows")
    listed = json.loads((base / "services.json").read_text(encoding="utf-8"))
    rows, missing = [], []
    for s in listed:
        name, sid = s.get("displayName"), s.get("serviceId")
        f = base / f"{sid}.json"
        if not f.is_file():
            continue
        skus = json.loads(f.read_text(encoding="utf-8"))
        for region in regions:
            got, miss = rows_from_skus(skus, sid, name, region, spec)
            rows += got
            missing += [f"{region}: {m}" for m in miss]
    return rows, missing, None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(f"usage: {KEY_ENV}=<key> python -m jsonui_doc_cli.infra.cost.gcp_prices <folder>", file=sys.stderr)
        return 2
    return download(Path(argv[0]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
