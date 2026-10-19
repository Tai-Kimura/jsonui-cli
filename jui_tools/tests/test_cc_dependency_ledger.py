"""The ledger of what we rely on in Claude Code, and its daily watcher (ticket 2026-10-19-claude-dependency-watch).

The gate: every scanned file a mark finds is listed in tools/cc_watch/ledger.json, every entry names a probe that
exists, and every listed repository file still exists and still matches. Each rule has an arm that turns it red; the
mark list has an arm per mark showing a narrowed list leaks a known hit.

The watcher, with a fake CLI, fake fetches and a fake notify: a changed shape files a ticket and notifies, a green
day does nothing but log, the same version never fetches the CHANGELOG, and no temporary folder is left behind.
"""
from __future__ import annotations

import copy
import json
import plistlib
import re
import sys
import tempfile
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from cc_watch import ledger as L  # noqa: E402
from cc_watch import marks as M  # noqa: E402
from cc_watch import probes as P  # noqa: E402
from cc_watch import watch as W  # noqa: E402

ROOT = M.repo_root()


# ------------------------------------------------------------------ the gate
def test_the_tree_is_green():
    assert L.check(ROOT) == []


def test_every_entry_names_a_probe_that_exists():
    assert {e["probe"] for e in L.load()["entries"]} <= set(P.PROBES)


def test_a_file_removed_from_the_ledger_while_it_still_matches_is_red():
    led = L.load()
    victim = "jui_tools/jui_cli/viz/clockout.py"
    for e in led["entries"]:
        e["files"] = [f for f in e["files"] if f != victim]
    problems = L.check(ROOT, ledger=led)
    assert any(victim in p for p in problems), problems


def test_a_new_marked_file_that_is_not_listed_is_red(tmp_path):
    (tmp_path / "tool").mkdir()
    (tmp_path / "tool" / "new_feature.py").write_text("HOOKS = HOME / '.claude/settings.json'\n")
    problems = L.check(tmp_path, ledger={"entries": []}, files=["tool/new_feature.py"])
    assert any("tool/new_feature.py" in p for p in problems), problems


def test_a_probe_name_that_does_not_exist_is_red():
    led = copy.deepcopy(L.load())
    led["entries"][0]["probe"] = "no_such_probe"
    problems = L.check(ROOT, ledger=led)
    assert any("no_such_probe" in p for p in problems), problems


def test_a_listed_file_that_no_longer_matches_is_red():
    led = copy.deepcopy(L.load())
    led["entries"][0]["files"].append("jui_tools/jui_cli/__init__.py")
    problems = L.check(ROOT, ledger=led)
    assert any("jui_tools/jui_cli/__init__.py" in p for p in problems), problems


@pytest.mark.parametrize("mark", sorted(M.SPECIMENS))
def test_a_narrowed_mark_list_leaks_its_specimen(tmp_path, mark):
    rel, text = M.SPECIMENS[mark]
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_text(text)
    full = M.scan(tmp_path, files=[rel])
    assert [h[0] for h in full.get(rel, [])] == [mark]
    marks = {k: v for k, v in M.COMPILED.items() if k != mark}
    paths = {k: v for k, v in M.COMPILED_PATHS.items() if k != mark}
    assert rel not in M.scan(tmp_path, marks=marks, path_marks=paths, files=[rel])
    # and through the gate: listed with every mark is green, unlisted is red, narrowed is (wrongly) green
    assert L.check(tmp_path, ledger={"entries": []}, files=[rel])
    assert not L.check(tmp_path, ledger={"entries": []}, files=[rel], marks=marks) or mark in M.PATH_MARKS


def test_every_mark_has_a_specimen():
    assert set(M.SPECIMENS) == set(M.MARKS) | set(M.PATH_MARKS)


# ------------------------------------------------------------------ the watcher
HELP = """Usage: claude [options]
Options:
  -n, --name <name>  -p, --print  -r, --resume  --settings <f>  --setting-sources <s>  --plugin-dir <d>
  --mcp-config <c>  --session-id <id>  --channels <c>  --dangerously-load-development-channels <c>
"""
PLUGIN_HELP = "Commands:\n  marketplace  x\n  install  x\n  update  x\n  list  x\n  enable  x\n  disable  x\n"
MCP_HELP = "Commands:\n  add  x\n  get  x\n  list  x\n  remove  x\n"


def fake_cli(version="2.1.303", help_text=HELP):
    calls = []

    def run(argv):
        calls.append(argv)
        if argv == ["--version"]:
            return 0, f"{version} (Claude Code)\n"
        if argv == ["--help"]:
            return 0, help_text
        if argv == ["plugin", "--help"]:
            return 0, PLUGIN_HELP
        if argv == ["mcp", "--help"]:
            return 0, MCP_HELP
        return 1, "unknown"
    run.calls = calls
    return run


