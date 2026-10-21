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


# ---------------------------------------------------------------- the independent verification (10-20): nothing dropped in silence

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



# ---------------------------------------------------------------- the independent re-verification (10-20)

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



# ---------------------------------------------------------------- the independent third verification (10-20)

@pytest.mark.parametrize("rel, text, provider, node", [
    ("k8s/big.yaml", "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n", "kubernetes",
     {"id": "web", "category": "compute.container", "provider": "kubernetes", "iac": ["Deployment/web"]}),            # O09
    ("k8s/big.yml", "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n", "kubernetes",
     {"id": "web", "category": "compute.container", "provider": "kubernetes", "iac": ["Deployment/web"]}),            # O26
    ("infra/stack.json", json.dumps({"terraform": {}, "resource": {"aws_s3_bucket": {"b": {}}}}), "*",
     {"id": "b", "category": "storage.object", "provider": "aws", "iac": ["aws_s3_bucket.b"]}),                      # O10
    ("infra/stack.yaml", "Resources:\n  Q:\n    Type: AWS::SQS::Queue\n", "aws",
     {"id": "q", "category": "queue", "provider": "aws", "iac": ["Q"]}),                                              # O24
    ("infra/stack.json", '{"Resources":{"Q":{"Type":"AWS::SQS::Queue"}}}', "aws",
     {"id": "q", "category": "queue", "provider": "aws", "iac": ["Q"]}),                                              # P4 (a)
])
def test_each_kind_of_big_file_is_known_by_its_head(tmp_path, monkeypatch, rel, text, provider, node):
    monkeypatch.setattr(C, "MAX_BYTES", 2_000)
    pad = ("\n#" if not rel.endswith(".json") else "") + "x" * 3_000
    big = text + pad if not rel.endswith(".json") else text[:-1] + ', "pad": "' + "x" * 3_000 + '"}'
    readable = {"kubernetes": ("k8s/a.yaml", "apiVersion: v1\nkind: Service\nmetadata:\n  name: lb\nspec:\n  type: LoadBalancer\n"),
                "*": ("infra/main.tf", 'resource "aws_sqs_queue" "q" {}\n'),
                "aws": ("infra/main.tf", 'resource "aws_sqs_queue" "q" {}\n')}[provider]
    _r, rep = _mini(tmp_path, {rel: big, readable[0]: readable[1]}, [node])
    t = _by_target(rep)
    assert t[f"{node['provider']}/{node['id']}"].status == "skipped"
    assert any(rel in w and "not read" in w for w in rep.target_extra["unverified"][provider])


@pytest.mark.parametrize("files, node", [
    ({"compose.yaml": "services:\n  app:\n    build: .\n", "compose.override.yaml": "services: [broken"},
     {"id": "w", "category": "compute.container", "provider": "docker", "iac": ["compose.override.yaml#services.w"]}),  # O14
    ({"wrangler.toml": 'name = "a"\n', "api/wrangler.toml": "name = [broken"},
     {"id": "w", "category": "compute.function", "provider": "cloudflare", "iac": ["api/wrangler.toml"]}),             # O15
    ({"k8s/a.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: a\n", "k8s/b.yaml": "apiVersion: v1\nkind: [broken"},
     {"id": "w", "category": "compute.container", "provider": "kubernetes", "iac": ["Deployment/b"]}),                 # O16
])
def test_a_broken_file_of_any_kind_never_gates(tmp_path, files, node):
    _r, rep = _mini(tmp_path, files, [node])
    assert _by_target(rep)[f"{node['provider']}/{node['id']}"].status == "skipped"


