"""A row can say an apiOutcomeRules side call was NOT made, without the screen
declaring it — and a not-called row is red in its own words.

The skill says a call made with an opt-out flag (a request that must not end
the session on 401) states it in its 401 row: `"api.<logout op>": "not-called"`.
Until this, that row could not be written unless the screen declared the
logout: the validator warned "not declared in dataFlow" and the generator
stopped at "has no `endpoint` declaration". So the rule that admits the
logout on 401 also hid a regressed flag (the {declared, not-called} × VM table
below, measured before the change: without the row the regressed VM passes).

- G1: `generate branch-tests` serves such an op on the side route
  `side_routes` already adds (op = the operationId), and the row asserts its
  count is 0. Only "not-called": "called" (it would permit the op in every
  row of the method, widening the rule's statuses), `when`, `.request`, and
  the operationId of an endpoint the screen declares under its own name
  (the side route is not added then, so the count would always read 0) are
  refused, each saying why.
- G2: a not-called row asserts its ops BEFORE the bound, with its own words.
  The bound leaves them out of what the row allows, so asserted after it a
  forbidden call was reported as the bound's red — whose advice is to say
  "called". Changes every generated test with a not-called row, on the three
  platforms (string arms for iOS / Android, a run for web).
- V1: `validate spec` stays silent for a not-called side call it can read in
  the app contracts spec (found from the `jui.config.json` nearest above the
  spec, as jsonui-test finds it), and keeps a WARNING — never an error, this
  is not a gate — for every other undeclared use, worded for the case.

Run with this tree on the path (see test_tag_gate_from_prev.py's header).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc
from tests import test_branch_unmatched_and_side_routes as t

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "document_tools"))
from jsonui_doc_cli.spec_doc.validator import SpecValidator  # noqa: E402

SPEC = "docs/screens/json/checkout.spec.json"
MESSAGE = "api.postLogout: this row says not-called — called"


def _spec(root: Path, *, then: dict | None = None, when: dict | None = None,
          declare: dict | None = None) -> Path:
    """t._project(rule=True), its 401 row (submit, branch 1) given `then` /
    `when` extras, and the screen's repository given `declare` methods."""
    t._project(root, rule=True)
    path = root / SPEC
    spec = json.loads(path.read_text())
    row = spec["branchContracts"]["methods"]["submit"]["branches"][0]
    row["then"].update(then or {})
    row["when"].update(when or {})
    if declare:
        spec["dataFlow"]["repositories"][0]["methods"].append(declare)
    path.write_text(json.dumps(spec))
    return path


def _run(root: Path, *, honoured: bool):
    """Generate for web and run it against a VM that posts logout on 401
    (the opt-out flag regressed) or does not (the flag honoured)."""
    base = t._HARNESS
    try:
        if honoured:
            t._HARNESS = base.replace("r.status === 401 || ", "")
            assert t._HARNESS != base
        _report, rows, _err = t._generate_and_run(root)
    finally:
        t._HARNESS = base
    return t._row(rows, "submit", 1)


# ------------------------------------------------------------ G1 + G2, run --

@pytest.mark.parametrize("declared", [False, True])
@pytest.mark.parametrize("honoured, green", [(False, False), (True, True)])
def test_a_not_called_side_call_is_red_in_its_own_words_when_made(tmp_path, declared,
                                                                   honoured, green):
    tc.tool("node")
    _spec(tmp_path, then={"api.postLogout": "not-called"},
          declare={"name": "postLogout", "endpoint": "POST /api/logout"} if declared else None)
    ok, message = _run(tmp_path, honoured=honoured)
    assert ok is green, message
    if not green:
        assert message.startswith(f"{MESSAGE} 1 time(s)"), message


def test_without_the_row_the_rule_admits_the_regressed_call(tmp_path):
    # The control: the rule admits the logout on 401, so a VM whose opt-out
    # flag regressed is green unless the row says not-called.
    tc.tool("node")
    _spec(tmp_path)
    ok, message = _run(tmp_path, honoured=False)
    assert ok, message


# ------------------------------------------------------------ G1 refusals --