def fake_fetch(latest, changelog="## 2.1.304\n- Hooks: SessionEnd gets a new field\n- Faster startup\n"):
    fetched = []

    def fetch(url):
        fetched.append(url)
        if url == W.REGISTRY:
            return json.dumps({"version": latest})
        if url == W.CHANGELOG:
            return changelog
        raise AssertionError(url)
    fetch.fetched = fetched
    return fetch


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo, state, temp = tmp_path / "repo", tmp_path / "state", tmp_path / "temp"
    repo.mkdir(); temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    notified = []
    return repo, state, temp, notified


def go(world, cli, fetch):
    repo, state, _temp, notified = world
    return W.run(repo, state, live=False, runner=cli, fetch=fetch, notify=lambda t: notified.append(t) or ["fake"])


def tickets(repo):
    return sorted((repo / "docs" / "bugs").glob("*.md")) if (repo / "docs" / "bugs").exists() else []


def test_a_green_day_writes_nothing_but_the_log(world):
    repo, state, temp, notified = world
    go(world, fake_cli(), fake_fetch("2.1.303"))           # first run: the baseline
    r = go(world, fake_cli(), fake_fetch("2.1.303"))
    assert r["changed"] == [] and not r["baseline"]
    assert tickets(repo) == [] and notified == []
    assert len((state / "watch.log").read_text().splitlines()) == 2
    assert list(temp.iterdir()) == []                        # every temporary folder removed


def test_the_same_version_never_fetches_the_changelog(world):
    fetch = fake_fetch("2.1.303")
    go(world, fake_cli("2.1.303"), fetch)
    assert fetch.fetched == [W.REGISTRY]


def test_a_new_version_fetches_the_changelog_and_keeps_the_ledger_lines(world):
    fetch = fake_fetch("2.1.304")
    r = go(world, fake_cli("2.1.303"), fetch)
    assert fetch.fetched == [W.REGISTRY, W.CHANGELOG]
    assert r["changelog_lines"] == 1                         # the hooks line, not "Faster startup"


def test_a_changed_shape_files_a_ticket_and_notifies(world):
    repo, state, temp, notified = world
    go(world, fake_cli(), fake_fetch("2.1.304"))
    renamed = HELP.replace("-n, --name <name>", "--title <name>")
    r = go(world, fake_cli(help_text=renamed), fake_fetch("2.1.304"))
    assert r["changed"] == ["cli_flags"]
    [ticket] = tickets(repo)
    assert notified == [ticket]
    text = ticket.read_text()
    assert "cli_flags" in text and "起動の引数" in text and "jui_tools/jui_cli/viz/sources/launch.py" in text
    assert '"--name": true' in text and '"--name": false' in text
    assert "SessionEnd gets a new field" in text
    assert (state / "shapes.json").exists() and list(state.glob("shapes-*-before.json"))
    # the change is filed once: the next day with the same shape is green
    go(world, fake_cli(help_text=renamed), fake_fetch("2.1.304"))
    assert len(tickets(repo)) == 1 and len(notified) == 1
    assert list(temp.iterdir()) == []


def test_a_probe_that_raises_is_red(world, monkeypatch):
    repo, _state, _temp, notified = world
    go(world, fake_cli(), fake_fetch("2.1.303"))
    def boom(ctx):
        raise RuntimeError("help text gone")
    monkeypatch.setitem(P.PROBES, "mcp_cli", boom)
    r = go(world, fake_cli(), fake_fetch("2.1.303"))
    assert r["changed"] == ["mcp_cli"] and len(notified) == 1


def test_the_session_folder_is_removed_even_when_the_session_fails(world):
    repo, state, temp, notified = world
    def failing(cli, work):
        (work / "config").mkdir()
        raise RuntimeError("no login")
    with pytest.raises(RuntimeError):
        W.run(repo, state, live=True, runner=fake_cli(), fetch=fake_fetch("2.1.303"), notify=lambda t: [],
              session_maker=failing)
    assert list(temp.iterdir()) == []


