"""check kind=infra (boundary §6): builtin:infra-iac and builtin:infra-code against a project built in tmp_path.

Each provider's IaC is compared with that provider's declared nodes through their iac addresses: matched, a category
that differs, declared but not in the IaC, in the IaC but not declared; fine-grained types dropped; and what could not
be checked said per provider (no IaC for a provider, a module from outside, count/for_each, an unmapped type).
infra-code: an evidence that went, an SDK the model does not name. Findings are warnings unless "gate": true.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jsonui_doc_cli.check import infra_check as C
from jsonui_doc_cli.check.report import report_path_for
from jsonui_doc_cli.check.runner import run_checks
from jsonui_doc_cli.project_config import ProjectConfigError, load_checks

MODEL = {
    "version": 0,
    "environments": [{"id": "production", "kind": "production"}, {"id": "local", "kind": "local"}],
    "groups": [{"id": "aws", "kind": "account", "provider": "aws"}, {"id": "cf", "kind": "account", "provider": "cloudflare"},
               {"id": "desk", "kind": "host", "provider": "docker", "environments": ["local"]}],
    "nodes": [
        {"id": "api", "category": "compute.container", "group": "aws", "iac": ["module.api.aws_ecs_service.api"]},
        {"id": "db", "category": "database.relational", "group": "aws", "iac": ["aws_db_instance.main"]},
        {"id": "cache", "category": "cache", "group": "aws", "iac": ["aws_elasticache_cluster.gone"]},
        {"id": "jobs", "category": "storage.object", "group": "aws", "iac": ["aws_sqs_queue.jobs"]},
        {"id": "role", "category": "security.iam", "group": "aws"},
        {"id": "cf-q", "category": "queue", "provider": "cloudflare", "iac": ["aws_sqs_queue.jobs"]},
        {"id": "worker", "category": "compute.function", "group": "cf", "iac": ["wrangler.toml"]},
        {"id": "kv", "category": "database.kv", "group": "cf", "iac": ["wrangler.toml#kv_namespaces.CACHE"]},
        {"id": "app-local", "category": "compute.container", "group": "desk", "iac": ["compose.yaml#services.app"], "environments": ["local"]},
        {"id": "db-local", "category": "database.relational", "group": "desk", "iac": ["compose.yaml#services.db"], "environments": ["local"]},
        {"id": "web", "category": "compute.paas", "provider": "vercel", "iac": ["vercel.json"]},
        {"id": "stripe", "category": "external.saas", "provider": "stripe", "managed_by": "external",
         "evidence": [{"file": "backend/pay.py", "pattern": "stripe.Charge"}, {"file": "backend/pay.py", "pattern": "stripe.Refund"}]},
        {"id": "mailer", "category": "mail", "provider": "sendgrid", "managed_by": "external",
         "evidence": [{"file": "backend/mail.py", "pattern": "sendgrid"}]},
    ],
}
FILES = {
    "infra/main.tf": '''
module "api" {
  source = "./modules/api"
}
module "net" {
  source  = "terraform-aws-modules/vpc/aws"
}
resource "aws_db_instance" "main" {
  engine = "mysql"
}
resource "aws_sqs_queue" "jobs" {}
resource "aws_s3_bucket" "logs" {}
resource "aws_iam_role" "api" {}
resource "aws_cloudwatch_metric_alarm" "cpu" {}
resource "aws_mystery_widget" "w" {}
''',
    "infra/modules/api/main.tf": 'resource "aws_ecs_service" "api" {\n  count = 2\n}\n',
    "compose.yaml": "services:\n  app:\n    build: .\n  db:\n    image: postgres:17\n",
    "wrangler.toml": 'name = "worker"\n[[kv_namespaces]]\nbinding = "CACHE"\nid = "x"\n',
    "template.yaml": "AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  Fn:\n    Type: AWS::Serverless::Function\n"
                     "    Properties:\n      Handler: !Ref Handler\n  FnRole:\n    Type: AWS::IAM::Role\n",
    "k8s/deploy.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web-k8s\n---\napiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cfg\n",
    "backend/pay.py": "import stripe\n\nstripe.Charge.create()\n",
    "backend/ai.py": "from openai import OpenAI\n",
    ".env.example": "REDIS_URL=\nSTRIPE_KEY=\n",
}


def _project(tmp_path, checks=None) -> Path:
    root = tmp_path / "proj"
    (root / "docs" / "infra").mkdir(parents=True)
    (root / "docs" / "infra" / "main.json").write_text(json.dumps(MODEL))
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    (root / "jui.config.json").write_text(json.dumps({"checks": checks or [
        {"name": "infra-iac", "type": "builtin:infra-iac"}, {"name": "infra-code", "type": "builtin:infra-code"}]}))
    return root


def _decls(root):
    return {d.name: d for d in load_checks(json.loads((root / "jui.config.json").read_text()), root)}


def _by_target(report):
    return {r.target: r for r in report.results}


def test_iac_against_the_model_per_provider(tmp_path):
    root = _project(tmp_path, [{"name": "iac", "type": "builtin:infra-iac", "gate": True}])
    rep = C.run_infra_iac(_decls(root)["iac"], root)
    t = _by_target(rep)
    assert t["aws/api"].status == "ok" and t["aws/db"].status == "ok"          # module.api.<addr> ends with the address read
    assert t["aws/cache"].status == "missing_in_impl"
    assert t["aws/jobs"].status == "mismatch" and (t["aws/jobs"].expected, t["aws/jobs"].actual) == ("storage.object", "queue")
    assert t["cloudflare/worker"].status == "ok" and t["cloudflare/kv"].status == "ok"
    assert t["docker/app-local"].status == "ok" and t["docker/db-local"].status == "ok"
    assert t["aws/role"].status == "skipped"                                   # no iac address: not compared
    assert t["vercel/web"].status == "skipped"
    assert t["cloudflare/cf-q"].status == "missing_in_impl"                    # an aws resource never answers a cloudflare node
    for undeclared in ("aws/aws_s3_bucket.logs", "aws/Fn", "kubernetes/Deployment/web-k8s"):
        assert t[undeclared].status == "missing_in_doc", undeclared
    assert not any("iam" in k or "alarm" in k or "FnRole" in k or "ConfigMap" in k for k in t)   # fine-grained: dropped
    assert "stripe" not in " ".join(t)                                        # external: not an IaC thing
    assert rep.has_mismatch


def test_what_could_not_be_checked_is_said_per_provider(tmp_path):
    root = _project(tmp_path)
    rep = C.run_infra_iac(_decls(root)["infra-iac"], root)
    un = rep.target_extra["unverified"]
    assert any("no IaC found" in w for w in un["vercel"])
    assert any("aws_mystery_widget" in w for w in un["aws"])
    assert not any("iam" in w or "alarm" in w for w in un["aws"])            # fine-grained types are dropped, not "unmapped"
    assert any('module "net" comes from outside' in w for w in un["*"])
    assert any("count / for_each are not evaluated" in w for w in un["aws"])   # the file's resources are aws's
    assert any(w.startswith("1 resource(s) that are parts") for w in un["kubernetes"])   # the ConfigMap: counted, not silent
    lines = [w for w in rep.warnings if w.startswith("[unverified] ")]
    assert len(lines) == sum(map(len, un.values()))


def test_findings_are_warnings_unless_gate(tmp_path):
    root = _project(tmp_path)
    rep = C.run_infra_iac(_decls(root)["infra-iac"], root)
    statuses = {r.status for r in rep.results}
    assert statuses <= {"ok", "skipped", "warning"} and "warning" in statuses and not rep.has_mismatch
    gated = _project(tmp_path / "g", [{"name": "iac", "type": "builtin:infra-iac", "gate": True}])
    assert run_checks(list(_decls(gated).values()), gated, {}) == 1
    assert run_checks(list(_decls(root).values()), root, {}) == 0


def test_code_evidence_and_sdks(tmp_path):
    root = _project(tmp_path, [{"name": "code", "type": "builtin:infra-code", "gate": True}])
    rep = C.run_infra_code(_decls(root)["code"], root)
    t = _by_target(rep)
    assert t["stripe/stripe#evidence/0"].status == "ok"
    assert t["stripe/stripe#evidence/1"].status == "missing_in_impl"         # the file is there, the pattern is not
    assert t["sendgrid/mailer#evidence/0"].status == "missing_in_impl"        # backend/mail.py is not there
    assert t["code/stripe"].status == "ok" and t["code/openai"].status == "missing_in_doc"
    assert "backend/ai.py:1" in t["code/openai"].message
    assert t["code/cache"].status == "ok"                                     # REDIS_URL, and a cache node exists
    assert any("only Python and JavaScript / TypeScript imports" in w for w in rep.warnings)


def test_reports_go_beside_the_model_hidden_from_its_reader(tmp_path):
    root = _project(tmp_path)
    assert run_checks(list(_decls(root).values()), root, {}) == 0
    for name in ("infra-iac", "infra-code"):
        path = report_path_for("infra", name, root)
        assert path == root / "docs" / "infra" / f".check-report.{name}.json" and path.is_file()
        data = json.loads(path.read_text())
        assert data["target"]["kind"] == "infra" and "unverified" in data["target"]
    from jsonui_doc_cli.infra import room
    assert room.read(root)["files"] == ["main.json"]                          # the reports are not model files


def test_a_model_with_errors_is_an_execution_error(tmp_path):
    root = _project(tmp_path)
    (root / "docs" / "infra" / "bad.json").write_text(json.dumps({"version": 0, "nodes": [{"id": "x", "category": "nope"}]}))
    assert run_checks(list(_decls(root).values()), root, {}) == 2


@pytest.mark.parametrize("decl", [{"name": "x", "type": "builtin:infra-iac", "gate": "yes"},
                                  {"name": "x", "type": "builtin:infra-iac", "ignore_types": "aws_s3_bucket"}])
def test_the_declaration_is_checked(tmp_path, decl):
    with pytest.raises(ProjectConfigError):
        load_checks({"checks": [decl]}, tmp_path)


def test_ignore_types(tmp_path):
    root = _project(tmp_path, [{"name": "iac", "type": "builtin:infra-iac", "ignore_types": ["aws_s3_bucket"]}])
    t = _by_target(C.run_infra_iac(_decls(root)["iac"], root))
    assert "aws/aws_s3_bucket.logs" not in t and "aws/aws_sqs_queue.jobs" not in t


def test_check_infra_from_the_cli(tmp_path):
    root = _project(tmp_path)
    tools = Path(__file__).resolve().parents[1]
    import os
    r = subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "check", "infra"], cwd=root, capture_output=True,
                       text=True, env={**os.environ, "PYTHONPATH": os.pathsep.join([str(tools), *sys.path])})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "builtin:infra-iac" in r.stdout and "[unverified] vercel" in r.stdout



# ---------------------------------------------------------------- one table with seed (ticket 2026-10-20-jui-infra-seed-and-check-tables-disagree)

def test_check_has_no_table_of_its_own():
    """The old names (check's own tables, then views of the shared one while seed moved) are gone: one coming back
    is a second table again."""
    for old in ("TF_CATEGORY", "TF_PROVIDER", "CFN_CATEGORY", "K8S_CATEGORY", "COMPOSE_IMAGE", "IGNORED"):
        assert not hasattr(C, old), old
    src = Path(C.__file__).read_text()
    assert '"aws_db_instance"' not in src and '"AWS::S3::Bucket"' not in src     # no type is spelled in check itself


def _mini(tmp_path, files, nodes):
    root = tmp_path / "mini"
    (root / "docs" / "infra").mkdir(parents=True)
    (root / "docs" / "infra" / "m.json").write_text(json.dumps({"version": 0, "nodes": nodes}))
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    (root / "jui.config.json").write_text(json.dumps({"checks": [{"name": "iac", "type": "builtin:infra-iac", "gate": True}]}))
    return root, C.run_infra_iac(_decls(root)["iac"], root)


def test_folded_resources_are_compared_when_declared_and_not_asked_for_when_not(tmp_path):
    tf = 'resource "aws_iam_role" "api" {}\nresource "aws_cloudwatch_metric_alarm" "cpu" {}\nresource "aws_iam_role_policy_attachment" "a" {}\n'
    root, rep = _mini(tmp_path, {"main.tf": tf}, [{"id": "role", "category": "security.iam", "provider": "aws", "iac": ["aws_iam_role.api"]}])
    t = _by_target(rep)
    assert t["aws/role"].status == "ok"
    assert not any("alarm" in k or "attachment" in k for k in t)               # not declared: not asked for; a part: never
    assert any("IAM / policy / alarm" in w and w.startswith("1 ") for w in rep.warnings)


def test_a_k8s_workload_is_a_container_and_the_cluster_is_compute_k8s(tmp_path):
    k8s = ("apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n---\napiVersion: v1\nkind: Service\n"
           "metadata:\n  name: lb\nspec:\n  type: LoadBalancer\n---\napiVersion: v1\nkind: Service\nmetadata:\n  name: inner\n")
    _r, rep = _mini(tmp_path, {"k8s/app.yaml": k8s}, [   # named like App Engine's file: a manifest all the same
        {"id": "web", "category": "compute.container", "provider": "kubernetes", "iac": ["Deployment/web"]},
        {"id": "lb", "category": "load_balancer", "provider": "kubernetes", "iac": ["Service/lb"]}])
    t = _by_target(rep)
    assert t["kubernetes/web"].status == "ok" and t["kubernetes/lb"].status == "ok"
    assert "kubernetes/Service/inner" not in t                                # a ClusterIP Service is a part


def test_a_synthesized_cdk_app_and_bicep_are_read(tmp_path):
    cdk = json.dumps({"Resources": {"ApiFnABC123": {"Type": "AWS::Lambda::Function"}, "ApiFnRole": {"Type": "AWS::IAM::Policy"},
                                    "CDKMetadata": {"Type": "AWS::CDK::Metadata"}}})
    bicep = "resource web 'Microsoft.Web/sites@2023-01-01' = {\n}\nresource plan 'Microsoft.Web/serverfarms@2023-01-01' = {\n}\n"
    _r, rep = _mini(tmp_path, {"cdk.out/App.template.json": cdk, "infra/main.bicep": bicep}, [
        {"id": "fn", "category": "compute.function", "provider": "aws", "iac": ["ApiFnABC123"]},
        {"id": "web", "category": "compute.paas", "provider": "azure", "iac": ["web"]}])
    t = _by_target(rep)
    assert t["aws/fn"].status == "ok" and t["azure/web"].status == "ok"
    assert not any("CDKMetadata" in k or "plan" in k for k in t)


def test_settings_seed_reads_are_said_not_compared(tmp_path):
    _r, rep = _mini(tmp_path, {"firebase.json": "{}", "fly.toml": "app = 'x'\n", "gae/app.yaml": "runtime: python312\n"},
                    [{"id": "h", "category": "compute.paas", "provider": "firebase", "iac": ["firebase:hosting"]}])
    un = rep.target_extra["unverified"]
    assert any("firebase.json" in w and "not compare" in w for w in un["firebase"]) and "fly" in un
    assert any("gae/app.yaml" in w for w in un["gcp"])                      # App Engine's app.yaml (a runtime, no apiVersion)
    assert _by_target(rep)["firebase/h"].status == "skipped"


# ---------------------------------------------------------------- dd's verification (10-20): nothing dropped in silence

def test_an_iac_file_not_read_is_said_and_never_gates(tmp_path, monkeypatch):
    """D4: a CDK template over the read limit made its declared node "missing_in_impl" (exit 1 with gate) and said
    nothing in unverified."""
    monkeypatch.setattr(C, "MAX_BYTES", 2_000)
    big = json.dumps({"Resources": {"BigDb": {"Type": "AWS::RDS::DBInstance"}}, "Pad": "x" * 3_000})
    small = "AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  Q:\n    Type: AWS::SQS::Queue\n"
    root, rep = _mini(tmp_path, {"cdk.out/Big.template.json": big, "template.yaml": small},   # aws IaC read, and one file not
                      [{"id": "db", "category": "database.relational", "provider": "aws", "iac": ["BigDb"]},
                       {"id": "q", "category": "queue", "provider": "aws", "iac": ["Q"]}])
    assert _by_target(rep)["aws/q"].status == "ok"
    assert any("cdk.out/Big.template.json" in w and "not read" in w for w in rep.target_extra["unverified"]["aws"])
    assert _by_target(rep)["aws/db"].status == "skipped" and not rep.has_mismatch


def test_terraform_json_tofu_and_json_manifests_are_read(tmp_path):
    tfjson = json.dumps({"resource": {"aws_s3_bucket": {"assets": {}}, "aws_iam_role_policy": {"p": {}}}})
    k8s = json.dumps({"apiVersion": "v1", "kind": "List", "items": [
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "web"}}]})
    _r, rep = _mini(tmp_path, {"cdktf.out/stacks/app/cdk.tf.json": tfjson, "infra/db.tofu": 'resource "aws_db_instance" "main" {}\n',
                               "k8s/web.json": k8s}, [
        {"id": "assets", "category": "storage.object", "provider": "aws", "iac": ["aws_s3_bucket.assets"]},
        {"id": "db", "category": "database.relational", "provider": "aws", "iac": ["aws_db_instance.main"]},
        {"id": "web", "category": "compute.container", "provider": "kubernetes", "iac": ["Deployment/web"]}])
    t = _by_target(rep)
    assert [t[k].status for k in ("aws/assets", "aws/db", "kubernetes/web")] == ["ok", "ok", "ok"]


def test_ignore_types_works_on_every_kind_of_type(tmp_path):
    root = _project(tmp_path, [{"name": "iac", "type": "builtin:infra-iac",
                                "ignore_types": ["AWS::Serverless::Function", "Deployment", "aws_s3_bucket"]}])
    t = _by_target(C.run_infra_iac(_decls(root)["iac"], root))
    assert not any(k in t for k in ("aws/Fn", "kubernetes/Deployment/web-k8s", "aws/aws_s3_bucket.logs"))


def test_nodes_from_platform_settings_are_not_compared_and_a_procfile_is_no_ones(tmp_path):
    """serverless:hello (seed drafts it from serverless.yml) was "declared but not in IaC" beside a CFN template."""
    _r, rep = _mini(tmp_path, {"serverless.yml": "functions:\n  hello: {}\n", "Procfile": "web: run\n",
                               "template.yaml": "AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  Q:\n    Type: AWS::SQS::Queue\n"},
                    [{"id": "hello", "category": "compute.function", "provider": "aws", "iac": ["serverless:hello"]},
                     {"id": "q", "category": "queue", "provider": "aws", "iac": ["Q"]}])
    t = _by_target(rep)
    assert t["aws/hello"].status == "skipped" and t["aws/q"].status == "ok" and not rep.has_mismatch
    un = rep.target_extra["unverified"]
    assert any("serverless settings are not compared" in w for w in un["aws"]) and any("Procfile" in w for w in un["*"])
    from jsonui_doc_cli.infra import iac_tables as T
    assert T.PAAS_FILES["Procfile"][0] is None and C.NOT_COMPARED["Procfile"] == "*"


def test_a_name_read_from_iac_with_a_secret_shape_is_masked_in_the_report(tmp_path):
    wr = 'name = "w"\n[[d1_databases]]\ndatabase_name = "998877665544"\n'
    _r, rep = _mini(tmp_path, {"wrangler.toml": wr}, [])
    text = json.dumps(rep.to_dict())
    assert "998877665544" not in text and "<masked: holds the shape of a secret>" in text


def test_code_is_read_through_the_shared_hints_and_other_languages_are_said(tmp_path):
    _r, _rep = _mini(tmp_path, {"svc/main.go": "package main\n", "app/db.py": "import psycopg2\n"},
                     [{"id": "pg", "category": "database.relational", "provider": "aws"}])
    root = _r
    (root / "jui.config.json").write_text(json.dumps({"checks": [{"name": "code", "type": "builtin:infra-code"}]}))
    rep = C.run_infra_code(_decls(root)["code"], root)
    t = _by_target(rep)
    assert t["code/database.relational"].status == "ok"                      # psycopg2 names no provider: its category
    assert any("1 Go file(s)" in w for w in rep.warnings)
    from jsonui_doc_cli.infra import code_hints as H
    src = Path(C.__file__).read_text()
    assert "psycopg2" not in src and "SDK_HINTS" not in src and H.SDK_PY      # one table: code_hints



# ---------------------------------------------------------------- dd's re-verification (10-20)

def test_a_big_iac_file_named_like_anything_is_said_by_its_head(tmp_path, monkeypatch):
    """N3 (a): stack.yaml over the limit: no name says it is CloudFormation; its head does."""
    monkeypatch.setattr(C, "MAX_BYTES", 2_000)
    big = "AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  Q:\n    Type: AWS::SQS::Queue\n#" + "x" * 3_000 + "\n"
    _r, rep = _mini(tmp_path, {"infra/stack.yaml": big, "infra/main.tf": 'resource "aws_s3_bucket" "b" {}\n'},
                    [{"id": "q", "category": "queue", "provider": "aws", "iac": ["Q"]},
                     {"id": "b", "category": "storage.object", "provider": "aws", "iac": ["aws_s3_bucket.b"]}])
    assert any("infra/stack.yaml" in w and "not read" in w for w in rep.target_extra["unverified"]["aws"])
    assert _by_target(rep)["aws/q"].status == "skipped" and not rep.has_mismatch


def test_a_file_that_does_not_parse_never_gates(tmp_path):
    """N3 (b): a broken template or cdk.tf.json is said, and its provider's nodes are not "missing"."""
    _r, rep = _mini(tmp_path, {"cdk.out/App.template.json": "{ broken", "infra/main.tf": 'resource "aws_s3_bucket" "b" {}\n'},
                    [{"id": "q", "category": "queue", "provider": "aws", "iac": ["Q"]},
                     {"id": "b", "category": "storage.object", "provider": "aws", "iac": ["aws_s3_bucket.b"]}])
    assert _by_target(rep)["aws/q"].status == "skipped" and not rep.has_mismatch
    _r2, rep2 = _mini(tmp_path / "2", {"cdk.tf.json": "{ broken", "infra/main.tf": 'resource "aws_s3_bucket" "b" {}\n'},
                      [{"id": "d", "category": "database.relational", "provider": "aws", "iac": ["aws_db_instance.main"]}])
    assert _by_target(rep2)["aws/d"].status == "skipped"


def test_an_unread_terraform_file_hides_only_terraform_addresses(tmp_path, monkeypatch):
    """N3 (c) and V17, V18: a big .tf / .tofu is said; a compose node is still compared."""
    monkeypatch.setattr(C, "MAX_BYTES", 2_000)
    big_tf = 'resource "aws_s3_bucket" "b" {}\n#' + "x" * 3_000 + "\n"
    _r, rep = _mini(tmp_path, {"infra/big.tofu": big_tf, "compose.yaml": "services:\n  app:\n    build: .\n",
                               "infra/small.tf": 'resource "aws_sqs_queue" "q" {}\n'},
                    [{"id": "gone", "category": "compute.container", "provider": "docker", "iac": ["compose.yaml#services.gone"]},
                     {"id": "b", "category": "storage.object", "provider": "aws", "iac": ["aws_s3_bucket.b"]}])
    t = _by_target(rep)
    assert any("infra/big.tofu" in w for w in rep.target_extra["unverified"]["*"])
    assert t["aws/b"].status == "skipped" and t["docker/gone"].status == "missing_in_impl"


def test_terraform_json_gets_the_notes_hcl_gets(tmp_path):
    """N3 (d) and V19: count / for_each and a module from outside, and CDKTF's list form."""
    tfj = json.dumps({"module": {"net": {"source": "terraform-aws-modules/vpc/aws"}},
                      "resource": [{"aws_db_instance": {"main": {"count": 2}}}]})
    _r, rep = _mini(tmp_path, {"cdk.tf.json": tfj},
                    [{"id": "db", "category": "database.relational", "provider": "aws", "iac": ["aws_db_instance.main"]}])
    un = rep.target_extra["unverified"]
    assert _by_target(rep)["aws/db"].status == "ok"
    assert any('module "net"' in w for w in un["*"]) and any("count / for_each" in w for w in un["aws"])


def test_every_field_of_the_report_is_masked(tmp_path):
    """V20: not the target alone — a message that names the file carries it too."""
    _r, rep = _mini(tmp_path, {"10.0.0.5/main.tf": 'resource "aws_sqs_queue" "q" {}\n'},
                    [{"id": "q", "category": "storage.object", "provider": "aws", "iac": ["aws_sqs_queue.q"]}])
    item = _by_target(rep)["aws/q"]
    assert item.status == "mismatch" and "10.0.0.5" not in json.dumps(rep.to_dict())
