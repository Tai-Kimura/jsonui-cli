"""The mock checker honours the project's declared API path scope.

Reproduces the reported shape: one swagger shared by several front-ends, each
declaring its slice in `api.schemas.include_paths`. Before this, every endpoint
belonging to another realm was reported MISSING — 66 of them, none reachable
from the app — so the gate was permanently red and the one MISSING that would
have mattered was invisible inside it.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.cli import _load_path_scope
from jsonui_test_cli.mock.generate import CheckReport, generate, update_default
from jsonui_test_cli.mock.scope import PathScope


def _op(operation_id, tag):
    return {
        "operationId": operation_id,
        "tags": [tag],
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["id"],
                            "properties": {"id": {"type": "string"}},
                        }
                    }
                }
            }
        },
    }


SHARED_SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/user/parks": {"get": _op("listUserParks", "User")},
        "/api/user/reservations": {"get": _op("listUserReservations", "User")},
        "/api/admin/parks": {"get": _op("listAdminParks", "Admin")},
        "/api/admin/users": {"get": _op("listAdminUsers", "Admin")},
        "/api/partner/slots": {"get": _op("listPartnerSlots", "Partner")},
    },
}

USER_SCOPE = PathScope(include=("/api/user/*",))


@pytest.fixture
def swagger(tmp_path):
    path = tmp_path / "shared.json"
    path.write_text(json.dumps(SHARED_SPEC), encoding="utf-8")
    return str(path)


class TestScopeMatching:
    def test_empty_scope_covers_everything(self):
        scope = PathScope()
        assert not scope.is_active()
        assert scope.covers("/api/admin/parks")

    def test_star_crosses_slashes(self):
        scope = PathScope(include=("/api/user/*",))
        assert scope.covers("/api/user/parks")
        assert scope.covers("/api/user/reservations/{id}/slots")
        assert not scope.covers("/api/admin/parks")

    def test_exclude_wins_over_include(self):
        scope = PathScope(include=("/api/*",), exclude=("/api/admin/*",))
        assert scope.covers("/api/user/parks")
        assert not scope.covers("/api/admin/parks")

    def test_patterns_are_anchored_at_both_ends(self):
        scope = PathScope(include=("/api/user",))
        assert scope.covers("/api/user")
        assert not scope.covers("/api/user/parks")
        assert not scope.covers("/prefix/api/user")


class TestConfigResolution:
    def _write(self, tmp_path, doc):
        (tmp_path / "jui.config.json").write_text(json.dumps(doc), encoding="utf-8")
        return tmp_path / "jui.config.json"

    def test_reads_the_same_keys_the_dto_codegen_filters_on(self, tmp_path):
        path = self._write(tmp_path, {
            "api": {"schemas": {
                "include_paths": ["/api/user/*"],
                "exclude_paths": [],
                "include_schemas": ["ErrorResponse"],
            }},
            "mock": {"swagger": "shared.json", "mockDir": "tests/mocks"},
        })
        scope = _load_path_scope(str(path))
        assert scope.include == ("/api/user/*",)
        assert scope.exclude == ()

    def test_mock_level_keys_win_when_present(self, tmp_path):
        path = self._write(tmp_path, {
            "api": {"schemas": {"include_paths": ["/api/user/*"]}},
            "mock": {"includePaths": ["/api/*"], "excludePaths": ["/api/admin/*"]},
        })
        scope = _load_path_scope(str(path))
        assert scope.include == ("/api/*",)
        assert scope.exclude == ("/api/admin/*",)

    def test_no_declaration_means_the_whole_swagger(self, tmp_path):
        path = self._write(tmp_path, {"mock": {"swagger": "shared.json"}})
        assert not _load_path_scope(str(path)).is_active()

    def test_a_bare_string_is_accepted_where_a_list_is_expected(self, tmp_path):
        path = self._write(tmp_path, {
            "api": {"schemas": {"include_paths": "/api/user/*"}}})
        assert _load_path_scope(str(path)).include == ("/api/user/*",)

    def test_mock_scope_can_widen_past_the_dto_scope(self, tmp_path):
        """A project that mocks more than it generates DTOs for opts out."""
        path = self._write(tmp_path, {
            "api": {"schemas": {"include_paths": ["/api/user/*"]}},
            "mock": {"includePaths": ["*"]},
        })
        scope = _load_path_scope(str(path))
        assert scope.covers("/api/admin/parks")


class TestOutOfScopeIsNotMissing:
    def test_the_reported_case_no_longer_fails(self, swagger, tmp_path):
        """Scoped project, mocks for its own realm only -> no drift."""
        mock_dir = tmp_path / "mocks"
        generate([swagger], mock_dir, scope=USER_SCOPE)
        report = generate([swagger], mock_dir, check=True, scope=USER_SCOPE)
        assert isinstance(report, CheckReport)
        assert report.missing == []
        assert not report.has_drift

    def test_without_a_scope_the_other_realms_are_still_reported(self, swagger, tmp_path):
        mock_dir = tmp_path / "mocks"
        generate([swagger], mock_dir, scope=USER_SCOPE)
        report = generate([swagger], mock_dir, check=True)
        assert len(report.missing) == 3  # admin x2, partner x1
        assert report.has_drift

    def test_out_of_scope_endpoints_are_not_scaffolded(self, swagger, tmp_path):
        mock_dir = tmp_path / "mocks"
        built = generate([swagger], mock_dir, scope=USER_SCOPE)
        assert len(built.created) == 2
        assert built.out_of_scope == [
            "GET /api/admin/parks", "GET /api/admin/users", "GET /api/partner/slots"]
        assert not list(mock_dir.rglob("*Admin*"))

    def test_an_in_scope_gap_is_still_reported(self, swagger, tmp_path):
        """The point of narrowing: the one that matters stays visible."""
        mock_dir = tmp_path / "mocks"
        generate([swagger], mock_dir, scope=USER_SCOPE)
        for path in mock_dir.rglob("listUserParks.mock.json"):
            path.unlink()
        report = generate([swagger], mock_dir, check=True, scope=USER_SCOPE)
        assert len(report.missing) == 1
        assert "/api/user/parks" in report.missing[0]

    def test_the_summary_states_what_was_excluded(self, swagger, tmp_path):
        mock_dir = tmp_path / "mocks"
        generate([swagger], mock_dir, scope=USER_SCOPE)
        report = generate([swagger], mock_dir, check=True, scope=USER_SCOPE)
        assert report.scope_excluded == 3
        assert report.scope_note == "include /api/user/*"


class TestOutOfScopeMockIsNotAnOrphan:
    def _mock_for(self, mock_dir, rel, method, path):
        target = mock_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "source": {"method": method, "path": path, "operationId": "x"},
            "scenarios": {"default": {"status": 200, "body": {"id": "1"}}},
        }), encoding="utf-8")

    def test_reported_separately_and_does_not_fail_the_check(self, swagger, tmp_path):
        mock_dir = tmp_path / "mocks"
        generate([swagger], mock_dir, scope=USER_SCOPE)
        self._mock_for(mock_dir, "admin/listAdminParks.mock.json",
                       "GET", "/api/admin/parks")

        report = generate([swagger], mock_dir, check=True, scope=USER_SCOPE)
        assert report.orphaned == []
        assert len(report.out_of_scope) == 1
        assert "/api/admin/parks" in report.out_of_scope[0]
        assert not report.has_drift

    def test_a_route_the_swagger_never_had_is_still_an_orphan(self, swagger, tmp_path):
        mock_dir = tmp_path / "mocks"
        generate([swagger], mock_dir, scope=USER_SCOPE)
        self._mock_for(mock_dir, "user/gone.mock.json", "GET", "/api/user/deleted")

        report = generate([swagger], mock_dir, check=True, scope=USER_SCOPE)
        assert len(report.orphaned) == 1
        assert report.out_of_scope == []
        assert report.has_drift


class TestUpdateDefaultRespectsScope:
    def test_out_of_scope_routes_are_not_counted_as_missing_files(self, swagger, tmp_path):
        mock_dir = tmp_path / "mocks"
        generate([swagger], mock_dir, scope=USER_SCOPE)
        upd = update_default([swagger], mock_dir, dry_run=True, scope=USER_SCOPE)
        assert upd.skipped == []

    def test_without_a_scope_they_are(self, swagger, tmp_path):
        mock_dir = tmp_path / "mocks"
        generate([swagger], mock_dir, scope=USER_SCOPE)
        upd = update_default([swagger], mock_dir, dry_run=True)
        assert len(upd.skipped) == 3
