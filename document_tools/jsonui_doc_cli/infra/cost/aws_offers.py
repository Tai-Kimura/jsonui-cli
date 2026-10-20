"""Price rows (infra-prices.v0) from AWS's Price List offer files (the public bulk files,
https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<service>/current/<region>/index.json). A pure function over
the parsed file: the bundled table is written with it (tools/build_bundled_prices.py), and the fetching (L-B2) will
use it too. Only on-demand prices; a price's steps (beginRange/endRange) become tiers; the free amounts AWS gives
outside the file (Lambda's monthly free tier) come from SPEC with the page that says them.
"""
from __future__ import annotations

OFFER_URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{offer}/current/{region}/index.json"
GLOBAL_OFFER_URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{offer}/current/index.json"
PREFIX = {"ap-northeast-1": ["APN1-"], "us-east-1": ["", "USE1-"]}
CF_ZONES = {"US": "north_america", "EU": "europe", "JP": "japan", "AP": "asia", "IN": "india",
            "AU": "australia", "SA": "south_america", "ZA": "south_africa", "ME": "middle_east"}


def S(offer, service, sku, unit, usagetype, per_units=1, family=None, attrs=None, free=None, note=None, scale=1.0):
    """One line of the spec: which offer row becomes which price. usagetype is a name (after the region's prefix), a
    list of names (the regions spell some differently), or a name ending in "*" (a prefix: RDS abbreviates xlarge to
    "xl", so its rows are matched by the instanceType attribute). scale multiplies the price (regional transfer is
    charged in and out)."""
    return {"offer": offer, "service": service, "sku": sku, "unit": unit, "usagetype": usagetype, "per_units": per_units,
            "family": family, "attrs": attrs or {}, "free": free, "note": note, "scale": scale}


LAMBDA_FREE = "https://aws.amazon.com/lambda/pricing/"
RDS_TYPES = ["db.t4g.micro", "db.t4g.small", "db.t4g.medium", "db.m6g.large", "db.r6g.large", "db.r6g.xlarge",
             "db.r6g.2xlarge"]
CACHE_TYPES = ["cache.t4g.micro", "cache.t4g.small", "cache.t4g.medium", "cache.m7g.large", "cache.r7g.large"]


def regional_spec() -> list[dict]:
    out = [
        S("AWSLambda", "lambda", "requests", "request", "Request", 1_000_000, family="Serverless",
          free={"amount": 1_000_000, "period": "month"}, note=f"free tier: {LAMBDA_FREE}"),
        S("AWSLambda", "lambda", "compute", "GB-second", "Lambda-GB-Second", family="Serverless",
          free={"amount": 400_000, "period": "month"}, note=f"x86; free tier: {LAMBDA_FREE}"),
        S("AmazonECS", "ecs", "vcpu", "vCPU-hour", "Fargate-vCPU-Hours:perCPU", note="Fargate Linux/x86"),
        S("AmazonECS", "ecs", "memory", "GB-hour", "Fargate-GB-Hours", note="Fargate Linux/x86"),
        S("AmazonS3", "s3", "storage", "GB-month", "TimedStorage-ByteHrs", family="Storage", note="S3 Standard"),
        S("AmazonS3", "s3", "put", "request", "Requests-Tier1", 1000, note="PUT, COPY, POST, LIST"),
        S("AmazonS3", "s3", "get", "request", "Requests-Tier2", 1000, note="GET and all other requests"),
        S("AmazonDynamoDB", "dynamodb", "read", "read_unit", "ReadRequestUnits", 1_000_000, note="on-demand"),
        S("AmazonDynamoDB", "dynamodb", "write", "write_unit", "WriteRequestUnits", 1_000_000, note="on-demand"),
        S("AmazonDynamoDB", "dynamodb", "storage", "GB-month", "TimedStorage-ByteHrs", family="Database Storage",
          note="Standard table class"),
        S("AmazonApiGateway", "apigateway", "requests", "request", "ApiGatewayHttpRequest", 1_000_000, note="HTTP API"),
        S("AmazonApiGateway", "apigateway.rest", "requests", "request", "ApiGatewayRequest", 1_000_000, note="REST API"),
        S("AWSQueueService", "sqs", "requests", "request", ["Requests-Tier1", "Requests-RBP"], 1_000_000,
          free={"amount": 1_000_000, "period": "month"}, note="standard queue; free: the offer's Global-Requests row"),
        S("AmazonSNS", "sns", "requests", "request", "Requests-Tier1", 1_000_000, note="API requests"),
        S("AWSELB", "elb.alb", "hour", "instance-hour", "LoadBalancerUsage", family="Load Balancer-Application"),
        S("AWSELB", "elb.alb", "lcu", "LCU-hour", "LCUUsage", family="Load Balancer-Application"),
        S("AWSELB", "elb.nlb", "hour", "instance-hour", "LoadBalancerUsage", family="Load Balancer-Network"),
        S("AWSELB", "elb.nlb", "lcu", "LCU-hour", "LCUUsage", family="Load Balancer-Network"),
        S("AmazonEKS", "eks", "cluster", "instance-hour", "AmazonEKS-Hours:perCluster", note="standard support"),
        S("AWSSecretsManager", "secretsmanager", "secret", "secret", "AWSSecretsManager-Secrets"),
        S("AWSSecretsManager", "secretsmanager", "api", "request", "AWSSecretsManagerAPIRequest", 10_000),
        S("AmazonCloudWatch", "cloudwatch", "ingest", "GB", "DataProcessing-Bytes", note="logs, Standard class"),
        S("AmazonCloudWatch", "cloudwatch", "storage", "GB-month", "TimedStorage-ByteHrs", family="Storage Snapshot",
          note="logs storage"),
        S("AmazonKinesis", "kinesis", "shard", "capacity_unit-hour", "Storage-ShardHour", note="provisioned shard"),
        S("AWSDataTransfer", "data-transfer", "egress", "GB", "DataTransfer-Out-Bytes",
          note="to the internet, beyond the global free tier"),
        S("AWSDataTransfer", "data-transfer", "transfer-regional", "GB", "DataTransfer-Regional-Bytes", scale=2.0,
          note="across zones: the offer's price, charged in and out (x2)"),
        S("AWSDataTransfer", "data-transfer", "transfer-inter-region", "GB", "AWS-Out-Bytes",
          note="out of the region to another AWS region"),
    ]
    for engine, svc in (("MySQL", "rds.mysql"), ("PostgreSQL", "rds.postgres")):
        for t in RDS_TYPES:
            out.append(S("AmazonRDS", svc, t, "instance-hour", "InstanceUsage:*",
                         attrs={"databaseEngine": engine, "deploymentOption": "Single-AZ", "instanceType": t}))
            out.append(S("AmazonRDS", svc, f"{t}:multi-az", "instance-hour", "Multi-AZUsage:*",
                         attrs={"databaseEngine": engine, "deploymentOption": "Multi-AZ", "instanceType": t}))
        out.append(S("AmazonRDS", svc, "storage", "GB-month", "RDS:GP3-Storage",
                     attrs={"databaseEngine": engine, "deploymentOption": "Single-AZ"}, note="gp3"))
        out.append(S("AmazonRDS", svc, "storage:multi-az", "GB-month", "RDS:Multi-AZ-GP3-Storage",
                     attrs={"databaseEngine": engine, "deploymentOption": "Multi-AZ"}, note="gp3"))
    for t in CACHE_TYPES:
        out.append(S("AmazonElastiCache", "elasticache", t, "instance-hour", f"NodeUsage:{t}",
                     attrs={"cacheEngine": "Redis"}, note="Redis OSS"))
    return out


