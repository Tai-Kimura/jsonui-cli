"""The flows of the infra model (the server room ticket's item 7 and its additions): a flow starts at any node, its
steps name nodes and edges as the load definitions do, and every path through its branches must hold together on the
merged model. A flow that does not is left out alone, with problems that name the place and the kind only."""
from __future__ import annotations

import copy
import json

import pytest

from jsonui_doc_cli.infra import model as M

BASE = {
    "version": 0,
    "environments": [{"id": "prod", "kind": "production"}, {"id": "stg", "kind": "staging"}],
    "nodes": [
        {"id": "browser", "category": "client"},
        {"id": "beacon", "category": "client", "label": "ビーコンの基地局"},
        {"id": "api", "category": "compute.container", "provider": "aws"},
        {"id": "cache", "category": "cache", "provider": "aws"},
        {"id": "db", "category": "database.relational", "provider": "aws"},
        {"id": "bucket", "category": "storage.object", "provider": "aws"},
        {"id": "queue", "category": "queue", "provider": "aws"},
        {"id": "worker", "category": "compute.function", "provider": "aws"},
        {"id": "cron", "category": "scheduler", "provider": "aws"},
        {"id": "stg-only", "category": "cache", "provider": "aws", "environments": ["stg"]},
    ],
    "edges": [
        {"id": "e-browser-api", "from": "browser", "to": "api"},
        {"from": "beacon", "to": "api"},
        {"from": "api", "to": "cache"},
        {"from": "api", "to": "db"},
        {"from": "api", "to": "bucket"},
        {"from": "api", "to": "queue"},
        {"from": "worker", "to": "queue", "direction": "in"},
        {"from": "worker", "to": "db"},
        {"from": "cron", "to": "worker"},
        {"from": "api", "to": "stg-only"},
    ],
}

LOGIN = {"id": "login", "label": "ログインする", "start": "browser", "steps": [
    {"edge": "e-browser-api", "action": "request", "label": "POST /login"},
    {"node": "api", "action": "auth"},
    {"branch": {"label": "キャッシュに有る？", "default": "hit", "choices": [
        {"id": "hit", "label": "有る", "steps": [{"from": "api", "to": "cache", "action": "read"},
                                                 {"from": "cache", "to": "api", "action": "response"}]},
        {"id": "miss", "label": "無い", "steps": [{"from": "api", "to": "db", "action": "read"},
                                                  {"from": "db", "to": "api", "action": "response"}]}]}},
    {"id": "reply", "from": "api", "to": "browser", "action": "response"},
]}


def _merge(*flows, base=None):
    doc = copy.deepcopy(base or BASE)
    doc["flows"] = list(flows)
    return M.merge([("m.json", json.dumps(doc, ensure_ascii=False).encode())])


def _codes(problems, severity="error"):
    return [(p["code"], p["path"]) for p in problems if p["severity"] == severity]


def test_a_flow_along_the_model_is_kept_with_each_move_s_ends():
    model, problems = _merge(LOGIN)
    assert problems == []
    f = model["flows"][0]
    assert (f["id"], f["label"], f["trigger"], f["environments"]) == ("login", "ログインする", "user", ["prod", "stg"])
    s = f["steps"]
    assert (s[0]["from"], s[0]["to"]) == ("browser", "api")                 # named by the edge's id
    assert s[1]["at"] == "api"
    miss = s[2]["branch"]["choices"][1]["steps"]
    assert [(x["from"], x["to"]) for x in miss] == [("api", "db"), ("db", "api")]   # a response goes back along the edge
    assert (s[3]["from"], s[3]["to"]) == ("api", "browser")


