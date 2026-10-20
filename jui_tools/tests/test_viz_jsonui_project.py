"""Specs, layouts, tests and tasks of a JsonUI project, and the sheet (jui viz P4)."""
from __future__ import annotations

import asyncio
import json
import os
import socket
from pathlib import Path

import aiohttp
import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import robots
from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.sheet import build_doc, sheet_for
from jui_cli.viz.sources.jsonui_project import JsonUIProject, layout_nodes, section_items
from jui_cli.viz.sources.tasks import TaskBook
from jui_cli.viz.state import VizState

LAYOUT = {
    "type": "SafeAreaView", "id": "login_root",
    "child": [
        {"type": "Label", "id": "title"},
        {"type": "View", "children": [{"type": "TextField", "id": "email"}, {"type": "Button", "id": "submit"}]},
    ],
}


def _spec(name: str, **extra) -> dict:
    spec = {
        "type": "screen_spec",
        "metadata": {"name": name, "displayName": f"{name} 画面", "description": "d", "platforms": ["ios"], "layoutFile": name.lower()},
        "structure": {"components": [], "layout": {}},
        "stateManagement": {"uiVariables": [{"name": "email", "type": "String", "initial": ""}],
                            "eventHandlers": [{"name": "onSubmit", "description": "send"}]},
        "dataFlow": {"viewModel": {"methods": ["onSubmit"], "vars": ["email"]}, "repositories": [{"name": "AuthRepository", "methods": []}],
                     "apiEndpoints": [{"path": "/login", "method": "POST"}]},
        "userActions": [{"action": "Tap submit", "processing": "onSubmit"}],
        "transitions": [{"condition": "success", "destination": "Home"}],
        "relatedFiles": [{"type": "ViewModel", "path": f"app/{name}ViewModel.swift"}],
    }
    spec.update(extra)
    return spec


