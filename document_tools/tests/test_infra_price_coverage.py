"""The bundled prices cover what the rules charge (ticket 2026-10-21-infra-bundled-prices-missing-common-aws-rows).

- The family: every (provider, category, service) the IaC tables draft, priced by its rule with every quantity it
  reads, finds a bundled price for each meter, in each bundled region; what is not bundled is a closed list, each
  with why, and an entry no meter needs any more is red too.
- A seeded draft is priced: the IaC tables said "rds" and "elb", the price rows "rds.mysql" and "elb.alb", so a seeded
  RDS or load balancer had no price at all.
- The answers: the hand-made monthly costs of two backends' drafts (draft A: a booking service's room draft and
  cost estimate; draft B: an app's cost draft; read, never changed), item by item, from the bundled prices. They count a month as 730 hours; the engine counts the calendar's (720, 744): an
  hourly item moves by that ratio, a monthly fee does not.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import iac_tables as T
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra import rules as RULES
from jsonui_doc_cli.infra import seed as S
from jsonui_doc_cli.infra.cost import engine as E
from jsonui_doc_cli.infra.cost import formulas as F
from jsonui_doc_cli.infra.cost import pricebook as PB

BOOK = PB.Book(bundled=PB.bundled_rows())
ON = "2027-06-01"
AWS_REGIONS = ("ap-northeast-1", "us-east-1")
SEED_FIX = Path(__file__).resolve().parent / "fixtures" / "infra_seed"

#: Providers with no bundled table (closed): their prices are the fetched ones or a person's file.
NOT_BUNDLED = {
    "azure": "fetched (Azure Retail Prices, fetch.py); no bundled table — the requester decides whether to bundle",
    "gcp": "no bundled table and no fetch yet — the requester decides",
    "digitalocean": "no bundled table", "heroku": "no bundled table", "kubernetes": "priced by its cluster's provider",
    "netlify": "no bundled table", "vercel": "no bundled table",
}
#: Meters of AWS and Cloudflare with no bundled price (closed, each with why). Stage B of the ticket moves most of
#: them into the table.
NOT_YET = {
    ("aws", "cognito", "mau"): "stage B (Cognito's MAU steps)",
    ("aws", "elasticache", "capacity"): "stage B (ElastiCache Serverless)",
    ("aws", "elasticache", "storage"): "stage B (ElastiCache Serverless)",
    ("aws", "lambda", "cpu"): "Lambda bills no CPU time (cpu_ms is Workers'); the generic formula offers it",
    ("aws", "stepfunctions", "requests"): "stage B (Step Functions' state transitions)",
    ("aws", "stepfunctions", "compute"): "stage B", ("aws", "stepfunctions", "cpu"): "stage B",
    ("aws", "apprunner", "instance"): "stage B (App Runner)", ("aws", "apprunner", "storage"): "stage B",
    ("aws", "beanstalk", "instance"): "priced by its EC2 instances, not drafted apart",
    ("aws", "beanstalk", "storage"): "priced by its EC2 instances",
    ("aws", "lightsail", "instance"): "stage B (Lightsail's bundles)", ("aws", "lightsail", "storage"): "stage B",
    ("aws", "docdb", "read"): "stage B (DocumentDB)", ("aws", "docdb", "write"): "stage B",
    ("aws", "docdb", "capacity"): "stage B", ("aws", "docdb", "storage"): "stage B",
    ("aws", "dynamodb", "capacity"): "stage B (DynamoDB provisioned capacity)",
    ("aws", "aurora", "storage"): "stage B (Aurora)", ("aws", "aurora", "capacity"): "stage B (Aurora Serverless v2)",
    ("aws", "aurora", "instance"): "stage B (Aurora)",
    ("aws", "rds", "storage"): "an RDS whose engine is a variable: its price rows are per engine",
    ("aws", "rds", "instance"): "an RDS whose engine is a variable",
    ("aws", "rds.mysql", "capacity"): "RDS is not serverless (Aurora is)", ("aws", "rds.postgres", "capacity"): "as mysql",
    ("aws", "rds.mariadb", "capacity"): "as mysql",
    ("aws", "rds.mariadb", "instance"): "stage B (MariaDB)", ("aws", "rds.mariadb", "storage"): "stage B (MariaDB)",
    ("aws", "rds.mysql", "rows-read"): "rows are D1's; RDS bills no rows", ("aws", "rds.mysql", "rows-written"): "as rows-read",
    ("aws", "rds.postgres", "rows-read"): "as mysql", ("aws", "rds.postgres", "rows-written"): "as mysql",
    ("aws", "rds.mariadb", "rows-read"): "as mysql", ("aws", "rds.mariadb", "rows-written"): "as mysql",
    ("aws", "rds", "rows-read"): "as mysql", ("aws", "rds", "rows-written"): "as mysql",
    ("aws", "rds", "capacity"): "as mysql",
    ("aws", "aurora", "rows-read"): "as mysql", ("aws", "aurora", "rows-written"): "as mysql",
    ("aws", "lightsail", "rows-read"): "as mysql", ("aws", "lightsail", "rows-written"): "as mysql",
    ("aws", "lightsail", "capacity"): "stage B",
    ("aws", "rds", "instance:multi-az"): "as instance", ("aws", "rds", "storage:multi-az"): "as storage",
    ("aws", "rds.mariadb", "instance:multi-az"): "stage B (MariaDB)", ("aws", "rds.mariadb", "storage:multi-az"): "stage B",
    ("aws", "aurora", "instance:multi-az"): "stage B (Aurora)", ("aws", "aurora", "storage:multi-az"): "stage B (Aurora)",
    ("aws", "lightsail", "instance:multi-az"): "stage B", ("aws", "lightsail", "storage:multi-az"): "stage B",
    ("aws", "opensearch", "instance"): "stage B (OpenSearch)", ("aws", "opensearch", "storage"): "stage B",
    ("aws", "elb", "hour"): "a load balancer whose type is a variable", ("aws", "elb", "lcu"): "as hour",
    ("aws", "elb.gwlb", "hour"): "stage B (Gateway Load Balancer)", ("aws", "elb.gwlb", "lcu"): "stage B",
    ("aws", "elb.classic", "hour"): "stage B (Classic Load Balancer, previous generation)",
    ("aws", "elb.classic", "lcu"): "stage B",
    ("aws", "eventbridge", "requests"): "a rule on the event bus: a scheduled rule is free; custom events stage B",
    ("aws", "kms", "secret"): "stage B (KMS keys)", ("aws", "kms", "api"): "stage B",
    ("aws", "ssm", "secret"): "a standard parameter is free; advanced ones stage B", ("aws", "ssm", "api"): "stage B",
    ("aws", "kinesis", "put"): "stage B (Kinesis PUT payload units)",
    ("aws", "msk", "shard"): "stage B (MSK)", ("aws", "msk", "put"): "stage B",
    ("cloudflare", "access", "mau"): "stage B (Zero Trust seats)",
    ("cloudflare", "workers", "compute"): "Workers bill CPU ms, not GB-seconds",
    ("cloudflare", "workers", "egress"): "Workers' data out is free",
    ("cloudflare", "pages", "instance"): "stage B (Pages)", ("cloudflare", "pages", "storage"): "stage B",
    ("cloudflare", "pages", "egress"): "Pages' data out is free",
    ("cloudflare", "kv", "read"): "stage B (KV)", ("cloudflare", "kv", "write"): "stage B",
    ("cloudflare", "kv", "capacity"): "KV has no provisioned capacity", ("cloudflare", "kv", "storage"): "stage B",
    ("cloudflare", "zone", "queries"): "Cloudflare DNS: free", ("cloudflare", "lb", "hour"): "stage B (Load Balancing)",
    ("cloudflare", "lb", "lcu"): "stage B",
}
#: A type-priced meter is looked up with a type the table holds (the formula says "instance" when none is given).
TYPE_OF = {"ec2": "t3.micro", "ec2.asg": "t3.micro", "rds.mysql": "db.t3.micro", "rds.postgres": "db.t3.micro",
           "elasticache": "cache.t4g.micro"}


def drafted() -> list[tuple[str, str, str]]:
    """(provider, category, service) as the seed writes them: the tables' names, refined as seed refines them."""
    out = set()
    for typ, (cat, svc) in list(T.TF_TYPES.items()) + [(t, m) for t, m in T.CFN_TYPES.items()] + list(T.BICEP_TYPES.items()):
        if cat.startswith("group:"):
            continue
        prov = "aws" if typ.startswith("AWS::") else "azure" if typ.startswith("microsoft.") else T.tf_provider(typ)
        if prov is None:
            continue
        names = {svc}
        if svc == "rds":
            names |= set(T.RDS_ENGINE_SERVICE.values())
        if svc == "elb":
            names |= set(T.LB_TYPE_SERVICE.values())
        out |= {(prov, cat, n) for n in names}
    return sorted(out)


