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
RDS_TYPES = ["db.t3.micro", "db.t3.small", "db.t3.medium", "db.t4g.micro", "db.t4g.small", "db.t4g.medium", "db.m6g.large", "db.r6g.large", "db.r6g.xlarge",
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
        # ticket 2026-10-21-infra-bundled-prices-missing-common-aws-rows (usage types read in the offers of 10-21)
        S("AWSLambda", "lambda", "compute:arm64", "GB-second", "Lambda-GB-Second-ARM", family="Serverless",
          free={"amount": 400_000, "period": "month"},
          note=f"ARM (Graviton); AWS's free tier is shared with x86, counted per row here: {LAMBDA_FREE}"),
        S("AmazonECS", "ecs", "vcpu:arm64", "vCPU-hour", "Fargate-ARM-vCPU-Hours:perCPU", note="Fargate Linux/ARM"),
        S("AmazonECS", "ecs", "memory:arm64", "GB-hour", "Fargate-ARM-GB-Hours", note="Fargate Linux/ARM"),
        S("AmazonEFS", "efs", "storage", "GB-month", "TimedStorage-ByteHrs", family="Storage",
          attrs={"storageClass": "General Purpose"}, note="Standard (General Purpose)"),
        S("AmazonRoute53", "route53", "queries", "request", "DNS-Queries", 1_000_000, note="standard queries"),
        S("AmazonSES", "ses", "emails", "email", "Recipients", 1000, family="Sending Email",
          note="outbound email, per recipient"),
        S("AmazonVPC", "vpc.ipv4", "address", "instance-hour", "PublicIPv4:InUseAddress",
          note="an in-use public IPv4 address (an EIP, a NAT gateway's, a load balancer's, a task's)"),
        S("AmazonCloudWatch", "cloudwatch", "alarm", "month", "CW:AlarmMonitorUsage", family="Alarm",
          free={"amount": 10, "period": "month"},
          note="standard-resolution metric alarm; free: the offer's Global-CW:AlarmMonitorUsage row"),
        S("AmazonCloudWatch", "cloudwatch", "metric", "month", "CW:MetricMonitorUsage", family="Metric",
          free={"amount": 10, "period": "month"},
          note="custom metrics (Container Insights' among them); free: the offer's Global-CW:MetricMonitorUsage row"),
        S("awswaf", "waf", "requests", "request", "RequestV2-Tier1", 1_000_000, note="WAFv2, up to 1,500 WCU"),
        S("awswaf", "waf", "acl", "month", "WebACLV2", note="WAFv2 web ACL"),
        S("awswaf", "waf", "rule", "month", "RuleV2", note="WAFv2 rule (a managed rule group counts as one)"),
        S("AWSEvents", "scheduler", "requests", "request", "ScheduledInvocation", 1_000_000,
          note="EventBridge Scheduler invocations; the first 14 million a month are the offer's free step"),
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


# ---------------------------------------------------------------- EC2 (plan L-B2): its offer is too big for JSON
# The EC2 offer of one region is 289 MB as CSV (446 MB as JSON; ap-northeast-1, 2026-10-15), so it is read a line at a
# time and only the on-demand price of a shared, Linux, no-software, used instance is kept, one row per type (the
# sku the rules ask for is the type, unit instance-hour). The file's first five lines are its version and its
# publication date; the sixth is the header.
EC2_CSV_URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/{region}/index.csv"
EC2_KEEP = {"TermType": "OnDemand", "Tenancy": "Shared", "Operating System": "Linux", "Pre Installed S/W": "NA",
            "CapacityStatus": "Used", "Product Family": "Compute Instance", "Unit": "Hrs", "Currency": "USD"}


#: Rows the EC2 offer holds besides instances (ticket 2026-10-21-infra-bundled-prices-missing-common-aws-rows): the usage
#: type (after the region's prefix) -> (service, sku, unit, note). gp3 is both an EBS volume's and an EC2 instance's
#: storage (the instance's root volume).
EC2_OTHER = {
    "NatGateway-Hours": [("vpc.nat", "hour", "instance-hour", "NAT gateway, each hour it runs")],
    "NatGateway-Bytes": [("vpc.nat", "processed", "GB", "NAT gateway, data processed")],
    "EBS:VolumeUsage.gp3": [("ebs", "storage", "GB-month", "gp3"), ("ec2", "storage", "GB-month", "gp3 (the root volume)")],
}


def rows_from_ec2_csv(lines, region: str, url: str) -> tuple[list[dict], list[str]]:
    """(price rows, why lines were not used) from the EC2 offer's CSV, given as an iterable of text lines (a stream:
    nothing but the kept rows is held): each shared Linux instance type, and the NAT gateway's and gp3's rows."""
    import csv
    reader = csv.reader(lines)
    effective, header = "", None
    for row in reader:
        if len(row) >= 2 and row[0] == "Publication Date":
            effective = row[1][:10]
        if row and row[0] == "SKU":
            header = {h: i for i, h in enumerate(row)}
            break
    if header is None or any(k not in header for k in (*EC2_KEEP, "Instance Type", "PricePerUnit", "usageType")):
        return [], ["the EC2 offer's header is not the one read (SKU … Instance Type, PricePerUnit, usageType)"]
    prefix = PREFIX.get(region, [""])
    out: dict[str, dict] = {}
    other: dict[tuple, dict] = {}
    others = {p + k: v for p in prefix for k, v in EC2_OTHER.items()}
    for row in reader:
        if len(row) < len(header):
            continue
        usage = row[header["usageType"]]
        if usage in others and row[header["TermType"]] == "OnDemand" and row[header["Currency"]] == "USD":
            try:
                price = float(row[header["PricePerUnit"]])
            except ValueError:
                continue
            for svc, sku, unit, note in others[usage]:
                other.setdefault((svc, sku), {"provider": "aws", "service": svc, "sku": sku, "region": region,
                                              "unit": unit, "price_usd": _round(price), "effective": effective,
                                              "source": url, "note": note})
            continue
        if any(row[header[k]] != v for k, v in EC2_KEEP.items()):
            continue
        typ, usage = row[header["Instance Type"]], row[header["usageType"]]
        # the usage type decides (BoxUsage is a shared instance; DedicatedUsage and HostUsage are not): Tenancy above
        # is a second guard with the same answer
        if not any(usage == f"{p}BoxUsage:{typ}" for p in prefix) or typ in out:
            continue
        try:
            price = float(row[header["PricePerUnit"]])
        except ValueError:
            continue
        out[typ] = {"provider": "aws", "service": "ec2", "sku": typ, "region": region, "unit": "instance-hour",
                    "price_usd": _round(price), "effective": effective, "source": url, "note": "Linux, shared, on-demand"}
    missing = [] if out else ["no on-demand Linux shared instance in the offer"]
    missing += [f"{svc} {sku} ({u})" for u, rows in EC2_OTHER.items() for svc, sku, *_ in rows if (svc, sku) not in other]
    return [out[k] for k in sorted(out)] + [other[k] for k in sorted(other)], missing
