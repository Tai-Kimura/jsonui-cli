"""Each category's formula: one node's hour -> its meters (plan, L-B の作り方の案). A formula knows the shape of a
charge (what is counted, in which unit, under which sku), never a price: the engine finds the price row and applies
its free amount and steps. A provider's rule (infra/rules) passes its constants (an ALB's LCU dimensions) and may name
other skus; the generic rules use these names, so a price file written with them works for any provider.

The skus by convention: instance (the type, instance-hour), storage (GB-month), egress (GB, service data-transfer),
requests (request), compute (GB-second), cpu (ms), plan (month, optional), vcpu (vCPU-hour), memory (GB-hour), get /
put (request), read / write (read_unit / write_unit), capacity (capacity_unit-hour), read-capacity /
write-capacity (capacity_unit-hour, provisioned), egress-<zone> (GB) and
requests-<zone> (request) for a CDN, hour
(instance-hour) and lcu (LCU-hour) for a load balancer, cluster (instance-hour), shard (capacity_unit-hour), rows-read /
rows-written (row), queries (request), emails (email), mau (user), secret (secret), api (request), ingest (GB),
hour (instance-hour) and processed (GB) for a NAT gateway, address (instance-hour) for a public IP address, alarm,
metric, acl and rule (month: each a monthly fee, its share of the month), input-tokens / output-tokens (token) for an
LLM, "<model>:" before them when the load names the model (requests too), and minutes (minute) for a CI service. A node whose spec says an ARM architecture
(arch / cpu_architecture / architecture: arm64, aarch64, graviton) is priced on the ":arm64" skus of its compute
(vcpu, memory, compute).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Meter:
    name: str                    # what the line says it is ("requests", "compute", "instance")
    amount: float                # this hour, in the price's unit
    unit: str                    # the price's unit (infra-prices.v0 $defs/unit)
    sku: str
    quantity: str | None = None  # the load's quantity it comes from (its rate is shown: リクエスト 100/sec)
    service: str | None = None   # a price of another service (data-transfer); None: the node's
    optional: bool = False       # no price is no warning (a plan's monthly fee that only some providers have)


@dataclass
class Hour:
    """One node's hour as a formula reads it."""
    node: dict
    q: dict                       # quantity -> this hour's amount (a flow per hour, a level, a per-request value)
    by_zone: dict = field(default_factory=dict)   # cdn_egress_gb by zone, this hour
    by_sku: dict = field(default_factory=dict)    # quantity -> sku -> this hour's amount (an LLM's tokens by model)
    running: float = 0.0          # instance-hours this hour (0 when stopped)
    sku: str | None = None        # the type this hour (a step, the row's sku)
    hours_in_month: int = 720


def _flow(h: Hour, name: str) -> float:
    return float(h.q.get(name, 0.0))


ARCH_KEYS = ("arch", "cpu_architecture", "architecture")


def arm(node: dict) -> bool:
    """The node's spec says it runs on ARM (Graviton): Fargate's and Lambda's ARM prices are 20-25% under x86's."""
    for item in node.get("spec") or []:
        if isinstance(item, dict) and item.get("key") in ARCH_KEYS and \
                str(item.get("value", "")).strip().lower() in ("arm64", "arm", "aarch64", "graviton"):
            return True
    return False


def _arch(h: Hour, sku: str) -> str:
    return f"{sku}:arm64" if arm(h.node) else sku


def instances(h: Hour, default_sku: str = "instance", name: str = "instance") -> list[Meter]:
    if not h.running:
        return []
    return [Meter(name, h.running, "instance-hour", h.sku or default_sku)]


def stored(h: Hour, sku: str = "storage", quantity: str = "storage_gb") -> list[Meter]:
    """A level in GB held this hour, as its share of a GB-month."""
    if quantity not in h.q:
        return []
    return [Meter("storage", h.q[quantity] / h.hours_in_month, "GB-month", sku, quantity)]


def egress(h: Hour) -> list[Meter]:
    if "egress_gb" not in h.q:
        return []
    return [Meter("egress", _flow(h, "egress_gb"), "GB", "egress", "egress_gb", service="data-transfer")]