@pytest.mark.parametrize("extra, words", [
    ({"then": {"api.postLogout": "called"}}, "would widen the rule's statuses"),
    ({"when": {"api.postLogout": "default"}}, "which no row chooses"),
    ({"then": {"api.postLogout.request": {"reason": "x"}}}, "its request is the network layer's"),
])
def test_a_side_call_can_only_be_said_not_called(tmp_path, extra, words):
    _spec(tmp_path, **extra)
    with pytest.raises(bt.BranchTestGenerationError) as e:
        bt.generate_branch_tests("checkout", tmp_path, platform="web", config_platforms=["web"])
    assert "'postLogout' is an apiOutcomeRules sideCalls operation this screen does not " \
           "declare — a row can only say it is \"not-called\"" in str(e.value)
    assert words in str(e.value)


def test_the_operation_id_of_an_endpoint_the_screen_names_otherwise_is_refused(tmp_path):
    # The side route is not added for an endpoint the screen declares, so a
    # count under the operationId would read 0 whatever the VM did.
    _spec(tmp_path, then={"api.postLogout": "not-called"},
          declare={"name": "endSession", "endpoint": "POST /api/logout"})
    with pytest.raises(bt.BranchTestGenerationError) as e:
        bt.generate_branch_tests("checkout", tmp_path, platform="web", config_platforms=["web"])
    assert "'postLogout' is POST /api/logout, which this screen declares as 'endSession' — " \
           "write api.endSession" in str(e.value)


def test_an_op_neither_declared_nor_a_side_call_still_stops_and_names_both_ways(tmp_path):
    _spec(tmp_path, then={"api.getProfile": "not-called"})
    with pytest.raises(bt.BranchTestGenerationError) as e:
        bt.generate_branch_tests("checkout", tmp_path, platform="web", config_platforms=["web"])
    assert "api operation 'getProfile' has no `endpoint` declaration" in str(e.value)
    assert "name its operationId in an apiOutcomeRules sideCalls and say \"not-called\"" \
        in str(e.value)


def test_without_the_rule_a_side_call_is_not_known(tmp_path):
    # No app contracts spec: nothing is a side call, and the row stops as before.
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    (tmp_path / "docs/screens/json/app_contracts.spec.json").unlink()
    with pytest.raises(bt.BranchTestGenerationError) as e:
        bt.generate_branch_tests("checkout", tmp_path, platform="web", config_platforms=["web"])
    assert "api operation 'postLogout' has no `endpoint` declaration" in str(e.value)


def test_an_operation_id_two_mocks_carry_is_no_side_call(tmp_path):
    # side_routes adds no route for it, so skipping its binding would leave a
    # count that always reads 0: it must stop as an undeclared op does.
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    t._mock(tmp_path, "logout_copy", "POST", "/api/logout2", "postLogout", {"default": {"status": 204}})
    with pytest.raises(bt.BranchTestGenerationError) as e:
        bt.generate_branch_tests("checkout", tmp_path, platform="web", config_platforms=["web"])
    assert "api operation 'postLogout' has no `endpoint` declaration" in str(e.value)


def test_the_row_binds_so_coverage_can_judge_it(tmp_path):
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    spec = json.loads((tmp_path / SPEC).read_text())
    rules = bt.find_app_contract_spec(tmp_path).rules
    bindings = bt.collect_bindings(spec, spec["branchContracts"]["methods"],
                                   bt.index_mock_files(tmp_path / "tests/mocks"), None, "web",
                                   rules=rules)
    assert bindings.errors == []
    row = next(r for r in bindings.rows if r.method == "submit" and r.number == 1)
    assert "postLogout" not in row.allowed_ops          # the row forbids it
    assert any(r.op == "postLogout" and r.side for r in bindings.routes)


# ------------------------------------------------------------ G2, emitted --

@pytest.mark.parametrize("platform, extra, assertion, old", [
    ("web", {}, 'expect(rec.countFor("postLogout"), `api.postLogout: this row says not-called — '
                'called ${rec.countFor("postLogout")} time(s)`).toBe(0);',
     'expect(rec.countFor("postLogout")).toBe(0);'),
    ("ios", {"module": "App"}, 'XCTAssertEqual(rec.countFor("postLogout"), 0, "api.postLogout: '
                               'this row says not-called — called \\(rec.countFor("postLogout")) time(s)")',
     'XCTAssertEqual(rec.countFor("postLogout"), 0)'),
    ("android", {"package": "com.example.app"},
     'assertEquals("api.postLogout: this row says not-called — called ${rec.countFor("postLogout")} '
     'time(s)", 0, rec.countFor("postLogout"))',
     'assertEquals(0, rec.countFor("postLogout"))'),
])
def test_the_not_called_assertion_comes_before_the_bound_on_every_platform(
        tmp_path, platform, extra, assertion, old):
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    bt.generate_branch_tests("checkout", tmp_path, platform=platform,
                             config_platforms=[platform], **extra)
    files = [f for f in (tmp_path / "tests/unit/generated").rglob("*")
             if f.is_file() and f.suffix in (".ts", ".swift", ".kt") and "branches" in f.name.lower()]
    assert len(files) == 1, files
    lines = [line.strip() for line in files[0].read_text().splitlines()]
    at = [i for i, line in enumerate(lines) if line == assertion]
    assert len(at) == 1, [line for line in lines if "postLogout" in line]
    bound = next(i for i in range(at[0], len(lines)) if "unexpectedOps" in lines[i])
    assert at[0] < bound
    assert old not in lines


