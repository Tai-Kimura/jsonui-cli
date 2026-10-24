"""A worktree's spec beside the spec it started from (2.3.23, ticket 2026-10-24-viz-worktree-spec-diff-against-base).

The base is where the worktree's branch left the room's checkout (merge-base); both sides are the sheet's doc
(sheet.build_doc), the left's prose and Layout read at the base commit; rows pair per section by their key. git runs
only here, read-only, and a base that cannot be read says why (the family table in the ticket): no parent HEAD, no
merge-base, git missing, git too slow, a new spec, a deleted one.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import threading
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import spec_diff as sd
from jui_cli.viz.config import VizConfig
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.sources.jsonui_project import JsonUIProject, SpecEntry
from jui_cli.viz.state import VizState


def _spec(name: str, description: str = "d", **extra) -> dict:
    return {"type": "screen_spec", "metadata": {"name": name, "displayName": name, "description": description,
                                                "platforms": ["ios"], **extra.pop("meta", {})}, **extra}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(cwd), "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}).stdout


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _room(tmp_path: Path) -> tuple[Path, Path]:
    """room/ on main: login (two variables, a Layout of two nodes, its description in a texts file) and gone; a
    worktree on feat/x outside the room: login with a variable added, one removed, one retyped and a node renamed,
    gone deleted, orders new (uncommitted). main moves on after the branch (the base stays where it left)."""
    root = tmp_path / "room"
    specs, layouts = root / "docs" / "screens" / "json", root / "docs" / "screens" / "layouts"
    _write(root / "jui.config.json", "{}")
    login = _spec("Login", {"md": "login.description"}, meta={"layoutFile": "login"},
                  stateManagement={"uiVariables": [{"name": "email", "type": "String"}, {"name": "busy", "type": "Bool"}]})
    _write(specs / "login.spec.json", login)
    _write(specs / "login.texts.yaml", "login:\n  description: the base's words\n")
    _write(specs / "gone.spec.json", _spec("Gone"))
    _write(layouts / "login.json", {"type": "View", "id": "root", "child": [{"type": "Label", "id": "title"}]})
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    wt = tmp_path / "scratch" / "wt"
    _git(root, "worktree", "add", "-q", "-b", "feat/x", str(wt))
    wspecs, wlayouts = wt / "docs" / "screens" / "json", wt / "docs" / "screens" / "layouts"
    login["stateManagement"]["uiVariables"] = [{"name": "email", "type": "Int"}, {"name": "password", "type": "String"}]
    _write(wspecs / "login.spec.json", login)
    _write(wspecs / "login.texts.yaml", "login:\n  description: the worktree's words\n")
    _write(wlayouts / "login.json", {"type": "View", "id": "root", "child": [{"type": "Label", "id": "heading"}]})
    (wspecs / "gone.spec.json").unlink()
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "wt")
    _write(wspecs / "orders.spec.json", _spec("Orders"))
    _write(specs / "later.spec.json", _spec("Later"))   # main after the branch: not in the base
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "later")
    return root, wt


def _project(root: Path, wt: Path) -> JsonUIProject:
    project = JsonUIProject(root, "p")
    project.load_all(0)
    assert project.set_worktrees([str(wt / "docs")], 10) is True
    return project


def _sid(project: JsonUIProject, name: str, app: str = "@feat/x") -> str:
    return next(sid for sid, e in project.specs.items() if e.source.key == app and e.path.name == name)


def _section(diff: dict, key: str) -> list:
    return next(s["rows"] for s in diff["sections"] if s["key"] == key)


def _tree_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(folder)).encode() + p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------- pairing

def test_rows_pair_by_their_key_in_both_sides_order():
    left = [["email", "String", ""], ["busy", "Bool", ""], ["age", "Int", ""]]
    right = [["email", "Int", ""], ["age", "Int", ""], ["password", "String", ""]]
    got = sd.diff_section(left, right, "uiVariables")
    assert [(r["s"], (r["l"] or r["r"])[0]) for r in got["rows"]] == [
        ("chg", "email"), ("del", "busy"), ("same", "age"), ("add", "password")]
    assert got["rows"][0]["cols"] == [1]
    assert got["counts"] == {"add": 1, "del": 1, "chg": 1}


def test_a_key_met_twice_pairs_by_order_and_a_keyless_row_by_its_content():
    left = [["tap", "a", "x"], ["tap", "b", "y"]]
    right = [["tap", "a", "x"], ["tap", "b", "z"], ["tap", "c", "w"]]
    got = sd.diff_section(left, right, "userActions")
    assert [r["s"] for r in got["rows"]] == ["same", "chg", "add"]
    comps = sd.diff_section([["Label", "", "Label", 1]], [["Label", "", "Label", 2]], "components")
    assert [r["s"] for r in comps["rows"]] == ["del", "add"]   # no id: compared whole, so a moved one is two rows


def test_no_difference_and_one_side_missing():
    doc = {"metadata": {"name": "A", "displayName": "A"}, "uiVariables": [["v", "Int", ""]]}
    assert sd.diff_docs(doc, doc)["counts"] == {"add": 0, "del": 0, "chg": 0}
    assert sd.diff_docs(None, doc)["counts"] == {"add": 3, "del": 0, "chg": 0}   # name, displayName, v
    assert sd.diff_docs(doc, None)["counts"] == {"add": 0, "del": 3, "chg": 0}


# ---------------------------------------------------------------- the base, read at the merge-base

def test_a_worktree_spec_against_where_its_branch_left(tmp_path):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    before = _tree_hash(root / ".git")
    got = sd.spec_diff(project, _sid(project, "login.spec.json"))
    assert got["ok"] and not got["isNew"] and got["file"] == "docs/screens/json/login.spec.json"
    assert got["base"] == _git(root, "rev-parse", "main~1").strip()   # where feat/x left, not main now
    variables = [(r["s"], (r["l"] or r["r"])[0]) for r in _section(got, "uiVariables")]
    assert variables == [("chg", "email"), ("del", "busy"), ("add", "password")]
    # the Layout and the texts file are read at the base too
    comps = [(r["s"], (r["l"] or r["r"])[1]) for r in _section(got, "components")]
    assert comps == [("same", "root"), ("del", "title"), ("add", "heading")]
    desc = next(r for r in _section(got, "metadata") if (r["l"] or r["r"])[0] == "description")
    assert desc["s"] == "chg" and "the base's words" in json.dumps(desc["l"]) and "the worktree's words" in json.dumps(desc["r"])
    assert _tree_hash(root / ".git") == before   # read-only (GIT_OPTIONAL_LOCKS=0)


def test_a_new_spec_has_everything_added(tmp_path):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    got = sd.spec_diff(project, _sid(project, "orders.spec.json"))
    assert got["ok"] and got["isNew"] and got["counts"]["del"] == 0 and got["counts"]["add"] > 0


def test_the_whole_list_marks_each_spec_and_names_the_deleted(tmp_path):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    got = sd.list_diff(project, "@feat/x")
    assert got["ok"]
    assert got["marks"][_sid(project, "login.spec.json")] == {"add": 2, "del": 2, "chg": 2, "isNew": False}
    assert got["marks"][_sid(project, "orders.spec.json")]["isNew"] is True
    assert got["deleted"] == [{"file": "docs/screens/json/gone.spec.json", "name": "Gone"}]
    gone = sd.spec_diff(project, app="@feat/x", deleted="docs/screens/json/gone.spec.json")
    assert gone["ok"] and gone["isDeleted"] and gone["counts"]["add"] == 0 and gone["counts"]["del"] > 0


def test_the_rooms_own_spec_has_no_base(tmp_path):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    got = sd.spec_diff(project, _sid(project, "login.spec.json", app=""))
    assert got == {"ok": False, "reason": "not-a-worktree", "detail": ""}


# ---------------------------------------------------------------- a base that cannot be read says why

def test_no_parent_head(tmp_path):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    (root / ".git" / "HEAD").write_text("garbage\n")
    got = sd.spec_diff(project, _sid(project, "login.spec.json"))
    assert got["ok"] is False and got["reason"] == "no-parent-head"


def test_no_merge_base(tmp_path):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    _git(root, "checkout", "-q", "--orphan", "other")
    _git(root, "commit", "-q", "--allow-empty", "-m", "unrelated")
    got = sd.spec_diff(project, _sid(project, "login.spec.json"))
    assert got["ok"] is False and got["reason"] == "no-merge-base"


def test_git_missing(tmp_path, monkeypatch):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    got = sd.spec_diff(project, _sid(project, "login.spec.json"))
    assert got["ok"] is False and got["reason"] == "git-missing"


def test_git_too_slow(tmp_path, monkeypatch):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    slow = tmp_path / "slowbin"
    slow.mkdir()
    (slow / "git").write_text("#!/bin/sh\nsleep 5\n")
    (slow / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{slow}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(sd, "GIT_TIMEOUT_SEC", 0.5)
    got = sd.spec_diff(project, _sid(project, "login.spec.json"))
    assert got["ok"] is False and got["reason"] == "timeout"


def test_what_a_base_commit_holds_is_cached_by_its_sha(tmp_path, monkeypatch):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    sd._BASE_CACHE.clear()
    calls = []
    real = sd._git
    monkeypatch.setattr(sd, "_git", lambda folder, *args: (calls.append(args[0]), real(folder, *args))[1])
    sd.spec_diff(project, _sid(project, "login.spec.json"))
    shows = calls.count("show")
    calls.clear()
    sd.spec_diff(project, _sid(project, "login.spec.json"))
    assert shows >= 2 and calls == ["merge-base"]   # the base commit asked again; its files not read again


def test_git_runs_only_when_a_diff_is_asked_for(tmp_path, monkeypatch):
    # the one exception to "git is read, never run" (sources/jsonui_project.py): reading the room, showing its
    # worktree, its rows and its sheet run no git; the diff does
    from jui_cli.viz.sheet import sheet_for
    root, wt = _room(tmp_path)
    ran = []
    real = subprocess.run

    def spy(args, *a, **kw):
        if args and str(args[0]).endswith("git"):
            ran.append(list(args))
        return real(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", spy)
    project = _project(root, wt)
    project.summaries(0)
    sid = _sid(project, "login.spec.json")
    assert sheet_for(project, sid) is not None
    assert ran == []
    assert sd.spec_diff(project, sid)["ok"]
    assert ran and all(a[3] in ("merge-base", "show") for a in ran)   # git -C <folder> <command>


# ---------------------------------------------------------------- what the executor walks is a copy (ticket
# 2026-10-24-viz-executor-iterates-dicts-the-loop-changes): since 2.3.23 the loop adds and drops a room's specs while
# the list's git runs in the executor; a dict walked in Python while it changes size raises RuntimeError. The fake
# changes it from inside the walk (the same thread, so the moment is certain).

class _Rooms:
    def __init__(self, **rooms):
        self.jsonui = rooms


def _changing_entry(specs: dict) -> SpecEntry:
    """An entry whose ``source``, read while the list is walked, adds a spec to ``specs`` (the loop applying a read)."""
    class Changing(SpecEntry):
        @property
        def source(self):
            specs.setdefault("p:@feat/x/new.spec.json", SpecEntry(path=Path("/nowhere/new.spec.json")))
            return None

        @source.setter
        def source(self, value):
            pass
    return Changing(path=Path("/nowhere/a.spec.json"))


def test_the_list_walks_a_copy_of_the_specs_taken_on_the_loop(tmp_path):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    project.specs["p:@feat/x/a.spec.json"] = _changing_entry(project.specs)
    with pytest.raises(RuntimeError, match="changed size during iteration"):
        sd.list_diff(project, "@feat/x")             # the old way: the dict itself, walked where the git runs
    project.specs.pop("p:@feat/x/new.spec.json")
    job = sd.job_for(_Rooms(p=project), {"type": "spec.diffList", "project": "p", "app": "@feat/x"})
    got = job()
    assert got["ok"] and any(k.endswith("login.spec.json") for k in got["marks"])
    assert "p:@feat/x/new.spec.json" in project.specs   # it did change while the copy was walked


def test_job_for_runs_no_git_and_its_call_does(tmp_path, monkeypatch):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    sd._BASE_CACHE.clear()
    calls = []
    real = sd._git
    monkeypatch.setattr(sd, "_git", lambda *a, **k: (calls.append(a[1:2]), real(*a, **k))[1])
    rooms = _Rooms(p=project)
    sid = next(s for s, e in project.specs.items() if e.source.key == "@feat/x" and e.path.name == "login.spec.json")
    jobs = [sd.job_for(rooms, m) for m in ({"type": "spec.diffList", "project": "p", "app": "@feat/x"},
                                           {"type": "spec.diff", "specId": sid},
                                           {"type": "spec.diff", "project": "p", "app": "@feat/x", "deleted": "docs/screens/json/gone.spec.json"},
                                           {"type": "spec.diff", "specId": "p:nope"})]
    assert calls == []
    got = [job() for job in jobs]
    assert calls and [g["ok"] for g in got] == [True, True, True, False] and got[3]["reason"] == "unknown-spec"


def test_the_server_copies_on_the_loop_and_runs_the_git_off_it(tmp_path):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    where = {}

    def handler(message):
        where["copied"] = threading.current_thread() is threading.main_thread()
        job = sd.job_for(_Rooms(p=project), message)

        def run():
            where["git"] = threading.current_thread() is threading.main_thread()
            return job()
        return run

    async def main():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        ctx = ServerContext(config=VizConfig(), port=port, token="t" * 43, state=VizState(), spec_diff=handler)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        try:
            ws = await client.ws_connect("/ws", headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"})
            await ws.receive_json()
            await ws.send_json({"type": "auth", "token": "t" * 43})
            await ws.receive_json()
            await ws.receive_json()
            await ws.send_json({"type": "spec.diffList", "reqId": 1, "project": "p", "app": "@feat/x"})
            while True:
                reply = await ws.receive_json(timeout=30)
                if reply.get("type") == "specDiff":
                    break
            assert reply["reqId"] == 1 and reply["diff"]["ok"]
            await ws.close()
        finally:
            await client.close()

    asyncio.run(main())
    assert where == {"copied": True, "git": False}


class _RoomAdded(dict):
    """world.jsonui after job_for returned: the loop adds a room (_install) at any moment, so a walk of it off the loop
    may meet the change; here every read of it is that moment."""

    def _met(self, *a, **k):
        raise RuntimeError("dictionary changed size during iteration")
    values = items = keys = get = __iter__ = __getitem__ = __contains__ = __len__ = _met


def test_each_diff_decides_its_room_on_the_loop_and_its_call_reads_no_room(tmp_path):
    root, wt = _room(tmp_path)
    project = _project(root, wt)
    rooms = _Rooms(p=project)
    sid = next(s for s, e in project.specs.items() if e.source.key == "@feat/x" and e.path.name == "login.spec.json")
    messages = [{"type": "spec.diff", "specId": sid},
                {"type": "spec.diffList", "project": "p", "app": "@feat/x"},
                {"type": "spec.diff", "project": "p", "app": "@feat/x", "deleted": "docs/screens/json/gone.spec.json"},
                {"type": "spec.diff", "specId": "p:nope"}]
    jobs = [sd.job_for(rooms, m) for m in messages]
    rooms.jsonui = _RoomAdded(rooms.jsonui)
    got = [job() for job in jobs]
    assert [g["ok"] for g in got] == [True, True, True, False]