def per_month(h: Hour, sku: str, unit: str, quantity: str | None = None, count: float = 1.0, optional: bool = False,
              name: str | None = None) -> list[Meter]:
    """A monthly charge spread over the month's hours (a plan's fee, a secret kept, a monthly active user)."""
    if quantity and quantity not in h.q:   # before reading it: a quantity the load does not give is no charge
        return []
    n = h.q[quantity] if quantity else count
    return [Meter(name or sku, n / h.hours_in_month, unit, sku, quantity, optional=optional)]


def counted(h: Hour, quantity: str, sku: str, unit: str, name: str | None = None) -> list[Meter]:
    if quantity not in h.q:
        return []
    return [Meter(name or quantity, _flow(h, quantity), unit, sku, quantity)]


# ---------------------------------------------------------------- the categories

def vm(h: Hour) -> list[Meter]:
    return instances(h) + stored(h) + egress(h)


def container(h: Hour) -> list[Meter]:
    """Fargate's way when vcpu or memory_gb is given (per task, times the tasks running); else instance-hours."""
    if "vcpu" in h.q or "memory_gb" in h.q:
        out = []
        if "vcpu" in h.q and h.running:
            out.append(Meter("vcpu", h.q["vcpu"] * h.running, "vCPU-hour", _arch(h, "vcpu"), "vcpu"))
        if "memory_gb" in h.q and h.running:
            out.append(Meter("memory", h.q["memory_gb"] * h.running, "GB-hour", _arch(h, "memory"), "memory_gb"))
        return out + egress(h)
    return instances(h) + egress(h)


def function(h: Hour, plan: bool = False) -> list[Meter]:
    """Requests, compute (requests x duration x memory in GB-seconds), CPU time (Workers), and a plan's fee."""
    out = counted(h, "requests", "requests", "request")
    n = _flow(h, "requests")
    if "duration_ms" in h.q and "memory_mb" in h.q:
        out.append(Meter("compute", n * h.q["duration_ms"] / 1000 * h.q["memory_mb"] / 1024, "GB-second",
                         _arch(h, "compute"), "duration_ms"))
    if "cpu_ms" in h.q:
        out.append(Meter("cpu", n * h.q["cpu_ms"], "ms", "cpu", "cpu_ms"))
    if plan:
        out += per_month(h, "plan", "month", optional=True)
    return out + egress(h)


def k8s(h: Hour) -> list[Meter]:
    return instances(h, "cluster", "cluster")


def cdn(h: Hour) -> list[Meter]:
    """Data out by the viewers' zone (egress-<zone>); requests split over the zones as the data is (requests-<zone>),
    or one "requests" when no zone is written."""
    out = [Meter(f"egress-{z}", gb, "GB", f"egress-{z}", "cdn_egress_gb") for z, gb in sorted(h.by_zone.items())]
    total = sum(h.by_zone.values())
    if "requests" in h.q and total > 0:
        out += [Meter(f"requests-{z}", _flow(h, "requests") * gb / total, "request", f"requests-{z}", "requests")
                for z, gb in sorted(h.by_zone.items())]
    else:
        out += counted(h, "requests", "requests", "request")
    return out + egress(h)


ALB = {"new_connections_per_second": 25, "active_connections": 3000, "processed_gb_per_hour": 1,
       "rule_evaluations_per_second": 1000}


def load_balancer(h: Hour, dims: dict | None = None) -> list[Meter]:
    """The hours it runs, and capacity units: lcu as written, else the largest of its dimensions (new connections a
    second, connections open, GB processed an hour, rule evaluations a second) each over what one unit takes."""
    dims = dims or ALB
    out = instances(h, "hour", "hour")
    if "lcu" in h.q:
        lcu = h.q["lcu"]
    else:
        parts = [_flow(h, "new_connections") / 3600 / dims["new_connections_per_second"],
                 h.q.get("active_connections", 0.0) / dims["active_connections"],
                 _flow(h, "processed_gb") / dims["processed_gb_per_hour"]]
        if dims.get("rule_evaluations_per_second"):
            parts.append(_flow(h, "rule_evaluations") / 3600 / dims["rule_evaluations_per_second"])
        lcu = max(parts) if any(k in h.q for k in ("new_connections", "active_connections", "processed_gb",
                                                     "rule_evaluations")) else None
    if lcu is not None and h.running:
        out.append(Meter("lcu", lcu, "LCU-hour", "lcu", "lcu" if "lcu" in h.q else "processed_gb"))
    return out


