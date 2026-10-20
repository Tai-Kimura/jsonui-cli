"""The cost simulator's calculation (infra/cost, infra/rules; plan docs/plans/2026-10-20-jui-viz-backend-load-and-cost-
simulator.md, L-B): the charges, the price book, the scaling, the formulas, the engine and its lines, the bundled table
and the rules. The rules are tested on the official pages' own examples (each test names its page), priced from the
bundled table where it holds the page's prices, else from the example's own prices.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra import prices as P
from jsonui_doc_cli.infra import room as R
from jsonui_doc_cli.infra import rules as RULES
from jsonui_doc_cli.infra.cost import aws_offers as A
from jsonui_doc_cli.infra.cost import currency as CUR
from jsonui_doc_cli.infra.cost import engine as E
from jsonui_doc_cli.infra.cost import formulas as F
from jsonui_doc_cli.infra.cost import parts
from jsonui_doc_cli.infra.cost import pricebook as PB
from jsonui_doc_cli.infra.cost import scale

FIX = Path(__file__).resolve().parent / "fixtures" / "infra"
ALL = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
BUNDLED = PB.Book(bundled=PB.bundled_rows())


def _model(nodes: list[dict], groups: list[dict] | None = None, edges: list[dict] | None = None) -> dict:
    doc = {"version": 0, "groups": groups or [], "nodes": nodes, "edges": edges or []}
    model, problems = M.merge([("m.json", json.dumps(doc).encode())])
    assert M.errors(problems) == []
    return model


def _run(nodes, loads, book=BUNDLED, month="2026-11", groups=None, edges=None, edge_loads=None, **extra):
    """(result, month totals) of one scenario over a model of ``nodes``."""
    model = _model(nodes, groups, edges)
    doc = {"version": 0, "id": "t", "month": month, "loads": loads, **({"edges": edge_loads} if edge_loads else {}), **extra}
    scenario, problems = L.normalize("t.json", doc, model)
    assert [p for p in problems if p["severity"] == "error"] == []
    result = E.simulate(scenario, model, book)
    return result, E.month_totals(result)


def _meter_usd(result, node, meter) -> float:
    run = next(r for r in result.nodes if r.node == node)
    return sum(v for v in run.meters[meter]["usd"] if v is not None)


def _per_hour(total: float, hours: int = 720) -> float:
    return total / hours


def _user(rows: list[dict]) -> PB.Book:
    return PB.Book(user=[dict(r, file="u.json", index=i, per_units=r.get("per_units", 1)) for i, r in enumerate(rows)])


# ---------------------------------------------------------------- parts: the charges

def test_a_charge_flat_free_and_stepped_on_the_months_total():
    flat = {"price_usd": 0.2, "per_units": 1_000_000}
    assert parts.charge(0, 3_000_000, flat)[0] == pytest.approx(0.6)
    free = dict(flat, free={"amount": 1_000_000, "period": "month"})
    assert parts.charge(0, 500_000, free) == (0.0, {"free": 500_000})
    usd, detail = parts.charge(500_000, 1_000_000, free)              # crosses the free amount
    assert usd == pytest.approx(0.1) and detail["free"] == 500_000
    tiers = {"tiers": [{"from": 0, "to": 10, "price_usd": 1.0}, {"from": 10, "price_usd": 0.5}], "per_units": 1}
    assert parts.charge(5, 10, tiers) == (pytest.approx(5 * 1.0 + 5 * 0.5), {"free": 0, "tiers": [0, 1]})
    assert parts.charge(20, 4, tiers)[0] == pytest.approx(2.0)
    both = dict(tiers, free={"amount": 10, "period": "month"})        # the free amount first, then the steps
    assert parts.charge(0, 25, both)[0] == pytest.approx(10 * 1.0 + 5 * 0.5)


# ---------------------------------------------------------------- the price book

ROW = {"provider": "aws", "service": "s3", "sku": "get", "region": "ap-northeast-1", "unit": "request",
       "price_usd": 1.0, "effective": "2026-10-01", "source": "manual"}


def test_the_book_takes_the_first_layer_the_region_then_global_and_the_latest_effective():
    book = PB.Book(user=[dict(ROW, price_usd=3.0, file="u", index=0)], cache=[dict(ROW, price_usd=2.0, file="c", index=0)],
                   bundled=[dict(ROW, file="b", index=0)])
    assert book.find("aws", "s3", "get", "request", "ap-northeast-1", "2026-11-01")["layer"] == "user"
    book = PB.Book(cache=[dict(ROW, price_usd=2.0)], bundled=[dict(ROW)])
    assert book.find("aws", "s3", "get", "request", "ap-northeast-1", "2026-11-01")["row"]["price_usd"] == 2.0
    book = PB.Book(bundled=[dict(ROW, region="global", price_usd=9.0), dict(ROW, price_usd=1.0),
                            dict(ROW, price_usd=1.5, effective="2026-11-15")])
    assert book.find("aws", "s3", "get", "request", "ap-northeast-1", "2026-11-01")["row"]["price_usd"] == 1.0
    assert book.find("aws", "s3", "get", "request", "ap-northeast-1", "2026-12-01")["row"]["price_usd"] == 1.5
    assert book.find("aws", "s3", "get", "request", "us-east-1", "2026-11-01")["row"]["price_usd"] == 9.0
    assert book.find("aws", "s3", "get", "request", "ap-northeast-1", "2026-09-01") is None   # not yet effective
    assert book.find("aws", "s3.standard", "get", "request", "ap-northeast-1", "2026-11-01")   # the service's head
    assert book.find("gcp", "s3", "get", "request", "ap-northeast-1", "2026-11-01") is None


def test_the_cache_is_read_from_viz_home(tmp_path):
    folder = PB.cache_dir({"JUI_VIZ_HOME": str(tmp_path)})
    assert folder == tmp_path / "cloud-prices"
    (folder / "aws").mkdir(parents=True)
    (folder / "aws" / "s3.json").write_text(json.dumps({"version": 0, "prices": [ROW]}))
    (folder / "bad.json").write_text("{")
    rows, why = PB.cache_rows(folder)
    assert [r["sku"] for r in rows] == ["get"] and why == ["bad.json: not used (json)"]


# ---------------------------------------------------------------- scale

def test_autoscale_clamps_marks_max_lags_and_steps():
    assert scale.wanted(100, 50, 0.5) == 4 and scale.wanted(0, 50, 1) == 0
    counts, at_max = scale.autoscale([100, 400, 100], 50, 1.0, [1, 1, 1], [4, 4, 4])
    assert counts == [2, 4, 2] and at_max == [False, True, False]
    counts, _ = scale.autoscale([50, 400, 400, 50, 50], 50, 1.0, [1] * 5, [10] * 5, out_delay_min=60, in_delay_min=120)
    assert counts == [1, 1, 8, 8, 8]        # up one hour late, down two hours late (the fifth hour still holds)
    counts, _ = scale.autoscale([50, 500], 50, 1.0, [1, 1], [10, 10], step=3)
    assert counts == [1, 4]
    counts, _ = scale.autoscale([50, 500], 50, 1.0, [1, 0], [10, 0])
    assert counts == [1, 0]                 # max 0: stopped at once
    counts, _ = scale.autoscale([100, 100], [50, 100], 1.0, [1, 1], [10, 10])
    assert counts == [2, 1]                 # one instance takes more on a bigger step


def test_a_delay_rounds_half_an_hour_up():
    assert [scale.lag_hours(m) for m in (None, 0, 29, 30, 89, 90, 149, 150, 210)] == [0, 0, 0, 1, 1, 2, 2, 3, 4]


LADDER = [{"sku": "s", "amount": 100}, {"sku": "m", "amount": 200}, {"sku": "l", "amount": 400}]


def test_vertical_picks_the_smallest_step_that_carries_it_by_order():
    args = dict(min_skus=["s"] * 3, max_skus=["l"] * 3, counts_lo=[1] * 3, counts_hi=[2] * 3, change_delay_min=0)
    assert scale.vertical([150, 350, 900], LADDER, 1.0, order="schedule_vertical", **args) == ["s", "m", "l"]
    assert scale.vertical([150, 350, 900], LADDER, 1.0, order="vertical_first", **args) == ["m", "l", "l"]
    assert scale.vertical([150], LADDER, 1.0, ["m"], ["m"], "schedule_vertical", [1], [1], 0) == ["m"]   # the range
    assert scale.vertical([50, 900, 50], LADDER, 1.0, ["s"] * 3, ["l"] * 3, "vertical_first", [1] * 3, [1] * 3, 60) == ["s", "s", "l"]
    assert scale.vertical([1], [{"sku": "a", "vcpu": 1}, {"sku": "b", "vcpu": 2}], 1.0, ["a"], ["b"], "vertical_first",
                          [1], [1], 0) == ["a"]                      # no amounts: the range's smallest
    assert scale.vertical([100], LADDER, 1.0, ["s"], ["l"], "vertical_first", [1], [1], 0, per_hours=1 / 3600) == ["s"]


def test_capacity_and_served():
    assert scale.capacity(3, 50) == 150 and scale.capacity(3, None) is None
    assert scale.served(200, 150) == (150, 50) and scale.served(100, 150) == (100, 0) and scale.served(9, None) == (9, 0)


# ---------------------------------------------------------------- formulas and rules

def test_every_meter_is_in_a_price_unit_and_every_rule_has_its_page():
    units = set(P.units())
    q = {k: 1.0 for k in L.quantities()}
    hour = F.Hour(node={"ha": "multi-az"}, q=q, by_zone={"japan": 1.0}, running=2.0, sku="t")
    for rule in RULES.REGISTRY:
        if rule.cost is None:
            assert rule.category in ("client", "ci", "external.saas", "security.iam", "security.policy", "monitoring.alarm")
            continue
        for m in rule.cost(hour):
            assert m.unit in units, (rule.id, m)
        if rule.provider:
            assert rule.source.startswith("https://") and rule.checked == "2026-10-20", rule.id


def test_the_most_specific_provider_rule_is_found():
    assert RULES.lookup({"category": "compute.function", "providerResolved": "aws", "service": "lambda"}).id == "aws/lambda"
    assert RULES.lookup({"category": "load_balancer", "providerResolved": "aws", "service": "elb.nlb"}).id == "aws/nlb"
    assert RULES.lookup({"category": "compute.function", "providerResolved": "gcp", "service": "functions"}).id == "generic/compute.function"


# ---------------------------------------------------------------- the official examples

def test_lambda_example_1():
    """https://aws.amazon.com/lambda/pricing/ example 1 (us-east-1, x86): 3 million requests a month, 120 ms, 1536 MB
    -> compute 540,000 GB-s - 400,000 free = $2.33, requests 2 million billable = $0.40, total $2.73."""
    node = {"id": "fn", "category": "compute.function", "provider": "aws", "service": "lambda", "region": "us-east-1"}
    load = {"node": "fn", "quantities": {"requests": _per_hour(3_000_000), "duration_ms": 120, "memory_mb": 1536}}
    result, totals = _run([node], [load])
    assert round(_meter_usd(result, "fn", "compute"), 2) == 2.33
    assert round(_meter_usd(result, "fn", "requests"), 2) == 0.40
    assert round(totals["usd"], 2) == 2.73


def test_workers_example_1():
    """https://developers.cloudflare.com/workers/platform/pricing/ example 1: 15 million requests, 7 ms CPU each ->
    $5.00 + requests $1.50 + CPU $1.50 = $8.00."""
    node = {"id": "w", "category": "compute.function", "provider": "cloudflare", "service": "workers"}
    result, totals = _run([node], [{"node": "w", "quantities": {"requests": _per_hour(15_000_000), "cpu_ms": 7}}])
    assert [round(_meter_usd(result, "w", m), 2) for m in ("plan", "requests", "cpu")] == [5.0, 1.5, 1.5]
    assert round(totals["usd"], 2) == 8.00


def test_alb_example():
    """https://aws.amazon.com/elasticloadbalancing/pricing/ (ALB, us-east-1): 1 new connection a second lasting 2
    minutes (120 open), 1.08 GB an hour, 250 rule evaluations a second -> 1.08 LCU, $0.03114 an hour, $22.42 a month."""
    node = {"id": "lb", "category": "load_balancer", "provider": "aws", "service": "elb.alb", "region": "us-east-1"}
    q = {"new_connections": {"amount": 1, "per": "second"}, "active_connections": 120, "processed_gb": 1.08,
         "rule_evaluations": {"amount": 250, "per": "second"}}
    result, totals = _run([node], [{"node": "lb", "quantities": q}])
    run = next(r for r in result.nodes if r.node == "lb")
    assert run.meters["lcu"]["amount"][0] == pytest.approx(1.08)
    assert run.meters["hour"]["usd"][0] + run.meters["lcu"]["usd"][0] == pytest.approx(0.03114)
    assert round(totals["usd"], 2) == 22.42


def test_dynamodb_on_demand_example():
    """https://aws.amazon.com/dynamodb/pricing/on-demand/ simple example (us-east-1): 3.55 million writes and reads,
    27 GB on average (25 free) -> writes $2.22, reads $0.44, storage $0.50, total $3.16."""
    node = {"id": "t", "category": "database.kv", "provider": "aws", "service": "dynamodb", "region": "us-east-1"}
    q = {"write_units": _per_hour(3_550_000), "read_units": _per_hour(3_550_000), "storage_gb": 27}
    result, totals = _run([node], [{"node": "t", "quantities": q}])
    assert [round(_meter_usd(result, "t", m), 2) for m in ("write_units", "read_units", "storage")] == [2.22, 0.44, 0.50]
    assert round(totals["usd"], 2) == 3.16


def test_r2_example():
    """https://developers.cloudflare.com/r2/pricing/ first example: 1,000 GB for a month, 1,000 writes, 1 million
    reads -> storage 990 billable GB-months $14.85; operations inside the free tier; total $14.85."""
    node = {"id": "b", "category": "storage.object", "provider": "cloudflare", "service": "r2"}
    q = {"storage_gb": 1000, "put_requests": _per_hour(1000), "get_requests": _per_hour(1_000_000), "egress_gb": 5}
    result, totals = _run([node], [{"node": "b", "quantities": q}])
    assert round(totals["usd"], 2) == 14.85 and totals["noPrice"] == []      # R2 has no egress charge at all


def test_queues_example_1():
    """https://developers.cloudflare.com/queues/platform/pricing/ example 1: 1 million messages a day written, read
    and deleted for 30 days -> 90 million operations - 1 million free = 89 million, $35.60."""
    node = {"id": "q", "category": "queue", "provider": "cloudflare", "service": "queues"}
    result, totals = _run([node], [{"node": "q", "quantities": {"messages": {"amount": 1_000_000, "per": "day"}}}])
    assert round(totals["usd"], 2) == 35.60


def test_fargate_example_vcpu_and_memory():
    """https://aws.amazon.com/fargate/pricing/ example (us-east-1, Linux/x86): 5 tasks, 1 vCPU and 2 GB each, 600
    seconds a day for 30 days, at $0.000011244 a vCPU-second and $0.000001235 a GB-second -> vCPU $1.01, memory $0.22
    (ephemeral storage is not modelled)."""
    book = _user([{"provider": "aws", "service": "ecs", "sku": "vcpu", "region": "us-east-1", "unit": "vCPU-hour",
                   "price_usd": 0.000011244 * 3600, "effective": "2026-10-01", "source": "manual"},
                  {"provider": "aws", "service": "ecs", "sku": "memory", "region": "us-east-1", "unit": "GB-hour",
                   "price_usd": 0.000001235 * 3600, "effective": "2026-10-01", "source": "manual"}])
    node = {"id": "api", "category": "compute.container", "provider": "aws", "service": "ecs.fargate",
            "region": "us-east-1", "count": 5}
    hour = F.Hour(node=node, q={"vcpu": 1, "memory_gb": 2}, running=5 * 600 / 3600, hours_in_month=720)
    usd = {m.name: 0.0 for m in RULES.lookup(node).cost(hour)}
    totals: dict = {}
    for _day in range(30):
        for m in RULES.lookup(node).cost(hour):
            usd[m.name] += E.price_meter(book, totals, m, node, "us-east-1", "2026-11-01")[0]
    assert (round(usd["vcpu"], 2), round(usd["memory"], 2)) == (1.01, 0.22)


# ---------------------------------------------------------------- the engine

def test_the_examples_run_and_say_what_is_not_priced():
    model = R.read(FIX / "aws-three-tier")
    sc = {s["id"]: s for s in L.read(FIX / "aws-three-tier")["scenarios"]}
    ordinary = E.month_totals(E.simulate(sc["ordinary"], model, BUNDLED))
    assert ordinary["noRule"] == ["stripe", "api-role", "api-5xx"]
    assert ordinary["noPrice"] == [{"node": "mailer", "meter": "emails", "sku": "emails", "unit": "email"}]   # sendgrid
    assert ordinary["usd"] > 0 and abs(sum(d["usd"] for d in ordinary["days"]) - ordinary["usd"]) < 1e-6
    sale = E.month_totals(E.simulate(sc["sale"], model, BUNDLED))
    assert sale["loadUndefined"] == ["mailer", "assets"] and "api-prod" in sale["overflowHours"]


def test_overflow_is_judged_by_capacity_and_left_out_of_the_charge_unless_the_rule_says():
    node = {"id": "api", "category": "compute.container", "provider": "aws", "service": "ecs", "region": "us-east-1"}
    load = {"node": "api", "quantities": {"requests": {"amount": 300, "per": "second"}},
            "autoscale": {"min": 1, "max": 2, "per_instance": {"quantity": "requests", "amount": 100, "per": "second"}}}
    result, totals = _run([node], [load])
    run = next(r for r in result.nodes if r.node == "api")
    assert run.running[0] == 2 and run.at_max[0] is True
    assert (run.demand[0], run.capacity[0], run.served[0], run.overflow[0]) == pytest.approx((1_080_000, 720_000, 720_000, 360_000))
    assert run.quantities["requests"]["perHour"][0] == pytest.approx(720_000)      # served, not demanded
    line = next(x for x in E.day_lines(result, "2026-11-02") if x["node"] == "api" and x["hour"] == 0)
    assert line["overflow"] == pytest.approx(360_000) and line["range"] == [1, 2] and line["atMax"] is True
    assert totals["overflowHours"] == {"api": 720}


def test_a_node_without_capacity_is_not_judged():
    node = {"id": "fn", "category": "compute.function", "provider": "aws", "service": "lambda", "region": "us-east-1"}
    result, totals = _run([node], [{"node": "fn", "quantities": {"requests": 1000}}])
    run = next(r for r in result.nodes if r.node == "fn")
    assert run.demand is None and totals["overflowHours"] == {}


def test_a_shared_free_amount_is_used_once_across_nodes():
    """Lambda's free requests are the account's: two functions of 600,000 requests each bill 200,000, not 0."""
    nodes = [{"id": f"f{i}", "category": "compute.function", "provider": "aws", "service": "lambda", "region": "us-east-1"}
             for i in (1, 2)]
    loads = [{"node": f"f{i}", "quantities": {"requests": _per_hour(600_000)}} for i in (1, 2)]
    _result, totals = _run(nodes, loads)
    assert totals["usd"] == pytest.approx(200_000 * 0.2 / 1_000_000)


def test_a_shared_free_amount_goes_to_the_first_node_in_the_models_order():
    """The month's totals run node by node in the model's order: of two functions of 1 million requests each, the
    first takes the free million (it pays 0.0) and the second pays for all of its own (0.2)."""
    nodes = [{"id": n, "category": "compute.function", "provider": "aws", "service": "lambda", "region": "us-east-1"}
             for n in ("a", "b")]
    loads = [{"node": n, "quantities": {"requests": _per_hour(1_000_000)}} for n in ("a", "b")]
    result, _totals = _run(nodes, loads)
    assert round(_meter_usd(result, "a", "requests"), 6) == 0.0
    assert round(_meter_usd(result, "b", "requests"), 6) == 0.2


def test_lines_carry_the_rate_as_written_and_the_price_trace():
    node = {"id": "cdn", "category": "edge.cdn", "provider": "aws", "service": "cloudfront"}
    load = {"node": "cdn", "quantities": {"requests": {"amount": 100, "per": "second"},
                                          "cdn_egress_gb": {"by_zone": {"japan": 3, "asia": 1}}}}
    result, _t = _run([node], [load])
    lines = [x for x in E.day_lines(result, "2026-11-02") if x["hour"] == 12]
    req = next(x for x in lines if x["meter"] == "requests-japan")
    assert req["rate"] == {"value": pytest.approx(75.0), "per": "second", "unit": "request", "label": "リクエスト"}
    assert req["price"]["layer"] == "bundled" and req["price"]["source"].startswith("https://pricing.us-east-1.amazonaws.com/")
    egress = next(x for x in lines if x["meter"] == "egress-asia")
    assert egress["rate"]["value"] == pytest.approx(1.0) and egress["usd"] > 0


def test_a_stopped_hour_runs_nothing_and_a_fixed_type_is_priced_by_its_sku():
    node = {"id": "db", "category": "database.relational", "provider": "aws", "service": "rds.mysql",
            "region": "ap-northeast-1"}
    load = {"node": "db", "sku": "db.r6g.large", "schedule": "night", "quantities": {"storage_gb": 100}}
    sch = {"night": {"default": 1, "rules": [{"days": ALL, "from": "00:00", "to": "06:00", "count": 0}]}}
    result, _t = _run([node], [load], schedules=sch)
    run = next(r for r in result.nodes if r.node == "db")
    inst = run.meters["instance"]
    assert inst["sku"] == "db.r6g.large" and inst["amount"][3] == 0 and inst["amount"][10] == 1
    assert sum(inst["usd"]) == pytest.approx(30 * 18 * 0.255)                        # 18 hours a day running
    assert sum(run.meters["storage"]["usd"]) == pytest.approx(100 * 0.138)           # storage stays when stopped


def test_edges_are_priced_as_data_transfer():
    nodes = [{"id": "a", "category": "compute.vm", "provider": "aws", "service": "ec2", "region": "ap-northeast-1"},
             {"id": "b", "category": "compute.vm", "provider": "aws", "service": "ec2", "region": "us-east-1"}]
    result, _t = _run(nodes, [], edges=[{"from": "a", "to": "b"}],
                      edge_loads=[{"from": "a", "to": "b", "quantities": {"transfer_gb": _per_hour(100)}}])
    run = next(r for r in result.nodes if r.node == "a>b")
    assert run.meters["transfer-inter-region"]["sku"] == "transfer-inter-region"
    assert sum(run.meters["transfer-inter-region"]["usd"]) == pytest.approx(100 * 0.09)


def test_a_rule_that_fails_is_a_warning_naming_the_node_and_hour():
    saved = list(RULES.REGISTRY)
    try:
        def broken(h):
            raise KeyError("x")
        RULES.register(RULES.Rule(id="aws/lambda", category="compute.function", provider="aws", service="lambda",
                                  reads=("requests",), cost=broken))
        node = {"id": "fn", "category": "compute.function", "provider": "aws", "service": "lambda", "region": "us-east-1"}
        _result, totals = _run([node], [{"node": "fn", "quantities": {"requests": 1}}])
        w = totals["warnings"][0]
        assert w["fn"] == "meters_of" and w["node"] == "fn" and w["hour"] == "2026-11-01T00"
    finally:
        RULES.REGISTRY[:] = saved


# ---------------------------------------------------------------- the bundled table and the offer files

def test_the_bundled_table_is_valid_and_traced():
    raw = PB.BUNDLED_PATH.read_bytes()
    doc, problems = P.read_file("bundled-prices.json", raw)
    rows, warnings = P.rows("bundled-prices.json", doc)
    assert problems == [] and warnings == [] and len(rows) == len(doc["prices"]) > 100
    assert all(r["source"].startswith("https://") for r in rows)
    assert {r["region"] for r in rows if r["provider"] == "aws"} == {"ap-northeast-1", "us-east-1", "global"}
    assert {r["service"] for r in rows if r["provider"] == "cloudflare"} == {"workers", "r2", "d1", "queues"}


def test_rows_from_an_offer_file():
    offer = {"publicationDate": "2026-10-16T18:23:59Z", "products": {
        "A": {"productFamily": "Serverless", "attributes": {"usagetype": "APN1-Request"}},
        "B": {"productFamily": "Serverless", "attributes": {"usagetype": "APN1-Request-ARM"}},
        "C": {"productFamily": "Storage", "attributes": {"usagetype": "APN1-TimedStorage-ByteHrs"}},
        "D": {"attributes": {"usagetype": "APN1-InstanceUsage:db.r6g.xl", "instanceType": "db.r6g.xlarge"}}},
        "terms": {"OnDemand": {
            "A": {"t": {"priceDimensions": {"d": {"unit": "Requests", "pricePerUnit": {"USD": "0.0000002000"}, "beginRange": "0", "endRange": "Inf"}}}},
            "B": {"t": {"priceDimensions": {"d": {"unit": "Requests", "pricePerUnit": {"USD": "0.0000001000"}, "beginRange": "0", "endRange": "Inf"}}}},
            "C": {"t": {"priceDimensions": {
                "x": {"unit": "GB-Mo", "pricePerUnit": {"USD": "0.024"}, "beginRange": "51200", "endRange": "Inf"},
                "y": {"unit": "GB-Mo", "pricePerUnit": {"USD": "0.025"}, "beginRange": "0", "endRange": "51200"}}}},
            "D": {"t": {"priceDimensions": {"d": {"unit": "Hrs", "pricePerUnit": {"USD": "0.51"}, "beginRange": "0", "endRange": "Inf"}}}}}}}
    spec = [A.S("AWSLambda", "lambda", "requests", "request", "Request", 1_000_000, family="Serverless",
                free={"amount": 1_000_000, "period": "month"}),
            A.S("AmazonS3", "s3", "storage", "GB-month", "TimedStorage-ByteHrs", family="Storage"),
            A.S("AmazonRDS", "rds.mysql", "db.r6g.xlarge", "instance-hour", "InstanceUsage:*", attrs={"instanceType": "db.r6g.xlarge"}),
            A.S("AmazonS3", "s3", "get", "request", "Requests-Tier2", 1000)]
    rows, missing = A.rows_from_offer(offer, spec, "ap-northeast-1", "https://x.example/index.json")
    assert rows[0] == {"provider": "aws", "service": "lambda", "sku": "requests", "region": "ap-northeast-1",
                       "unit": "request", "effective": "2026-10-16", "source": "https://x.example/index.json",
                       "per_units": 1_000_000, "price_usd": 0.2, "free": {"amount": 1_000_000, "period": "month"}}
    assert rows[1]["tiers"] == [{"from": 0.0, "to": 51200.0, "price_usd": 0.025}, {"from": 51200.0, "price_usd": 0.024}]
    assert rows[2]["price_usd"] == 0.51
    assert missing == ["s3 get (Requests-Tier2)"]


# ---------------------------------------------------------------- the currency's place

def test_the_currency_is_usd_and_a_converter_is_only_read(tmp_path):
    assert CUR.config(tmp_path) == (None, [])
    (tmp_path / "jui.config.json").write_text(json.dumps({"infra": {"currency": {"plugin": "fx.jpy:convert"}}}))
    cfg, warnings = CUR.config(tmp_path)
    assert cfg == {"plugin": "fx.jpy:convert"} and "converts nothing" in warnings[0]
    (tmp_path / "jui.config.json").write_text(json.dumps({"infra": {"currency": {"plugin": "rm -rf /"}}}))
    assert CUR.config(tmp_path)[0] is None
    assert CUR.convert(1.5, cfg) == {"usd": 1.5}
