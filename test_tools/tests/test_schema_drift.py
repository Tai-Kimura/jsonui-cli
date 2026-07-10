"""Cross-repo drift guard: validator constants (jsonui-cli) must match the
canonical JSON Schemas (jsonui-test-runner).

Validation is driven entirely by the Python constants in
``jsonui_test_cli.schema`` / ``jsonui_test_cli.report`` — nothing reads a schema
file at runtime — so the constants and the canonical schemas can silently drift
apart. These tests load the vendored copies of the schemas (see
``schema_fixtures/VENDOR.md``) and assert the two still agree. A failure means a
real drift: fix the constants or re-vendor + reconcile, never loosen the test.
"""

import json
from pathlib import Path

import pytest

from jsonui_test_cli import schema as sc
from jsonui_test_cli import report as rp

FIXTURES = Path(__file__).parent / "schema_fixtures"


def _load(name):
    return json.loads((FIXTURES / f"{name}.schema.json").read_text("utf-8"))


def _consts_from_actions(actions_schema):
    """Extract action consts, assert consts, and launch keys from actions.schema.json."""
    actions, asserts = set(), set()
    for d in actions_schema["definitions"].values():
        props = d.get("properties", {})
        if "action" in props and "const" in props["action"]:
            actions.add(props["action"]["const"])
        if "assert" in props and "const" in props["assert"]:
            asserts.add(props["assert"]["const"])
    launch = set((actions_schema["definitions"]["launch"].get("properties") or {}).keys())
    return actions, asserts, launch


def _top_props(schema):
    return set((schema.get("properties") or {}).keys())


def _responsive_variants(actions_schema):
    """Split #/definitions/responsive oneOf into (bucket-enum variant, constraint-object variant)."""
    one_of = actions_schema["definitions"]["responsive"]["oneOf"]
    named = next(v for v in one_of if v.get("type") == "string")
    constraint = next(v for v in one_of if v.get("type") == "object")
    return named, constraint


def _result_item_props(results_schema):
    return (
        results_schema["properties"]["suites"]["items"]["properties"]["results"]
        ["items"]["properties"]
    )


# --- actions.schema.json <-> schema.py -------------------------------------

def test_actions_match_supported_actions():
    actions, _, _ = _consts_from_actions(_load("actions"))
    assert actions == set(sc.SUPPORTED_ACTIONS), (
        "actions.schema.json action consts drifted from SUPPORTED_ACTIONS.\n"
        f"  only in schema: {sorted(actions - set(sc.SUPPORTED_ACTIONS))}\n"
        f"  only in const : {sorted(set(sc.SUPPORTED_ACTIONS) - actions)}"
    )


def test_assertions_match_supported_assertions():
    _, asserts, _ = _consts_from_actions(_load("actions"))
    assert asserts == set(sc.SUPPORTED_ASSERTIONS), (
        "actions.schema.json assert consts drifted from SUPPORTED_ASSERTIONS.\n"
        f"  only in schema: {sorted(asserts - set(sc.SUPPORTED_ASSERTIONS))}\n"
        f"  only in const : {sorted(set(sc.SUPPORTED_ASSERTIONS) - asserts)}"
    )


def test_launch_keys_match():
    _, _, launch = _consts_from_actions(_load("actions"))
    assert launch == set(sc.VALID_LAUNCH_KEYS), (
        "actions.schema.json launch props drifted from VALID_LAUNCH_KEYS.\n"
        f"  only in schema: {sorted(launch - set(sc.VALID_LAUNCH_KEYS))}\n"
        f"  only in const : {sorted(set(sc.VALID_LAUNCH_KEYS) - launch)}"
    )


# --- condition + responsive <-> schema.py -----------------------------------

def test_condition_keys_match():
    props = set(_load("actions")["definitions"]["condition"]["properties"].keys())
    assert props == set(sc.VALID_CONDITION_KEYS), (
        "actions.schema.json condition props drifted from VALID_CONDITION_KEYS.\n"
        f"  only in schema: {sorted(props - set(sc.VALID_CONDITION_KEYS))}\n"
        f"  only in const : {sorted(set(sc.VALID_CONDITION_KEYS) - props)}"
    )


def test_responsive_bucket_enum_matches():
    named, _ = _responsive_variants(_load("actions"))
    buckets = set(named["enum"])
    assert buckets == set(sc.RESPONSIVE_BUCKETS), (
        "actions.schema.json responsive bucket enum drifted from RESPONSIVE_BUCKETS.\n"
        f"  only in schema: {sorted(buckets - set(sc.RESPONSIVE_BUCKETS))}\n"
        f"  only in const : {sorted(set(sc.RESPONSIVE_BUCKETS) - buckets)}"
    )


def test_responsive_constraint_keys_match():
    _, constraint = _responsive_variants(_load("actions"))
    keys = set(constraint["properties"].keys())
    assert keys == set(sc.RESPONSIVE_CONSTRAINT_KEYS), (
        "actions.schema.json responsive constraint props drifted from RESPONSIVE_CONSTRAINT_KEYS.\n"
        f"  only in schema: {sorted(keys - set(sc.RESPONSIVE_CONSTRAINT_KEYS))}\n"
        f"  only in const : {sorted(set(sc.RESPONSIVE_CONSTRAINT_KEYS) - keys)}"
    )