def test_a_flow_starts_at_any_node_a_device_a_schedule_or_an_event():
    beacon = {"id": "beacon-seen", "start": "beacon", "trigger": "device", "steps": [{"from": "beacon", "to": "api", "action": "request"}]}
    cron = {"id": "nightly", "start": "cron", "trigger": "schedule", "schedule": "rate(5 minutes)",
            "steps": [{"from": "cron", "to": "worker", "action": "invoke"}, {"from": "worker", "to": "db", "action": "write"}]}
    queued = {"id": "drain", "start": "queue", "trigger": "event",
              "steps": [{"from": "queue", "to": "worker", "action": "dequeue"}]}            # an edge whose direction is in
    model, problems = _merge(beacon, cron, queued)
    assert problems == [] and [f["trigger"] for f in model["flows"]] == ["device", "schedule", "event"]
    assert model["flows"][1]["schedule"] == "rate(5 minutes)"


@pytest.mark.parametrize("flow, code, path", [
    ({"id": "f", "start": "nowhere", "steps": [{"node": "nowhere"}]}, "flow.node.missing", "/flows/0/start"),
    ({"id": "f", "start": "browser", "steps": [{"from": "browser", "to": "db"}]}, "flow.edge.missing", "/flows/0/steps/0"),
    ({"id": "f", "start": "browser", "steps": [{"edge": "no-such"}]}, "flow.edge.missing", "/flows/0/steps/0/edge"),
    ({"id": "f", "start": "browser", "steps": [{"from": "api", "to": "db"}]}, "flow.discontinuous", "/flows/0/steps/0/from"),
    ({"id": "f", "start": "browser", "steps": [{"node": "api"}]}, "flow.discontinuous", "/flows/0/steps/0/node"),
    ({"id": "f", "start": "queue", "steps": [{"from": "queue", "to": "api"}]}, "flow.edge.missing", "/flows/0/steps/0"),   # against the edge
    ({"id": "f", "start": "browser", "steps": [{"action": "read"}]}, "flow.step.kind", "/flows/0/steps/0"),
    ({"id": "f", "start": "browser", "steps": [{"node": "browser", "from": "browser", "to": "api"}]}, "flow.step.kind", "/flows/0/steps/0"),
    ({"id": "f", "start": "browser", "steps": [{"from": "browser"}]}, "flow.step.kind", "/flows/0/steps/0"),
    ({"id": "f", "start": "browser", "schedule": "rate(1 hour)", "steps": [{"node": "browser"}]}, "flow.schedule.trigger", "/flows/0/schedule"),
    ({"id": "f", "start": "api", "environments": ["prod"], "steps": [{"from": "api", "to": "stg-only"}]}, "flow.node.missing", "/flows/0/steps/0/to"),
    ({"id": "f", "start": "browser", "environments": ["dev"], "steps": [{"node": "browser"}]}, "environment.missing", "/flows/0/environments"),
])
def test_a_flow_that_does_not_hold_together_is_left_out_alone(flow, code, path):
    ok = {"id": "ok", "start": "browser", "steps": [{"node": "browser"}]}
    model, problems = _merge(flow, ok)
    assert [f["id"] for f in model["flows"]] == ["ok"] and model["nodes"]          # the rest of the file stays
    assert (code, path) in _codes(problems), _codes(problems)


def test_a_branch_s_paths_each_hold_together():
    bad = copy.deepcopy(LOGIN)
    bad["steps"][2]["branch"]["choices"][1]["steps"] = [{"from": "api", "to": "db", "action": "read"}]   # ends at db
    _model, problems = _merge(bad)
    # after the branch the flow is at api on one path and at db on the other: the next step is reached at two nodes
    assert ("flow.paths_disagree", "/flows/0/steps/3") in _codes(problems)


