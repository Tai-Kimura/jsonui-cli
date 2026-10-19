"""The infra model v0 (the server room's boundary, docs/plans/2026-10-20-jui-viz-server-room-boundary.md).

The schema file is the one source of the vocabularies and limits; model.py walks it. The examples under
tests/fixtures/infra are what make_examples.py writes, the valid ones have no problem, and each invalid one is refused
for its own reason. A file holding a secret's shape never reaches the model. Files merge into one model per room:
environments by id, providers inherited from groups (a logical group gives none), crossProvider from the two ends.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import model as M

FIX = Path(__file__).resolve().parent / "fixtures" / "infra"


def _room(folder: Path):
    return M.merge([(f.name, f.read_bytes()) for f in sorted(folder.glob("*.json"))])


def _make():
    spec = importlib.util.spec_from_file_location("make_examples", FIX / "make_examples.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- the examples

def test_the_examples_are_what_the_generator_writes():
    mod = _make()
    for rel, data in mod.all_examples().items():
        want = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=1) + "\n"
        assert (FIX / rel).read_text(encoding="utf-8") == want, rel


@pytest.mark.parametrize("room, folder, envs, nodes, edges, cross", [
    ("aws-three-tier", "docs/infra", ["production", "staging"], 12, 10, 3),
    ("multi-provider", "docs/infra", ["production", "preview"], 11, 10, 5),
    ("compose-and-cloud", "infra/model", ["local", "production"], 7, 5, 0),
    ("large-multi-provider", "docs/infra", ["production", "staging"], 2000, 5000, 566),
])
def test_the_valid_examples(room, folder, envs, nodes, edges, cross):
    model, problems = _room(FIX / room / folder)
    assert problems == []
    assert [e["id"] for e in model["environments"]] == envs
    assert (len(model["nodes"]), len(model["edges"]), sum(e["crossProvider"] for e in model["edges"])) == (nodes, edges, cross)


def test_the_large_example_is_the_target_size_over_four_providers():
    model, _ = _room(FIX / "large-multi-provider" / "docs" / "infra")
    assert {n["providerResolved"] for n in model["nodes"]} == {"aws", "gcp", "azure", "cloudflare"}
    assert len(model["nodes"]) == 2000 and len(model["edges"]) == 5000


def test_the_compose_example_names_its_folder_and_icons_in_jui_config():
    cfg = json.loads((FIX / "compose-and-cloud" / "jui.config.json").read_text())
    assert cfg["infra"]["dir"] == "infra/model" and not (FIX / "compose-and-cloud" / "docs" / "infra").exists()
    for key, path in cfg["infra"]["icons"].items():
        assert key.split(":", 1)[0] in ("service", "provider", "category") and (FIX / "compose-and-cloud" / path).is_file()


# ---------------------------------------------------------------- environments, providers, folding

def test_environments_switch_and_default_to_all():
    model, _ = _room(FIX / "aws-three-tier" / "docs" / "infra")
    by = {n["id"]: n for n in model["nodes"]}
    assert by["db-prod"]["environments"] == ["production"] and by["db-stg"]["environments"] == ["staging"]
    assert by["cdn"]["environments"] == ["production", "staging"]          # left out: every environment


def test_a_model_without_environments_has_the_implicit_one():
    model, problems = M.merge([("a.json", json.dumps({"version": 0, "nodes": [{"id": "x", "category": "cache"}]}).encode())])
    assert problems == [] and model["environments"] == [M.IMPLICIT_ENV] and model["nodes"][0]["environments"] == ["default"]


def test_providers_are_inherited_and_a_logical_group_gives_none():
    model, _ = _room(FIX / "multi-provider" / "docs" / "infra")
    nodes = {n["id"]: n for n in model["nodes"]}
    groups = {g["id"]: g for g in model["groups"]}
    assert groups["shop"]["providerResolved"] == "" and groups["gcp-tokyo"]["providerResolved"] == "gcp"
    assert nodes["api"]["providerResolved"] == "cloudflare" and nodes["search"]["providerResolved"] == "gcp"
    assert nodes["browser"]["providerResolved"] == ""                      # no provider, no group
    edges = {(e["from"], e["to"]): e["crossProvider"] for e in model["edges"]}
    assert edges[("api", "kv")] is False and edges[("web", "api")] is True and edges[("r2", "backup")] is True
    assert edges[("browser", "web")] is False                              # an end with no provider is not a crossing


def test_iam_and_alarms_fold_by_default_and_fold_overrides():
    model, _ = _room(FIX / "aws-three-tier" / "docs" / "infra")
    fold = {n["id"]: n["fold"] for n in model["nodes"]}
    assert fold["api-role"] is True and fold["api-5xx"] is True and fold["api-prod"] is False
    m2, _ = M.merge([("a.json", json.dumps({"version": 0, "nodes": [
        {"id": "r", "category": "security.iam", "fold": False}, {"id": "c", "category": "cache", "fold": True}]}).encode())])
    assert [n["fold"] for n in m2["nodes"]] == [False, True]


# ---------------------------------------------------------------- what is refused

SINGLE = {
    "secret-arn.json": {"secret.arn"}, "secret-account-id.json": {"secret.account_id"},
    "secret-ip.json": {"secret.ip_address"}, "secret-connection-string.json": {"secret.connection_string"},
    "secret-url-credentials.json": {"secret.url_credentials"}, "secret-private-key.json": {"secret.private_key"},
    "secret-access-key.json": {"secret.access_key"}, "secret-token.json": {"secret.token"},
    "schema-unknown-field.json": {"schema"}, "schema-category.json": {"schema"}, "schema-version.json": {"schema"},
    "not-json.json": {"json"},
}


@pytest.mark.parametrize("name", sorted(SINGLE))
def test_each_invalid_file_is_refused_for_its_reason_and_left_out_whole(name):
    raw = (FIX / "invalid" / "single" / name).read_bytes()
    data, problems = M.check_file(name, raw)
    codes = {p["code"] for p in problems}
    assert data is None and SINGLE[name] <= codes, codes
    if name.startswith("secret-"):
        assert codes <= SINGLE[name] | {"secret.account_id"}            # an ARN carries an account id too
    model, _ = M.merge([(name, raw)])
    assert model["nodes"] == [] and model["groups"] == []
    assert set(SINGLE) == {f.name for f in (FIX / "invalid" / "single").glob("*.json")}


def test_a_problem_never_carries_the_value_it_found():
    for f in (FIX / "invalid" / "single").glob("secret-*.json"):
        data = json.loads(f.read_text())
        secrets = [v for _p, v in M._walk_strings(data, "") if M.secret_findings(v)]
        _d, problems = M.check_file(f.name, f.read_bytes())
        for p in problems:
            for v in secrets:
                assert v not in json.dumps(p, ensure_ascii=False), (f.name, p)


def test_a_secret_in_one_file_leaves_out_that_file_not_the_room():
    good = (FIX / "aws-three-tier" / "docs" / "infra" / "main.json").read_bytes()
    bad = json.dumps({"version": 0, "nodes": [{"id": "leak", "category": "cache", "label": "redis://cache.internal:6379"}]}).encode()
    model, problems = M.merge([("main.json", good), ("leak.json", bad)])
    assert "leak" not in {n["id"] for n in model["nodes"]} and model["files"] == ["main.json"]
    assert "redis://" not in json.dumps(model) and [p["code"] for p in problems] == ["secret.connection_string"]


def test_references_across_files():
    model, problems = _room(FIX / "invalid" / "refs" / "docs" / "infra")
    codes = sorted(p["code"] for p in problems)
    assert codes == ["edge.missing", "environment.conflict", "environment.missing", "group.cycle", "group.cycle",
                     "group.missing", "id.duplicate"], codes
    assert model["edges"] == [] and [n["id"] for n in model["nodes"]] == ["api"] and "group" not in model["nodes"][0]
    assert all("parent" not in g for g in model["groups"])                 # the cycle is cut


@pytest.mark.parametrize("text, kinds", [
    ("arn:aws:s3:::bucket", {"arn"}), ("arn:aws-cn:iam::role", {"arn"}), ("postgresql://h/db", {"connection_string"}),
    ("mongodb+srv://c.example/x", {"connection_string"}), ("Server=tcp:x;Password=y", {"connection_string"}),
    ("https://u:p@h", {"url_credentials"}), ("ASIAABCDEFGHIJKLMNOP", {"access_key"}), ("ghp_" + "a" * 36, {"token"}),
    ("eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.sig", {"token"}), ("192.168.0.1", {"ip_address"}), ("10.0.0.0/16", {"ip_address"}),
    ("-----BEGIN PRIVATE KEY-----", {"private_key"}), ("998877665544", {"account_id"}),
    ("mysql 8.4", set()), ("v1.2.3", set()), ("ap-northeast-1", set()), ("https://example.com/docs", set()),
    ("postgres 17", set()), ("Cloud SQL (Postgres)", set()), ("port 5432", set()), ("1.2.3.4.5", set()),
])
def test_the_secret_shapes(text, kinds):
    assert set(M.secret_findings(text)) == kinds


# ---------------------------------------------------------------- the schema is the one source

def test_the_vocabularies_come_from_the_schema_file(monkeypatch):
    schema = copy.deepcopy(M.schema())
    schema["$defs"]["category"]["enum"].append("quantum.annealer")
    monkeypatch.setattr(M, "_SCHEMA", [schema])
    raw = json.dumps({"version": 0, "nodes": [{"id": "q", "category": "quantum.annealer"}]}).encode()
    assert M.check_file("a.json", raw)[1] == []
    monkeypatch.setattr(M, "_SCHEMA", [])
    assert [p["code"] for p in M.check_file("a.json", raw)[1]] == ["schema"]


def test_the_room_keeps_the_limits_across_files():
    cap = M.schema()["properties"]["nodes"]["maxItems"]
    files = [(f"f{i}.json", json.dumps({"version": 0, "nodes": [{"id": f"n{i}-{k}", "category": "cache"}
                                                               for k in range(cap // 2 + 1)]}).encode()) for i in range(2)]
    model, problems = M.merge(files)
    assert len(model["nodes"]) == cap and [p["code"] for p in problems] == ["model.too_big"]
