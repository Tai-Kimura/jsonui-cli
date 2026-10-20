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


def test_every_example_file_is_in_the_repository():
    """A fixture room has a project root's shape (<room>/docs/infra), and the root .gitignore drops docs/ at any
    depth: the examples were on disk and green here, and missing from a fresh checkout (ticket
    2026-10-20-jui-infra-fixtures-under-docs-not-committed). Every file make_examples.py writes must be tracked and not
    ignored; nothing generated (__pycache__) may be."""
    import shutil
    import subprocess
    repo = FIX.parents[3]
    if shutil.which("git") is None or not (repo / ".git").exists():
        pytest.skip("not a git checkout")
    rels = [f"document_tools/tests/fixtures/infra/{rel}" for rel in _make().all_examples()]
    ignored = subprocess.run(["git", "check-ignore", "--no-index", *rels], cwd=repo, capture_output=True, text=True).stdout.split()
    assert ignored == [], f"ignored by .gitignore: {ignored}"
    tracked = set(subprocess.run(["git", "ls-files", "document_tools/tests/fixtures/infra"], cwd=repo,
                                 capture_output=True, text=True, check=True).stdout.split())
    assert sorted(set(rels) - tracked) == [], "written by make_examples.py but not in the repository"
    assert [t for t in tracked if "__pycache__" in t or t.endswith(".pyc")] == []


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
    # a logical group inside a provider's account still gives what it holds no provider
    m2, _ = M.merge([("a.json", json.dumps({"version": 0, "groups": [
        {"id": "acct", "kind": "account", "provider": "aws"}, {"id": "tier", "kind": "logical", "parent": "acct"}],
        "nodes": [{"id": "n", "category": "cache", "group": "tier"}]}).encode())])
    assert m2["nodes"][0]["providerResolved"] == ""
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
    # The independent verification, 10-20: what slipped through ...
    ("host 10.0.0.5.", {"ip_address"}), ("2001:db8::1", {"ip_address"}), ("fe80::1ff:fe23:4567:890a", {"ip_address"}),
    ("1234-5678-9012", {"account_id"}), ("github_pat_" + "a1" * 11, {"token"}), ("glpat-" + "x" * 20, {"token"}),
    ("-----begin rsa private key-----", {"private_key"}), ("arn\u200b:aws:s3:::b", {"arn"}),
    ("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", {"token"}),
    # ... and what an ordinary model writes, which is no secret
    ("0.0.0.0:8080", set()), ("127.0.0.1", set()), ("::1", set()), ("postgresql://", set()), ("redis://", set()),
    ("Password=", set()), ("Server=", set()), ("Data Source=", set()), ("v1.25.3.1", set()), ("12:30:45", set()),
    ("da39a3ee5e6b4b0d3255bfef95601890afd80709", set()), ("docs/infra/icons/database-relational-01.svg", set()),
    # The independent re-verification, 10-20 (N2, N4, V01, V02, V03, V12)
    ("PaymentWebhookHandlerServiceRole3C1A9F2B", set()), ("OrderProcessingServiceProductionCluster1", set()),
    ("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", {"token"}),
    ("aws_secret_access_key = A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0", {"token"}),
    ("r2_buckets.10.0.0.9", {"ip_address"}), ("db.10.0.0.5", {"ip_address"}), ("db_10.0.0.5", {"ip_address"}),
    ("host:10.0.0.1", {"ip_address"}), ("10.0\u00ad.0.5", {"ip_address"}), ("Password: hunter2", {"password"}),
    ('"password":"hunter2"', {"password"}),
    ("release-1.2.3.4", set()), ("pkg@1.2.3.4", set()), ("::ffff", set()), ("listen [::]:80", set()),
    ("127.1.2.3", set()), ("password rotation monthly", set()),
    # The independent third verification, 10-20 (P1, P2, P3, W1, O03, O04, and the HCL "secret =")
    ("DB password: stored in Secrets Manager", set()), ("Password: rotated monthly", set()), ("Forgot password: link", set()),
    ("Password: ********", set()), ("password: ${DB_PASSWORD}", set()), ("pwd: /home/app", set()),
    ("passwd: hunter2", {"password"}), ("pwd: hunter2", {"password"}), ("password: correcthorsebatterystaple", {"password"}),
    ("docs/infra/icons/Database/Relational01ab", set()), ("path/to/some/Folder1/AnotherFolderName2X", set()),
    ("x=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", {"token"}),
    ('"SecretAccessKey": "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"', {"token"}),
    ("aws_secret_access_key: A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0", {"token"}),
    ('secret = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"', {"token"}),
    ("ec2-user@10.0.0.5", {"ip_address"}), ("bastion-10.0.0.5", {"ip_address"}), ("ip-10-0-0-5.ec2.internal", {"ip_address"}),
    ("10_0_0_5", {"ip_address"}), ("64:ff9b::a00:5", {"ip_address"}), ("::a00:5", {"ip_address"}),
    ("release_2026_10_20", set()), ("v1_2_3_4", set()),
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



