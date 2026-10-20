"""Price rows (infra-prices.v0) from Azure Retail Prices (https://prices.azure.com/api/retail/prices, no key; plan L-B2).
A pure function over the items the API returned: the fetching (fetch.py) asks one service in one region at a time
and hands the items here.

Read from the answers themselves (2026-10-20, japaneast):
  * a price is per unitOfMeasure, which counts in blocks: "10" (executions), "10K", "1M", "1 GB/Month", "1 Hour",
    "1 GB Second", "1/Hour";
  * a free amount is a first step at 0 USD: tierMinimumUnits counts those blocks (Functions' "Standard Total
    Executions" is 0 up to 100000 blocks of 10, a million executions), so the steps become tiers in plain units;
  * only type "Consumption" is a pay-as-you-go price (Reservation and DevTestConsumption are not).
SPEC maps an Azure meter (productName, skuName, meterName) to the sku the cost rules ask for (formulas.py's
conventional names): the node's service is what the seed writes for Azure (functions, blob, servicebus, keyvault,
cosmosdb) and transfer is service data-transfer.
"""
from __future__ import annotations

import re
import urllib.parse

API = "https://prices.azure.com/api/retail/prices"


def S(azure_service, product, sku_name, meter, service, sku, unit, per_units=1, units=(), note=None):
    """One line of the spec. units: the unitOfMeasure values this meter is read in (another is not guessed)."""
    return {"azure_service": azure_service, "product": product, "sku_name": sku_name, "meter": meter,
            "service": service, "sku": sku, "unit": unit, "per_units": per_units, "units": tuple(units), "note": note}


SPEC = [
    S("Functions", "Functions", "Standard", "Standard Total Executions", "functions", "requests", "request",
      1_000_000, ["10"], "Consumption plan"),
    S("Functions", "Functions", "Standard", "Standard Execution Time", "functions", "compute", "GB-second",
      1, ["1 GB Second"], "Consumption plan"),
    S("Storage", "Blob Storage", "Hot LRS", "Hot LRS Data Stored", "blob", "storage", "GB-month", 1, ["1 GB/Month"],
      "Hot, LRS"),
    S("Storage", "Blob Storage", "Hot LRS", "Hot Read Operations", "blob", "get", "request", 10_000, ["10K"],
      "Hot, LRS"),
    S("Storage", "Blob Storage", "Hot LRS", "Hot LRS Write Operations", "blob", "put", "request", 10_000, ["10K"],
      "Hot, LRS"),
    S("Service Bus", "Service Bus", "Standard", "Standard Messaging Operations", "servicebus", "requests", "request",
      1_000_000, ["1M"], "Standard tier"),
    S("Key Vault", "Key Vault", "Standard", "Operations", "keyvault", "api", "request", 10_000, ["10K"],
      "Standard, secret operations"),
    S("Azure Cosmos DB", "Azure Cosmos DB serverless", "RUs", "1M RUs", "cosmosdb", "read", "read_unit", 1_000_000,
      ["1M"], "serverless: a read's request units"),
    S("Azure Cosmos DB", "Azure Cosmos DB serverless", "RUs", "1M RUs", "cosmosdb", "write", "write_unit", 1_000_000,
      ["1M"], "serverless: a write's request units"),
    S("Azure Cosmos DB", "Azure Cosmos DB", "RUs", "Data Stored", "cosmosdb", "storage", "GB-month", 1,
      ["1 GB/Month"], "transactional storage"),
    S("Azure Cosmos DB", "Azure Cosmos DB", "RUs", "100 RU/s", "cosmosdb", "capacity", "capacity_unit-hour", 1,
      ["1/Hour", "1 Hour"], "provisioned, a capacity unit is 100 RU/s"),
    S("Bandwidth", "Rtn Preference: MGN", "Standard", "Standard Data Transfer Out", "data-transfer", "egress", "GB",
      1, ["1 GB"], "to the internet over Microsoft's network"),
    S("Bandwidth", "Rtn Preference: MGN", "Standard", "Standard Inter-Availability Zone Data Transfer Out",
      "data-transfer", "transfer-regional", "GB", 1, ["1 GB"], "across availability zones"),
    S("Bandwidth", "Rtn Preference: MGN", "Standard", "Standard Inter-Region Data Transfer", "data-transfer",
      "transfer-inter-region", "GB", 1, ["1 GB"], "to another Azure region"),
]
SERVICES = tuple(dict.fromkeys(s["azure_service"] for s in SPEC))

