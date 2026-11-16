"""properties together with a typed additionalProperties: one side is dropped, and a WARNING says which.

Ticket jui-api-model-properties-with-typed-additional-properties-drops-one-side.
The generated types stay as they were (a top-level schema keeps the
properties, a schema written in place is the map); every path that drops one
side prints one ``WARNING [api-model]`` on stderr naming the schema or the
place and the side dropped. ``additionalProperties: true`` (the documented
soft case: extra keys are ignored) prints nothing.
"""
from __future__ import annotations

import contextlib
import io
import unittest

from jui_cli.core.openapi_loader import parse_swagger

R = "#/components/schemas/"
MIXED = {"type": "object", "properties": {"id": {"type": "string"}, "rank": {"type": "integer"}},
         "additionalProperties": {"type": "string"}}
KEEPS_PROPS = "keeps the properties (id, rank) and drops every other key (the additionalProperties map)"
KEEPS_MAP = "is the additionalProperties map and drops the properties (id, rank)"
HOW = "Declare only the map, or only the properties."


def _parse(schemas: dict):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        doc = parse_swagger({"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {},
                             "components": {"schemas": schemas}}, "/r/s.json")
    return doc, [l for l in err.getvalue().splitlines() if "WARNING [api-model]" in l], out.getvalue()


class WarnsTests(unittest.TestCase):
    def _one(self, schemas, where, side):
        doc, warnings, stdout = _parse(schemas)
        self.assertEqual(stdout, "", "the loader runs inside MCP servers: nothing on stdout")
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn(f"WARNING [api-model]: {where} declares both properties and a typed additionalProperties; "
                      f"the generated type {side}. {HOW}", warnings[0])
        return {s.name: s for s in doc.schemas}

    def test_a_top_level_schema(self):
        by = self._one({"M": MIXED}, "schema 'M'", KEEPS_PROPS)
        self.assertEqual([f.wire_name for f in by["M"].fields], ["id", "rank"])   # type unchanged

    def test_a_field_written_in_place(self):
        by = self._one({"K": {"type": "object", "properties": {"f": MIXED}}},
                       "#/components/schemas/K/properties/f", KEEPS_MAP)
        self.assertTrue(by["K"].fields[0].type.is_map)

    def test_an_array_element_written_in_place(self):
        by = self._one({"K": {"type": "object", "properties": {"f": {"type": "array", "items": MIXED}}}},
                       "#/components/schemas/K/properties/f/items", KEEPS_MAP)
        self.assertTrue(by["K"].fields[0].type.element.is_map)

    def test_a_map_value_written_in_place(self):
        by = self._one({"K": {"type": "object", "properties": {
            "f": {"type": "object", "additionalProperties": MIXED}}}},
            "#/components/schemas/K/properties/f/additionalProperties", KEEPS_MAP)
        self.assertTrue(by["K"].fields[0].type.element.is_map)

    def test_a_schema_level_allof(self):
        by = self._one({"O": {"type": "object", "properties": {"id": {"type": "string"}, "rank": {"type": "integer"}}},
                        "M": {"allOf": [{"$ref": R + "O"}, {"additionalProperties": {"type": "string"}}]}},
                       "schema 'M'", KEEPS_PROPS)
        self.assertEqual([f.wire_name for f in by["M"].fields], ["id", "rank"])

    def test_the_documented_soft_case_and_the_plain_shapes_say_nothing(self):
        for schemas in (
            {"M": {"type": "object", "properties": {"id": {"type": "string"}}, "additionalProperties": True}},
            {"M": {"type": "object", "properties": {"id": {"type": "string"}}, "additionalProperties": False}},
            {"M": {"type": "object", "properties": {"id": {"type": "string"}}}},
            {"M": {"type": "object", "additionalProperties": {"type": "string"}}},
            {"K": {"type": "object", "properties": {"f": {"type": "object", "additionalProperties": {"type": "string"}}}}},
        ):
            _, warnings, _ = _parse(schemas)
            self.assertEqual(warnings, [], schemas)


if __name__ == "__main__":
    unittest.main()
