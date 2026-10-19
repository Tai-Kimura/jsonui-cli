"""check kind=infra: the room's declared infrastructure (docs/infra, boundary §6) against what the project's own files say.

builtin:infra-iac — the IaC and deploy settings in the project (Docker Compose, Terraform / OpenTofu HCL, CloudFormation
/ SAM, Kubernetes manifests, Cloudflare wrangler), read statically: no credentials, no plan, no state (state holds
secrets in the clear). Each resource is mapped to a category and a provider by the tables below (fine-grained types —
IAM, policies, alarms, rules, attachments — are dropped by IGNORED, InfraMap's way); each provider's resources are
compared with that provider's declared nodes (providerResolved) through their ``iac`` addresses.

builtin:infra-code — the code: every node's ``evidence`` (the file is there, the pattern still in it), and the services
the code talks to by its SDK imports and the *names* of its environment variables (never their values), against the
declared nodes.

Both say what they could not check, per provider (report.target_extra["unverified"] and a warnings line each): no IaC
found for a provider that has declared nodes, a module from a source outside the project, count / for_each not
evaluated, a file that could not be parsed, a resource type with no mapping, a scan cap reached. "0 mismatches" covers
only what was read.

Findings are warnings unless the check declares "gate": true (jui.config.json checks[]): drift in a hand-kept model is
reported, it gates CI only when the project asks.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath

from ..infra import model as M
from ..infra import room as R
from .report import CheckReport, ResultItem, compute_input_hashes

SKIP_DIRS = {".git", "node_modules", "vendor", "build", "dist", ".terraform", ".venv", "venv", "__pycache__", "Pods",
             ".next", ".wrangler", "target", ".gradle", "DerivedData", "cdk.out"}
MAX_FILES = 5000
MAX_BYTES = 1_000_000


class InfraCheckError(Exception):
    pass


# ---------------------------------------------------------------- walking the project

def _walk(root: Path, accept) -> tuple[list[Path], bool]:
    """Files under root (no symlink followed, SKIP_DIRS and hidden folders left out) that accept(name) takes, at most
    MAX_FILES; the bool says whether the cap was reached."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if accept(name) and p.is_file() and not p.is_symlink():
                out.append(p)
                if len(out) >= MAX_FILES:
                    return out, True
    return out, False


def _text(p: Path) -> str | None:
    try:
        if p.stat().st_size > MAX_BYTES:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _rel(p: Path, root: Path) -> str:
    return PurePosixPath(p.relative_to(root)).as_posix()


# ---------------------------------------------------------------- the IaC tables

TF_PROVIDER = {"aws": "aws", "google": "gcp", "azurerm": "azure", "cloudflare": "cloudflare", "kubernetes": "kubernetes",
               "vercel": "vercel", "digitalocean": "digitalocean", "fly": "fly", "heroku": "heroku", "netlify": "netlify",
               "supabase": "supabase"}
