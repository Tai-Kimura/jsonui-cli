"""Tests for request-side contract checking in `mock serve`.

Regression: mock-contract-validation-does-not-run.

The server answered from a fixed scenario without reading the request, so a
screen that omitted every required field, sent a mode *name* where the
contract wanted a uuid, and passed an empty string for an id kept the E2E
suite green for months. The real API returns 422 for all three.
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.contract import ContractIndex, ContractLog, RequestViolation
from jsonui_test_cli.mock.generate import generate
from jsonui_test_cli.mock.server import MockServer, MockStore, RunManager


SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/admin/reservations": {
            "post": {
                "operationId": "createReservation",
                "tags": ["AdminReservations"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/ReservationCreate"}}},
                },
                "responses": {"201": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/Reservation"}}}}},
            },
            "get": {
                "operationId": "listReservations",
                "tags": ["AdminReservations"],
                "parameters": [
                    {"name": "page", "in": "query", "required": True,
                     "schema": {"type": "integer"}},
                    {"name": "sort", "in": "query",
                     "schema": {"type": "string", "enum": ["asc", "desc"]}},
                ],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/Reservation"}}}}},
            },
        },
    },
    "components": {"schemas": {
        "ReservationCreate": {
            "type": "object",
            "required": ["usage_mode_id", "slot_id", "entry_date"],
            "properties": {
                "usage_mode_id": {"type": "string", "format": "uuid"},
                "slot_id": {"type": "string"},
                "entry_date": {"type": "string", "format": "date"},
                "guests": {"type": "integer"},
            },
        },
        "Reservation": {"type": "object", "properties": {"id": {"type": "string"}}},
    }},
}


@pytest.fixture
def spec_file(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(SPEC), encoding="utf-8")
    return str(path)


class TestContractIndex:
    def test_a_body_missing_required_fields_is_reported(self, spec_file):
        index = ContractIndex.load([spec_file])
        problems = index.check(
            "POST", "/api/admin/reservations", {},
            {"usage_mode_id": "daily", "slot_id": ""},
        )
        # The F-47 shape: entry_date absent entirely.
        assert any("entry_date" in p and "required" in p for p in problems)

    def test_a_wrong_type_in_the_body_is_reported(self, spec_file):
        index = ContractIndex.load([spec_file])
        problems = index.check(
            "POST", "/api/admin/reservations", {},
            {"usage_mode_id": "x", "slot_id": "s", "entry_date": "2026-01-01",
             "guests": "two"},
        )
        assert any("guests" in p and "contract says integer" in p for p in problems)

    def test_a_valid_body_is_clean(self, spec_file):
        index = ContractIndex.load([spec_file])
        assert index.check(
            "POST", "/api/admin/reservations", {},
            {"usage_mode_id": "x", "slot_id": "s", "entry_date": "2026-01-01"},
        ) == []

    def test_a_missing_body_on_a_required_request_body_is_reported(self, spec_file):
        index = ContractIndex.load([spec_file])
        problems = index.check("POST", "/api/admin/reservations", {}, None)
        assert problems == ["body: required by the contract, missing"]

    def test_a_missing_required_query_parameter_is_reported(self, spec_file):
        index = ContractIndex.load([spec_file])
        problems = index.check("GET", "/api/admin/reservations", {}, None)
        assert any("page" in p and "required" in p for p in problems)

    def test_a_query_value_outside_an_enum_is_reported(self, spec_file):
        index = ContractIndex.load([spec_file])
        problems = index.check(
            "GET", "/api/admin/reservations", {"page": ["1"], "sort": ["sideways"]}, None)
        assert any("sideways" in p for p in problems)

    def test_a_numeric_query_string_is_read_as_its_declared_type(self, spec_file):
        # Query values always arrive as strings; "1" is a valid integer.
        index = ContractIndex.load([spec_file])
        assert index.check(
            "GET", "/api/admin/reservations", {"page": ["1"], "sort": ["asc"]}, None) == []
        problems = index.check(
            "GET", "/api/admin/reservations", {"page": ["abc"]}, None)
        assert any("page" in p and "contract says integer" in p for p in problems)

    def test_an_unknown_route_is_not_second_guessed(self, spec_file):
        index = ContractIndex.load([spec_file])
        assert index.check("POST", "/api/not/in/spec", {}, {"anything": 1}) == []


class TestContractLog:
    def test_identical_violations_collapse_in_the_summary(self):
        log = ContractLog()
        for _ in range(3):
            log.record(RequestViolation("POST", "/api/x", "createX", ["body: bad"]))
        summary = log.summary()
        assert any("x3" in line for line in summary)
        assert sum(1 for line in summary if line.startswith("  POST")) == 1

    def test_summary_is_empty_when_nothing_was_recorded(self):
        assert ContractLog().summary() == []

    def test_only_violations_after_the_mark_are_summarised(self):
        log = ContractLog()
        log.record(RequestViolation("POST", "/api/before", "a", ["body: bad"]))
        mark = log.count()
        log.record(RequestViolation("POST", "/api/after", "b", ["body: bad"]))
        summary = log.summary(mark)
        assert any("/api/after" in line for line in summary)
        assert not any("/api/before" in line for line in summary)


class TestServing:
    """End to end through the real HTTP server."""

    @pytest.fixture
    def running(self, tmp_path, spec_file):
        mock_dir = tmp_path / "mocks"
        generate([spec_file], mock_dir)
        contract = ContractIndex.load([spec_file])
        log = ContractLog()
        server = MockServer(
            MockStore.load(mock_dir),
            RunManager({}, tmp_path, contract_log=log),
            port=0, contract=contract, contract_log=log,
        )
        server.bind()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.05)
        yield server, log
        server.shutdown()
        thread.join(timeout=2)

    def _post(self, server, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/api/admin/reservations",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read() or b"null")

    def test_a_violating_request_is_still_served(self, running):
        # Recorded, not enforced: a 422 here would turn "the implementation
        # is wrong" into "this screen should show an error".
        server, log = running
        status, _body = self._post(server, {"usage_mode_id": "daily", "slot_id": ""})
        assert status == 201
        assert log.count() == 1
        assert any("entry_date" in p for p in log.all()[0].problems)

    def test_a_valid_request_records_nothing(self, running):
        server, log = running
        status, _ = self._post(server, {
            "usage_mode_id": "u", "slot_id": "s", "entry_date": "2026-01-01"})
        assert status == 201
        assert log.count() == 0

    def test_violations_are_readable_through_the_admin_api(self, running):
        server, log = running
        self._post(server, {"slot_id": ""})
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/__jsonui__/contract-violations",
            headers={"X-JsonUI-Token": server.token},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read())
        assert data and data[0]["operationId"] == "createReservation"

    def test_a_scenario_can_opt_out(self, running):
        server, log = running
        endpoint = server.store.match("POST", "/api/admin/reservations")
        endpoint.scenarios[endpoint.active_scenario]["skipRequestValidation"] = True
        self._post(server, {"slot_id": ""})
        assert log.count() == 0


class TestOverlay:
    """A hand-written mock overlays the generated one, scenario by scenario."""

    def _tree(self, tmp_path, spec_file):
        mock_dir = tmp_path / "mocks"
        generate([spec_file], mock_dir)
        return mock_dir

    def test_a_thin_hand_written_file_adds_one_scenario(self, tmp_path, spec_file):
        # The point of the split: hand-written files carry only what the
        # tests drive; `empty` / `error_*` keep coming from the generated side.
        mock_dir = self._tree(tmp_path, spec_file)
        generated = json.loads(
            (mock_dir / "generated" / "adminreservations" / "createReservation.mock.json")
            .read_text(encoding="utf-8"))
        assert "default" in generated["scenarios"]

        thin = mock_dir / "adminreservations" / "createReservation.mock.json"
        thin.parent.mkdir(parents=True, exist_ok=True)
        thin.write_text(json.dumps({
            "source": {"operationId": "createReservation",
                       "method": "POST", "path": "/api/admin/reservations"},
            "activeScenario": "real_id",
            "scenarios": {"real_id": {"status": 201, "body": {"id": "res-42"}}},
        }), encoding="utf-8")

        store = MockStore.load(mock_dir)
        endpoint = store.match("POST", "/api/admin/reservations")
        assert set(endpoint.scenarios) >= {"default", "real_id"}
        assert endpoint.active_scenario == "real_id"
        assert endpoint.scenarios["real_id"]["body"]["id"] == "res-42"

    def test_a_hand_written_scenario_wins_over_the_generated_one(self, tmp_path, spec_file):
        mock_dir = self._tree(tmp_path, spec_file)
        thin = mock_dir / "adminreservations" / "createReservation.mock.json"
        thin.parent.mkdir(parents=True, exist_ok=True)
        thin.write_text(json.dumps({
            "source": {"operationId": "createReservation",
                       "method": "POST", "path": "/api/admin/reservations"},
            "scenarios": {"default": {"status": 201, "body": {"id": "mine"}}},
        }), encoding="utf-8")

        store = MockStore.load(mock_dir)
        endpoint = store.match("POST", "/api/admin/reservations")
        assert endpoint.scenarios["default"]["body"] == {"id": "mine"}

    def test_the_overlay_is_recorded_for_the_startup_log(self, tmp_path, spec_file):
        mock_dir = self._tree(tmp_path, spec_file)
        thin = mock_dir / "adminreservations" / "createReservation.mock.json"
        thin.parent.mkdir(parents=True, exist_ok=True)
        thin.write_text(json.dumps({
            "source": {"operationId": "createReservation",
                       "method": "POST", "path": "/api/admin/reservations"},
            "scenarios": {"default": {"status": 201, "body": {}}},
        }), encoding="utf-8")
        store = MockStore.load(mock_dir)
        assert store.overrides == ["adminreservations/createReservation.mock.json"]

    def test_a_generated_only_tree_serves_normally(self, tmp_path, spec_file):
        store = MockStore.load(self._tree(tmp_path, spec_file))
        assert store.match("POST", "/api/admin/reservations") is not None
        assert store.overrides == []
