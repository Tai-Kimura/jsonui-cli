"""The pricing rules: one place where each kind of node says how it is priced (plan
docs/plans/2026-10-20-jui-viz-backend-load-and-cost-simulator.md, 作りの決まり 4).

A rule declares what it reads and how it is billed; the simulator's body knows no kind. L-A (the load schema and its
validate) reads only ``reads`` and ``hourly``: which quantities mean something on a node, and whether a schedule,
autoscale or vertical scaling does. The cost (L-B) adds to a rule its formula, the units and skus it looks up in the
price files, and the official page it follows (``source``, ``checked``); a provider's or a service's own rule is
registered beside the generic one and wins by being more specific (provider and service > provider > category).

The generic rules (generic.py) are registered when this package is imported.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Rule:
    id: str                          # "generic/compute.function", "aws/lambda"
    category: str
    provider: str | None = None
    service: str | None = None       # the node's service, or its head before "." ("rds" for "rds.mysql")
    reads: tuple[str, ...] = ()      # the quantities it reads (names in infra-load.v0's $defs/quantities)
    hourly: bool = False             # billed for the time it runs: schedules, autoscale and vertical mean something
    source: str = ""                 # the official pricing page (L-B)
    checked: str = ""                # the day the page was read (L-B)
    extra: dict = field(default_factory=dict, compare=False)   # what the cost's rule adds (units, skus, formula)
    cost: Callable | None = field(default=None, compare=False)


REGISTRY: list[Rule] = []


def register(rule: Rule) -> Rule:
    """Add a rule; one with the same id replaces the earlier (a rule is changed in one place)."""
    REGISTRY[:] = [r for r in REGISTRY if r.id != rule.id] + [rule]
    return rule


def _service_matches(want: str, have: str) -> bool:
    return have == want or have.split(".", 1)[0] == want


def lookup(node: dict) -> Rule | None:
    """The most specific rule for a merged model's node (its category, providerResolved and service), or None."""
    cat, prov, svc = node.get("category"), node.get("providerResolved") or node.get("provider") or "", node.get("service") or ""
    best, rank = None, -1
    for r in REGISTRY:
        if r.category != cat or (r.provider and r.provider != prov) or (r.service and not _service_matches(r.service, svc)):
            continue
        k = (2 if r.service else 0) + (1 if r.provider else 0)
        if k > rank:
            best, rank = r, k
    return best


def provider_rule(id: str, category: str, provider: str, service: str, cost: Callable, source: str, checked: str,
                  **extra) -> Rule:
    """A provider's rule for a category: what it reads and whether it is billed by the hour as the generic rule says
    (``reads`` / ``hourly`` in extra change them), its formula, and the official page it follows."""
    from .generic import GENERIC   # noqa: PLC0415
    reads, hourly = GENERIC[category]
    return register(Rule(id=id, category=category, provider=provider, service=service, reads=extra.pop("reads", reads),
                         hourly=extra.pop("hourly", hourly), source=source, checked=checked, extra=extra, cost=cost))


from . import generic  # noqa: E402,F401  (registers the generic rules)
from . import aws  # noqa: E402,F401
from . import cloudflare  # noqa: E402,F401
