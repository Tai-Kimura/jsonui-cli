"""Azure's rules (Retail Prices read 2026-10-21; prices in the bundled table, built by azure_prices). The generic
formulas with Azure's shapes where they differ: a managed disk billed by its size's tier, a month each; a load
balancer by its rules' hours and the data it processes; a database's high availability as a standby of the same
size; the WAF of a node that does not say its kind priced as Application Gateway WAF v2's (and said)."""
from __future__ import annotations

from .. import model as M
from ..cost import formulas as F
from ..cost.azure_prices import DISK_TIERS
from . import provider_rule

CHECKED = "2026-10-21"
PAGES = {
    "vm": "https://azure.microsoft.com/pricing/details/virtual-machines/linux/",
    "appservice": "https://azure.microsoft.com/pricing/details/app-service/linux/",
    "staticwebapps": "https://azure.microsoft.com/pricing/details/app-service/static/",
    "aci": "https://azure.microsoft.com/pricing/details/container-instances/",
    "containerapps": "https://azure.microsoft.com/pricing/details/container-apps/",
    "functions": "https://azure.microsoft.com/pricing/details/functions/",
    "aks": "https://azure.microsoft.com/pricing/details/kubernetes-service/",
    "mysql": "https://azure.microsoft.com/pricing/details/mysql/flexible-server/",
    "postgresql": "https://azure.microsoft.com/pricing/details/postgresql/flexible-server/",
    "sql": "https://azure.microsoft.com/pricing/details/azure-sql-database/single/",
    "redis": "https://azure.microsoft.com/pricing/details/cache/",
    "search": "https://azure.microsoft.com/pricing/details/search/",
    "dns": "https://azure.microsoft.com/pricing/details/dns/",
    "frontdoor": "https://azure.microsoft.com/pricing/details/frontdoor/",
    "waf": "https://azure.microsoft.com/pricing/details/web-application-firewall/",
    "apim": "https://azure.microsoft.com/pricing/details/api-management/",
    "appgateway": "https://azure.microsoft.com/pricing/details/application-gateway/",
    "lb": "https://azure.microsoft.com/pricing/details/load-balancer/",
    "monitor": "https://azure.microsoft.com/pricing/details/monitor/",
    "eventhubs": "https://azure.microsoft.com/pricing/details/event-hubs/",
    "disk": "https://azure.microsoft.com/pricing/details/managed-disks/",
}
WAF_KINDS = ("appgateway", "frontdoor")


def _r(name, category, service, cost, page=None, **extra):
    provider_rule(f"azure/{name}", category, "azure", service, cost, PAGES[page or name], CHECKED, **extra)


def disk_tier(gb: float, premium: bool = False) -> str:
    """The managed disk tier a size is billed at: the smallest tier holding it (128 GB is E10, 129 GB E15)."""
    kind = "P" if premium else "E"
    for n, size in DISK_TIERS.items():
        if gb <= size:
            return f"{kind}{n}"
    return f"{kind}{list(DISK_TIERS)[-1]}"


def _premium(node: dict) -> bool:
    return "premium" in F.spec_value(node, "sku", "storage_account_type", "disk_sku")


def disk(h: F.Hour, service: str | None = None) -> list[F.Meter]:
    """A managed disk: its tier's monthly price (Standard SSD; Premium SSD when the spec says so), whatever is
    written on it — the node's count is how many disks. ``service``: "disk" for a VM's OS disk (the disk's rows)."""
    if "storage_gb" not in h.q:
        return []
    count = h.running or 1.0
    return [F.Meter("storage", count / h.hours_in_month, "month", disk_tier(h.q["storage_gb"], _premium(h.node)),
                    "storage_gb", service=service)]


def vm(h: F.Hour) -> list[F.Meter]:
    """A VM: its size by the hour, its OS disk as a managed disk's tier, and its egress."""
    return F.instances(h) + disk(h, "disk") + F.egress(h)


def app_plan(h: F.Hour) -> list[F.Meter]:
    """An App Service plan: its size by the hour (storage comes with the plan) and its egress."""
    return F.instances(h) + F.egress(h)


def static_web_app(h: F.Hour) -> list[F.Meter]:
    """Static Web Apps (Standard): an app's monthly fee and its bandwidth (100 GB a month free: the meter's step)."""
    out = F.per_month(h, "plan", "month") if h.running else []
    return out + F.counted(h, "egress_gb", "bandwidth", "GB", "bandwidth")


