"""Two repositories declaring the same method name.

`collect_endpoint_ops` keyed a flat `name -> endpoint` dict, so the second
declaration overwrote the first: a spec declaring `getProfile` on both
UserRepository and ProfilingRepository bound `api.getProfile` to whichever
came last, generated no route for the other endpoint, and said nothing. The
screen's contract could not name the endpoint it meant, the unrouted call
599'd during the act, and the spec validated clean — the failure looked like
a broken screen rather than a contract that was never written.

Declaring the same method name on two classes is ordinary: the implementation
has two repositories, and renaming the method in the spec would rename it in
the generated Repository interface and break the hand-written Impl.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_test_cli.branch_tests import (
    BranchTestGenerationError,
    collect_endpoint_ops,
    generate_branch_tests,
)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


_TWO_OWNERS = {
    "repositories": [
        {"name": "UserRepository", "methods": [
            {"name": "getProfile", "endpoint": "GET /api/user/profile"}]},
        {"name": "ProfilingRepository", "methods": [
            {"name": "getProfile", "endpoint": "GET /api/profiling/profile"}]},
    ],
}

_ONE_OWNER = {
    "repositories": [
        {"name": "UserRepository", "methods": [
            {"name": "getProfile", "endpoint": "GET /api/user/profile"}]},
    ],
}


def _project(tmp_path: Path, data_flow_extra, branches) -> Path:
    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "jui.config.json", {"spec_directory": "docs/specs"})
    data_flow = {
        "viewModel": {"methods": [{"name": "onAppear"}], "vars": []},
    }
    data_flow.update(data_flow_extra)
    _write(root / "docs/specs/mypage.spec.json", {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"name": "Mypage", "displayName": "Mypage",
                     "description": "d", "layoutFile": "mypage"},
        "structure": {"components": [], "layout": {}},
        "dataFlow": data_flow,
        "stateManagement": {"uiVariables": []},
        "branchContracts": {"methods": {"onAppear": {"branches": branches}}},
    })
    for name, path in (("user", "/api/user/profile"),
                       ("profiling", "/api/profiling/profile")):
        _write(root / f"tests/mocks/{name}.mock.json", {
            "source": {"method": "GET", "path": path},
            "activeScenario": "success",
            "scenarios": {"success": {"status": 200, "body": {"ok": True}},
                          "failure": {"status": 500, "body": {"ok": False}}},
        })
    return root


def _generate(root: Path):
    return generate_branch_tests(
        "mypage", platform="web", out_dir=root / "out",
        harness_dir=root / "harness", project_root=root,
    )


class TestCollectEndpointOps:
    def test_a_unique_name_keeps_its_bare_key(self):
        """No collision, no rename — the population this fix is not for.

        Keying everything qualified would have changed the op string in every
        generated file on every project without a duplicate name.
        """
        ops = collect_endpoint_ops({"dataFlow": _ONE_OWNER})
        assert list(ops.canonical) == ["getProfile"]
        assert ops.collisions == {}
        assert ops.resolve("getProfile") == "getProfile"

    def test_the_qualified_spelling_also_resolves_when_unique(self):
        ops = collect_endpoint_ops({"dataFlow": _ONE_OWNER})
        assert ops.resolve("UserRepository.getProfile") == "getProfile"

    def test_a_duplicated_name_keeps_both_endpoints(self):
        """The whole defect: two declarations used to leave one key."""
        ops = collect_endpoint_ops({"dataFlow": _TWO_OWNERS})
        assert sorted(ops.canonical) == [
            "ProfilingRepository.getProfile", "UserRepository.getProfile"]
        assert {v["path"] for v in ops.canonical.values()} == {
            "/api/user/profile", "/api/profiling/profile"}

    def test_the_bare_name_stops_resolving_and_is_recorded(self):
        ops = collect_endpoint_ops({"dataFlow": _TWO_OWNERS})
        assert ops.resolve("getProfile") is None
        assert ops.collisions["getProfile"] == [
            "UserRepository.getProfile", "ProfilingRepository.getProfile"]


class TestGeneration:
    def test_a_bare_reference_to_a_duplicated_name_is_refused(self, tmp_path):
        root = _project(tmp_path, _TWO_OWNERS, [
            {"when": {"api.getProfile": "failure"},
             "then": {"api.getProfile": "called"}}])
        with pytest.raises(BranchTestGenerationError) as e:
            _generate(root)
        msg = str(e.value)
        assert "UserRepository.getProfile" in msg
        assert "ProfilingRepository.getProfile" in msg

    def test_qualified_references_bind_both_endpoints(self, tmp_path):
        root = _project(tmp_path, _TWO_OWNERS, [
            {"when": {"api.UserRepository.getProfile": "failure"},
             "then": {"api.UserRepository.getProfile": "called"}},
            {"when": {"api.ProfilingRepository.getProfile": "failure"},
             "then": {"api.ProfilingRepository.getProfile": "called"}},
        ])
        _generate(root)
        content = (root / "out" / "mypage.branches.test.ts").read_text()
        assert '"UserRepository.getProfile"' in content
        assert '"ProfilingRepository.getProfile"' in content
        # Both endpoints reach the route table — the half that used to vanish.
        assert "/api/user/profile" in content
        assert "/api/profiling/profile" in content

    def test_a_request_match_can_be_qualified_too(self, tmp_path):
        """`then` must take the same qualification as `when`.

        Being able to select the endpoint in `when` but not in `then` would
        leave the contract unable to say anything about the one it selected.
        """
        root = _project(tmp_path, _TWO_OWNERS, [
            {"when": {"api.UserRepository.getProfile": "success"},
             "then": {"api.UserRepository.getProfile.request": {"scope": "full"}}},
        ])
        _generate(root)
        content = (root / "out" / "mypage.branches.test.ts").read_text()
        assert '"UserRepository.getProfile"' in content
        assert '"scope": "full"' in content

    def test_an_unreferenced_duplicate_still_joins_the_table_once(self, tmp_path):
        """The incidental-endpoint pass is keyed by endpoint, not op string.

        Keyed by op string it would have added a second route over a path a
        contract had already bound under its bare name, and the runtime
        records against whichever route matches first — so every assert
        under the other spelling would count zero.
        """
        root = _project(tmp_path, _TWO_OWNERS, [
            {"when": {"api.UserRepository.getProfile": "failure"},
             "then": {"api.UserRepository.getProfile": "called"}},
        ])
        _generate(root)
        content = (root / "out" / "mypage.branches.test.ts").read_text()
        assert content.count('op: "UserRepository.getProfile"') == 1
        assert content.count('op: "ProfilingRepository.getProfile"') == 1

    def test_mixing_two_spellings_for_one_endpoint_is_refused(self, tmp_path):
        """One endpoint, one name.

        `countFor` matches recorded calls by op string and only the first
        matching route records, so a second route over the same path makes
        every assert under the other spelling count zero — a contract that is
        written and never checked, which is the failure this ticket is about.
        """
        root = _project(tmp_path, _ONE_OWNER, [
            {"when": {"api.getProfile": "failure"},
             "then": {"api.UserRepository.getProfile": "called"}},
        ])
        with pytest.raises(BranchTestGenerationError) as e:
            _generate(root)
        assert "one endpoint by one name" in str(e.value)
