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

from jsonui_doc_cli.infra import code_hints as CH
from jsonui_doc_cli.infra import iac_tables as T
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra import rules as RULES
from jsonui_doc_cli.infra import seed as S
from jsonui_doc_cli.infra.cost import aws_offers as A
from jsonui_doc_cli.infra.cost import build_bundled as BB
from jsonui_doc_cli.infra.cost import engine as E
from jsonui_doc_cli.infra.cost import formulas as F
from jsonui_doc_cli.infra.cost import pricebook as PB

BOOK = PB.Book(bundled=PB.bundled_rows())
ON = "2027-06-01"
AWS_REGIONS = ("ap-northeast-1", "us-east-1")
#: each provider's bundled regions (a global row serves them all)
REGIONS = {"aws": AWS_REGIONS, "azure": ("japaneast", "eastus"), "gcp": ("asia-northeast1", "us-east1")}
SEED_FIX = Path(__file__).resolve().parent / "fixtures" / "infra_seed"

#: Providers with no bundled table (closed): their prices are the fetched ones or a person's file.
NOT_BUNDLED = {
    "digitalocean": "no bundled table", "heroku": "no bundled table", "kubernetes": "priced by its cluster's provider",
    "netlify": "no bundled table", "vercel": "no bundled table",
}
#: Meters of AWS, Cloudflare and Firebase with no bundled price (closed, each with why): no price by design.
NOT_YET = {
    ("aws", "lambda", "cpu"): "Lambda bills no CPU time (cpu_ms is Workers'); the generic formula offers it",
    ("aws", "beanstalk", "instance"): "priced by its EC2 instances, not drafted apart",
    ("aws", "beanstalk", "storage"): "priced by its EC2 instances",
    ("aws", "aurora", "storage"): "an Aurora whose engine is a variable: its price rows are per engine",
    ("aws", "aurora", "capacity"): "an Aurora whose engine is a variable", ("aws", "aurora", "instance"): "as capacity",
    ("aws", "rds", "storage"): "an RDS whose engine is a variable: its price rows are per engine",
    ("aws", "rds", "instance"): "an RDS whose engine is a variable",
    ("aws", "rds.mysql", "capacity"): "RDS is not serverless (Aurora is)", ("aws", "rds.postgres", "capacity"): "as mysql",
    ("aws", "rds.mariadb", "capacity"): "as mysql",
    ("aws", "rds.mysql", "rows-read"): "rows are D1's; RDS bills no rows", ("aws", "rds.mysql", "rows-written"): "as rows-read",
    ("aws", "rds.postgres", "rows-read"): "as mysql", ("aws", "rds.postgres", "rows-written"): "as mysql",
    ("aws", "rds.mariadb", "rows-read"): "as mysql", ("aws", "rds.mariadb", "rows-written"): "as mysql",
    ("aws", "rds", "rows-read"): "as mysql", ("aws", "rds", "rows-written"): "as mysql",
    ("aws", "rds", "capacity"): "as mysql",
    ("aws", "rds", "instance:multi-az"): "as instance", ("aws", "rds", "storage:multi-az"): "as storage",
    ("aws", "elb", "hour"): "a load balancer whose type is a variable", ("aws", "elb", "lcu"): "as hour",
    ("cloudflare", "workers", "compute"): "Workers bill CPU ms, not GB-seconds",
    ("cloudflare", "workers", "egress"): "Workers' data out is free",
    ("cloudflare", "pages", "instance"): "Pages: static asset requests are free and unlimited (its Functions are "
                                         "Workers, priced on the Workers rows)",
    ("cloudflare", "pages", "storage"): "as instance", ("cloudflare", "pages", "egress"): "Pages' data out is free",
    ("cloudflare", "zone", "queries"): "Cloudflare DNS: free",
    # CI (2.3.16: a CI node bills its build minutes): not bundled, a person's price file prices them
    ("aws", "codebuild", "minutes"): "CodeBuild bills by its compute type's minute: not bundled",
    ("aws", "codebuild", "storage"): "CodeBuild keeps no storage of its own (S3 holds the artifacts)",
    ("aws", "codepipeline", "minutes"): "CodePipeline bills a pipeline a month (V1) or an action's minute (V2): not bundled",
    ("aws", "codepipeline", "storage"): "as codebuild",
    ("azure", "acr", "minutes"): "a container registry bills no build minutes (ACR Tasks: not bundled)",
    ("azure", "acr", "storage"): "ACR bills its tier by the day, storage over the tier's: not bundled",
    # GCP: the services not bundled yet (stage C), and two that the catalog does not give as the rules count
    **{("gcp", svc, sku): "GCP stage C: not bundled yet (the generic rule; a person's price file prices it)" for svc, sku in [
        ('apigateway', 'requests'), ('appengine', 'instance'), ('appengine', 'storage'), ('armor', 'requests'),
        ('armor', 'rule'), ('bigquery', 'capacity'), ('bigquery', 'instance'), ('bigquery', 'instance:multi-az'),
        ('bigquery', 'rows-read'), ('bigquery', 'rows-written'), ('bigquery', 'storage'),
        ('bigquery', 'storage:multi-az'), ('bigtable', 'capacity'), ('bigtable', 'read'), ('bigtable', 'storage'),
        ('bigtable', 'write'), ('cloudtasks', 'requests'), ('filestore', 'storage'), ('identityplatform', 'mau'),
        ('lb', 'hour'), ('lb', 'lcu'), ('monitoring', 'alarm'), ('scheduler', 'requests'), ('spanner', 'capacity'),
        ('spanner', 'instance'), ('spanner', 'instance:multi-az'), ('spanner', 'rows-read'),
        ('spanner', 'rows-written'), ('spanner', 'storage'), ('spanner', 'storage:multi-az'),
    ]},
    ("gcp", "firestore", "read"): "the catalog lists no Standard-edition operations for the bundled regions "
                                  "(Enterprise units only)",
    ("gcp", "firestore", "write"): "as read", ("gcp", "firestore", "storage"): "as read",
    ("gcp", "firestore", "capacity"): "Firestore has no provisioned capacity",
    ("gcp", "pubsub", "requests"): "Pub/Sub bills the data delivered (TiB); the rule counts messages",
    # Firebase's pricing page: past the no-cost quota these are "Google Cloud pricing" (GCP: no bundled table)
    ("firebase", "firestore", "read"): "Google Cloud pricing past the no-cost quota",
    ("firebase", "firestore", "write"): "as read", ("firebase", "firestore", "storage"): "as read",
    ("firebase", "firestore", "capacity"): "Firestore has no provisioned capacity",
    ("firebase", "auth", "mau"): "Google Cloud pricing (Identity Platform) past 50K MAUs",
    ("firebase", "storage", "storage"): "Cloud Storage pricing past the no-cost quota",
    ("firebase", "storage", "get"): "as storage", ("firebase", "storage", "put"): "as storage",
    ("firebase", "storage", "egress"): "as storage",
}
#: A type-priced meter is looked up with a type the table holds (the formula says "instance" when none is given).
TYPE_OF = {"ec2": "t3.micro", "ec2.asg": "t3.micro", "rds.mysql": "db.t3.micro", "rds.postgres": "db.t3.micro",
           "rds.mariadb": "db.t3.micro", "aurora.mysql": "db.t4g.medium", "aurora.postgres": "db.t4g.medium",
           "elasticache": "cache.t4g.micro", "opensearch": "t3.small.search", "docdb": "db.t4g.medium",
           "msk": "kafka.m7g.large", "lightsail": "micro_3_0",
           # Azure (the IaC's spelling of a size) and GCP (a machine type, a Cloud SQL tier)
           "vm": "Standard_B2s", "vmss": "Standard_B2s", "appservice": "B1", "mysql": "B_Standard_B1ms",
           "postgresql": "B_Standard_B1ms", "sql": "GP_Gen5_2", "redis": "Basic_C0", "search": "basic",
           "gce": "e2-medium", "gce.mig": "e2-medium", "cloudsql": "db-custom-2-7680"}


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
        if svc in ("rds", "aurora"):
            names |= {n for n in T.RDS_ENGINE_SERVICE.values() if n.startswith(svc + ".")}
        if svc == "elb":
            names |= set(T.LB_TYPE_SERVICE.values())
        out |= {(prov, cat, n) for n in names}
    # Firebase is drafted from the code (its SDK's imports), not from an IaC table
    out |= {what for _mod, what in CH.SDK_PY + CH.SDK_JS if what[0] == "firebase"}
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
        regions = REGIONS.get(prov, ("global",))
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
    assert provs - set(NOT_BUNDLED) == {"aws", "azure", "cloudflare", "firebase", "gcp"}
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
    assert (T.priced_service("aurora", "aurora-postgresql"), T.priced_service("aurora", "aurora-mysql"),
            T.priced_service("aurora", "aurora"), T.priced_service("rds", "aurora-mysql")) == (
        "aurora.postgres", "aurora.mysql", "aurora.mysql", "aurora.mysql")   # an instance of a cluster, too
    assert T.priced_service("aurora", None) == "aurora" and T.priced_service("rds", "mariadb") == "rds.mariadb"


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


