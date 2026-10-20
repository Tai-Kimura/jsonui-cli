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


#: Zero Trust (the plans page read 2026-10-21): "Free" is "50 users", "Pay-as-you-go" "$7 /user/month" — past 50 the
#: account is on Pay-as-you-go and every user is a seat, not only the 51st.
ACCESS_FREE_USERS = 50


def access(h: F.Hour) -> list[F.Meter]:
    """Zero Trust seats: 50 users or fewer cost 0 (the Free plan); more, every user at the seat's price."""
    if "monthly_active_users" not in h.q:
        return []
    users = h.q["monthly_active_users"]
    return [F.Meter("seat", users / h.hours_in_month if users > ACCESS_FREE_USERS else 0.0, "user", "seat",
                    "monthly_active_users")]


def load_balancer(h: F.Hour) -> list[F.Meter]:
    """Load Balancing's base fee, a month (the page says "Starting at $5/mo"; what the endpoints and DNS queries past
    the base add is not on a public page)."""
    return F.per_month(h, "plan", "month") if h.running else []


provider_rule("cloudflare/workers", "compute.function", "cloudflare", "workers", partial(F.function, plan=True),
              "https://developers.cloudflare.com/workers/platform/pricing/", CHECKED)
provider_rule("cloudflare/r2", "storage.object", "cloudflare", "r2", r2,
              "https://developers.cloudflare.com/r2/pricing/", CHECKED)
provider_rule("cloudflare/d1", "database.relational", "cloudflare", "d1", d1,
              "https://developers.cloudflare.com/d1/platform/pricing/", CHECKED, hourly=False,
              reads=("rows_read", "rows_written", "storage_gb", "requests"))
provider_rule("cloudflare/queues", "queue", "cloudflare", "queues", sqs,
              "https://developers.cloudflare.com/queues/platform/pricing/", CHECKED)
provider_rule("cloudflare/kv", "database.kv", "cloudflare", "kv", F.key_value,
              "https://developers.cloudflare.com/kv/platform/pricing/", "2026-10-21",
              reads=("read_units", "write_units", "storage_gb", "requests"))   # no provisioned capacity
provider_rule("cloudflare/access", "auth", "cloudflare", "access", access,
              "https://www.cloudflare.com/plans/sase-zero-trust/", "2026-10-21")
provider_rule("cloudflare/lb", "load_balancer", "cloudflare", "lb", load_balancer,
              "https://www.cloudflare.com/plans/network-cdn/", "2026-10-21", reads=())
