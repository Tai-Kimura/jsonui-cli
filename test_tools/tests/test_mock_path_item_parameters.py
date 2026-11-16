"""The mock reads an operation's parameters as OpenAPI says: the path item's
with the operation's, one of the same `name` and `in` on the operation taking
the inherited one's place, a $ref path item (3.1 `components.pathItems`)
followed (ticket jui-openapi-canonical-ignores-path-item-parameters). Until
jsonui-cli 2.3.36 both lists end to end — a parameter written on both checked
twice, the inherited declaration too — and a $ref path item had no
operations.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.openapi import OpenApiDoc


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


def test_each_parameter_once_as_the_operation_takes_it():
    got = {(o.method, o.path): [(p["in"], p["name"], p["schema"]["type"], p["required"]) for p in o.parameters]
           for o in OpenApiDoc(DOC).operations()}
    assert got == {
        ("GET", "/c"): [("query", "q", "integer", True)],
        ("GET", "/e/{id}"): [("path", "id", "string", True)],
        ("GET", "/g/{id}"): [("path", "id", "string", True)],
        ("GET", "/b/{id}"): [("path", "id", "string", True)],   # control
    }
