"""Seed (`jsonui-doc seed infra`, infra/seed.py): a draft of a room's infra model from IaC, config files and code.

The draft must be a model the room accepts (model.check_file and model.merge give no error), hold no value (no ARN,
account id, IP address or CIDR block, connection string, key), never come from a file that holds values (Terraform
state and variables, .env), say per provider what it could not match, give each node its own provider across a
multi-provider project, and compare clean with `check kind=infra`, which reads the same table (iac_tables.py); what
check still asks of a draft is listed (REMAINING_GAP, docs/bugs/2026-10-20-jui-infra-seed-and-check-tables-disagree.md).

The two example projects are under tests/fixtures/infra_seed; the files that hold values are written into a copy at
test time (never kept in the repository).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import re

from jsonui_doc_cli.check import infra_check as IC
from jsonui_doc_cli.infra import code_hints as C
from jsonui_doc_cli.infra import iac_tables as T
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra import room as R
from jsonui_doc_cli.infra import seed as S

FIX = Path(__file__).resolve().parent / "fixtures" / "infra_seed"
TOOLS = Path(__file__).resolve().parents[1]

# The files that hold values: the project has them, seed never reads them. Each carries a sentinel that must not
# appear anywhere in the output.
VALUE_FILES = {
    "infra/terraform.tfstate": json.dumps({"version": 4, "resources": [{
        "mode": "managed", "type": "aws_sqs_queue", "name": "only_in_state",
        "instances": [{"attributes": {"arn": "arn:aws:sqs:ap-northeast-1:123456789012:only-in-state",
                                      "private_ip": "10.0.1.23"}}]}]}),
    "infra/terraform.tfstate.backup": json.dumps({"version": 4, "resources": [{"type": "aws_sqs_queue", "name": "only_in_state"}]}),
    "infra/prod.tfvars": 'db_password = "only-in-tfvars"\n',
    "api/.env": "DATABASE_URL=postgres://app:only-in-dotenv@10.0.1.23:5432/app\nONLY_IN_DOTENV_S3_BUCKET=x\n",
}
SENTINELS = ("only_in_state", "only-in-state", "only-in-tfvars", "only-in-dotenv", "ONLY_IN_DOTENV")


def _project(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    shutil.copytree(FIX / name, root)
    if name == "multi-cloud":
        for rel, text in VALUE_FILES.items():
            (root / rel).write_text(text)
    return root


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _by_iac(doc: dict) -> dict[str, dict]:
    return {a: n for n in doc["nodes"] for a in n.get("iac") or []}


# ---------------------------------------------------------------- the draft is a model the room accepts

@pytest.mark.parametrize("name", ["multi-cloud", "mixed-config"])
def test_the_draft_passes_the_models_own_check(tmp_path, name):
    doc, _rep = S.draft(_project(tmp_path, name))
    raw = json.dumps(doc).encode()
    data, problems = M.check_file("draft.json", raw)
    assert M.errors(problems) == [] and data is not None
    model, merged = M.merge([("draft.json", raw)])
    assert merged == []      # no problem of any severity: environments too (an edge, a node, a group inside what holds it)
    assert len(model["nodes"]) == len(doc["nodes"]) >= 20 and len(model["edges"]) == len(doc["edges"]) >= 10
    assert all(n.get("evidence") for n in doc["nodes"]), "every node says where it came from"


# ---------------------------------------------------------------- no value leaves

@pytest.mark.parametrize("name", ["multi-cloud", "mixed-config"])
def test_no_value_reaches_the_draft_or_the_report(tmp_path, name):
    root = _project(tmp_path, name)
    if name == "multi-cloud":   # the premise: the inputs do hold values (a CIDR block in the HCL)
        assert "ip_address" in M.secret_findings((root / "infra/main.tf").read_text())
    doc, rep = S.draft(root)
    found = {s: M.secret_findings(s) for s in _strings(doc) if M.secret_findings(s)}
    found.update({s: M.secret_findings(s) for s in _strings(rep) if M.secret_findings(s)})
    assert found == {}


def test_a_draft_that_fails_its_own_check_is_not_written(tmp_path, monkeypatch):
    root = _project(tmp_path, "mixed-config")
    real = S.draft

    def leaky(*a, **k):
        doc, rep = real(*a, **k)
        doc["nodes"][0]["label"] = "10.0.0.0/16"
        return doc, rep
    monkeypatch.setattr(S, "draft", leaky)
    errs: list[str] = []
    assert S.run(root, echo=lambda s: None, err=errs.append) == 2
    assert not (root / "docs" / "infra").exists()
    assert any("secret.ip_address" in e for e in errs) and not any("10.0.0.0" in e for e in errs)


# ---------------------------------------------------------------- files that hold values are never read

def test_state_variables_and_env_files_are_never_read(tmp_path, monkeypatch):
    root = _project(tmp_path, "multi-cloud")
    read: list[str] = []
    real = S.read_text

    def watch(path):
        read.append(Path(path).name)
        return real(path)
    monkeypatch.setattr(S, "read_text", watch)
    doc, rep = S.draft(root)
    assert "main.tf" in read and ".env.example" in read            # the watch sees the reads
    assert not [n for n in read if ".tfstate" in n or n.endswith(".tfvars") or n == ".env"]
    out = json.dumps([doc, rep])
    assert not [s for s in SENTINELS if s in out]
    skipped = {s["file"] for s in rep["skipped"]}
    assert skipped == {"infra/terraform.tfstate", "infra/terraform.tfstate.backup", "infra/prod.tfvars", "api/.env"}


# ---------------------------------------------------------------- what could not be matched is said, per provider

EXPECTED_UNMATCHED = {
    "multi-cloud": {("aws", "aws_quantumledger_widget.mystery"), ("terraform", "module.cdn"),
                    ("cloudflare", "wrangler ai"), ("(unknown)", "WEIRD_SERVICE_URL")},
    "mixed-config": {("aws", "Gadget (AWS::Gizmo::Gadget)"), ("azure", "odd (microsoft.contoso/widgets)"),
                     ("kubernetes", "Rollout/canary"), ("kubernetes", "charts/web/Chart.yaml"),
                     ("kubernetes", "charts/web/templates/deployment.yaml"), ("pulumi", "Pulumi.yaml"),
                     ("(unknown)", "Procfile"), ("firebase", "unknownProduct")},
}


@pytest.mark.parametrize("name", ["multi-cloud", "mixed-config"])
def test_what_could_not_be_matched_is_reported_per_provider(tmp_path, name):
    _doc, rep = S.draft(_project(tmp_path, name))
    got = {(p, i["what"]) for p, v in rep["unmatched"].items() for i in v["items"]}
    assert got == EXPECTED_UNMATCHED[name]
    assert all(v["count"] == len(v["items"]) for v in rep["unmatched"].values())
    if name == "multi-cloud":   # a part of another resource is counted, not drawn — and not silently gone
        assert rep["notDrawn"]["aws"] == {"aws_db_subnet_group": 1, "aws_route53_record": 1}
        assert rep["notDrawn"]["terraform"] == {"random_id": 1}


# ---------------------------------------------------------------- each node its own provider, edges across them

def test_each_node_has_its_own_provider_across_a_multi_provider_project(tmp_path):
    doc, _rep = S.draft(_project(tmp_path, "multi-cloud"))
    by_iac = _by_iac(doc)
    want = {"aws_db_instance.orders": "aws", "aws_ecs_service.api": "aws", "aws_lb.web": "aws",
            "google_cloud_run_v2_service.reports": "gcp", "google_sql_database_instance.reports": "gcp",
            "cloudflare_workers_script.edge": "cloudflare", "cloudflare_r2_bucket.assets": "cloudflare",
            "edge/wrangler.toml": "cloudflare", "edge/wrangler.toml#d1_databases.DB": "cloudflare"}
    assert {a: by_iac[a].get("provider") for a in want} == want
    by_label = {n["label"]: n for n in doc["nodes"]}
    code = {"stripe payments": "stripe", "openai api": "openai", "sentry errors": "sentry", "sendgrid email": "sendgrid",
            "vercel kv": "vercel", "aws sqs": "aws", "aws s3": "aws"}
    assert {k: by_label[k].get("provider") for k in code} == code
    assert by_label["web"]["provider"] == "vercel"
    # external services of several providers share one logical group (the boundary's cross-provider group)
    ext = {n["provider"] for n in doc["nodes"] if n.get("group") == "external"}
    assert ext >= {"stripe", "openai", "sentry", "sendgrid"} and next(
        g for g in doc["groups"] if g["id"] == "external")["kind"] == "logical"
    model, _ = M.merge([("draft.json", json.dumps(doc).encode())])
    cross = {(e["from"], e["to"]) for e in model["edges"] if e["crossProvider"]}
    worker, lb = by_iac["cloudflare_workers_script.edge"]["id"], by_iac["aws_lb.web"]["id"]
    assert (worker, lb) in cross                     # Cloudflare Worker -> AWS load balancer
    assert {n["providerResolved"] for n in model["nodes"]} >= {"aws", "gcp", "cloudflare", "vercel", "stripe", "openai"}


def test_compose_is_the_local_environment(tmp_path):
    doc, _rep = S.draft(_project(tmp_path, "mixed-config"))
    assert [e["id"] for e in doc["environments"]] == ["local", "deployed"]
    by_iac = _by_iac(doc)
    assert by_iac["docker-compose.yml#services.db"]["environments"] == ["local"]
    assert by_iac["docker-compose.yml#services.db"]["category"] == "database.relational"
    assert by_iac["Deployment/web"]["environments"] == ["deployed"]


# ---------------------------------------------------------------- the round trip with check kind=infra

# What check (infra-iac) still says of a seeded room taken as it is ("declared, but no such resource"), with seed and
# check reading the one table (iac_tables.py) and the one code-hint table (code_hints.py): nothing
# (docs/bugs/2026-10-20-jui-infra-seed-and-check-tables-disagree.md). A difference coming back is red here.
REMAINING_GAP: dict[str, set] = {"multi-cloud": set(), "mixed-config": set()}


@pytest.mark.parametrize("name", ["multi-cloud", "mixed-config"])
def test_a_seeded_room_compares_clean_with_check_where_check_sees(tmp_path, name):
    root = _project(tmp_path, name)
    doc, _rep = S.draft(root)
    (root / "docs" / "infra").mkdir(parents=True)
    (root / "docs" / "infra" / "draft.json").write_text(json.dumps(doc))
    decl = SimpleNamespace(gate=False, ignore_types=[])
    iac = IC.run_infra_iac(decl, root).results
    assert [r.target for r in iac if r.message and "category differs" in r.message] == []
    assert [r.target for r in iac if r.message and "no node names it" in r.message] == []
    ids = {n["id"]: n for n in doc["nodes"]}
    gap = {f"{t.split('/', 1)[0]}/{ids[t.split('/', 1)[1]]['iac'][0]}" for t in
           (r.target for r in iac if r.message and "no such resource" in r.message)}
    assert gap == REMAINING_GAP[name]
    assert sum(r.status == "ok" for r in iac) >= 8
    code = IC.run_infra_code(decl, root).results
    assert [(r.target, r.message) for r in code if r.status != "ok"] == []
    assert sum(r.status == "ok" for r in code) >= 20


# ---------------------------------------------------------------- a CDK logical id is a name, not a secret

CDK_ID_40 = "PaymentWebhookHandlerServiceRole3C1A9F2B"     # a construct path and 8 hex characters: 40 long


def test_a_cdk_logical_id_of_40_characters_is_drafted_and_accepted(tmp_path):
    """A synthesized CDK app names its resources by the construct path and a hash; 40 characters is common. Seed
    drafts the resource with that id as its iac address and evidence, and the model takes the file with no problem
    (an AWS secret key's shape is 40 base64 characters too, but with a "/" or "+", or after a secret key's name)."""
    root = _project(tmp_path, "mixed-config")
    assert len(CDK_ID_40) == 40 and CDK_ID_40 in (root / "cdk.out" / "AppStack.template.json").read_text()
    doc, rep = S.draft(root)
    node = _by_iac(doc)[CDK_ID_40]
    assert (node["provider"], node["category"]) == ("aws", "security.iam")
    assert {"file": "cdk.out/AppStack.template.json", "pattern": CDK_ID_40} == {k: node["evidence"][0][k] for k in ("file", "pattern")}
    assert rep["withheld"] == 0
    raw = json.dumps(doc).encode()
    assert M.check_file("draft.json", raw)[1] == []
    assert M.merge([("draft.json", raw)])[1] == []


# ---------------------------------------------------------------- the command

def _cli(*args):
    return subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "seed", "infra", *args], cwd=TOOLS,
                          capture_output=True, text=True, env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})


def test_the_command_writes_below_the_models_folder_and_never_over_a_draft(tmp_path):
    root = _project(tmp_path, "multi-cloud")
    r = _cli(str(root))
    assert r.returncode == 0, r.stderr
    draft = root / "docs" / "infra" / "seed" / "draft.json"
    rep = json.loads((root / "docs" / "infra" / "seed" / "seed-report.json").read_text())
    assert json.loads(draft.read_text())["nodes"] and rep["unmatched"]["aws"]["count"] == 1
    assert R.counts(root)["files"] == 0                # the draft is not the display's source
    assert "unmatched 4 (" in r.stdout
    before = draft.read_bytes()
    r2 = _cli(str(root))
    assert r2.returncode == 2 and "--force" in r2.stderr and draft.read_bytes() == before
    assert _cli(str(root), "--force").returncode == 0
    out = _cli(str(root), "--stdout")
    assert out.returncode == 0 and json.loads(out.stdout)["version"] == 0 and "seed infra:" in out.stderr


def test_the_configured_folder_is_used_and_a_bad_one_refused(tmp_path):
    root = _project(tmp_path, "mixed-config")
    (root / "jui.config.json").write_text(json.dumps({"infra": {"dir": "infra/model"}}))
    assert _cli(str(root)).returncode == 0 and (root / "infra" / "model" / "seed" / "draft.json").is_file()
    (root / "jui.config.json").write_text(json.dumps({"infra": {"dir": "../outside"}}))
    r = _cli(str(root))
    assert r.returncode == 2 and "bad_config" in r.stderr


def test_an_existing_declaration_is_kept_and_the_draft_names_what_it_lacks(tmp_path):
    root = _project(tmp_path, "multi-cloud")
    (root / "docs" / "infra").mkdir(parents=True)
    declared = {"version": 0, "nodes": [{"id": "db", "category": "database.relational", "provider": "aws",
                                         "iac": ["aws_db_instance.orders"]}]}
    main = root / "docs" / "infra" / "main.json"
    main.write_text(json.dumps(declared))
    before = main.read_bytes()
    assert S.run(root, echo=lambda s: None, err=lambda s: None) == 0
    assert main.read_bytes() == before
    rep = json.loads((root / "docs" / "infra" / "seed" / "seed-report.json").read_text())
    new = set(rep["declared"]["draftNodesNotDeclared"])
    assert "rds-orders" not in new and {"ecs-api", "elb-web", "run-reports"} <= new


# ---------------------------------------------------------------- a large configuration

def test_a_large_configuration_is_capped_at_the_models_limit_and_says_so(tmp_path):
    root = tmp_path / "big"
    (root / "infra").mkdir(parents=True)
    body = "".join(f'resource "aws_s3_bucket" "b{i}" {{\n  bucket = "b{i}"\n}}\n' for i in range(6000))
    (root / "infra" / "main.tf").write_text('provider "aws" {\n  region = "us-east-1"\n}\n' + body)
    t0 = time.monotonic()
    doc, rep = S.draft(root)
    took = time.monotonic() - t0
    assert len(doc["nodes"]) == 5000 and any("6000 nodes found" in n for n in rep["notes"])
    assert S.check_draft(doc) == []
    assert took < 30, took


# ---------------------------------------------------------------- one table: seed keeps none of its own

def test_seed_keeps_no_table_of_its_own():
    """What an IaC resource is comes from iac_tables.py, what code says from code_hints.py — the copies check reads.
    A table of seed's own, under a shared table's name or any other, would be a second answer again."""
    src = Path(S.__file__).read_text(encoding="utf-8")
    shared = [n for mod in (C, T) for n, v in vars(mod).items()
              if n.isupper() and isinstance(v, (dict, list, tuple, set, frozenset, re.Pattern))]
    assert len(shared) >= 20
    assert [n for n in shared if re.search(rf"^\s*{n}\s*[:=]", src, re.M)] == []
    shapes = {
        "an SDK or environment entry": r'\(\s*r?"[^"]+"\s*,\s*\(\s*"[^"]*"\s*,\s*"[a-z]+(?:\.[a-z_]+)?"\s*,\s*"[^"]*"\s*\)\s*\)',
        "an IaC type entry": r'"(?:[a-z0-9]+_[a-z0-9_]+|AWS::\w+::\w+|[Mm]icrosoft\.\w+/\w+)"\s*:\s*\(',
        "an IaC type name": r'"(?:aws|google|azurerm|azuread|cloudflare|vercel|digitalocean|kubernetes|helm|heroku|netlify)_[a-z0-9_]+"',
        "a CloudFormation or Bicep type": r'AWS::[A-Za-z0-9]+::|[Mm]icrosoft\.[A-Za-z]+/',
    }
    assert {k: re.findall(rx, src) for k, rx in shapes.items() if re.findall(rx, src)} == {}