def test_an_unread_terraform_file_hides_a_module_path_address_too(tmp_path, monkeypatch):
    """O17: module.x.<type>.<name> is a Terraform address."""
    monkeypatch.setattr(C, "MAX_BYTES", 2_000)
    _r, rep = _mini(tmp_path, {"infra/big.tf": 'resource "aws_s3_bucket" "b" {}\n#' + "x" * 3_000 + "\n",
                               "infra/small.tf": 'resource "aws_sqs_queue" "q" {}\n'},
                    [{"id": "b", "category": "storage.object", "provider": "aws", "iac": ["module.x.aws_s3_bucket.b"]},
                     {"id": "q", "category": "queue", "provider": "aws", "iac": ["aws_sqs_queue.q"]}])
    assert _by_target(rep)["aws/b"].status == "skipped"


def test_a_module_inside_the_project_is_not_said_to_come_from_outside(tmp_path):
    """O12: the .tf.json module branch tells ./ from a registry source."""
    tfj = json.dumps({"module": {"net": {"source": "./modules/net"}, "ext": {"source": "hashicorp/consul/aws"}},
                      "resource": {"aws_s3_bucket": {"b": {}}}})
    _r, rep = _mini(tmp_path, {"cdk.tf.json": tfj},
                    [{"id": "b", "category": "storage.object", "provider": "aws", "iac": ["aws_s3_bucket.b"]}])
    star = rep.target_extra["unverified"].get("*", [])
    assert any('module "ext"' in w for w in star) and not any('module "net"' in w for w in star)


def test_a_note_that_mentions_aws_types_is_not_a_template(tmp_path):
    """P4 (b): a broken notes file with "AWS::" in prose made every aws node "not read"."""
    _r, rep = _mini(tmp_path, {"docs-notes/notes.yaml": "body: we use AWS::SQS::Queue and: [broken",
                               "infra/main.tf": 'resource "aws_sqs_queue" "q" {}\n'},
                    [{"id": "gone", "category": "queue", "provider": "aws", "iac": ["aws_sqs_queue.gone"]},
                     {"id": "q", "category": "queue", "provider": "aws", "iac": ["aws_sqs_queue.q"]}])
    assert _by_target(rep)["aws/gone"].status == "missing_in_impl"


def test_a_provider_whose_files_were_not_read_is_not_said_to_have_none(tmp_path):
    """P4 (c): "not read" and "no IaC found" side by side for the same provider."""
    _r, rep = _mini(tmp_path, {"k8s/b.yaml": "apiVersion: v1\nkind: [broken"},
                    [{"id": "w", "category": "compute.container", "provider": "kubernetes", "iac": ["Deployment/b"]}])
    un = rep.target_extra["unverified"]["kubernetes"]
    assert any("not parsed" in w for w in un) and not any("no IaC found" in w for w in un)


# ---------------------------------------------------------------- the independent fourth verification (2026-10-20 14:42)


def test_a_wrangler_jsonc_as_npm_create_cloudflare_writes_it_is_read(tmp_path):
    """R1: a block comment first, "//" after a value, a "," after the last item — check read only whole-line "//"."""
    jsonc = ('/**\n * For more details on how to configure Wrangler, refer to:\n * https://developers.cloudflare.com/workers/\n */\n'
             '{\n\t"name": "my-worker", // the worker\n\t"main": "src/index.ts",\n\t"note": "a // and ,} in a string",\n'
             '\t"kv_namespaces": [\n\t\t{ "binding": "CACHE", "id": "abc", },\n\t],\n}\n')
    _r, rep = _mini(tmp_path, {"wrangler.jsonc": jsonc},
                    [{"id": "w", "category": "compute.function", "provider": "cloudflare", "iac": ["wrangler.jsonc"]},
                     {"id": "kv", "category": "database.kv", "provider": "cloudflare", "iac": ["wrangler.jsonc#kv_namespaces.CACHE"]}])
    t = _by_target(rep)
    assert (t["cloudflare/w"].status, t["cloudflare/kv"].status) == ("ok", "ok")
    assert not any("not parsed" in w for w in rep.target_extra["unverified"].get("cloudflare", []))