def database(h: F.Hour) -> list[F.Meter]:
    """A Flexible Server or SQL Database: its size by the hour and its storage; zone-redundant high availability
    (ha multi-az) is a standby of the same size and storage, billed again."""
    copies = 2.0 if "multi" in (h.node.get("ha") or "").lower() else 1.0
    out = [F.Meter("instance", h.running * copies, "instance-hour", h.sku or "instance")] if h.running else []
    if "storage_gb" in h.q:
        out.append(F.Meter("storage", h.q["storage_gb"] * copies / h.hours_in_month, "GB-month", "storage",
                           "storage_gb"))
    return out + F.egress(h)


def load_balancer(h: F.Hour) -> list[F.Meter]:
    """Standard Load Balancer: its included rules by the hour, and the data it processes."""
    return F.instances(h, "hour", "hour") + F.counted(h, "processed_gb", "processed", "GB", "processed")


def waf_kind(node: dict) -> tuple[str, bool]:
    """(the WAF's kind, whether the node said it): the spec's kind / attached_to, else Application Gateway WAF v2."""
    said = F.spec_value(node, "kind", "attached_to", "waf_kind")
    for kind in WAF_KINDS:
        if kind in said.replace(" ", "").replace("_", "").replace("-", ""):
            return kind, True
    return "appgateway", False


def waf(h: F.Hour) -> list[F.Meter]:
    """Application Gateway WAF v2: the gateway's hours and its capacity units (capacity_units; lcu as the ALB's).
    A Front Door WAF policy is not bundled: its policy, rules and requests are listed for a person's price file."""
    if waf_kind(h.node)[0] == "frontdoor":
        return (F.counted(h, "requests", "requests", "request") + F.per_month(h, "acl", "month")
                + F.per_month(h, "rule", "month", "rules"))
    out = F.instances(h, "hour", "hour")
    units = h.q.get("capacity_units", h.q.get("lcu"))
    if units is not None and h.running:
        out.append(F.Meter("capacity", units, "capacity_unit-hour", "capacity", "capacity_units"))
    return out


def waf_notice(node, quantities, running):
    kind, said = waf_kind(node)
    if said:
        name = "Front Door" if kind == "frontdoor" else "Application Gateway"
        return [("cost.waf_kind", M.Why(f"WAF priced as {name} WAF (the node's spec says so)", "cost.waf_kind.said",
                                        kind=name))]
    return [("cost.waf_kind", M.Why("WAF priced as Application Gateway WAF v2 (the node does not say its kind; spec "
                                    "kind: frontdoor to price a Front Door policy)", "cost.waf_kind.default"))]


def cdn(h: F.Hour) -> list[F.Meter]:
    """Front Door Standard: by the viewers' zone, and the profile's base fee a month."""
    return F.cdn(h) + (F.per_month(h, "plan", "month") if h.node.get("service") == "frontdoor" else [])


_r("vm", "compute.vm", "vm", vm)
_r("vmss", "compute.vm", "vmss", vm, "vm")
_r("appservice", "compute.paas", "appservice", app_plan, reads=("requests", "egress_gb"))
_r("staticwebapps", "compute.paas", "staticwebapps", static_web_app, reads=("requests", "egress_gb"))
_r("aci", "compute.container", "aci", F.container)
_r("containerapps", "compute.container", "containerapps", F.container)
_r("functions", "compute.function", "functions", F.function,
   reads=("requests", "duration_ms", "memory_mb", "concurrency", "egress_gb"))
_r("aks", "compute.k8s", "aks", F.k8s)
for _engine in ("mysql", "postgresql", "sql"):
    _r(_engine, "database.relational", _engine, database, reads=("requests", "storage_gb", "egress_gb"))
_r("redis", "cache", "redis", F.instances, reads=("requests",))
_r("search", "database.search", "search", F.instances, reads=("requests",))
_r("frontdoor", "edge.cdn", "frontdoor", cdn)
_r("cdn", "edge.cdn", "cdn", cdn, "frontdoor")
_r("waf", "edge.waf", "waf", waf, reads=("requests", "rules", "capacity_units", "lcu"), hourly=True,
   notice=waf_notice)
_r("lb", "load_balancer", "lb", load_balancer, reads=("processed_gb", "requests"))
_r("loganalytics", "monitoring", "loganalytics", F.monitoring, "monitor", reads=("log_ingest_gb", "storage_gb"))
_r("appinsights", "monitoring", "appinsights", F.monitoring, "monitor", reads=("log_ingest_gb", "storage_gb"))
_r("eventhubs", "stream", "eventhubs", F.stream)
_r("disk", "storage.block", "disk", disk, hourly=True)