def test_join_goto_and_default():
    join = copy.deepcopy(LOGIN)
    join["steps"][2]["branch"]["choices"][0] = {"id": "hit", "label": "有る", "join": "reply"}
    assert _merge(join)[1] == []
    for target, code in (("no-step", "flow.join.missing"), ("auth-step", "flow.join.backward")):
        f = copy.deepcopy(join)
        f["steps"][1]["id"] = "auth-step"
        f["steps"][2]["branch"]["choices"][0]["join"] = target
        assert (code, "/flows/0/steps/2/branch/choices/0/join") in _codes(_merge(f)[1])
    f = copy.deepcopy(LOGIN)
    f["steps"][2]["branch"]["default"] = "neither"
    assert ("flow.default.missing", "/flows/0/steps/2/branch/default") in _codes(_merge(f)[1])
    f = copy.deepcopy(LOGIN)
    f["steps"][2]["branch"]["choices"][1] = {"id": "miss", "label": "無い", "goto": "nowhere"}
    assert ("flow.goto.missing", "/flows/0/steps/2/branch/choices/1/goto") in _codes(_merge(f)[1])


def test_a_goto_to_a_flow_that_starts_elsewhere_is_a_warning_the_page_jumps():
    retry = {"id": "retry", "start": "browser", "steps": [{"edge": "e-browser-api", "action": "request"}]}
    f = copy.deepcopy(LOGIN)
    f["steps"][2]["branch"]["choices"][1] = {"id": "miss", "label": "無い", "goto": "retry"}     # left at api
    model, problems = _merge(f, retry)
    assert [x["id"] for x in model["flows"]] == ["login", "retry"]
    assert _codes(problems, "warning") == [("flow.goto.jump", "/flows/0/steps/2/branch/choices/1/goto")]


def test_a_loop_closed_by_defaults_alone_is_refused_one_a_person_closes_is_not():
    def flow(fid, other, default):
        return {"id": fid, "start": "browser", "steps": [{"branch": {"label": "?", **({"default": "again"} if default else {}),
                                                                      "choices": [{"id": "again", "label": "もう一度", "goto": other},
                                                                                  {"id": "stop", "label": "やめる", "steps": [{"node": "browser"}]}]}}]}
    model, problems = _merge(flow("a", "b", True), flow("b", "a", True))
    assert model["flows"] == [] and sorted(_codes(problems)) == [("flow.default_cycle", "/flows/0"), ("flow.default_cycle", "/flows/1")]
    model, problems = _merge(flow("a", "b", True), flow("b", "a", False))     # b stops for a person
    assert _codes(problems) == [] and len(model["flows"]) == 2


def test_lanes_side_by_side_leave_from_where_the_flow_is_and_it_stays_there():
    f = {"id": "upload", "start": "browser", "steps": [
        {"edge": "e-browser-api", "action": "upload"},
        {"parallel": [[{"from": "api", "to": "bucket", "action": "upload"}],
                      [{"from": "api", "to": "queue", "action": "enqueue", "async": True}]]},
        {"from": "api", "to": "browser", "action": "response"}]}
    model, problems = _merge(f)
    assert problems == []
    lanes = model["flows"][0]["steps"][1]["parallel"]
    assert [(lane[0]["from"], lane[0]["to"]) for lane in lanes] == [("api", "bucket"), ("api", "queue")]
    bad = copy.deepcopy(f)
    bad["steps"][1]["parallel"][0] = [{"from": "browser", "to": "api"}]          # a lane leaves where the flow is not
    assert ("flow.discontinuous", "/flows/0/steps/1/parallel/0/0/from") in _codes(_merge(bad)[1])


def test_nesting_is_capped_and_ids_are_once():
    step = {"node": "browser"}
    for _ in range(5):
        step = {"branch": {"label": "?", "choices": [{"id": "a", "label": "a", "steps": [step]}, {"id": "b", "label": "b"}]}}
    _m, problems = _merge({"id": "deep", "start": "browser", "steps": [step]})
    assert any(c == "flow.too_deep" for c, _p in _codes(problems))
    one = {"id": "same", "start": "browser", "steps": [{"node": "browser"}]}
    model, problems = _merge(one, one)
    assert len(model["flows"]) == 1 and _codes(problems) == [("flow.id.duplicate", "/flows/1/id")]