def meters(prov: str, cat: str, svc: str, spec: list | None = None) -> list[F.Meter]:
    """Every meter the rule can charge: with each quantity it reads, and again without the serverless capacity (with
    capacity_units a database or a cache charges capacity, not instance-hours), each in one and in multi-AZ."""
    rule = RULES.lookup({"category": cat, "providerResolved": prov, "service": svc})
    if rule is None or rule.cost is None:
        return []
    out = {}
    for ha in ("", "multi-az"):
        node = {"category": cat, "providerResolved": prov, "service": svc, "ha": ha, "spec": spec or []}
        for drop in ((), ("capacity_units",)):
            h = F.Hour(node=node, q={k: 1.0 for k in rule.reads if k not in drop},
                       by_zone={"japan": 1.0} if cat == "edge.cdn" else {}, running=1.0, sku=TYPE_OF.get(svc))
            out.update({(m.sku, m.unit, m.service): m for m in rule.cost(h)})
    return list(out.values())


def found(prov: str, svc: str, m: F.Meter, region: str) -> bool:
    return BOOK.find(prov, m.service or svc, m.sku, m.unit, region, ON) is not None


def unpriced() -> dict[tuple, list[str]]:
    out: dict[tuple, list[str]] = {}
    for prov, cat, svc in drafted():
        if prov in NOT_BUNDLED:
            continue
        regions = AWS_REGIONS if prov == "aws" else ("global",)
        for m in meters(prov, cat, svc):
            missing = [r for r in regions if not found(prov, svc, m, r)]
            if missing and not m.optional:
                out.setdefault((prov, svc, m.sku), []).append(f"{cat}: {', '.join(missing)}")
    return out


