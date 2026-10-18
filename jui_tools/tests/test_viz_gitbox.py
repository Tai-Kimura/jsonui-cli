"""The cardboard box: git push / pull seen in a session's Bash (jui_cli/viz/gitbox.py, World._git_trip; 2.3.4).

Every repository here is made in tmp_path; nothing reads or writes a real one. The names are neutral.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from jui_cli.viz import gitbox as G
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState


# ---------------------------------------------------------------- which commands count

@pytest.mark.parametrize("command, cwd, want", [
    ("git push", "/w/app", {"kind": "push", "dir": "/w/app"}),
    ("git pull --rebase", "/w/app", {"kind": "pull", "dir": "/w/app"}),
    ("git -C /w/other push origin main", "/w/app", {"kind": "push", "dir": "/w/other"}),
    ("git -C sub push", "/w/app", {"kind": "push", "dir": "/w/app/sub"}),
    ("cd sub && git push -u origin feat", "/w/app", {"kind": "push", "dir": "/w/app/sub"}),
    ("cd /w/x; git add -A && git commit -m wip && git push", None, {"kind": "push", "dir": "/w/x"}),
    ("git --no-pager -c core.pager=cat push origin main", "/w/app", {"kind": "push", "dir": "/w/app"}),
    ("env GIT_TRACE=0 timeout 60 git pull", "/w/app", {"kind": "pull", "dir": "/w/app"}),
    ("git pull && git push", "/w/app", {"kind": "push", "dir": "/w/app"}),      # the last one
])
def test_a_push_or_a_pull_is_read_from_the_program_and_its_subcommand(command, cwd, want):
    assert G.git_action(command, cwd) == want


@pytest.mark.parametrize("command", [
    "git push --dry-run", "git push -n origin main", "git pull --dry-run",
    'echo "git push"', "grep -rn 'git pull' docs", "git log --grep push", "git push --help",
    "git fetch && git merge origin/main", "git status", "gitk push", "python3 - <<'EOF'\nimport os\nos.system('x')\ngit push\nEOF",
    "printf 'git pull' | cat", "git 'push", "",
])
def test_text_that_only_mentions_git_is_not_a_push_or_a_pull(command):
    assert G.git_action(command, "/w/app") is None


# ---------------------------------------------------------------- what the output says

PUSH_OK = "To example.invalid:team/app.git\n   1a2b3c4..5d6e7f8  main -> main\n"
PUSH_FORCED = "To example.invalid:team/app.git\n + 1a2b3c4...5d6e7f8 main -> main (forced update)\n"
PUSH_NEW = "To example.invalid:team/app.git\n * [new branch]      feat/box -> feat/box\n"
PUSH_TAG_AND_BRANCH = " * [new tag]         v1.0 -> v1.0\n   1a2b3c4..5d6e7f8  main -> main\n"
PUSH_DELETED = " - [deleted]         old/thing\n"
PUSH_REJECTED = " ! [rejected]        main -> main (fetch first)\nerror: failed to push some refs to 'x'\n"
PUSH_REMOTE_REJECTED = " ! [remote rejected] main -> main (pre-receive hook declined)\n"


@pytest.mark.parametrize("text, status, branch", [
    (PUSH_OK, "pushed", "main"), (PUSH_FORCED, "forced", "main"), (PUSH_NEW, "new", "feat/box"),
    (PUSH_TAG_AND_BRANCH, "pushed", "main"), (PUSH_DELETED, "deleted", "old/thing"),
    (PUSH_REJECTED, "rejected", "main"), (PUSH_REMOTE_REJECTED, "rejected", "main"),
    ("Everything up-to-date\n", "uptodate", None), ("", "unknown", None),
])
def test_what_a_push_said(text, status, branch):
    got = G.parse_push(text)
    assert (got["status"], got["branch"]) == (status, branch)


def test_a_push_keeps_the_range_and_never_the_remote_url():
    got = G.parse_push("To https://user:secret-token@example.invalid/app.git\n" + PUSH_OK)
    assert (got["old"], got["new"]) == ("1a2b3c4", "5d6e7f8")
    assert "secret-token" not in repr(got) and "example.invalid" not in repr(got)


PULL_FF = ("From example.invalid:team/app\n * branch            main       -> FETCH_HEAD\nUpdating 1a2b3c4..5d6e7f8\n"
           "Fast-forward\n src/a.txt | 12 +++++++++---\n 2 files changed, 9 insertions(+), 3 deletions(-)\n")


@pytest.mark.parametrize("text, status, branch, stats", [
    (PULL_FF, "pulled", "main", (2, 9, 3)),
    ("Already up to date.\n", "uptodate", None, (None, None, None)),
    ("Already up-to-date.\n", "uptodate", None, (None, None, None)),
    ("Auto-merging a.txt\nCONFLICT (content): Merge conflict in a.txt\nAutomatic merge failed; fix conflicts\n", "conflict", None, (None, None, None)),
    ("fatal: not a git repository\n", "failed", None, (None, None, None)),
    ("Successfully rebased and updated refs/heads/feat.\n", "rebased", "feat", (None, None, None)),
    (" 1 file changed, 1 insertion(+)\n", "pulled", None, (1, 1, 0)),
])
def test_what_a_pull_said(text, status, branch, stats):
    got = G.parse_pull(text)
    assert (got["status"], got["branch"], (got["files"], got["ins"], got["dels"])) == (status, branch, stats)


# ---------------------------------------------------------------- the amount, read from a repository (tmp_path only)

def _git(repo, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "a.txt").write_text("one\n")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-q", "-m", "first")
    first = _git(r, "rev-parse", "HEAD")
    (r / "a.txt").write_text("one\ntwo\nthree\n")
    (r / "b.txt").write_text("x\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "second")
    (r / "a.txt").write_text("two\nthree\n")
    _git(r, "commit", "-q", "-am", "third")
    return r, first, _git(r, "rev-parse", "HEAD")


def test_the_range_is_counted_read_only(repo):
    r, first, last = repo
    index = r / ".git" / "index"
    before = (index.stat().st_mtime_ns, sorted(p.name for p in (r / ".git").iterdir()))
    got = G.count_range(str(r), first[:7], last[:7])
    assert got == {"commits": 2, "files": 2, "ins": 3, "dels": 1}   # a.txt: one -> two, three; b.txt: x
    assert (index.stat().st_mtime_ns, sorted(p.name for p in (r / ".git").iterdir())) == before   # nothing written


def test_a_new_branch_is_counted_from_origins_default_branch(repo):
    r, first, last = repo
    _git(r, "update-ref", "refs/remotes/origin/main", first)
    _git(r, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    assert G.count_range(str(r), None, "main")["commits"] == 2


def test_no_repository_no_amount_and_no_error(tmp_path, repo):
    r, first, last = repo
    assert G.count_range(str(tmp_path / "nowhere"), first, last) is None
    assert G.count_range(str(tmp_path), first, last) is None                 # not a repository
    assert G.count_range(str(r), None, "main") is None                         # a new branch without origin/HEAD
    assert G.count_range(str(r), "0000000", last) is None                     # an unknown commit


# ---------------------------------------------------------------- the world

def _hook(kind, sid="s1", **fields):
    return {"hook_event_name": kind, "session_id": sid, "cwd": "/w/app", **fields}


def _bash(world, command, out, err="", use="b1", at=1):
    world.apply_hook(_hook("PreToolUse", tool_name="Bash", tool_use_id=use, tool_input={"command": command}), at)
    world.apply_hook(_hook("PostToolUse", tool_name="Bash", tool_use_id=use, tool_input={"command": command},
                           tool_response={"stdout": out, "stderr": err}), at + 1)


def test_a_push_becomes_a_trip_and_its_amount_follows():
    world = World(VizState())
    _bash(world, "git push", "", PUSH_OK)
    trip = world.agents["s1"]["git"]
    assert (trip["kind"], trip["status"], trip["branch"], trip["pending"]) == ("push", "pushed", "main", True)
    jobs = world.take_git_jobs()
    assert jobs == [("s1", "b1", {"folder": "/w/app", "old": "1a2b3c4", "new": "5d6e7f8"})] and world.take_git_jobs() == []
    world.git_counted("s1", "b1", {"commits": 3, "files": 2, "ins": 120, "dels": 8}, 5)
    trip = world.agents["s1"]["git"]
    assert trip["counted"]["ins"] == 120 and trip["pending"] is False
    assert any(e.get("kind") == "GitPush" and e["text"] == "↑ push main 3 コミット +120 −8" for e in world.state.events)


def test_a_pull_reads_its_own_numbers_and_up_to_date_is_a_trip_with_nothing():
    world = World(VizState())
    _bash(world, "git pull", PULL_FF)
    trip = world.agents["s1"]["git"]
    assert trip["counted"] == {"commits": None, "files": 2, "ins": 9, "dels": 3}
    _bash(world, "git pull", "Already up to date.\n", use="b2", at=10)
    trip = world.agents["s1"]["git"]
    assert (trip["status"], trip["pending"], G.label(trip)) == ("uptodate", False, "↓ pull — 変更なし")


def test_an_instruction_stops_the_trip_and_other_commands_make_none():
    world = World(VizState())
    _bash(world, "echo 'git push'", "git push\n")
    assert "git" not in world.agents["s1"]
    _bash(world, "git push", "", PUSH_REJECTED, use="b2", at=5)
    assert world.agents["s1"]["git"]["status"] == "rejected" and world.take_git_jobs() == []   # nothing to count
    world.apply_hook(_hook("UserPromptSubmit", prompt="next"), 9)
    trip = world.agents["s1"]["git"]
    assert trip["stopped"] is True and trip["id"] == "b2" and trip["label"].startswith("↑ push")   # kept for the card


def test_a_count_after_an_instruction_keeps_the_trip_stopped():
    world = World(VizState())
    _bash(world, "git push", "", PUSH_OK)
    world.apply_hook(_hook("UserPromptSubmit", prompt="next"), 3)
    world.git_counted("s1", "b1", {"commits": 1, "files": 1, "ins": 2, "dels": 0}, 5)
    trip = world.agents["s1"]["git"]
    assert trip["stopped"] is True and trip["counted"]["ins"] == 2


def test_the_counted_trip_is_published_again():
    """The page sees the amount: the agents slice must change (a trip changed in place compared equal and was never
    sent — the snapshot shares the object, so only the slice's revision tells)."""
    world = World(VizState())
    _bash(world, "git push", "", PUSH_OK)
    world.publish()
    rev, sent = world.state.rev, world.state.slices["agents"][0]["git"]
    world.git_counted("s1", "b1", {"commits": 1, "files": 1, "ins": 2, "dels": 0}, 5)
    world.publish()
    assert world.state.rev > rev and sent["pending"] is True                     # the sent slice was not changed
    assert world.state.slices["agents"][0]["git"]["counted"]["ins"] == 2


def test_a_late_count_for_a_replaced_trip_is_dropped():
    world = World(VizState())
    _bash(world, "git push", "", PUSH_OK)
    _bash(world, "git push", "", PUSH_FORCED, use="b2", at=5)
    world.git_counted("s1", "b1", {"commits": 9, "files": 9, "ins": 9, "dels": 9}, 6)
    assert "counted" not in world.agents["s1"]["git"] and world.agents["s1"]["git"]["id"] == "b2"


# ---------------------------------------------------------------- the real server counts the range off the event loop

def test_the_server_counts_a_push_and_publishes_its_amount(tmp_path, repo):
    import json
    import socket
    import sys
    import time
    import urllib.request
    from pathlib import Path

    r, first, last = repo
    jt = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if k not in ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")}
    env["HOME"] = str(home)
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port), "--no-agents-poll"],
                           env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        server_json = home / ".local" / "state" / "jui-viz" / "server.json"
        for _ in range(150):
            if server_json.exists():
                break
            time.sleep(0.1)
        token = json.loads(server_json.read_text())["token"]
        fwd = jt / "jui_cli" / "viz" / "forward.py"
        base = {"session_id": "11111111-2222-4333-8444-555555555555", "cwd": str(r)}
        for p in ({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "u1", "tool_input": {"command": "git push"}},
                  {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_use_id": "u1", "tool_input": {"command": "git push"},
                   "tool_response": {"stdout": "", "stderr": f"   {first[:7]}..{last[:7]}  main -> main\n"}}):
            subprocess.run([sys.executable, "-I", "-S", str(fwd)], input=json.dumps({**base, **p}).encode(), env=env, timeout=10, check=True)
        trip = None
        for _ in range(100):
            snap = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/snapshot",
                                                                            headers={"X-Jui-Viz-Token": token}), timeout=2).read())
            agents = snap["slices"].get("agents") or []
            trip = next((a.get("git") for a in agents if a.get("git")), None)
            if trip and not trip.get("pending"):
                break
            time.sleep(0.1)
        assert trip and trip["pending"] is False and trip["counted"] == {"commits": 2, "files": 2, "ins": 3, "dels": 1}, trip
        assert trip["label"] == "↑ push main 2 コミット +3 −1"
    finally:
        srv.terminate()
        out, _ = srv.communicate(timeout=10)
    assert "Traceback" not in out, out
