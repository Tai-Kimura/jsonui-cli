"""Cloudflare's rules (the official pages read 2026-10-20). What a plan includes (Workers' 10 million requests and 30
million CPU ms, R2's free tier, D1's rows) is the price rows' free amount, not code."""
from __future__ import annotations

from functools import partial

from ..cost import formulas as F
from . import provider_rule
from .aws import sqs

CHECKED = "2026-10-20"


def r2(h: F.Hour) -> list[F.Meter]:
    """R2: storage, class A (put) and class B (get); data out is free (no egress meter)."""
    return [m for m in F.object_store(h) if m.name != "egress"]


def d1(h: F.Hour) -> list[F.Meter]:
    """D1: rows read, rows written and storage; no instance-hours."""
    return F.counted(h, "rows_read", "rows-read", "row") + F.counted(h, "rows_written", "rows-written", "row") + F.stored(h)


provider_rule("cloudflare/workers", "compute.function", "cloudflare", "workers", partial(F.function, plan=True),
              "https://developers.cloudflare.com/workers/platform/pricing/", CHECKED)
provider_rule("cloudflare/r2", "storage.object", "cloudflare", "r2", r2,
              "https://developers.cloudflare.com/r2/pricing/", CHECKED)
provider_rule("cloudflare/d1", "database.relational", "cloudflare", "d1", d1,
              "https://developers.cloudflare.com/d1/platform/pricing/", CHECKED, hourly=False,
              reads=("rows_read", "rows_written", "storage_gb", "requests"))
provider_rule("cloudflare/queues", "queue", "cloudflare", "queues", sqs,
              "https://developers.cloudflare.com/queues/platform/pricing/", CHECKED)
