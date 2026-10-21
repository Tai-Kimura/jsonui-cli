"""A SaaS billed by use is priced from its load (ticket doc-infra-cost-external-saas-reads-no-load, 2.3.16).

Before, external.saas read no quantity and had no formula: an LLM, the biggest bill of a backend, was "no rule" and
$0, and its load could not even be written. Now it reads requests and an LLM's tokens in and out; tokens can be
written by model (by_sku), each priced under <model>:input-tokens / <model>:output-tokens. The answer is a hand
calculation (below); the same model and load on 2.3.15 is $0 with the node under noRule (the old shape: requests only,
since the tokens were not in the load's vocabulary).
"""
from __future__ import annotations

import json
import subprocess
import sys

from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra.cost import engine as E
from jsonui_doc_cli.infra.cost import pricebook as PB
from test_infra_load import TOOLS

SONNET, HAIKU = "model-large", "model-small"
LLM = {"id": "llm", "category": "external.saas", "provider": "llm-vendor", "service": "messages", "managed_by": "external"}
GEO = {"id": "geo", "category": "external.saas", "provider": "maps-vendor", "service": "geocoding", "managed_by": "external"}


def _price(provider, service, sku, unit, usd, per_units=1, **extra) -> dict:
    return {"provider": provider, "service": service, "sku": sku, "region": "global", "unit": unit, "per_units": per_units,
            "price_usd": usd, "effective": "2026-10-01", "source": "manual", **extra}


#: per million tokens: the large model $2 in / $10 out, the small one $0.10 / $0.50; geocoding $5 per 1,000 past
#: 10,000 free a month
PRICES = [
    _price("llm-vendor", "messages", f"{SONNET}:input-tokens", "token", 2.0, 1_000_000),
    _price("llm-vendor", "messages", f"{SONNET}:output-tokens", "token", 10.0, 1_000_000),
    _price("llm-vendor", "messages", f"{HAIKU}:input-tokens", "token", 0.10, 1_000_000),
    _price("llm-vendor", "messages", f"{HAIKU}:output-tokens", "token", 0.50, 1_000_000),
    _price("maps-vendor", "geocoding", "requests", "request", 5.0, 1000, free={"amount": 10_000, "period": "month"}),
]
#: a day: 10,000 replies on the large model (5,000 tokens in, 600 out each) and 32,000 intent calls on the small one
#: (1,500 in, 80 out); 20 geocoding calls
LOADS = [
    {"node": "llm", "quantities": {
        "requests": {"amount": 42_000, "per": "day"},
        "input_tokens": {"by_sku": {SONNET: 10_000 * 5_000, HAIKU: 32_000 * 1_500}, "per": "day"},
        "output_tokens": {"by_sku": {SONNET: 10_000 * 600, HAIKU: 32_000 * 80}, "per": "day"}}},
    {"node": "geo", "quantities": {"requests": {"amount": 20, "per": "day"}}},
]
#: by hand, a day: large 50M in x $2 = $100, 6M out x $10 = $60; small 48M in x $0.10 = $4.80, 2.56M out x $0.50 =
#: $1.28; $166.08 a day, 30 days in 2026-11: $4,982.40. Geocoding: 600 calls, within the 10,000 free: $0 (counted).
HAND = {f"{SONNET}:input-tokens": 3000.0, f"{SONNET}:output-tokens": 1800.0, f"{HAIKU}:input-tokens": 144.0,
        f"{HAIKU}:output-tokens": 38.4}
HAND_MONTH = 4982.40


def _simulate(loads=LOADS, prices=PRICES):
    doc = {"version": 0, "groups": [], "nodes": [LLM, GEO], "edges": []}
    model, problems = M.merge([("m.json", json.dumps(doc).encode())])
    assert M.errors(problems) == []
    scenario, problems = L.normalize("t.json", {"version": 0, "id": "t", "month": "2026-11", "loads": loads}, model)
    assert [p for p in problems if p["severity"] == "error"] == [] and \
        [p["code"] for p in problems if p["code"] == "load.quantity_unused"] == []
    book = PB.Book(user=[dict(r, file="u.json", index=i) for i, r in enumerate(prices)])
    result = E.simulate(scenario, model, book)
    return result, E.month_totals(result)


def _usd(result, node: str) -> dict:
    run = next(r for r in result.nodes if r.node == node)
    return {name: round(sum(v for v in m["usd"] if v is not None), 2) for name, m in run.meters.items()}


def test_an_llm_is_priced_by_its_tokens_model_by_model_as_by_hand():
    result, totals = _simulate()
    llm = _usd(result, "llm")
    assert {k: v for k, v in llm.items() if k != "requests"} == HAND
    assert llm["requests"] == 0.0             # no price per call: an LLM bills its tokens (optional, no warning)
    assert round(totals["usd"], 2) == HAND_MONTH and totals["noRule"] == [] and totals["noPrice"] == []


