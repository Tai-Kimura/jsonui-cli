"""AWS's rules: the generic formulas with AWS's constants and skus, each with the official page it follows and the day
it was read (plan, 作りの決まり 4). The prices are in the price files (the bundled table has AWS ap-northeast-1 and
us-east-1 from AWS's Price List offer files)."""
from __future__ import annotations

import re
from functools import partial

from .. import model as M
from ..cost import formulas as F
from . import provider_rule

CHECKED = "2026-10-20"
NLB = {"new_connections_per_second": 800, "active_connections": 100_000, "processed_gb_per_hour": 1}
# a Gateway Load Balancer Capacity Unit (the page read 2026-10-21): 600 new flows a second, 60,000 active, 1 GB an hour
GWLB = {"new_connections_per_second": 600, "active_connections": 60_000, "processed_gb_per_hour": 1}
PAGES = {
    "lambda": "https://aws.amazon.com/lambda/pricing/",
    "fargate": "https://aws.amazon.com/fargate/pricing/",
    "ec2": "https://aws.amazon.com/ec2/pricing/on-demand/",
    "eks": "https://aws.amazon.com/eks/pricing/",
    "cloudfront": "https://aws.amazon.com/cloudfront/pricing/",
    "route53": "https://aws.amazon.com/route53/pricing/",
    "waf": "https://aws.amazon.com/waf/pricing/",
    "elb": "https://aws.amazon.com/elasticloadbalancing/pricing/",
    "apigateway": "https://aws.amazon.com/api-gateway/pricing/",
    "rds": "https://aws.amazon.com/rds/pricing/",
    "dynamodb": "https://aws.amazon.com/dynamodb/pricing/on-demand/",
    "opensearch": "https://aws.amazon.com/opensearch-service/pricing/",
    "elasticache": "https://aws.amazon.com/elasticache/pricing/",
    "s3": "https://aws.amazon.com/s3/pricing/",
    "efs": "https://aws.amazon.com/efs/pricing/",
    "ebs": "https://aws.amazon.com/ebs/pricing/",
    "sqs": "https://aws.amazon.com/sqs/pricing/",
    "sns": "https://aws.amazon.com/sns/pricing/",
    "kinesis": "https://aws.amazon.com/kinesis/data-streams/pricing/",
    "scheduler": "https://aws.amazon.com/eventbridge/pricing/",
    "ses": "https://aws.amazon.com/ses/pricing/",
    "cognito": "https://aws.amazon.com/cognito/pricing/",
    "secretsmanager": "https://aws.amazon.com/secrets-manager/pricing/",
    "cloudwatch": "https://aws.amazon.com/cloudwatch/pricing/",
    "nat": "https://aws.amazon.com/vpc/pricing/",
    "ipv4": "https://aws.amazon.com/vpc/pricing/",
    "aurora": "https://aws.amazon.com/rds/aurora/pricing/",
    "docdb": "https://aws.amazon.com/documentdb/pricing/",
    "msk": "https://aws.amazon.com/msk/pricing/",
    "kms": "https://aws.amazon.com/kms/pricing/",
    "ssm": "https://aws.amazon.com/systems-manager/pricing/",
    "ecr": "https://aws.amazon.com/ecr/pricing/",
    "stepfunctions": "https://aws.amazon.com/step-functions/pricing/",
    "apprunner": "https://aws.amazon.com/apprunner/pricing/",
    "lightsail": "https://aws.amazon.com/lightsail/pricing/",
    "eventbridge": "https://aws.amazon.com/eventbridge/pricing/",
}


def _r(name: str, category: str, service: str, cost, page: str | None = None, checked: str = CHECKED, **extra) -> None:
    provider_rule(f"aws/{name}", category, "aws", service, cost, PAGES[page or name], checked, **extra)


def sqs(h: F.Hour, ops_per_message: int = 3) -> list[F.Meter]:
    """Each message is sent, received and deleted: 3 requests (64 KB each, counted as one here)."""
    if "messages" not in h.q and "requests" not in h.q:
        return []
    n = h.q.get("messages", 0.0) * ops_per_message + h.q.get("requests", 0.0)
    return [F.Meter("requests", n, "request", "requests", "messages" if "messages" in h.q else "requests")]


