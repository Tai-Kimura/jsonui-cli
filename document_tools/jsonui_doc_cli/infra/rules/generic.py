"""The generic rules: one per category, what a node of that kind reads, whether it is billed by the hour, and its
formula (infra/cost/formulas.py) under the conventional skus: a price file written with those names prices any
provider. A provider's own rules (aws.py, cloudflare.py) sit beside these and win by being more specific."""
from __future__ import annotations

from ..cost import formulas as F
from . import Rule, register

LB = ("lcu", "new_connections", "active_connections", "processed_gb", "rule_evaluations", "requests")
GENERIC: dict[str, tuple[tuple[str, ...], bool]] = {   # category: (reads, hourly)
    "client": ((), False),
    "compute.vm": (("requests", "egress_gb", "storage_gb"), True),
    "compute.container": (("requests", "concurrency", "vcpu", "memory_gb", "duration_ms", "egress_gb"), True),
    "compute.function": (("requests", "duration_ms", "memory_mb", "cpu_ms", "concurrency", "egress_gb"), False),
    "compute.k8s": (("requests",), True),
    "compute.paas": (("requests", "egress_gb", "storage_gb"), True),
    "edge.cdn": (("requests", "cdn_egress_gb", "egress_gb"), False),
    "edge.dns": (("requests",), False),
    "edge.waf": (("requests", "rules"), False),
    "load_balancer": (LB, True),
    "gateway.api": (("requests", "processed_gb", "egress_gb"), False),
    "gateway.nat": (("processed_gb",), True),
    "network.ip": ((), True),
    "database.relational": (("requests", "rows_read", "rows_written", "storage_gb", "capacity_units", "egress_gb"), True),
    "database.document": (("requests", "read_units", "write_units", "storage_gb", "capacity_units"), False),
    "database.kv": (("requests", "read_units", "write_units", "storage_gb", "capacity_units"), False),
    "database.search": (("requests", "storage_gb"), True),
    "cache": (("requests", "storage_gb", "capacity_units"), True),
    "storage.object": (("get_requests", "put_requests", "storage_gb", "egress_gb"), False),
    "storage.file": (("requests", "storage_gb"), False),
    "storage.block": (("storage_gb",), False),
    "queue": (("messages", "requests"), False),
    "stream": (("messages", "capacity_units"), True),
    "scheduler": (("requests",), False),
    "mail": (("emails",), False),
    "auth": (("monthly_active_users", "requests"), False),
    "secrets": (("secrets", "requests"), False),
    "monitoring": (("log_ingest_gb", "storage_gb", "metrics"), False),
    "ci": (("build_minutes", "storage_gb"), False),
    "external.saas": (("requests", "input_tokens", "output_tokens"), False),
    "security.iam": ((), False),
    "security.policy": ((), False),
    "monitoring.alarm": ((), True),
}

for _cat, (_reads, _hourly) in GENERIC.items():
    register(Rule(id=f"generic/{_cat}", category=_cat, reads=_reads, hourly=_hourly, cost=F.BY_CATEGORY.get(_cat)))