# ---------------------------------------------------------------- the independent verification (10-20): environments, groups, limits

def _all_rooms():
    for room, folder in (("aws-three-tier", "docs/infra"), ("multi-provider", "docs/infra"),
                         ("compose-and-cloud", "infra/model"), ("large-multi-provider", "docs/infra")):
        yield room, _room(FIX / room / folder)[0]


def test_nothing_is_drawn_in_an_environment_what_holds_it_is_not_in():
    """D1: an edge with no environments of its own was put in every environment, so switching to one drew a cable
    with no end (alb-prod→api-prod in staging; 5 in compose-and-cloud, 105 in the large one)."""
    for room, m in _all_rooms():
        nodes = {n["id"]: n for n in m["nodes"]}
        groups = {g["id"]: g for g in m["groups"]}
        for e in m["edges"]:
            assert set(e["environments"]) <= set(nodes[e["from"]]["environments"]) & set(nodes[e["to"]]["environments"]), (room, e)
        for n in m["nodes"]:
            if n.get("group"):
                assert set(n["environments"]) <= set(groups[n["group"]]["environments"]), (room, n["id"])
        for g in m["groups"]:
            if g.get("parent"):
                assert set(g["environments"]) <= set(groups[g["parent"]]["environments"]), (room, g["id"])
    m = dict(_all_rooms())["aws-three-tier"]
    assert next(e for e in m["edges"] if (e["from"], e["to"]) == ("alb-prod", "api-prod"))["environments"] == ["production"]


def test_naming_an_environment_the_container_is_not_in():
    raw = json.dumps({"version": 0, "environments": [{"id": "p"}, {"id": "s"}],
                      "groups": [{"id": "g", "kind": "account", "environments": ["p"]}],
                      "nodes": [{"id": "a", "category": "cache", "group": "g", "environments": ["p", "s"]},
                                {"id": "b", "category": "cache", "group": "g", "environments": ["s"]},
                                {"id": "c", "category": "cache", "environments": ["s"]}],
                      "edges": [{"from": "a", "to": "c"}]}).encode()
    m, problems = M.merge([("a.json", raw)])
    codes = sorted(p["code"] for p in problems)
    assert codes == ["environment.none", "environment.none", "environment.outside", "environment.outside"], codes
    assert {n["id"]: n["environments"] for n in m["nodes"]} == {"a": ["p"], "c": ["s"]} and m["edges"] == []


def test_a_group_left_out_is_no_one_s_parent():
    """D5: a group left out (here for an environment not declared) was still named as its child's parent."""
    raw = json.dumps({"version": 0, "environments": [{"id": "p"}], "groups": [
        {"id": "pa", "kind": "account", "environments": ["nope"]}, {"id": "ch", "kind": "network", "parent": "pa"}]}).encode()
    m, problems = M.merge([("a.json", raw)])
    assert [g["id"] for g in m["groups"]] == ["ch"] and "parent" not in m["groups"][0]
    assert "group.missing" in {p["code"] for p in problems}