# ---------------------------------------------------------------- stage B: the rest, each from its price rows
# (label, node, quantities per hour, how many run, the month of 730 hours by hand from the offer's or the page's price)
def cf(id_: str, cat: str, svc: str, **extra) -> dict:
    return {"id": id_, "category": cat, "provider": "cloudflare", "providerResolved": "cloudflare", "service": svc, **extra}


STAGE_B = [
    ("Aurora PostgreSQL db.t4g.medium + 10 GB", aws("au", "database.relational", "aurora.postgres", ha="multi-az"),
     {"_sku": "db.t4g.medium", "storage_gb": 10.0}, 1, 0.113 * 730 + 0.12 * 10),
    ("Aurora Serverless v2 0.5 ACU", aws("au", "database.relational", "aurora.mysql"), {"capacity_units": 0.5}, 1,
     0.5 * 730 * 0.15),
    ("MariaDB db.t4g.micro Multi-AZ + 20 GB", aws("ma", "database.relational", "rds.mariadb", ha="multi-az"),
     {"_sku": "db.t4g.micro", "storage_gb": 20.0}, 1, 0.05 * 730 + 0.276 * 20),
    ("DocumentDB db.t4g.medium ×2 + 50 GB", aws("doc", "database.document", "docdb"),
     {"_sku": "db.t4g.medium", "storage_gb": 50.0}, 2, 0.11543 * 730 * 2 + 0.12 * 50),
    ("OpenSearch t3.small.search ×2 + 20 GB", aws("os", "database.search", "opensearch"),
     {"_sku": "t3.small.search", "storage_gb": 20.0}, 2, 0.056 * 730 * 2 + 0.1464 * 20),
    ("MSK kafka.m7g.large ×3 + 100 GB", aws("msk", "stream", "msk"), {"_sku": "kafka.m7g.large", "storage_gb": 100.0}, 3,
     0.2635 * 730 * 3 + 0.12 * 100),
    ("Kinesis 1 million records", aws("ks", "stream", "kinesis"), {"messages": 1_000_000 / 730}, 0, 0.0215),
    ("DynamoDB provisioned 100 RCU + 10 WCU (25 each free)", aws("ddb", "database.kv", "dynamodb"),
     {"read_capacity_units": 100.0, "write_capacity_units": 10.0}, 0, (100 * 730 - 25 * 744) * 0.0001484),
    ("ElastiCache Serverless Redis 1 GB + 1 million ECPU an hour", aws("ec", "cache", "elasticache"),
     {"storage_gb": 1.0, "ecpu": 1_000_000.0}, 1, 0.151 * 730 + 0.0041 * 730),
    ("ElastiCache Serverless Valkey", aws("ec", "cache", "elasticache", spec=[{"key": "engine", "value": "valkey"}]),
     {"storage_gb": 1.0, "ecpu": 1_000_000.0}, 1, 0.101 * 730 + 0.0027 * 730),
    ("Cognito Essentials 20,000 MAU (10,000 free)", aws("cg", "auth", "cognito"), {"monthly_active_users": 20_000.0}, 0,
     10_000 * 0.015),
    ("Cognito Lite 20,000 MAU", aws("cg", "auth", "cognito", spec=[{"key": "tier", "value": "lite"}]),
     {"monthly_active_users": 20_000.0}, 0, 10_000 * 0.0055),
    ("Cognito Plus 20,000 MAU", aws("cg", "auth", "cognito", spec=[{"key": "tier", "value": "Plus"}]),
     {"monthly_active_users": 20_000.0}, 0, 20_000 * 0.02),
    ("KMS 2 keys + 30,000 requests (20,000 free)", aws("kms", "secrets", "kms"),
     {"secrets": 2.0, "requests": 30_000 / 730}, 0, 2.0 + 10_000 / 10_000 * 0.03),
    ("SSM 40 standard parameters: free", aws("ssm", "secrets", "ssm"), {"secrets": 40.0, "requests": 100.0}, 0, 0.0),
    ("SSM 10 advanced parameters + 20,000 API", aws("ssm", "secrets", "ssm", spec=[{"key": "tier", "value": "advanced"}]),
     {"secrets": 10.0, "requests": 20_000 / 730}, 0, 10 * 0.05 + 2 * 0.05),
    ("KV 20 million reads + 2 million writes + 3 GB", cf("kv", "database.kv", "kv"),
     {"read_units": 20_000_000 / 730, "write_units": 2_000_000 / 730, "storage_gb": 3.0}, 0, 5.0 + 5.0 + 1.0),
    ("Load Balancing", cf("lb", "load_balancer", "lb"), {}, 1, 5.0),
]


