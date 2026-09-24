"""An app contracts spec that declares only harnessConditions validates.

P2d (1.8.118) added `harnessConditions` to the app contracts spec, and the
validator still required `unitContracts` of every app spec — a requirement whose
reason is apiOutcomeRules' alone (each rule's `verifiedBy` names unit cases of
the same file). An app declaring only its harness preconditions, written as the
README's P2d section showed, failed validate unless it named a unit test it did
not have. Found in the pilot's scratch run, 2026-09-25.

The boundary, four ways: conditions only passes; rules only still fails;
conditions and rules without unitContracts fail; nothing at all fails.
"""
from __future__ import annotations

from jsonui_doc_cli.spec_doc.validator import SpecValidator

CASE = "request_onTerminal401_postsLogout"
CONDITIONS = {"session": {"values": ["absent", "present"], "default": "absent",
                          "reason": "whether a user is signed in"}}
RULES = [{"id": "logout", "statuses": ["401"], "sideCalls": ["postLogout"],
          "verifiedBy": [CASE], "reason": "the client posts logout on a terminal 401"}]


def _app(**keys):
    return {"type": "app_contracts_spec", "version": "1.0",
            "metadata": {"name": "app", "description": "d"}, **keys}


def _errors(spec):
    return [(e.path, e.message) for e in SpecValidator().validate_data(spec, "spec").errors]


def test_conditions_only_passes():
    assert _errors(_app(harnessConditions=CONDITIONS)) == []


def test_rules_only_still_needs_unit_contracts():
    assert ("unitContracts", "Required field 'unitContracts' is missing") in \
        _errors(_app(apiOutcomeRules=RULES))


def test_conditions_and_rules_without_unit_contracts_fail():
    assert ("unitContracts", "Required field 'unitContracts' is missing") in \
        _errors(_app(harnessConditions=CONDITIONS, apiOutcomeRules=RULES))


def test_an_app_spec_declaring_nothing_fails():
    assert ("unitContracts", "Required field 'unitContracts' is missing") in _errors(_app())


def test_control_conditions_rules_and_units_pass():
    units = [{"target": "ApiClient", "cases": [{"name": CASE}]}]
    assert _errors(_app(harnessConditions=CONDITIONS, apiOutcomeRules=RULES,
                        unitContracts=units)) == []


def test_the_readme_example_is_this_spec():
    """The README shows a whole conditions-only spec; it must be one that passes."""
    import json
    import re
    from pathlib import Path

    readme = (Path(__file__).resolve().parents[2] / "test_tools/README.md").read_text(encoding="utf-8")
    section = readme.split("### Harness conditions", 1)[1]
    block = re.search(r"```json\n(.*?)```", section, re.S).group(1)
    assert _errors(json.loads(block)) == []


def test_an_empty_unit_contracts_list_still_fails():
    # ee, design v4.16: an empty unitContracts is an error, as before.
    assert any(p.startswith("unitContracts") for p, _ in _errors(_app(unitContracts=[])))
