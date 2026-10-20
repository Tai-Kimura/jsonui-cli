"""The charges, each a pure function. A price row is infra-prices.v0's (price_usd or tiers, per_units, free); amounts
are in the row's unit. The month's total so far (``before``) decides the free amount and the step: a price's free
amount and steps are the account's, shared by every node priced by the same row."""
from __future__ import annotations


def billable(before: float, add: float, free: float) -> tuple[float, float]:
    """The part of [before, before + add] above the free amount, as (from, to) in billable units."""
    return max(0.0, before - free), max(0.0, before + add - free)


def flat(lo: float, hi: float, price_usd: float, per_units: float) -> float:
    return (hi - lo) * price_usd / per_units


def tiered(lo: float, hi: float, tiers: list[dict], per_units: float) -> tuple[float, list[int]]:
    """The charge of [lo, hi] of the month's billable units on stepped prices, and the steps it touched."""
    usd, touched = 0.0, []
    for k, t in enumerate(tiers):
        a, b = max(lo, t["from"]), min(hi, t.get("to", float("inf")))
        if b > a:
            usd += (b - a) * t["price_usd"] / per_units
            touched.append(k)
    return usd, touched


def charge(before: float, add: float, row: dict) -> tuple[float, dict]:
    """(usd, detail) for ``add`` units this hour after ``before`` this month, on one price row. detail: free (the
    units this hour inside the free amount) and tiers (the steps touched)."""
    free = (row.get("free") or {}).get("amount", 0.0)
    lo, hi = billable(before, add, free)
    per = row.get("per_units", 1) or 1
    detail = {"free": add - (hi - lo)}
    if "tiers" in row:
        usd, detail["tiers"] = tiered(lo, hi, row["tiers"], per)
    else:
        usd = flat(lo, hi, row["price_usd"], per)
    return usd, detail
