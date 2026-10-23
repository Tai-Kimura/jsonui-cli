"""An OpenAPI document written in YAML (ticket 2026-10-23-jsonui-test-mock-generate-yaml-traceback).

`jsonui-test mock generate --swagger api.yaml` ended in a JSONDecodeError traceback with exit 1 (2.3.19, 2.3.20): every
jsonui-test reader took JSON only. They read YAML now by the rule shared/core/openapi_file.py holds; a document that
cannot be read is one line naming it, never a traceback; without PyYAML that line says what to do.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.contracts_coverage import load_api_index
from jsonui_test_cli.mock.contract import ContractIndex
from jsonui_test_cli.mock.generate import route_key

ROOT = Path(__file__).resolve().parent.parent
# the ticket's own document
DOC = yaml.safe_load("""
openapi: 3.0.3
info: {title: Items, version: "1"}
paths:
  /api/items:
    get:
      operationId: listItems
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  count: {type: integer, minimum: 1}
                  name: {type: string}
              example: {count: 3, name: "Pen"}
""")


def _cli(cwd, *args, no_pyyaml=False):
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    if no_pyyaml:   # a Python without PyYAML: `import yaml` fails
        stub = cwd / "no-yaml"
        stub.mkdir(exist_ok=True)
        (stub / "yaml.py").write_text("raise ImportError(\"No module named 'yaml'\")\n")
        env["PYTHONPATH"] = f"{stub}{os.pathsep}{ROOT}"
    return subprocess.run([sys.executable, "-m", "jsonui_test_cli.cli", *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=60)


def _tree(d: Path) -> dict:
    """Each generated file, its source.swagger (the document's own name) set aside."""
    out = {}
    for p in sorted(d.rglob("*")):
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data.get("source"), dict):
                data["source"].pop("swagger", None)
            out[p.relative_to(d).as_posix()] = data
    return out


def test_mock_generate_reads_yaml_and_yml_as_it_reads_json(tmp_path):
    (tmp_path / "api.json").write_text(json.dumps(DOC), encoding="utf-8")
    (tmp_path / "api.yaml").write_text(yaml.safe_dump(DOC), encoding="utf-8")
    (tmp_path / "api.yml").write_text(yaml.safe_dump(DOC), encoding="utf-8")
    trees = {}
    for name in ("api.json", "api.yaml", "api.yml"):
        got = _cli(tmp_path, "mock", "generate", "--swagger", name, "--out", f"out-{name}")
        assert got.returncode == 0 and "Traceback" not in got.stderr, (name, got.stdout, got.stderr)
        trees[name] = _tree(tmp_path / f"out-{name}")
    assert "generated/default/listItems.mock.json" in trees["api.yaml"]
    assert trees["api.yaml"] == trees["api.json"] == trees["api.yml"]


