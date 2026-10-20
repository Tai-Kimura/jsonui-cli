"""AWS's rules: the generic formulas with AWS's constants and skus, each with the official page it follows and the day
it was read (plan, 作りの決まり 4). The prices are in the price files (the bundled table has AWS ap-northeast-1 and
us-east-1 from AWS's Price List offer files)."""
from __future__ import annotations

from functools import partial

from ..cost import formulas as F
from . import provider_rule

CHECKED = "2026-10-20"
NLB = {"new_connections_per_second": 800, "active_connections": 100_000, "processed_gb_per_hour": 1}
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
