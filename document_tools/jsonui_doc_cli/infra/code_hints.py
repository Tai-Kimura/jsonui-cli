"""What a project's code says about the services it talks to — one copy, read by seed (drafting) and check (comparing).

Ticket 2026-10-20-jui-infra-seed-and-check-tables-disagree (the code-hint half, found by the seed lane): seed had
SDK_PY / SDK_JS / ENV_RULES and check its own SDK_HINTS / ENV_HINTS. The tables below are seed's, moved here;
``scan_text`` reads one file the way seed read it, without a draft: the SDK imports (Python and JavaScript /
TypeScript), the AWS SDK clients, and the *names* of the environment variables the code reads (never a value).
Other languages are not read (the caller says so).
"""
from __future__ import annotations

import os
import re

CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".tsx", ".jsx"}
ENV_NAME_FILES = re.compile(r"^(\.env\.(example|sample|template|dist|defaults)|example\.env|env\.example|sample\.env)$")

# Code: SDK imports (Python module prefixes and JavaScript packages) -> (provider, category, service).
# provider "" = not clear from the import (a driver that talks to any host).
SDK_PY: list[tuple[str, tuple[str, str, str]]] = [
    ("stripe", ("stripe", "external.saas", "payments")), ("openai", ("openai", "external.saas", "api")),
    ("anthropic", ("anthropic", "external.saas", "api")), ("sendgrid", ("sendgrid", "mail", "email")),
    ("mailgun", ("mailgun", "mail", "email")), ("postmarker", ("postmark", "mail", "email")),
    ("resend", ("resend", "mail", "email")), ("twilio", ("twilio", "external.saas", "messaging")),
    ("sentry_sdk", ("sentry", "monitoring", "errors")), ("ddtrace", ("datadog", "monitoring", "apm")),
    ("datadog", ("datadog", "monitoring", "apm")), ("auth0", ("auth0", "auth", "identity")),
    ("algoliasearch", ("algolia", "database.search", "search")), ("supabase", ("supabase", "database.relational", "postgres")),
    ("slack_sdk", ("slack", "external.saas", "messaging")), ("pusher", ("pusher", "external.saas", "realtime")),
    ("google.cloud.storage", ("gcp", "storage.object", "gcs")), ("google.cloud.pubsub", ("gcp", "queue", "pubsub")),
    ("google.cloud.firestore", ("gcp", "database.document", "firestore")),
    ("google.cloud.bigquery", ("gcp", "database.relational", "bigquery")),
    ("google.cloud.secretmanager", ("gcp", "secrets", "secretmanager")),
    ("google.cloud.tasks", ("gcp", "queue", "cloudtasks")), ("google.cloud.spanner", ("gcp", "database.relational", "spanner")),
    ("firebase_admin.firestore", ("firebase", "database.document", "firestore")),
    ("firebase_admin.auth", ("firebase", "auth", "auth")), ("firebase_admin.storage", ("firebase", "storage.object", "storage")),
    ("azure.storage.blob", ("azure", "storage.object", "blob")), ("azure.servicebus", ("azure", "queue", "servicebus")),
    ("azure.cosmos", ("azure", "database.document", "cosmosdb")), ("azure.keyvault", ("azure", "secrets", "keyvault")),
    ("azure.eventhub", ("azure", "stream", "eventhubs")),
    ("psycopg2", ("", "database.relational", "postgres")), ("psycopg", ("", "database.relational", "postgres")),
    ("asyncpg", ("", "database.relational", "postgres")), ("pymysql", ("", "database.relational", "mysql")),
    ("MySQLdb", ("", "database.relational", "mysql")), ("aiomysql", ("", "database.relational", "mysql")),
    ("sqlalchemy", ("", "database.relational", "")), ("pymongo", ("", "database.document", "mongodb")),
    ("motor", ("", "database.document", "mongodb")), ("redis", ("", "cache", "redis")), ("aioredis", ("", "cache", "redis")),
    ("elasticsearch", ("", "database.search", "elasticsearch")), ("opensearchpy", ("", "database.search", "opensearch")),
    ("kafka", ("", "stream", "kafka")), ("confluent_kafka", ("", "stream", "kafka")), ("aiokafka", ("", "stream", "kafka")),
    ("pika", ("", "queue", "rabbitmq")), ("aio_pika", ("", "queue", "rabbitmq")), ("smtplib", ("", "mail", "smtp")),
]
SDK_JS: list[tuple[str, tuple[str, str, str]]] = [
    ("stripe", ("stripe", "external.saas", "payments")), ("openai", ("openai", "external.saas", "api")),
    ("@anthropic-ai/sdk", ("anthropic", "external.saas", "api")), ("@sendgrid/mail", ("sendgrid", "mail", "email")),
    ("mailgun.js", ("mailgun", "mail", "email")), ("postmark", ("postmark", "mail", "email")),
    ("resend", ("resend", "mail", "email")), ("twilio", ("twilio", "external.saas", "messaging")),
    ("@sentry/", ("sentry", "monitoring", "errors")), ("dd-trace", ("datadog", "monitoring", "apm")),
    ("@auth0/", ("auth0", "auth", "identity")), ("auth0", ("auth0", "auth", "identity")),
    ("@clerk/", ("clerk", "auth", "identity")), ("algoliasearch", ("algolia", "database.search", "search")),
    ("@supabase/supabase-js", ("supabase", "database.relational", "postgres")),
    ("@slack/web-api", ("slack", "external.saas", "messaging")), ("pusher", ("pusher", "external.saas", "realtime")),
    ("@upstash/redis", ("upstash", "cache", "redis")), ("@vercel/postgres", ("vercel", "database.relational", "postgres")),
    ("@vercel/kv", ("vercel", "database.kv", "kv")), ("@vercel/blob", ("vercel", "storage.object", "blob")),
    ("@neondatabase/serverless", ("neon", "database.relational", "postgres")),
    ("@planetscale/database", ("planetscale", "database.relational", "mysql")),
    ("@google-cloud/storage", ("gcp", "storage.object", "gcs")), ("@google-cloud/pubsub", ("gcp", "queue", "pubsub")),
    ("@google-cloud/firestore", ("gcp", "database.document", "firestore")),
    ("@google-cloud/bigquery", ("gcp", "database.relational", "bigquery")),
    ("@google-cloud/secret-manager", ("gcp", "secrets", "secretmanager")),
    ("@google-cloud/tasks", ("gcp", "queue", "cloudtasks")),
    ("firebase-admin/firestore", ("firebase", "database.document", "firestore")),
    ("firebase-admin/auth", ("firebase", "auth", "auth")), ("firebase-admin/storage", ("firebase", "storage.object", "storage")),
    ("firebase/firestore", ("firebase", "database.document", "firestore")), ("firebase/auth", ("firebase", "auth", "auth")),
    ("firebase/storage", ("firebase", "storage.object", "storage")),
    ("@azure/storage-blob", ("azure", "storage.object", "blob")), ("@azure/service-bus", ("azure", "queue", "servicebus")),
    ("@azure/cosmos", ("azure", "database.document", "cosmosdb")), ("@azure/keyvault-secrets", ("azure", "secrets", "keyvault")),
    ("@azure/event-hubs", ("azure", "stream", "eventhubs")),
    ("pg", ("", "database.relational", "postgres")), ("postgres", ("", "database.relational", "postgres")),
    ("mysql2", ("", "database.relational", "mysql")), ("mysql", ("", "database.relational", "mysql")),
    ("@prisma/client", ("", "database.relational", "")), ("mongodb", ("", "database.document", "mongodb")),
    ("mongoose", ("", "database.document", "mongodb")), ("ioredis", ("", "cache", "redis")), ("redis", ("", "cache", "redis")),
    ("@elastic/elasticsearch", ("", "database.search", "elasticsearch")), ("kafkajs", ("", "stream", "kafka")),
    ("amqplib", ("", "queue", "rabbitmq")), ("nodemailer", ("", "mail", "smtp")),
]
# AWS SDK clients (boto3.client("x") / @aws-sdk/client-x) -> (category, service).
AWS_CLIENTS = {"s3": ("storage.object", "s3"), "sqs": ("queue", "sqs"), "sns": ("queue", "sns"),
               "dynamodb": ("database.kv", "dynamodb"), "ses": ("mail", "ses"), "sesv2": ("mail", "ses"),
               "secretsmanager": ("secrets", "secretsmanager"), "secrets-manager": ("secrets", "secretsmanager"),
               "kinesis": ("stream", "kinesis"), "lambda": ("compute.function", "lambda"),
               "eventbridge": ("scheduler", "eventbridge"), "events": ("scheduler", "eventbridge"),
               "sfn": ("compute.function", "stepfunctions"), "cognito-idp": ("auth", "cognito"),
               "cognito-identity-provider": ("auth", "cognito"), "ssm": ("secrets", "ssm"), "kms": ("secrets", "kms"),
               "rds-data": ("database.relational", "rds"), "elasticache": ("cache", "elasticache"),
               "cloudwatch": ("monitoring", "cloudwatch"), "cloudwatch-logs": ("monitoring", "cloudwatch.logs"),
               "logs": ("monitoring", "cloudwatch.logs")}
