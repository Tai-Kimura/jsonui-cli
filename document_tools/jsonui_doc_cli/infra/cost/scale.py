"""How many run and which step, hour by hour (plan, 自動スケール / モデルのスケール / 捌ききれなくなった時). Pure
functions over lists of the month's hours. The delays are rounded to whole hours (the simulator counts hours; under
half an hour is none). An approximation of what a real scaler does (by CPU, in minutes): said on the page.
"""
from __future__ import annotations

import math


def wanted(demand: float, per_instance: float, target: float) -> int:
    """Instances that carry ``demand`` at ``target`` of what one takes (per_instance), before min and max."""
    if demand <= 0:
        return 0
    return math.ceil(demand / (per_instance * target) - 1e-9)


def lag_hours(delay_min: int | None) -> int:
    """A delay in whole hours, half an hour and up rounding up (30 -> 1, 89 -> 1, 90 -> 2); round() would go to the
    even hour (30 -> 0, 150 -> 2)."""
    return int((delay_min or 0) / 60 + 0.5)


def autoscale(demand: list[float], per_instance: float | list[float], target: float, mins: list[int], maxs: list[int],
              step: int | None = None, out_delay_min: int | None = None, in_delay_min: int | None = None
              ) -> tuple[list[int], list[bool]]:
    """(instances per hour, the hours it wanted more than max). per_instance is one amount, or one per hour (a vertical
    step's). An hour's want is clamped to its min and max; a rise shows after the scale-out delay, a fall after the
    scale-in delay (whole hours); step is the most it changes in an hour. max 0 (stopped) is 0 at once."""
    per = per_instance if isinstance(per_instance, list) else [per_instance] * len(demand)
    raw = [wanted(d, p, target) for d, p in zip(demand, per)]
    want = [min(max(w, lo), hi) for w, lo, hi in zip(raw, mins, maxs)]
    at_max = [w > hi for w, hi in zip(raw, maxs)]
    out_lag, in_lag = lag_hours(out_delay_min), lag_hours(in_delay_min)
    counts: list[int] = []
    for h, w in enumerate(want):
        if not counts:
            counts.append(w)
            continue
        prev = counts[-1]
        lag = out_lag if w > prev else in_lag
        goal = want[h - lag] if h - lag >= 0 and lag else w
        goal = min(max(goal, mins[h]), maxs[h])          # the hour's own range holds whatever the lag says
        if step and goal != prev:
            goal = prev + max(-step, min(step, goal - prev))
        counts.append(0 if maxs[h] == 0 else goal)
    return counts, at_max


def step_index(ladder: list[dict], sku: str) -> int:
    return [s["sku"] for s in ladder].index(sku)


def vertical(demand: list[float], ladder: list[dict], target: float, min_skus: list[str], max_skus: list[str],
             order: str, counts_lo: list[float], counts_hi: list[float], change_delay_min: int | None = 60,
             per_hours: float = 1.0) -> list[str]:
    """The step (sku) per hour. Each step's amount is what one instance takes (per ``per_hours`` hours: 1/3600 for a
    "per second" amount). Within the hour's range of steps:
    - schedule_vertical: the smallest step that the most instances allowed (counts_hi) can carry;
    - vertical_first: the smallest step the fewest instances (counts_lo) can carry;
    - horizontal_first: the smallest step the most instances can carry (instances first, steps after).
    No step carries it: the hour's largest. A step with no amount (vcpu / memory only): the range's smallest. A change
    shows after change_delay_min (whole hours): the step picked that many hours before, held to this hour's range."""
    lag = lag_hours(change_delay_min)
    picked: list[str] = []
    for h, d in enumerate(demand):
        lo, hi = step_index(ladder, min_skus[h]), step_index(ladder, max_skus[h])
        steps = ladder[lo:hi + 1]
        n = counts_lo[h] if order == "vertical_first" else counts_hi[h]
        fit = [s for s in steps if "amount" in s and n * s["amount"] / per_hours * target >= d]
        picked.append((fit[0] if fit else steps[-1] if any("amount" in s for s in steps) else steps[0])["sku"])
    if not lag:
        return picked
    out = []                       # what was picked lag hours before, held to this hour's range
    for h in range(len(picked)):
        k = step_index(ladder, picked[max(0, h - lag)])
        lo, hi = step_index(ladder, min_skus[h]), step_index(ladder, max_skus[h])
        out.append(ladder[min(max(k, lo), hi)]["sku"])
    return out


def capacity(count: float, per_instance: float | None) -> float | None:
    """What the instances can take in the hour, or None (no per-instance amount: capacity undefined)."""
    return None if per_instance is None else count * per_instance


def served(demand: float, cap: float | None) -> tuple[float, float]:
    """(served, overflow): all of it when the capacity is undefined (not judged)."""
    if cap is None:
        return demand, 0.0
    return min(demand, cap), max(0.0, demand - cap)