def test_a_template_with_a_bom_and_no_version_line_is_read(tmp_path):
    """Q2: a BOM first hid "Resources" from the line-start match; a quoted 'Resources': too."""
    for text in ("\ufeffResources:\n  Q:\n    Type: AWS::SQS::Queue\n", "'Resources':\n  Q:\n    Type: AWS::SQS::Queue\n"):
        root = tmp_path / f"r{len(text)}"
        root.mkdir()
        r, _ = _mini(root, {"infra/main.tf": 'resource "aws_sqs_queue" "other" {}\n'}, [{"id": "q", "category": "queue", "provider": "aws", "iac": ["Q"]}])
        (r / "infra" / "stack.yaml").write_bytes(text.encode("utf-8"))
        rep = C.run_infra_iac(_decls(r)["iac"], r)
        assert _by_target(rep)["aws/q"].status == "ok", text[:12]


@pytest.mark.parametrize("notes", ["body: [broken\nType: AWS::SQS::Queue\n", "Resources:\n  body: [broken, no type\n"])
def test_a_broken_note_with_only_one_half_of_a_template_is_not_one(tmp_path, notes):
    """A14 / A15: each of the two conditions of P4 (b) — Resources and an AWS:: Type — is needed: a broken note with
    only one of them is no template, so it never hides the aws nodes as "not read"."""
    _r, rep = _mini(tmp_path, {"docs-notes/notes.yaml": notes, "infra/main.tf": 'resource "aws_sqs_queue" "q" {}\n'},
                    [{"id": "gone", "category": "queue", "provider": "aws", "iac": ["aws_sqs_queue.gone"]}])
    assert _by_target(rep)["aws/gone"].status == "missing_in_impl"


def test_a_provider_is_not_said_to_have_none_when_a_file_of_no_known_provider_was_not_read(tmp_path, monkeypatch):
    """Q4: a Terraform file over the size ("*": anyone's) and "no IaC found" for aws side by side."""
    monkeypatch.setattr(C, "MAX_BYTES", 200)
    _r, rep = _mini(tmp_path, {"infra/main.tf": "# " + "x" * 400 + '\nresource "aws_sqs_queue" "q" {}\n'},
                    [{"id": "q", "category": "queue", "provider": "aws", "iac": ["aws_sqs_queue.q"]}])
    un = rep.target_extra["unverified"]
    assert any("not read" in w for w in un.get("*", []))
    assert not any("no IaC found" in w for w in un.get("aws", [])) and any("see *" in w for w in un.get("aws", []))
    _r2, rep2 = _mini(tmp_path / "plain", {"k8s/a.yaml": "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: a\n"},
                      [{"id": "q", "category": "queue", "provider": "aws", "iac": ["aws_sqs_queue.q"]}])
    assert any("no IaC found" in w for w in rep2.target_extra["unverified"]["aws"])   # nothing unread: still said


def test_which_file_is_what_is_one_table():
    """R3 / (C)'s request: iac_tables says which file is IaC, of which kind and whose; check spells none of it."""
    from jsonui_doc_cli.infra import iac_tables as T
    want = {"infra/main.tf": ("terraform", "*"), "infra/main.tofu": ("terraform", "*"), "a.tf.json": ("terraform_json", "*"),
            "m.bicep": ("bicep", "azure"), "wrangler.jsonc": ("wrangler", "cloudflare"), "docker-compose.yml": ("compose", "docker"),
            "compose.prod.yaml": ("compose", "docker"), "template.yaml": ("cfn", "aws"), "api.template.json": ("cfn", "aws"),
            "net.cfn.yml": ("cfn", "aws"), "cdk.out/S.template.json": ("cfn", "aws"), "k8s/app.json": ("by_text", "*"),
            "stack.yaml": ("by_text", "*"), "Procfile": (None, "*"), "app.py": (None, "*")}
    assert {r: (T.iac_kind(r), T.iac_provider(r)) for r in want} == want
    assert T.iac_kind_by_text("k8s/app.json", '{"apiVersion": "v1", "kind": "List", "items": []}') == "k8s"
    assert T.iac_kind_by_text("s.yaml", "Resources:   # the stack\n  Q:\n    Type: AWS::SQS::Queue\n") == "cfn"
    assert T.iac_kind_by_text("notes.yaml", "we use AWS::SQS::Queue\n") is None
    assert C.SKIP_DIRS is T.SKIP_DIRS and C._is_cfn is T.is_cfn          # the names seed imports today are the table's
    src = Path(C.__file__).read_text()
    for spelled in ("Resources[", "Resources\\\\s", "^apiVersion:", '".tofu"', "compose(?:", "wrangler\\\\.(?:", '"DerivedData"',
                    '".template.json"', '"template.yaml"'):
        assert spelled not in src, spelled