def dynamodb(h: F.Hour) -> list[F.Meter]:
    """On-demand reads and writes and storage, and provisioned capacity: reads and writes each their own price."""
    return F.key_value(h) + F.provisioned(h)


def elasticache(h: F.Hour) -> list[F.Meter]:
    """Nodes by the hour (the type), or Serverless when ECPUs are given: the data stored by the GB-hour and the ECPUs
    (Valkey's own prices when the node's engine or spec says valkey)."""
    if "ecpu" not in h.q:
        return F.instances(h)
    tag = ":valkey" if "valkey" in (str(h.node.get("engine") or "") + F.spec_value(h.node, "engine")).lower() else ""
    out = [F.Meter("ecpu", h.q["ecpu"], "ECPU", f"ecpu{tag}", "ecpu")]
    if "storage_gb" in h.q:
        out.append(F.Meter("storage", h.q["storage_gb"], "GB-hour", f"cached-data{tag}", "storage_gb"))
    return out


def cognito(h: F.Hour) -> list[F.Meter]:
    """Monthly active users on the pool's tier (spec tier: lite, essentials, plus; a new pool's is essentials)."""
    tier = F.spec_value(h.node, "tier", "feature_plan", "user_pool_tier")
    sku = {"lite": "mau:lite", "plus": "mau:plus"}.get(tier, "mau")
    return F.per_month(h, sku, "user", "monthly_active_users", name="mau")


def kms(h: F.Hour) -> list[F.Meter]:
    """Customer managed keys (secrets: how many), each a monthly fee, and the API requests."""
    return F.per_month(h, "key", "month", "secrets", name="key") + F.counted(h, "requests", "api", "request", "api")


def ssm(h: F.Hour) -> list[F.Meter]:
    """Parameter Store: a standard parameter and its API interactions are free (a price of 0); an advanced one (spec
    tier: advanced) has its month and its API interactions."""
    adv = ":advanced" if F.spec_value(h.node, "tier") == "advanced" else ""
    return (F.per_month(h, f"secret{adv}", "secret", "secrets", name="secret")
            + F.counted(h, "requests", f"api{adv}", "request", "api"))


def step_functions(h: F.Hour) -> list[F.Meter]:
    """Standard workflows (AWS's default): each state transition. Express (spec workflow_type or type: express): its
    requests and their duration in GB-seconds, as a function's."""
    if F.spec_value(h.node, "workflow_type", "type") == "express":
        return [F.Meter(m.name, m.amount, m.unit, f"{m.sku}:express", m.quantity)
                for m in F.function(h) if m.sku in ("requests", "compute")]
    return F.counted(h, "state_transitions", "transitions", "request", "transitions")


def _any(quantities: dict, name: str, running: list | None = None) -> bool:
    """Some hour of the run has ``name`` above 0 (and, given ``running``, an instance running then)."""
    hours = (quantities.get(name) or {}).get("perHour") or []
    return any(v > 0 and (running is None or running[k] > 0) for k, v in enumerate(hours))


def step_functions_notice(node: dict, quantities: dict, running: list) -> list[tuple[str, str]]:
    """A Standard workflow with requests and no state_transitions is 0: say so (the transitions are not guessed)."""
    if F.spec_value(node, "workflow_type", "type") == "express" or "state_transitions" in quantities:
        return []
    if not _any(quantities, "requests"):
        return []
    return [("cost.stepfunctions_no_transitions", M.Why(f"{node['id']}: a Standard workflow is billed per state "
             "transition; its load has requests and no state_transitions, so it is priced 0 (write state_transitions, "
             "or spec workflow_type: express)", "cost.stepfunctions_no_transitions"))]


def app_runner_notice(node: dict, quantities: dict, running: list) -> list[tuple[str, str]]:
    """An hour with requests is counted active through the hour: say that it is the most it can be."""
    if not ("vcpu" in quantities and "memory_gb" in quantities and _any(quantities, "requests", running)):
        return []
    return [("cost.apprunner_active_upper_bound", M.Why(f"{node['id']}: each hour with requests is counted as active "
             "for the whole hour (vCPU and memory); App Runner bills the seconds it processes requests, so this is the "
             "most it can be", "cost.apprunner_active_upper_bound"))]


