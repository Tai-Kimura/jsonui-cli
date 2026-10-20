"""The generic rules: one per category, what a node of that kind reads and whether it is billed by the hour. No
formula yet (L-B adds the costs, and a provider's own rules beside these)."""
from __future__ import annotations

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
    "edge.waf": (("requests",), False),
    "load_balancer": (LB, True),
    "gateway.api": (("requests", "processed_gb", "egress_gb"), False),
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
    "monitoring": (("log_ingest_gb", "storage_gb"), False),
    "ci": ((), False),
    "external.saas": ((), False),
    "security.iam": ((), False),
    "security.policy": ((), False),
    "monitoring.alarm": ((), False),
}

for _cat, (_reads, _hourly) in GENERIC.items():
    register(Rule(id=f"generic/{_cat}", category=_cat, reads=_reads, hourly=_hourly))
