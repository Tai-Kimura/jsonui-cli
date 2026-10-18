"""Deletions for the shredder (requester, 10-19): which Bash commands delete, what, and how the robot learns it.

Judged per simple command by program and subcommand (robots.deletions), as test runs are: both sides are specimens,
since a rule tightened on one side drops real deletions and one loosened fakes them.
"""
from __future__ import annotations

import pytest

from jui_cli.viz import robots
from jui_cli.viz.ingest import DELETING_KEPT, World
from jui_cli.viz.state import VizState

DELETES = [
    ("rm a.txt", ["a.txt"], False, "rm"),
    ("rm -f a.txt b.txt c.txt", ["a.txt", "b.txt", "c.txt"], False, "rm"),
    ("rm -rf build", ["build"], True, "rm"),
    ("rm -r -- -weird x", ["-weird", "x"], True, "rm"),
    ("command rm -- -weird", ["-weird"], False, "rm"),
    ("cd /work/app && rm *.log", ["*.log"], False, "rm"),              # the glob as written
    ("sudo rm -f /tmp/x", ["/tmp/x"], False, "rm"),
    ("sudo -u web rm cache.db", ["cache.db"], False, "rm"),
    ("\\rm x", ["x"], False, "rm"),
    ("env -u FOO rm y", ["y"], False, "rm"),
    ("rmdir empty", ["empty"], True, "rmdir"),
    ("unlink f", ["f"], False, "unlink"),
    ("trash old/", ["old/"], True, "trash"),
    ("git rm src/a.py", ["src/a.py"], False, "git rm"),
    ("git -C repo rm -r docs", ["docs"], True, "git rm"),
    ("git worktree remove ../wt/x", ["../wt/x"], True, "git worktree remove"),
    ("git -C /r worktree remove --force ../wt/y", ["../wt/y"], True, "git worktree remove"),
    ('find . -name "*.pyc" -delete', ["./*.pyc"], False, "find -delete"),
    ("find build -type f -exec rm {} +", ["build"], False, "find -exec rm"),
    ("find tmp -delete", ["tmp"], True, "find -delete"),
    ("ls; rm a && rm b", ["a", "b"], False, "rm"),
    ("find . -name '*.tmp' | xargs rm", ["（標準入力）"], False, "xargs rm"),       # the targets come on stdin
    ("xargs -0 -n 10 rm -f < list.txt", ["（標準入力）"], False, "xargs rm"),
    ("git ls-files -d | xargs git rm", ["（標準入力）"], False, "xargs git rm"),
    ("find build -print0 | xargs -0 rm -rf", ["（標準入力）"], True, "xargs rm"),
]

NOT_DELETES = [
    "echo rm a.txt",
    "grep -rn 'rm -rf' docs/",
    "git rm -n a.txt",
    "git rm --dry-run a.txt",
    "git rm --cached a.txt",          # only from the index: the file stays
    "git log -- rm.txt",
    "find . -name '*.pyc'",
    "rm",                             # no operand
    "cat > x.sh <<'EOF'\nrm -rf build\nEOF",   # a heredoc body is data
    "python3 -c \"import os; os.remove('x')\"",   # not seen: deletes from inside a script
    "rsync -a --delete src/ dst/",
    "printf 'rm -rf /'",
    "echo 'unbalanced",
    "find . -name '*.py' | xargs grep -l rm",     # xargs runs grep, not rm
    "xargs echo rm < list.txt",
]


@pytest.mark.parametrize("command,targets,folder,how", DELETES)
def test_a_deletion_is_read_with_its_targets(command, targets, folder, how):
    d = robots.deletions(command)
    assert d == {"targets": targets, "folder": folder, "how": how}


@pytest.mark.parametrize("command", NOT_DELETES)
def test_a_command_that_only_mentions_deleting_deletes_nothing(command):
    assert robots.deletions(command) is None


def test_the_label_names_the_last_segment_and_counts_the_rest():
    assert robots.deletion_label(robots.deletions("rm src/a.txt")) == "a.txt"
    assert robots.deletion_label(robots.deletions("rm a b")) == "a、b"
    assert robots.deletion_label(robots.deletions("rm x/a.txt y/b.txt c d e")) == "a.txt、b.txt ほか 3 件"
    assert robots.deletion_label(robots.deletions("rm -rf build/")) == "build"


def test_rm_and_git_say_when_there_was_nothing_to_delete():
    assert robots.deletion_failed("rm: nope.txt: No such file or directory")
    assert robots.deletion_failed("fatal: pathspec 'x' did not match any files")
    assert robots.deletion_failed("fatal: '../wt/x' is not a working tree")
    assert not robots.deletion_failed("") and not robots.deletion_failed("removed 'a.txt'")


# ---------------------------------------------------------------- what the page gets


def _world():
    state = VizState()
    world = World(state)
    world.apply_hook({"session_id": "s", "cwd": "/w/app", "hook_event_name": "SessionStart"}, 0)
    return world, state


def _bash(world, uid, command, at, stderr="", failed=False):
    world.apply_hook({"session_id": "s", "cwd": "/w/app", "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": uid,
                      "tool_input": {"command": command}}, at)
    world.apply_hook({"session_id": "s", "cwd": "/w/app", "hook_event_name": "PostToolUseFailure" if failed else "PostToolUse",
                      "tool_name": "Bash", "tool_use_id": uid, "tool_input": {"command": command},
                      "tool_response": {"stdout": "", "stderr": stderr}}, at + 5)
    world.publish()


def test_a_deletion_that_ran_gives_the_robot_a_shred_and_a_log_line():
    world, state = _world()
    _bash(world, "u1", "rm -rf build a.txt c.txt", 10)
    agent = state.slices["agents"][0]
    assert agent["shred"] == {"at": 15, "ok": True, "label": "build、a.txt ほか 1 件", "count": 3, "folder": True, "how": "rm"}
    assert agent["act"] == "シュレッダー build、a.txt ほか 1 件"
    assert any(e["text"] == "削除 build、a.txt ほか 1 件（rm）" for e in state.events)


@pytest.mark.parametrize("stderr,failed", [("rm: nope.txt: No such file or directory", False), ("", True)])
def test_a_deletion_that_found_nothing_or_failed_is_not_ok(stderr, failed):
    world, state = _world()
    _bash(world, "u1", "rm nope.txt", 10, stderr, failed)
    agent = state.slices["agents"][0]
    assert agent["shred"]["ok"] is False and agent["act"] == "削除できず nope.txt"


def test_other_commands_leave_no_shred_and_an_instruction_is_timed():
    world, state = _world()
    _bash(world, "u1", "echo rm x", 10)
    assert "shred" not in state.slices["agents"][0]
    world.apply_hook({"session_id": "s", "cwd": "/w/app", "hook_event_name": "UserPromptSubmit", "prompt": "next"}, 40)
    world.publish()
    assert state.slices["agents"][0]["promptAt"] == 40   # the page ends an errand an instruction overtakes


def test_deletions_waiting_for_their_end_are_capped():
    world, _ = _world()
    for i in range(DELETING_KEPT + 30):
        world.apply_hook({"session_id": "s", "cwd": "/w/app", "hook_event_name": "PreToolUse", "tool_name": "Bash",
                          "tool_use_id": f"u{i}", "tool_input": {"command": f"rm f{i}"}}, i)
    assert len(world._deleting) == DELETING_KEPT and f"u{DELETING_KEPT + 29}" in world._deleting