def make_project(root: Path) -> Path:
    (root / "docs/screens/json/auth").mkdir(parents=True)
    (root / "docs/screens/layouts").mkdir(parents=True)
    (root / "tests/screens").mkdir(parents=True)
    (root / "app").mkdir()
    (root / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/screens/json", "layouts_directory": "docs/screens/layouts"}))
    (root / "docs/screens/json/auth/login.spec.json").write_text(json.dumps(_spec("Login", branchContracts={
        "methods": {"onSubmit": {"branches": [{"when": {"email": "empty"}, "then": {"error": "@required"}}, {"note": "network down"}]}}})))
    (root / "docs/screens/json/empty.spec.json").write_text(json.dumps({"metadata": {}}))
    (root / "docs/screens/layouts/login.json").write_text(json.dumps(LAYOUT))
    (root / "tests/screens/login.test.json").write_text(json.dumps({"source": {"layout": "docs/screens/layouts/login.json"},
                                                                      "cases": [{"name": "a"}, {"name": "b"}, {"nope": 1}]}))
    return root


def _summary(project, stem):
    return next(s for s in project.summaries(0) if s["file"].endswith(stem))


def test_the_usual_spec_reads_its_structure_from_the_layout_file(tmp_path):
    """layoutFile, not structure.components, is what specs use (0 of 279 list components)."""
    project = JsonUIProject(make_project(tmp_path), "p")
    project.load_all(0)
    login = _summary(project, "login.spec.json")
    sections = {s["key"]: s for s in login["sections"]}
    assert sections["structure"] == {"key": "structure", "state": "written", "items": 5}  # 5 typed nodes in LAYOUT
    assert sections["branchContracts"]["items"] == 2
    assert sections["metadata"]["items"] == 5
    assert login["name"] == "Login 画面" and login["file"] == "docs/screens/json/auth/login.spec.json"
    assert login["tests"]["total"] == 2  # cases with a name, joined through source.layout
    # impl: related ViewModel missing, Layout present -> 1 of 2
    assert {k: login["impl"][k] for k in ("total", "done", "related", "layout")} == {
        "total": 2, "done": 1, "related": {"total": 1, "done": 0}, "layout": True}
    assert login["bucket"] == "partial"
    empty = _summary(project, "empty.spec.json")
    assert empty["bucket"] == "todo" and all(s["state"] == "empty" for s in empty["sections"])


def test_layout_nodes_follow_child_and_children():
    nodes = [(n["type"], n.get("id"), n["depth"]) for n in layout_nodes_from(LAYOUT)]
    assert nodes == [("SafeAreaView", "login_root", 0), ("Label", "title", 1), ("View", None, 1),
                     ("TextField", "email", 2), ("Button", "submit", 2)]


def layout_nodes_from(tree) -> list:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(tree, f)
    try:
        return layout_nodes(Path(f.name))
    finally:
        os.unlink(f.name)


def test_listed_components_still_win_when_a_spec_has_them():
    spec = _spec("X", structure={"components": [{"type": "Label", "id": "a", "description": "d"}]})
    assert section_items(spec, "structure", layout_nodes=9) == 1


def test_a_rewritten_section_is_writing_for_ten_seconds_and_a_broken_file_keeps_the_summary(tmp_path):
    root = make_project(tmp_path)
    project = JsonUIProject(root, "p")
    project.load_all(0)
    path = root / "docs/screens/json/auth/login.spec.json"
    spec = json.loads(path.read_text())
    spec["transitions"].append({"condition": "cancel", "destination": "Top"})
    path.write_text(json.dumps(spec))
    assert project.reload_spec(path, 1_000, by="agent-1") == ["transitions"]
    states = {s["key"]: s["state"] for s in project.summaries(5_000)[0]["sections"]}
    assert states["transitions"] == "writing" and states["metadata"] == "written"
    assert {s["key"]: s["state"] for s in project.summaries(11_001)[0]["sections"]}["transitions"] == "written"
    path.write_text('{"metadata": ')  # mid-write
    project.reload_spec(path, 12_000, by="agent-1")
    after = project.summaries(12_500)[0]
    assert {s["key"]: s["items"] for s in after["sections"]}["transitions"] == 2  # previous summary kept
    assert after["by"] == "agent-1" and after["bucket"] == "live"


def test_edits_to_the_layout_or_a_related_file_name_the_spec(tmp_path):
    root = make_project(tmp_path)
    project = JsonUIProject(root, "p")
    project.load_all(0)
    login_id = "p:auth/login.spec.json"
    assert project.specs_touching(str(root / "docs/screens/layouts/login.json")) == [login_id]
    assert project.specs_touching(str(root / "app/LoginViewModel.swift")) == [login_id]
    assert project.specs_touching(str(root / "app/Other.swift")) == []


def test_the_world_links_edits_tasks_and_test_runs(tmp_path):
    root = make_project(tmp_path)
    state = VizState()
    world = World(state)
    base = {"session_id": "s1", "cwd": str(root)}
    world.apply_hook({**base, "hook_event_name": "SessionStart"}, 0)
    world.publish()
    assert len(state.slices["specs"]) == 2  # loaded when the JsonUI room appeared

    vm = str(root / "app/LoginViewModel.swift")
    world.apply_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Write", "tool_use_id": "w", "tool_input": {"file_path": vm}}, 100)
    Path(vm).write_text("class LoginViewModel {}")
    world.apply_hook({**base, "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_use_id": "w", "tool_input": {"file_path": vm}}, 200)
    world.publish()
    login = next(s for s in state.slices["specs"] if s["file"].endswith("login.spec.json"))
    assert login["by"] == "s1" and login["bucket"] == "live" and (login["impl"]["total"], login["impl"]["done"]) == (2, 2)

    world.apply_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "TodoWrite", "tool_use_id": "t",
                      "tool_input": {"todos": [{"content": "Login 画面のテストを書く", "status": "in_progress", "activeForm": "書いている"},
                                               {"content": "ほか", "status": "pending"}]}}, 300)
    world.publish()
    tasks = state.slices["tasks"]
    assert [t["status"] for t in tasks] == ["in_progress", "pending"]
    assert tasks[0]["specId"] == f"{state.slices['projects'][0]['id']}:auth/login.spec.json" and "specId" not in tasks[1]

    cmd = "xcodebuild test -scheme App -destination 'platform=iOS Simulator,name=iPhone 16'"
    world.apply_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "b", "tool_input": {"command": cmd}}, 400)
    world.publish()
    assert state.slices["tests"][0]["status"] == "running" and state.slices["tests"][0]["platform"] == "ios"
    world.apply_hook({**base, "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_use_id": "b", "tool_input": {"command": cmd},
                      "tool_response": {"stdout": "Executed 8 tests, with 1 failure (1 unexpected)", "stderr": ""}}, 900)   # a real failure: 1 unexpected
    world.publish()
    run = state.slices["tests"][0]
    assert run["status"] == "failed" and run["summary"] == "7 passed, 1 failed" and run["endedAt"] == 900

    world.tick(20_000)
    world.publish()
    assert "by" not in next(s for s in state.slices["specs"] if s["file"].endswith("login.spec.json"))


def test_a_room_that_is_not_jsonui_has_no_specs(tmp_path):
    state = VizState()
    world = World(state)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(tmp_path)}, 0)
    world.publish()
    assert state.slices["specs"] == [] and state.slices["projects"][0]["jsonui"] is False