def test_a_template_named_so_is_aws_even_when_its_head_says_nothing(tmp_path, monkeypatch):
    """A *.cfn.yaml too big to read, whose first bytes hold no Resources: whose it is comes from its name."""
    monkeypatch.setattr(C, "MAX_BYTES", 200)
    monkeypatch.setattr(C, "HEAD_BYTES", 40)
    _r, rep = _mini(tmp_path, {"infra/net.cfn.yaml": "Description: " + "x" * 300 + "\nResources:\n  Q:\n    Type: AWS::SQS::Queue\n"},
                    [{"id": "q", "category": "queue", "provider": "aws", "iac": ["Q"]}])
    assert any("net.cfn.yaml" in w and "not read" in w for w in rep.target_extra["unverified"].get("aws", []))
    assert _by_target(rep)["aws/q"].status == "skipped"


def test_a_big_template_with_a_bom_is_known_by_its_head(tmp_path, monkeypatch):
    """Q2 in the head read too: a template over the size, a BOM first and no version line, is aws's (not read; its
    node skipped, never missing)."""
    monkeypatch.setattr(C, "MAX_BYTES", 200)
    r, _ = _mini(tmp_path, {"infra/main.tf": 'resource "aws_sqs_queue" "other" {}\n'}, [{"id": "q", "category": "queue", "provider": "aws", "iac": ["Q"]}])
    (r / "infra" / "stack.yaml").write_bytes(("\ufeffResources:\n  Q:\n    Type: AWS::SQS::Queue\n" + "#" * 300 + "\n").encode("utf-8"))
    rep = C.run_infra_iac(_decls(r)["iac"], r)
    assert any("stack.yaml" in w and "not read" in w for w in rep.target_extra["unverified"].get("aws", []))
    assert _by_target(rep)["aws/q"].status == "skipped"


def test_jsonc_keeps_an_escaped_quote_and_a_trailing_backslash_inside_a_string():
    """The independent fifth verification X1: a \\" inside a string does not end it, so a // or ,} after it is still text; a
    string ending in an escaped backslash ends at its quote. A comment between the last "," and the close is skipped
    when deciding that the "," is the last."""
    from jsonui_doc_cli.infra import iac_tables as T
    assert T.parse_jsonc('{"name": "a \\" // b", "x": "c \\" ,} d",}') == {"name": 'a " // b', "x": 'c " ,} d'}
    assert T.parse_jsonc('{"path": "C:\\\\", // the drive\n "n": 1,}') == {"path": "C:\\", "n": 1}
    # a last "," with a comment between it and the close (the generated file's own way of writing a list)
    assert T.parse_jsonc('{"a": [1, 2, // the last\n ], "b": 3, /* end */ }') == {"a": [1, 2], "b": 3}


# ---------------------------------------------------------------- a node's spec (ticket 2026-10-20-jui-viz-server-room-lines-dark-filter-spec §4)

