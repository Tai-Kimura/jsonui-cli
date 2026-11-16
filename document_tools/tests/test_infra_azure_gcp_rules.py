"""Azure's and Google Cloud's bundled prices through their rules (the bundled table: Retail Prices and the Cloud
Billing Catalog read 2026-10-21), each against a hand count of a 730-hour month from the row's own price."""
from __future__ import annotations

import pytest

from jsonui_doc_cli.infra import rules as RULES
from jsonui_doc_cli.infra.cost import engine as E
from jsonui_doc_cli.infra.cost import formulas as F
from jsonui_doc_cli.infra.cost import pricebook as PB
from jsonui_doc_cli.infra.rules import azure as AZR

BOOK = PB.Book(bundled=PB.bundled_rows())
ON = "2027-06-01"


def node(provider, id_, cat, svc, **extra):
    return {"id": id_, "category": cat, "provider": provider, "providerResolved": provider, "service": svc, **extra}


def month(n, q, running, hours=730, region="japaneast", totals=None):
    """usd by meter of one node over a month (totals: shared with other nodes, for a pool's free amount)."""
    rule, totals, usd = RULES.lookup(n), {} if totals is None else totals, {}
    for _ in range(hours):
        for m in rule.cost(F.Hour(node=n, q=q, running=running, sku=q.get("_sku"), hours_in_month=hours)):
            got = E.price_meter(BOOK, totals, m, n, region, ON)[0]
            assert got is not None, (n["id"], m)
            usd[m.name] = usd.get(m.name, 0.0) + got
    return usd


def price(provider, service, sku, unit, region):
    return BOOK.find(provider, service, sku, unit, region, ON)["row"]


def az(*a, **k):
    return node("azure", *a, **k)


def gcp(*a, **k):
    return node("gcp", *a, **k)


@pytest.mark.parametrize("gb, tier", [(32, "E4"), (128, "E10"), (129, "E15"), (4096, "E50"), (5000, "E50")])
def test_a_managed_disk_is_billed_at_the_smallest_tier_holding_it(gb, tier):
    assert AZR.disk_tier(gb) == tier and AZR.disk_tier(gb, premium=True) == "P" + tier[1:]


@pytest.mark.parametrize("gb, usd", [(128, 9.6), (129, 19.2)])
def test_a_disk_at_a_tiers_edge_costs_that_tiers_month(gb, usd):
    """japaneast Standard SSD: E10 (128 GB) $9.60 a month, E15 (256 GB) $19.20 — 129 GB is E15's price."""
    got = month(az("d", "storage.block", "disk"), {"storage_gb": float(gb)}, 1)
    assert round(sum(got.values()), 6) == usd
    prem = month(az("d", "storage.block", "disk", spec=[{"key": "sku", "value": "Premium_LRS"}]), {"storage_gb": 128.0}, 1)
    assert round(sum(prem.values()), 4) == round(price("azure", "disk", "P10", "month", "japaneast")["price_usd"], 4)


def test_a_vm_is_its_size_by_the_hour_and_its_os_disk_tier():
    got = month(az("vm", "compute.vm", "vm"), {"_sku": "Standard_B2s", "storage_gb": 100.0}, 1)
    assert {k: round(v, 4) for k, v in got.items()} == {"instance": round(0.0544 * 730, 4), "storage": 9.6}


def test_container_apps_take_the_subscriptions_grant_once_across_apps():
    """The Consumption grant (the page: 180,000 vCPU-seconds and 360,000 GiB-seconds a month per subscription) is
    one pool: two apps of 0.25 vCPU / 0.5 GB share 50 vCPU-hours and 100 GB-hours, not 50 each."""
    rate_v = price("azure", "containerapps", "vcpu", "vCPU-hour", "japaneast")["price_usd"]
    rate_m = price("azure", "containerapps", "memory", "GB-hour", "japaneast")["price_usd"]
    assert (round(rate_v, 6), round(rate_m, 6)) == (0.0864, 0.0108)
    totals: dict = {}
    usd = [month(az(f"app{i}", "compute.container", "containerapps"), {"vcpu": 0.25, "memory_gb": 0.5}, 1,
                 totals=totals) for i in (1, 2)]
    vcpu = sum(u["vcpu"] for u in usd)
    memory = sum(u["memory"] for u in usd)
    assert round(vcpu, 4) == round((0.5 * 730 - 50) * rate_v, 4)
    assert round(memory, 4) == round((1.0 * 730 - 100) * rate_m, 4)


def test_a_waf_that_does_not_say_its_kind_is_application_gateway_waf_v2_and_says_so():
    plain = az("waf", "edge.waf", "waf")
    got = month(plain, {"capacity_units": 2.0}, 1)
    hour = price("azure", "waf", "hour", "instance-hour", "japaneast")["price_usd"]
    unit = price("azure", "waf", "capacity", "capacity_unit-hour", "japaneast")["price_usd"]
    assert {k: round(v, 4) for k, v in got.items()} == {"hour": round(hour * 730, 4), "capacity": round(unit * 2 * 730, 4)}
    notice = RULES.lookup(plain).extra["notice"]
    assert "Application Gateway WAF v2" in notice(plain, {}, [1])[0][1] and "does not say" in notice(plain, {}, [1])[0][1]
    fd = az("waf", "edge.waf", "waf", spec=[{"key": "kind", "value": "Front Door"}])
    assert {m.sku for m in RULES.lookup(fd).cost(F.Hour(node=fd, q={"requests": 1.0, "rules": 2.0}, running=1.0))} == {
        "requests", "acl", "rule"}
    assert "Front Door" in notice(fd, {}, [1])[0][1] and "spec says so" in notice(fd, {}, [1])[0][1]