SDK_UNCLEAR = {"boto3": "aws", "botocore": "aws", "aws-sdk": "aws", "firebase_admin": "firebase", "firebase-admin": "firebase",
               "firebase": "firebase", "google.cloud": "gcp", "azure": "azure", "@aws-sdk/client-": "aws"}

# Environment variable names -> (provider, category, service). The first match wins.
ENV_RULES: list[tuple[re.Pattern, tuple[str, str, str]]] = [(re.compile(rx), v) for rx, v in (
    (r"S3_BUCKET|^AWS_S3_|_S3_", ("aws", "storage.object", "s3")), (r"SQS", ("aws", "queue", "sqs")),
    (r"SNS_TOPIC", ("aws", "queue", "sns")), (r"DYNAMO", ("aws", "database.kv", "dynamodb")),
    (r"GCS_BUCKET|^GCS_|GOOGLE_CLOUD_STORAGE", ("gcp", "storage.object", "gcs")), (r"PUBSUB", ("gcp", "queue", "pubsub")),
    (r"^AZURE_STORAGE", ("azure", "storage.object", "blob")), (r"SERVICEBUS|SERVICE_BUS", ("azure", "queue", "servicebus")),
    (r"COSMOS", ("azure", "database.document", "cosmosdb")), (r"^R2_|_R2_BUCKET", ("cloudflare", "storage.object", "r2")),
    (r"^STRIPE_", ("stripe", "external.saas", "payments")), (r"^OPENAI_", ("openai", "external.saas", "api")),
    (r"^ANTHROPIC_", ("anthropic", "external.saas", "api")), (r"^SENDGRID_", ("sendgrid", "mail", "email")),
    (r"^MAILGUN_", ("mailgun", "mail", "email")), (r"^POSTMARK_", ("postmark", "mail", "email")),
    (r"^RESEND_", ("resend", "mail", "email")), (r"^TWILIO_", ("twilio", "external.saas", "messaging")),
    (r"^SENTRY_", ("sentry", "monitoring", "errors")), (r"^DATADOG_|^DD_API_KEY$", ("datadog", "monitoring", "apm")),
    (r"^AUTH0_", ("auth0", "auth", "identity")), (r"^CLERK_|^NEXT_PUBLIC_CLERK_", ("clerk", "auth", "identity")),
    (r"^ALGOLIA_", ("algolia", "database.search", "search")),
    (r"^SUPABASE_|^NEXT_PUBLIC_SUPABASE_", ("supabase", "database.relational", "postgres")),
    (r"^SLACK_(BOT_TOKEN|WEBHOOK)", ("slack", "external.saas", "messaging")), (r"^PUSHER_", ("pusher", "external.saas", "realtime")),
    (r"^UPSTASH_REDIS", ("upstash", "cache", "redis")),
    (r"^(DATABASE_URL|DB_URL|DB_HOST|DATABASE_HOST)$|^POSTGRES_(HOST|URL|DB)$|^PG(HOST|DATABASE)$", ("", "database.relational", "")),
    (r"^MYSQL_(HOST|URL|DATABASE)$", ("", "database.relational", "mysql")),
    (r"^MONGO(DB)?_(URI|URL|HOST)$", ("", "database.document", "mongodb")),
    (r"^REDIS_(URL|HOST|URI)$|_REDIS_URL$", ("", "cache", "redis")),
    (r"^(SMTP|MAIL|EMAIL)_HOST$", ("", "mail", "smtp")),
    (r"^(ELASTICSEARCH|OPENSEARCH)_(URL|HOST|NODE)", ("", "database.search", "search")),
    (r"^KAFKA_(BROKERS|BOOTSTRAP)", ("", "stream", "kafka")), (r"^(RABBITMQ|AMQP)_URL$", ("", "queue", "rabbitmq")),
)]
ENV_INFRA_HINT = re.compile(r"(_URL|_URI|_HOST|_BUCKET|_QUEUE|_TOPIC|_DSN|_ENDPOINT|_API_KEY|_CONNECTION_STRING)$")
SAAS = {"stripe", "openai", "anthropic", "sendgrid", "mailgun", "postmark", "resend", "twilio", "sentry", "datadog",
        "auth0", "clerk", "algolia", "slack", "pusher", "supabase", "upstash", "neon", "planetscale"}