@pytest.mark.parametrize("label, node, q, running, hand", STAGE_B, ids=[x[0] for x in STAGE_B])
def test_stage_b_costs_come_out_of_the_bundled_prices(label, node, q, running, hand):
    assert round(sum(month(node, dict(q), running, 730).values()), 4) == round(hand, 4), label


@pytest.mark.parametrize("users, usd", [(50, 0.0), (51, 51 * 7.0)])
def test_zero_trust_is_free_to_fifty_users_then_every_user_is_a_seat(users, usd):
    """Cloudflare's Zero Trust plans (read 2026-10-21): Free "50 users", Pay-as-you-go "$7 /user/month". 50 cost 0
    (priced, not "no price"); the 51st puts the account on Pay-as-you-go, every user a seat, in any month."""
    for hours in (730, 744):
        got = month(cf("za", "auth", "access"), {"monthly_active_users": float(users)}, 0, hours)
        assert set(got) == {"seat"} and round(got["seat"], 6) == usd


def test_load_balancing_is_a_month_only_while_the_node_runs():
    """Load Balancing's base fee is a month while the load balancer is there: a month at 0 running (its environment
    stopped, or the count 0) is 0, half a month running is half the fee."""
    node = cf("lb", "load_balancer", "lb")
    assert sum(month(node, {}, 0, 744).values()) == 0.0
    rule, usd = RULES.lookup(node), 0.0
    for i in range(744):
        for m in rule.cost(F.Hour(node=node, q={}, running=1.0 if i < 372 else 0.0, hours_in_month=744)):
            usd += E.price_meter(BOOK, {}, m, node, "global", ON)[0]
    assert round(usd, 6) == 2.5