def test_the_schema_holds_the_vocabularies_and_a_secret_in_a_flow_leaves_the_file_out():
    assert M.vocabulary("action")[:3] == ["request", "response", "read"] and M.vocabulary("trigger") == ["user", "device", "schedule", "event"]
    labels = M.schema()["$defs"]["action"]
    assert set(labels["x-label"]) == set(labels["enum"]) == set(labels["x-icon"])         # every action has its words and mark
    bad = copy.deepcopy(LOGIN)
    bad["steps"][0]["label"] = "POST https://admin:hunter2@api.internal/login"
    model, problems = _merge(bad)
    assert model["nodes"] == [] and ("secret.url_credentials", "/flows/0/steps/0/label") in _codes(problems)
    assert "hunter2" not in json.dumps(problems)
    bad = copy.deepcopy(LOGIN)
    bad["steps"][0]["action"] = "teleport"
    assert ("schema", "/flows/0/steps/0/action") in _codes(_merge(bad)[1])


def test_every_problem_code_of_flows_has_its_short_line_in_words():
    """room.short names each flow problem in words; the codes are read from flows.py itself, not listed here."""
    import re
    from pathlib import Path
    from jsonui_doc_cli.infra import flows as F, room as R
    codes = set(re.findall(r'"(flow\.[a-z_.]+)"', Path(F.__file__).read_text(encoding="utf-8")))
    assert codes and codes == set(R.FLOW_JA)
    for code in codes:
        line = R.short({"file": "m.json", "path": "/flows/0", "code": code, "message": ""}, "docs/infra")
        assert line.startswith("docs/infra/m.json: /flows/0 の flow ") and R.FLOW_JA[code] in line, line


def test_a_loop_closed_by_any_default_goto_is_refused_not_only_the_first_one():
    """The independent check's probe: a's first lane goes by default to c (which ends), its second to b, and b to a.
    The loop a -> b -> a is closed by defaults; c is not on it and stays."""
    def stop_or(goto):
        return {"branch": {"label": "?", "default": "go", "choices": [{"id": "go", "label": "進む", "goto": goto},
                                                                       {"id": "stop", "label": "やめる", "steps": [{"node": "browser"}]}]}}
    a = {"id": "a", "start": "browser", "steps": [{"parallel": [[stop_or("c")], [stop_or("b")]]}]}
    b = {"id": "b", "start": "browser", "steps": [stop_or("a")]}
    c = {"id": "c", "start": "browser", "steps": [{"node": "browser"}]}
    model, problems = _merge(a, b, c)
    assert [f["id"] for f in model["flows"]] == ["c"]
    assert sorted(_codes(problems)) == [("flow.default_cycle", "/flows/0"), ("flow.default_cycle", "/flows/1")]
    a1 = {"id": "a", "start": "browser", "steps": [stop_or("a")]}                  # a default back to itself
    assert _codes(_merge(a1)[1]) == [("flow.default_cycle", "/flows/0")]


def test_an_edge_only_in_another_environment_does_not_carry_the_flow():
    """The independent check's G4: an edge drawn in stg only is not one a flow of prod can take, though its two ends
    are drawn in both."""
    base = copy.deepcopy(BASE)
    base["edges"].append({"from": "cache", "to": "db", "environments": ["stg"]})
    f = {"id": "f", "start": "api", "environments": ["prod"], "steps": [{"from": "api", "to": "cache"}, {"from": "cache", "to": "db"}]}
    model, problems = _merge(f, base=base)
    assert model["flows"] == [] and ("flow.edge.missing", "/flows/0/steps/1") in _codes(problems)
    f["environments"] = ["stg"]
    assert _merge(f, base=base)[1] == []


def _with_pay():
    """A payment service drawn in prod only, reached from the api; the edges between api and cache split by environment."""
    base = copy.deepcopy(BASE)
    base["nodes"].append({"id": "pay", "category": "external.saas", "environments": ["prod"]})
    base["edges"] += [{"id": "e-api-pay", "from": "api", "to": "pay"},
                      {"id": "e-cache-db-prod", "from": "cache", "to": "db", "environments": ["prod"]},
                      {"id": "e-db-bucket-stg", "from": "db", "to": "bucket", "environments": ["stg"]}]
    return base