def test_responsive_orientation_enum_matches():
    _, constraint = _responsive_variants(_load("actions"))
    orientation = set(constraint["properties"]["orientation"]["enum"])
    assert orientation == set(sc.RESPONSIVE_ORIENTATIONS), (
        "actions.schema.json responsive orientation enum drifted from RESPONSIVE_ORIENTATIONS"
    )


def test_set_orientation_action_enum_matches():
    schema = _load("actions")
    action = next(
        d for d in schema["definitions"].values()
        if (d.get("properties") or {}).get("action", {}).get("const") == "setOrientation"
    )
    orientation = set(action["properties"]["orientation"]["enum"])
    assert orientation == set(sc.RESPONSIVE_ORIENTATIONS), (
        "actions.schema.json setOrientation orientation enum drifted from RESPONSIVE_ORIENTATIONS"
    )


# --- screen-test + flow-test top-level <-> VALID_TOP_LEVEL_KEYS -------------

def test_top_level_keys_match_union_of_screen_and_flow():
    union = _top_props(_load("screen-test")) | _top_props(_load("flow-test"))
    assert union == set(sc.VALID_TOP_LEVEL_KEYS), (
        "screen-test + flow-test top-level props drifted from VALID_TOP_LEVEL_KEYS.\n"
        f"  only in schemas: {sorted(union - set(sc.VALID_TOP_LEVEL_KEYS))}\n"
        f"  only in const  : {sorted(set(sc.VALID_TOP_LEVEL_KEYS) - union)}"
    )


# --- screen-test case objects <-> VALID_CASE_KEYS ---------------------------

def test_screen_case_keys_match():
    props = set(_load("screen-test")["properties"]["cases"]["items"]["properties"].keys())
    assert props == set(sc.VALID_CASE_KEYS), (
        "screen-test.schema.json case props drifted from VALID_CASE_KEYS.\n"
        f"  only in schema: {sorted(props - set(sc.VALID_CASE_KEYS))}\n"
        f"  only in const : {sorted(set(sc.VALID_CASE_KEYS) - props)}"
    )


# --- description.schema.json <-> VALID_DESCRIPTION_KEYS ---------------------

def test_description_keys_match():
    props = _top_props(_load("description"))
    assert props == set(sc.VALID_DESCRIPTION_KEYS), (
        "description.schema.json props drifted from VALID_DESCRIPTION_KEYS.\n"
        f"  only in schema: {sorted(props - set(sc.VALID_DESCRIPTION_KEYS))}\n"
        f"  only in const : {sorted(set(sc.VALID_DESCRIPTION_KEYS) - props)}"
    )


# --- results.schema.json <-> report.py (the three-point results contract) --

def test_results_status_enum_matches():
    schema = _load("results")
    status = set(_result_item_props(schema)["status"]["enum"])
    assert status == set(rp.VALID_RESULT_STATUSES), (
        "results.schema.json status enum drifted from report.VALID_RESULT_STATUSES"
    )


def test_results_platform_enum_matches():
    schema = _load("results")
    platform = set(schema["properties"]["platform"]["enum"])
    assert platform == set(rp.VALID_RESULT_PLATFORMS), (
        "results.schema.json platform enum drifted from report.VALID_RESULT_PLATFORMS"
    )


def test_results_top_level_keys_match():
    schema = _load("results")
    top = set(schema["properties"].keys())
    assert top == set(rp.VALID_RESULTS_TOP_LEVEL_KEYS), (
        "results.schema.json top-level props drifted from report.VALID_RESULTS_TOP_LEVEL_KEYS.\n"
        f"  only in schema: {sorted(top - set(rp.VALID_RESULTS_TOP_LEVEL_KEYS))}\n"
        f"  only in const : {sorted(set(rp.VALID_RESULTS_TOP_LEVEL_KEYS) - top)}"
    )


def test_results_skip_reason_enum_matches():
    schema = _load("results")
    reasons = set(_result_item_props(schema)["skipReason"]["enum"])
    assert reasons == set(rp.VALID_SKIP_REASONS), (
        "results.schema.json skipReason enum drifted from report.VALID_SKIP_REASONS.\n"
        f"  only in schema: {sorted(reasons - set(rp.VALID_SKIP_REASONS))}\n"
        f"  only in const : {sorted(set(rp.VALID_SKIP_REASONS) - reasons)}"
    )


def test_results_version_is_const_1():
    schema = _load("results")
    assert schema["properties"]["version"] == {"const": 1}, (
        "results.schema.json version const drifted (skipReason landed as an "
        "optional field on version 1; a bump must be encoded in report.RESULTS_VERSION)"
    )
    assert rp.RESULTS_VERSION == 1


def test_results_item_keys_match():
    schema = _load("results")
    keys = set(_result_item_props(schema).keys())
    assert keys == set(rp.VALID_RESULT_KEYS), (
        "results.schema.json result-item props drifted from report.VALID_RESULT_KEYS.\n"
        f"  only in schema: {sorted(keys - set(rp.VALID_RESULT_KEYS))}\n"
        f"  only in const : {sorted(set(rp.VALID_RESULT_KEYS) - keys)}"
    )
