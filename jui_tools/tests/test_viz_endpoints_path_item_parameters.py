"""jui viz: an endpoint's parameters on the data shelf are what the operation
takes — the path item's with the operation's, the operation's winning a name
and `in` both write, a local $ref followed (shared/core/openapi_canonical.
path_item_operations; ticket jui-openapi-canonical-ignores-path-item-
parameters). Until jsonui-cli 2.3.36 both lists end to end: a parameter
written on both was shown twice, a $ref one as its pointer, and a $ref path
item not at all.
"""
from __future__ import annotations

from jui_cli.viz import data_docs


def P(name, where="path", required=True, t="string"):
    return {"name": name, "in": where, "required": required, "schema": {"type": t}}


OK = {"responses": {"200": {"description": "ok"}}}
DOC = {
    "openapi": "3.1.0",
    "components": {"parameters": {"Id": P("id")},
                   "pathItems": {"G": {"parameters": [P("id")], "get": dict(OK)}}},
    "paths": {
        "/c": {"parameters": [P("q", "query", False, "string")],
               "get": {"parameters": [P("q", "query", True, "integer")], **OK}},
        "/e/{id}": {"parameters": [{"$ref": "#/components/parameters/Id"}], "get": dict(OK)},
        "/g/{id}": {"$ref": "#/components/pathItems/G"},
        "/b/{id}": {"get": {"parameters": [P("id")], **OK}},
    },
}


def test_the_shelf_lists_each_parameter_once_as_the_operation_takes_it():
    got = {(e["method"], e["path"]): [(p["in"], p["name"], p["schema"]["type"]) for p in e["parameters"]]
           for e in data_docs._endpoints(DOC)}
    assert got == {
        ("GET", "/c"): [("query", "q", "integer")],
        ("GET", "/e/{id}"): [("path", "id", "string")],
        ("GET", "/g/{id}"): [("path", "id", "string")],
        ("GET", "/b/{id}"): [("path", "id", "string")],   # control
    }