def test_every_meter_the_rules_charge_has_a_bundled_price():
    assert {k: v for k, v in unpriced().items() if k not in NOT_YET} == {}


def test_the_not_yet_list_names_only_meters_still_unpriced():
    assert sorted(set(NOT_YET) - set(unpriced())) == []


def test_every_drafted_provider_is_bundled_or_said_not_to_be():
    provs = {p for p, _, _ in drafted()}
    assert provs - set(NOT_BUNDLED) == {"aws", "cloudflare"}
    assert set(NOT_BUNDLED) - provs == set()


@pytest.mark.parametrize("value", ["arm64", "ARM", "aarch64", "Graviton"])
def test_each_way_of_saying_arm_is_read(value):
    assert F.arm({"spec": [{"key": "arch", "value": value}]})
    assert {m.sku for m in meters("aws", "compute.container", "ecs.fargate", [{"key": "arch", "value": value}])} >= {
        "vcpu:arm64", "memory:arm64"}
    assert not F.arm({"spec": [{"key": "arch", "value": "x86_64"}]}) and not F.arm({"spec": [{"key": "app", "value": "arm64"}]})


@pytest.mark.parametrize("prov, cat, svc", [("aws", "compute.container", "ecs.fargate"), ("aws", "compute.function", "lambda")])
def test_arm_is_priced_on_its_own_rows(prov, cat, svc):
    """Fargate and Lambda on ARM are 20-25% under x86 (draft A: $0.04045 against $0.05056 a
    vCPU-hour): a spec that says arm64 is priced on the :arm64 rows, in each bundled region."""
    x86 = {m.sku for m in meters(prov, cat, svc)}
    arm = {m.sku for m in meters(prov, cat, svc, [{"key": "arch", "value": "arm64"}])}
    assert arm - x86 and all(s.endswith(":arm64") for s in arm - x86)
    for m in meters(prov, cat, svc, [{"key": "cpu_architecture", "value": "ARM64"}]):
        assert (prov, svc.split(".")[0], m.sku) in NOT_YET or all(found(prov, svc, m, r) for r in AWS_REGIONS), m