def cloudfront_spec() -> list[dict]:
    out = []
    for code, zone in CF_ZONES.items():
        out.append(S("AmazonCloudFront", "cloudfront", f"egress-{zone}", "GB", f"{code}-DataTransfer-Out-Bytes",
                     note=f"to viewers in {code}"))
        out.append(S("AmazonCloudFront", "cloudfront", f"requests-{zone}", "request", f"{code}-Requests-Tier2-HTTPS",
                     10_000, note=f"HTTPS, viewers in {code}"))
    return out


def _round(x: float) -> float:
    return float(f"{x:.10g}")


def _dimensions(data: dict, sku: str) -> list[dict]:
    terms = data.get("terms", {}).get("OnDemand", {}).get(sku, {})
    return [pd for t in terms.values() for pd in t["priceDimensions"].values()]


def price_row(dims: list[dict], spec: dict, region: str, effective: str, source: str) -> dict | None:
    """One price row from an offer row's price dimensions: one price, or tiers (from the ranges, in order)."""
    if not dims:
        return None
    k = spec["per_units"] * spec["scale"]
    row = {"provider": "aws", "service": spec["service"], "sku": spec["sku"], "region": region, "unit": spec["unit"],
           "effective": effective, "source": source}
    if spec["per_units"] != 1:
        row["per_units"] = spec["per_units"]
    steps = sorted(dims, key=lambda d: float(d.get("beginRange") or 0))
    if len(steps) == 1 and float(steps[0].get("beginRange") or 0) == 0:
        row["price_usd"] = _round(float(steps[0]["pricePerUnit"]["USD"]) * k)
    else:
        row["tiers"] = []
        for d in steps:
            t = {"from": float(d.get("beginRange") or 0), "price_usd": _round(float(d["pricePerUnit"]["USD"]) * k)}
            if d.get("endRange") not in (None, "Inf"):
                t["to"] = float(d["endRange"])
            row["tiers"].append(t)
    if spec["free"]:
        row["free"] = dict(spec["free"])
    if spec["note"]:
        row["note"] = spec["note"][:200]
    return row


def rows_from_offer(data: dict, spec: list[dict], region: str, url: str) -> tuple[list[dict], list[str]]:
    """(price rows, the spec lines no product matched) for one offer file. effective: the file's publication date."""
    effective = (data.get("publicationDate") or "")[:10]
    prefixes = PREFIX.get(region, [""]) if region != "global" else [""]
    out, missing = [], []
    for s in spec:
        names = s["usagetype"] if isinstance(s["usagetype"], list) else [s["usagetype"]]
        uts = {p + n for p in prefixes for n in names}

        def named(ut: str | None) -> bool:
            return ut in uts or any(u.endswith("*") and (ut or "").startswith(u[:-1]) for u in uts)
        hits = [sku for sku, p in data.get("products", {}).items()
                if named(p.get("attributes", {}).get("usagetype"))
                and (s["family"] is None or p.get("productFamily") == s["family"])
                and all(p.get("attributes", {}).get(k) == v for k, v in s["attrs"].items())]
        rows = [r for r in (price_row(_dimensions(data, sku), s, region, effective, url) for sku in hits) if r]
        if not rows:
            missing.append(f"{s['service']} {s['sku']} ({s['usagetype']})")
            continue
        out.append(rows[0])
    return out, missing