def test_session_probes_read_a_recorded_session(tmp_path):
    cfg = tmp_path / "cfg"
    (cfg / "projects" / "p").mkdir(parents=True)
    (cfg / "sessions").mkdir(); (cfg / "plugins").mkdir(); (cfg / "settings.json").write_text("{}")
    rec = {"type": "assistant", "timestamp": "t", "sessionId": "s", "cwd": "/", "uuid": "u",
           "message": {"id": "m", "model": "x", "usage": {}, "content": [{"type": "text", "text": "ok"}]}}
    (cfg / "projects" / "p" / "s.jsonl").write_text(json.dumps(rec) + "\n")
    s = P.Session(config_dir=cfg, hook_inputs=[{"hook_event_name": "SessionEnd", "session_id": "s", "reason": "other",
                                                "transcript_path": "x", "cwd": "/", "permission_mode": "default"}],
                  hook_env={"CLAUDE_PROJECT_DIR": "/"}, statusline={"session_id": "s"}, sigterm_exit=143,
                  sigterm_session_end=True)
    ctx = P.Context(run=fake_cli(), session=s)
    assert P.config_paths(ctx) == {p: True for p in P.CONFIG_PATHS}
    assert P.transcript_shape(ctx)["keys"]["assistant"] == {k: True for k in P.TRANSCRIPT_KEYS["assistant"]}
    assert P.hook_input_shape(ctx)["SessionEnd"] == {"reason": True}
    assert P.env_vars(ctx)["CLAUDE_PROJECT_DIR"] is True
    assert P.sigterm_session_end(ctx) == {"exited": True, "session_end": True}
    assert P.transcript_shape(P.Context(run=fake_cli()))["skipped"]


def test_the_launch_agent_runs_the_watch_daily_and_the_session_is_opt_in(tmp_path):
    plain = plistlib.loads(W.plist(tmp_path / "repo", tmp_path / "state"))
    assert plain["Label"] == W.LABEL and "Hour" in plain["StartCalendarInterval"]
    assert plain["ProgramArguments"][2:4] == ["run", "--repo"] and "--live" not in plain["ProgramArguments"]
    assert "--live" in plistlib.loads(W.plist(tmp_path / "repo", tmp_path / "state", live=True))["ProgramArguments"]


def test_changelog_lines_keep_only_the_range_and_the_ledger_words():
    text = "## 2.1.305\n- New hook event\n## 2.1.304\n- statusLine gets cost\n- UI polish\n## 2.1.303\n- hooks old\n"
    assert W.changelog_lines(text, "2.1.303", "2.1.304") == ["2.1.304: - statusLine gets cost"]


# ------------------------------------------------------------------ cd's side: the hook, "seen", the notice
import os  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402


def hook_output(repo):
    p = subprocess.run(["sh", str(W.HOOK), str(repo)], capture_output=True, text=True, timeout=10)
    assert p.returncode == 0, p.stderr
    return p.stdout


def red_ticket(repo, name, status="open — 自動起票"):
    (repo / "docs" / "bugs").mkdir(parents=True, exist_ok=True)
    path = repo / "docs" / "bugs" / name
    path.write_text(f"---\nlibrary: jsonui-cli\nstatus: {status}\n---\n# x\n")
    return path


def test_the_hook_names_a_new_red_ticket(tmp_path):
    red_ticket(tmp_path, "2026-10-20-other-bug.md")
    t = red_ticket(tmp_path, "2026-10-20-cc-dependency-watch-red.md")
    out = hook_output(tmp_path)
    assert t.name in out and "other-bug" not in out


def test_a_seen_or_old_ticket_and_no_ticket_say_nothing(tmp_path):
    assert hook_output(tmp_path) == ""                               # no docs/bugs at all
    (tmp_path / "docs" / "bugs").mkdir(parents=True)
    started = time.monotonic()
    assert hook_output(tmp_path) == ""                               # no tickets
    assert time.monotonic() - started < 1.0
    red_ticket(tmp_path, "2026-10-01-cc-dependency-watch-red.md", status="closed — 直した")
    t = red_ticket(tmp_path, "2026-10-20-cc-dependency-watch-red.md")
    assert t.name in hook_output(tmp_path)
    assert W.mark_seen(t) and not W.mark_seen(t)
    assert "status: seen" in t.read_text()
    assert hook_output(tmp_path) == ""


def test_the_hook_reads_the_ticket_the_watcher_writes(world):
    repo, *_ = world
    go(world, fake_cli(), fake_fetch("2.1.303"))
    go(world, fake_cli(help_text=HELP.replace("--plugin-dir <d>", "")), fake_fetch("2.1.303"))
    [ticket] = tickets(repo)
    assert ticket.name in hook_output(repo)
    W.mark_seen(ticket)
    assert hook_output(repo) == ""


def test_the_desktop_notice_names_the_ticket(tmp_path):
    t = tmp_path / "2026-10-20-cc-dependency-watch-red-2.md"
    assert f"docs/bugs/{t.name}" in W.notice_text(t)


