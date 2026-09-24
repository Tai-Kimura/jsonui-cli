"""Coverage and the generator give the validator's answer on conditions-only app specs.

ee, design v4.16: with apiOutcomeRules, unitContracts is required; without,
at least one of unitContracts / harnessConditions. The validator states the
rule (document_tools); the P1 parser that coverage and the generator read with
has no requirement of its own to agree or disagree — a rule's `verifiedBy`
must name a case of the same file, which a spec without unitContracts cannot.
So the ANSWERS are compared here, not the code: conditions only — accepted by
all three; rules without unitContracts — refused by all three.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli import contracts_coverage as cc
from tests import test_contracts_coverage as tcc

CONDITIONS = {"session": {"values": ["absent", "present"], "default": "absent",
                          "reason": "whether a user is signed in"}}
RULES = [{"id": "logout", "statuses": ["401"], "sideCalls": ["postLogout"],
          "verifiedBy": ["request_on401_logsOut"], "reason": "r"}]


def _app(**keys):
    return {"type": "app_contracts_spec", "version": "1.0",
            "metadata": {"name": "app", "description": "d"}, **keys}


def _validator_errors(app):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "document_tools"))
    from jsonui_doc_cli.spec_doc.validator import SpecValidator
    return SpecValidator().validate_data(app, "spec").errors


def test_conditions_only_is_accepted_by_all_three(tmp_path):
    app = _app(harnessConditions=CONDITIONS)
    assert _validator_errors(app) == []
    root = tcc._project(tmp_path, app=app)
    report = cc.run_coverage(root)
    assert report.app_errors == [] and report.conditions == ["session"]
    found = bt._app_rules_for_generation(root)          # the generator's reader
    assert [c.name for c in found.conditions] == ["session"] and found.problems == []


def test_rules_without_unit_contracts_are_refused_by_all_three(tmp_path):
    app = _app(apiOutcomeRules=RULES)
    assert _validator_errors(app)
    report = cc.run_coverage(tcc._project(tmp_path, app=app))
    assert any("verifiedBy" in (e["path"] or "") or "verifiedBy" in e["message"]
               for e in report.app_errors), report.app_errors
    assert report.exit == 1
    try:
        bt._app_rules_for_generation(tmp_path)
    except bt.BranchTestGenerationError as e:
        assert "verifiedBy" in str(e)
    else:
        raise AssertionError("the generator accepted rules whose verifiedBy names no case")
