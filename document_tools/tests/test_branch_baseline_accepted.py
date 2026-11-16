"""A branch may declare its own `baseline`, and it is validated like one.

The vocabulary asymmetry the ticket names: `when data.*` takes scalars only,
`baseline` takes any JSON, and `baseline` sat at the METHOD. So a list-valued
pre-state was fixed across every branch while the scalars agreeing with it
moved per branch, and half-moved states became easy to build.

Accepting the key is only half — a branch baseline that named an undeclared
field, or seeded something the spec never declared seedable, would be a new
way to write an unchecked arrange. It goes through the same witness
validation the method's does, so the checks that already guard one guard the
other.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonui_doc_cli.spec_doc.validator import SpecValidator


def _spec(branch, *, method_baseline=None, seedable=None):
    contract = {"branches": [branch]}
    if method_baseline is not None:
        contract["baseline"] = method_baseline
    bc = {"methods": {"onLoad": contract}}
    if seedable is not None:
        bc["seedableState"] = seedable
    return {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"name": "Listing", "displayName": "Listing",
                     "description": "d", "layoutFile": "listing"},
        "structure": {"components": []},
        "dataFlow": {"viewModel": {"methods": [{"name": "onLoad"}], "vars": []}},
        "stateManagement": {"uiVariables": [
            {"name": "rows", "type": "Array", "description": "the rows"},
            {"name": "listEmptyVisibility", "type": "String",
             "description": "empty-view visibility"},
        ]},
        "branchContracts": bc,
    }


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "jui.config.json").write_text(json.dumps(
        {"layouts_directory": "layouts"}), encoding="utf-8")
    layouts = tmp_path / "layouts"
    layouts.mkdir()
    (layouts / "listing.json").write_text("{}", encoding="utf-8")
    (tmp_path / "specs").mkdir()
    return tmp_path


def _validate(project, doc):
    path = project / "specs" / "listing.spec.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return SpecValidator().validate_file(str(path))


BRANCH = {"when": {"data.listEmptyVisibility": "visible"},
          "then": {"data.rows": []}}


def test_a_branch_baseline_is_accepted(project):
    result = _validate(project, _spec(
        dict(BRANCH, baseline={"rows": [], "listEmptyVisibility": "visible"})))

    assert result.errors == [], [m.message for m in result.errors]


def test_the_control_arm_without_one_is_also_clean(project):
    """So "accepted" is not being read off a document that passes anyway
    for some unrelated reason."""
    assert _validate(project, _spec(BRANCH)).errors == []


def test_an_unknown_branch_key_is_still_rejected(project):
    """The allow-list gained one entry, not its purpose."""
    result = _validate(project, _spec(dict(BRANCH, baselines={"rows": []})))

    assert any("Unknown branch key" in m.message for m in result.errors)
    assert any("'baseline'" in m.message for m in result.errors)


def _undeclared(result):
    return [m for m in result.warnings + result.errors
            if "is not declared" in m.message]


def test_a_branch_baseline_naming_an_undeclared_field_is_reported(project):
    """It goes through the same witness validation as the method's, so the
    guard that already covers one covers the other. Accepting the key
    without this would have made the branch baseline the one arrange nobody
    checked."""
    result = _validate(project, _spec(
        dict(BRANCH, baseline={"noSuchField": 1})))

    assert _undeclared(result), "an undeclared field was accepted in silence"


def test_it_is_reported_at_the_same_weight_as_the_method_baseline(project):
    """The pair. Measured rather than assumed — this is a WARNING on both,
    not an error, and asserting the wrong severity on one of them would
    have made "the same validation" a claim the tests did not check."""
    branch_side = _validate(project, _spec(
        dict(BRANCH, baseline={"noSuchField": 1})))
    method_side = _validate(project, _spec(
        BRANCH, method_baseline={"noSuchField": 1}))

    assert ([m.level for m in _undeclared(branch_side)]
            == [m.level for m in _undeclared(method_side)])
    assert _undeclared(branch_side)[0].level == "warning"
