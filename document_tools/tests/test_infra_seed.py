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
    # each of these is counted in skipped too (not only left unread): a missing count is red
    "infra/x.tfvars.json": json.dumps({"db_password": "only-in-tfvars"}),
    "infra/plan.tfplan": "only-in-state",
    "infra/terraform.tfstate.1700000000.backup": json.dumps({"resources": [{"name": "only_in_state"}]}),
    "api/.env.production.local": "ONLY_IN_DOTENV_A=1\n",
    "api/secrets.env": "ONLY_IN_DOTENV_B=1\n",
    "api/.envrc": "export ONLY_IN_DOTENV_C=1\n",
    "Pulumi.prod.yaml": "config:\n  app:dbPassword: only-in-tfvars\n",
    "charts/values.yaml": "password: only-in-tfvars\n",
    "infra/credentials.json": json.dumps({"secret": "only-in-tfvars"}),
}
SENTINELS = ("only_in_state", "only-in-state", "only-in-tfvars", "only-in-dotenv", "ONLY_IN_DOTENV")


def _project(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    shutil.copytree(FIX / name, root)
    if name == "multi-cloud":
        for rel, text in VALUE_FILES.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
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
    assert not set(read) & {Path(r).name for r in VALUE_FILES}
    out = json.dumps([doc, rep])
    assert not [s for s in SENTINELS if s in out]
    skipped = {s["file"] for s in rep["skipped"]}
    assert skipped == set(VALUE_FILES) and rep["skippedCount"] == len(VALUE_FILES)


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


# ---------------------------------------------------------------- value-shaped names: masked where they are, the rest drafted

# A room whose names and folders have a value's shape (an account id as a folder, an IP in a resource or service
# name, a version that is an IP). Written at test time; none of these strings may reach the draft or the report.
VALUE_NAMED = {
    "accounts/123456789012/main.tf": 'provider "aws" {\n  region = "us-east-1"\n}\n\n'
                                     'resource "aws_sqs_queue" "q_123456789012" {}\n\n'
                                     'resource "aws_sqs_queue" "jobs" {}\n\n'
                                     'resource "aws_db_instance" "orders" {\n  engine         = "postgres"\n'
                                     '  engine_version = "10.0.0.5"\n}\n',
    "edge/wrangler.toml": 'name = "edge"\nmain = "src/index.ts"\n\n[[services]]\nbinding = "PEER"\nservice = "svc-10.0.0.5"\n',
    "ops/10.0.0.5/compose.yml": "services:\n  cache:\n    image: redis:7\n",
    "api/pyproject.toml": "[project]\nname = 'api'\n",
    "api/app.py": 'import os\n\nBUCKET = os.getenv("S3_BUCKET_10_0_0_5")\nREDIS = os.getenv("REDIS_10_0_0_5_URL")\n',
    "10.0.0.5/.env": "X=1\n",
    "envs/123456789012/Pulumi.yaml": "name: x\nruntime: python\n",
}
VALUE_MARKS = ("123456789012", "10.0.0.5", "10_0_0_5")


def _value_named_room(tmp_path: Path) -> Path:
    root = tmp_path / "value-named"
    for rel, text in VALUE_NAMED.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def _leaks(value) -> list[str]:
    return [s for s in _strings(value) if M.secret_findings(s) or S.value_shaped(s) or any(m in s for m in VALUE_MARKS)]


def test_value_shaped_names_are_masked_in_the_draft_and_the_rest_is_drafted(tmp_path):
    """The masking itself, read off the draft (not left to the last gate, check_draft): an id, a label, an iac
    address, an evidence file or pattern, an engine with a value's shape never reaches the draft; the rest of the room
    is still drafted (one such name does not stop the whole draft)."""
    root = _value_named_room(tmp_path)
    doc, rep = S.draft(root)
    assert _leaks(doc) == []
    assert S.check_draft(doc) == []
    by_iac = _by_iac(doc)
    assert {"aws_sqs_queue.jobs", "aws_db_instance.orders", "edge/wrangler.toml"} <= set(by_iac)
    assert by_iac["aws_db_instance.orders"].get("engine") is None          # "postgres 10.0.0.5" is withheld
    ids = {n["id"] for n in doc["nodes"]}
    assert {"withheld", "withheld-2"} <= ids                                 # q_123456789012 and svc-10.0.0.5
    queue = next(n for n in doc["nodes"] if n["id"] in ("withheld", "withheld-2") and n["category"].startswith("queue"))
    assert queue["provider"] == "aws" and "iac" not in queue
    worker = by_iac["edge/wrangler.toml"]["id"]
    assert any(e["from"] == worker and e["to"].startswith("withheld") for e in doc["edges"])
    cache = next(n for n in doc["nodes"] if n["id"] == "compose-cache")
    assert "evidence" not in cache and "iac" not in cache                    # its file is ops/10.0.0.5/compose.yml
    app_hits = [e for n in doc["nodes"] for e in n.get("evidence") or [] if e["file"] == "api/app.py"]
    assert app_hits and all("10_0_0_5" not in (e.get("pattern") or "") for e in app_hits)
    assert rep["withheld"] >= 8


def test_the_report_says_where_each_withheld_string_was_and_masks_only_the_value(tmp_path):
    root = _value_named_room(tmp_path)
    assert S.run(root, echo=lambda s: None, err=lambda s: None) == 0       # written: one value-shaped name stops nothing
    raw = (root / "docs" / "infra" / "seed" / "seed-report.json").read_text()
    rep = json.loads(raw)
    assert _leaks(rep) == [] and not any(m in raw for m in VALUE_MARKS)
    where = {(w["file"], w.get("line"), w["what"]) for w in rep["withheldFrom"]}
    assert ("accounts/(withheld)/main.tf", 5, "an id") in where
    assert ("accounts/(withheld)/main.tf", 9, "engine") in where           # the line of its resource block
    assert {("ops/(withheld)/compose.yml", "the file's path (evidence)"), ("ops/(withheld)/compose.yml", "an iac address"),
            ("api/app.py", "an evidence pattern")} <= {(f, w) for f, _l, w in where}
    assert ("edge/wrangler.toml", 6, "an id") in where
    assert rep["withheldFromCount"] == len(rep["withheldFrom"])
    assert {s["file"] for s in rep["skipped"]} == {"(withheld)/.env"}
    assert ("pulumi", "envs/(withheld)/Pulumi.yaml", "envs/(withheld)/Pulumi.yaml") in {
        (p, i["file"], i["what"]) for p, v in rep["unmatched"].items() for i in v["items"]}


def test_a_region_with_a_values_shape_is_not_a_group(tmp_path):
    root = tmp_path / "region"
    (root / "infra").mkdir(parents=True)
    (root / "infra" / "main.tf").write_text('provider "aws" {\n  region = "123456789012"\n}\n\n'
                                            'resource "aws_sqs_queue" "jobs" {}\n')
    assert S.REGION_RX.match("123456789012")                # the premise: the shape check is what stops it
    doc, _rep = S.draft(root)
    assert _leaks(doc) == [] and S.check_draft(doc) == []
    assert [g["kind"] for g in doc["groups"]] == ["account"]
    assert _by_iac(doc)["aws_sqs_queue.jobs"]["group"] == doc["groups"][0]["id"]


# ---------------------------------------------------------------- symlinks: never read through, never written through

def test_an_input_that_is_a_symlink_is_skipped_not_read(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.tf").write_text('resource "aws_sqs_queue" "outside_q" {}\n')
    root = tmp_path / "room"
    (root / "infra").mkdir(parents=True)
    (root / "infra" / "main.tf").write_text('resource "aws_sqs_queue" "inside_q" {}\n')
    (root / "infra" / "link.tf").symlink_to(outside / "x.tf")
    doc, rep = S.draft(root)
    assert "aws_sqs_queue.inside_q" in _by_iac(doc) and "aws_sqs_queue.outside_q" not in _by_iac(doc)
    assert {s["file"] for s in rep["skipped"]} == {"infra/link.tf"}


def _symlinked_out(tmp_path: Path, how: str) -> tuple[Path, Path]:
    root = _project(tmp_path, "mixed-config")
    outside = tmp_path / "outside"
    outside.mkdir()
    seed = root / "docs" / "infra" / "seed"
    if how == "file":                    # seed/draft.json -> a file outside, not there yet
        seed.mkdir(parents=True)
        (seed / "draft.json").symlink_to(outside / "draft.json")
    elif how == "existing":              # seed/draft.json -> a file outside that is there (--force must not follow it)
        seed.mkdir(parents=True)
        (outside / "draft.json").write_text("keep")
        (seed / "draft.json").symlink_to(outside / "draft.json")
    elif how == "folder":                # seed -> a folder outside
        seed.parent.mkdir(parents=True)
        seed.symlink_to(outside, target_is_directory=True)
    elif how == "docs":                  # docs -> a folder outside (a part on the way)
        root.joinpath("docs").symlink_to(outside, target_is_directory=True)
    return root, outside


@pytest.mark.parametrize("how", ["file", "existing", "folder", "docs"])
@pytest.mark.parametrize("force", [False, True])
def test_the_draft_is_never_written_through_a_symlink(tmp_path, how, force):
    root, outside = _symlinked_out(tmp_path, how)
    before = {p.relative_to(outside).as_posix(): p.read_bytes() for p in outside.rglob("*") if p.is_file()}
    errs: list[str] = []
    assert S.run(root, force=force, echo=lambda s: None, err=errs.append) == 2
    after = {p.relative_to(outside).as_posix(): p.read_bytes() for p in outside.rglob("*") if p.is_file()}
    assert after == before
    assert any("nothing written" in e for e in errs)


def test_an_out_folder_outside_the_room_is_written_and_its_symlink_refused(tmp_path):
    root = _project(tmp_path, "mixed-config")
    out = tmp_path / "elsewhere" / "seed"
    assert S.run(root, out_dir=out, echo=lambda s: None, err=lambda s: None) == 0
    assert (out / "draft.json").is_file() and (out / "seed-report.json").is_file()
    link = tmp_path / "linked"
    link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert S.run(root, out_dir=link, force=True, echo=lambda s: None, err=lambda s: None) == 2


# ---------------------------------------------------------------- inputs check reads, seed reads too (the round trip)

READ_BY_BOTH = {
    "infra/main.tofu": 'resource "aws_sqs_queue" "tofu_q" {}\n',
    "k8s/app.json": json.dumps({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "json-web"},
                                "spec": {"template": {"metadata": {"labels": {"app": "w"}}}}}),
    "k8s/list.json": json.dumps({"apiVersion": "v1", "kind": "List", "items": [
        {"apiVersion": "apps/v1", "kind": "StatefulSet", "metadata": {"name": "listed-db"}, "spec": {}}]}),
    "infra/stack.json": json.dumps({"Resources": {"JsonQueue": {"Type": "AWS::SQS::Queue"}}}),
    "cfn/stack.yaml": "Resources:   # the stack\n  CommentedTopic:\n    Type: AWS::SNS::Topic\n",
    "tmp/extra.tf": 'resource "aws_sqs_queue" "tmp_q" {}\n',
}


def test_the_inputs_check_reads_are_drafted_and_compare_clean(tmp_path):
    root = tmp_path / "both"
    for rel, text in READ_BY_BOTH.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    doc, _rep = S.draft(root)
    assert {"aws_sqs_queue.tofu_q", "Deployment/json-web", "StatefulSet/listed-db", "JsonQueue", "CommentedTopic",
            "aws_sqs_queue.tmp_q"} <= set(_by_iac(doc))
    assert S.check_draft(doc) == []
    (root / "docs" / "infra").mkdir(parents=True)
    (root / "docs" / "infra" / "draft.json").write_text(json.dumps(doc))
    iac = IC.run_infra_iac(SimpleNamespace(gate=False, ignore_types=[]), root).results
    assert [(r.target, r.message) for r in iac if r.status != "ok" and r.status != "skipped"] == []
    assert sum(r.status == "ok" for r in iac) == 6


def test_code_is_not_read_under_a_folder_seed_reads_only_iac_in(tmp_path):
    root = tmp_path / "scratch"
    (root / "tmp").mkdir(parents=True)
    (root / "tmp" / "probe.py").write_text("import stripe\n")
    (root / "tmp" / "extra.tf").write_text('resource "aws_sqs_queue" "tmp_q" {}\n')
    doc, _rep = S.draft(root)
    assert {n.get("provider") for n in doc["nodes"]} == {"aws"}


def test_a_commented_wrangler_jsonc_is_read_by_the_shared_reader_and_compares_clean(tmp_path):
    """wrangler.jsonc as `npm create cloudflare` writes it (a block comment on top, a line comment after a value, a ","
    after the last item) read by iac_tables.parse_jsonc, the reader check uses too: a ",}" inside a string is text."""
    root = tmp_path / "cf"
    root.mkdir()
    (root / "wrangler.jsonc").write_text(
        '/**\n * For more details on how to configure Wrangler, refer to:\n * https://developers.cloudflare.com/\n */\n'
        '{\n  "name": "edge,}", // the worker\n  "main": "src/index.ts",\n'
        '  "kv_namespaces": [{ "binding": "CACHE" },],\n}\n')
    doc, _rep = S.draft(root)
    by_iac = _by_iac(doc)
    assert by_iac["wrangler.jsonc"]["label"] == "edge,}"
    assert "wrangler.jsonc#kv_namespaces.CACHE" in by_iac
    (root / "docs" / "infra").mkdir(parents=True)
    (root / "docs" / "infra" / "draft.json").write_text(json.dumps(doc))
    iac = IC.run_infra_iac(SimpleNamespace(gate=False, ignore_types=[]), root).results
    assert [(r.target, r.status) for r in iac if r.status != "ok"] == [] and sum(r.status == "ok" for r in iac) == 2


def test_seed_withholds_a_name_exactly_when_the_model_says_it_is_a_value(tmp_path):
    """One rule (model.secret_findings) for the model, check and seed: an IPv4 address written with "_" inside an
    environment name is withheld; build_1_2_3_4, which the model decided is not a value, is drafted as it is."""
    assert M.secret_findings("REDIS_10_0_0_5_URL") and not M.secret_findings("build_1_2_3_4")   # the model's decision
    root = tmp_path / "names"
    (root / "infra").mkdir(parents=True)
    (root / "infra" / "main.tf").write_text('resource "aws_sqs_queue" "build_1_2_3_4" {}\n')
    (root / "api").mkdir()
    (root / "api" / "pyproject.toml").write_text("[project]\nname = 'api'\n")
    (root / "api" / "app.py").write_text('import os\n\nREDIS = os.getenv("REDIS_10_0_0_5_URL")\n')
    doc, rep = S.draft(root)
    node = _by_iac(doc)["aws_sqs_queue.build_1_2_3_4"]
    assert node["id"] == "sqs-build_1_2_3_4" and node["label"].startswith("build_1_2_3_4")
    assert "10_0_0_5" not in json.dumps([doc, rep])
    assert [s for s in _strings([doc, rep]) if M.secret_findings(s)] == []
    assert S.check_draft(doc) == []


# ---------------------------------------------------------------- a node's spec (ticket 2026-10-20-jui-viz-server-room-lines-dark-filter-spec §4)

SPEC_TF = '''provider "aws" {
  region = "ap-northeast-1"
}
resource "aws_db_instance" "orders" {
  engine            = "postgres"
  engine_version    = var.pg_version
  instance_class    = "db.r6g.large"
  allocated_storage = 100
  multi_az          = true
  storage_type      = "${var.kind}"
}
resource "aws_lambda_function" "resize" {
  runtime     = "python3.12"
  memory_size = 512
  timeout     = local.t
}
resource "aws_instance" "bastion" {
  instance_type = "10.0.0.5"
}
'''
SPEC_CFN = '''AWSTemplateFormatVersion: "2010-09-09"
Resources:
  Cache:
    Type: AWS::ElastiCache::CacheCluster
    Properties:
      CacheNodeType: cache.t4g.small
      NumCacheNodes: 2
      EngineVersion: !Ref CacheVersion
'''


def _spec_project(tmp_path):
    root = tmp_path / "spec-room"
    (root / "infra").mkdir(parents=True)
    (root / "infra" / "main.tf").write_text(SPEC_TF)
    (root / "cfn").mkdir()
    (root / "cfn" / "template.yaml").write_text(SPEC_CFN)
    return root


def test_seed_drafts_a_spec_from_the_values_the_iac_writes_and_nothing_else(tmp_path):
    doc, rep = S.draft(_spec_project(tmp_path))
    by = _by_iac(doc)
    assert by["aws_db_instance.orders"]["spec"] == [
        {"key": "instance_class", "value": "db.r6g.large"}, {"key": "storage_gb", "value": "100"},
        {"key": "multi_az", "value": "true"}]                            # var.pg_version and "${var.kind}" not evaluated
    assert by["aws_lambda_function.resize"]["spec"] == [{"key": "memory_mb", "value": "512"}, {"key": "runtime", "value": "python3.12"}]
    assert by["Cache"]["spec"] == [{"key": "node_type", "value": "cache.t4g.small"}, {"key": "nodes", "value": "2"}]   # !Ref not
    assert "spec" not in by["aws_instance.bastion"]                     # its one value has a secret's shape: withheld
    assert rep["specValues"] == 7 and rep["withheld"] >= 1
    assert "10.0.0.5" not in json.dumps(doc) and "10.0.0.5" not in json.dumps(rep)
    raw = json.dumps(doc).encode()
    assert M.check_file("draft.json", raw)[1] == []


def test_a_seeded_spec_compares_clean_with_check(tmp_path):
    root = _spec_project(tmp_path)
    doc, _rep = S.draft(root)
    (root / "docs" / "infra").mkdir(parents=True)
    (root / "docs" / "infra" / "draft.json").write_text(json.dumps(doc))
    iac = IC.run_infra_iac(SimpleNamespace(gate=False, ignore_types=[]), root).results
    assert [r.target for r in iac if "#spec." in r.target] == []