# ------------------------------------------------------------ V1 ----------

def _warnings(spec: Path) -> list[str]:
    result = SpecValidator().validate_file(spec)
    assert not [m for m in result.errors if "postLogout" in m.message or "getProfile" in m.message]
    return [m.message for m in result.warnings if "postLogout" in m.message
            or "getProfile" in m.message]


def test_the_validator_is_silent_for_a_not_called_side_call(tmp_path):
    assert _warnings(_spec(tmp_path, then={"api.postLogout": "not-called"})) == []


@pytest.mark.parametrize("extra", [
    {"then": {"api.postLogout": "called"}},
    {"when": {"api.postLogout": "default"}},
    {"then": {"api.postLogout.request": {"reason": "x"}}},
])
def test_the_validator_warns_for_any_other_use_of_a_side_call(tmp_path, extra):
    assert _warnings(_spec(tmp_path, **extra)) == [
        "API operation 'postLogout' is an apiOutcomeRules sideCalls operation this screen "
        "does not declare — a row can only say it is \"not-called\" (a side route is served "
        "with its mock's default scenario, and the call itself is the rule's verifiedBy unit "
        "case's to assert)"]


BASE = ("API operation 'getProfile' is not declared in dataFlow.repositories[].methods "
        "or dataFlow.useCases[].methods")


@pytest.mark.parametrize("extra, message", [
    ({"then": {"api.getProfile": "not-called"}},
     BASE + " — or, for a call the app's network layer makes, name its operationId in an "
            "apiOutcomeRules sideCalls"),
    ({"then": {"api.getProfile": "called"}}, BASE),      # unchanged for every other use
    ({"when": {"api.getProfile": "default"}}, BASE),
])
def test_an_op_that_is_no_side_call_keeps_its_warning(tmp_path, extra, message):
    assert _warnings(_spec(tmp_path, **extra)) == [message]


def test_with_no_config_to_read_the_rules_from_the_warning_stays(tmp_path):
    # The spec moved where no jui.config.json is above it: the side call
    # cannot be told, and the answer is a warning, never a silence.
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    (tmp_path / "jui.config.json").unlink()
    assert _warnings(tmp_path / SPEC) == [
        "API operation 'postLogout' is not declared in dataFlow.repositories[].methods or "
        "dataFlow.useCases[].methods — or, for a call the app's network layer makes, name its "
        "operationId in an apiOutcomeRules sideCalls (the app contracts spec could not be "
        "read from here: no jui.config.json above this spec, so sideCalls was not checked)"]


# ------------------------------------------------------------ extends stub --
# A face keeps a doc-tree stub above its specs — `{extends, layouts_directory}`,
# so `jsonui-doc generate html --app` resolves layouts from a spec — and the
# validator read the stub as the app's config: no spec_directory, no rules, an
# EMPTY set, and a warning advising to name in sideCalls an op already named
# (1.8.120, found by a face adopting it). It now follows `extends` with the
# resolver the html generator uses (`project_config._follow_extends`), checks
# that the config it lands on owns the spec, and tells "read, not named" from
# "could not read".

READ_NOT_NAMED = (" — or, for a call the app's network layer makes, name its operationId in "
                  "an apiOutcomeRules sideCalls")