WORKFLOW_HINTS = [(re.compile(rx), p) for rx, p in (
    (r"uses:\s*aws-actions/", "aws"), (r"uses:\s*google-github-actions/", "gcp"), (r"uses:\s*azure/", "azure"),
    (r"uses:\s*cloudflare/(wrangler|pages)-action", "cloudflare"), (r"vercel", "vercel"), (r"uses:\s*superfly/", "fly"),
    (r"netlify", "netlify"), (r"uses:\s*FirebaseExtended/", "firebase"), (r"firebase deploy", "firebase"),
)]

ENV_NAME_CODE = re.compile(
    r"""(?:os\.environ(?:\.get)?\s*[\[(]\s*|os\.getenv\s*\(\s*|getenv\s*\(\s*|environ\[\s*|ENV(?:\.fetch)?\s*[\[(]\s*)
        ['"]([A-Z][A-Z0-9_]{1,80})['"]
       |(?:process\.env|import\.meta\.env)\.([A-Z][A-Z0-9_]{1,80})\b
       |(?:process\.env|import\.meta\.env)\[\s*['"]([A-Z][A-Z0-9_]{1,80})['"]""", re.X)
PY_IMPORT = re.compile(r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import\s+([\w, ()*]+)|import\s+([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*))", re.M)
JS_IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)['"]([^'"\s]+)['"]""", re.M)
AWS_CLIENT_PY = re.compile(r"""boto3\.(?:client|resource)\(\s*['"]([a-z0-9-]+)['"]""")
ENV_FILE_NAME = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{1,80})\s*=", re.M)


