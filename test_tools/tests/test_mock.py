"""Tests for API mock generation, validation, and server routing."""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.openapi import OpenApiDoc, slugify, _fallback_operation_id
from jsonui_test_cli.mock.generate import generate, mock_relpath, build_mock_definition
from jsonui_test_cli.mock.server import MockStore, MockServer, RunManager, _path_to_regex
from jsonui_test_cli.validation.validator import TestValidator as _Validator


SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/v1/stocks": {
            "get": {
                "operationId": "listStocks",
                "tags": ["Stocks"],
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/StockList"}}}},
                    "500": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                },
            }
        },
        "/v1/stocks/{id}": {
            "get": {
                "operationId": "getStock",
                "tags": ["Stocks"],
                "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Stock"}}}}},
            }
        },
        "/v1/report": {
            "get": {
                "tags": ["Import / Customs"],  # slash in tag, missing operationId
                "responses": {"200": {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
            }
        },
    },
    "components": {
        "schemas": {
            "Stock": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "name": {"type": "string"},
                    "qty": {"type": "integer"},
                },
            },
            "StockList": {
                "type": "object",
                "properties": {"items": {"type": "array", "items": {"$ref": "#/components/schemas/Stock"}}},
            },
            "Error": {"type": "object", "properties": {"detail": {"type": "string"}}},
        }
    },
}


@pytest.fixture
def doc():
    return OpenApiDoc(SPEC, source_path="spec.json")


class TestOpenApi:
    def test_enumerate_operations(self, doc):
        ops = {o.operation_id: o for o in doc.operations()}
        assert "listStocks" in ops
        assert ops["listStocks"].method == "GET"
        assert ops["listStocks"].tag == "Stocks"

    def test_fallback_operation_id(self, doc):
        ops = doc.operations()
        report_op = next(o for o in ops if o.path == "/v1/report")
        assert report_op.id_was_synthesized
        assert report_op.operation_id == _fallback_operation_id("get", "/v1/report")

    def test_ref_resolution_and_sample(self, doc):
        schema, ctype = doc.success_schema(next(o for o in doc.operations() if o.operation_id == "listStocks"))
        assert ctype == "application/json"
        sample = doc.sample_for_schema(schema)
        assert "items" in sample
        assert isinstance(sample["items"], list) and sample["items"]
        assert sample["items"][0]["id"] == "00000000-0000-0000-0000-000000000000"

    def test_non_json_response(self, doc):
        op = next(o for o in doc.operations() if o.path == "/v1/report")
        schema, ctype = doc.success_schema(op)
        assert ctype == "application/pdf"

    def test_slugify(self):
        assert slugify("Import / Customs") == "import-customs"
        assert slugify("Stocks") == "stocks"


class TestGenerate:
    def test_generate_creates_files(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(SPEC))
        out = tmp_path / "mocks"
        report = generate([str(spec_file)], out)
        assert len(report.created) == 3
        # tag slug dir
        assert (out / "stocks" / "listStocks.mock.json").exists()
        assert (out / "import-customs").exists()
        # error + empty scenarios synthesized
        data = json.loads((out / "stocks" / "listStocks.mock.json").read_text())
        assert "empty" in data["scenarios"]
        assert "error_500" in data["scenarios"]
        assert data["scenarios"]["empty"]["body"]["items"] == []

    def test_regenerate_skips_existing(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(SPEC))
        out = tmp_path / "mocks"
        generate([str(spec_file)], out)
        report2 = generate([str(spec_file)], out)
        assert report2.created == []
        assert len(report2.skipped) == 3

    def test_check_detects_drift(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(SPEC))
        out = tmp_path / "mocks"
        generate([str(spec_file)], out)
        report = generate([str(spec_file)], out, check=True)
        assert not report.has_drift
        # remove one file -> missing
        (out / "stocks" / "listStocks.mock.json").unlink()
        report2 = generate([str(spec_file)], out, check=True)
        assert report2.has_drift
        assert any("listStocks" in m for m in report2.missing)


class TestRouting:
    def test_static_beats_param(self):
        # /v1/stocks (static) must not be shadowed by /v1/stocks/{id}
        assert _path_to_regex("/v1/stocks").match("/v1/stocks")
        assert not _path_to_regex("/v1/stocks").match("/v1/stocks/5")
        assert _path_to_regex("/v1/stocks/{id}").match("/v1/stocks/5")

    def test_store_match_priority(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(SPEC))
        out = tmp_path / "mocks"
        generate([str(spec_file)], out)
        store = MockStore.load(out)
        assert store.match("GET", "/v1/stocks").operation_id == "listStocks"
        assert store.match("GET", "/v1/stocks/abc").operation_id == "getStock"