_BLOCK = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KM])?(?![A-Za-z])")


def block(unit_of_measure: str) -> float | None:
    """How many plain units one unitOfMeasure is: "10" 10, "10K" 10000, "1M" 1000000, "1 GB/Month" 1, "1/Hour" 1."""
    m = _BLOCK.match(unit_of_measure or "")
    if not m:
        return None
    return float(m[1]) * {"K": 1_000, "M": 1_000_000, None: 1}[m[2]]


# a service whose region holds thousands of meters is asked for the products the spec reads only
NARROW = {"Storage": "productName eq 'Blob Storage' and skuName eq 'Hot LRS'"}


def query_url(azure_service: str, region: str) -> str:
    """One service in one region, pay-as-you-go only."""
    flt = f"serviceName eq '{azure_service}' and armRegionName eq '{region}' and priceType eq 'Consumption'"
    if azure_service in NARROW:
        flt += f" and {NARROW[azure_service]}"
    return f"{API}?{urllib.parse.urlencode({'$filter': flt})}"


def _round(x: float) -> float:
    return float(f"{x:.10g}")


def price_row(items: list[dict], spec: dict, region: str, source: str) -> tuple[dict | None, str | None]:
    """(the row, or None and why) from the items of one meter: one price, or tiers in plain units."""
    units = {i.get("unitOfMeasure") for i in items}
    if len(units) != 1 or next(iter(units)) not in spec["units"]:
        return None, f"unit {sorted(map(str, units))} is not {list(spec['units'])}"
    m = block(next(iter(units)))
    steps: dict[float, float] = {}
    for i in sorted(items, key=lambda i: float(i.get("tierMinimumUnits") or 0)):
        steps.setdefault(float(i.get("tierMinimumUnits") or 0) * m, float(i["retailPrice"]) / m * spec["per_units"])
    row = {"provider": "azure", "service": spec["service"], "sku": spec["sku"], "region": region, "unit": spec["unit"],
           "effective": max(str(i.get("effectiveStartDate") or "")[:10] for i in items), "source": source}
    if spec["per_units"] != 1:
        row["per_units"] = spec["per_units"]
    froms = sorted(steps)
    if froms == [0.0]:
        row["price_usd"] = _round(steps[0.0])
    else:
        row["tiers"] = []
        for k, f in enumerate(froms):
            t = {"from": f, "price_usd": _round(steps[f])}
            if k + 1 < len(froms):
                t["to"] = froms[k + 1]
            row["tiers"].append(t)
    if spec["note"]:
        row["note"] = spec["note"][:200]
    return row, None


def rows_from_items(items: list[dict], azure_service: str, region: str, source: str) -> tuple[list[dict], list[str]]:
    """(price rows, the spec lines of this service that no item matched, with why) for one service's items."""
    out, missing = [], []
    for s in (s for s in SPEC if s["azure_service"] == azure_service):
        hits = [i for i in items if isinstance(i, dict) and i.get("type") == "Consumption"
                and i.get("productName") == s["product"] and i.get("skuName") == s["sku_name"]
                and i.get("meterName") == s["meter"] and i.get("armRegionName") == region
                and isinstance(i.get("retailPrice"), (int, float)) and not isinstance(i.get("retailPrice"), bool)]
        if not hits:
            missing.append(f"{s['service']} {s['sku']} ({s['product']} / {s['sku_name']} / {s['meter']}): no item")
            continue
        row, why = price_row(hits, s, region, source)
        if row is None:
            missing.append(f"{s['service']} {s['sku']} ({s['meter']}): {why}")
            continue
        out.append(row)
    return out, missing
