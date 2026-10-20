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


def S(azure_service, product, sku_name, meter, service, sku, unit, per_units=1, units=(), note=None, scale=1.0,
      free=None, arm=None, arm_sku=None, narrow=None):
    """One line of the spec. units: the unitOfMeasure values this meter is read in (another is not guessed).
    product: the productName, or a compiled pattern on it. scale: the rows' unit over the meter's (a vCPU-second
    read as a vCPU-hour is 3600). free: the row's free amount (a page's, with the page in note). arm: where the meter
    is listed when not in the region itself — a zone by region ({"japaneast": "Zone 2", …}, the row stays the
    region's) or one name ("Global", "Zone 1": the row is the global one). arm_sku: the meter's armSkuName (a VM's
    type). narrow: the query's extra filter for a service whose region holds thousands of meters."""
    return {"azure_service": azure_service, "product": product, "sku_name": sku_name, "meter": meter,
            "service": service, "sku": sku, "unit": unit, "per_units": per_units, "units": tuple(units), "note": note,
            "scale": scale, "free": free, "arm": arm, "arm_sku": arm_sku, "narrow": narrow}


SPEC = [
    S("Functions", "Functions", "Standard", "Standard Total Executions", "functions", "requests", "request",
      1_000_000, ["10"], "Consumption plan"),
    S("Functions", "Functions", "Standard", "Standard Execution Time", "functions", "compute", "GB-second",
      1, ["1 GB Second"], "Consumption plan"),
    # the seed writes an Azure storage account as "storage" (the IaC tables); "blob" was a name no node carried
    S("Storage", "Blob Storage", "Hot LRS", "Hot LRS Data Stored", "storage", "storage", "GB-month", 1,
      ["1 GB/Month"], "Hot, LRS"),
    S("Storage", "Blob Storage", "Hot LRS", "Hot Read Operations", "storage", "get", "request", 10_000, ["10K"],
      "Hot, LRS"),
    S("Storage", "Blob Storage", "Hot LRS", "Hot LRS Write Operations", "storage", "put", "request", 10_000, ["10K"],
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

# ---------------------------------------------------------------- the bundled table's further lines (read 2026-10-21)
# The meters the rules charge for every Azure (category, service) the IaC tables draft, from the Retail Prices answers
# for japaneast and eastus. The type-priced skus are spelled as the IaC writes the type (azurerm sizes, sku_name).
ACA_PAGE = "https://azure.microsoft.com/pricing/details/container-apps/"
FD_PAGE = "https://azure.microsoft.com/pricing/details/frontdoor/"
_LINUX_VM = re.compile(r"^Virtual Machines .* Series$")
VM_TYPES = ("Standard_B1s", "Standard_B1ms", "Standard_B2s", "Standard_B2ms", "Standard_D2s_v5", "Standard_D4s_v5",
            "Standard_D2as_v5")
VM_NARROW = "(" + " or ".join(f"armSkuName eq '{t}'" for t in VM_TYPES) + ")"
APP_PLANS = {"B1": ("Azure App Service Basic Plan - Linux", "B1", "B1"),
             "B2": ("Azure App Service Basic Plan - Linux", "B2", "B2"),
             "S1": ("Azure App Service Standard Plan - Linux", "S1", "S1 App"),
             "P0v3": ("Azure App Service Premium v3 Plan - Linux", "P0v3", "P0v3 App"),
             "P1v3": ("Azure App Service Premium v3 Plan - Linux", "P1 v3", "P1 v3 App")}
#: Managed Disks bill a disk by its size's tier, a month each (Standard SSD "E", Premium SSD "P")
DISK_TIERS = {"4": 32, "6": 64, "10": 128, "15": 256, "20": 512, "30": 1024, "40": 2048, "50": 4096}
FD_ZONES = {"north_america": "Zone 1", "japan": "Zone 2", "asia": "Zone 2", "south_america": "Zone 3",
            "australia": "Zone 4", "india": "Zone 5"}
H, GBH, MO = ["1 Hour", "1/Hour"], ["1 GB Hour", "1 GiB Hour"], ["1/Month"]


def _bundled() -> list[dict]:
    out = []
    for t in VM_TYPES:
        for svc in ("vm", "vmss"):
            out.append(S("Virtual Machines", _LINUX_VM, None, None, svc, t, "instance-hour", 1, H, "Linux, pay as you go",
                         arm_sku=t, narrow=VM_NARROW))
    for sku, (product, sku_name, meter) in APP_PLANS.items():
        out.append(S("Azure App Service", product, sku_name, meter, "appservice", sku, "instance-hour", 1, H, "Linux"))
    out += [
        S("Container Instances", "Container Instances", "Standard", "Standard vCPU Duration", "aci", "vcpu",
          "vCPU-hour", 1, H, "Linux"),
        S("Container Instances", "Container Instances", "Standard", "Standard Memory Duration", "aci", "memory",
          "GB-hour", 1, GBH, "Linux"),
        # the Consumption plan's grant (the page: "The first 180,000 vCPU-seconds, 360,000 GiB-seconds, and 2 million
        # requests per subscription per month are free"), the subscription's: one pool across apps and regions
        S("Azure Container Apps", "Azure Container Apps", "Standard", "Standard vCPU Active Usage", "containerapps",
          "vcpu", "vCPU-hour", 1, ["1 Second"], f"Consumption, active; free: {ACA_PAGE} (read 2026-10-21)", scale=3600,
          free={"amount": 50, "period": "month", "pool": "azure:container-apps-grant-vcpu"}),
        S("Azure Container Apps", "Azure Container Apps", "Standard", "Standard Memory Active Usage", "containerapps",
          "memory", "GB-hour", 1, ["1 GiB Second"], f"Consumption, active, per GiB; free: {ACA_PAGE} (read 2026-10-21)",
          scale=3600, free={"amount": 100, "period": "month", "pool": "azure:container-apps-grant-memory"}),
        # Static Web Apps sit under App Service in Retail Prices; eastus has none (eastus2 is its US East region)
        S("Azure App Service", "Static Web Apps", "Standard", "Standard App", "staticwebapps", "plan", "month", 1, MO,
          "Standard, an app a month", arm={"japaneast": "japaneast", "eastus": "eastus2"},
          narrow="productName eq 'Static Web Apps'"),
        S("Azure App Service", "Static Web Apps", "Standard", "Standard Bandwidth Usage", "staticwebapps", "bandwidth",
          "GB", 1, ["1 GB"], "Standard; the first 100 GB are the meter's free step (the page: per subscription)",
          arm={"japaneast": "japaneast", "eastus": "eastus2"}, narrow="productName eq 'Static Web Apps'"),
        S("Azure Front Door Service", "Azure Front Door", "Standard", "Standard Base Fees", "frontdoor", "plan",
          "month", 1, MO, f"Standard base fee, a profile a month: {FD_PAGE}", arm="Zone 2"),
        S("Azure Kubernetes Service", "Azure Kubernetes Service", "Standard", "Standard Uptime SLA", "aks", "cluster",
          "instance-hour", 1, H, "Standard tier (the Free tier's control plane is not charged)"),
    ]
    for engine, product_b, product_gp, gp_type, gp_vcores, storage_product in (
            ("mysql", "Azure Database for MySQL Flexible Server Burstable BS Series Compute",
             "Azure Database for MySQL Flexible Server General Purpose Dadsv5 Series Compute", "GP_Standard_D2ads_v5", 2,
             "Azure Database for MySQL Flexible Server Storage"),
            ("postgresql", "Azure Database for PostgreSQL Flexible Server Burstable BS Series Compute",
             "Azure Database for PostgreSQL Flexible Server General Purpose Ddsv5 Series Compute", "GP_Standard_D2ds_v5",
             2, "Azure Database for PostgreSQL Flex Server Storage")):
        for t, name in (("B_Standard_B1ms", "B1MS"), ("B_Standard_B2s", "B2S")):
            out.append(S(f"Azure Database for {'MySQL' if engine == 'mysql' else 'PostgreSQL'}", product_b, name, name,
                         engine, t, "instance-hour", 1, H, "Flexible Server, Burstable"))
        out.append(S(f"Azure Database for {'MySQL' if engine == 'mysql' else 'PostgreSQL'}", product_gp, "vCore",
                     "vCore", engine, gp_type, "instance-hour", 1, H, f"Flexible Server, {gp_vcores} vCores",
                     scale=gp_vcores))
        out.append(S(f"Azure Database for {'MySQL' if engine == 'mysql' else 'PostgreSQL'}", storage_product,
                     "Storage", "Storage Data Stored", engine, "storage", "GB-month", 1, ["1 GB/Month"], "LRS"))
    sql_compute = "SQL Database Single/Elastic Pool General Purpose - Compute Gen5"
    for v in (2, 4):
        out.append(S("SQL Database", sql_compute, f"{v} vCore", "vCore", "sql", f"GP_Gen5_{v}", "instance-hour", 1, H,
                     "General Purpose, provisioned"))
    out.append(S("SQL Database", "SQL Database Single/Elastic Pool General Purpose - Storage", "General Purpose",
                 "General Purpose Data Stored", "sql", "storage", "GB-month", 1, ["1 GB/Month"], "General Purpose"))
    for tier in ("Basic", "Standard"):
        for c in ("C0", "C1"):
            out.append(S("Redis Cache", f"Azure Redis Cache {tier}", c, f"{c} Cache", "redis", f"{tier}_{c}",
                         "instance-hour", 1, H, f"{tier} {c}"))
    out += [
        S("Azure Cognitive Search", "Azure AI Search", "Basic", "Basic Unit", "search", "basic", "instance-hour", 1, H),
        S("Azure Cognitive Search", "Azure AI Search", "Standard S1", "Standard S1 Unit", "search", "standard",
          "instance-hour", 1, H, "Standard S1"),
        S("Azure DNS", "Azure DNS", "Public", "Public Zone", "dns", "zone", "month", 1, ["1"], "public zone",
          arm="Zone 1"),
        S("Azure DNS", "Azure DNS", "Public", "Public Queries", "dns", "queries", "request", 1_000_000, ["1M"],
          "public queries", arm="Zone 1"),
    ]
    for zone, arm in FD_ZONES.items():
        for svc in ("frontdoor", "cdn"):   # classic CDN profiles are Front Door's now: priced on its rows
            out.append(S("Azure Front Door Service", "Azure Front Door", "Standard", "Standard Data Transfer Out", svc,
                         f"egress-{zone}", "GB", 1, ["1 GB"], f"Standard, edge to client, {arm}; zones: {FD_PAGE}",
                         arm=arm))
            out.append(S("Azure Front Door Service", "Azure Front Door", "Standard", "Standard Requests", svc,
                         f"requests-{zone}", "request", 10_000, ["10K"], f"Standard, {arm}", arm=arm))
    out += [
        # the WAF a node does not say the kind of is Application Gateway WAF v2's (the rule says so)
        S("Application Gateway", "Application Gateway WAF v2", "Standard", "Standard Fixed Cost", "waf", "hour",
          "instance-hour", 1, H, "Application Gateway WAF v2, the gateway's hours"),
        S("Application Gateway", "Application Gateway WAF v2", "Standard", "Standard Capacity Units", "waf", "capacity",
          "capacity_unit-hour", 1, H, "Application Gateway WAF v2"),
        S("Application Gateway", "Application Gateway Standard v2", "Standard", "Standard Fixed Cost", "appgateway",
          "hour", "instance-hour", 1, H, "Standard v2"),
        S("Application Gateway", "Application Gateway Standard v2", "Standard", "Standard Capacity Units",
          "appgateway", "lcu", "LCU-hour", 1, H, "Standard v2, a capacity unit"),
        S("Load Balancer", "Load Balancer", "Standard", "Standard Included LB Rules and Outbound Rules", "lb", "hour",
          "instance-hour", 1, H, "Standard, the first 5 rules", arm="Global"),
        S("Load Balancer", "Load Balancer", "Standard", "Standard Data Processed", "lb", "processed", "GB", 1,
          ["1 GB"], "Standard", arm="Global"),
        S("API Management", "API Management", "Basic v2", "Basic v2 Calls", "apim", "requests", "request", 10_000,
          ["10K"], "Basic v2 (its unit's hours are not counted)"),
        S("Log Analytics", "Log Analytics", "Analytics Logs", "Analytics Logs Data Ingestion", "loganalytics", "ingest",
          "GB", 1, ["1 GB"], "Analytics Logs; the first 5 GB a month are the meter's free step"),
        S("Log Analytics", "Log Analytics", "Analytics Logs", "Analytics Logs Data Retention", "loganalytics",
          "storage", "GB-month", 1, ["1 GB/Month"], "Analytics Logs retention"),
        S("Log Analytics", "Log Analytics", "Analytics Logs", "Analytics Logs Data Ingestion", "appinsights", "ingest",
          "GB", 1, ["1 GB"], "a workspace-based Application Insights ingests into Log Analytics"),
        S("Log Analytics", "Log Analytics", "Analytics Logs", "Analytics Logs Data Retention", "appinsights",
          "storage", "GB-month", 1, ["1 GB/Month"], "a workspace-based Application Insights"),
        S("Azure Monitor", "Azure Monitor", "Alerts", "Alerts Metric Monitored", "monitor", "alarm", "month", 1, MO,
          "metric alert rule; the first 10 a month are the meter's free step"),
        S("Event Grid", "Event Grid", "Standard", "Standard Operations", "eventgrid", "requests", "request", 100_000,
          ["100K"], "Standard operations"),
        S("Event Hubs", "Event Hubs", "Standard", "Standard Throughput Unit", "eventhubs", "shard",
          "capacity_unit-hour", 1, H, "Standard, a throughput unit"),
        S("Event Hubs", "Event Hubs", "Standard", "Standard Ingress Events", "eventhubs", "put", "request", 1_000_000,
          ["1M"], "Standard ingress events"),
        S("Storage", "Files", "Standard LRS", "LRS Data Stored", "files", "storage", "GB-month", 1, ["1 GB/Month"],
          "Standard (transaction optimized), LRS",
          narrow="(productName eq 'Files' or contains(productName, 'Managed Disks'))"),
    ]
    for kind, product in (("E", "Standard SSD Managed Disks"), ("P", "Premium SSD Managed Disks")):
        for n in DISK_TIERS:
            out.append(S("Storage", product, f"{kind}{n} LRS", f"{kind}{n} LRS Disk", "disk", f"{kind}{n}", "month", 1,
                         MO, f"{product}, {DISK_TIERS[n]} GB, LRS",
                         narrow="(productName eq 'Files' or contains(productName, 'Managed Disks'))"))
    return out


BUNDLED_SPEC = SPEC + _bundled()
BUNDLED_REGIONS = ("japaneast", "eastus")

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
    scale = spec.get("scale") or 1.0
    steps: dict[float, float] = {}
    for i in sorted(items, key=lambda i: float(i.get("tierMinimumUnits") or 0)):
        steps.setdefault(float(i.get("tierMinimumUnits") or 0) * m / scale,
                         float(i["retailPrice"]) / m * spec["per_units"] * scale)
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
    if spec.get("free"):
        row["free"] = dict(spec["free"])
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


# ---------------------------------------------------------------- the bundled table: download, then rows

def _matches(i: dict, s: dict, arm_region: str) -> bool:
    product = s["product"]
    return (isinstance(i, dict) and i.get("type") == "Consumption" and i.get("armRegionName") == arm_region
            and (product.search(i.get("productName") or "") if hasattr(product, "search")
                 else i.get("productName") == product)
            and (s["sku_name"] is None or i.get("skuName") == s["sku_name"])
            and (s["meter"] is None or i.get("meterName") == s["meter"])
            and (s.get("arm_sku") is None or i.get("armSkuName") == s["arm_sku"])
            and "Spot" not in (i.get("skuName") or "") and "Low Priority" not in (i.get("skuName") or "")
            and isinstance(i.get("retailPrice"), (int, float)) and not isinstance(i.get("retailPrice"), bool))


def arm_of(s: dict, region: str) -> tuple[str, str]:
    """(where the meter is listed, the row's region) for a bundled region."""
    arm = s.get("arm")
    if isinstance(arm, dict):
        return arm[region], region
    if isinstance(arm, str):
        return arm, "global"
    return region, region


def _query_key(s: dict, arm_region: str) -> str:
    flt = f"serviceName eq '{s['azure_service']}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption'"
    narrow = s.get("narrow") or NARROW.get(s["azure_service"])
    return flt + (f" and {narrow}" if narrow else "")


def queries(regions=BUNDLED_REGIONS, spec=None) -> list[str]:
    """Every $filter the bundled spec needs, once each."""
    out = []
    for s in spec or BUNDLED_SPEC:
        for region in regions:
            q = _query_key(s, arm_of(s, region)[0])
            if q not in out:
                out.append(q)
    return out


def download(folder, regions=BUNDLED_REGIONS, spec=None, opener=None, log=print, pages: int = 40) -> int:
    """Write <folder>/azure/<n>.json per query (the items, all pages) and <folder>/azure/index.json (query -> file).
    No key: Retail Prices is public; a row's date is its meter's effectiveStartDate. 0: done; 1: a query failed."""
    import json as _json
    import urllib.request
    from pathlib import Path as _Path

    from . import fetch as _fetch   # L-B2's rules: https to prices.azure.com only, a redirect checked first
    opener = opener or _fetch._opener().open
    out = _Path(folder) / "azure"
    out.mkdir(parents=True, exist_ok=True)
    index = {"files": {}}
    for n, q in enumerate(queries(regions, spec)):
        url, items = f"{API}?{urllib.parse.urlencode({'$filter': q})}", []
        try:
            for _ in range(pages):
                req = urllib.request.Request(_fetch.check_url(url), headers={"User-Agent": "jsonui-cli"})
                with opener(req, timeout=60) as resp:
                    page = _json.loads(resp.read().decode("utf-8"))
                items += page.get("Items") or []
                url = page.get("NextPageLink")
                if not url:
                    break
        except Exception as e:   # noqa: BLE001
            log(f"azure: {q}: {type(e).__name__}: {e}")
            return 1
        (out / f"{n}.json").write_text(_json.dumps(items), encoding="utf-8")
        index["files"][q] = f"{n}.json"
        log(f"azure: {len(items)} items: {q}")
    (out / "index.json").write_text(_json.dumps(index, indent=1), encoding="utf-8")
    return 0


def source_of(s: dict, arm_region: str, item: dict) -> str:
    """The query that answers this one meter (the service, where it is listed, the meter, and a VM's size), short
    enough for a row's source."""
    flt = (f"serviceName eq '{s['azure_service']}' and armRegionName eq '{arm_region}' and "
           f"meterName eq '{item.get('meterName')}'")
    if s.get("arm_sku"):
        flt += f" and armSkuName eq '{s['arm_sku']}'"
    return f"{API}?{urllib.parse.urlencode({'$filter': flt})}"[:300]


def rows_from_folder(folder, regions=BUNDLED_REGIONS, spec=None) -> tuple[list[dict], list[str]]:
    """(rows, missing) from <folder>/azure as download wrote it; a global meter makes one row."""
    import json as _json
    from pathlib import Path as _Path
    base = _Path(folder) / "azure"
    if not (base / "index.json").is_file():
        return [], [f"azure: not downloaded ({base}/index.json missing)"]
    index = _json.loads((base / "index.json").read_text(encoding="utf-8"))
    cache: dict[str, list] = {}
    rows, missing, made = [], [], set()
    for s in spec or BUNDLED_SPEC:
        for region in regions:
            arm_region, row_region = arm_of(s, region)
            key = (s["service"], s["sku"], s["unit"], row_region)
            if key in made:
                continue
            q = _query_key(s, arm_region)
            f = index["files"].get(q)
            if f is None:
                missing.append(f"{region}: {s['service']} {s['sku']}: the query was not downloaded")
                continue
            items = cache.setdefault(f, _json.loads((base / f).read_text(encoding="utf-8")))
            hits = [i for i in items if _matches(i, s, arm_region)]
            if not hits:
                missing.append(f"{region}: {s['service']} {s['sku']} ({s['meter']}): no item")
                continue
            row, why = price_row(hits, s, row_region, source_of(s, arm_region, hits[0]))
            if row is None:
                missing.append(f"{region}: {s['service']} {s['sku']}: {why}")
                continue
            made.add(key)
            rows.append(row)
    return rows, missing
