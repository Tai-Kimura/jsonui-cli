"""A path item's `parameters` are the operation's too (ticket
jui-openapi-canonical-ignores-path-item-parameters).

OpenAPI lets `parameters` be written once on the path item, beside `get` and
`patch`, for every operation under it; one of the same `name` and `in` on the
operation takes the inherited one's place. Until jsonui-cli 2.3.36 the canon
read the operation's own list only: `{id}` written on the path item was no
argument of a `@canonical` method, and a `$ref` parameter was none either —
without a word. `openapi-diff` (openapi_normalize) read them this way already;
the canon now agrees with it on every shape below.
"""

from __future__ import annotations

from jsonui_doc_cli import shared_core
from jsonui_doc_cli.check import openapi_normalize

canon = shared_core.openapi_canonical()


def P(name, where="path", required=True, t="string"):
    return {"name": name, "in": where, "required": required, "schema": {"type": t}}


OK = {"responses": {"200": {"description": "ok"}}}
DOC = {
    "openapi": "3.1.0",
    "components": {"parameters": {"Id": P("id")},
                   "pathItems": {"G": {"parameters": [P("id")], "get": dict(OK)}}},
    "paths": {
        "/a/{id}": {"parameters": [P("id")], "get": dict(OK), "patch": dict(OK)},
        "/b/{id}": {"get": {"parameters": [P("id")], **OK}},
        "/c": {"parameters": [P("q", "query", False, "string")],
               "get": {"parameters": [P("q", "query", True, "integer")], **OK}},
        "/e/{id}": {"parameters": [{"$ref": "#/components/parameters/Id"}], "get": dict(OK)},
        "/f/{id}": {"get": {"parameters": [{"$ref": "#/components/parameters/Id"}], **OK}},
        "/g/{id}": {"$ref": "#/components/pathItems/G"},
    },
}


def _canon():
    return {(op.method, op.path): [(p.location, p.name, p.type) for p in op.params]
            for op in canon.index_documents([("doc", DOC)]).values()}


def test_every_shape_is_read_as_openapi_diff_reads_it():
    got = _canon()
    assert got == {
        ("GET", "/a/{id}"): [("path", "id", "String")],
        ("PATCH", "/a/{id}"): [("path", "id", "String")],
        ("GET", "/b/{id}"): [("path", "id", "String")],
        ("GET", "/c"): [("query", "q", "Int")],          # the operation's wins
        ("GET", "/e/{id}"): [("path", "id", "String")],
        ("GET", "/f/{id}"): [("path", "id", "String")],
        ("GET", "/g/{id}"): [("path", "id", "String")],
    }
    norm = openapi_normalize.normalize_spec(DOC, "doc")
    ops = norm.operations.values() if isinstance(norm.operations, dict) else norm.operations
    assert {(o.method, o.path): sorted((k[0], k[1]) for k in o.parameters) for o in ops} == \
        {k: sorted((loc, name) for loc, name, _ in v) for k, v in got.items()}


def _expand(doc, endpoint):
    spec = {"dataFlow": {"repositories": [{"name": "R", "methods": [
        {"name": "m", "endpoint": endpoint, "params": "@canonical"}]}]}}
    errors, warnings = canon.resolve_spec_marks(spec, canon.index_documents([("doc", doc)]))
    return spec["dataFlow"]["repositories"][0]["methods"][0]["params"], errors, warnings


def test_the_tickets_shape_the_path_id_is_the_first_argument():
    doc = {"openapi": "3.0.3", "paths": {"/api/admin/receive-methods/{id}": {
        "parameters": [P("id")],
        "patch": {"requestBody": {"required": True, "content": {"application/json": {"schema": {
            "type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}}}}, **OK}}}}
    params, errors, warnings = _expand(doc, "PATCH /api/admin/receive-methods/{id}")
    assert params == [{"name": "id", "type": "String"}, {"name": "name", "type": "String"}]
    assert (errors, warnings) == ([], [])


def test_a_declaration_one_of_the_same_name_shadows_is_said():
    doc = {"openapi": "3.0.3", "paths": {"/d/{k}": {
        "parameters": [P("k")], "get": {"parameters": [P("k", "query", False)], **OK}}}}
    params, errors, warnings = _expand(doc, "GET /d/{k}")
    assert params == [{"name": "k", "type": "String"}]
    assert errors == []
    assert warnings == [("dataFlow.repositories[0].methods[0].params",
                         "query k is no argument: the operation declares another of the same name first, and a "
                         "method takes one argument per name. Rename one in the API document, or write the "
                         "params out.")]


def test_control_operation_level_parameters_expand_as_before():
    doc = {"openapi": "3.0.3", "paths": {"/b/{id}": {"get": {
        "parameters": [P("id"), P("limit", "query", False, "integer")], **OK}}}}
    params, errors, warnings = _expand(doc, "GET /b/{id}")
    assert params == [{"name": "id", "type": "String"}, {"name": "limit", "type": "Int?"}]
    assert (errors, warnings) == ([], [])