def test_add_hook_merges_once_and_keeps_the_rest(tmp_path):
    f = tmp_path / ".claude" / "settings.local.json"
    f.parent.mkdir()
    f.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"Stop": [{"hooks": []}]}}))
    assert W.add_hook(f, tmp_path) and not W.add_hook(f, tmp_path)
    data = json.loads(f.read_text())
    assert data["permissions"] == {"allow": ["Bash(ls)"]} and "Stop" in data["hooks"]
    [entry] = data["hooks"]["UserPromptSubmit"]
    assert entry["hooks"][0]["command"].endswith(f"red_ticket_hook.sh {tmp_path}")


# ------------------------------------------------------------------ the throwaway session, against a fake CLI
FAKE_CLI = r'''#!/usr/bin/env python3
import json, os, signal, subprocess, sys, time
args = sys.argv[1:]
settings = json.load(open(args[args.index("--settings") + 1]))
mode = os.environ.get("FAKE_MODE", "ok")
def fire(event, extra):
    for e in settings["hooks"].get(event, []):
        for h in e["hooks"]:
            payload = dict(session_id="s", transcript_path="t", cwd=os.getcwd(), hook_event_name=event, **extra)
            subprocess.run(h["command"], shell=True, input=json.dumps(payload), text=True,
                           env={**os.environ, "CLAUDE_PROJECT_DIR": os.getcwd()})
open(os.path.join(os.environ["FAKE_LOG"], "argv-%d" % time.time_ns()), "w").write(json.dumps(
    {"argv": args, "cwd": os.getcwd(), "config": os.environ.get("CLAUDE_CONFIG_DIR"),
     "token": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"), "leaked": sorted(k for k in os.environ if k.startswith("CLAUDE")
     and k not in ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_OAUTH_TOKEN"))}))
fire("SessionStart", {"source": "startup"})
if mode == "nologin":
    fire("SessionEnd", {"reason": "other"})
    print(json.dumps({"is_error": True, "result": "Not logged in · Please run /login", "terminal_reason": "api_error",
                      "total_cost_usd": 0, "usage": {"input_tokens": 0, "output_tokens": 0}}))
    sys.exit(1)
if "Count" in " ".join(args):
    signal.signal(signal.SIGTERM, lambda *a: (fire("SessionEnd", {"reason": "other"}), sys.exit(143)))
    time.sleep(30)
    sys.exit(0)
fire("UserPromptSubmit", {"prompt": "p", "permission_mode": "default"})
fire("SessionEnd", {"reason": "other"})
print(json.dumps({"is_error": False, "result": "ok", "total_cost_usd": 0.01, "usage": {"input_tokens": 5, "output_tokens": 1}}))
'''


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)
    log = tmp_path / "log"
    log.mkdir()
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "the-parent-session")   # must not reach the throwaway session
    work = tmp_path / "work"
    work.mkdir()
    return cli, log, work


def launched(log):
    return [json.loads(p.read_text()) for p in sorted(log.iterdir())]


def test_the_live_session_runs_twice_isolated_and_sigterms_its_own_child(fake_claude):
    cli, log, work = fake_claude
    s = W.live_session(str(cli), work, token=lambda: "tok")
    runs = launched(log)
    assert len(runs) == 2
    for r in runs:
        assert r["config"] == str(work / "config") and r["cwd"] == str(work / "cwd") and r["leaked"] == []
        assert r["token"] == "tok"
        assert r["argv"][:4] == ["--setting-sources", "", "--settings", str(work / "settings.json")]
    assert s.result["ok"] and s.result["cost_usd"] == 0.01 and s.result["usage"]["input_tokens"] == 5
    assert s.sigterm_exit == 143 and s.sigterm_session_end is True
    events = {h["hook_event_name"] for h in s.hook_inputs}
    assert events == {"SessionStart", "UserPromptSubmit", "SessionEnd"}
    assert s.hook_env.get("CLAUDE_PROJECT_DIR") == str(work / "cwd")
    assert P.session_ran(P.Context(run=fake_cli(), session=s)) == {"ok": True}


def test_a_lost_login_is_one_red_shape_and_no_second_run(fake_claude, monkeypatch):
    cli, log, work = fake_claude
    monkeypatch.setenv("FAKE_MODE", "nologin")
    s = W.live_session(str(cli), work, token=lambda: None)
    assert len(launched(log)) == 1 and launched(log)[0]["token"] is None
    assert s.sigterm_exit is None
    assert P.session_ran(P.Context(run=fake_cli(), session=s)) == {
        "ok": False, "result": "Not logged in · Please run /login", "terminal_reason": "api_error"}
