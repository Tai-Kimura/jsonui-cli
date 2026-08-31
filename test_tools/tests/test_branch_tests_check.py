"""`generate branch-tests --check` — the generated tests are copies, so
nothing else can tell whether they are current.

The emitted test carries each route's status and body as an INLINE COPY,
because a test has to return a body. `mock generate --check` compares the
mock files to the swagger; nothing compared the copies to the mock files.
So a swagger edit followed by `mock generate` left every gate green while
the branch tests kept answering with the old contract — green against a
contract that no longer exists.

The reported instance had two independent sources and neither was visible:

- **input side** — the embedded scenarios were a subset of the mock file's
  (`default, no_refund, error_409` against six on disk)
- **generator side** — the shared runtime gained `seedState` in v1.7.29, so
  the on-disk output was a release behind while the suite stayed green

It was found by regenerating for an unrelated reason, not by a check. The
stale form is silent by construction: the case count, the verdict, and the
runtime are all unchanged, so nothing in a passing run distinguishes
"green because correct" from "green against a stale copy".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli.cli import main
from jsonui_test_cli.branch_tests import (
    BranchTestGenerationError,
    discover_branch_screens,
    generate_branch_tests,
)

from test_branch_tests_generator import _contract, _project, _write


def _branches():
    return _contract([
        {"title": "conflict",
         "when": {"method": "onConfirmTap", "api": {"createOrder": "conflict"}},
         "then": {"expect": {"errorMessage": "sold out"}}},
    ])


@pytest.fixture
def project(tmp_path):
    return _project(tmp_path, _branches())


def _second_screen(root: Path, name: str) -> None:
    """A second spec that declares branchContracts, sharing the runtime."""
    spec = json.loads((root / "docs/specs/checkout.spec.json").read_text())
    spec["metadata"]["name"] = name.title()
    _write(root / f"docs/specs/{name}.spec.json", spec)


def _plain_screen(root: Path, name: str) -> None:
    """A spec with no branchContracts — scanned, not generated."""
    spec = json.loads((root / "docs/specs/checkout.spec.json").read_text())
    spec.pop("branchContracts")
    spec["metadata"]["name"] = name.title()
    _write(root / f"docs/specs/{name}.spec.json", spec)


def _check(root: Path, screen: str = "checkout"):
    return generate_branch_tests(screen, project_root=root, check=True)


# --------------------------------------------------------------------- #
# The check itself
# --------------------------------------------------------------------- #

def test_a_freshly_generated_tree_is_current(project):
    generate_branch_tests("checkout", project_root=project)
    report = _check(project)
    assert report.drifted == []
    assert report.absent == []
    assert len(report.matched) == 2  # test + shared runtime


def test_a_changed_mock_body_drifts_the_embedded_copy(project):
    """The reported input-side source. `mock generate --check` stays green
    on this — the mock file is what it compares against."""
    generate_branch_tests("checkout", project_root=project)
    mock = project / "tests/mocks/orders/post_api-user-orders.mock.json"
    data = json.loads(mock.read_text())
    data["scenarios"]["conflict"]["body"] = {"error": {"code": "sold_out_v2"}}
    _write(mock, data)

    report = _check(project)
    assert [p.name for p in report.drifted] == ["checkout.branches.test.ts"]


def test_a_scenario_added_to_the_mock_drifts_the_embedded_copy(project):
    """The reported shape exactly: the copy held three scenarios where the
    mock file had six. A subset reads as a smaller contract, not a wrong
    one, so nothing downstream fails."""
    generate_branch_tests("checkout", project_root=project)
    mock = project / "tests/mocks/orders/post_api-user-orders.mock.json"
    data = json.loads(mock.read_text())
    data["scenarios"]["error_429"] = {"status": 429, "body": {"error": {"code": "rate"}}}
    _write(mock, data)

    assert [p.name for p in _check(project).drifted] == ["checkout.branches.test.ts"]


def test_a_changed_runtime_template_drifts_every_screen(project, monkeypatch):
    """The generator-side source: the runtime is one file the whole output
    directory shares, so a release that changes its shape leaves every
    screen a version behind — which is what v1.7.29 did."""
    _second_screen(project, "cart")
    generate_branch_tests("checkout", project_root=project)
    generate_branch_tests("cart", project_root=project)

    monkeypatch.setattr(bt, "RUNTIME_TS", bt.RUNTIME_TS + "\n// a later release\n")
    for screen in ("checkout", "cart"):
        drifted = [p.name for p in _check(project, screen).drifted]
        assert drifted == ["jsonui-branch-runtime.ts"], screen


def test_generation_is_deterministic(project):
    """The precondition the whole check rests on. If the same input and the
    same version produced different bytes, every run would report drift and
    the gate would be switched off within the week."""
    first = generate_branch_tests("checkout", project_root=project)
    test_bytes = first.test_file.read_text()
    runtime_bytes = first.runtime_file.read_text()

    second = generate_branch_tests("checkout", project_root=project)

    assert second.test_file.read_text() == test_bytes
    assert second.runtime_file.read_text() == runtime_bytes


def test_an_edit_to_the_generated_file_itself_is_drift(project):
    """@generated may not be hand-edited, and this is the axis a hash of the
    generator's INPUTS cannot cover: the inputs are untouched, so an input
    digest still matches while the file says something else."""
    report = generate_branch_tests("checkout", project_root=project)
    report.test_file.write_text(
        report.test_file.read_text() + "\n// edited by hand\n",
        encoding="utf-8")

    assert [p.name for p in _check(project).drifted] == [
        "checkout.branches.test.ts"]


def test_a_hand_written_only_scenario_is_part_of_the_comparison(project):
    """The embedded copy is the UNION of the hand-written and generated
    mocks, so a scenario that exists only in the hand-written file is in it.
    A check keyed on the swagger would be green here — the swagger did not
    change."""
    generate_branch_tests("checkout", project_root=project)
    mock = project / "tests/mocks/orders/post_api-user-orders.mock.json"
    data = json.loads(mock.read_text())
    data["scenarios"]["hand_written_only"] = {"status": 200,
                                              "body": {"ok": True}}
    _write(mock, data)

    assert [p.name for p in _check(project).drifted] == [
        "checkout.branches.test.ts"]


def test_a_never_generated_tree_is_absent_not_current(project):
    report = _check(project)
    assert sorted(p.name for p in report.absent) == [
        "checkout.branches.test.ts", "jsonui-branch-runtime.ts"]
    assert report.matched == []


# --------------------------------------------------------------------- #
# The check does not touch the tree
# --------------------------------------------------------------------- #

def test_check_writes_nothing_and_digs_nothing(project):
    """A check that creates the directory it audits reports the fresh tree
    as current and then agrees with itself forever after."""
    out = project / "tests/unit/generated"
    harness = project / "tests/unit/branch-harness"
    assert not out.exists() and not harness.exists()

    _check(project)

    assert not out.exists(), "check created the output directory"
    assert not harness.exists(), "check created the harness directory"


def test_check_does_not_rewrite_a_drifted_file(project):
    generate_branch_tests("checkout", project_root=project)
    test_file = project / "tests/unit/generated/checkout.branches.test.ts"
    mock = project / "tests/mocks/orders/post_api-user-orders.mock.json"
    data = json.loads(mock.read_text())
    data["scenarios"]["conflict"]["body"] = {"error": {"code": "changed"}}
    _write(mock, data)
    before = test_file.read_text()

    _check(project)

    assert test_file.read_text() == before, "check repaired what it reported"


def test_a_missing_harness_is_reported_but_is_not_drift(project):
    """The harness is consumer-owned: comparing it would make every check
    red. Saying nothing would call a project current whose generated tests
    cannot compile, so it is reported on its own channel."""
    generate_branch_tests("checkout", project_root=project)
    (project / "tests/unit/branch-harness/checkout.ts").unlink()

    report = _check(project)
    assert report.harness_absent is True
    assert report.drifted == [] and report.absent == []


def test_check_does_not_recreate_the_harness(project):
    generate_branch_tests("checkout", project_root=project)
    harness = project / "tests/unit/branch-harness/checkout.ts"
    harness.unlink()

    _check(project)

    assert not harness.exists()


# --------------------------------------------------------------------- #
# Enumeration and its denominator
# --------------------------------------------------------------------- #

def test_enumeration_separates_declaring_from_scanned(project):
    _second_screen(project, "cart")
    _plain_screen(project, "landing")

    declaring, scanned = discover_branch_screens(project)

    assert declaring == ["cart", "checkout"]
    assert scanned == ["cart", "checkout", "landing"]


def test_an_unreadable_spec_stays_in_the_denominator(project):
    (project / "docs/specs/broken.spec.json").write_text("{ not json",
                                                         encoding="utf-8")
    declaring, scanned = discover_branch_screens(project)

    # Dropping it from `scanned` too would shrink the denominator to match
    # the numerator and report full coverage of what happened to parse.
    assert "broken" not in declaring
    assert "broken" in scanned


def _split_out(root: Path, parent: str, child: str) -> Path:
    """Move the fixture screen into `<spec_directory>/<parent>/`, the
    placement a parent-spec split produces."""
    src = root / "docs/specs/checkout.spec.json"
    dest = root / "docs/specs" / parent / f"{child}.spec.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(), encoding="utf-8")
    src.unlink()
    return dest


def test_a_screen_in_a_subdirectory_resolves(project):
    """Splitting a parent spec puts screens one level down. A non-recursive
    lookup cannot find them, and since @generated files may not be edited by
    hand, a screen the generator cannot resolve can never be updated again.
    """
    _split_out(project, "catalog", "price_tiers")

    report = generate_branch_tests("price_tiers", project_root=project)

    assert report.test_file.name == "price_tiers.branches.test.ts"
    assert report.test_file.exists()


def test_a_subdirectory_screen_is_enumerated(project):
    _split_out(project, "catalog", "price_tiers")

    declaring, scanned = discover_branch_screens(project)

    # An enumeration that stops at the top level reports "0 drifted" for a
    # project whose screens it never looked at.
    assert declaring == ["price_tiers"]
    assert scanned == ["price_tiers"]


def test_the_directory_is_not_part_of_the_screen_id(project):
    """Canon is `screen_id_for_path`: the basename is the identity and the
    directories above it are not part of it."""
    _split_out(project, "catalog", "price_tiers")

    with pytest.raises(BranchTestGenerationError):
        generate_branch_tests("catalog-price_tiers",
                              project_root=project)


def test_one_id_matching_two_specs_is_refused(project):
    _split_out(project, "catalog", "price_tiers")
    twin = project / "docs/specs/legacy/price_tiers.spec.json"
    twin.parent.mkdir(parents=True, exist_ok=True)
    twin.write_text(
        (project / "docs/specs/catalog/price_tiers.spec.json").read_text(),
        encoding="utf-8")

    # Picking by sort order is how a route silently collapses onto one file.
    with pytest.raises(BranchTestGenerationError) as caught:
        generate_branch_tests("price_tiers", project_root=project)
    assert "matches 2 specs" in str(caught.value)


def test_a_flat_spec_still_wins_over_a_nested_namesake(project):
    """The historical placement keeps resolving without a search, so a
    project that never split anything cannot be affected by this."""
    nested = project / "docs/specs/archive/checkout.spec.json"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text("{ deliberately unparseable", encoding="utf-8")

    report = generate_branch_tests("checkout", project_root=project)
    assert report.test_file.exists()


def test_an_undeclared_spec_directory_is_an_error(tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    with pytest.raises(BranchTestGenerationError) as caught:
        discover_branch_screens(root)
    assert "spec_directory" in str(caught.value)


def test_a_missing_spec_directory_is_an_error(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _write(root / "jui.config.json", {"spec_directory": "docs/specs"})
    with pytest.raises(BranchTestGenerationError) as caught:
        discover_branch_screens(root)
    assert "not found" in str(caught.value)


# --------------------------------------------------------------------- #
# The gate: exit codes and what the summary claims
# --------------------------------------------------------------------- #

def _cli(root: Path, *argv, monkeypatch) -> int:
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["jsonui-test", "generate",
                                      "branch-tests", *argv])
    return main()


def test_the_gate_passes_on_a_current_tree(project, monkeypatch, capsys):
    _cli(project, monkeypatch=monkeypatch)
    assert _cli(project, "--check", monkeypatch=monkeypatch) == 0
    assert "1 up to date, 0 stale" in capsys.readouterr().out


def test_the_gate_fails_on_a_stale_copy(project, monkeypatch, capsys):
    _cli(project, monkeypatch=monkeypatch)
    mock = project / "tests/mocks/orders/post_api-user-orders.mock.json"
    data = json.loads(mock.read_text())
    data["scenarios"]["conflict"]["body"] = {"error": {"code": "v2"}}
    _write(mock, data)

    assert _cli(project, "--check", monkeypatch=monkeypatch) == 1
    out = capsys.readouterr().out
    assert "[DRIFT]" in out and "checkout.branches.test.ts" in out


def test_omitting_the_screen_covers_every_declaring_spec(project, monkeypatch,
                                                         capsys):
    _second_screen(project, "cart")
    _plain_screen(project, "landing")

    assert _cli(project, monkeypatch=monkeypatch) == 0
    out = capsys.readouterr().out
    assert "Generated branch tests for 'cart'" in out
    assert "Generated branch tests for 'checkout'" in out
    assert "landing" not in out

    assert _cli(project, "--check", monkeypatch=monkeypatch) == 0
    assert ("2 screen(s) declaring branchContracts of 3 spec(s) scanned"
            in capsys.readouterr().out)


def test_the_shared_runtime_is_reported_once_not_once_per_screen(
        project, monkeypatch, capsys):
    """Nine screens share one runtime. Reporting it per screen turns one
    stale file into nine findings and sends the reader round nine times."""
    _second_screen(project, "cart")
    _second_screen(project, "orders")
    _cli(project, monkeypatch=monkeypatch)
    capsys.readouterr()

    runtime = project / "tests/unit/generated/jsonui-branch-runtime.ts"
    runtime.write_text(runtime.read_text() + "\n// edited\n", encoding="utf-8")

    assert _cli(project, "--check", monkeypatch=monkeypatch) == 1
    out = capsys.readouterr().out
    assert out.count("[DRIFT]") == 1
    # ...and the screen count still says all three are stale, because they
    # are: every one of them emits that file.
    assert "0 up to date, 3 stale" in out
    assert "1 drifted" in out


def test_no_screen_declaring_contracts_is_red_not_green(project, monkeypatch,
                                                        capsys):
    """The failure this shape ships with: a scan that reaches nothing and a
    project with nothing to check both print "0 drifted"."""
    _plain_screen(project, "landing")
    (project / "docs/specs/checkout.spec.json").unlink()

    assert _cli(project, "--check", monkeypatch=monkeypatch) == 1
    assert "no screen declares branchContracts" in capsys.readouterr().err


def test_an_empty_spec_directory_is_red(project, monkeypatch, capsys):
    for path in (project / "docs/specs").glob("*.spec.json"):
        path.unlink()

    assert _cli(project, "--check", monkeypatch=monkeypatch) == 1
    assert "0 spec(s) scanned" in capsys.readouterr().err


def test_spec_without_a_screen_name_is_refused(project, monkeypatch, capsys):
    """--spec names one file, so it cannot mean "all of them"."""
    rc = _cli(project, "--check", "--spec", "docs/specs/checkout.spec.json",
              monkeypatch=monkeypatch)
    assert rc == 1
    assert "a screen name is required" in capsys.readouterr().err


def test_a_missing_harness_does_not_fail_the_gate(project, monkeypatch,
                                                  capsys):
    _cli(project, monkeypatch=monkeypatch)
    (project / "tests/unit/branch-harness/checkout.ts").unlink()

    assert _cli(project, "--check", monkeypatch=monkeypatch) == 0
    assert "harness missing" in capsys.readouterr().out


def test_the_gate_fails_on_a_tree_that_never_generated(project, monkeypatch,
                                                       capsys):
    """The first state a project is in, and the one a check most needs to
    refuse: nothing on disk is not nothing to do."""
    assert _cli(project, "--check", monkeypatch=monkeypatch) == 1
    out = capsys.readouterr().out
    assert "[ABSENT]" in out
    assert "0 up to date, 1 stale" in out


def _unbindable_screen(root: Path, name: str) -> None:
    """A screen whose contract names an operation nothing declares an
    endpoint for. Generation refuses it — correctly — so it stands in for
    any screen a whole-project run cannot produce.

    The reported instance was a sub-spec whose contract referenced an
    operation its SIBLING sub-spec declared the endpoint for; the shape
    that matters here is only that the reference does not bind.
    """
    spec = json.loads((root / "docs/specs/checkout.spec.json").read_text())
    spec["metadata"]["name"] = name.title()
    spec["branchContracts"] = {"methods": {"onConfirmTap": {"branches": [
        {"when": {"api.notDeclaredAnywhere": "empty"},
         "then": {"data.screenState": "error"}},
    ]}}}
    _write(root / f"docs/specs/{name}.spec.json", spec)


def test_one_unproducible_screen_does_not_hide_the_rest(project, monkeypatch,
                                                        capsys):
    """Stopping at the first failure hides every screen after it — the ones
    that are fine, and any other failure. A consumer lost a whole iOS run
    to a single screen this way."""
    _second_screen(project, "cart")
    _unbindable_screen(project, "orders")

    rc = _cli(project, monkeypatch=monkeypatch)
    captured = capsys.readouterr()

    assert rc == 1
    assert "Generated branch tests for 'cart'" in captured.out
    assert "Generated branch tests for 'checkout'" in captured.out
    assert "[FAILED]  orders" in captured.err
    assert "Generated 2 screen(s); 1 failed." in captured.err


def test_a_named_screen_still_answers_with_its_own_error(project, monkeypatch,
                                                         capsys):
    """One screen was asked for, so its failure is the answer — not a
    summary of a project the caller did not ask about."""
    _unbindable_screen(project, "orders")

    rc = _cli(project, "orders", monkeypatch=monkeypatch)

    assert rc == 1
    err = capsys.readouterr().err
    assert "has no `endpoint` declaration" in err
    assert "[FAILED]" not in err


def test_check_does_not_call_an_unproducible_screen_current(project,
                                                            monkeypatch,
                                                            capsys):
    """Not verifiable is not verified: a screen that cannot be generated
    cannot be compared to what is on disk either."""
    _cli(project, monkeypatch=monkeypatch)
    capsys.readouterr()
    _unbindable_screen(project, "orders")

    rc = _cli(project, "--check", monkeypatch=monkeypatch)
    captured = capsys.readouterr()

    assert rc == 1
    assert "1 up to date, 0 stale" in captured.out  # checkout is genuinely fine
    assert "could not be generated, so they were not checked" in captured.err


# --------------------------------------------------------------------- #
# Screens that belong to another platform
#
# Generation used to emit a test file on every platform, holding no
# assertion when every branch was scoped away. That is a test that can
# never fail, and — because generation would write it — `--check` had to
# expect it, so a project that sensibly did not generate it read as one
# with missing output. Both sides move together, per the convention that a
# column which did not run is not printed.
# --------------------------------------------------------------------- #

IOS_ONLY = _contract([
    {"when": {"api.createOrder": "conflict"},
     "then": {"data.screenState": "error"}, "platforms": ["ios"]},
])

PLATFORM_DIRS = {"web": "tests/unit/generated", "ios": "Tests/Generated",
                 "android": "app/src/test/java"}
PLATFORM_ARGS = {"web": {}, "ios": {"module": "App"},
                 "android": {"package": "com.acme.app"}}


@pytest.fixture
def ios_only(tmp_path):
    return _project(tmp_path, IOS_ONLY)


def _gen(root: Path, platform: str, **extra):
    out = PLATFORM_DIRS[platform]
    return generate_branch_tests(
        "checkout", project_root=root, platform=platform, out_dir=out,
        harness_dir=out, **PLATFORM_ARGS[platform], **extra)


@pytest.mark.parametrize("platform", ["web", "android"])
def test_a_screen_scoped_to_another_platform_emits_nothing(ios_only, platform):
    report = _gen(ios_only, platform)

    assert report.platform_applicable is False
    assert report.declared_branches == 0 and report.platform_skipped == 1
    assert not (ios_only / PLATFORM_DIRS[platform]).exists()


def test_the_platform_it_belongs_to_still_emits(ios_only):
    report = _gen(ios_only, "ios")

    assert report.platform_applicable is True
    assert report.test_file.exists()


@pytest.mark.parametrize("platform", ["web", "android"])
def test_check_does_not_expect_what_generation_would_not_write(ios_only,
                                                               platform):
    """The invariant this whole check rests on: --check predicts generate.
    Suppressing one side alone would make them disagree."""
    _gen(ios_only, platform)
    report = _gen(ios_only, platform, check=True)

    assert report.platform_applicable is False
    assert report.absent == [] and report.drifted == []


def test_a_screen_with_active_branches_is_unaffected(project):
    """The ordinary case must not be swept up: platform_skipped is 0 here,
    so nothing about this screen is platform-scoped."""
    report = generate_branch_tests("checkout", project_root=project)
    assert report.platform_applicable is True
    assert report.test_file.exists()


def test_a_contract_of_only_notes_is_not_a_platform_question(tmp_path):
    """`declared_branches == 0` has more than one cause. A contract that
    lists only notes has nothing scoped away, and suppressing it here would
    silently retire a screen for a reason this rule is not about — found by
    a red-check that killed nothing, which is what a missing test looks
    like from the outside."""
    root = _project(tmp_path, _contract([{"note": "polling is out of scope"}]))

    report = generate_branch_tests("checkout", project_root=root)

    assert report.declared_branches == 0
    assert report.platform_skipped == 0
    assert report.platform_applicable is True
    assert report.test_file.exists()


def test_the_summary_separates_not_applicable_from_up_to_date(ios_only,
                                                              monkeypatch,
                                                              capsys):
    """A screen that was never a candidate is not "up to date", and it is
    not a scan that reached nothing either."""
    assert _cli(ios_only, monkeypatch=monkeypatch) == 0
    out = capsys.readouterr().out
    assert "Skipped 'checkout'" in out

    assert _cli(ios_only, "--check", monkeypatch=monkeypatch) == 0
    summary = capsys.readouterr().out
    assert "1 not applicable to this platform" in summary
    assert "0 up to date, 0 stale" in summary


# --------------------------------------------------------------------- #
# Split screens: parent + subSpecs is one screen
# --------------------------------------------------------------------- #

def _split_family(root: Path) -> None:
    """A parent declaring two sub-specs: one holds the contract, the other
    holds the endpoint declaration the contract refers to."""
    spec = json.loads((root / "docs/specs/checkout.spec.json").read_text())

    core = json.loads(json.dumps(spec))
    core.pop("branchContracts")
    core["metadata"]["name"] = "CheckoutCore"
    _write(root / "docs/specs/checkout/checkout-core.spec.json", core)

    panel = json.loads(json.dumps(spec))
    panel["dataFlow"].pop("repositories")       # the sibling declares them
    panel["metadata"]["name"] = "CheckoutPanel"
    _write(root / "docs/specs/checkout/checkout-panel.spec.json", panel)

    _write(root / "docs/specs/checkout.spec.json", {
        "type": "screen_parent_spec", "version": "1.0",
        "metadata": {"name": "Checkout", "displayName": "Checkout",
                     "description": "d", "layoutFile": "checkout"},
        "subSpecs": [{"file": "checkout/checkout-core.spec.json"},
                     {"file": "checkout/checkout-panel.spec.json"}],
    })


def test_a_split_screen_generates_under_the_parent_name(project):
    """The contract is in one sub-spec and the endpoint it names is in a
    sibling. `jui build` and `jui verify` already read parent + subSpecs as
    ONE screen; reading it differently here is what made the siblings
    strangers to each other."""
    _split_family(project)

    report = generate_branch_tests("checkout", project_root=project)

    assert report.test_file.name == "checkout.branches.test.ts"
    assert report.declared_branches == 1
    assert "createOrder" in report.routes


def test_sub_specs_are_not_enumerated_as_screens(project):
    _split_family(project)

    declaring, scanned = discover_branch_screens(project)

    assert declaring == ["checkout"]
    assert "checkout-panel" in scanned  # scanned, so the denominator is honest


def test_naming_a_sub_spec_says_what_it_is(project):
    """It used to fail on whatever its half of the screen could not see —
    an endpoint declared in the sibling — which sends the reader to add a
    declaration that already exists."""
    _split_family(project)

    with pytest.raises(BranchTestGenerationError) as caught:
        generate_branch_tests("checkout-panel", project_root=project)

    assert "is a sub-spec of 'checkout'" in str(caught.value)


def test_the_family_is_the_declaration_not_the_directory(project):
    """Sitting in the same folder is not membership. An undeclared spec
    beside the sub-specs stays a screen of its own."""
    _split_family(project)
    stray = json.loads(
        (project / "docs/specs/checkout/checkout-panel.spec.json").read_text())
    stray["metadata"]["name"] = "Stray"
    _write(project / "docs/specs/checkout/stray.spec.json", stray)

    declaring, _ = discover_branch_screens(project)

    assert sorted(declaring) == ["checkout", "stray"]


# --------------------------------------------------------------------- #
# The other two emitters
#
# Kotlin and Swift go through the same _Emitter, and all three grew the
# check together — so the properties are pinned on all three rather than
# on the one the report came from. A platform whose check quietly wrote
# would be found by nobody: web is the only one with a ticket.
# --------------------------------------------------------------------- #

PLATFORMS = [
    pytest.param("web", {}, "checkout.branches.test.ts",
                 "tests/unit/generated", id="web"),
    pytest.param("ios", {"module": "App"}, "CheckoutBranchesTest.swift",
                 "Tests/Generated", id="ios"),
    pytest.param("android", {"package": "com.example.app"},
                 "CheckoutBranchesTest.kt",
                 "app/src/test/java/com/example/app", id="android"),
]


@pytest.mark.parametrize("platform,kwargs,test_name,out_dir", PLATFORMS)
def test_every_platform_detects_a_stale_copy(project, platform, kwargs,
                                             test_name, out_dir):
    defaults = {"web": ("tests/unit/generated", "tests/unit/branch-harness"),
                "ios": ("Tests/Generated", "Tests/Generated"),
                "android": ("app/src/test/java", "app/src/test/java")}
    out, harness = defaults[platform]
    common = dict(project_root=project, platform=platform, out_dir=out,
                  harness_dir=harness, **kwargs)
    generate_branch_tests("checkout", **common)

    mock = project / "tests/mocks/orders/post_api-user-orders.mock.json"
    data = json.loads(mock.read_text())
    data["scenarios"]["conflict"]["body"] = {"error": {"code": "v2"}}
    _write(mock, data)

    report = generate_branch_tests("checkout", check=True, **common)
    assert [p.name for p in report.drifted] == [test_name]


@pytest.mark.parametrize("platform,kwargs,test_name,out_dir", PLATFORMS)
def test_every_platform_check_digs_nothing(project, platform, kwargs,
                                           test_name, out_dir):
    defaults = {"web": ("tests/unit/generated", "tests/unit/branch-harness"),
                "ios": ("Tests/Generated", "Tests/Generated"),
                "android": ("app/src/test/java", "app/src/test/java")}
    out, harness = defaults[platform]
    # The whole tree, rather than the output path: naming the directory the
    # check should not create tests the path the assertion already assumes,
    # and on a case-insensitive filesystem `Tests/` matched the fixture's
    # own `tests/` and passed for the wrong reason.
    before = {p for p in project.rglob("*")}

    generate_branch_tests("checkout", project_root=project, platform=platform,
                          out_dir=out, harness_dir=harness, check=True,
                          **kwargs)

    assert {p for p in project.rglob("*")} == before
