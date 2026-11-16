"""One OpenAPI document, read one way by every reader of the family (2.3.21; the family table of ticket 2026-10-23-
jsonui-test-mock-generate-yaml-traceback).

The same document written as JSON and as YAML the way a person writes it — an unquoted date and time in an example
and a default, unquoted status codes — must give every reader the same data. Until 2.3.21 the readers disagreed: jui
build halted on the date, the canonical index held a date object, jsonui-test held the string, and an unquoted `200:`
ended `mock generate` in a traceback. Each reader is reached here through its own entry, across the three tools.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
for tool in ("test_tools", "document_tools"):
    if (REPO_ROOT / tool).is_dir() and str(REPO_ROOT / tool) not in sys.path:
        sys.path.append(str(REPO_ROOT / tool))

from jui_cli.core import shared_core  # noqa: E402
from tests.test_ls_cmd import _capture_stdout, _in_project, _write_config  # noqa: E402

DOC = {
    "openapi": "3.0.3", "info": {"title": "Dated", "version": "1"},
    "paths": {"/api/when": {"get": {"operationId": "getWhen", "responses": {
        "200": {"description": "ok", "content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/When"},
            "example": {"created": "2024-01-01", "at": "2024-01-01T10:00:00Z"}}}},
        "404": {"description": "none"}}}}},
    "components": {"schemas": {"When": {"type": "object", "properties": {
        "created": {"type": "string", "format": "date", "default": "2024-01-01"},
        "at": {"type": "string", "format": "date-time"}}}}},
}
# as a person writes it: no quotes on the date, the time or the status codes
YAML_TEXT = (yaml.safe_dump(DOC, sort_keys=False)
             .replace("'2024-01-01'", "2024-01-01").replace("'2024-01-01T10:00:00Z'", "2024-01-01T10:00:00Z")
             .replace("'200':", "200:").replace("'404':", "404:"))


@pytest.fixture
def both(tmp_path):
    """Two folders holding the one document: as JSON, and as hand-written YAML."""
    assert "created: 2024-01-01\n" in YAML_TEXT and "\n        200:\n" in YAML_TEXT   # the fixture is what it says
    j, y = tmp_path / "json/docs/api", tmp_path / "yaml/docs/api"
    j.mkdir(parents=True)
    y.mkdir(parents=True)
    (j / "api.json").write_text(json.dumps(DOC), encoding="utf-8")
    (y / "api.yaml").write_text(YAML_TEXT, encoding="utf-8")
    return j / "api.json", y / "api.yaml"


def test_the_shared_rule(both):
    of = shared_core.load("openapi_file")
    assert of.read(both[1]) == of.read(both[0]) == DOC


def test_jui_builds_loader(both):
    from jui_cli.core.openapi_loader import load_swagger

    def fields(folder):
        (doc,) = load_swagger(folder)
        return {s.name: [(f.wire_name, f.default) for f in s.fields] for s in doc.schemas}
    assert fields(both[1].parent) == fields(both[0].parent) == {"When": [("created", "2024-01-01"), ("at", None)]}


def test_jui_ls_api_specs(both, tmp_path):
    from jui_cli.commands.ls_cmd import cmd_ls

    got = []
    for doc in both:
        root = doc.parents[2]
        _write_config(root)
        with _in_project(root), _capture_stdout() as buf:
            assert cmd_ls(argparse.Namespace(ls_target="api-specs", as_json=True)) == 0
        (entry,) = json.loads(buf.getvalue())["files"]
        got.append({k: v for k, v in entry.items() if k not in ("path", "absolute_path")})
    assert got[0] == got[1] and got[0]["endpoint_count"] == 1, got


def test_the_canonical_index(both):
    canonical = shared_core.load("openapi_canonical")
    (j,), _ = canonical.load_documents(both[0].parent)
    (y,), missing = canonical.load_documents(both[1].parent)
    assert missing == 0 and y[1] == j[1] == DOC


def test_the_viz_rack(both):
    from jui_cli.viz import data_docs

    assert data_docs._swagger(both[1].read_bytes(), both[1].name) == data_docs._swagger(both[0].read_bytes(), both[0].name) == DOC


def test_jsonui_tests_reader(both):
    pytest.importorskip("jsonui_test_cli")
    from jsonui_test_cli.mock.openapi import OpenApiDoc

    assert OpenApiDoc.load(both[1]).spec == OpenApiDoc.load(both[0]).spec == DOC


def test_jsonui_docs_readers(both):
    pytest.importorskip("jsonui_doc_cli")
    from jsonui_doc_cli.test_doc.html.swagger import parse_swagger_file

    assert parse_swagger_file(both[1]) == parse_swagger_file(both[0]) == DOC


# ---- an answer that hangs on it: `@canonical.wire` names the success response's schema. Read with YAML 1.1's safe load
# the unquoted `200:` was the integer 200, no success response was found, and jui build (spec_extractor) and jsonui-doc
# validate refused the mark the JSON document resolved.
def _canon_project(root: Path, as_yaml: bool) -> Path:
    from tests.test_canonical_marks_agree_with_doc_tools import SPEC, SWAGGER

    (root / "docs/api").mkdir(parents=True)
    (root / "docs/screens").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps({"spec": {"canonical_param_case": "camelCase"}}), encoding="utf-8")
    if as_yaml:
        text = yaml.safe_dump(SWAGGER, sort_keys=False).replace("'200':", "200:")
        assert "\n        200:\n" in text or "200:\n" in text
        (root / "docs/api/swagger.yaml").write_text(text, encoding="utf-8")
    else:
        (root / "docs/api/swagger.json").write_text(json.dumps(SWAGGER), encoding="utf-8")
    spec = root / "docs/screens/b.spec.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    return spec


def test_jui_build_resolves_a_mark_from_yaml_as_from_json(tmp_path):
    from jui_cli.core.spec_extractor import extract_screen_spec

    def resolved(spec):
        m = extract_screen_spec(json.loads(spec.read_text()), spec).repositories[0].methods[0]
        return [(p.name, p.type) for p in m.params], m.return_type
    got = [resolved(_canon_project(tmp_path / k, k == "yaml")) for k in ("json", "yaml")]
    assert got[0] == got[1] and got[1][1] == "ItemListResponse", got


def test_jsonui_doc_validate_resolves_a_mark_from_yaml_as_from_json(tmp_path):
    pytest.importorskip("jsonui_doc_cli")
    from jsonui_doc_cli.spec_doc.validator import SpecValidationResult, SpecValidator

    def resolved(spec):
        data = json.loads(spec.read_text())
        v = SpecValidator()
        v._spec_file_path = spec
        result = SpecValidationResult()
        v._resolve_canonical_marks(data, result)
        m = data["dataFlow"]["repositories"][0]["methods"][0]
        return [e.message for e in result.errors], m["returnType"]
    got = [resolved(_canon_project(tmp_path / k, k == "yaml")) for k in ("json", "yaml")]
    assert got[0] == got[1] == ([], "ItemListResponse"), got


def test_a_number_key_written_as_json_writes_it_is_that_string(tmp_path):
    """`200:` and `1.5:` are the strings JSON holds; `"NO":` quoted is NO."""
    of = shared_core.load("openapi_file")
    (tmp_path / "a.yaml").write_text("x-flags:\n  200: ok\n  1.5: half\n  -1: minus\n  'NO': quoted\n", encoding="utf-8")
    assert of.read(tmp_path / "a.yaml") == {"x-flags": {"200": "ok", "1.5": "half", "-1": "minus", "NO": "quoted"}}


# ---- a key JSON would not hold as written halts every reader (ticket 2026-10-24-yaml-bool-mapping-key-silently-
# becomes-false). Up to 2.3.20 jui build's loader halted on every non-string key and the other readers did not read YAML;
# the pre-tag 2.3.21 load wrote each key as JSON would, so the property `NO` was generated as `false`, `~` as `null`,
# `010` as `8` — with nothing said, by all nine readers. The halt is in the one load (openapi_file.load_yaml), so each
# reader says it: the readers that raise name the text and its line; the canonical index leaves the document out and
# carries the line (jui build's marks and jsonui-doc validate say it); the viz rack, jsonui-doc's html and db-schema pass
# it by, as they pass any document they cannot read (and as they passed every YAML document up to 2.3.20).
TYPED = {   # the key as written -> what the halt names
    "        NO: {type: string}\n": "Mapping key NO (line 9) was implicitly typed as bool",
    "        yes: {type: string}\n": "Mapping key yes (line 9) was implicitly typed as bool",
    "        ~: {type: string}\n": "Mapping key ~ (line 9) was implicitly typed as NoneType",
    "        010: {type: string}\n": "Mapping key 010 (line 9) was implicitly typed as int",
    "        1.50: {type: string}\n": "Mapping key 1.50 (line 9) was implicitly typed as float",
    "        s: {type: string, enum: [NO, x]}\n": "Enum member NO (line 9) was implicitly typed as bool",
}
TYPED_HEAD = ("openapi: 3.0.3\ninfo: {title: T, version: '1'}\npaths: {}\ncomponents:\n  schemas:\n    M:\n      type: object\n"
              "      properties:\n")


def _every_reader(folder: Path) -> dict:
    """What each reader of the family made of the one document in folder: its error's line, or what it read."""
    from jui_cli.commands.ls_cmd import cmd_ls
    from jui_cli.core.openapi_loader import load_swagger
    from jui_cli.viz import data_docs
    from jsonui_doc_cli.check.db_schema.doc_parser import parse_db_docs
    from jsonui_doc_cli.check.openapi_diff import load_doc_side
    from jsonui_doc_cli.test_doc.html.swagger import parse_swagger_file
    from jsonui_test_cli.mock.openapi import OpenApiDoc, api_documents, read_document

    doc = folder / "api.yaml"

    def said(fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — the line each reader gives
            return f"ERR {exc}"

    def listed():
        _write_config(folder.parents[1])
        with _in_project(folder.parents[1]), _capture_stdout() as buf:
            cmd_ls(argparse.Namespace(ls_target="api-specs", as_json=True))
        (entry,) = json.loads(buf.getvalue())["files"]
        return f"ERR {entry['error']}" if "error" in entry else entry["schema_count"]

    def indexed():
        unread: list = []
        pairs, _ = shared_core.load("openapi_canonical").load_documents(folder, unread=unread)
        return f"ERR {unread[0]}" if unread else pairs[0][1]

    return {
        "the shared rule": said(lambda: shared_core.load("openapi_file").read(doc)),
        "jui build's loader": said(lambda: load_swagger(folder)),
        "jui ls api-specs": said(listed),
        "the canonical index": said(indexed),
        "jsonui-test mock": said(lambda: OpenApiDoc.load(doc).spec),
        "contracts coverage": said(lambda: read_document(api_documents(folder)[0])),
        "openapi-diff": said(lambda: load_doc_side(folder)),
        "the viz rack": said(lambda: data_docs._swagger(doc.read_bytes(), doc.name)),
        "jsonui-doc html": said(lambda: parse_swagger_file(doc)),
        "db-schema": said(lambda: parse_db_docs(folder)),
    }


def test_a_key_json_would_not_hold_as_written_halts_every_reader(tmp_path):
    pytest.importorskip("jsonui_test_cli")
    pytest.importorskip("jsonui_doc_cli")
    quiet = {"the viz rack": None, "jsonui-doc html": None, "db-schema": {}}   # as for any document they cannot read
    for n, (line, named) in enumerate(TYPED.items()):
        folder = tmp_path / f"p{n}/docs/api"
        folder.mkdir(parents=True)
        (folder / "api.yaml").write_text(TYPED_HEAD + line, encoding="utf-8")
        got = _every_reader(folder)
        for reader, answer in got.items():
            if reader in quiet:
                assert answer == quiet[reader], (line, reader, answer)
            else:
                assert isinstance(answer, str) and answer.startswith("ERR ") and named in answer, (line, reader, answer)
                assert "Quote the" in answer, (line, reader, answer)
    # the control: the same document with the key quoted is read by every reader, as NO; and a null enum member (a
    # nullable enum — JSON holds null in an enum, and jui build's walk always passed it) is read as None, not halted
    folder = tmp_path / "quoted/docs/api"
    folder.mkdir(parents=True)
    (folder / "api.yaml").write_text(TYPED_HEAD + "        'NO': {type: string}\n"
                                     "        s: {type: string, nullable: true, enum: [a, null]}\n"
                                     "        t: {type: string, nullable: true, enum: [a, ~]}\n", encoding="utf-8")
    got = _every_reader(folder)
    assert not [r for r, a in got.items() if isinstance(a, str) and a.startswith("ERR ")], got
    assert [f.wire_name for f in got["jui build's loader"][0].schemas[0].fields] == ["NO", "s", "t"]
    props = got["the shared rule"]["components"]["schemas"]["M"]["properties"]
    assert list(props) == ["NO", "s", "t"] and props["s"]["enum"] == props["t"]["enum"] == ["a", None], props
    # a YAML file beside the documents that the prefilter takes for one (`openapi:` at a line's start, inside a quoted
    # string) and is not — a workflow, with its `on:` — is still passed by, not halted on
    from jui_cli.core.openapi_loader import is_swagger_yaml_file, load_swagger

    (folder / "ci.yaml").write_text('on: push\nnote: "see the\nopenapi: 3 job"\n', encoding="utf-8")
    assert is_swagger_yaml_file(folder / "ci.yaml")
    assert [Path(d.source_path).name for d in load_swagger(folder)] == ["api.yaml"]


def test_a_mark_into_a_document_with_a_typed_key_names_the_key(tmp_path):
    """The canonical index leaves the document out; jui build and jsonui-doc validate say why, not "not declared"."""
    pytest.importorskip("jsonui_doc_cli")
    from jui_cli.core.spec_extractor import CanonicalMarkError, extract_screen_spec
    from jsonui_doc_cli.spec_doc.validator import SpecValidationResult, SpecValidator

    spec = _canon_project(tmp_path, True)
    doc = spec.parents[2] / "docs/api/swagger.yaml"
    doc.write_text(doc.read_text(encoding="utf-8").replace("components:\n", "x-flags:\n  NO: 1\ncomponents:\n", 1), encoding="utf-8")
    with pytest.raises(CanonicalMarkError, match=r"Mapping key NO \(line \d+\) was implicitly typed as bool"):
        extract_screen_spec(json.loads(spec.read_text()), spec)
    v = SpecValidator()
    v._spec_file_path = spec
    result = SpecValidationResult()
    v._resolve_canonical_marks(json.loads(spec.read_text()), result)
    assert any("Mapping key NO (line" in e.message and str(doc) in e.message for e in result.errors), [e.message for e in result.errors]


def test_a_mapping_inside_a_list_has_its_keys_as_json_writes_them(tmp_path):
    """Every mapping key, at any depth: one inside a list (a parameter's examples, an extension's samples) too."""
    of = shared_core.load("openapi_file")
    (tmp_path / "a.yaml").write_text(
        "x-samples:\n  - 200: {since: 2024-01-01}\n  - [{404: none}]\n"
        "parameters:\n  - name: day\n    in: query\n    examples:\n      2024: {value: 2024-01-01}\n", encoding="utf-8")
    assert of.read(tmp_path / "a.yaml") == {
        "x-samples": [{"200": {"since": "2024-01-01"}}, [{"404": "none"}]],
        "parameters": [{"name": "day", "in": "query", "examples": {"2024": {"value": "2024-01-01"}}}]}
