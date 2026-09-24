"""A repositories / useCases method's `platforms` is declared in the spec schema.

Three readers already used the field — the spec validator (it suggests
`platforms: ["ios"]` for a method typed with iOS-only types), `jui generate
project` (it leaves the method out of the other platforms' Repository /
UseCase protocols) and, from 1.8.118, `jsonui-test contracts coverage` — while
the schema declared `platforms` on metadata, viewModelVar, unreachedOp,
excludedOutcome and branchEntry only. A field the tools ask authors to write
belongs in the declaration first.

Both `repositories[].methods[]` and `useCases[].methods[]` use the one
`repositoryMethod` definition, so one declaration covers both.
"""
from jsonui_doc_cli.spec_doc.screen_spec_schema import SCREEN_SPEC_SCHEMA as SCHEMA


def _defs():
    return SCHEMA["$defs"]


def test_repository_method_declares_platforms():
    prop = _defs()["repositoryMethod"]["properties"].get("platforms")
    assert prop is not None
    assert prop["type"] == "array"


def test_its_values_are_the_view_model_var_values():
    ours = _defs()["repositoryMethod"]["properties"]["platforms"]["items"]
    theirs = _defs()["viewModelVar"]["properties"]["platforms"]["items"]
    assert ours == theirs == {"type": "string", "enum": ["ios", "android", "web"]}


def test_repositories_and_use_cases_share_the_definition():
    ref = {"$ref": "#/$defs/repositoryMethod"}
    for owner in ("repository", "useCase"):
        assert ref in _defs()[owner]["properties"]["methods"]["items"]["oneOf"], owner