def test_each_models_tokens_are_their_own_segment_on_the_page():
    from jsonui_doc_cli.infra.cost import view as V
    result, _t = _simulate()
    run = next(r for r in result.nodes if r.node == "llm")
    segs = {s["meter"]: s for s in V.node_hour(run, 10)["segments"]}
    assert segs[f"{SONNET}:input-tokens"]["label"] == f"入力トークン（{SONNET}）"
    assert segs[f"{HAIKU}:output-tokens"]["label"] == f"出力トークン（{HAIKU}）" and segs["requests"]["label"] == "リクエスト"
    # its rate is the model's own: 10,000 x 5,000 tokens a day
    assert segs[f"{SONNET}:input-tokens"]["rate"]["value"] == 50_000_000 and segs[f"{SONNET}:input-tokens"]["rate"]["per"] == "day"


def test_a_saas_billed_per_call_within_its_free_amount_is_counted_as_0():
    result, totals = _simulate()
    run = next(r for r in result.nodes if r.node == "geo")
    assert round(sum(run.meters["requests"]["amount"])) == 600 and _usd(result, "geo") == {"requests": 0.0}
    assert "geo" not in totals["noRule"] and "geo" not in totals["loadUndefined"]


def test_tokens_as_one_flow_are_priced_under_the_rows_model_or_the_plain_sku():
    one = {"node": "llm", "sku": SONNET, "quantities": {"input_tokens": {"amount": 50_000_000, "per": "day"}}}
    result, _t = _simulate([one, LOADS[1]])
    assert _usd(result, "llm") == {f"{SONNET}:input-tokens": 3000.0}
    plain = [_price("llm-vendor", "messages", "input-tokens", "token", 1.0, 1_000_000)]
    result, _t = _simulate([{"node": "llm", "quantities": {"input_tokens": {"amount": 1_000_000, "per": "day"}}},
                            LOADS[1]], PRICES + plain)
    assert _usd(result, "llm") == {"input-tokens": 30.0}


def test_a_call_price_with_no_tokens_is_required_and_said_when_missing():
    result, totals = _simulate([{"node": "llm", "quantities": {"requests": {"amount": 100, "per": "day"}}}, LOADS[1]])
    assert totals["noPrice"] == [{"node": "llm", "meter": "requests", "sku": "requests", "unit": "request"}]


def test_the_command_sums_the_llm_and_lists_no_rule_for_it(tmp_path):
    """jsonui-doc cost infra (the CLI's summary, and the JSON the MCP's infra_cost relays) reads the new lines."""
    root = tmp_path / "room"
    for rel, doc in (("docs/infra/main.json", {"version": 0, "nodes": [LLM, GEO]}),
                     ("docs/infra/load/s.json", {"version": 0, "id": "s", "month": "2026-11", "loads": LOADS}),
                     ("docs/infra/prices/p.json", {"version": 0, "id": "p", "currency": "USD", "prices": PRICES})):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(doc))
    env = {"JUI_VIZ_HOME": str(tmp_path / "none")}
    run = lambda *a: subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "cost", "infra", str(root), *a],
                                    cwd=TOOLS, capture_output=True, text=True, env={**__import__("os").environ, **env})
    got = run("--json")
    assert got.returncode == 0, got.stderr
    out = json.loads(got.stdout)
    assert round(out["month"]["usd"], 2) == HAND_MONTH and out["month"]["noRule"] == []
    assert [t["node"] for t in out["topNodes"]][:1] == ["llm"]
    text = run()
    assert text.returncode == 0 and "$4,982.40" in text.stdout and "no rule" not in text.stdout


def test_a_ci_service_is_priced_by_its_build_minutes():
    """The same family (a kind billed by use that read nothing): 3,000 runner minutes in the month, 2,000 free, $0.008
    a minute past them -> $8.00 by hand in a 730-hour month; the engine counts November's 720 hours, so $7.67."""
    ci = {"id": "ci", "category": "ci", "provider": "ci-vendor", "service": "actions", "managed_by": "external"}
    model, problems = M.merge([("m.json", json.dumps({"version": 0, "groups": [], "nodes": [ci], "edges": []}).encode())])
    load = {"node": "ci", "quantities": {"build_minutes": {"amount": 3000, "per": "month"}}}
    scenario, problems = L.normalize("t.json", {"version": 0, "id": "t", "month": "2026-11", "loads": [load]}, model)
    assert [p["code"] for p in problems] == []
    price = _price("ci-vendor", "actions", "minutes", "minute", 0.008, free={"amount": 2000, "period": "month"})
    totals = E.month_totals(E.simulate(scenario, model, PB.Book(user=[dict(price, file="u.json", index=0)])))
    # 3,000 a month written per month (730 hours) over November's 720 hours: 2,958.9 minutes
    assert round(totals["usd"], 2) == round((3000 * 720 / 730 - 2000) * 0.008, 2) and totals["noRule"] == []