def test_a_seeded_aurora_is_priced(tmp_path):
    """CloudFormation through the seed: a DB cluster's Engine aurora-postgresql drafts aurora.postgres, priced by the
    Aurora rule (no Multi-AZ price: a replica is one more instance); an Engine written as a reference stays "aurora"."""
    def draft(props, name):
        root = tmp_path / name
        root.mkdir()
        (root / "template.json").write_text(json.dumps({"AWSTemplateFormatVersion": "2010-09-09", "Resources": {
            "Db": {"Type": "AWS::RDS::DBCluster", "Properties": props}}}))
        doc, _rep = S.draft(root)
        return next(nd for nd in doc["nodes"] if nd["category"] == "database.relational")
    node = draft({"Engine": "aurora-postgresql"}, "a")
    assert node["service"] == "aurora.postgres" and RULES.lookup(node).id == "aws/aurora"
    assert draft({"Engine": {"Ref": "E"}}, "b")["service"] == "aurora"
    ha = dict(node, ha="multi-az")
    assert [m.sku for m in RULES.lookup(ha).cost(F.Hour(node=ha, q={"storage_gb": 1.0}, running=1.0,
                                                          sku="db.r6g.large"))] == ["db.r6g.large", "storage"]


def test_the_meters_a_rule_no_longer_charges_are_gone():
    """DocumentDB and MSK are billed by their instances (brokers) and storage, not read/write units or shards; KV and
    DynamoDB charge no single capacity; Aurora no rows (D1's)."""
    assert {m.sku for m in meters("aws", "database.document", "docdb")} == {"db.t4g.medium", "storage"}
    assert {m.sku for m in meters("aws", "stream", "msk")} == {"kafka.m7g.large", "storage"}
    assert "capacity" not in {m.sku for m in meters("aws", "database.kv", "dynamodb")}
    assert "capacity" not in {m.sku for m in meters("cloudflare", "database.kv", "kv")}
    assert not {"rows-read", "rows-written"} & {m.sku for m in meters("aws", "database.relational", "aurora.mysql")}


