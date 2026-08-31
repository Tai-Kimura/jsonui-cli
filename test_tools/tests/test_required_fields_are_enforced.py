"""Every `required` field a schema declares must actually fail validation.

The canonical schemas declare two things about a document's shape, and
only one of them was implemented:

| declaration                    | implemented as |
|--------------------------------|----------------|
| `additionalProperties: false`  | **error**      |
| `required`                     | warning, or nothing |

Measured before the fix: dropping `source`, `metadata` or `cases` from a
screen test produced warnings; dropping `metadata` from a flow test
produced **no message at all**. A file holding nothing but
`{"type": "screen"}` validated clean — a file that names no screen and
asserts nothing.

The consumer who found it named the reason it stayed hidden:

> the same schema's `additionalProperties: false` is enforced, and **one
> declaration being enforced looks like evidence that its neighbour is**

So this does not test the four fields that were wrong. It walks the
`required` list of each vendored schema and asserts each entry
individually, in both directions — a field added to a schema cannot reach
a release either unchecked or undeclared. Fixing the four by hand would
have left the next addition to open the same hole.

Same shape as `KEY_DRIVER_REQUIREMENTS` / `x-requires-driver`: the
declaration and the proof that it fires live beside each other, and the
set is derived rather than typed twice.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.schema import REQUIRED_TOP_LEVEL_KEYS
from jsonui_test_cli.validation.validator import TestValidator

FIXTURES = Path(__file__).parent / "schema_fixtures"

#: A document that validates clean, per type. The baseline matters as much
#: as the mutations: if it were invalid for some unrelated reason, every
#: "dropping X is an error" below would pass for that reason instead.
VALID = {
    "screen": {
        "type": "screen",
        "source": {"layout": "home.json"},
        "metadata": {"name": "home", "description": "d"},
        "cases": [{"name": "c", "steps": [{"action": "wait", "ms": 100}]}],
    },
    "flow": {
        "type": "flow",
        "metadata": {"name": "f", "description": "d"},
        "sources": [{"layout": "home.json", "alias": "home"}],
        "steps": [{"action": "wait", "ms": 100, "screen": "home"}],
    },
}

SCHEMA_FILE = {"screen": "screen-test", "flow": "flow-test"}


def _validate(tmp_path: Path, doc: dict):
    path = tmp_path / "probe.test.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return TestValidator().validate_file(path)


def _schema_required(test_type: str) -> list[str]:
    schema = json.loads(
        (FIXTURES / f"{SCHEMA_FILE[test_type]}.schema.json").read_text("utf-8"))
    return list(schema.get("required", []))


@pytest.mark.parametrize("test_type", sorted(VALID))
def test_the_baseline_document_is_valid(tmp_path, test_type):
    """The control. Without this, every case below could pass because the
    document was invalid for a reason that has nothing to do with the
    field being dropped."""
    result = _validate(tmp_path, VALID[test_type])
    assert result.is_valid, [m.message for m in result.errors]


def _cases():
    for test_type in sorted(VALID):
        for field in _schema_required(test_type):
            yield pytest.param(test_type, field, id=f"{test_type}-{field}")


@pytest.mark.parametrize("test_type,field", list(_cases()))
def test_dropping_a_required_field_is_an_error(tmp_path, test_type, field):
    doc = {k: v for k, v in VALID[test_type].items() if k != field}

    result = _validate(tmp_path, doc)

    assert result.errors, (
        f"{test_type}: the schema marks {field!r} required, but dropping it "
        f"produced {len(result.warnings)} warning(s) and no error"
    )


@pytest.mark.parametrize("test_type", sorted(VALID))
def test_the_declared_set_matches_the_schema(test_type):
    """Both directions. A field in the schema but not here would go
    unchecked; a field here but not in the schema would be enforced on the
    strength of nothing."""
    assert REQUIRED_TOP_LEVEL_KEYS[test_type] == _schema_required(test_type)


def test_every_schema_with_a_required_list_is_covered():
    """The set is derived, not typed twice. A new test type whose schema
    declares `required` has to appear here rather than being quietly out of
    scope — the failure mode this file exists to remove."""
    declared = set(REQUIRED_TOP_LEVEL_KEYS)
    assert declared == set(VALID), (
        "REQUIRED_TOP_LEVEL_KEYS and the baseline documents disagree about "
        "which test types exist"
    )


def test_an_empty_cases_list_is_a_warning_not_an_error(tmp_path):
    """`required` asks for the key, not for its contents. A file that
    declares an empty list has said something; conflating the two would
    make the check say 'missing' about a key that is present."""
    doc = dict(VALID["screen"], cases=[])

    result = _validate(tmp_path, doc)

    assert result.is_valid
    assert any("No test cases" in m.message for m in result.warnings)