def test_a_document_that_cannot_be_read_is_one_line_and_exit_1(tmp_path):
    (tmp_path / "bad.yaml").write_text("openapi: [unclosed\n", encoding="utf-8")
    (tmp_path / "list.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    for name, why in (("bad.yaml", "not readable as YAML"), ("list.yaml", "not an OpenAPI document"), ("gone.yaml", "no such file")):
        got = _cli(tmp_path, "mock", "generate", "--swagger", name, "--out", "out")
        assert got.returncode == 1 and "Traceback" not in got.stderr, (name, got.stderr)
        assert got.stderr.strip().splitlines() == [got.stderr.strip()] and got.stderr.startswith(f"Error: {name}: {why}"), got.stderr


def test_without_pyyaml_a_yaml_document_says_what_to_do(tmp_path):
    (tmp_path / "api.yaml").write_text(yaml.safe_dump(DOC), encoding="utf-8")
    got = _cli(tmp_path, "mock", "generate", "--swagger", "api.yaml", "--out", "out", no_pyyaml=True)
    assert got.returncode == 1 and "Traceback" not in got.stderr, got.stderr
    assert got.stderr.strip() == "Error: api.yaml: a YAML OpenAPI document needs PyYAML (pip3 install pyyaml), or give its JSON form"


def test_help_says_json_or_yaml(tmp_path):
    got = _cli(tmp_path, "mock", "generate", "--help")
    assert "JSON or YAML" in " ".join(got.stdout.split()), got.stdout


def test_serve_says_which_document_it_could_not_read(tmp_path):
    """mock serve's request contract: a document it cannot read is named, not "no swagger configured"."""
    (tmp_path / "bad.yaml").write_text("openapi: [unclosed\n", encoding="utf-8")
    (tmp_path / "api.yaml").write_text(yaml.safe_dump(DOC), encoding="utf-8")
    index = ContractIndex.load([str(tmp_path / "bad.yaml"), str(tmp_path / "api.yaml")])
    assert list(index.operations) == [route_key("GET", "/api/items")]
    assert len(index.unread) == 1 and index.unread[0].startswith(f"{tmp_path / 'bad.yaml'}: not readable as YAML")


def test_contracts_find_a_yaml_document_in_the_api_directory(tmp_path):
    api = tmp_path / "docs/api"
    api.mkdir(parents=True)
    (api / "items.yml").write_text(yaml.safe_dump(DOC), encoding="utf-8")
    index = load_api_index([], api)
    assert index.elsewhere == {route_key("GET", "/api/items"): api / "items.yml"}


DATED = {"openapi": "3.0.3", "info": {"title": "Dated", "version": "1"},
         "paths": {"/api/when": {"get": {"operationId": "getWhen", "responses": {"200": {"description": "ok", "content": {
             "application/json": {"schema": {"type": "object", "properties": {"created": {"type": "string", "format": "date"},
                                                                             "at": {"type": "string", "format": "date-time"}}},
                                  "example": {"created": "2024-01-01", "at": "2024-01-01T10:00:00Z"}}}}}}}}}
# the same document as YAML writes it by hand: the example's date and time unquoted
DATED_YAML = yaml.safe_dump(DATED, sort_keys=False).replace("'2024-01-01'", "2024-01-01").replace("'2024-01-01T10:00:00Z'", "2024-01-01T10:00:00Z")


def test_an_unquoted_date_in_a_yaml_example_is_the_string_json_holds(tmp_path):
    """Found by the integration's check of 2.3.21: the date became a Python date, json.dump stopped at its key, a half
    written mock was left and the run said 0."""
    assert "created: 2024-01-01\n" in DATED_YAML   # the fixture is what it says
    (tmp_path / "api.yaml").write_text(DATED_YAML, encoding="utf-8")
    (tmp_path / "api.json").write_text(json.dumps(DATED), encoding="utf-8")
    trees = {}
    for name in ("api.yaml", "api.json"):
        got = _cli(tmp_path, "mock", "generate", "--swagger", name, "--out", f"out-{name}")
        assert got.returncode == 0 and "Traceback" not in got.stderr, (name, got.stderr)
        trees[name] = _tree(tmp_path / f"out-{name}")
    body = trees["api.yaml"]["generated/default/getWhen.mock.json"]["scenarios"]["default"]["body"]
    assert body == {"created": "2024-01-01", "at": "2024-01-01T10:00:00Z"}
    assert trees["api.yaml"] == trees["api.json"]


def test_a_mock_that_fails_to_write_leaves_no_half_file(tmp_path, monkeypatch):
    """Written whole or not at all: the text is put beside the file and moved over it."""
    from jsonui_test_cli.mock import generate as G

    (tmp_path / "api.json").write_text(json.dumps(DOC), encoding="utf-8")
    assert G.generate([str(tmp_path / "api.json")], tmp_path / "out") is not None
    target = tmp_path / "out" / "generated/default/listItems.mock.json"
    assert oct(target.stat().st_mode & 0o777) == oct(0o666 & ~_umask())   # a plain write's mode, not mkstemp's 0600
    monkeypatch.setattr(G, "build_mock_definition", lambda doc, op: {"body": object()})   # json cannot write it
    with pytest.raises(TypeError):
        G.generate([str(tmp_path / "api.json")], tmp_path / "out")
    # generated/ is rebuilt each run: the file is gone or whole, never cut at the value json could not write
    assert not target.exists() or json.loads(target.read_text(encoding="utf-8"))
    assert [p.name for p in target.parent.iterdir() if p.name.endswith(".tmp")] == []


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def test_the_validate_gate_says_a_document_it_cannot_read_in_one_line(tmp_path, capsys):
    from jsonui_test_cli.cli import _check_mocks_against_swagger

    (tmp_path / "bad.yaml").write_text("openapi: [unclosed\n", encoding="utf-8")
    (tmp_path / "tests/mocks").mkdir(parents=True)
    (tmp_path / "tests/mocks/m.mock.json").write_text(json.dumps({"scenarios": {}}), encoding="utf-8")
    (tmp_path / "jui.config.json").write_text(json.dumps({"mock": {"swagger": ["bad.yaml"], "mockDir": "tests/mocks"}}), encoding="utf-8")
    got = _check_mocks_against_swagger(str(tmp_path / "jui.config.json"))
    out = capsys.readouterr().out
    assert got == (1, None, 1, {}) and "Error: " in out and "not readable as YAML" in out and "Traceback" not in out, (got, out)