TF_CATEGORY = {
    "aws_instance": "compute.vm", "aws_ecs_service": "compute.container", "aws_apprunner_service": "compute.container",
    "aws_lambda_function": "compute.function", "aws_eks_cluster": "compute.k8s",
    "aws_lb": "load_balancer", "aws_alb": "load_balancer", "aws_elb": "load_balancer",
    "aws_cloudfront_distribution": "edge.cdn", "aws_route53_zone": "edge.dns", "aws_wafv2_web_acl": "edge.waf",
    "aws_api_gateway_rest_api": "gateway.api", "aws_apigatewayv2_api": "gateway.api",
    "aws_db_instance": "database.relational", "aws_rds_cluster": "database.relational",
    "aws_dynamodb_table": "database.kv", "aws_docdb_cluster": "database.document",
    "aws_opensearch_domain": "database.search", "aws_elasticache_cluster": "cache",
    "aws_elasticache_replication_group": "cache", "aws_s3_bucket": "storage.object", "aws_efs_file_system": "storage.file",
    "aws_ebs_volume": "storage.block", "aws_sqs_queue": "queue", "aws_sns_topic": "queue", "aws_kinesis_stream": "stream",
    "aws_cloudwatch_event_rule": "scheduler", "aws_scheduler_schedule": "scheduler", "aws_ses_domain_identity": "mail",
    "aws_cognito_user_pool": "auth", "aws_secretsmanager_secret": "secrets", "aws_vpc": None, "aws_subnet": None,
    "google_compute_instance": "compute.vm", "google_cloud_run_service": "compute.container",
    "google_cloud_run_v2_service": "compute.container", "google_cloudfunctions_function": "compute.function",
    "google_cloudfunctions2_function": "compute.function", "google_container_cluster": "compute.k8s",
    "google_app_engine_application": "compute.paas", "google_compute_global_forwarding_rule": "load_balancer",
    "google_dns_managed_zone": "edge.dns", "google_sql_database_instance": "database.relational",
    "google_spanner_instance": "database.relational", "google_firestore_database": "database.document",
    "google_redis_instance": "cache", "google_storage_bucket": "storage.object", "google_pubsub_topic": "queue",
    "google_cloud_scheduler_job": "scheduler", "google_secret_manager_secret": "secrets", "google_compute_network": None,
    "azurerm_linux_virtual_machine": "compute.vm", "azurerm_windows_virtual_machine": "compute.vm",
    "azurerm_container_app": "compute.container", "azurerm_linux_function_app": "compute.function",
    "azurerm_kubernetes_cluster": "compute.k8s", "azurerm_linux_web_app": "compute.paas",
    "azurerm_application_gateway": "load_balancer", "azurerm_lb": "load_balancer", "azurerm_cdn_frontdoor_profile": "edge.cdn",
    "azurerm_dns_zone": "edge.dns", "azurerm_mssql_server": "database.relational",
    "azurerm_postgresql_flexible_server": "database.relational", "azurerm_cosmosdb_account": "database.document",
    "azurerm_redis_cache": "cache", "azurerm_storage_account": "storage.object", "azurerm_servicebus_namespace": "queue",
    "azurerm_key_vault": "secrets", "azurerm_virtual_network": None,
    "cloudflare_zone": "edge.dns", "cloudflare_worker_script": "compute.function", "cloudflare_workers_script": "compute.function",
    "cloudflare_pages_project": "compute.paas", "cloudflare_workers_kv_namespace": "database.kv",
    "cloudflare_r2_bucket": "storage.object", "cloudflare_d1_database": "database.relational", "cloudflare_queue": "queue",
}
# fine-grained: never a node of their own (folded like InfraMap does), whatever the provider
IGNORED = re.compile(r"(?:^|_)(?:iam|policy|policies|role|roles|alarm|alarms|metric|log_group|rule|rules|attachment"
                     r"|association|permission|security_group|route|routes|record|records|binding|bindings|member"
                     r"|version|key_pair|subnet|vpc|network|eip|nat_gateway|internet_gateway|acl|listener|target_group"
                     r"|task_definition|launch_template|parameter|lifecycle|notification|cors|website|object|alias"
                     r"|certificate|access_key|user|group|account_iam|service_account)(?:_|$)")
CFN_CATEGORY = {"AWS::EC2::Instance": "compute.vm", "AWS::ECS::Service": "compute.container",
                "AWS::Lambda::Function": "compute.function", "AWS::Serverless::Function": "compute.function",
                "AWS::EKS::Cluster": "compute.k8s", "AWS::ElasticLoadBalancingV2::LoadBalancer": "load_balancer",
                "AWS::CloudFront::Distribution": "edge.cdn", "AWS::Route53::HostedZone": "edge.dns",
                "AWS::ApiGateway::RestApi": "gateway.api", "AWS::Serverless::Api": "gateway.api",
                "AWS::Serverless::HttpApi": "gateway.api", "AWS::RDS::DBInstance": "database.relational",
                "AWS::RDS::DBCluster": "database.relational", "AWS::DynamoDB::Table": "database.kv",
                "AWS::Serverless::SimpleTable": "database.kv", "AWS::ElastiCache::CacheCluster": "cache",
                "AWS::S3::Bucket": "storage.object", "AWS::SQS::Queue": "queue", "AWS::SNS::Topic": "queue",
                "AWS::Kinesis::Stream": "stream", "AWS::Events::Rule": "scheduler", "AWS::Cognito::UserPool": "auth",
                "AWS::SecretsManager::Secret": "secrets"}