def app_runner(h: F.Hour) -> list[F.Meter]:
    """Each instance's memory while provisioned (idle), and its vCPU and memory while active. An hour with requests
    counts as active through the hour (AWS bills the seconds it processes them: this is the most it can be)."""
    if not h.running or "vcpu" not in h.q or "memory_gb" not in h.q:
        return F.egress(h)
    if h.q.get("requests"):
        out = [F.Meter("vcpu", h.q["vcpu"] * h.running, "vCPU-hour", "vcpu", "vcpu"),
               F.Meter("memory", h.q["memory_gb"] * h.running, "GB-hour", "memory", "memory_gb")]
    else:
        out = [F.Meter("memory", h.q["memory_gb"] * h.running, "GB-hour", "memory:provisioned", "memory_gb")]
    return out + F.egress(h)


#: Lightsail's bundle ids -> the memory the offer names their bundles by (the AWS CLI reference's get-bundles and
#: get-relational-database-bundles, and the Lightsail user guide's snapshot page, read 2026-10-21). A bundle written
#: by its memory ("16GB") is that; one not here is not guessed.
LIGHTSAIL_BUNDLES = {"nano": "0.5GB", "micro": "1GB", "small": "2GB", "medium": "4GB", "large": "8GB"}
LIGHTSAIL_DB_BUNDLES = {"micro": "1GB", "small": "2GB", "medium": "4GB", "large": "8GB"}


def _lightsail_size(sku: str | None, names: dict) -> tuple[str, bool]:
    """(the offer's size, high availability) from a bundle id ("micro_3_0", "small_ha_2_0") or a size ("2GB")."""
    m = re.fullmatch(r"([0-9a-z]+?)(_ha)?(_\d+_\d+)?", (sku or "").strip().lower())
    if not m:
        return sku or "instance", False
    head = m.group(1)
    return names.get(head, head.upper() if re.fullmatch(r"[0-9.]+gb", head) else head), bool(m.group(2))


def lightsail(h: F.Hour) -> list[F.Meter]:
    """A bundle by the hour (its disk and its data transfer quota are in its price), and block storage disks."""
    if not h.running:
        return F.stored(h)
    size, _ha = _lightsail_size(h.sku, LIGHTSAIL_BUNDLES)
    return [F.Meter("instance", h.running, "instance-hour", size)] + F.stored(h)


def lightsail_database(h: F.Hour) -> list[F.Meter]:
    """A database bundle by the hour, high availability its own bundle (the node's ha, or an "_ha" bundle id); its
    storage is in the price."""
    if not h.running:
        return []
    size, ha = _lightsail_size(h.sku, LIGHTSAIL_DB_BUNDLES)
    multi = ha or "multi" in (h.node.get("ha") or "").lower()
    return [F.Meter("instance", h.running, "instance-hour", f"db:{size}:multi-az" if multi else f"db:{size}")]


def classic_load_balancer(h: F.Hour) -> list[F.Meter]:
    """The hours it runs and the GB it processes (no capacity units: the previous generation's billing)."""
    return F.instances(h, "hour", "hour") + F.counted(h, "processed_gb", "processed", "GB", "processed")


def event_bus(h: F.Hour) -> list[F.Meter]:
    """A rule on an event bus: its requests are the custom events published to the bus. A scheduled rule's runs are
    free (EventBridge Scheduler is aws/scheduler)."""
    return F.counted(h, "requests", "events", "request", "events")