def test_only_the_groups_on_a_cycle_are_said_to_be_on_it():
    raw = json.dumps({"version": 0, "groups": [{"id": "d", "kind": "region", "parent": "a"},
                                               {"id": "a", "kind": "region", "parent": "b"},
                                               {"id": "b", "kind": "region", "parent": "a"}]}).encode()
    m, problems = M.merge([("a.json", raw)])
    assert sorted(p["path"] for p in problems if p["code"] == "group.cycle") == ["/groups/1/parent", "/groups/2/parent"]
    assert {g["id"]: g.get("parent") for g in m["groups"]}["d"] == "a"


def test_the_limits_cut_and_the_rest_is_drawn():
    cap = M.schema()["properties"]["groups"]["maxItems"]
    files = [(f"f{i}.json", json.dumps({"version": 0, "groups": [{"id": f"g{i}-{k}", "kind": "region"}
                                                                for k in range(cap // 2 + 100)]}).encode()) for i in range(2)]
    m, problems = M.merge(files)
    assert len(m["groups"]) == cap and [p["code"] for p in problems] == ["model.too_big"]
    ncap = M.schema()["properties"]["nodes"]["maxItems"]
    one = json.dumps({"version": 0, "nodes": [{"id": f"n{k}", "category": "cache"} for k in range(ncap + 1)]}).encode()
    m, problems = M.merge([("one.json", one)])                    # one file past the limit is cut, not thrown away
    assert len(m["nodes"]) == ncap and [p["code"] for p in problems] == ["model.too_big"]


@pytest.mark.parametrize("version", [False, 0.0, "0", None])
def test_version_is_the_integer_zero(version):
    assert [p["code"] for p in M.check_file("a.json", json.dumps({"version": version}).encode())[1]] == ["schema"]


@pytest.mark.parametrize("key", ["10.9.8.7", "arn:aws:iam::123456789012:role/x", "998877665544", "anything-else"])
def test_a_key_is_never_shown_in_a_path(key):
    """D2: a key that is not a field of the model may be a value: a path shows it as <key>."""
    raw = json.dumps({"version": 0, "nodes": [{"id": "a", "category": "cache", key: "x"}]}).encode()
    _d, problems = M.check_file("a.json", raw)
    assert problems and all(key not in json.dumps(p, ensure_ascii=False) for p in problems)
    assert {p["path"] for p in problems} == {"/nodes/0/<key>"}


def test_deep_nesting_is_a_json_problem_not_an_exception():
    raw = ('{"version": 0, "description": ' + "[" * 1100 + "]" * 1100 + "}").encode()
    data, problems = M.check_file("deep.json", raw)
    assert data is None and [p["code"] for p in problems] == ["json"]
    m, _ = M.merge([("deep.json", raw)])
    assert m["nodes"] == []



# ---------------------------------------------------------------- the independent re-verification (10-20)

def test_a_cdk_logical_id_in_iac_keeps_its_file():
    """N2: an id of exactly 40 characters (a name and 8 hex) took the file out as a secret."""
    raw = json.dumps({"version": 0, "nodes": [{"id": "role", "category": "security.iam", "provider": "aws",
                                                "iac": ["PaymentWebhookHandlerServiceRole3C1A9F2B"]}]}).encode()
    m, problems = M.merge([("a.json", raw)])
    assert problems == [] and m["nodes"][0]["iac"] == ["PaymentWebhookHandlerServiceRole3C1A9F2B"]


def test_a_group_is_drawn_only_where_its_parent_is():
    """V08: the group step of D1 (a child that names no environment takes its parent's)."""
    raw = json.dumps({"version": 0, "environments": [{"id": "p"}, {"id": "s"}],
                      "groups": [{"id": "pa", "kind": "account", "environments": ["p"]},
                                 {"id": "ch", "kind": "network", "parent": "pa"}]}).encode()
    m, problems = M.merge([("a.json", raw)])
    assert problems == [] and {g["id"]: g["environments"] for g in m["groups"]} == {"pa": ["p"], "ch": ["p"]}


def test_a_bom_is_not_an_error():
    """N5: some editors write one."""
    raw = "\ufeff".encode() + json.dumps({"version": 0}).encode()
    assert M.check_file("a.json", raw)[1] == []



def test_a_sentence_about_a_password_keeps_its_file():
    """P1: a description that says how a password is kept took the whole file out."""
    raw = json.dumps({"version": 0, "description": "DB password: stored in Secrets Manager",
                      "nodes": [{"id": "db", "category": "database.relational", "label": "Password: rotated monthly"}]}).encode()
    m, problems = M.merge([("a.json", raw)])
    assert problems == [] and [n["id"] for n in m["nodes"]] == ["db"]


# ---------------------------------------------------------------- the independent fourth verification (2026-10-20 14:42)

def _pw(text):
    return "password" in M.secret_findings(text)


def _ip(text):
    return "ip_address" in M.secret_findings(text)


@pytest.mark.parametrize("text", ["DB password: N/A", "Password: auto-generated", "password: IAM-auth", "password: AWSSecretsManager",
                                  "password: ssm:/prod/db/password", "password: vault:secret/db", "password: (secret)",
                                  "password: e.g.", "password: Vault."])
def test_a_password_line_that_is_a_word_a_place_or_a_name_is_no_value(text):
    """Q1: one word of a sentence (letters joined by - / . with no digit), a word in "(", a place named by a scheme,
    a name of capitalised words — none is a password's value, and none may drop the whole file."""
    assert not _pw(text)
    assert M.secret_findings(text) == [] or "password" not in M.secret_findings(text)


@pytest.mark.parametrize("text", ["password: hunter2", "password: P@ssw0rd", "pwd: Summer2026", "passwd: s3cr3t!",
                                  "password: xKqzPwLmRtYvBnHs", "password: abcdefghijklmnop", '"password": "Sup3r"'])
def test_a_password_value_is_still_one(text):
    assert _pw(text)


def test_the_boundaries_of_a_password_value():
    """A01: a word with a digit and then a sentence is no value (P1's ruling: "a word with more after it" is outside
    §3's promise). A05: 16 letters (no name) is a value, 15 is not."""
    assert not _pw("password: 90-day rotation") and not _pw("password: hunter2 rotated monthly")
    assert _pw("password: abcdefghijklmnop") and not _pw("password: abcdefghijklmno")


def test_the_boundary_of_a_path_in_a_40_character_key():
    """A07: three "/" make a 40-character run a path; two do not."""
    three = "wJalrXUtnFEMI/K7MDENG/bPxRfi/YEXAMPLEKEY"
    two = "wJalrXUtnFEMI/K7MDENGbPxRfi/YEXAMPLEKEYx"
    assert len(three) == len(two) == 40
    assert "token" not in M.secret_findings(three) and "token" in M.secret_findings(two)


@pytest.mark.parametrize("text", ["IP-10-0-0-5", "IP-1-2-3-4", "ip-10-0-0-5", "10_0_0_5_url", "ec2-54-12-34-56.compute-1.amazonaws.com", "host-10-0-0-5",
                                  "10-0-0-5", "db_10_0_0_5_url", "db_10_0_0_5", "10_0_0_5", "::a00:5", "64:ff9b::a00:5",
                                  "::ffff:a00:5", "fe80::1", "2001:db8::1"])
def test_an_address_written_another_way_is_one(text):
    """A10 (ip- in any case names an address whatever its first number: IP-1-2-3-4), Q3's misses (ec2-, a name before "-", "_" and more after it)."""
    assert _ip(text)


@pytest.mark.parametrize("text", ["ip-127-0-0-1", "127_0_0_1", "0_0_0_0", "ip-10-0-0-5-6", "ip-10-0-0-500", "build_1_2_3_4",
                                  "version_1_2_3_4", "release-1-2-3-4", "a::b", "Db::Feed", "::2", "::ffff:0", "::",
                                  "::1", "::ffff", "::ffff:127.0.0.1", "::ffff:7f00:1", "::7f00:1", "listen [::]:80"])
def test_no_ones_address_and_what_only_looks_like_one_is_none(text):
    """A11 (127 and 0), A21 (more numbers after), A13 (::/112: ::2), Q3's false hits (a version after "_", hex
    words joined by "::", ::ffff:0 = ::255.255.0.0)."""
    assert not _ip(text)


# ---------------------------------------------------------------- a node's spec (ticket 2026-10-20-jui-viz-server-room-lines-dark-filter-spec §4)

def _spec_file(spec, **node):
    return json.dumps({"version": 0, "nodes": [{"id": "db", "category": "database.relational", "provider": "aws", **node, "spec": spec}]}).encode()


def test_a_nodes_spec_is_kept_in_order_and_a_key_written_twice_keeps_the_first():
    spec = [{"key": "instance_class", "value": "db.r6g.large"}, {"key": "storage_gb", "value": "100"},
            {"key": "instance_class", "value": "db.t3.micro"}]
    model, problems = M.merge([("m.json", _spec_file(spec))])
    assert model["nodes"][0]["spec"] == spec[:2]
    assert [(p["code"], p["severity"], p["path"]) for p in problems] == [("spec.duplicate", "warning", "/nodes/0/spec/2/key")]


@pytest.mark.parametrize("item, path", [
    ({"key": "Instance", "value": "x"}, "/nodes/0/spec/0/key"),              # a key is lower case, a letter first
    ({"key": "1st", "value": "x"}, "/nodes/0/spec/0/key"),
    ({"key": "a" * 41, "value": "x"}, "/nodes/0/spec/0/key"),
    ({"key": "memory", "value": "x" * 121}, "/nodes/0/spec/0/value"),
    ({"key": "memory", "value": "   "}, "/nodes/0/spec/0/value"),
    ({"key": "memory", "value": 512}, "/nodes/0/spec/0/value"),             # a string: "512", as the display shows it
    ({"key": "memory"}, "/nodes/0/spec/0/value"),
    ({"key": "memory", "value": "1", "unit": "GB"}, "/nodes/0/spec/0/<key>"),      # a field it does not have: masked
])
def test_a_spec_item_out_of_its_form_is_a_schema_error(item, path):
    data, problems = M.check_file("m.json", _spec_file([item]))
    assert data is None and [(p["code"], p["path"]) for p in problems] == [("schema", path)]


def test_spec_has_at_most_20_items():
    spec = [{"key": f"k{i}", "value": "v"} for i in range(21)]
    _d, problems = M.check_file("m.json", _spec_file(spec))
    assert [(p["code"], p["path"]) for p in problems] == [("schema", "/nodes/0/spec")]


@pytest.mark.parametrize("value, kind", [
    ("postgres://app@db.internal:5432/orders", "connection_string"), ("10.0.3.12", "ip_address"),
    ("arn:aws:rds:ap-northeast-1:123456789012:db:orders", "arn"), ("AKIA" "ABCDEFGHIJKLMNOP", "access_key")])
def test_a_secret_in_a_spec_value_leaves_the_file_out_and_never_shows_the_value(value, kind):
    """The guard is the one every string of a file passes (check_file's _walk_strings): a spec is no exception."""
    raw = _spec_file([{"key": "instance_class", "value": "db.r6g.large"}, {"key": "endpoint", "value": value}])
    data, problems = M.check_file("m.json", raw)
    assert data is None and f"secret.{kind}" in {p["code"] for p in problems}
    assert {p["path"] for p in problems if p["code"].startswith("secret.")} == {"/nodes/0/spec/1/value"}
    model, _ = M.merge([("m.json", raw)])
    assert model["nodes"] == [] and value not in json.dumps(problems) and value not in json.dumps(model)


def test_a_secret_in_a_spec_key_is_found_too():
    _d, problems = M.check_file("m.json", _spec_file([{"key": "db_10_0_0_5", "value": "primary"}]))
    assert [(p["code"], p["path"]) for p in problems] == [("secret.ip_address", "/nodes/0/spec/0/key")]