def test_the_page_rows_are_the_bundled_ones():
    """The rows no offer file holds (Route 53's zone, Parameter Store, Cloudflare, Firebase) are written by build_bundled as the
    table has them, on the days the table says: a free standard parameter is a price of 0, not "no price"."""
    key = lambda r: (r["provider"], r["service"], r["sku"], r["unit"])
    bundled = {key(r): r for r in json.loads(PB.BUNDLED_PATH.read_text(encoding="utf-8"))["prices"]
               if r["provider"] in ("cloudflare", "firebase") or r["source"] in (BB.R53, BB.SSM, BB.KEY_VAULT)}
    built = (BB.aws_page_rows("2026-10-21") + BB.cloudflare_rows("2026-10-20", "2026-10-21") + BB.firebase_rows("2026-10-21")
             + BB.azure_page_rows("2026-10-21"))
    assert {key(r): r for r in built} == bundled
    ssm = {r["sku"]: r["price_usd"] for r in built if r["service"] == "ssm"}
    assert ssm == {"secret": 0.0, "api": 0.0, "secret:advanced": 0.05}


def test_a_usage_type_that_spells_its_region_out_is_found():
    """KMS's usage types are "ap-northeast-1-KMS-Keys", not "APN1-…": the spec's "{region}" is the region itself."""
    spec = [s for s in A.regional_spec() if s["offer"] == "awskms"]
    for region, other in (("ap-northeast-1", "us-east-1"), ("us-east-1", "ap-northeast-1")):
        def product(ut, fam):
            return {"productFamily": fam, "attributes": {"usagetype": ut}}
        offer = {"publicationDate": "2026-09-11T12:46:01Z", "products": {
            "K": product(f"{region}-KMS-Keys", "Encryption Key"), "R": product(f"{region}-KMS-Requests", "API Request"),
            "X": product(f"{other}-KMS-Keys", "Encryption Key")},
            "terms": {"OnDemand": {k: {"t": {"priceDimensions": {"d": {"pricePerUnit": {"USD": usd}, "beginRange": "0",
                                                                     "endRange": "Inf"}}}}
                                   for k, usd in (("K", "1.0"), ("R", "0.000003"), ("X", "9.0"))}}}
        rows, missing = A.rows_from_offer(offer, spec, region, "u")
        assert missing == [] and {(r["sku"], r["price_usd"]) for r in rows} == {("key", 1.0), ("api", 0.03)}


# ---------------------------------------------------------------- Firebase's Realtime Database and ECR (draft A's gaps)