_r("lambda", "compute.function", "lambda", F.function)
_r("fargate", "compute.container", "ecs", F.container)
_r("ec2", "compute.vm", "ec2", F.vm)
_r("eks", "compute.k8s", "eks", F.k8s)
_r("cloudfront", "edge.cdn", "cloudfront", F.cdn)
_r("route53", "edge.dns", "route53", F.dns)
_r("waf", "edge.waf", "waf", partial(F.waf, acl_optional=False))
_r("alb", "load_balancer", "elb.alb", F.load_balancer, "elb")
_r("nlb", "load_balancer", "elb.nlb", partial(F.load_balancer, dims=NLB), "elb")
_r("apigateway", "gateway.api", "apigateway", F.gateway)
_r("rds", "database.relational", "rds", F.relational)
DYNAMODB = ("requests", "read_units", "write_units", "storage_gb", "read_capacity_units", "write_capacity_units")
_r("dynamodb", "database.kv", "dynamodb", dynamodb, reads=DYNAMODB)
_r("dynamodb-document", "database.document", "dynamodb", dynamodb, "dynamodb", reads=DYNAMODB)
_r("opensearch", "database.search", "opensearch", F.search)
_r("elasticache", "cache", "elasticache", elasticache, reads=("requests", "storage_gb", "ecpu"))
_r("s3", "storage.object", "s3", F.object_store)
_r("efs", "storage.file", "efs", F.file_store)
_r("ebs", "storage.block", "ebs", F.file_store)
_r("sqs", "queue", "sqs", sqs)
_r("sns", "queue", "sns", partial(sqs, ops_per_message=1))
_r("kinesis", "stream", "kinesis", F.stream)
_r("scheduler", "scheduler", "scheduler", F.scheduler)   # EventBridge Scheduler (a rule on the bus: eventbridge)
_r("ses", "mail", "ses", F.mail)
_r("cognito", "auth", "cognito", cognito)
_r("secretsmanager", "secrets", "secretsmanager", F.secrets)
_r("cloudwatch", "monitoring", "cloudwatch", F.monitoring)
# ticket 2026-10-21-infra-bundled-prices-missing-common-aws-rows: the pages read that day
_r("cloudwatch-alarm", "monitoring.alarm", "cloudwatch", F.alarm, "cloudwatch", checked="2026-10-21")
_r("nat", "gateway.nat", "vpc.nat", F.nat, checked="2026-10-21")
_r("ipv4", "network.ip", "vpc.ipv4", F.ip_address, checked="2026-10-21")
# the ticket's stage B: the pages read 10-21
_r("aurora", "database.relational", "aurora", partial(F.relational, multi_az=False), checked="2026-10-21",
   reads=("requests", "storage_gb", "capacity_units", "egress_gb"))   # a replica is one more instance: no Multi-AZ price
_r("docdb", "database.document", "docdb", F.search, checked="2026-10-21", reads=("requests", "storage_gb"), hourly=True)
_r("msk", "stream", "msk", F.search, checked="2026-10-21", reads=("storage_gb",))   # a broker an instance
_r("kms", "secrets", "kms", kms, checked="2026-10-21")
_r("ssm", "secrets", "ssm", ssm, checked="2026-10-21")
# a registry's images stored (the pulls in the same region are free; their data through a NAT gateway is the NAT's)
_r("ecr", "ci", "ecr", F.file_store, checked="2026-10-21", reads=("storage_gb",))
# the rest of stage B: the pages read 10-21
_r("stepfunctions", "compute.function", "stepfunctions", step_functions, checked="2026-10-21",
   reads=("requests", "state_transitions", "duration_ms", "memory_mb"), notice=step_functions_notice)
_r("apprunner", "compute.paas", "apprunner", app_runner, checked="2026-10-21",
   reads=("requests", "vcpu", "memory_gb", "egress_gb"), notice=app_runner_notice)
_r("lightsail", "compute.vm", "lightsail", lightsail, checked="2026-10-21", reads=("storage_gb",))
_r("lightsail-database", "database.relational", "lightsail", lightsail_database, "lightsail", checked="2026-10-21",
   reads=())
_r("gwlb", "load_balancer", "elb.gwlb", partial(F.load_balancer, dims=GWLB), "elb", checked="2026-10-21")
_r("classic-lb", "load_balancer", "elb.classic", classic_load_balancer, "elb", checked="2026-10-21",
   reads=("processed_gb",))
_r("eventbridge", "scheduler", "eventbridge", event_bus, checked="2026-10-21")
