"""The generator does not write a body that violates its own contract.

Placeholder synthesis stopped at a fixed depth and returned `null` there.
Depth is a proxy for "this schema refers to itself": it stops the infinite
case, and it also stopped a consumer's legitimately eight-deep schema, so a
required non-nullable integer came out `null`. `--check` then reported the
generator's own output as stale and told the reader to regenerate — which
rewrote the identical bytes, so the warning could never clear. A permanent
warning is a warning that stops being read.

Two properties are pinned here:

- self-reference is detected directly, so a deep-but-finite schema is
  synthesised in full, and where synthesis genuinely cannot continue the
  value is the type's zero rather than `null`;
- the remedy printed with a finding is checked before it is printed: "regenerating
  fixes it" is only said when regeneration would actually change the file.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.openapi import OpenApiDoc


def nested(levels: int) -> dict:
    """A finite schema `levels` deep whose leaf is a required integer."""
    if levels == 0:
        return {"type": "object", "required": ["price"],
                "properties": {"price": {"type": "integer"}}}
    return {"type": "object", "required": ["inner"],
            "properties": {"inner": nested(levels - 1)}}


def leaf_of(sample):
    while isinstance(sample, dict) and "inner" in sample:
        sample = sample["inner"]
    return sample.get("price") if isinstance(sample, dict) else sample


class DeepButFiniteSchemasAreSynthesisedInFull:
    pass


class TestFiniteDepth:
    @pytest.mark.parametrize("levels", [7, 8, 9, 20])
    def test_a_required_integer_is_never_null(self, levels):
        # 8 was the old cap and the depth the reporting consumer's schema
        # actually reached — 7 passed and 8 did not, in the same file.
        doc = OpenApiDoc({})
        assert leaf_of(doc.sample_for_schema(nested(levels))) == 0

    def test_the_body_satisfies_the_schema_it_came_from(self):
        """The property the null broke: what the generator writes must pass
        the check the generator runs. Compared through the real comparator,
        not by eyeballing the value."""
        from jsonui_test_cli.mock.generate import compare_to_schema

        doc = OpenApiDoc({})
        schema = nested(9)
        found = compare_to_schema(doc, schema, doc.sample_for_schema(schema))
        assert found.violations == []
        assert found.missing == []


class TestSelfReference:
    def _doc(self):
        return OpenApiDoc({"components": {"schemas": {
            "Node": {"type": "object", "required": ["id", "child"],
                     "properties": {"id": {"type": "integer"},
                                    "child": {"$ref": "#/components/schemas/Node"}}}}}})

    def test_it_terminates_with_a_typed_value_not_null(self):
        sample = self._doc().sample_for_schema({"$ref": "#/components/schemas/Node"})
        assert sample["id"] == 0
        # `{}` may still miss required properties — the check names those
        # precisely. `null` would instead read as "integer, got null" and
        # point the reader at their schema rather than at the limit.
        assert sample["child"] == {}

    def test_mutual_recursion_terminates_too(self):
        doc = OpenApiDoc({"components": {"schemas": {
            "A": {"type": "object", "required": ["b"],
                  "properties": {"b": {"$ref": "#/components/schemas/B"}}},
            "B": {"type": "object", "required": ["a"],
                  "properties": {"a": {"$ref": "#/components/schemas/A"}}}}}})
        assert doc.sample_for_schema({"$ref": "#/components/schemas/A"}) == {"b": {"a": {}}}

    def test_a_repeated_ref_in_a_sibling_is_not_a_cycle(self):
        """The over-detection direction: the same `$ref` used twice side by
        side is ordinary reuse, not self-reference, and must synthesise
        fully both times."""
        doc = OpenApiDoc({"components": {"schemas": {
            "Money": {"type": "object", "required": ["amount"],
                      "properties": {"amount": {"type": "integer"}}},
            "Pair": {"type": "object", "required": ["a", "b"],
                     "properties": {"a": {"$ref": "#/components/schemas/Money"},
                                    "b": {"$ref": "#/components/schemas/Money"}}}}}})
        assert doc.sample_for_schema({"$ref": "#/components/schemas/Pair"}) == {
            "a": {"amount": 0}, "b": {"amount": 0}}


CYCLIC_SPEC = {
    "openapi": "3.0.3",
    "paths": {"/api/tree": {"get": {
        "operationId": "getTree", "tags": ["T"],
        "responses": {"200": {"content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/Node"}}}}}}}},
    "components": {"schemas": {"Node": {
        "type": "object", "required": ["id", "child"],
        "properties": {"id": {"type": "integer"},
                       "child": {"$ref": "#/components/schemas/Node"}}}}},
}


class TestTheRemedyIsCheckedBeforeItIsPrinted:
    @pytest.fixture
    def project(self, tmp_path):
        (tmp_path / "swagger.json").write_text(json.dumps(CYCLIC_SPEC),
                                               encoding="utf-8")
        (tmp_path / "jui.config.json").write_text(json.dumps(
            {"project_name": "t", "mock": {"swagger": ["swagger.json"],
                                           "mockDir": "tests/mocks"}}),
            encoding="utf-8")
        return tmp_path

    def test_a_body_generation_itself_produced_does_not_advise_regenerating(
            self, project):
        # A cyclic required property stops at `{}`, which the check reads as
        # a missing required field. Regenerating writes the same bytes, so
        # the advice would send the reader round a loop with no exit.
        from jsonui_test_cli.mock.generate import generate

        mocks = project / "tests" / "mocks"
        generate([str(project / "swagger.json")], mocks)
        report = generate([str(project / "swagger.json")], mocks, check=True)
        stale = report.stale_generated
        assert len(stale) == 1, stale
        assert stale[0].regenerating_helps is False

    def test_a_body_a_person_edited_still_advises_regenerating(self, project):
        from jsonui_test_cli.mock.generate import generate

        mocks = project / "tests" / "mocks"
        generate([str(project / "swagger.json")], mocks)
        target = next(mocks.rglob("*.mock.json"))
        data = json.loads(target.read_text(encoding="utf-8"))
        data["scenarios"]["default"]["body"] = {"id": "not-an-integer"}
        target.write_text(json.dumps(data), encoding="utf-8")

        report = generate([str(project / "swagger.json")], mocks, check=True)
        edited = [b for b in report.stale_generated
                  if any("id" in v for v in b.violations)]
        assert edited and edited[0].regenerating_helps is True


class TestGeneratorSourcesAreWarningFree:
    """No module emits a SyntaxWarning when imported.

    A Swift interpolation (`\\(name)`) written into a non-raw Python string
    is an unknown escape: CPython keeps it verbatim today, so the emitted
    Swift is correct, and warns that a future version will make it a
    SyntaxError. The cost before then is not cosmetic either — the MCP
    tool surfaces the warning in its `errors` field, so a *successful*
    call comes back with errors non-empty and a real one has somewhere to
    hide.

    Compiled here rather than grepped: the warning is the compiler's
    verdict, and a grep for the pattern would have to re-implement "is
    this escape known", which is the thing being checked.

    `compile()` rather than importing, for two measured reasons. Neither is
    deduplication, which is what a first pass here wrongly claimed:

    - CPython emits one SyntaxWarning per *string literal*, not per
      occurrence, so the three that prompted this — all inside one
      triple-quoted Swift template — could only ever surface as one. And
      `-W error` aborts the compile at the first, capping any run at one
      however many literals offend. A count from a single run is not a
      census, so this asserts on the whole set.
    - SyntaxWarning is a compile-time verdict, so a warm `__pycache__`
      makes an import silent — `-W error::SyntaxWarning` does not even
      promote, and exits 0. It is bistable and the state is invisible from
      the output: `-W error` never writes a .pyc for an offending module
      (the compile fails), so the module is either permanently cold and
      always reports, or was warmed by an earlier ordinary run and is
      permanently silent. `compile()` reads the source and bypasses the
      cache, which is the only form that reproduces.
    """

    def test_no_module_warns_on_compile(self):
        import pathlib
        import warnings

        root = pathlib.Path(__file__).resolve().parents[1] / "jsonui_test_cli"
        offenders = []
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for path in sorted(root.rglob("*.py")):
                if "__pycache__" in str(path):
                    continue
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            for entry in caught:
                if issubclass(entry.category, SyntaxWarning):
                    offenders.append(f"{entry.filename}:{entry.lineno}: {entry.message}")
        assert offenders == [], "\n".join(offenders)