def test_task_book_replaces_todos_and_follows_hooks():
    book = TaskBook()
    book.from_todowrite("s", "s", [{"content": "a", "status": "pending"}, {"content": "b", "status": "pending"}], 1)
    book.from_todowrite("s", "s", [{"content": "a", "status": "completed"}], 2)
    assert [(t["subject"], t["status"]) for t in book.items()] == [("a", "completed")]
    assert book.items()[0]["completedAt"] == 2
    book.created("s", {"task_id": 7, "task_subject": "x"}, "agent", 3)
    book.completed("s", {"task_id": 7}, 4)
    assert next(t for t in book.items() if t["id"] == "7")["status"] == "completed"
    book.link_specs({"login": "p:login", "home": "p:home"})
    book.created("s", {"task_id": 8, "task_subject": "login と home"}, "agent", 5)
    book.link_specs({"login": "p:login", "home": "p:home"})
    assert "specId" not in next(t for t in book.items() if t["id"] == "8")  # two hits: no link


def test_sheet_doc_has_the_renderers_shape(tmp_path):
    project = JsonUIProject(make_project(tmp_path), "p")
    project.load_all(0)
    doc = sheet_for(project, "p:auth/login.spec.json")
    assert [c[:2] for c in doc["components"]] == [["SafeAreaView", "login_root"], ["Label", "title"], ["View", ""],
                                                   ["TextField", "email"], ["Button", "submit"]]
    assert [c[3] for c in doc["components"]] == [0, 1, 1, 2, 2]   # the Layout's depth, as a number (2026-10-20)
    assert doc["layoutChildren"] == ["login_root", "title", "email", "submit"]
    assert doc["uiVariables"] == [["email", "String", ""]] and doc["vmMethods"] == ["onSubmit"]
    assert doc["repositories"] == ["AuthRepository"] and doc["apis"][0][1:] == ["POST", "/login"]
    assert doc["branches"] == [["onSubmit", {"email": "empty"}, {"error": "@required"}], ["onSubmit", "note", "network down"]]
    assert doc["related"] == [["ViewModel", "app/LoginViewModel.swift", False]]
    assert sheet_for(project, "p:nope") is None
    long = build_doc({"userActions": [{"action": "a" * 1000, "processing": "p"}]}, [], [], {"total": 0, "done": 0})
    assert len(long["userActions"][0][0]) == 300