def gateway(h: Hour) -> list[Meter]:
    return counted(h, "requests", "requests", "request") + egress(h)


def relational(h: Hour, multi_az: bool | None = None) -> list[Meter]:
    """Instance-hours (":multi-az" skus when the node's ha says multi-az), storage, serverless capacity, rows (D1)."""
    multi = "multi" in (h.node.get("ha") or "").lower() if multi_az is None else multi_az
    out = []
    if h.running and "capacity_units" not in h.q:
        sku = h.sku or "instance"
        out.append(Meter("instance", h.running, "instance-hour", f"{sku}:multi-az" if multi else sku))
    out += stored(h, "storage:multi-az" if multi else "storage")
    if "capacity_units" in h.q:
        out.append(Meter("capacity", h.q["capacity_units"], "capacity_unit-hour", "capacity", "capacity_units"))
    out += counted(h, "rows_read", "rows-read", "row") + counted(h, "rows_written", "rows-written", "row")
    return out + egress(h)


def key_value(h: Hour) -> list[Meter]:
    out = counted(h, "read_units", "read", "read_unit") + counted(h, "write_units", "write", "write_unit")
    if "capacity_units" in h.q:
        out.append(Meter("capacity", h.q["capacity_units"], "capacity_unit-hour", "capacity", "capacity_units"))
    return out + stored(h)


def provisioned(h: Hour) -> list[Meter]:
    """Provisioned reads and writes, each its own price (DynamoDB's RCU and WCU): units held this hour."""
    return [Meter(f"{kind}-capacity", h.q[f"{kind}_capacity_units"], "capacity_unit-hour", f"{kind}-capacity",
                  f"{kind}_capacity_units") for kind in ("read", "write") if f"{kind}_capacity_units" in h.q]


def spec_value(node: dict, *keys: str) -> str:
    """The first of ``keys`` the node's spec writes, lower case ("" when none)."""
    for item in node.get("spec") or []:
        if isinstance(item, dict) and item.get("key") in keys:
            return str(item.get("value", "")).strip().lower()
    return ""


def search(h: Hour) -> list[Meter]:
    return instances(h) + stored(h)


def cache(h: Hour) -> list[Meter]:
    out = instances(h) if "capacity_units" not in h.q else []
    if "capacity_units" in h.q:
        out.append(Meter("capacity", h.q["capacity_units"], "capacity_unit-hour", "capacity", "capacity_units"))
    return out + stored(h)


def object_store(h: Hour) -> list[Meter]:
    return (stored(h) + counted(h, "get_requests", "get", "request", "get") + counted(h, "put_requests", "put", "request", "put")
            + egress(h))


def file_store(h: Hour) -> list[Meter]:
    return stored(h)


def queue(h: Hour) -> list[Meter]:
    n = _flow(h, "messages") + _flow(h, "requests")
    if "messages" not in h.q and "requests" not in h.q:
        return []
    return [Meter("requests", n, "request", "requests", "messages" if "messages" in h.q else "requests")]


def stream(h: Hour) -> list[Meter]:
    out = []
    if "capacity_units" in h.q and h.running:
        out.append(Meter("shard", h.q["capacity_units"], "capacity_unit-hour", "shard", "capacity_units"))
    return out + counted(h, "messages", "put", "request", "put")


def scheduler(h: Hour) -> list[Meter]:
    return counted(h, "requests", "requests", "request")


def dns(h: Hour) -> list[Meter]:
    return counted(h, "requests", "queries", "request", "queries") + per_month(h, "zone", "month", optional=True)


def waf(h: Hour, acl_optional: bool = True) -> list[Meter]:
    """Requests, the web ACL's monthly fee (a provider without one: optional) and its rules' (rules: how many)."""
    return (counted(h, "requests", "requests", "request") + per_month(h, "acl", "month", optional=acl_optional)
            + per_month(h, "rule", "month", "rules"))


