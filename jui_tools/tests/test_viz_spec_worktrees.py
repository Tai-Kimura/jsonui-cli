"""The spec board shows the worktrees sessions work in (ticket 2026-10-23-jui-viz-spec-board-shows-worktree-in-progress):
a session's git worktree of a room's repository, outside the room, had its specs on the board only after a merge
and a pull.

A room shows each of its apps' worktrees that a session not ended works in, as an app of its own
("<app>@<branch>", every row tagged with its branch and the worktree's folder), beside the room's own app (tagged
with the room's branch then): a spec in both checkouts is two rows, never one dropped. A worktree no session works
in is not shown; one inside the room is shown the same way (the room's walk does not enter it), and a worktree gone or left takes its rows
with it. git is read, never written or run (the repository's files are the same after).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from jui_cli.viz.ingest import WORKTREE_TOUCH_MS, WORKTREES_EVERY_MS, World
from jui_cli.viz.sources.jsonui_project import JsonUIProject, git_dir, head_branch, worktrees
from jui_cli.viz.state import VizState


def _spec(name: str, description: str = "d") -> dict:
    return {"type": "screen_spec", "metadata": {"name": name, "displayName": name, "description": description,
                                                "platforms": ["ios"]}}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(cwd), "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})


def _room(tmp_path: Path, app: str = "") -> tuple[Path, Path]:
    """A repository whose room has one app (at its root, or in ``app``/) with login.spec.json, committed on main, and
    a worktree of it outside the room on feat/x: the room's root and the worktree's folder."""
    root = tmp_path / "room"
    where = root / app if app else root
    spec_dir = where / "docs" / "screens" / "json"
    spec_dir.mkdir(parents=True)
    (root / "jui.config.json").write_text("{}", encoding="utf-8")
    if app:
        (where / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/screens/json"}), encoding="utf-8")
    (spec_dir / "login.spec.json").write_text(json.dumps(_spec("Login")), encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    wt = tmp_path / "scratch" / "wt"
    _git(root, "worktree", "add", "-q", "-b", "feat/x", str(wt))
    wt_specs = (wt / app if app else wt) / "docs" / "screens" / "json"
    (wt_specs / "login.spec.json").write_text(json.dumps(_spec("Login", "changed in the worktree")), encoding="utf-8")
    (wt_specs / "orders.spec.json").write_text(json.dumps(_spec("Orders")), encoding="utf-8")
    return root, wt


def _tree_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(folder)).encode() + p.read_bytes())
    return h.hexdigest()


def _rows(project: JsonUIProject) -> dict[str, dict]:
    return {s["id"]: s for s in project.summaries(0)}


def test_git_is_read_from_the_repositorys_files(tmp_path):
    root, wt = _room(tmp_path)
    assert head_branch(git_dir(root)) == "main" and git_dir(wt) == (root / ".git" / "worktrees" / "wt").resolve()
    assert worktrees(root) == [(wt, "feat/x")]


def test_a_worktree_a_session_works_in_is_shown_beside_the_rooms_own(tmp_path):
    root, wt = _room(tmp_path)
    before = _tree_hash(root / ".git")
    project = JsonUIProject(root, "p")
    project.load_all(0)
    assert sorted(_rows(project)) == ["p:login.spec.json"] and "checkout" not in _rows(project)["p:login.spec.json"]
    assert project.set_worktrees([str(wt / "docs")], 10) is True
    rows = _rows(project)
    assert sorted(rows) == ["p:@feat/x/login.spec.json", "p:@feat/x/orders.spec.json", "p:login.spec.json"]
    assert rows["p:login.spec.json"]["checkout"] == {"branch": "main"}   # the room's row: its own branch, both shown
    wt_login = rows["p:@feat/x/login.spec.json"]
    assert wt_login["app"] == "@feat/x" and wt_login["checkout"]["branch"] == "feat/x"
    assert wt_login["checkout"]["worktree"].endswith("scratch/wt")
    assert project.set_worktrees([str(wt / "docs")], 20) is False   # nothing changed: nothing read again
    assert _tree_hash(root / ".git") == before   # read, never written


def test_a_worktree_no_session_works_in_is_not_shown(tmp_path):
    root, wt = _room(tmp_path)
    project = JsonUIProject(root, "p")
    project.load_all(0)
    assert project.set_worktrees([str(tmp_path / "elsewhere")], 10) is False
    assert sorted(_rows(project)) == ["p:login.spec.json"]


def test_a_worktree_inside_the_room_is_shown_by_its_branch_and_the_rooms_walk_does_not_enter_it(tmp_path):
    """Ticket 2026-10-26-viz-worktree-inside-the-room-not-on-spec-board: Claude Code's worktrees are
    <repo>/.claude/worktrees/<name>, inside the room. The room's walk (3 folders deep) found the worktree's top config
    and not its apps (4 deep), and the worktrees were skipped as the walk's: neither showed them."""
    root, _wt = _room(tmp_path, app="admin")
    inside = root / ".claude" / "worktrees" / "pr254"
    _git(root, "worktree", "add", "-q", "-b", "claude/pr254", str(inside))
    (inside / "admin" / "docs" / "screens" / "json" / "orders.spec.json").write_text(json.dumps(_spec("Orders")), encoding="utf-8")
    project = JsonUIProject(root, "p")
    project.load_all(0)
    assert sorted(_rows(project)) == ["p:admin/login.spec.json"]          # no source from inside the worktree
    assert project.set_worktrees([str(inside)], 10) is True
    rows = _rows(project)
    assert sorted(rows) == ["p:admin/login.spec.json", "p:admin@claude/pr254/login.spec.json",
                            "p:admin@claude/pr254/orders.spec.json"]
    assert rows["p:admin@claude/pr254/orders.spec.json"]["checkout"]["worktree"].endswith(".claude/worktrees/pr254")
    assert project.set_worktrees([], 20) is True and sorted(_rows(project)) == ["p:admin/login.spec.json"]