def test_a_declared_spec_is_compared_with_the_values_the_iac_writes(tmp_path):
    tf = ('resource "aws_db_instance" "orders" {\n  instance_class = "db.t3.micro"\n  allocated_storage = 100\n'
          '  engine_version = var.v\n}\n')
    cfn = ('Resources:\n  Fn:\n    Type: AWS::Lambda::Function\n    Properties:\n      MemorySize: 1024\n'
           '      Runtime: !Ref Rt\n')
    spec_db = [{"key": "instance_class", "value": "db.r6g.large"}, {"key": "storage_gb", "value": "100"},
               {"key": "version", "value": "16"}, {"key": "owner", "value": "team-a"}]
    spec_fn = [{"key": "memory_mb", "value": "1024"}, {"key": "runtime", "value": "nodejs20.x"}]
    _r, rep = _mini(tmp_path, {"main.tf": tf, "cfn/template.yaml": cfn}, [
        {"id": "db", "category": "database.relational", "provider": "aws", "iac": ["aws_db_instance.orders"], "spec": spec_db},
        {"id": "fn", "category": "compute.function", "provider": "aws", "iac": ["Fn"], "spec": spec_fn}])
    t = _by_target(rep)
    assert t["aws/db"].status == "ok" and t["aws/fn"].status == "ok"
    differs = t["aws/db#spec.instance_class"]
    assert (differs.status, differs.expected, differs.actual) == ("mismatch", "db.r6g.large", "db.t3.micro")
    assert "main.tf" in differs.message
    assert [k for k in t if "#spec." in k] == ["aws/db#spec.instance_class"]   # storage the same; memory the same
    # version (a variable), owner (no table key), runtime (a !Ref): not compared, and said so
    assert any("3 declared spec value(s) not compared" in w for w in rep.warnings), rep.warnings


def test_a_spec_difference_is_a_warning_unless_gate(tmp_path):
    root, _rep = _mini(tmp_path, {"main.tf": 'resource "aws_instance" "w" {\n  instance_type = "t3.small"\n}\n'},
                       [{"id": "w", "category": "compute.vm", "provider": "aws", "iac": ["aws_instance.w"],
                         "spec": [{"key": "instance_type", "value": "t3.large"}]}])
    (root / "jui.config.json").write_text(json.dumps({"checks": [{"name": "iac", "type": "builtin:infra-iac"}]}))
    rep = C.run_infra_iac(_decls(root)["iac"], root)
    assert _by_target(rep)["aws/w#spec.instance_type"].status == "warning"


SECRET_RUNTIME = "postgres://admin:hunter2pass@db.internal:5432/app"


@pytest.mark.parametrize("files, iac", [
    ({"main.tf": f'resource "aws_lambda_function" "fn" {{\n  runtime = "{SECRET_RUNTIME}"\n}}\n'}, "aws_lambda_function.fn"),
    ({"cfn/template.yaml": f"Resources:\n  Fn:\n    Type: AWS::Lambda::Function\n    Properties:\n      Runtime: {SECRET_RUNTIME}\n"}, "Fn"),
])
def test_a_spec_value_read_from_iac_with_a_secret_shape_is_masked_in_every_field(tmp_path, files, iac):
    """A spec difference names the IaC's value (actual): one with a secret's shape is masked, in the result and in the
    report as a whole (the independent check found no arm on this path: a mutation not masking actual stayed green)."""
    _r, rep = _mini(tmp_path, files, [{"id": "fn", "category": "compute.function", "provider": "aws", "iac": [iac],
                                       "spec": [{"key": "runtime", "value": "python3.12"}]}])
    item = _by_target(rep)["aws/fn#spec.runtime"]
    assert item.status == "mismatch" and item.expected == "python3.12" and item.actual.startswith("<masked")
    dumped = json.dumps(rep.to_dict()) + "\n".join(rep.warnings)
    assert SECRET_RUNTIME not in dumped and "hunter2pass" not in dumped and "db.internal" not in dumped


# ---------------------------------------------------------------- the walk is seed's (ticket doc-infra-iac-scan-cap-reached-before-terraform)

