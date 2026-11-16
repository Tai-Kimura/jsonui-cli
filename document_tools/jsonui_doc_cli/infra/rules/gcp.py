"""Google Cloud's rules (the catalog read 2026-10-21 through the Cloud Billing Catalog API; prices in the bundled
table, built by gcp_prices). An instance is billed by its vCPUs and its memory, not by its type: Compute Engine and
Cloud SQL read the type and price the two apart."""
from __future__ import annotations

import re

from .. import model as M
from ..cost import formulas as F
from . import provider_rule

CHECKED = "2026-10-21"
PAGES = {
    "run": "https://cloud.google.com/run/pricing",
    "functions": "https://cloud.google.com/functions/pricing",
    "gce": "https://cloud.google.com/compute/vm-instance-pricing",
    "pd": "https://cloud.google.com/compute/disks-image-pricing",
    "cloudsql": "https://cloud.google.com/sql/pricing",
    "memorystore": "https://cloud.google.com/memorystore/docs/redis/pricing",
    "gcs": "https://cloud.google.com/storage/pricing",
    "secretmanager": "https://cloud.google.com/secret-manager/pricing",
    "kms": "https://cloud.google.com/kms/pricing",
    "clouddns": "https://cloud.google.com/dns/pricing",
    "gke": "https://cloud.google.com/kubernetes-engine/pricing",
    "artifactregistry": "https://cloud.google.com/artifact-registry/pricing",
}

#: machine type -> (family, vCPUs billed, GB of memory); e2's shared-core types bill a fraction of their 2 vCPUs
MACHINES = {
    "e2-micro": ("e2", 0.25, 1), "e2-small": ("e2", 0.5, 2), "e2-medium": ("e2", 1, 4),
    "e2-standard-2": ("e2", 2, 8), "e2-standard-4": ("e2", 4, 16), "e2-standard-8": ("e2", 8, 32),
    "e2-highmem-2": ("e2", 2, 16), "e2-highcpu-2": ("e2", 2, 2),
    "n2-standard-2": ("n2", 2, 8), "n2-standard-4": ("n2", 4, 16), "n2-standard-8": ("n2", 8, 32),
    "n2-highmem-2": ("n2", 2, 16), "n2-highcpu-2": ("n2", 2, 2),
}
_CUSTOM_SQL = re.compile(r"^db-custom-(\d+)-(\d+)$")


def _r(name, category, service, cost, **extra):
    provider_rule(f"gcp/{name}", category, "gcp", service, cost, PAGES[name.split("-")[0]], CHECKED, **extra)


def run(h: F.Hour) -> list[F.Meter]:
    """Cloud Run, request-based billing: vCPU and memory while serving, and the requests."""
    return F.container(h) + F.counted(h, "requests", "requests", "request")


def vcpu_and_ram(h: F.Hour, family: str, vcpus: float, gb: float, multi: bool = False) -> list[F.Meter]:
    tag = ":multi-az" if multi else ""
    if not h.running:
        return []
    return [F.Meter("vcpu", vcpus * h.running, "vCPU-hour", f"{family}vcpu{tag}"),
            F.Meter("memory", gb * h.running, "GB-hour", f"{family}ram{tag}")]


def gce(h: F.Hour) -> list[F.Meter]:
    """A VM: its type's vCPUs and memory by the hour (a type not in MACHINES is priced as written, as the generic
    rule does), its boot disk's storage and its egress."""
    machine = MACHINES.get(h.sku or "")
    out = vcpu_and_ram(h, f"{machine[0]}:", machine[1], machine[2]) if machine else F.instances(h)
    return out + F.stored(h) + F.egress(h)


def cloudsql(h: F.Hour) -> list[F.Meter]:
    """Cloud SQL: a custom tier's vCPUs and memory (db-custom-<vCPUs>-<MB>), regional (ha multi-az) on the
    :multi-az skus, and storage."""
    multi = "multi" in (h.node.get("ha") or "").lower()
    m = _CUSTOM_SQL.match(h.sku or "")
    out = vcpu_and_ram(h, "", int(m[1]), int(m[2]) / 1024, multi) if m else F.instances(h)
    return out + F.stored(h, "storage:multi-az" if multi else "storage") + F.egress(h)


def memorystore(h: F.Hour) -> list[F.Meter]:
    """Memorystore for Redis: the instance's GB by the hour, at its tier's (basic / standard) and capacity band's
    rate (M1 1-4 GB, M2 5-10, M3 11-35, M4 36-100, M5 over 100)."""
    if not h.running:
        return []
    size = float(F.spec_value(h.node, "memory_size_gb") or 1)
    tier = "standard" if "standard" in F.spec_value(h.node, "tier") else "basic"
    band = next(b for b, top in (("m1", 4), ("m2", 10), ("m3", 35), ("m4", 100), ("m5", float("inf"))) if size <= top)
    return [F.Meter("capacity", size * h.running, "GB-hour", f"{tier}:{band}")]


def run_grant_notice(node, quantities, running):
    """Said, not silent: the free vCPU and memory a billing account gets a month is not taken off."""
    return [("cost.free_not_counted", M.Why("Cloud Run's monthly free vCPU-seconds and GiB-seconds (per billing account) "
                                            "are not taken off: the Cloud Billing Catalog does not list them and the page "
                                            "could not be read — vCPU and memory are priced from the first second (the "
                                            "free 2 million requests are counted)", "cost.free_not_counted.run"))]


def gke_credit_notice(node, quantities, running):
    return [("cost.free_not_counted", M.Why("GKE's monthly free credit for the cluster management fee (per billing "
                                            "account) is not taken off: the fee is priced from the first hour",
                                            "cost.free_not_counted.gke"))]


def kms(h: F.Hour) -> list[F.Meter]:
    return F.per_month(h, "key", "month", "secrets", name="key") + F.counted(h, "requests", "api", "request", "api")


def registry(h: F.Hour) -> list[F.Meter]:
    return F.stored(h)


_r("run-job", "compute.container", "run.job", F.container)    # before run: a run.job node is a job's
_r("run", "compute.container", "run", run, reads=("requests", "vcpu", "memory_gb", "egress_gb"),
   notice=run_grant_notice)
_r("functions", "compute.function", "functions", F.function,
   reads=("requests", "duration_ms", "memory_mb", "concurrency", "egress_gb"))
_r("gce", "compute.vm", "gce", gce)
_r("pd", "storage.block", "pd", F.file_store)
_r("cloudsql", "database.relational", "cloudsql", cloudsql, reads=("requests", "storage_gb", "egress_gb"))
_r("memorystore", "cache", "memorystore", memorystore, reads=("requests",))
_r("gcs", "storage.object", "gcs", F.object_store)
_r("secretmanager", "secrets", "secretmanager", F.secrets)
_r("kms", "secrets", "kms", kms)
_r("clouddns", "edge.dns", "clouddns", F.dns)
_r("gke", "compute.k8s", "gke", F.k8s, notice=gke_credit_notice)
_r("artifactregistry", "ci", "artifactregistry", registry, reads=("storage_gb",))