BUY = {"id": "buy", "start": "browser", "steps": [{"edge": "e-browser-api"}, {"edge": "e-api-pay", "action": "request"}]}


def test_a_flow_naming_its_environments_holds_together_in_each_of_them():
    """Asked by a backend writing staging flows: a step drawn in prod only does not carry a flow that names stg too
    (it was taken as soon as one of the flow's environments drew it)."""
    base = _with_pay()
    model, problems = _merge({**BUY, "environments": ["prod", "stg"]}, base=base)
    assert model["flows"] == [] and _codes(problems) == [("flow.env.partial", "/flows/0/environments")]
    assert "stg" in problems[0]["message"] and "prod" not in problems[0]["message"]
    model, problems = _merge({**BUY, "environments": ["prod"]}, base=base)
    assert problems == [] and model["flows"][0]["environments"] == ["prod"]
    # its start not drawn in one it names: that one is not dropped quietly either
    late = {"id": "late", "start": "stg-only", "environments": ["prod", "stg"], "steps": [{"node": "stg-only"}]}
    assert _codes(_merge(late, base=base)[1]) == [("flow.env.partial", "/flows/0/environments")]


def test_a_flow_naming_no_environment_is_drawn_where_its_whole_way_is():
    base = _with_pay()
    model, problems = _merge(BUY, base=base)
    assert problems == [] and model["flows"][0]["environments"] == ["prod"]
    # a way whose steps are each drawn somewhere, but in no one environment all of them
    mixed = {"id": "mixed", "start": "api", "steps": [{"from": "api", "to": "cache"}, {"edge": "e-cache-db-prod"},
                                                      {"edge": "e-db-bucket-stg"}]}
    model, problems = _merge(mixed, base=base)
    assert model["flows"] == [] and _codes(problems) == [("flow.env.partial", "/flows/0")]
    # what is wrong with the way itself is said as before, not as the environments
    assert _codes(_merge({**BUY, "steps": [{"from": "browser", "to": "db"}]}, base=base)[1]) == [("flow.edge.missing", "/flows/0/steps/0")]


def test_a_loop_whose_flows_also_go_to_a_flow_that_ends_is_refused_and_that_flow_kept():
    """The independent check's H2: r goes by default to s; s's two lanes go by default to r and to c (no goto). Only r
    and s are on the loop: c, reached from it and done first, stays."""
    def to(goto):
        return {"branch": {"label": "?", "default": "go", "choices": [{"id": "go", "label": "進む", "goto": goto},
                                                                       {"id": "stop", "label": "やめる", "steps": [{"node": "browser"}]}]}}
    c = {"id": "c", "start": "browser", "steps": [{"node": "browser"}]}
    r = {"id": "r", "start": "browser", "steps": [to("s")]}
    s = {"id": "s", "start": "browser", "steps": [{"parallel": [[to("r")], [to("c")]]}]}
    model, problems = _merge(c, r, s)
    assert [f["id"] for f in model["flows"]] == ["c"]
    assert sorted(_codes(problems)) == [("flow.default_cycle", "/flows/1"), ("flow.default_cycle", "/flows/2")]


def test_a_long_chain_of_defaults_needs_no_deep_recursion():
    """Flows from all of a room's files together may be more than one file's 200: the loop finder walks with a stack of
    its own (a chain of 3,000 flows, each going by default to the next, ends without a loop and without an error)."""
    from jsonui_doc_cli.infra import flows as FL
    graph = {f"f{i}": {f"f{i + 1}"} for i in range(3000)}
    graph["f3000"] = set()
    assert FL._on_cycles(graph) == set()
    graph["f3000"] = {"f0"}
    assert len(FL._on_cycles(graph)) == 3001