def _data_folder_before_terraform(root: Path, n: int) -> None:
    """A gitignored folder of n JSON files that sorts before the Terraform, as a project's scraped data does."""
    (root / ".gitignore").write_text("backend/scripts/data/\n")
    data = root / "backend" / "scripts" / "data"
    data.mkdir(parents=True)
    for i in range(n):
        (data / f"item_{i:05d}.json").write_text("{}")


def test_a_data_folder_bigger_than_the_old_cap_does_not_hide_the_terraform(tmp_path):
    """check stopped at its 5,000th candidate (every JSON counted) before infrastructure/: the aws node was skipped
    with "no IaC read for aws" while seed, in the same project, read the Terraform."""
    root = tmp_path / "mini"
    root.mkdir()
    _data_folder_before_terraform(root, 5001)
    root2, rep = _mini(tmp_path, {"infrastructure/terraform/main.tf": 'resource "aws_db_instance" "main" {}\n'},
                       [{"id": "db", "category": "database.relational", "provider": "aws", "iac": ["aws_db_instance.main"]}])
    assert root2 == root
    assert _by_target(rep)["aws/db"].status == "ok"
    assert not rep.target_extra["unverified"].get("*")
    from jsonui_doc_cli.infra import seed as S
    model, _report = S.draft(root)
    assert "aws_db_instance.main" in json.dumps(model["nodes"])


def test_the_walk_cap_is_said_and_what_was_not_looked_at_is_not_said_missing(tmp_path, monkeypatch):
    """Reaching the cap is named — how many, and the folder the walk stopped in — and the files not looked at are
    unread: a node not found is skipped, not missing, and a provider with nothing read is not said to have none."""
    from jsonui_doc_cli.infra import iac_tables as T
    monkeypatch.setattr(T, "WALK_CAP", 50)
    root = tmp_path / "mini"
    root.mkdir()
    _data_folder_before_terraform(root, 60)
    assert T.git_ignored(root) is None     # no git here: the .gitignore is not read, the walk is as before
    _r, rep = _mini(tmp_path, {"infrastructure/terraform/main.tf": 'resource "aws_db_instance" "main" {}\n',
                               "admin/compose.yaml": "services:\n  web:\n    image: nginx\n"},   # read: before the stop
                    [{"id": "db", "category": "database.relational", "provider": "aws", "iac": ["aws_db_instance.main"]},
                     {"id": "app", "category": "compute.container", "provider": "docker", "iac": ["compose.yaml#services.app"]}])
    un = rep.target_extra["unverified"]
    assert any("more than 50 files" in w and "backend/scripts/data/" in w for w in un["*"])
    assert _by_target(rep)["aws/db"].status == "skipped"
    # docker's compose was read and has no "app": the unseen files may hold it (not only a Terraform address)
    assert _by_target(rep)["docker/app"].status == "skipped"
    assert not any("no IaC found" in w for w in un.get("aws", []))


def test_the_code_cap_is_seeds_and_is_said(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "MAX_CODE_FILES", 3)
    assert C.MAX_CODE_FILES != 5000
    root = tmp_path / "p"
    for i in range(5):
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "src" / f"m{i}.py").write_text("import os\n")
    _hints, notes = C.scan_code(root)
    assert any("more than 3 source files" in n and "src/m3.py" in n for n in notes)