def test_a_submodule_is_still_walked_into(tmp_path):
    from jui_cli.viz.sources.jsonui_project import find_configs, is_worktree_root
    sub = tmp_path / "room" / "client"
    sub.mkdir(parents=True)
    (sub / ".git").write_text("gitdir: ../.git/modules/client\n", encoding="utf-8")
    (sub / "jui.config.json").write_text("{}", encoding="utf-8")
    assert not is_worktree_root(sub) and find_configs(tmp_path / "room") == [sub / "jui.config.json"]


def test_a_worktree_left_or_removed_takes_its_rows_with_it(tmp_path):
    root, wt = _room(tmp_path)
    project = JsonUIProject(root, "p")
    project.load_all(0)
    project.set_worktrees([str(wt)], 10)
    assert project.set_worktrees([], 20) is True
    assert sorted(_rows(project)) == ["p:login.spec.json"] and "checkout" not in _rows(project)["p:login.spec.json"]
    project.set_worktrees([str(wt)], 30)
    _git(root, "worktree", "remove", "--force", str(wt))
    assert project.set_worktrees([str(wt)], 40) is True
    assert sorted(_rows(project)) == ["p:login.spec.json"]


def test_an_app_below_the_rooms_root_is_shown_as_app_at_branch(tmp_path):
    root, wt = _room(tmp_path, app="client")
    project = JsonUIProject(root, "p")
    project.load_all(0)
    project.set_worktrees([str(wt / "client")], 10)
    rows = _rows(project)
    assert sorted(rows) == ["p:client/login.spec.json", "p:client@feat/x/login.spec.json", "p:client@feat/x/orders.spec.json"]
    orders = rows["p:client@feat/x/orders.spec.json"]
    assert (orders["specDir"], orders["file"]) == ("client/docs/screens/json", "client/docs/screens/json/orders.spec.json")   # from the worktree's folder
    assert orders["checkout"]["worktree"].endswith("scratch/wt")