def test_realtime_database_is_drafted_from_its_imports_and_priced():
    """Draft A uses Realtime Database only (firebase_admin's db, firebase/database): the code's imports draft it as
    firebase rtdb, and its GB stored and downloaded are the Blaze plan's (the pricing page read 2026-10-21: 1 GB stored
    and ~10 GB downloaded a month no-cost, then $5/GB and $1/GB)."""
    for rel, text in (("a.py", "from firebase_admin import db\n"), ("b.ts", "import { getDatabase } from 'firebase/database'\n"),
                      ("c.js", "const { getDatabase } = require('firebase-admin/database')\n")):
        assert [h[0] for h in CH.scan_text(rel, text)["hits"]] == [("firebase", "database.document", "rtdb")], rel
    node = {"id": "rtdb", "category": "database.document", "provider": "firebase", "providerResolved": "firebase",
            "service": "rtdb"}
    assert RULES.lookup(node).id == "firebase/rtdb"
    got = month(node, {"storage_gb": 3.0, "egress_gb": 25 / 730}, 0, 730)
    assert {k: round(v, 6) for k, v in got.items()} == {"storage": 10.0, "download": 15.0}
    assert month(node, {"storage_gb": 0.5, "egress_gb": 5 / 730}, 0, 744) == {"storage": 0.0, "download": 0.0}


def test_ecr_is_its_images_stored():
    """Draft A's hand count: "ECR 保存 $0.10 / GB月 × 3 GB = $0.30 / env" (https://aws.amazon.com/ecr/pricing/).
    The pulls in the same region are free (their data through a NAT gateway is the NAT's processed_gb)."""
    node = aws("ecr", "ci", "ecr")
    assert RULES.lookup(node).id == "aws/ecr" and RULES.lookup(node).reads == ("storage_gb",)
    for region in AWS_REGIONS:
        assert round(sum(month(node, {"storage_gb": 3.0}, 0, 730, region).values()), 6) == 0.30


def test_ecr_is_priced_on_its_standard_storage_not_the_archive():
    """The ECR offer holds standard storage (TimedStorage-ByteHrs) and the archive's (TimedStorage-Archive-ByteHrs,
    stepped); the images a pull reads are the standard's."""
    spec = [s for s in A.regional_spec() if s["offer"] == "AmazonECR"]

    def product(ut):
        return {"productFamily": "EC2 Container Registry", "attributes": {"usagetype": ut}}
    offer = {"publicationDate": "2026-09-11T12:44:25Z", "products": {
        "S": product("APN1-TimedStorage-ByteHrs"), "R": product("APN1-TimedStorage-Archive-ByteHrs")},
        "terms": {"OnDemand": {k: {"t": {"priceDimensions": {"d": {"pricePerUnit": {"USD": usd}, "beginRange": "0",
                                                                 "endRange": "Inf"}}}}
                               for k, usd in (("S", "0.10"), ("R", "0.0114"))}}}
    rows, missing = A.rows_from_offer(offer, spec, "ap-northeast-1", "u")
    assert missing == [] and [(r["service"], r["sku"], r["price_usd"]) for r in rows] == [("ecr", "storage", 0.1)]