def test_the_seeds_service_is_the_price_rows():
    assert T.priced_service("rds", "postgres") == "rds.postgres" and T.priced_service("rds", "MySQL") == "rds.mysql"
    assert T.priced_service("rds", None) == "rds"                      # a variable: not guessed
    assert T.priced_service("rds", "oracle-ee") == "rds"
    assert T.priced_service("elb") == "elb.alb"                        # none written: AWS's default
    assert T.priced_service("elb", lb_type="network", lb_type_written=True) == "elb.nlb"
    assert T.priced_service("elb", lb_type=None, lb_type_written=True) == "elb"   # a variable: not guessed
    assert T.priced_service("elb.classic") == "elb.classic" and T.priced_service("s3", "x") == "s3"


@pytest.mark.parametrize("kind", ["LoadBalancer", "DBInstance"])
def test_a_cfn_value_written_as_a_reference_is_not_guessed(tmp_path, kind):
    """CloudFormation, through the seed: a load balancer's Type or an RDS's Engine written as {"Ref": ...} keeps "elb" /
    "rds" (no price is better than the wrong one); a load balancer with no Type is AWS's default, application."""
    typ = {"LoadBalancer": "AWS::ElasticLoadBalancingV2::LoadBalancer", "DBInstance": "AWS::RDS::DBInstance"}[kind]
    key = {"LoadBalancer": "Type", "DBInstance": "Engine"}[kind]

    def service(props, n=[0]):
        n[0] += 1
        root = tmp_path / f"r{n[0]}"
        root.mkdir()
        (root / "template.json").write_text(json.dumps({"AWSTemplateFormatVersion": "2010-09-09", "Resources": {
            "Res": {"Type": typ, "Properties": props}}}))
        doc, _rep = S.draft(root)
        return next(nd["service"] for nd in doc["nodes"] if nd["category"] in ("load_balancer", "database.relational"))
    assert service({key: {"Ref": "Param"}}) == ("elb" if kind == "LoadBalancer" else "rds")
    if kind == "LoadBalancer":
        assert (service({}), service({"Type": "network"})) == ("elb.alb", "elb.nlb")
    else:
        assert (service({}), service({"Engine": "postgres"})) == ("rds", "rds.postgres")


def test_a_seeded_rds_and_load_balancer_are_priced(tmp_path):
    """The seed's draft of a Terraform room (fixtures/infra_seed/multi-cloud: aws_db_instance engine postgres,
    aws_lb with no type) merged as the room reads it: its RDS's storage and its load balancer's hours have prices."""
    root = tmp_path / "multi-cloud"
    shutil.copytree(SEED_FIX / "multi-cloud", root)
    doc, _rep = S.draft(root)
    model, _problems = M.merge([("draft.json", json.dumps(doc).encode())])
    by_iac = {a: n for n in model["nodes"] for a in n.get("iac") or []}
    rds, lb = by_iac["aws_db_instance.orders"], by_iac["aws_lb.web"]
    assert (rds["service"], lb["service"]) == ("rds.postgres", "elb.alb")
    region = "ap-northeast-1"
    rds_storage = [m for m in RULES.lookup(rds).cost(F.Hour(node=rds, q={"storage_gb": 20.0}, running=1.0))
                   if m.sku == "storage"]
    lb_hour = [m for m in RULES.lookup(lb).cost(F.Hour(node=lb, q={}, running=1.0)) if m.sku == "hour"]
    assert RULES.lookup(lb).id == "aws/alb"
    assert rds_storage and lb_hour
    assert BOOK.find("aws", rds["service"], "storage", "GB-month", region, ON)["row"]["price_usd"] == 0.138
    assert BOOK.find("aws", lb["service"], "hour", "instance-hour", region, ON)["row"]["price_usd"] == 0.0243
    assert BOOK.find("aws", rds["service"], "db.t3.micro", "instance-hour", region, ON) is not None


