"""Tests for `mock` config normalisation.

Regression: test-mock-config-swagger-string-iterated-as-list.

Every consumer of this config iterates `swagger`, so a bare string — the
obvious thing to write — was opened one character at a time and failed with
`Is a directory: '.'`: an error that points at the filesystem instead of at
the key that is wrong.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.cli import _load_mock_config, _resolve_swaggers


def _config(tmp_path, mock_section):
    path = tmp_path / "jui.config.json"
    path.write_text(json.dumps({"mock": mock_section}), encoding="utf-8")
    return path


class TestSwaggerNormalisation:
    def test_a_bare_string_becomes_a_one_element_list(self, tmp_path):
        path = _config(tmp_path, {"swagger": "../docs/api/spec.json"})
        config, _ = _load_mock_config(str(path))
        assert config["swagger"] == ["../docs/api/spec.json"]

    def test_a_list_is_left_alone(self, tmp_path):
        path = _config(tmp_path, {"swagger": ["a.json", "b.json"]})
        config, _ = _load_mock_config(str(path))
        assert config["swagger"] == ["a.json", "b.json"]

    def test_a_missing_key_stays_missing(self, tmp_path):
        path = _config(tmp_path, {"mockDir": "tests/mocks"})
        config, _ = _load_mock_config(str(path))
        assert "swagger" not in config

    def test_an_unusable_type_is_dropped_with_a_message_naming_the_key(
            self, tmp_path, capsys):
        path = _config(tmp_path, {"swagger": 42})
        config, _ = _load_mock_config(str(path))
        assert config["swagger"] == []
        assert "mock.swagger" in capsys.readouterr().err

    def test_the_loaded_config_is_a_copy(self, tmp_path):
        # Normalising must not write the list back into the file on the next
        # save, nor mutate a shared dict.
        path = _config(tmp_path, {"swagger": "a.json"})
        _load_mock_config(str(path))
        assert json.loads(path.read_text(encoding="utf-8"))["mock"]["swagger"] == "a.json"


class TestResolveSwaggers:
    def test_relative_paths_resolve_against_the_config_directory(self, tmp_path):
        (tmp_path / "docs").mkdir()
        spec = tmp_path / "docs" / "spec.json"
        spec.write_text("{}", encoding="utf-8")
        proj = tmp_path / "proj"
        proj.mkdir()
        resolved = _resolve_swaggers(["../docs/spec.json"], proj, proj / "jui.config.json")
        assert resolved == [str(proj / ".." / "docs" / "spec.json")]

    def test_an_absolute_path_is_kept(self, tmp_path):
        spec = tmp_path / "spec.json"
        spec.write_text("{}", encoding="utf-8")
        assert _resolve_swaggers([str(spec)], tmp_path, None) == [str(spec)]

    def test_a_path_that_points_nowhere_names_the_config_key(self, tmp_path, capsys):
        resolved = _resolve_swaggers(["nope.json"], tmp_path, tmp_path / "jui.config.json")
        assert resolved == []
        err = capsys.readouterr().err
        assert "swagger not found" in err
        assert "mock.swagger" in err

    def test_one_bad_path_does_not_discard_the_good_ones(self, tmp_path):
        spec = tmp_path / "spec.json"
        spec.write_text("{}", encoding="utf-8")
        resolved = _resolve_swaggers(["spec.json", "nope.json"], tmp_path, None)
        assert resolved == [str(spec)]


class TestEndToEnd:
    """The reported symptom, through `validate`."""

    def _project(self, tmp_path, swagger_value):
        docs = tmp_path / "docs" / "api"
        docs.mkdir(parents=True)
        (docs / "spec.json").write_text(json.dumps({
            "openapi": "3.0.0",
            "paths": {"/api/x": {"get": {
                "tags": ["X"], "operationId": "getX",
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"type": "object", "properties": {"id": {"type": "string"}}}}}}},
            }}},
        }), encoding="utf-8")
        proj = tmp_path / "proj"
        (proj / "tests").mkdir(parents=True)
        (proj / "tests" / "mocks").mkdir()
        (proj / "tests" / "sample.test.json").write_text(json.dumps({
            "type": "screen",
            "metadata": {"name": "sample_test", "description": "d"},
            "cases": [{"name": "c", "description": "d",
                       "steps": [{"assert": "visible", "id": "root"}]}],
        }), encoding="utf-8")
        (proj / "jui.config.json").write_text(json.dumps({
            "mock": {"swagger": swagger_value, "mockDir": "tests/mocks"},
        }), encoding="utf-8")
        return proj

    @pytest.mark.parametrize("swagger_value", [
        "../docs/api/spec.json",
        ["../docs/api/spec.json"],
    ])
    def test_a_string_and_a_list_behave_identically(self, tmp_path, swagger_value):
        from jsonui_test_cli.cli import _check_mocks_against_swagger

        proj = self._project(tmp_path, swagger_value)
        cwd = os.getcwd()
        os.chdir(proj)
        try:
            assert _check_mocks_against_swagger(None) == 0
        finally:
            os.chdir(cwd)
        generated = list((proj / "tests" / "mocks" / "generated").rglob("*.mock.json"))
        assert len(generated) == 1