# ---------------------------------------------------------------- the rest of stage B (2.3.15): its own rules and rows
# (label, node, quantities per hour, how many run, the month of 730 hours by hand from the offers' prices of 10-21)
REST = [
    ("Step Functions Standard 100,000 transitions (4,000 free)", aws("sf", "compute.function", "stepfunctions"),
     {"state_transitions": 100_000 / 730}, 0, (100_000 - 4000) / 1000 * 0.025),
    ("Step Functions Express 1 million requests, 100 ms, 64 MB",
     aws("sf", "compute.function", "stepfunctions", spec=[{"key": "workflow_type", "value": "EXPRESS"}]),
     {"requests": 1_000_000 / 730, "duration_ms": 100.0, "memory_mb": 64.0}, 0, 1.0 + 1_000_000 * 0.1 * 0.0625 * 0.00001667),
    ("App Runner 1 vCPU 2 GB, active every hour", aws("ar", "compute.paas", "apprunner"),
     {"vcpu": 1.0, "memory_gb": 2.0, "requests": 10.0}, 1, 730 * (0.0809 + 2 * 0.00885)),
    ("App Runner 1 vCPU 2 GB, idle (provisioned)", aws("ar", "compute.paas", "apprunner"),
     {"vcpu": 1.0, "memory_gb": 2.0}, 1, 730 * 2 * 0.00885),
    ("Lightsail micro_3_0 + a 10 GB disk", aws("ls", "compute.vm", "lightsail"),
     {"_sku": "micro_3_0", "storage_gb": 10.0}, 1, 730 * 0.0094 + 10 * 0.1),
    ("Lightsail a bundle written by its memory (16GB)", aws("ls", "compute.vm", "lightsail"), {"_sku": "16GB"}, 1,
     730 * 0.1129),
    ("Lightsail database small_ha_2_0", aws("lsd", "database.relational", "lightsail"), {"_sku": "small_ha_2_0"}, 1,
     730 * 0.08065),
    ("Lightsail database medium_2_0, the node's ha multi-az", aws("lsd", "database.relational", "lightsail", ha="multi-az"),
     {"_sku": "medium_2_0"}, 1, 730 * 0.16129),
    ("Gateway Load Balancer, 2 GB an hour (2 GLCU)", aws("gw", "load_balancer", "elb.gwlb"), {"processed_gb": 2.0}, 1,
     730 * 0.0135 + 730 * 2 * 0.004),
    ("Gateway Load Balancer, 1,200 new flows a second (2 GLCU; an ALB's units would be 48)",
     aws("gw", "load_balancer", "elb.gwlb"), {"new_connections": 1200 * 3600.0}, 1, 730 * 0.0135 + 730 * 2 * 0.004),
    ("Classic Load Balancer + 100 GB processed", aws("clb", "load_balancer", "elb.classic"),
     {"processed_gb": 100 / 730}, 1, 730 * 0.027 + 100 * 0.008),
    ("EventBridge 3 million custom events", aws("eb", "scheduler", "eventbridge"), {"requests": 3_000_000 / 730}, 0, 3.0),
]


@pytest.mark.parametrize("label, node, q, running, hand", REST, ids=[x[0] for x in REST])
def test_the_rest_of_stage_b_comes_out_of_the_bundled_prices(label, node, q, running, hand):
    assert round(sum(month(node, dict(q), running, 730).values()), 4) == round(hand, 4), label


def test_a_lightsail_bundle_not_known_is_not_guessed():
    """xlarge and 2xlarge are not in the docs read (their memory is not said there): no price, not another bundle's."""
    node = aws("ls", "compute.vm", "lightsail")
    (m,) = RULES.lookup(node).cost(F.Hour(node=node, q={}, running=1.0, sku="xlarge_3_0"))
    assert m.sku == "xlarge" and BOOK.find("aws", "lightsail", m.sku, m.unit, "ap-northeast-1", ON) is None


def test_step_functions_standard_reads_transitions_not_requests():
    """A Standard workflow is billed per state transition, which requests do not say (a step is not an execution):
    with requests alone it charges nothing rather than guess; Express is billed by its requests."""
    node = aws("sf", "compute.function", "stepfunctions")
    assert RULES.lookup(node).cost(F.Hour(node=node, q={"requests": 5.0}, running=0.0)) == []
    express = dict(node, spec=[{"key": "type", "value": "express"}])
    assert [m.sku for m in RULES.lookup(express).cost(F.Hour(node=express, q={"requests": 5.0}, running=0.0))] == [
        "requests:express"]


def _offer(products: dict, prices: dict) -> dict:
    return {"publicationDate": "2026-09-11T12:45:44Z", "products": products,
            "terms": {"OnDemand": {k: {"t": {"priceDimensions": {"d": {"pricePerUnit": {"USD": usd}, "beginRange": "0",
                                                                     "endRange": "Inf"}}}}
                                   for k, usd in prices.items()}}}