K8S_CATEGORY = {"Deployment": "compute.k8s", "StatefulSet": "compute.k8s", "DaemonSet": "compute.k8s",
                "CronJob": "scheduler", "Job": "compute.k8s", "Ingress": "load_balancer",
                "PersistentVolumeClaim": "storage.block"}
COMPOSE_IMAGE = (("postgres", "database.relational"), ("mysql", "database.relational"), ("mariadb", "database.relational"),
                 ("mongo", "database.document"), ("redis", "cache"), ("valkey", "cache"), ("memcached", "cache"),
                 ("rabbitmq", "queue"), ("kafka", "stream"), ("elasticsearch", "database.search"),
                 ("opensearch", "database.search"), ("minio", "storage.object"), ("nginx", "load_balancer"),
                 ("traefik", "load_balancer"), ("mailhog", "mail"), ("mailpit", "mail"))
COMPOSE_NAMES = re.compile(r"^(?:docker-)?compose(?:\.[\w-]+)?\.ya?ml$")
WRANGLER = re.compile(r"^wrangler\.(?:toml|json|jsonc)$")


def _yaml():
    try:
        import yaml
    except ImportError:
        return None

    class Loader(yaml.SafeLoader):
        pass

    def _any(loader, suffix, node):          # CloudFormation's short forms (!Ref, !GetAtt, ...): not evaluated
        return None
    Loader.add_multi_constructor("!", _any)
    return yaml, Loader


def scan_iac(root: Path) -> tuple[list[dict], dict[str, list[str]]]:
    """Resources the project's IaC declares: {address, provider, category, source}, and what could not be read, per
    provider ("*" when the provider cannot be told)."""
    found: list[dict] = []
    unverified: dict[str, list[str]] = {}

    def note(provider: str, why: str) -> None:
        unverified.setdefault(provider, [])
        if why not in unverified[provider]:
            unverified[provider].append(why)

    names = lambda n: n.endswith((".tf", ".yaml", ".yml", ".json", ".toml", ".jsonc"))  # noqa: E731
    files, capped = _walk(root, names)
    if capped:
        note("*", f"more than {MAX_FILES} candidate files: the rest were not read")
    y = _yaml()
    unmapped: dict[str, set[str]] = {}
    for p in files:
        rel, name = _rel(p, root), p.name
        if rel.startswith(R.DEFAULT_DIR + "/") or name.endswith(".check-report.json") or "/.check-report" in rel:
            continue
        text = _text(p)
        if text is None:
            continue
        if name.endswith(".tf"):
            for t, n in re.findall(r'^\s*resource\s+"([a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"', text, re.M):
                prefix = t.split("_", 1)[0]
                provider = TF_PROVIDER.get(prefix, prefix)
                cat = TF_CATEGORY.get(t, "?")
                if cat is None or (cat == "?" and IGNORED.search(t)):
                    continue
                if cat == "?":
                    unmapped.setdefault(provider, set()).add(t)
                    continue
                found.append({"address": f"{t}.{n}", "provider": provider, "category": cat, "source": rel})
            for mname, body in re.findall(r'^\s*module\s+"([A-Za-z0-9_-]+)"\s*\{(.*?)^\}', text, re.M | re.S):
                src = re.search(r'^\s*source\s*=\s*"([^"]+)"', body, re.M)
                if src and not src.group(1).startswith(("./", "../")):
                    note("*", f"{rel}: module \"{mname}\" comes from outside the project: its resources were not read")
            if re.search(r"^\s*(?:count|for_each)\s*=", text, re.M):
                note("*", f"{rel}: count / for_each are not evaluated (a static read; no plan): how many is not checked")
        elif COMPOSE_NAMES.match(name) or WRANGLER.match(name):
            if WRANGLER.match(name):
                _wrangler(p, rel, text, found, note)
            elif y is None:
                note("docker", f"{rel}: PyYAML is not installed: not read")
            else:
                try:
                    data = y[0].load(text, Loader=y[1])
                except Exception:   # noqa: BLE001 — a file that does not parse is said, not fatal
                    note("docker", f"{rel}: not YAML: not read")
                    continue
                for svc, spec in ((data or {}).get("services") or {}).items():
                    image = str((spec or {}).get("image") or "") if isinstance(spec, dict) else ""
                    cat = next((c for key, c in COMPOSE_IMAGE if key in image.lower()), "compute.container")
                    found.append({"address": f"{rel}#services.{svc}", "provider": "docker", "category": cat, "source": rel})
        elif name.endswith((".yaml", ".yml", ".json")):
            if "AWSTemplateFormatVersion" in text or "AWS::" in text:
                _cfn(p, rel, text, y, found, note)
            elif re.search(r"^apiVersion:", text, re.M) and re.search(r"^kind:", text, re.M):
                _k8s(rel, text, y, found, note)
    for provider, types in unmapped.items():
        note(provider, f"{len(types)} resource type(s) with no mapping to a category, not compared: "
                       + ", ".join(sorted(types)[:8]) + (" …" if len(types) > 8 else ""))
    return found, unverified