class TestValidation:
    def test_valid_mock_passes(self, tmp_path):
        f = tmp_path / "x.mock.json"
        f.write_text(json.dumps({
            "source": {"method": "GET", "path": "/v1/x"},
            "activeScenario": "default",
            "scenarios": {"default": {"status": 200, "body": {}}},
        }))
        result = _Validator().validate_file(f)
        assert result.is_valid

    def test_bad_active_scenario_fails(self, tmp_path):
        f = tmp_path / "x.mock.json"
        f.write_text(json.dumps({
            "source": {"method": "GET", "path": "/v1/x"},
            "activeScenario": "nope",
            "scenarios": {"default": {"status": 200}},
        }))
        result = _Validator().validate_file(f)
        assert not result.is_valid

    def test_missing_status_fails(self, tmp_path):
        f = tmp_path / "x.mock.json"
        f.write_text(json.dumps({
            "source": {"method": "GET", "path": "/v1/x"},
            "scenarios": {"default": {"body": {}}},
        }))
        result = _Validator().validate_file(f)
        assert not result.is_valid


class TestMockReferences:
    """Root `mocks` (screen tests) and `setMocks` steps are checked against tests/mocks."""

    def _project(self, tmp_path):
        from jsonui_test_cli.validation.mock import _MOCK_INDEX_CACHE
        _MOCK_INDEX_CACHE.clear()
        mdir = tmp_path / "tests" / "mocks" / "stocks"
        mdir.mkdir(parents=True)
        (mdir / "listStocks.mock.json").write_text(json.dumps({
            "source": {"method": "GET", "path": "/v1/stocks", "operationId": "listStocks"},
            "activeScenario": "default",
            "scenarios": {"default": {"status": 200}, "empty": {"status": 200}},
        }))
        sdir = tmp_path / "tests" / "screens"
        sdir.mkdir(parents=True)
        return sdir

    def test_valid_root_mocks_passes(self, tmp_path):
        sdir = self._project(tmp_path)
        f = sdir / "ok.test.json"
        f.write_text(json.dumps({
            "type": "screen", "source": {"layout": "L.json"}, "metadata": {},
            "mocks": {"listStocks": "empty"},
            "cases": [{"name": "c", "description": "d", "steps": [{"assert": "visible", "id": "x"}]}],
        }))
        assert _Validator().validate_file(f).is_valid

    def test_unknown_scenario_errors(self, tmp_path):
        sdir = self._project(tmp_path)
        f = sdir / "bad.test.json"
        f.write_text(json.dumps({
            "type": "screen", "source": {"layout": "L.json"}, "metadata": {},
            "mocks": {"listStocks": "nope"},
            "cases": [{"name": "c", "description": "d", "steps": [{"assert": "visible", "id": "x"}]}],
        }))
        result = _Validator().validate_file(f)
        assert not result.is_valid
        assert any("no scenario 'nope'" in e.message for e in result.errors)

    def test_setmocks_unknown_op_errors(self, tmp_path):
        sdir = self._project(tmp_path)
        f = sdir / "flow.test.json"
        f.write_text(json.dumps({
            "type": "screen", "source": {"layout": "L.json"}, "metadata": {},
            "cases": [{"name": "c", "description": "d", "steps": [
                {"action": "setMocks", "mocks": {"ghostOp": "default"}}]}],
        }))
        result = _Validator().validate_file(f)
        assert not result.is_valid
        assert any("unknown mock operationId 'ghostOp'" in e.message for e in result.errors)

    def test_no_mockdir_skips_existence(self, tmp_path):
        from jsonui_test_cli.validation.mock import _MOCK_INDEX_CACHE
        _MOCK_INDEX_CACHE.clear()
        # test file with no discoverable tests/mocks dir: shape ok -> valid
        f = tmp_path / "lonely.test.json"
        f.write_text(json.dumps({
            "type": "screen", "source": {"layout": "L.json"}, "metadata": {},
            "mocks": {"anyOp": "anyScenario"},
            "cases": [{"name": "c", "description": "d", "steps": [{"assert": "visible", "id": "x"}]}],
        }))
        assert _Validator().validate_file(f).is_valid