def test_check_reads_iac_where_seed_reads_it(tmp_path):
    """One walk (iac_tables.walk_project): IaC under .github/ (the hidden folder seed keeps) and tmp/ (a folder seed
    reads only IaC in) is read by both; a hidden folder neither reads."""
    tpl = lambda n: f"AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  {n}:\n    Type: AWS::SQS::Queue\n"  # noqa: E731
    files = {".github/cfn/q.yaml": tpl("GhQueue"), "tmp/q.yaml": tpl("TmpQueue"), ".hidden/q.yaml": tpl("HiddenQueue")}
    root, rep = _mini(tmp_path, files, [
        {"id": "gh", "category": "queue", "provider": "aws", "iac": ["GhQueue"]},
        {"id": "tmp", "category": "queue", "provider": "aws", "iac": ["TmpQueue"]}])
    assert _by_target(rep)["aws/gh"].status == "ok" and _by_target(rep)["aws/tmp"].status == "ok"
    found, _un = C.scan_iac(root)
    assert not any("HiddenQueue" in f["address"] for f in found)
    from jsonui_doc_cli.infra import seed as S
    model, _report = S.draft(root)
    seen = json.dumps(model["nodes"])
    assert "GhQueue" in seen and "TmpQueue" in seen and "HiddenQueue" not in seen


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_what_git_ignores_neither_seed_nor_check_reads(tmp_path):
    """walk_project leaves out what git ignores — fetched modules in .terraform/, an import's output — for seed and
    check alike; a tracked file in an ignored folder and an untracked one that is not ignored are still read."""
    tpl = lambda n: f"AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  {n}:\n    Type: AWS::SQS::Queue\n"  # noqa: E731
    files = {".gitignore": "out/\n.terraform/\ndata/\n", "data/q.yaml": tpl("DataQueue"),
             "out/q.yaml": tpl("IgnoredQueue"), "out/kept.yaml": tpl("TrackedQueue"),
             "infra/.terraform/modules/m/main.tf": 'resource "aws_s3_bucket" "fetched" {}\n',
             "infra/main.tf": 'resource "aws_db_instance" "main" {}\n', "new/q.yaml": tpl("NewQueue")}
    root = tmp_path / "mini"
    root.mkdir()
    _git(root, "init", "-q")
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    _git(root, "add", "-f", "out/kept.yaml")
    from jsonui_doc_cli.infra import iac_tables as T
    assert {"out/q.yaml", "infra/.terraform/", "data/"} <= T.git_ignored(root)
    found, _un = C.scan_iac(root)
    addresses = {f["address"] for f in found}
    assert {"TrackedQueue", "NewQueue", "aws_db_instance.main"} <= addresses
    assert not {"IgnoredQueue", "DataQueue", "aws_s3_bucket.fetched"} & addresses
    from jsonui_doc_cli.infra import seed as S
    model, _report = S.draft(root)
    seen = json.dumps(model["nodes"])
    assert "TrackedQueue" in seen and "NewQueue" in seen and "IgnoredQueue" not in seen and "DataQueue" not in seen
    assert "fetched" not in seen


def test_code_only_in_a_folder_seed_reads_only_iac_in_is_no_evidence(tmp_path):
    """tmp/ and coverage/ (a copy, instrumented code): seed reads only IaC there, and check's infra-code does not count
    an SDK client made only there."""
    root = tmp_path / "p"
    for rel in ("tmp/copy.py", "coverage/lcov/app.py"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text('import boto3\ns3 = boto3.client("s3")\n')
    hints, _notes = C.scan_code(root)
    assert hints == []
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text('import boto3\ns3 = boto3.client("s3")\n')
    hints, _notes = C.scan_code(root)
    assert {h["file"] for h in hints} == {"src/app.py"}


@pytest.mark.parametrize("under, git_says", [("scratch", {"./"}), ("scratch/proj", None)])
def test_a_project_inside_a_folder_its_parent_repo_ignores_is_still_read(tmp_path, under, git_says):
    """A project copied under a folder its parent repo ignores: git says only "./" when the root is the ignored folder,
    and fails ("directory entry not superset of prefix") when it is deeper. Either way no file under it is left out."""
    outer = tmp_path / "outer"
    root = outer / under
    root.mkdir(parents=True)
    _git(outer, "init", "-q")
    (outer / ".gitignore").write_text("scratch/\n")
    (root / "main.tf").write_text('resource "aws_db_instance" "main" {}\n')
    from jsonui_doc_cli.infra import iac_tables as T
    assert T.git_ignored(root) == git_says
    found, _un = C.scan_iac(root)
    assert "aws_db_instance.main" in {f["address"] for f in found}