def _cfn(p, rel, text, y, found, note):
    if y is None and not p.name.endswith(".json"):
        note("aws", f"{rel}: PyYAML is not installed: not read")
        return
    try:
        data = json.loads(text) if p.name.endswith(".json") else y[0].load(text, Loader=y[1])
    except Exception:   # noqa: BLE001
        note("aws", f"{rel}: not parsed: not read")
        return
    for logical, res in ((data or {}).get("Resources") or {}).items() if isinstance(data, dict) else []:
        t = (res or {}).get("Type") if isinstance(res, dict) else None
        if not isinstance(t, str):
            continue
        cat = CFN_CATEGORY.get(t)
        if cat:
            found.append({"address": logical, "provider": "aws", "category": cat, "source": rel})
        elif not IGNORED.search(t.replace("::", "_").lower()):
            note("aws", f"{rel}: {t} has no mapping to a category, not compared")


def _k8s(rel, text, y, found, note):
    if y is None:
        note("kubernetes", f"{rel}: PyYAML is not installed: not read")
        return
    try:
        docs = list(y[0].load_all(text, Loader=y[1]))
    except Exception:   # noqa: BLE001
        note("kubernetes", f"{rel}: not YAML: not read")
        return
    for d in docs:
        if not isinstance(d, dict):
            continue
        kind, name = d.get("kind"), (d.get("metadata") or {}).get("name")
        if kind in K8S_CATEGORY and isinstance(name, str):
            found.append({"address": f"{kind}/{name}", "provider": "kubernetes", "category": K8S_CATEGORY[kind], "source": rel})
    if "{{" in text:
        note("kubernetes", f"{rel}: a Helm template is not rendered: not read as it deploys")


def _wrangler(p, rel, text, found, note):
    try:
        if p.name.endswith(".toml"):
            import tomllib
            data = tomllib.loads(text)
        else:
            data = json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))
    except Exception:   # noqa: BLE001
        note("cloudflare", f"{rel}: not parsed: not read")
        return
    found.append({"address": rel, "provider": "cloudflare", "category": "compute.function", "source": rel})
    for key, cat in (("kv_namespaces", "database.kv"), ("r2_buckets", "storage.object"), ("d1_databases", "database.relational")):
        for b in data.get(key) or []:
            if isinstance(b, dict) and isinstance(b.get("binding"), str):
                found.append({"address": f"{rel}#{key}.{b['binding']}", "provider": "cloudflare", "category": cat, "source": rel})


# ---------------------------------------------------------------- code: SDKs and environment names