class TestServer:
    @pytest.fixture
    def server(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(SPEC))
        out = tmp_path / "mocks"
        generate([str(spec_file)], out)
        store = MockStore.load(out)
        srv = MockServer(store, RunManager({}, tmp_path), port=0)
        srv.bind()  # discover ephemeral port before serving
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.1)
        yield srv
        srv.shutdown()

    def _req(self, server, method, path, token=None, body=None, host=None):
        host = host or f"127.0.0.1:{server.port}"
        headers = {"Host": host}
        if token:
            headers["X-JsonUI-Token"] = token
        data = json.dumps(body).encode() if body is not None else None
        url = f"http://127.0.0.1:{server.port}{path}"
        req = urllib.request.Request(url, method=method, headers=headers, data=data)
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_mock_default_and_scenario_switch(self, server):
        status, body = self._req(server, "GET", "/v1/stocks")
        assert status == 200 and "items" in body
        status, _ = self._req(server, "POST", "/__jsonui__/scenario-set", token=server.token,
                              body={"mocks": {"listStocks": "empty"}})
        assert status == 200
        status, body = self._req(server, "GET", "/v1/stocks")
        assert json.loads(body)["items"] == []

    def test_admin_requires_token(self, server):
        status, _ = self._req(server, "GET", "/__jsonui__/mocks")
        assert status == 401
        status, _ = self._req(server, "GET", "/__jsonui__/mocks", token=server.token)
        assert status == 200

    def test_bad_host_rejected(self, server):
        status, _ = self._req(server, "GET", "/v1/stocks", host="evil.example.com")
        assert status == 403

    def test_unmatched_recorded(self, server):
        status, _ = self._req(server, "GET", "/v1/does-not-exist")
        assert status == 404
        status, body = self._req(server, "GET", "/__jsonui__/requests", token=server.token)
        recs = json.loads(body)
        assert any(r["path"] == "/v1/does-not-exist" and r["matched"] is None for r in recs)

    def test_run_rejects_unknown_target(self, server):
        status, body = self._req(server, "POST", "/__jsonui__/run", token=server.token, body={"target": "nope"})
        assert status == 409
        assert "unknown target" in body

    def test_get_definition_includes_bodies(self, server):
        status, body = self._req(server, "GET", "/__jsonui__/mocks/listStocks", token=server.token)
        assert status == 200
        data = json.loads(body)
        # editor needs full scenario bodies, not just names
        assert "items" in data["scenarios"]["default"]["body"]
        assert data["scenarios"]["empty"]["body"]["items"] == []

    def test_get_definition_unknown(self, server):
        status, _ = self._req(server, "GET", "/__jsonui__/mocks/doesNotExist", token=server.token)
        assert status == 404

    def test_panel_served_with_token(self, server):
        status, body = self._req(server, "GET", "/__jsonui__/panel")
        assert status == 200
        assert server.token in body

    def test_put_rejects_path_traversal(self, server):
        status, _ = self._req(server, "PUT", "/__jsonui__/mocks/..%2f..%2fetc",
                              token=server.token, body={"scenario": "default", "payload": {}})
        assert status in (400, 404)


class TestRunManager:
    def test_read_results_from_target(self, tmp_path):
        from jsonui_test_cli.mock.server import RunManager
        (tmp_path / "jsonui-results.json").write_text(json.dumps(
            {"format": "jsonui-test-results", "version": 1, "suites": []}))
        rm = RunManager({"web": {"command": "true", "cwd": ".", "resultsPath": "jsonui-results.json"}}, tmp_path)
        rm._last_target = "web"  # simulate a completed run
        results = rm.read_results()
        assert results is not None and results["format"] == "jsonui-test-results"

    def test_read_results_none_without_run(self, tmp_path):
        from jsonui_test_cli.mock.server import RunManager
        rm = RunManager({"web": {"command": "true"}}, tmp_path)
        assert rm.read_results() is None

    def test_read_results_blocks_escape(self, tmp_path):
        from jsonui_test_cli.mock.server import RunManager
        rm = RunManager({"web": {"command": "true", "cwd": ".", "resultsPath": "../../etc/passwd"}}, tmp_path)
        rm._last_target = "web"
        assert rm.read_results() is None