def mail(h: Hour) -> list[Meter]:
    return counted(h, "emails", "emails", "email")


def auth(h: Hour) -> list[Meter]:
    return per_month(h, "mau", "user", "monthly_active_users")


def secrets(h: Hour) -> list[Meter]:
    return per_month(h, "secret", "secret", "secrets") + counted(h, "requests", "api", "request", "api")


def monitoring(h: Hour) -> list[Meter]:
    """Logs taken in and kept, and custom metrics (metrics: how many are kept; Container Insights' are counted here)."""
    return counted(h, "log_ingest_gb", "ingest", "GB", "ingest") + stored(h) + per_month(h, "metric", "month", "metrics")


def alarm(h: Hour) -> list[Meter]:
    """Alarms, each a monthly fee: the node's count (running) is how many."""
    if not h.running:
        return []
    return [Meter("alarm", h.running / h.hours_in_month, "month", "alarm")]


def nat(h: Hour) -> list[Meter]:
    """A NAT gateway: the hours it runs (each gateway) and the GB it processes."""
    return instances(h, "hour", "hour") + counted(h, "processed_gb", "processed", "GB", "processed")


TOKENS = (("input_tokens", "input-tokens"), ("output_tokens", "output-tokens"))


def saas(h: Hour) -> list[Meter]:
    """A SaaS billed by use (an LLM, a geocoding or a rates API): its requests, and an LLM's tokens in and out. Tokens
    written by sku (by_sku: one node calling two models) are each priced under <sku>:input-tokens /
    <sku>:output-tokens; written as one flow, under the row's sku the same way, else input-tokens / output-tokens. With
    tokens, requests are optional (an LLM bills its tokens; a price per call is still taken when one is written)."""
    out = []
    for quantity, kind in TOKENS:
        if quantity in h.by_sku:
            out += [Meter(f"{sku}:{kind}", n, "token", f"{sku}:{kind}", quantity) for sku, n in sorted(h.by_sku[quantity].items())]
        elif quantity in h.q:
            sku = f"{h.sku}:{kind}" if h.sku else kind
            out.append(Meter(sku, _flow(h, quantity), "token", sku, quantity))
    if "requests" in h.q:
        sku = f"{h.sku}:requests" if h.sku else "requests"
        out.insert(0, Meter("requests", _flow(h, "requests"), "request", sku, "requests", optional=bool(out)))
    return out


def ci(h: Hour) -> list[Meter]:
    """A CI service: the build minutes it bills (a runner's minutes) and the artifacts it keeps."""
    return counted(h, "build_minutes", "minutes", "minute", "minutes") + stored(h)


def ip_address(h: Hour) -> list[Meter]:
    """Public IP addresses: each an hourly charge (the node's count is how many)."""
    return instances(h, "address", "address")


BY_CATEGORY = {
    "compute.vm": vm, "compute.container": container, "compute.function": function, "compute.k8s": k8s,
    "compute.paas": vm, "edge.cdn": cdn, "edge.dns": dns, "edge.waf": waf, "load_balancer": load_balancer,
    "gateway.api": gateway, "database.relational": relational, "database.document": key_value,
    "database.kv": key_value, "database.search": search, "cache": cache, "storage.object": object_store,
    "storage.file": file_store, "storage.block": file_store, "queue": queue, "stream": stream, "scheduler": scheduler,
    "mail": mail, "auth": auth, "secrets": secrets, "monitoring": monitoring, "monitoring.alarm": alarm,
    "gateway.nat": nat, "network.ip": ip_address, "external.saas": saas, "ci": ci,
}


def transfer(gb_by_kind: dict[str, float]) -> list[Meter]:
    """An edge's data this hour: egress_gb out to the internet, transfer_gb between regions (or within one, across
    zones): sku egress, transfer-inter-region, transfer-regional, service data-transfer."""
    return [Meter(kind, gb, "GB", kind, "egress_gb" if kind == "egress" else "transfer_gb", service="data-transfer")
            for kind, gb in gb_by_kind.items() if gb]
