"""Every reader of an OpenAPI document takes JSON and YAML alike (ticket 2026-10-23-jsonui-test-mock-generate-yaml-
traceback: `jsonui-test mock generate --swagger api.yaml` ended in a JSONDecodeError traceback, and five other readers
passed a YAML document by without a word).

The rule is shared/core/openapi_file.py; this file holds its arms and those of the jui_tools readers that follow it
(`jui ls api-specs`, the viz data server's rack). test_tools and document_tools hold their own readers' arms.
"""
from __future__ import annotations

import argparse
import builtins
import json
from pathlib import Path

import pytest
import yaml

from jui_cli.core import shared_core
from tests.test_ls_cmd import _capture_stdout, _in_project, _write_config
from tests.test_viz_data_docs import API, _project, _room

OF = shared_core.load("openapi_file")
DOC = {"openapi": "3.0.3", "info": {"title": "Items", "version": "1"},
       "paths": {"/api/items": {"get": {"operationId": "listItems", "responses": {"200": {"description": "ok"}}}}}}


@pytest.fixture
def no_pyyaml(monkeypatch):
    """`import yaml` fails, as in a Python without PyYAML."""
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "yaml" or name.startswith("yaml."):
            raise ImportError("No module named 'yaml'")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)


def test_the_same_document_reads_the_same_as_json_yaml_and_yml(tmp_path):
    for name, text in (("a.json", json.dumps(DOC)), ("a.yaml", yaml.safe_dump(DOC)), ("a.yml", yaml.safe_dump(DOC)),
                       ("a.openapi", yaml.safe_dump(DOC))):   # another name: JSON, then YAML
        (tmp_path / name).write_text(text, encoding="utf-8")
        assert OF.read(tmp_path / name) == DOC, name


def test_a_document_that_cannot_be_read_is_one_line_naming_it(tmp_path):
    (tmp_path / "bad.yaml").write_text("openapi: [unclosed\n", encoding="utf-8")
    (tmp_path / "bad.json").write_text("{nope", encoding="utf-8")
    for name, why in (("bad.yaml", "not readable as YAML"), ("bad.json", "not readable as JSON"), ("gone.yaml", "no such file")):
        with pytest.raises(OF.OpenApiFileError) as got:
            OF.read(tmp_path / name)
        line = str(got.value)
        assert line.startswith(f"{tmp_path / name}: {why}") and "\n" not in line, line


def test_without_pyyaml_a_yaml_document_says_what_to_do(tmp_path, no_pyyaml):
    (tmp_path / "api.yaml").write_text(yaml.safe_dump(DOC), encoding="utf-8")
    with pytest.raises(OF.OpenApiFileError) as got:
        OF.read(tmp_path / "api.yaml")
    assert str(got.value) == OF.NEEDS_PYYAML.format(path=tmp_path / "api.yaml")
    assert "pip3 install pyyaml" in str(got.value)


def test_documents_lists_the_three_extensions_below_a_folder(tmp_path):
    for rel in ("a.json", "b.yaml", "sub/c.yml", "notes.md", "d.txt"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("{}", encoding="utf-8")
    assert [p.relative_to(tmp_path).as_posix() for p in OF.documents(tmp_path)] == ["a.json", "b.yaml", "sub/c.yml"]
    assert OF.documents(tmp_path / "missing") == []


def test_jui_ls_api_specs_lists_a_yaml_document_as_jui_build_reads_it(tmp_path):
    """Before 2.3.21 `jui ls api-specs` (MCP list_api_specs) took *.json only: a YAML document `jui build` reads was
    not in the list."""
    from jui_cli.commands.ls_cmd import cmd_ls

    _write_config(tmp_path)
    api = tmp_path / "docs/api"
    api.mkdir(parents=True)
    (api / "items.yaml").write_text(yaml.safe_dump(DOC), encoding="utf-8")
    (api / "other.yml").write_text("kind: not-openapi\n", encoding="utf-8")   # a YAML that is no document: left out
    with _in_project(tmp_path), _capture_stdout() as buf:
        assert cmd_ls(argparse.Namespace(ls_target="api-specs", as_json=True)) == 0
    files = json.loads(buf.getvalue())["files"]
    assert [f["path"] for f in files] == ["docs/api/items.yaml"] and files[0]["title"] == "Items" and files[0]["endpoint_count"] == 1, files


def test_the_viz_rack_counts_and_reads_a_yaml_document(tmp_path):
    from jui_cli.viz import data_docs

    root = _room(tmp_path / "app", api=False, db=False)
    (root / "docs/api").mkdir(parents=True)
    (root / "docs/api/users.yaml").write_text(yaml.safe_dump(API, allow_unicode=True), encoding="utf-8")
    assert data_docs.counts(_project(root)) == {"api": 1, "db": 0}
    got = data_docs.read(_project(root))
    assert [d["file"] for d in got["api"]] == ["docs/api/users.yaml"], got


def test_an_unquoted_date_or_time_stays_the_string_json_would_hold(tmp_path):
    """YAML 1.1's safe load makes `2024-01-01` a date: no JSON writer takes it, and it stopped `mock generate` half way
    through a mock (found by the integration's check of 2.3.21). Read here it is the string a JSON document holds."""
    (tmp_path / "a.yaml").write_text("example: {created: 2024-01-01, at: 2024-01-01T10:00:00Z, n: 3, ok: true}\n", encoding="utf-8")
    got = OF.read(tmp_path / "a.yaml")
    assert got == {"example": {"created": "2024-01-01", "at": "2024-01-01T10:00:00Z", "n": 3, "ok": True}}
    assert json.dumps(got)   # what a JSON writer does with it