SDK_HINTS = (  # (regex on an import / require line, provider, category or None)
    (r"\bboto3\b|@aws-sdk/|aws-sdk", "aws", None), (r"google[.-]cloud|@google-cloud/", "gcp", None),
    (r"firebase-admin|firebase/", "firebase", None), (r"@azure/|azure[.-]", "azure", None),
    (r"@supabase/supabase-js|\bsupabase\b", "supabase", None), (r"\bstripe\b", "stripe", "external.saas"),
    (r"\bopenai\b", "openai", "external.saas"), (r"\banthropic\b", "anthropic", "external.saas"),
    (r"@sendgrid/|\bsendgrid\b", "sendgrid", "mail"), (r"\btwilio\b", "twilio", "external.saas"),
    (r"@auth0/|\bauth0\b", "auth0", "auth"), (r"\bsentry[_-]sdk\b|@sentry/", "sentry", "monitoring"),
)
ENV_HINTS = ((r"\bDATABASE_URL\b|\b(?:DB|POSTGRES|MYSQL)_HOST\b", "database.relational"),
             (r"\bREDIS_(?:URL|HOST)\b", "cache"), (r"\b[A-Z_]*S3_BUCKET[A-Z_]*\b|\bGCS_BUCKET\b", "storage.object"),
             (r"\bSMTP_HOST\b", "mail"), (r"\b(?:SQS|PUBSUB)_[A-Z_]*\b", "queue"))
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rb", ".kt", ".java", ".swift", ".dart")
IMPORT_LINE = re.compile(r"^\s*(?:import\b|from\s+\S+\s+import\b|const\s+.*=\s*require\(|require\b|use\b).*$", re.M)


def scan_code(root: Path) -> tuple[list[dict], list[str]]:
    """What the code names: {provider|None, category|None, file, line, why} from import lines and environment
    variable *names*; and what was not scanned."""
    hints: list[dict] = []
    notes: list[str] = []
    files, capped = _walk(root, lambda n: n.endswith(CODE_EXT) or n in (".env.example", "env.example"))
    if capped:
        notes.append(f"more than {MAX_FILES} source files: the rest were not scanned")
    for p in files:
        text = _text(p)
        if text is None:
            continue
        rel = _rel(p, root)
        for m in IMPORT_LINE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            for rx, provider, cat in SDK_HINTS:
                if re.search(rx, m.group(0)):
                    hints.append({"provider": provider, "category": cat, "file": rel, "line": line, "why": "import"})
        for rx, cat in ENV_HINTS:
            for m in re.finditer(rx, text):
                hints.append({"provider": None, "category": cat, "file": rel,
                              "line": text.count("\n", 0, m.start()) + 1, "why": f"environment name {m.group(0)}"})
    return hints, notes


# ---------------------------------------------------------------- the checkers

def _model(project_root: Path) -> tuple[dict, str, list[Path]]:
    got = R.read(project_root)
    if not got.get("ok"):
        raise InfraCheckError(f"the infra model cannot be read ({got['reason']}): {got['message']}")
    errs = M.errors(got["problems"])
    if errs:
        raise InfraCheckError(f"the infra model has {len(errs)} error(s): run `jsonui-doc validate infra` first")
    files = [project_root / got["dir"] / f for f in got["files"]]
    return got, got["dir"], files


def _status(decl, status: str) -> str:
    return status if getattr(decl, "gate", False) or status in ("ok", "skipped") else "warning"


