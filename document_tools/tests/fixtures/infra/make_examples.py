"""Writes the infra model v0 examples (the boundary's fixtures): `python make_examples.py` from this folder.

Each folder under here is a room's root: <room>/docs/infra/*.json (or the folder its jui.config.json's infra.dir
names). test_infra_model.py checks the files here equal what this script writes, and what validate says of each.
The large one is generated (seeded, so the same every time): about 2,000 nodes and 5,000 edges over four providers,
for (B) to time the drawing with.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = "https://jsonui.dev/schemas/infra-model/v0.json"


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def aws_three_tier() -> dict[str, object]:
    """One provider, two environments to switch between, two files, folded IAM and alarm, an external SaaS."""
    main = {
        "$schema": SCHEMA, "version": 0, "description": "A web API on AWS: load balancer, containers, MySQL, a bucket",
        "environments": [{"id": "production", "label": "本番", "kind": "production"},
                         {"id": "staging", "label": "ステージング", "kind": "staging"}],
        "groups": [
            {"id": "aws-prod", "kind": "account", "provider": "aws", "label": "本番アカウント", "environments": ["production"]},
            {"id": "aws-stg", "kind": "account", "provider": "aws", "label": "ステージングアカウント", "environments": ["staging"]},
            {"id": "apne1-prod", "kind": "region", "region": "ap-northeast-1", "parent": "aws-prod", "environments": ["production"]},
            {"id": "apne1-stg", "kind": "region", "region": "ap-northeast-1", "parent": "aws-stg", "environments": ["staging"]},
            {"id": "vpc-prod", "kind": "network", "parent": "apne1-prod", "label": "VPC (2 AZ)", "environments": ["production"]},
            {"id": "vpc-stg", "kind": "network", "parent": "apne1-stg", "label": "VPC (1 AZ)", "environments": ["staging"]},
            {"id": "private-prod", "kind": "subnet", "parent": "vpc-prod", "visibility": "private", "environments": ["production"]},
            {"id": "private-stg", "kind": "subnet", "parent": "vpc-stg", "visibility": "private", "environments": ["staging"]},
        ],
        "nodes": [
            {"id": "cdn", "category": "edge.cdn", "service": "cloudfront", "provider": "aws", "label": "CloudFront"},
            {"id": "alb-prod", "category": "load_balancer", "service": "elb.alb", "group": "vpc-prod", "environments": ["production"]},
            {"id": "alb-stg", "category": "load_balancer", "service": "elb.alb", "group": "vpc-stg", "environments": ["staging"]},
            {"id": "api-prod", "category": "compute.container", "service": "ecs.fargate", "group": "private-prod", "count": 3,
             "app": "backend", "iac": ["module.api.aws_ecs_service.this"], "environments": ["production"]},
            {"id": "api-stg", "category": "compute.container", "service": "ecs.fargate", "group": "private-stg",
             "app": "backend", "environments": ["staging"]},
            {"id": "db-prod", "category": "database.relational", "service": "rds.mysql", "group": "private-prod",
             "engine": "mysql 8.4", "ha": "multi-az", "data_doc": "docs/db", "environments": ["production"]},
            {"id": "db-stg", "category": "database.relational", "service": "rds.mysql", "group": "private-stg",
             "engine": "mysql 8.4", "data_doc": "docs/db", "environments": ["staging"]},
            {"id": "assets", "category": "storage.object", "service": "s3", "provider": "aws", "label": "アセットのバケツ"},
            {"id": "api-role", "category": "security.iam", "service": "iam.role", "provider": "aws", "label": "API の実行ロール"},
            {"id": "api-5xx", "category": "monitoring.alarm", "service": "cloudwatch.alarm", "provider": "aws",
             "label": "API の 5xx", "environments": ["production"]},
        ],
        "edges": [
            {"from": "cdn", "to": "alb-prod", "protocol": "https", "port": 443, "environments": ["production"]},
            {"from": "cdn", "to": "alb-stg", "protocol": "https", "port": 443, "environments": ["staging"]},
            {"from": "alb-prod", "to": "api-prod", "protocol": "http", "port": 8000},
            {"from": "alb-stg", "to": "api-stg", "protocol": "http", "port": 8000},
            {"from": "api-prod", "to": "db-prod", "protocol": "mysql", "port": 3306},
            {"from": "api-stg", "to": "db-stg", "protocol": "mysql", "port": 3306},
            {"from": "cdn", "to": "assets", "protocol": "https"},
        ],
    }
    external = {
        "$schema": SCHEMA, "version": 0, "description": "What the API talks to outside AWS",
        "nodes": [
            {"id": "stripe", "category": "external.saas", "provider": "stripe", "label": "Stripe", "managed_by": "external",
             "evidence": [{"file": "backend/app/config.py", "pattern": "stripe_"}]},
            {"id": "mailer", "category": "mail", "provider": "sendgrid", "label": "メール配信", "managed_by": "external"},
        ],
        "edges": [
            {"from": "api-prod", "to": "stripe", "protocol": "https", "direction": "out", "environments": ["production"]},
            {"from": "api-prod", "to": "mailer", "protocol": "https", "direction": "out", "environments": ["production"]},
            {"from": "api-stg", "to": "stripe", "protocol": "https", "label": "テストモード", "environments": ["staging"]},
        ],
    }
    return {"aws-three-tier/docs/infra/main.json": main, "aws-three-tier/docs/infra/external.json": external}


def multi_provider() -> dict[str, object]:
    """Across providers: a logical group holding provider groups, edges between providers, preview and production."""
    m = {
        "$schema": SCHEMA, "version": 0, "description": "Front on Vercel, API on Cloudflare Workers, data on Cloudflare and GCP, backups on AWS",
        "environments": [{"id": "production", "kind": "production"}, {"id": "preview", "kind": "preview"}],
        "groups": [
            {"id": "shop", "kind": "logical", "label": "ショップ（製品の全体）"},
            {"id": "vercel", "kind": "project", "provider": "vercel", "parent": "shop", "label": "Vercel のプロジェクト"},
            {"id": "cf", "kind": "account", "provider": "cloudflare", "parent": "shop", "label": "Cloudflare のアカウント"},
            {"id": "gcp", "kind": "project", "provider": "gcp", "parent": "shop", "label": "GCP のプロジェクト"},
            {"id": "gcp-tokyo", "kind": "region", "region": "asia-northeast1", "parent": "gcp"},
            {"id": "aws", "kind": "account", "provider": "aws", "label": "バックアップ用の AWS"},
        ],
        "nodes": [
            {"id": "browser", "category": "client", "label": "ブラウザ"},
            {"id": "dns", "category": "edge.dns", "service": "dns", "group": "cf"},
            {"id": "web", "category": "compute.paas", "service": "nextjs", "group": "vercel", "app": "web"},
            {"id": "api", "category": "compute.function", "service": "workers", "group": "cf", "app": "api",
             "iac": ["wrangler.toml"]},
            {"id": "kv", "category": "database.kv", "service": "kv", "group": "cf"},
            {"id": "d1", "category": "database.relational", "service": "d1", "group": "cf", "data_doc": "docs/db"},
            {"id": "r2", "category": "storage.object", "service": "r2", "group": "cf"},
            {"id": "search", "category": "database.search", "service": "vertex-ai-search", "group": "gcp-tokyo",
             "environments": ["production"]},
            {"id": "queue", "category": "queue", "service": "pubsub", "group": "gcp-tokyo"},
            {"id": "backup", "category": "storage.object", "service": "s3", "group": "aws", "label": "R2 の写し"},
            {"id": "auth0", "category": "auth", "provider": "auth0", "label": "Auth0", "managed_by": "external"},
        ],
        "edges": [
            {"from": "browser", "to": "dns", "protocol": "dns"},
            {"from": "browser", "to": "web", "protocol": "https"},
            {"from": "web", "to": "api", "protocol": "https"},
            {"from": "web", "to": "auth0", "protocol": "https"},
            {"from": "api", "to": "kv", "protocol": "binding"},
            {"from": "api", "to": "d1", "protocol": "binding"},
            {"from": "api", "to": "r2", "protocol": "binding"},
            {"from": "api", "to": "search", "protocol": "https", "environments": ["production"]},
            {"from": "api", "to": "queue", "protocol": "https"},
            {"from": "r2", "to": "backup", "protocol": "s3", "label": "毎晩の写し", "environments": ["production"]},
        ],
    }
    return {"multi-provider/docs/infra/system.json": m}


def compose_and_cloud() -> dict[str, object]:
    """The folder from jui.config.json (infra.dir), and a local environment (Compose) to switch to beside production."""
    m = {
        "$schema": SCHEMA, "version": 0, "description": "docker compose on the desk, Cloud Run in production",
        "environments": [{"id": "local", "label": "手元（docker compose）", "kind": "local"},
                         {"id": "production", "label": "本番", "kind": "production"}],
        "groups": [
            {"id": "compose", "kind": "host", "provider": "docker", "label": "compose.yaml", "environments": ["local"]},
            {"id": "gcp", "kind": "project", "provider": "gcp", "environments": ["production"]},
            {"id": "tokyo", "kind": "region", "region": "asia-northeast1", "parent": "gcp", "environments": ["production"]},
        ],
        "nodes": [
            {"id": "app-local", "category": "compute.container", "service": "compose.service", "group": "compose",
             "app": "backend", "iac": ["compose.yaml#services.app"], "environments": ["local"]},
            {"id": "db-local", "category": "database.relational", "service": "postgres", "group": "compose",
             "engine": "postgres 17", "iac": ["compose.yaml#services.db"], "environments": ["local"]},
            {"id": "cache-local", "category": "cache", "service": "redis", "group": "compose", "environments": ["local"]},
            {"id": "app", "category": "compute.container", "service": "run", "group": "tokyo", "app": "backend",
             "count": 2, "environments": ["production"]},
            {"id": "db", "category": "database.relational", "service": "cloudsql.postgres", "group": "tokyo",
             "engine": "postgres 17", "ha": "regional", "environments": ["production"]},
            {"id": "cache", "category": "cache", "service": "memorystore.redis", "group": "tokyo", "environments": ["production"]},
            {"id": "secrets", "category": "secrets", "service": "secret-manager", "group": "gcp", "environments": ["production"]},
        ],
        "edges": [
            {"from": "app-local", "to": "db-local", "protocol": "postgres", "port": 5432},
            {"from": "app-local", "to": "cache-local", "protocol": "redis", "port": 6379},
            {"from": "app", "to": "db", "protocol": "postgres", "port": 5432},
            {"from": "app", "to": "cache", "protocol": "redis", "port": 6379},
            {"from": "app", "to": "secrets", "protocol": "https"},
        ],
    }
    config = {"infra": {"dir": "infra/model", "icons": {"service:gcp/run": "infra/icons/run.svg", "category:cache": "infra/icons/cache.svg"}}}
    icon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="3" fill="#888"/></svg>\n'
    return {"compose-and-cloud/infra/model/stack.json": m, "compose-and-cloud/jui.config.json": config,
            "compose-and-cloud/infra/icons/run.svg": icon, "compose-and-cloud/infra/icons/cache.svg": icon}


def large(nodes_target: int = 2000, edges_target: int = 5000) -> dict[str, object]:
    """About 2,000 nodes and 5,000 edges over aws, gcp, azure and cloudflare (seeded): for timing the drawing."""
    rnd = random.Random(20261020)
    providers = {"aws": ["ecs.fargate", "lambda", "rds.postgres", "dynamodb", "s3", "sqs", "elasticache.redis"],
                 "gcp": ["run", "functions", "cloudsql.postgres", "firestore", "gcs", "pubsub", "memorystore.redis"],
                 "azure": ["containerapps", "functions", "sql", "cosmosdb", "blob", "servicebus", "cache.redis"],
                 "cloudflare": ["workers", "workers", "d1", "kv", "r2", "queues", "kv"]}
    cats = ["compute.container", "compute.function", "database.relational", "database.document", "storage.object", "queue", "cache"]
    groups = [{"id": "platform", "kind": "logical", "label": "全体"}]
    nodes, by_provider = [], {p: [] for p in providers}
    regions = {"aws": ["ap-northeast-1", "us-east-1"], "gcp": ["asia-northeast1", "us-central1"],
               "azure": ["japaneast", "eastus"], "cloudflare": ["global"]}
    subnets = []
    for p in providers:
        groups.append({"id": f"{p}", "kind": "account", "provider": p, "parent": "platform"})
        for r in regions[p]:
            gid = f"{p}-{r}"
            groups.append({"id": gid, "kind": "region", "region": r, "parent": p})
            for k in range(6):
                sid = f"{gid}-net{k}"
                groups.append({"id": sid, "kind": "network", "parent": gid, "label": f"{r} net {k}"})
                subnets.append((p, sid))
    for i in range(nodes_target):
        p, sid = subnets[i % len(subnets)]
        k = rnd.randrange(len(cats))
        n = {"id": f"n{i:04d}", "category": cats[k], "service": providers[p][k], "group": sid}
        if k == 0 and rnd.random() < 0.3:
            n["count"] = rnd.randint(2, 6)
        if i % 97 == 0:
            n["environments"] = ["production"]
        nodes.append(n)
        by_provider[p].append(n["id"])
    ids = [n["id"] for n in nodes]
    edges, seen = [], set()
    while len(edges) < edges_target:
        a = rnd.choice(ids)
        same = rnd.random() < 0.85
        pa = next(p for p, l in by_provider.items() if a in l) if same else None
        b = rnd.choice(by_provider[pa]) if same else rnd.choice(ids)
        if a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        edges.append({"from": a, "to": b, "protocol": rnd.choice(["https", "grpc", "postgres", "redis", "binding"])})
    m = {"$schema": SCHEMA, "version": 0, "description": f"Generated by make_examples.py: {len(nodes)} nodes, {len(edges)} edges, four providers",
         "environments": [{"id": "production", "kind": "production"}, {"id": "staging", "kind": "staging"}],
         "groups": groups, "nodes": nodes, "edges": edges}
    return {"large-multi-provider/docs/infra/generated.json": m}


def invalid() -> dict[str, object]:
    """One problem per file, named by the file: what validate must refuse (and the display must leave out)."""
    ok_node = {"id": "api", "category": "compute.container"}
    base = lambda **kw: {"version": 0, **kw}  # noqa: E731
    files = {
        "secret-arn.json": base(nodes=[dict(ok_node, label="arn:aws:iam::123456789012:role/x")]),
        "secret-account-id.json": base(groups=[{"id": "acct", "kind": "account", "label": "account 123456789012"}]),
        "secret-ip.json": base(nodes=[dict(ok_node, label="10.0.1.25 の API")]),
        "secret-connection-string.json": base(nodes=[dict(ok_node, engine="postgres://db.internal/app")]),
        "secret-url-credentials.json": base(nodes=[dict(ok_node, label="https://user:pass@example.com")]),
        "secret-private-key.json": base(nodes=[dict(ok_node, label="-----BEGIN RSA PRIVATE KEY-----")]),
        "secret-access-key.json": base(nodes=[dict(ok_node, label="AKIAABCDEFGHIJKLMNOP")]),
        "secret-token.json": base(nodes=[dict(ok_node, label="sk_live_abcdefghijklmnop")]),
        "schema-unknown-field.json": base(nodes=[dict(ok_node, password="x")]),
        "schema-category.json": base(nodes=[{"id": "x", "category": "computer"}]),
        "schema-version.json": {"version": 1},
        "not-json.json": "{ broken",
    }
    out = {f"invalid/single/{k}": v for k, v in files.items()}
    # across files: each folder is one room whose files pass alone and fail together (or by reference)
    out["invalid/refs/docs/infra/a.json"] = base(
        environments=[{"id": "production", "kind": "production"}],
        groups=[{"id": "g1", "kind": "region", "parent": "g2"}, {"id": "g2", "kind": "region", "parent": "g1"}],
        nodes=[dict(ok_node, group="nowhere"), {"id": "db", "category": "database.relational", "environments": ["qa"]}],
        edges=[{"from": "api", "to": "ghost"}])
    out["invalid/refs/docs/infra/b.json"] = base(
        environments=[{"id": "production", "kind": "staging"}],
        nodes=[{"id": "api", "category": "cache"}])
    return out


def all_examples() -> dict[str, object]:
    out = {}
    for make in (aws_three_tier, multi_provider, compose_and_cloud, large, invalid):
        out.update(make())
    return out


def main() -> int:
    for rel, data in all_examples().items():
        path = HERE / rel
        if isinstance(data, str):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding="utf-8")
        else:
            dump(path, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