def test_spec_sheet_over_the_websocket(tmp_path):
    project = JsonUIProject(make_project(tmp_path), "p")
    project.load_all(0)

    async def main():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        ctx = ServerContext(config=VizConfig(), port=port, token="t" * 43, state=VizState(),
                            sheet=lambda sid: sheet_for(project, sid))
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        try:
            ws = await client.ws_connect("/ws", headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"})
            await ws.receive_json()
            await ws.send_json({"type": "auth", "token": "t" * 43})
            await ws.receive_json()
            await ws.receive_json()
            await ws.send_json({"type": "spec.sheet", "reqId": 1, "specId": "p:auth/login.spec.json"})
            reply = await ws.receive_json(timeout=2)
            assert reply["type"] == "sheet" and reply["reqId"] == 1 and reply["cards"]["metadata"]["name"] == "Login"
            await ws.send_json({"type": "spec.sheet", "reqId": 2, "specId": "p:nope"})
            assert await ws.receive_json(timeout=2) == {"type": "ack", "reqId": 2, "ok": False, "error": "unknown spec"}
            await ws.close()
        finally:
            await client.close()

    asyncio.run(main())


def test_test_command_summaries():
    # XCTExpectFailure's 2 are expected (0 unexpected): the run passed (ticket 2026-10-20-jui-viz-test-run-ios-shows-
    # failed-while-passing; this arm held "10 passed, 2 failed" before)
    assert robots.test_summary("Executed 1 test, with 0 failures\n...\nExecuted 12 tests, with 2 failures (0 unexpected)") == ("12 passed, 0 failed", 12, 0)
    assert robots.test_summary("Executed 12 tests, with 3 failures (1 unexpected)") == ("11 passed, 1 failed", 11, 1)
    assert robots.test_summary("12 tests completed, 1 failed") == ("11 passed, 1 failed", 11, 1)
    assert robots.test_summary("  2 failed\n  30 passed (40s)") == ("30 passed, 2 failed", 30, 2)
    assert robots.test_summary("BUILD SUCCESSFUL in 3s") == ("BUILD SUCCESSFUL", None, 0)
    assert robots.test_summary("") == ("", None, None)
    assert robots.test_platform("./gradlew connectedDebugAndroidTest") == "android"
    assert robots.test_platform("npx playwright test") == "web"


def test_a_new_artifact_is_carried_but_an_edit_is_not(tmp_path):
    root = make_project(tmp_path)
    state = VizState()
    world = World(state)
    base = {"session_id": "s1", "cwd": str(root)}
    world.apply_hook({**base, "hook_event_name": "SessionStart"}, 0)
    new = root / "tests/screens/home.test.json"
    world.apply_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Write", "tool_use_id": "n", "tool_input": {"file_path": str(new)}}, 10)
    new.write_text("{}")
    world.apply_hook({**base, "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_use_id": "n", "tool_input": {"file_path": str(new)}}, 20)
    world.publish()
    agent = state.slices["agents"][0]
    assert agent["state"] == "carry" and agent["act"] == "運ぶ tests/screens/home.test.json"
    old = root / "docs/screens/layouts/login.json"
    world.tick(5_000)
    world.apply_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_use_id": "e", "tool_input": {"file_path": str(old)}}, 6_000)
    world.apply_hook({**base, "hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_use_id": "e", "tool_input": {"file_path": str(old)}}, 6_100)
    world.publish()
    assert state.slices["agents"][0]["state"] == "idle"  # an edit of an existing file is not carried


# ---------------------------------------------------------------- ticket 2026-10-20-jui-viz-test-run-ios-shows-failed-while-passing
# The requester's screen: "iOS 失敗 · 0 passed, 36 failed" for a run that passed 36 (TEST SUCCEEDED). Counts came from
# "(\d+) failed" anywhere, so an agent's echoed `passed=36 failed=0` read as 36 failed.
TODAY = "rc=0\n** TEST SUCCEEDED **\npassed=36 failed=0\n\n"


@pytest.mark.parametrize("output, want", [
    (TODAY, ("** TEST SUCCEEDED **", None, 0)),                                                    # today's output itself
    ("passed=36 failed=0\n", ("", None, None)),                                                    # an echo is no runner's line
    ("writing /tmp/run 3 failed.log\nsee docs/5 failed attempts.md\n", ("", None, None)),          # numbers and "failed" in a path or a sentence
    ("test_2_failed_logins_lock_the_account PASSED\n", ("", None, None)),                          # a test's name
    ("=== 1 failed, 3 passed in 2.1s ===\n--- rerun ---\n4 passed in 1.0s\n", ("4 passed, 0 failed", 4, 0)),   # pytest's rerun: the last line alone
    ("rc=0\n** TEST FAILED **\n", ("** TEST FAILED **", None, None)),                             # a redirected failed run, exit 0
    ("Test case 'A.t1()' passed on 'Clone 1 of iPhone'\nTest case 'A.t2()' passed on 'Clone 2 of iPhone'\n** TEST SUCCEEDED **\n",
     ("2 passed, 0 failed", 2, 0)),                                                                # parallel testing: no Executed line
    ("Test case 'A.t1()' passed on 'Clone 1'\nTest case 'A.t2()' failed on 'Clone 2'\n** TEST FAILED **\n", ("1 passed, 1 failed", 1, 1)),
    ("Executed 5 tests, with 1 failure (1 unexpected)\n** TEST SUCCEEDED **\n", ("** TEST SUCCEEDED **", None, 0)),   # the mark decides
    ("Tests:       1 failed, 35 passed, 36 total\n", ("35 passed, 1 failed", 35, 1)),               # jest
    ("4057 passed, 16 skipped in 300.1s\n", ("4057 passed, 0 failed", 4057, 0)),                    # pytest -q
])
def test_counts_come_only_from_a_runners_own_summary_line(output, want):
    assert robots.test_summary(output) == want


def test_a_redirected_xcodebuild_failure_with_exit_code_0_is_a_failed_run_and_todays_is_passed(tmp_path):
    root = make_project(tmp_path)
    for out, want in ((TODAY, "passed"), ("rc=0\n** TEST FAILED **\n", "failed")):
        world = World(VizState())
        base = {"session_id": "s1", "cwd": str(root)}
        world.apply_hook({**base, "hook_event_name": "SessionStart"}, 0)
        cmd = "cd ios && xcodebuild test -scheme App > $L 2>&1; echo rc=$?"
        world.apply_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": cmd}}, 1)
        world.apply_hook({**base, "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": cmd},
                          "tool_response": {"stdout": out, "stderr": ""}}, 2)
        runs = list(world.tests.values())
        assert len(runs) == 1 and runs[0]["status"] == want, (out, runs)
