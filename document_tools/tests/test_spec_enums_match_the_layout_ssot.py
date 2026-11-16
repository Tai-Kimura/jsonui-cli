"""A spec schema enum that names a Layout JSON fact holds exactly the Layout
SSoT's values (shared/core/attribute_definitions.json), both ways.

Measured 2026-09-26 by walking both spec schemas for every `enum` and pairing
those that describe the layout with the SSoT's:
- embedEntry.navigationMode: the spec allowed ["delegate"] ("isolated
  deferred to v1.5"), the SSoT declares delegate / isolated and jui build
  gates isolated Embeds; the validator kept ("delegate",) with a note to keep
  it aligned with the SSoT.
- component.type (screen and component spec): Spacer and Divider, which no
  Layout tool knows, were allowed, and ten SSoT components were not
  (NetworkImage, CircleView, IconLabel, Radio, Segment, Slider, Progress,
  Blur, GradientView, and Embed — which a spec declares through
  structure.embeds, so it stays out, by name, below).
- tab.iconType: equal.
Every enum either names a Layout fact and is paired here, or is named with
the reason it does not — a new enum in either schema is red until it is one
of the two.
"""
from __future__ import annotations

import json

import pytest

from jsonui_doc_cli import shared_core
from jsonui_doc_cli.spec_doc.component_spec_schema import COMPONENT_SPEC_SCHEMA
from jsonui_doc_cli.spec_doc.screen_spec_schema import SCREEN_SPEC_SCHEMA
from jsonui_doc_cli.spec_doc.validator import SpecValidator


def _ssot() -> dict:
    core = shared_core.shared_core_dir()
    if core is None:
        pytest.skip("shared/core is not beside document_tools")
    return json.loads((core / "attribute_definitions.json").read_text(encoding="utf-8"))


def _enums(schema: dict) -> dict[str, list]:
    out: dict[str, list] = {}

    def walk(node, path):
        if isinstance(node, dict):
            if "enum" in node:
                out[path] = node["enum"]
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(schema, "")
    return out


def _canonical_components(ssot: dict) -> set[str]:
    """Every component the SSoT declares, by its canonical name (an alias —
    `_alias_of` — is the normalizer's, not a spelling a spec writes)."""
    return {k for k, v in ssot.items()
            if not k.startswith("_") and k != "common" and isinstance(v, dict) and not v.get("_alias_of")}


#: A spec's way to host another screen is structure.embeds, not a component.
NOT_A_SPEC_COMPONENT = {"Embed"}
#: A component spec describes a part of a screen, never a screen's root.
SCREEN_ONLY = {"TabView", "SafeAreaView"}


def _pairs(ssot: dict) -> dict[tuple[str, str], set]:
    """(schema, enum path) -> the values the SSoT says it holds."""
    components = _canonical_components(ssot) - NOT_A_SPEC_COMPONENT
    return {
        ("screen", "$defs.component.properties.type"): components,
        ("component", "$defs.component.properties.type"): components - SCREEN_ONLY,
        ("screen", "$defs.embedEntry.properties.navigationMode"): set(ssot["Embed"]["navigationMode"]["enum"]),
        ("screen", "$defs.tab.properties.iconType"):
            set(ssot["TabView"]["tabs"]["items"]["properties"]["iconType"]["enum"]),
    }


#: Enums that name no Layout JSON fact, and why.
NOT_LAYOUT = {
    ("screen", "$defs.metadata.properties.platforms.items"): "jui.config.json's platforms",
    ("screen", "$defs.viewModelVar.properties.platforms.items"): "jui.config.json's platforms",
    ("screen", "$defs.repositoryMethod.properties.platforms.items"): "jui.config.json's platforms",
    ("screen", "$defs.contractPlatforms.items"): "jui.config.json's platforms",
    ("screen", "$defs.branchEntry.oneOf[1].properties.platforms.items"): "jui.config.json's platforms",
    ("screen", "$defs.apiEndpoint.properties.method"): "HTTP",
    ("screen", "$defs.excludedOutcome.properties.by"): "jsonui-test's contract vocabulary",
    ("screen", "$defs.relatedFile.properties.type"): "a documentation link's kind",
    ("component", "$defs.metadata.properties.category"): "jsonui-doc's catalogue grouping",
}

SCHEMAS = {"screen": SCREEN_SPEC_SCHEMA, "component": COMPONENT_SPEC_SCHEMA}


PAIR_KEYS = [
    ("screen", "$defs.component.properties.type"),
    ("component", "$defs.component.properties.type"),
    ("screen", "$defs.embedEntry.properties.navigationMode"),
    ("screen", "$defs.tab.properties.iconType"),
]


def test_the_pairs_are_the_listed_ones():
    assert sorted(_pairs(_ssot())) == sorted(PAIR_KEYS)


@pytest.mark.parametrize("key", PAIR_KEYS, ids=lambda k: f"{k[0]} {k[1]}")
def test_the_enum_holds_the_layout_ssots_values_both_ways(key):
    want = _pairs(_ssot())[key]
    have = set(_enums(SCHEMAS[key[0]])[key[1]])
    assert (sorted(have - want), sorted(want - have)) == ([], []), \
        f"{key}: in the spec only {sorted(have - want)}; in the SSoT only {sorted(want - have)}"


def test_every_enum_is_paired_or_named_with_its_reason():
    seen = {(name, path) for name, schema in SCHEMAS.items() for path in _enums(schema)}
    pairs = set(_pairs(_ssot()))
    unnamed = sorted(seen - pairs - set(NOT_LAYOUT))
    stale = sorted((pairs | set(NOT_LAYOUT)) - seen)
    assert not unnamed, f"an enum neither paired with the SSoT nor named: {unnamed}"
    assert not stale, f"named here, no longer an enum: {stale}"


def test_the_validator_reads_the_schemas_values():
    assert SpecValidator.VALID_SCREEN_COMPONENT_TYPES == set(
        SCREEN_SPEC_SCHEMA["$defs"]["component"]["properties"]["type"]["enum"])
    assert SpecValidator.VALID_COMPONENT_TYPES == set(
        COMPONENT_SPEC_SCHEMA["$defs"]["component"]["properties"]["type"]["enum"])
    assert set(SpecValidator._EMBED_VALID_NAV_MODES) == {"delegate", "isolated"}


def test_an_isolated_embed_validates(tmp_path):
    spec = tmp_path / "home.spec.json"
    spec.write_text(json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Home", "displayName": "H", "description": "d"},
        "structure": {"components": [], "layout": {"root": "r", "children": []},
                      "embeds": [{"regionId": "detailPane", "screen": "detail",
                                  "navigationMode": "isolated"}]}}))
    result = SpecValidator().validate_file(spec)
    assert not [m for m in result.errors if "navigationMode" in m.path], result.errors