def test_nat_and_ip_addresses_are_drafted_and_billed_by_the_hour():
    assert T.tf_mapping("aws_nat_gateway") == ("gateway.nat", "vpc.nat")
    assert T.tf_mapping("aws_eip") == ("network.ip", "vpc.ipv4")
    assert T.cfn_mapping("AWS::EC2::NatGateway") == ("gateway.nat", "vpc.nat")
    assert T.cfn_mapping("AWS::EC2::EIP") == ("network.ip", "vpc.ipv4")
    schema = json.loads((Path(M.__file__).with_name("infra-model.v0.schema.json")).read_text(encoding="utf-8"))
    cats = schema["$defs"]["category"]["enum"]
    assert {"gateway.nat", "network.ip"} <= set(cats)                 # v0: added, no version bump (the ruling 10-21)
    assert RULES.lookup({"category": "gateway.nat", "providerResolved": "aws", "service": "vpc.nat"}).id == "aws/nat"
    assert RULES.lookup({"category": "network.ip", "providerResolved": "aws", "service": "vpc.ipv4"}).id == "aws/ipv4"
    assert all(RULES.lookup({"category": c, "providerResolved": "aws", "service": "vpc.x"}).hourly
               for c in ("gateway.nat", "network.ip"))


# ---------------------------------------------------------------- the two backends' hand-made costs

def month(node: dict, q: dict, running: float, hours: int, region: str = "ap-northeast-1") -> dict[str, float]:
    """usd by meter of one node over a month of ``hours`` hours (the price rows' month totals carried hour to hour)."""
    rule, totals, usd = RULES.lookup(node), {}, {}
    for _ in range(hours):
        for m in rule.cost(F.Hour(node=node, q=q, running=running, sku=q.get("_sku"), hours_in_month=hours)):
            got = E.price_meter(BOOK, totals, m, node, region, ON)[0]
            assert got is not None, (node["id"], m)
            usd[m.name] = usd.get(m.name, 0.0) + got
    return usd


def aws(id_: str, cat: str, svc: str, **extra) -> dict:
    return {"id": id_, "category": cat, "provider": "aws", "providerResolved": "aws", "service": svc, **extra}


# (what the draft says, node, quantities per hour, how many run, the hand value for 730 hours, monthly fee or hourly)
DRAFT_A = [
    ("NAT ×2 $90.52", aws("nat", "gateway.nat", "vpc.nat"), {}, 2, 90.52, "hourly"),
    ("NAT の処理量 75 GB $4.65", aws("nat", "gateway.nat", "vpc.nat"), {"processed_gb": 75 / 730}, 0, 4.65, "monthly"),
    ("RDS db.t4g.small Multi-AZ + 20 GB $79.25", aws("rds", "database.relational", "rds.mysql", ha="multi-az"),
     {"_sku": "db.t4g.small", "storage_gb": 20.0}, 1, 79.25, "hourly"),
    ("Fargate ARM 6 タスク 0.25 vCPU 0.5 GB $53.97",
     aws("api", "compute.container", "ecs.fargate", spec=[{"key": "arch", "value": "arm64"}]),
     {"vcpu": 0.25, "memory_gb": 0.5}, 6, 53.97, "hourly"),
    ("ALB の時間 $17.74", aws("alb", "load_balancer", "elb.alb"), {}, 1, 17.74, "hourly"),
    ("IPv4 ×4 $14.60", aws("ip", "network.ip", "vpc.ipv4"), {}, 4, 14.60, "hourly"),
    ("WAF Web ACL 1 + ルール 2 $7.00", aws("waf", "edge.waf", "waf"), {"rules": 2.0}, 0, 7.00, "monthly"),
    # Container Insights: 113 metrics × $0.30 = $33.90 by hand; AWS's 10 free metrics a month (the offer's
    # Global-CW:MetricMonitorUsage row) are not taken off there: 103 × $0.30 = $30.90
    ("Container Insights 113 メトリクス $33.90（無料の 10 を引いて $30.90）", aws("logs", "monitoring", "cloudwatch"),
     {"metrics": 113.0}, 0, 33.90 - 10 * 0.30, "monthly"),
]
DRAFT_B = [
    ("rds-prod db.t3.small Multi-AZ + 100 GB $103", aws("rds", "database.relational", "rds.mysql", ha="multi-az"),
     {"_sku": "db.t3.small", "storage_gb": 100.0}, 1, 0.104 * 730 + 0.276 * 100, "hourly"),
    ("efs-prod 2 GB $1（$0.72）", aws("efs", "storage.file", "efs"), {"storage_gb": 2.0}, 0, 0.36 * 2, "monthly"),
    ("dns-public hosted zone 1 $1（$0.50）", aws("dns", "edge.dns", "route53"), {}, 0, 0.50, "monthly"),
    ("secrets-prod 11 本 $4（$4.40）", aws("secrets", "secrets", "secretsmanager"), {"secrets": 11.0}, 0, 4.40, "monthly"),
    ("ses 数千通（3,000 通 $0.30）", aws("ses", "mail", "ses"), {"emails": 3000 / 730}, 0, 0.30, "monthly"),
]