def _stub(root: Path, rel: str, config: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8")


@pytest.mark.parametrize("op, stub, expected", [
    ("postLogout", False, []),
    ("postLogout", True, []),                       # the defect: 1 warning before
    ("getProfile", True, [                          # control: read, and not named
        "API operation 'getProfile' is not declared in dataFlow.repositories[].methods or "
        "dataFlow.useCases[].methods" + READ_NOT_NAMED]),
])
def test_a_doc_tree_stub_leads_to_the_app_s_rules(tmp_path, op, stub, expected):
    _spec(tmp_path, then={f"api.{op}": "not-called"})
    if stub:
        _stub(tmp_path, "docs/jui.config.json",
              {"extends": "../jui.config.json", "layouts_directory": "screens/layouts"})
    assert _warnings(tmp_path / SPEC) == expected


def test_two_hops_and_a_directory_spelling_are_followed(tmp_path):
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    _stub(tmp_path, "docs/jui.config.json", {"extends": "../cfg", "layouts_directory": "x"})
    _stub(tmp_path, "cfg/jui.config.json", {"extends": "../jui.config.json"})
    assert _warnings(tmp_path / SPEC) == []


def _unread(op: str, why: str) -> list[str]:
    return [f"API operation '{op}' is not declared in dataFlow.repositories[].methods or "
            f"dataFlow.useCases[].methods{READ_NOT_NAMED} (the app contracts spec could not "
            f"be read from here: {why}, so sideCalls was not checked)"]


def test_a_chain_that_reaches_no_spec_directory_is_unknown_not_empty(tmp_path):
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    _stub(tmp_path, "docs/jui.config.json", {"extends": "../other", "layouts_directory": "x"})
    _stub(tmp_path, "other/jui.config.json", {"layouts_directory": "y"})
    stub, other = (tmp_path / "docs/jui.config.json"), (tmp_path / "other/jui.config.json").resolve()
    assert _warnings(tmp_path / SPEC) == _unread(
        "postLogout", f"no config on the extends chain from {stub} declares spec_directory "
                      f"(it ended at {other})")


def test_a_config_that_does_not_own_the_spec_is_not_read(tmp_path):
    # The stub points at another app, whose spec_directory is elsewhere: its
    # rules answer for that app, not for this spec.
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    _stub(tmp_path, "docs/jui.config.json", {"extends": "../other", "layouts_directory": "x"})
    _stub(tmp_path, "other/jui.config.json", {"spec_directory": "specs"})
    (tmp_path / "other/specs").mkdir()
    owner = (tmp_path / "other/jui.config.json").resolve()
    assert _warnings(tmp_path / SPEC) == _unread(
        "postLogout", f"{owner}'s spec_directory ({owner.parent / 'specs'}) does not hold this spec")


def test_a_stub_that_extends_itself_ends_as_unknown(tmp_path):
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    _stub(tmp_path, "docs/jui.config.json", {"extends": ".", "layouts_directory": "x"})
    stub = tmp_path / "docs/jui.config.json"
    assert _warnings(tmp_path / SPEC) == _unread(
        "postLogout", f"no config on the extends chain from {stub} declares spec_directory "
                      f"(it ended at {stub.resolve()})")


def test_generation_from_a_stub_says_the_rules_were_not_read(tmp_path):
    # jsonui-test does not follow `extends` (4f 2026-09-25: run from the app's
    # config directory). Run from the stub with the spec and mocks given, the
    # "no endpoint declaration" error must not read as advice to name an op
    # the rules already name: it says the rules were not read, and why.
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    _stub(tmp_path, "docs/jui.config.json",
          {"extends": "../jui.config.json", "layouts_directory": "screens/layouts"})
    with pytest.raises(bt.BranchTestGenerationError) as e:
        bt.generate_branch_tests("checkout", tmp_path / "docs", spec_path=str(tmp_path / SPEC),
                                 mocks_dir=str(tmp_path / "tests/mocks"), platform="web",
                                 config_platforms=["web"])
    assert (f"apiOutcomeRules could not be read from here (no spec_directory in "
            f"{tmp_path / 'docs' / 'jui.config.json'}) — run from the app's config directory, "
            "or declare the operation") in str(e.value)


def test_generation_that_read_the_rules_does_not_say_it_could_not(tmp_path):
    # The control: spec_directory declared, no app contracts spec — the rules
    # were read and are empty, so the error has no "could not be read".
    _spec(tmp_path, then={"api.postLogout": "not-called"})
    (tmp_path / "docs/screens/json/app_contracts.spec.json").unlink()
    with pytest.raises(bt.BranchTestGenerationError) as e:
        bt.generate_branch_tests("checkout", tmp_path, platform="web", config_platforms=["web"])
    assert "has no `endpoint` declaration" in str(e.value)
    assert "could not be read" not in str(e.value)