def run_infra_iac(decl, project_root: Path) -> CheckReport:
    model, folder, model_files = _model(project_root)
    found, unverified = scan_iac(project_root)
    ignore = set(getattr(decl, "ignore_types", []) or [])
    found = [f for f in found if f["address"].split(".")[0] not in ignore]
    nodes = [n for n in model["nodes"] if n["managed_by"] == "iac"]
    results: list[ResultItem] = []
    claimed: set[str] = set()
    by_provider: dict[str, list[dict]] = {}
    for f in found:
        by_provider.setdefault(f["provider"], []).append(f)
    declared_providers = {n["providerResolved"] or "?" for n in nodes}
    for provider in sorted(declared_providers - set(by_provider) - {"?"}):
        unverified.setdefault(provider, []).append("no IaC found for this provider in the project: its nodes are not compared")
    for n in nodes:
        provider = n["providerResolved"] or "?"
        target = f"{provider}/{n['id']}"
        if not n.get("iac"):
            results.append(ResultItem(target, "skipped", "metadata", message="no iac address on the node: not compared"))
            continue
        if provider not in by_provider:
            results.append(ResultItem(target, "skipped", "metadata", message=f"no IaC read for {provider}"))
            continue
        hit = [f for f in by_provider[provider] for a in n["iac"] if a == f["address"] or a.endswith("." + f["address"])]
        if hit:
            claimed.update(f["address"] for f in hit)
            cats = {f["category"] for f in hit}
            if n["category"] in cats:
                results.append(ResultItem(target, "ok", "metadata"))
            else:
                results.append(ResultItem(target, _status(decl, "mismatch"), "metadata", expected=n["category"],
                                          actual=", ".join(sorted(cats)), message=f"category differs from {hit[0]['source']}"))
        else:
            results.append(ResultItem(target, _status(decl, "missing_in_impl"), "metadata", expected=", ".join(n["iac"]),
                                      message="declared, but no such resource in this provider's IaC"))
    for f in found:
        if f["address"] not in claimed:
            results.append(ResultItem(f"{f['provider']}/{f['address']}", _status(decl, "missing_in_doc"), "metadata",
                                      actual=f["category"], message=f"in {f['source']}, but no node names it in iac"))
    rep = CheckReport(checker="builtin:infra-iac", target_kind="infra", target_name="infra-iac",
                      target_extra={"dir": folder, "unverified": unverified, "gate": bool(getattr(decl, "gate", False))},
                      input_hashes=compute_input_hashes(model_files, project_root), results=results, unit="resource")
    rep.warnings = [f"[unverified] {p}: {why}" for p, whys in sorted(unverified.items()) for why in whys]
    return rep


def run_infra_code(decl, project_root: Path) -> CheckReport:
    model, folder, model_files = _model(project_root)
    results: list[ResultItem] = []
    for n in model["nodes"]:
        for i, ev in enumerate(n.get("evidence") or []):
            target = f"{n['providerResolved'] or '?'}/{n['id']}#evidence/{i}"
            raw = R.read_capped(project_root, ev["file"], MAX_BYTES)
            if not isinstance(raw, bytes):
                results.append(ResultItem(target, _status(decl, "missing_in_impl"), "proof", expected=ev["file"],
                                          message="the evidence file is not there"))
            elif ev.get("pattern") and ev["pattern"] not in raw.decode("utf-8", errors="replace"):
                results.append(ResultItem(target, _status(decl, "missing_in_impl"), "proof", expected=ev["file"],
                                          message="the evidence pattern is no longer in the file"))
            else:
                results.append(ResultItem(target, "ok", "proof"))
    hints, notes = scan_code(project_root)
    providers = {n["providerResolved"] for n in model["nodes"]} | {n.get("provider") for n in model["nodes"]}
    categories = {n["category"] for n in model["nodes"]}
    seen: set[tuple] = set()
    for h in hints:
        key = (h["provider"], h["category"])
        if key in seen:
            continue
        seen.add(key)
        known = (h["provider"] in providers) if h["provider"] else (h["category"] in categories)
        target = f"code/{h['provider'] or h['category']}"
        if known:
            results.append(ResultItem(target, "ok", "sampled"))
        else:
            results.append(ResultItem(target, _status(decl, "missing_in_doc"), "sampled",
                                      actual=h["provider"] or h["category"],
                                      message=f"{h['file']}:{h['line']} ({h['why']}) — no node for it"))
    rep = CheckReport(checker="builtin:infra-code", target_kind="infra", target_name="infra-code",
                      target_extra={"dir": folder, "unverified": {"*": notes} if notes else {},
                                    "gate": bool(getattr(decl, "gate", False))},
                      input_hashes=compute_input_hashes(model_files, project_root), results=results, unit="reference")
    rep.warnings = [f"[unverified] *: {n}" for n in notes] + [
        "[unverified] *: only import lines and environment variable names are read (not values, not calls): a service "
        "reached another way is not seen"]
    return rep