def test_the_world_shows_it_while_the_session_lives_and_hears_its_robot_write(tmp_path):
    root, wt = _room(tmp_path)
    state = VizState()
    world = World(state)
    watched = []
    world.on_sources_changed = lambda project: watched.append(project.project_id)
    world.apply_hook({"session_id": "main", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    world.apply_hook({"session_id": "wt", "cwd": str(wt), "hook_event_name": "SessionStart"}, 0)
    world.tick(10)
    world.publish()
    room_id = next(p["id"] for p in state.slices["projects"] if p["name"] == "room/")
    ids = sorted(s["id"] for s in state.slices["specs"] if s["projectId"] == room_id)
    assert ids == [f"{room_id}:@feat/x/login.spec.json", f"{room_id}:@feat/x/orders.spec.json", f"{room_id}:login.spec.json"]
    assert watched == [room_id]   # serve watches the worktree's folders
    path = str(wt / "docs" / "screens" / "json" / "orders.spec.json")
    world.apply_hook({"session_id": "wt", "cwd": str(wt), "hook_event_name": "PreToolUse", "tool_name": "Write",
                      "tool_use_id": "w", "tool_input": {"file_path": path}}, 100)
    world.publish()
    orders = next(s for s in state.slices["specs"] if s["id"] == f"{room_id}:@feat/x/orders.spec.json")
    assert orders["by"] == "wt" and orders["bucket"] == "live"   # the room hears the worktree's robot write
    world.apply_hook({"session_id": "wt", "cwd": str(wt), "hook_event_name": "SessionEnd"}, 200)
    world.tick(300)
    world.publish()
    assert sorted(s["id"] for s in state.slices["specs"] if s["projectId"] == room_id) == [f"{room_id}:login.spec.json"]


def test_a_detached_worktree_is_named_by_its_commit(tmp_path):
    """A worktree on no branch (git worktree add --detach: the gates' and the integration's): its commit's 8 characters."""
    root, _wt = _room(tmp_path)
    det = tmp_path / "scratch" / "det"
    _git(root, "worktree", "add", "-q", "--detach", str(det))
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=det, capture_output=True, text=True, check=True).stdout.strip()
    project = JsonUIProject(root, "p")
    project.load_all(0)
    project.set_worktrees([str(det)], 10)
    rows = _rows(project)
    assert f"p:@{sha[:8]}/login.spec.json" in rows, sorted(rows)
    assert rows[f"p:@{sha[:8]}/login.spec.json"]["checkout"]["branch"] == sha[:8]


def test_a_cwd_through_a_symlink_finds_its_worktree(tmp_path):
    """macOS: a session's cwd under /tmp, the worktree's gitdir under /private/tmp (or the other way): compared real."""
    root, wt = _room(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(wt)
    project = JsonUIProject(root, "p")
    project.load_all(0)
    assert project.set_worktrees([str(link / "docs")], 10) is True
    assert "p:@feat/x/orders.spec.json" in _rows(project)


# A lane whose cwd is the parent and works in a worktree by absolute paths (ticket
# 2026-10-24-jui-viz-worktree-rows-only-from-session-cwd): the worktree a tool's path names counts for
# WORKTREE_TOUCH_MS after the last call that named it, while the session lives; a prunable one never.

def _world_with_parent_session(tmp_path):
    root, wt = _room(tmp_path)
    state = VizState()
    world = World(state)
    world.apply_hook({"session_id": "lane", "cwd": str(root), "hook_event_name": "SessionStart"}, 0)
    world.tick(10)
    world.publish()
    room_id = next(p["id"] for p in state.slices["projects"] if p["name"] == "room/")
    return root, wt, state, world, room_id


def _ids(state, room_id):
    return sorted(s["id"] for s in state.slices["specs"] if s["projectId"] == room_id)


def _call(world, root, at, tool, tool_input, agent=None):
    """A tool call of the session whose cwd is the room (the parent), or of its subagent."""
    payload = {"session_id": "lane", "cwd": str(root), "hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_use_id": f"u{at}", "tool_input": tool_input}
    if agent:
        payload |= {"agent_id": agent, "agent_type": "general-purpose"}
    world.apply_hook(payload, at)


def test_a_worktree_a_parent_session_edits_by_path_is_shown_until_its_time_runs_out(tmp_path):
    root, wt, state, world, room_id = _world_with_parent_session(tmp_path)
    assert _ids(state, room_id) == [f"{room_id}:login.spec.json"]   # the cwd alone: no worktree
    _call(world, root, 1_000, "Edit", {"file_path": str(wt / "docs" / "screens" / "json" / "login.spec.json")})
    world.tick(1_010)
    world.publish()
    assert _ids(state, room_id) == [f"{room_id}:@feat/x/login.spec.json", f"{room_id}:@feat/x/orders.spec.json",
                                    f"{room_id}:login.spec.json"]
    row = next(s for s in state.slices["specs"] if s["id"] == f"{room_id}:@feat/x/login.spec.json")
    assert str(wt) not in json.dumps(row.get("checkout", {}).get("branch")) and row["checkout"]["branch"] == "feat/x"
    world.tick(1_000 + WORKTREE_TOUCH_MS - 1)
    world.publish()
    assert f"{room_id}:@feat/x/orders.spec.json" in _ids(state, room_id)   # still within its time
    world.tick(1_000 + WORKTREE_TOUCH_MS)
    world.publish()
    assert _ids(state, room_id) == [f"{room_id}:login.spec.json"]


def test_a_subagent_s_read_counts_and_the_session_s_end_takes_it(tmp_path):
    root, wt, state, world, room_id = _world_with_parent_session(tmp_path)
    _call(world, root, 1_000, "Grep", {"pattern": "x", "path": str(wt / "docs")}, agent="sub1")
    world.tick(1_010)
    world.publish()
    assert f"{room_id}:@feat/x/orders.spec.json" in _ids(state, room_id)
    world.apply_hook({"session_id": "lane", "cwd": str(root), "hook_event_name": "SessionEnd"}, 2_000)
    world.tick(2_010)
    world.publish()
    assert _ids(state, room_id) == [f"{room_id}:login.spec.json"]


def test_a_relative_path_or_a_bash_command_names_no_worktree(tmp_path, monkeypatch):
    root, wt, state, world, room_id = _world_with_parent_session(tmp_path)
    monkeypatch.chdir(wt.parent)   # read from the server's own folder, the path would be inside the worktree
    _call(world, root, 1_000, "Read", {"file_path": "wt/docs/screens/json/login.spec.json"})
    _call(world, root, 1_001, "Bash", {"command": f"cd {wt} && ls"})
    world.tick(1_010)
    world.publish()
    assert _ids(state, room_id) == [f"{room_id}:login.spec.json"]


def test_a_worktree_gone_prunable_is_not_shown_though_a_path_named_it(tmp_path):
    import shutil
    root, wt, state, world, room_id = _world_with_parent_session(tmp_path)
    _call(world, root, 1_000, "Write", {"file_path": str(wt / "docs" / "screens" / "json" / "login.spec.json")})
    world.tick(1_010)
    world.publish()
    assert f"{room_id}:@feat/x/orders.spec.json" in _ids(state, room_id)
    shutil.rmtree(wt)   # git worktree list now says prunable: its folder is gone, its admin entry stays
    assert (root / ".git" / "worktrees" / "wt").is_dir()
    world.tick(1_010 + WORKTREES_EVERY_MS)
    world.publish()
    assert _ids(state, room_id) == [f"{room_id}:login.spec.json"]


def test_a_jui_tools_call_s_project_dir_names_its_worktree(tmp_path):
    root, wt, state, world, room_id = _world_with_parent_session(tmp_path)
    _call(world, root, 1_000, "mcp__jui-tools__jui_build", {"project_dir": str(wt)})
    world.tick(1_010)
    world.publish()
    assert f"{room_id}:@feat/x/orders.spec.json" in _ids(state, room_id)


def test_a_session_keeps_its_latest_checkouts_and_drops_the_oldest(tmp_path):
    from jui_cli.viz.ingest import TOUCHED_KEPT
    root, _wt, _state, world, _room_id = _world_with_parent_session(tmp_path)
    tops = []
    for i in range(TOUCHED_KEPT + 1):
        top = tmp_path / "many" / f"c{i}"
        (top / ".git").mkdir(parents=True)
        tops.append(str(top))
        _call(world, root, 1_000 + i, "Read", {"file_path": str(top / "a.txt")})
    assert list(world._touched["lane"]) == tops[1:]   # the newest kept, the first dropped