def test_a_flexible_servers_high_availability_is_a_standby_of_the_same_size():
    one = month(az("db", "database.relational", "mysql"), {"_sku": "B_Standard_B1ms", "storage_gb": 20.0}, 1)
    ha = month(az("db", "database.relational", "mysql", ha="multi-az"), {"_sku": "B_Standard_B1ms", "storage_gb": 20.0}, 1)
    assert round(one["instance"], 4) == round(0.026 * 730, 4) and round(one["storage"], 4) == round(0.138 * 20, 4)
    assert {k: round(v, 4) for k, v in ha.items()} == {k: round(2 * v, 4) for k, v in one.items()}


def test_static_web_apps_and_the_load_balancer():
    swa = month(az("web", "compute.paas", "staticwebapps"), {"egress_gb": 150 / 730}, 1)
    assert {k: round(v, 4) for k, v in swa.items()} == {"plan": 9.0, "bandwidth": round(50 * 0.2, 4)}
    lb = month(az("lb", "load_balancer", "lb"), {"processed_gb": 100 / 730}, 1)
    assert {k: round(v, 4) for k, v in lb.items()} == {"hour": round(0.025 * 730, 4), "processed": 0.5}


def test_a_gce_instance_is_its_vcpus_and_its_memory():
    """e2-medium: 1 vCPU and 4 GB (asia-northeast1: $0.02802642 a vCPU-hour, $0.00373911 a GB-hour) and a 10 GB
    Balanced PD boot disk ($0.13 a GB-month)."""
    got = month(gcp("vm", "compute.vm", "gce"), {"_sku": "e2-medium", "storage_gb": 10.0}, 1, region="asia-northeast1")
    assert {k: round(v, 4) for k, v in got.items()} == {
        "vcpu": round(0.02802642 * 730, 4), "memory": round(4 * 0.00373911 * 730, 4), "storage": 1.3}
    micro = month(gcp("vm", "compute.vm", "gce"), {"_sku": "e2-micro"}, 1, region="us-east1")
    assert round(micro["vcpu"], 4) == round(0.25 * 0.02181159 * 730, 4)


@pytest.mark.parametrize("ha, vcpu, ram", [("", 0.0537, 0.0091), ("multi-az", 0.1074, 0.0182)])
def test_a_cloud_sql_custom_tier_is_its_vcpus_and_memory(ha, vcpu, ram):
    got = month(gcp("db", "database.relational", "cloudsql", ha=ha), {"_sku": "db-custom-2-7680"}, 1,
                region="asia-northeast1")
    assert {k: round(v, 4) for k, v in got.items()} == {"vcpu": round(2 * vcpu * 730, 4),
                                                        "memory": round(7.5 * ram * 730, 4)}


@pytest.mark.parametrize("tier, gb, sku", [("BASIC", 1, "basic:m1"), ("STANDARD_HA", 5, "standard:m2"),
                                           ("basic", 4, "basic:m1"), ("basic", 10, "basic:m2")])
def test_memorystore_is_its_gb_at_its_tier_and_bands_rate(tier, gb, sku):
    n = gcp("cache", "cache", "memorystore", spec=[{"key": "tier", "value": tier},
                                                    {"key": "memory_size_gb", "value": str(gb)}])
    got = month(n, {}, 1, region="asia-northeast1")
    rate = price("gcp", "memorystore", sku, "GB-hour", "asia-northeast1")["price_usd"]
    assert round(got["capacity"], 4) == round(gb * rate * 730, 4)


def test_cloud_run_requests_take_the_catalogs_free_two_million():
    got = month(gcp("run", "compute.container", "run"), {"requests": 3_000_000 / 730}, 0, region="asia-northeast1")
    assert round(got["requests"], 6) == 0.4


@pytest.mark.parametrize("svc, cat, words", [("run", "compute.container", "Cloud Run's monthly free vCPU-seconds"),
                                              ("gke", "compute.k8s", "GKE's monthly free credit")])
def test_a_free_amount_not_counted_is_said(svc, cat, words):
    """Not counted is not silent: Cloud Run's vCPU and memory grant (not in the catalog, its page unread) and GKE's
    credit are not taken off, and the result says so."""
    n = gcp("x", cat, svc)
    said = RULES.lookup(n).extra["notice"](n, {}, [1])
    assert [c for c, _m in said] == ["cost.free_not_counted"] and words in said[0][1] and "not taken off" in said[0][1]


def test_the_notice_reaches_the_result():
    """Through the engine: a model with a Cloud Run service carries the notice once, for its node."""
    from test_infra_cost import _notices, _run
    n = {"id": "api", "category": "compute.container", "provider": "gcp", "service": "run", "region": "asia-northeast1"}
    result, _ = _run([n], [{"node": "api", "quantities": {"vcpu": 1, "memory_gb": 0.5, "requests": 100}}])
    got = _notices(result, "cost.free_not_counted")
    assert len(got) == 1 and got[0]["node"] == "api" and "Cloud Run's monthly free" in got[0]["message"]