def test_the_load_balancers_of_one_usage_type_are_told_by_their_family():
    """The ELB offer names every load balancer's hour LoadBalancerUsage: Classic's family is "Load Balancer",
    Gateway's "Load Balancer-Gateway" (and the application and network ones' theirs)."""
    spec = [s for s in A.regional_spec() if s["offer"] == "AWSELB"]

    def product(ut, fam):
        return {"productFamily": fam, "attributes": {"usagetype": ut}}
    # the gateway's first: a row taken without its family would be the first one's
    fams = {"G": "Load Balancer-Gateway", "A": "Load Balancer-Application", "N": "Load Balancer-Network", "C": "Load Balancer"}
    products = {k: product("APN1-LoadBalancerUsage", f) for k, f in fams.items()}
    products |= {k + "L": product("APN1-LCUUsage", f) for k, f in fams.items() if k != "C"}
    products["CP"] = product("APN1-DataProcessing-Bytes", "Load Balancer")
    prices = {"C": "0.027", "G": "0.0135", "A": "0.0243", "N": "0.0243", "GL": "0.004", "AL": "0.008", "NL": "0.006",
              "CP": "0.008"}
    rows, missing = A.rows_from_offer(_offer(products, prices), spec, "ap-northeast-1", "u")
    got = {(r["service"], r["sku"]): r["price_usd"] for r in rows}
    assert missing == [] and (got[("elb.classic", "hour")], got[("elb.gwlb", "hour")], got[("elb.gwlb", "lcu")],
                              got[("elb.classic", "processed")]) == (0.027, 0.0135, 0.004, 0.008)


def test_custom_events_are_not_partner_events():
    """EventBridge's custom and partner events share the usage type Event-64K-Chunks: the custom events' row is the
    one whose eventType says so."""
    spec = [s for s in A.regional_spec() if s["offer"] == "AWSEvents" and s["service"] == "eventbridge"]

    def product(kind):
        return {"productFamily": "EventBridge", "attributes": {"usagetype": "APN1-Event-64K-Chunks", "eventType": kind}}
    offer = _offer({"P": product("Partner Event"), "C": product("Custom Event")}, {"P": "0.000002", "C": "0.000001"})
    rows, missing = A.rows_from_offer(offer, spec, "ap-northeast-1", "u")
    assert missing == [] and [(r["sku"], r["price_usd"]) for r in rows] == [("events", 1.0)]


def test_a_lightsail_bundle_is_its_linux_ipv4_one():
    """Lightsail's offer has each size as Linux, Linux IPv6-only (_IPv6) and Windows (_win): the bundle is the Linux one
    with a public IPv4 address. In the offers of 10-21 the usage type alone tells them apart (no usage type has two
    operating systems, in either region); the operating system is a guard against a Windows row of the same name,
    first here so a spec without it would take it."""
    spec = [s for s in A.regional_spec() if s["offer"] == "AmazonLightsail" and s["sku"] == "1GB"]

    def product(ut, os_):
        return {"productFamily": "Lightsail Instance", "attributes": {"usagetype": ut, "operatingSystem": os_}}
    offer = _offer({"X": product("APN1-BundleUsage:1GB", "Windows"), "L": product("APN1-BundleUsage:1GB", "Linux"),
                    "6": product("APN1-BundleUsage:1GB_IPv6", "Linux"), "W": product("APN1-BundleUsage:1GB_win", "Windows")},
                   {"L": "0.0094", "6": "0.00672", "W": "0.0161", "X": "0.0161"})
    rows, missing = A.rows_from_offer(offer, spec, "ap-northeast-1", "u")
    assert missing == [] and [r["price_usd"] for r in rows] == [0.0094]


def test_every_line_of_the_offer_spec_is_in_the_bundled_table():
    """build_bundled writes one row per line of the spec and region: a line added to the spec with the table not built
    again, or a row the build lost, is a line with no row here."""
    have = {(r["service"], r["sku"], r["region"]): r for r in json.loads(PB.BUNDLED_PATH.read_text(encoding="utf-8"))["prices"]
            if r["provider"] == "aws"}
    lost = [(s["service"], s["sku"], region) for s in A.regional_spec() for region in AWS_REGIONS
            if (s["service"], s["sku"], region) not in have]
    assert lost == []
    # and as the spec says it: its unit, its per_units, its free amount (a spec changed and the table not built again)
    differ = [(s["service"], s["sku"], region) for s in A.regional_spec() for region in AWS_REGIONS
              if (lambda r: (r["unit"], r.get("per_units", 1), r.get("free")) != (s["unit"], s["per_units"], s["free"]))(
                  have[(s["service"], s["sku"], region)])]
    assert differ == []
