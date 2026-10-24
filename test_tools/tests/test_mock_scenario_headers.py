"""A scenario's response headers (ticket 2026-10-24-jsonui-test-mock-scenario-cannot-set-response-headers).

A scenario could carry no header: the validator called `headers` an unknown key, `mock serve` sent Content-Type and
CORS only, the three branch-test runtimes Content-Type only (the mobile ones were not even handed the rest), and
`mock generate` read none of the headers an OpenAPI response declares — so a branch that reads `Retry-After`,
`Content-Disposition` or `X-Request-ID` could not be a row. The family, in JSON and in YAML OpenAPI alike:

- generate writes each declared header with a value (its example, its examples' first, its schema's), every required
  one, through a header's `$ref` and a response's; none for an optional header with no value, none for Content-Type
- the validator takes `headers` and names a header the server would not send (not a token, not a string, a line
  break, Content-Type / Content-Length)
- `mock serve` sends them, lists their names in Access-Control-Expose-Headers, and sends none it would not
- `--check` names an undeclared header, a required one absent and a value its schema does not take, a file response's
  too; `contractViolations` subtracts them; `--update-default` adds a required one to the default
- branch-tests hands each runtime the headers `mock serve` sends; the runtimes, run, put them on the response
  (test_branch_scenario_headers.py: web and iOS, with the compilers; _android.py: the Android leg)
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli.mock.generate import build_mock_definition, generate, update_default
from jsonui_test_cli.mock.openapi import OpenApiDoc
from jsonui_test_cli.mock.server import MockServer, MockStore, RunManager
from jsonui_test_cli.validation.mock import MockValidator
from jsonui_test_cli.validation.models import ValidationResult
from tests.test_branch_tests_generator import BASIC, _project

INT = {"type": "integer"}
# name -> (the 429's headers, the scenario's headers generate must write)
FORMS = {
    "header example": ({"Retry-After": {"schema": INT, "example": 30}}, {"Retry-After": "30"}),
    "header examples": ({"Retry-After": {"schema": INT, "examples": {"a": {"value": 30}}}}, {"Retry-After": "30"}),
    "header examples -> components/examples": (
        {"Retry-After": {"schema": INT, "examples": {"a": {"$ref": "#/components/examples/Thirty"}}}}, {"Retry-After": "30"}),
    "schema example": ({"Retry-After": {"schema": {"type": "integer", "example": 30}}}, {"Retry-After": "30"}),
    "schema enum": ({"X-Mode": {"schema": {"type": "string", "enum": ["closed", "open"]}}}, {"X-Mode": "closed"}),
    "$ref -> components/headers": ({"Retry-After": {"$ref": "#/components/headers/RetryAfter"}}, {"Retry-After": "30"}),
    "required, no example": ({"Retry-After": {"required": True, "schema": INT}}, {"Retry-After": "0"}),
    "optional, no example": ({"X-Request-ID": {"schema": {"type": "string"}}}, None),
    "Content-Type declared": ({"Content-Type": {"schema": {"type": "string"}, "example": "text/plain"}}, None),
}


def _spec(headers_429, *, ref_response=False, headers_200=None, csv=False) -> dict:
    r429 = {"description": "x", "headers": headers_429,
            "content": {"application/json": {"schema": {"type": "object", "properties": {"code": {"type": "string"}}}}}}
    r200 = {"description": "ok", "content": {"text/csv": {"schema": {"type": "string"}}} if csv
            else {"application/json": {"schema": {"type": "object", "properties": {"a": INT}}}}}
    if headers_200:
        r200["headers"] = headers_200
    return {"openapi": "3.0.3", "info": {"title": "t", "version": "1"},
            "components": {"headers": {"RetryAfter": {"schema": INT, "example": 30}},
                           "examples": {"Thirty": {"value": 30}}, "responses": {"Limited": r429}},
            "paths": {"/x": {"get": {"operationId": "getX", "responses": {
                "200": r200, "429": {"$ref": "#/components/responses/Limited"} if ref_response else r429}}}}}


def _write(tmp_path: Path, spec: dict, fmt: str = "json") -> Path:
    path = tmp_path / f"api.{fmt}"
    path.write_text(json.dumps(spec) if fmt == "json" else yaml.safe_dump(spec), encoding="utf-8")
    return path


# ---------------------------------------------------------------- generate ----

@pytest.mark.parametrize("fmt", ["json", "yaml"])
@pytest.mark.parametrize("ref_response", [False, True], ids=["in place", "response $ref"])
@pytest.mark.parametrize("form", list(FORMS))
def test_generate_writes_the_declared_headers(tmp_path, fmt, ref_response, form):
    headers, want = FORMS[form]
    doc = OpenApiDoc.load(_write(tmp_path, _spec(headers, ref_response=ref_response), fmt))
    (op,) = doc.operations()
    scenario = build_mock_definition(doc, op)["scenarios"]["error_429"]
    assert scenario.get("headers") == want
    assert "headers" not in build_mock_definition(doc, op)["scenarios"]["default"]   # the 200 declares none


@pytest.mark.parametrize("fmt", ["json", "yaml"])
def test_a_generated_scenario_carries_every_required_header_so_check_finds_nothing(tmp_path, fmt):
    swagger = _write(tmp_path, _spec({"Retry-After": {"required": True, "schema": INT}},
                                     headers_200={"X-Total": {"required": True, "schema": INT}}), fmt)
    mocks = tmp_path / "mocks"
    generate([str(swagger)], mocks)
    report = generate([str(swagger)], mocks, check=True)
    assert [b for b in report.bodies if b.missing or b.extra or b.violations] == []


# ---------------------------------------------------------------- validator ----

def _validate(scenario: dict) -> list[str]:
    mock = {"source": {"method": "GET", "path": "/x"}, "activeScenario": "s", "scenarios": {"s": scenario}}
    result = ValidationResult(file_path=Path("x.mock.json"))
    MockValidator().validate(mock, "x.mock.json", result)
    return [m.message for m in result.errors + result.warnings]


def test_the_validator_takes_headers():
    assert _validate({"status": 429, "headers": {"Retry-After": "30", "X-Request-ID": "r-1"}, "body": {}}) == []


@pytest.mark.parametrize("headers, says", [
    (["Retry-After"], "must be an object"),
    ({"Retry-After": 30}, "a header's value is a string"),
    ({"Retry-After": "30\r\nX-Evil: 1"}, "line break"),
    ({"Retry After": "30"}, "is not a header name"),
    ({"content-type": "text/plain"}, "contentType"),
    ({"Content-Length": "3"}, "written by the server"),
])
def test_the_validator_names_a_header_the_server_would_not_send(headers, says):
    messages = _validate({"status": 429, "headers": headers, "body": {}})
    assert any(says in m for m in messages), messages


# ---------------------------------------------------------------- serve ----

def _serve(tmp_path: Path, scenario: dict):
    mocks = tmp_path / "mocks"
    path = mocks / "x" / "getX.mock.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"source": {"method": "GET", "path": "/x", "operationId": "getX"},
                                "activeScenario": "s", "scenarios": {"s": scenario}}), encoding="utf-8")
    srv = MockServer(MockStore.load(mocks), RunManager({}, tmp_path), port=0)
    srv.bind()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.1)
    request = urllib.request.Request(f"http://127.0.0.1:{srv.port}/x",
                                     headers={"Host": f"127.0.0.1:{srv.port}", "Origin": "http://localhost:5173"})
    try:
        with urllib.request.urlopen(request, timeout=5) as resp:
            got = resp.status, resp.headers
    except urllib.error.HTTPError as exc:
        got = exc.code, exc.headers
    srv.shutdown()
    return got


def test_serve_sends_a_scenarios_headers_and_exposes_them(tmp_path):
    status, headers = _serve(tmp_path, {"status": 429, "headers": {"Retry-After": "30", "X-Request-ID": "r-1"},
                                        "body": {"code": "rate_limited"}})
    assert status == 429 and headers["Retry-After"] == "30" and headers["X-Request-ID"] == "r-1"
    assert headers["Access-Control-Expose-Headers"] == "Retry-After, X-Request-ID"
    assert headers["Content-Type"] == "application/json"


def test_serve_sends_none_it_would_not(tmp_path):
    status, headers = _serve(tmp_path, {"status": 200, "headers": {"X-Evil": "1\r\nSet-Cookie: a=b", "Content-Type": "text/plain",
                                                                  "X-Ok": "yes"}, "body": {}})
    assert status == 200 and headers["X-Ok"] == "yes"
    assert headers.get("X-Evil") is None and headers.get("Set-Cookie") is None
    assert headers["Content-Type"] == "application/json" and headers["Access-Control-Expose-Headers"] == "X-Ok"


def test_serve_without_headers_sends_what_it_did(tmp_path):
    _, headers = _serve(tmp_path, {"status": 200, "body": {}})
    assert headers.get("Access-Control-Expose-Headers") is None


# ---------------------------------------------------------------- --check / --update-default ----

def _hand(mocks: Path, scenarios: dict) -> None:
    path = mocks / "x" / "getX.mock.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"source": {"method": "GET", "path": "/x", "operationId": "getX"},
                                "activeScenario": "default", "scenarios": scenarios}), encoding="utf-8")


def _found(report) -> dict:
    """Each hand-written scenario with a finding (an optional body field left out is not one)."""
    return {b.scenario: (b.missing, b.extra, [v.split(":")[0] for v in b.violations], b.declaration)
            for b in report.bodies if b.rel == "x/getX.mock.json"
            and (b.missing or b.extra or b.violations or b.declaration)}


@pytest.mark.parametrize("fmt", ["json", "yaml"])
def test_check_compares_the_headers(tmp_path, fmt):
    swagger = _write(tmp_path, _spec({"Retry-After": {"required": True, "schema": INT}}), fmt)
    mocks = tmp_path / "mocks"
    generate([str(swagger)], mocks)
    _hand(mocks, {
        "default": {"status": 200, "body": {"a": 1}},
        "right": {"status": 429, "headers": {"retry-after": "30"}, "body": {}},           # any case
        "absent": {"status": 429, "body": {}},
        "undeclared": {"status": 429, "headers": {"Retry-After": "30", "X-Request-ID": "r"}, "body": {}},
        "wrong": {"status": 429, "headers": {"Retry-After": "soon"}, "body": {}},
        "declared": {"status": 429, "headers": {"Retry-After": "30", "X-Request-ID": "r"}, "body": {},
                     "contractViolations": {"extra": ["headers.X-Request-ID"], "reason": "the gateway adds it"}},
    })
    got = _found(generate([str(swagger)], mocks, check=True))
    assert "right" not in got and "declared" not in got and "default" not in got, got
    assert got["absent"][0] == ["headers.Retry-After"]
    assert got["undeclared"][1] == ["headers.X-Request-ID"]
    assert got["wrong"][2] == ["headers.Retry-After"]


def test_check_compares_a_file_responses_headers(tmp_path):
    """A CSV export has no body to compare and still has its Content-Disposition."""
    swagger = _write(tmp_path, _spec({}, headers_200={"Content-Disposition": {"required": True, "schema": {"type": "string"}}},
                                     csv=True))
    mocks = tmp_path / "mocks"
    generate([str(swagger)], mocks)
    _hand(mocks, {"default": {"status": 200, "contentType": "text/csv", "bodyFile": None},
                  "named": {"status": 200, "contentType": "text/csv", "bodyFile": None,
                            "headers": {"Content-Disposition": 'attachment; filename="a.csv"'}},
                  "stale": {"status": 200, "contentType": "text/csv", "bodyFile": None,
                            "headers": {"Content-Disposition": "x"},
                            "contractViolations": {"missing": ["headers.Content-Disposition"], "reason": "r"}}})
    got = _found(generate([str(swagger)], mocks, check=True))
    assert got["default"][0] == ["headers.Content-Disposition"] and "named" not in got, got
    assert any("no longer violates" in d for d in got["stale"][3]), got


def test_update_default_adds_a_required_header(tmp_path):
    swagger = _write(tmp_path, _spec({}, headers_200={"X-Total": {"required": True, "schema": INT, "example": 3},
                                                      "X-Note": {"schema": {"type": "string"}, "example": "n"}}))
    mocks = tmp_path / "mocks"
    generate([str(swagger)], mocks)
    _hand(mocks, {"default": {"status": 200, "headers": {"X-Other": "kept"}, "body": {"a": 1}}})
    report = update_default([str(swagger)], mocks)
    assert report.added == {"x/getX.mock.json": ["headers.X-Total"]}
    data = json.loads((mocks / "x" / "getX.mock.json").read_text())
    assert data["scenarios"]["default"]["headers"] == {"X-Other": "kept", "X-Total": "3"}


# ---------------------------------------------------------------- branch-tests ----

SCENARIOS = {
    "success": {"status": 200, "body": {"order": {"id": "o1"}}},
    "conflict": {"status": 409, "body": {"error": {"code": "sold_out"}},
                 "headers": {"Retry-After": "30", "X-Evil": "a\nb"}},
}


def test_web_is_handed_the_headers_serve_sends(tmp_path):
    root = _project(tmp_path, BASIC, scenarios=SCENARIOS)
    text = bt.generate_branch_tests("checkout", root).test_file.read_text(encoding="utf-8")
    assert '"headers": {"Retry-After": "30"}' in text.replace("\n", "").replace("  ", " ") or '"Retry-After": "30"' in text
    assert "X-Evil" not in text


def test_android_and_ios_are_handed_the_headers_serve_sends(tmp_path):
    root = _project(tmp_path, BASIC, scenarios=SCENARIOS)
    kt = bt.generate_branch_tests("checkout", root, platform="android", package="com.example.checkout",
                                  out_dir="app/src/test/java", harness_dir="app/src/test/java").test_file.read_text()
    assert 'headers = mapOf("conflict" to mapOf("Retry-After" to "30"))' in kt and "X-Evil" not in kt
    swift = bt.generate_branch_tests("checkout", root, platform="ios", module="checkout_app").test_file.read_text()
    assert 'headers: ["conflict": ["Retry-After": "30"]]' in swift and "X-Evil" not in swift


def test_a_screen_without_headers_generates_what_it_did(tmp_path):
    root = _project(tmp_path, BASIC)
    for kw in ({}, {"platform": "android", "package": "com.example.checkout", "out_dir": "app/src/test/java",
                    "harness_dir": "app/src/test/java"}, {"platform": "ios", "module": "checkout_app"}):
        text = bt.generate_branch_tests("checkout", root, **kw).test_file.read_text()
        assert "headers = mapOf" not in text and "headers: [" not in text and '"headers"' not in text