@pytest.mark.parametrize("label, node, q, running, hand, kind", DRAFT_A + DRAFT_B, ids=[x[0] for x in DRAFT_A + DRAFT_B])
def test_the_hand_made_costs_come_out_of_the_bundled_prices(label, node, q, running, hand, kind):
    q = dict(q)
    got = sum(month(node, q, running, 730).values())
    assert round(got, 2) == round(hand, 2), label


@pytest.mark.parametrize("label, node, q, running, hand, kind", DRAFT_A, ids=[x[0] for x in DRAFT_A])
def test_the_calendars_hours_move_an_hourly_item_by_their_ratio_only(label, node, q, running, hand, kind):
    """The engine's month is the calendar's (744 hours in a 31-day month): an hourly item is the 730-hour value times
    744 / 730; a monthly fee is the same in any month."""
    at730, at744 = month(node, dict(q), running, 730), month(node, dict(q), running, 744)
    for name, usd in at730.items():
        # hours run (instance, hour, address, vcpu, memory) move by the ratio; a level spread over the month (storage,
        # metrics, rules) and a monthly fee do not; a flow given per hour (processed) moves as its hours do
        ratio = 744 / 730 if name in ("instance", "hour", "address", "vcpu", "memory", "processed") else 1.0
        assert abs(at744[name] - usd * ratio) < 1e-6 * max(1.0, usd), (label, name)


def test_draft_as_fixed_cost_is_its_own_items_less_the_free_metrics():
    """Draft A's production fixed cost ($299.98) is the items above plus ones it states
    apart (WAF's requests, S3, Secrets Manager…); the items reproduced here sum to the draft's own figures."""
    hand = {"NAT ×2": 90.52, "RDS": 79.25, "Fargate 6 タスク": 53.97, "Container Insights": 33.90, "ALB": 17.74,
            "IPv4": 14.60, "WAF": 7.00}
    got = [round(sum(month(n, dict(q), r, 730).values()), 2) for label, n, q, r, _h, _k in DRAFT_A if "処理量" not in label]
    assert round(sum(got), 2) == round(sum(hand.values()) - 3.00, 2)   # the 10 free metrics: $3.00


def test_alarms_are_a_monthly_fee_less_the_ten_free():
    """Draft A's production has 12 alarms (its model draft): $0.10 each a month after AWS's 10 free
    (the offer's Global-CW:AlarmMonitorUsage row) is $0.20, the same in a 730- and a 744-hour month. The draft's $1.80
    puts the custom metrics in with them and takes no free alarm off."""
    node = aws("alarms", "monitoring.alarm", "cloudwatch.alarm")
    assert RULES.lookup(node).id == "aws/cloudwatch-alarm"
    for hours in (730, 744):
        assert round(sum(month(node, {}, 12, hours).values()), 6) == 0.2
