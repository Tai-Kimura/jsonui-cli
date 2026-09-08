"""A unit target several screens own, sitting in one screen's spec.

This is the mirror of the app-level direction, and it is the one that finds
what is already there: before the app contracts spec existed, a target no
single screen owned had nowhere else to go, so it was filed under whichever
screen happened to declare it and was then reported as that screen's.

⚠️ The restriction to "two or more owners" is forced, not cautious, and the
arms below exist mostly to hold it in place. Neither declaration-site caller
resolves the component source, so every owner count is a LOWER BOUND:

    >= 2 owners      adding the missing source keeps it >= 2   sound
    exactly 1 owner  adding the missing source makes it 2      NOT sound

So "declared in A's spec, but B owns it" is deliberately not reported. The
full rule might answer `{A, B}`, which is app-owned and belongs near neither.

Measured on the shared corpus while this was written: one face has 5 such
declarations, one of them owned by 9 screens, and three faces have none. The
descent from 2 to 1 is therefore not a hypothetical shape -- targets with
exactly two owners exist there.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import unit_contracts as uc  # noqa: E402


def _repo(tmp_path, screens: dict, app: dict | None = None) -> Path:
    """`screens` maps name -> (dataFlow, unitContracts target or None)."""
    specs = tmp_path / "docs" / "screens"
    specs.mkdir(parents=True)
    for name, (flow, target) in screens.items():
        spec: dict = {"type": "screen", "metadata": {"name": name}}
        if flow:
            spec["dataFlow"] = flow
        if target:
            spec["unitContracts"] = [{"target": target,
                                      "cases": [{"name": "works"}]}]
        (specs / f"{name}.spec.json").write_text(json.dumps(spec), "utf-8")
    if app is not None:
        (specs / "whole.spec.json").write_text(json.dumps({
            "type": "app_contracts_spec", "metadata": {"name": "whole"},
            "unitContracts": [app],
        }), "utf-8")
    (tmp_path / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens",
        "platforms": {"web": {"unitTestsDir": "tests/web"}},
    }), "utf-8")
    (tmp_path / "tests" / "web").mkdir(parents=True)
    return tmp_path


def _repo_named(target: str):
    return {"repositories": [{"name": target, "methods": []}]}


def _problems(root) -> list[str]:
    return uc.check_unit_contracts(root).problems


def test_a_target_two_screens_own_is_reported(tmp_path):
    root = _repo(tmp_path, {
        "Login": (_repo_named("UserRepository"), "UserRepository"),
        "Mypage": (_repo_named("UserRepository"), None),
    })
    hits = [p for p in _problems(root) if "UserRepository" in p]
    assert len(hits) == 1, _problems(root)
    # The count and the remedy are both in the sentence: a reader who is told
    # only "wrong place" has to work out where the right one is.
    assert "2 screens own it" in hits[0]
    assert "app contracts spec" in hits[0]


def test_the_owners_are_named(tmp_path):
    root = _repo(tmp_path, {
        "Login": (_repo_named("UserRepository"), "UserRepository"),
        "Mypage": (_repo_named("UserRepository"), None),
    })
    hits = [p for p in _problems(root) if "UserRepository" in p]
    assert "Login" in hits[0] and "Mypage" in hits[0]


def test_a_target_its_own_screen_owns_is_silent(tmp_path):
    root = _repo(tmp_path, {
        "Login": (_repo_named("LoginRepository"), "LoginRepository"),
        "Mypage": (_repo_named("UserRepository"), None),
    })
    assert [p for p in _problems(root) if "LoginRepository" in p] == []


def test_a_target_one_other_screen_owns_is_deliberately_silent(tmp_path):
    """⚠️ The arm that holds the restriction in place.

    `Settings` declares a target only `Mypage` owns. That looks like the
    clearest possible misplacement, and reporting it would be UNSOUND: the
    component source is unresolved, so the full rule may answer `{Settings,
    Mypage}` -- app-owned, and belonging in neither spec. Deleting this arm
    and widening the check to `owners[0] != screen` would pass every other
    arm in this file.
    """
    root = _repo(tmp_path, {
        "Mypage": (_repo_named("UserRepository"), None),
        "Settings": ({}, "UserRepository"),
    })
    assert [p for p in _problems(root) if "UserRepository" in p] == []


def test_a_target_nobody_owns_is_silent(tmp_path):
    # Zero owners is UNDETERMINED without the full symbol table, and an
    # unanswered question is not a finding any more than it is a permission.
    root = _repo(tmp_path, {"Login": ({}, "SomeHelper")})
    assert [p for p in _problems(root) if "SomeHelper" in p] == []


def test_one_line_per_target_not_per_declaring_screen(tmp_path):
    # The same target declared twice is one misplacement, not two. Reported
    # per declaration, a target declared in nine screens would fill the
    # output with nine remedies that are all the same move.
    root = _repo(tmp_path, {
        "Login": (_repo_named("LoginUseCase"), "LoginUseCase"),
        "TwoFa": (_repo_named("LoginUseCase"), "LoginUseCase"),
    })
    hits = [p for p in _problems(root) if "LoginUseCase" in p]
    assert len(hits) == 1, hits


def test_an_app_level_declaration_is_not_judged_by_this_direction(tmp_path):
    # That pair is the app-level check's to report. Two tools naming the same
    # pair from opposite ends hands a reader one fact twice, with two
    # different remedies.
    root = _repo(tmp_path, {"Login": (_repo_named("UserRepository"), None)},
                 app={"target": "UserRepository", "cases": [{"name": "x"}]})
    assert [p for p in _problems(root)
            if "app contracts spec, which is where" in p] == []


def test_the_limit_is_stated_on_a_run_with_no_app_spec(tmp_path):
    root = _repo(tmp_path, {"Login": (_repo_named("LoginRepository"),
                                      "LoginRepository")})
    assert uc.check_unit_contracts(root).notes == [uc.OWNERSHIP_PARTIAL]


def test_an_unloadable_rule_is_said_once_not_twice(tmp_path):
    """Both directions raise the same sentence about the same outage.

    Printed twice it reads as two faults, and `problems` is what a reader
    counts.
    """
    root = _repo(tmp_path, {"Login": (_repo_named("UserRepository"), "UserRepository"),
                            "Mypage": (_repo_named("UserRepository"), None)},
                 app={"target": "Other", "cases": [{"name": "x"}]})
    real = uc._ownership_rule
    uc._ownership_rule = lambda: None
    try:
        problems = _problems(root)
    finally:
        uc._ownership_rule = real
    assert problems.count(uc.OWNERSHIP_UNAVAILABLE) == 1, problems