def env_hit(name: str):
    """(provider, category, service) for an environment variable's name, or None; "unclear" when it only looks like
    infrastructure."""
    for rx, what in ENV_RULES:
        if rx.search(name):
            return what
    return "unclear" if ENV_INFRA_HINT.search(name) else None


def scan_text(rel: str, text: str) -> dict:
    """One code file's hints: {"hits": [((provider, category, service), rel, the text as written, line)],
    "unclear": [(provider, rel, module, line)], "misses": [(provider, rel, what, why)]}. A provider of "" means the
    import does not say whose (a driver that talks to any host)."""
    out: dict = {"hits": [], "unclear": [], "misses": []}
    ext = os.path.splitext(rel)[1]
    if ext == ".py":
        mods = []
        for m in PY_IMPORT.finditer(text):
            if m.group(1):
                mods.append((m.group(1), m.start(), m.group(1)))
                mods.extend((f"{m.group(1)}.{x.strip()}", m.start(), m.group(1))
                            for x in re.split(r"[,()\s]+", m.group(2)) if x.strip() and x.strip() != "*")
            else:
                mods.extend((x.strip(), m.start(), x.strip()) for x in m.group(3).split(","))
        table = SDK_PY
    else:
        mods = [(m.group(1), m.start(), m.group(1)) for m in JS_IMPORT.finditer(text)]
        table = SDK_JS
    for mod, pos, literal in mods:
        line = text.count("\n", 0, pos) + 1
        hit = None
        for prefix, what in table:
            if mod == prefix or mod.startswith(prefix if prefix.endswith(("/", "-")) else prefix + ".") or \
                    (ext != ".py" and mod.startswith(prefix + "/")):
                hit = what
                break
        m = re.match(r"@aws-sdk/client-([a-z0-9-]+)$", mod)
        if m:
            c = AWS_CLIENTS.get(m.group(1))
            if not c:
                out["misses"].append(("aws", rel, mod, "AWS client with no category"))
                continue
            hit = ("aws", c[0], c[1])
        if hit:
            out["hits"].append((hit, rel, literal, line))
        else:
            for prefix, prov in SDK_UNCLEAR.items():
                if mod == prefix or mod.startswith(prefix + ".") or mod.startswith(prefix + "/"):
                    out["unclear"].append((prov, rel, mod, line))
                    break
    for m in AWS_CLIENT_PY.finditer(text):
        c = AWS_CLIENTS.get(m.group(1))
        line = text.count("\n", 0, m.start()) + 1
        if c:
            out["hits"].append((("aws", c[0], c[1]), rel, m.group(0), line))
        else:
            out["misses"].append(("aws", rel, m.group(0), "AWS client with no category"))
    for m in ENV_NAME_CODE.finditer(text):
        _env(out, m.group(1) or m.group(2) or m.group(3), rel, text.count("\n", 0, m.start()) + 1)
    return out


def scan_env_names(rel: str, text: str) -> dict:
    """The names in an .env.example-like file (names only: those files carry no values by convention, and none is
    read here)."""
    out: dict = {"hits": [], "unclear": [], "misses": []}
    for m in ENV_FILE_NAME.finditer(text):
        _env(out, m.group(1), rel, text.count("\n", 0, m.start()) + 1)
    return out


def _env(out: dict, name: str, rel: str, line: int) -> None:
    what = env_hit(name)
    if what == "unclear":
        out["misses"].append(("(unknown)", rel, name, "environment variable that looks like infrastructure; no rule matches it"))
    elif what:
        out["hits"].append((what, rel, name, line))
