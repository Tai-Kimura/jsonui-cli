"""A saved or live result reaches its app's spec when the apps' test folders sit inside the room's own
(10-19 ticket 2026-10-19-jui-viz-saved-results-tie-to-the-outer-tests-folder).

The measured shape: the room's config reads tests/ (no specs of its own), the admin and user apps declare
testDir ../tests/admin and ../tests/user, and both apps have screens/account_settings.test.json. Until
2.3.2 every one of that room's 1156 saved rows reached nothing: tests/user/flows/x was also the room's
user/flows/x, which agrees with the driver's ../tests/user/flows/x for longer than the user app's flows/x,
so the room's own app (no specs) won; and the two apps' screens/account_settings tied.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState


def _app(room: Path, app: str, screens: list[str]) -> None:
    (room / app).mkdir(parents=True)
    (room / app / "jui.config.json").write_text(json.dumps({
        "spec_directory": f"../docs/{app}/screens/json", "layouts_directory": f"../docs/{app}/screens/layouts",
        "test": {"testDir": f"../tests/{app}"}}))
    for name in screens:
        spec_dir, layouts = room / f"docs/{app}/screens/json", room / f"docs/{app}/screens/layouts"
        spec_dir.mkdir(parents=True, exist_ok=True)
        layouts.mkdir(parents=True, exist_ok=True)
        (spec_dir / f"{name}.spec.json").write_text(json.dumps({"metadata": {"name": f"{app}-{name}", "layoutFile": name}}))
        (layouts / f"{name}.json").write_text(json.dumps({"type": "View", "id": "root"}))
        test = room / f"tests/{app}/screens/{name}.test.json"
        test.parent.mkdir(parents=True, exist_ok=True)
        test.write_text(json.dumps({"source": {"layout": f"../../../docs/{app}/screens/layouts/{name}.json"},
                                    "cases": [{"name": "ok"}, {"name": "ng"}]}))


def _room(tmp_path: Path) -> Path:
    room = tmp_path / "room"
    room.mkdir()
    (room / "jui.config.json").write_text("{}")                   # the room's own app: tests/, no specs
    _app(room, "admin", ["account_settings", "admin_users"])
    _app(room, "user", ["account_settings", "booking_confirm"])
    return room


def _world(room: Path) -> tuple[World, VizState]:
    state = VizState()
    world = World(state)
    world.apply_hook({"session_id": "s0", "cwd": str(room), "hook_event_name": "SessionStart"}, 0)
    world.publish()
    return world, state


def _tests(state: VizState, name: str) -> dict:
    return next(s["tests"] for s in state.slices["specs"] if s["name"] == name)


def _row(app: str, file: str, case: str, status: str) -> dict:
    return {"platform": "web", "app": f"com.acme.{app}", "run": f"{app}-{file}-saved", "file": file,
            "test": file, "case": case, "status": status, "t": 1_000}


def test_a_saved_row_reaches_the_app_whose_test_folder_is_innermost(tmp_path):
    world, state = _world(_room(tmp_path))
    world.apply_saved_results([
        _row("user", "../tests/user/screens/booking_confirm.test.json", "ok", "passed"),
        _row("user", "../tests/user/screens/booking_confirm.test.json", "ng", "failed"),
        _row("admin", "../tests/admin/screens/admin_users.test.json", "ok", "passed"),
    ])
    world.publish()
    assert (_tests(state, "user-booking_confirm")["passed"], _tests(state, "user-booking_confirm")["failed"]) == (1, 1)
    assert _tests(state, "admin-admin_users")["passed"] == 1


def test_the_same_file_name_in_two_apps_is_told_apart_by_the_folder_the_driver_names(tmp_path):
    world, state = _world(_room(tmp_path))
    world.apply_saved_results([
        _row("admin", "../tests/admin/screens/account_settings.test.json", "ok", "passed"),
        _row("user", "../tests/user/screens/account_settings.test.json", "ok", "failed"),
    ])
    world.publish()
    assert (_tests(state, "admin-account_settings")["passed"], _tests(state, "admin-account_settings")["failed"]) == (1, 0)
    assert (_tests(state, "user-account_settings")["passed"], _tests(state, "user-account_settings")["failed"]) == (0, 1)


def test_a_bare_file_name_that_two_apps_have_still_reaches_neither(tmp_path):
    """iOS names the bare file: nothing tells the apps apart, so the row is not guessed into one."""
    world, state = _world(_room(tmp_path))
    world.apply_saved_results([{**_row("user", "account_settings.test.json", "ok", "passed"), "platform": "ios"}])
    world.publish()
    assert _tests(state, "admin-account_settings")["passed"] == 0
    assert _tests(state, "user-account_settings")["passed"] == 0


def test_a_live_run_reaches_the_inner_apps_spec_and_the_static_totals_count_each_file_once(tmp_path):
    room = _room(tmp_path)
    world, state = _world(room)
    assert _tests(state, "user-booking_confirm")["total"] == 2   # the room's own app does not count tests/user again
    at = int(time.time() * 1000)
    world.apply_hook({"session_id": "s0", "cwd": str(room / "user"), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                      "tool_use_id": "b1", "tool_input": {"command": "npx playwright test"}}, at)
    run = str(uuid.uuid4())

    def rec(event, **kw):
        return {"v": 1, "t": at + 1, "platform": "web", "run": run, "event": event, **kw}

    world.apply_progress(rec("run_start", files=1), "web", None, at + 1)
    for case in ("ok", "ng"):
        world.apply_progress(rec("case_end", file="../tests/user/screens/booking_confirm.test.json", test="booking_confirm",
                                 case=case, attempt=1, status="passed", durationMs=1), "web", None, at + 1)
    world.tick(at + 2)
    world.publish()
    assert _tests(state, "user-booking_confirm")["passed"] == 2
