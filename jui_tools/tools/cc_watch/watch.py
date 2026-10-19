#!/usr/bin/env python3
"""The daily watch over what we rely on in Claude Code (ticket 2026-10-19-claude-dependency-watch).

    python3 jui_tools/tools/cc_watch/watch.py run --repo ~/resource/jsonui-cli [--live]
    python3 jui_tools/tools/cc_watch/watch.py print-plist --repo ~/resource/jsonui-cli
    python3 jui_tools/tools/cc_watch/watch.py install --repo ~/resource/jsonui-cli      # the user runs this
    python3 jui_tools/tools/cc_watch/watch.py uninstall

One run:
  1. versions: the installed CLI's (`claude --version`) and the newest published one (the npm registry). Only when they
     differ is the CHANGELOG fetched, and its lines between the two versions that name something in the ledger are kept.
  2. probes: every probe of probes.py; with --live, after one short throwaway session (live_session) in a temporary
     config folder (CLAUDE_CONFIG_DIR) with no setting source but its own (`--setting-sources ""`, `--settings`): the
     user's hooks, plugins and statusLine do not run, so no robot appears in viz and nothing reaches session-recovery.
     Each shape is compared with the one saved by the last run (the state folder); the first run only saves.
  3. red (a shape changed, or a probe raised): a ticket in <repo>/docs/bugs, the orchestrator told (notify), the new
     shapes saved (one ticket per change, not one a day); green: one log line, nothing else.
Every temporary folder is removed whatever happens.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from cc_watch import probes as P  # noqa: E402
from cc_watch.ledger import load  # noqa: E402

LABEL = "dev.jsonui.cc-dependency-watch"
REGISTRY = "https://registry.npmjs.org/@anthropic-ai/claude-code/latest"
CHANGELOG = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"
#: CHANGELOG words that touch the ledger (hooks, channels, transcripts, statusLine, plugins, the options we pass …).
WORDS = re.compile(r"hook|SessionStart|SessionEnd|PreToolUse|PostToolUse|UserPromptSubmit|PermissionRequest|channel"
                   r"|transcript|jsonl|statusLine|status line|plugin|marketplace|\bmcp\b|--name|\B-n\b|--resume|settings\.json"
                   r"|SIGTERM|CLAUDE_|setting-sources|--print", re.I)
DEFAULT_STATE = Path("~/.local/state/cc-dependency-watch").expanduser()


def _version(text: str) -> str | None:
    m = re.search(r"(\d+\.\d+\.\d+)", text or "")
    return m.group(1) if m else None


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:   # noqa: S310 (fixed https URLs)
        return r.read().decode("utf-8", "replace")


def default_runner(cli: str, env: dict | None = None) -> Callable[[list[str]], tuple[int, str]]:
    def run(argv: list[str]) -> tuple[int, str]:
        p = subprocess.run([cli, *argv], capture_output=True, text=True, timeout=60, env=env, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout + p.stderr
    return run


def changelog_lines(text: str, old: str, new: str) -> list[str]:
    """The lines of the sections after *old* up to *new* that name something in the ledger."""
    out, current = [], None
    for line in text.splitlines():
        m = re.match(r"^#+\s*\[?(\d+\.\d+\.\d+)", line)
        if m:
            current = m.group(1)
            continue
        if current and _vkey(old) < _vkey(current) <= _vkey(new) and WORDS.search(line):
            out.append(f"{current}: {line.strip()}")
    return out


# ------------------------------------------------------------------ the throwaway session (--live)
CAPTURE = r'''import json, os, sys, time
d = sys.argv[1]; kind = sys.argv[2]
data = sys.stdin.read()
name = f"{kind}-{time.time_ns()}.json"
with open(os.path.join(d, name), "w") as f:
    json.dump({"kind": kind, "stdin": data, "env": {k: v for k, v in os.environ.items() if k.startswith("CLAUDE_")}}, f)
if kind == "statusline":
    print("ok")
'''


#: The Keychain item the watcher reads its login from (made once by the user, see token_from_keychain).
TOKEN_SERVICE = "cc-dependency-watch"


def token_from_keychain() -> str | None:
    """The long-lived login for the throwaway session. Measured 10-19 22:00: with CLAUDE_CONFIG_DIR set to a temporary
    folder the CLI does not find the user's login ("Not logged in · Please run /login", nothing spent), so the session
    needs its own: `claude setup-token` once, stored by the user in the login Keychain under TOKEN_SERVICE, passed to
    the session as CLAUDE_CODE_OAUTH_TOKEN (never written to a file)."""
    if not shutil.which("security"):
        return None
    r = subprocess.run(["security", "find-generic-password", "-s", TOKEN_SERVICE, "-w"], capture_output=True, text=True)
    return r.stdout.strip() or None if r.returncode == 0 else None


#: How the user stores the login. `-w` comes last with no value, so `security` asks for the token at a prompt: the
#: token never appears as an argument (shell history, `ps`). Printed by `watch.py token-help` and in a login ticket.
TOKEN_HELP = (
    "1. `claude setup-token` を撃ち、表示されたトークンを控える。\n"
    f"2. `security add-generic-password -s {TOKEN_SERVICE} -a \"$USER\" -w` を撃ち、聞かれたらトークンを貼る"
    "（-w は最後に値なしで書く。値を引数に書くと履歴と ps に残る）。\n"
    f"3. 作り直すときは `security delete-generic-password -s {TOKEN_SERVICE}` の後に 2 をもう一度。"
)


def default_watched() -> list[Path]:
    """The user's real state the throwaway session must not reach: session-recovery, sessions, projects, viz's state."""
    home = Path.home()
    viz = os.environ.get("JUI_VIZ_HOME") or (os.path.join(os.environ["XDG_STATE_HOME"], "jui-viz")
                                             if os.environ.get("XDG_STATE_HOME") else str(home / ".local/state/jui-viz"))
    return [home / ".claude/session-recovery", home / ".claude/sessions", home / ".claude/projects", Path(viz)]


def watched_state(roots: list[Path]) -> dict[str, tuple[float, int]]:
    """path -> (mtime, size) under each root; ~/.claude/projects only one level down (one folder per working folder)."""
    out: dict[str, tuple[float, int]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        entries = root.iterdir() if root.name == "projects" else root.rglob("*")
        for f in entries:
            try:
                st = f.stat()
            except OSError:
                continue
            out[str(f)] = (st.st_mtime, st.st_size if f.is_file() else -1)
    return out


def own_traces(before: dict, after: dict, marks: list[str]) -> list[str]:
    """The added or changed paths whose name or content carries one of *marks* (the session id, the temporary path
    and its folder-name form). Other lanes rewrite these folders all the time; only our own marks mean a leak."""
    hits = []
    for path, stamp in after.items():
        if before.get(path) == stamp:
            continue
        if any(m in path for m in marks):
            hits.append(path)
            continue
        if stamp[1] < 0 or stamp[1] > 20_000_000:
            continue
        try:
            data = Path(path).read_bytes()
        except OSError:
            continue
        if any(m.encode() in data for m in marks):
            hits.append(path)
    return sorted(hits)


def live_session(cli: str, work: Path, timeout: int = 180, token: Callable[[], str | None] = token_from_keychain,
                 watched: Callable[[], list[Path]] = default_watched) -> P.Session:
    """One short session in a temporary config folder and an empty working folder, its own hooks recording their input,
    then one run stopped with SIGTERM (only the process started here). Uses a little of the account's quota.
    Measured 10-19 22:00 (run 1): CLAUDE_CONFIG_DIR=<tmp> + --setting-sources "" + --settings <own> fired only the
    hooks of <own> (SessionStart, UserPromptSubmit, SessionEnd captured); no robot in viz, nothing for the session in
    session-recovery, ~/.claude/projects or ~/.claude/sessions.
    The guard: the watched folders are read before and after the first run; if a path added or changed there carries
    this session's id or temporary path, the SIGTERM run is not fired and the session reports the leak (red).
    The token reaches the CLI only through the child's environment, never its argv."""
    config, cap, cwd = work / "config", work / "captured", work / "cwd"
    for d in (config, cap, cwd):
        d.mkdir()
    script = work / "capture.py"
    script.write_text(CAPTURE)
    hook = lambda kind: [{"hooks": [{"type": "command", "command": f"{sys.executable} {script} {cap} {kind}"}]}]  # noqa: E731
    settings = {"hooks": {e: hook(e) for e in ("SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")},
                "statusLine": {"type": "command", "command": f"{sys.executable} {script} {cap} statusline"}}
    (work / "settings.json").write_text(json.dumps(settings))
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    env.update(CLAUDE_CONFIG_DIR=str(config))
    if (t := token()) is not None:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = t
    base = [cli, "--setting-sources", "", "--settings", str(work / "settings.json")]
    roots = watched()
    before = watched_state(roots)
    p = subprocess.run([*base, "-p", "Run the shell command `true`, then reply with the single word ok.",
                        "--output-format", "json", "--allowedTools", "Bash(true)"],
                       cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    session = P.Session(config_dir=config)
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = {"is_error": True, "result": (p.stdout + p.stderr).strip()[:200]}
    session.result = {"ok": not out.get("is_error", True), "result": str(out.get("result", ""))[:200],
                      "terminal_reason": out.get("terminal_reason"), "cost_usd": out.get("total_cost_usd"),
                      "usage": {k: (out.get("usage") or {}).get(k) for k in ("input_tokens", "output_tokens",
                                "cache_creation_input_tokens", "cache_read_input_tokens")}}
    marks = [str(work), re.sub(r"[^A-Za-z0-9-]", "-", str(work))] + ([out["session_id"]] if out.get("session_id") else [])
    session.result["leaks"] = own_traces(before, watched_state(roots), marks)
    if session.result["ok"] and not session.result["leaks"]:
        # SIGTERM: a second run, stopped once its SessionStart hook ran (only this process, which we started)
        before = {f.name for f in cap.iterdir()}
        proc = subprocess.Popen([*base, "-p", "Count from 1 to 200, one number per line."], cwd=cwd, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and not any(n.startswith("SessionStart") for n in {f.name for f in cap.iterdir()} - before):
                time.sleep(0.5)
            proc.send_signal(signal.SIGTERM)
            session.sigterm_exit = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        time.sleep(2)   # a SessionEnd hook may still be writing
        after = {f.name for f in cap.iterdir()} - before
        session.sigterm_session_end = any(n.startswith("SessionEnd") for n in after)
    else:
        after = set()
    for f in sorted(cap.iterdir()):
        if f.name in after:
            continue
        rec = json.loads(f.read_text())
        if rec["kind"] == "statusline":
            session.statusline = json.loads(rec["stdin"] or "null")
        else:
            try:
                session.hook_inputs.append(json.loads(rec["stdin"]))
            except ValueError:
                pass
            session.hook_env.update(rec["env"])
    return session


# ------------------------------------------------------------------ one run
def run_probes(ctx: P.Context) -> dict:
    out = {}
    for name, fn in P.PROBES.items():
        try:
            out[name] = fn(ctx)
        except Exception as e:  # a probe that raises is red, with what it raised
            out[name] = {"error": f"{type(e).__name__}: {e}"[:300]}
    return out


def notice_text(ticket: Path) -> str:
    """The desktop notice: the ticket's file name in one line the user can paste to cd."""
    return f"Claude Code の依存の見張りが赤: docs/bugs/{ticket.name} を見て"


def notify_route(ticket: Path) -> list[str]:
    """Tell the orchestrator. Measured 10-19: a script has no way to send a cross-session message (the CLI has no such
    command; that channel exists only inside a running session), and viz has no notice endpoint (its /hook would make
    a robot). What reaches cd from a script: the ticket in docs/bugs (cd's queue), and the desktop notification the
    user sees (they forward it). On top of both (10-19 ruling), red_ticket_hook.sh, a UserPromptSubmit hook cd installs
    in its own session (`watch.py print-hook`), puts every unseen red ticket in cd's context at its next prompt.
    Returns what was done."""
    done = [f"ticket {ticket}"]
    if shutil.which("osascript"):
        msg = notice_text(ticket)
        r = subprocess.run(["osascript", "-e", f'display notification {json.dumps(msg)} with title "cc-dependency-watch"'],
                           capture_output=True, timeout=20)
        done.append(f"desktop notification (exit {r.returncode})")
    return done


def write_ticket(repo: Path, today: str, installed: str | None, latest: str | None, changed: dict, lines: list[str]) -> Path:
    folder = repo / "docs" / "bugs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{today}-cc-dependency-watch-red.md"
    n = 2
    while path.exists():
        path = folder / f"{today}-cc-dependency-watch-red-{n}.md"
        n += 1
    led = {"session_ran": {"name": "使い捨てのセッションが動いたか（ログイン）",
                           "impact": "セッション系の probe（hooks・transcript・env・statusLine・SIGTERM・config）が測れない",
                           "files": []},
           **{e["probe"]: e for e in load()["entries"]}}
    body = [
        "---", "library: jsonui-cli", "component: Claude Code への依存（jui_tools/tools/cc_watch/ledger.json）",
        "reported_by: cc-dependency-watch（毎日の見張り、自動）", f"reported_at: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "kind: bug（依存の変化）", "status: open — 自動起票。cd が手の空いた JsonUI のセッションに振る", "severity: medium",
        f"found_on: Claude Code {installed or '?'}（配布の最新 {latest or '?'}）", "---", "",
        f"# Claude Code の頼りどころが変わった（{', '.join(sorted(changed))}）", "",
        "## 落ちた probe（前回の形 → 今回の形）",
    ]
    for name, (old, new) in sorted(changed.items()):
        e = led.get(name, {})
        body += [f"### {name}（{e.get('name', '?')}）", f"- 影響: {e.get('impact', '?')}",
                 f"- 使っている所: {', '.join(e.get('files', []))}",
                 f"- 前回: `{json.dumps(old, ensure_ascii=False, sort_keys=True)}`",
                 f"- 今回: `{json.dumps(new, ensure_ascii=False, sort_keys=True)}`", ""]
    if "session_ran" in changed:
        body += ["## ログインの入れ方（使い捨てのセッションが動かなかったとき）", TOKEN_HELP, ""]
    body += ["## CHANGELOG の該当しそうな行", *(f"- {ln}" for ln in lines or ["（版が変わっていない、または該当なし）"]), ""]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


def run(repo: Path, state: Path, live: bool, cli: str = "claude", runner=None, fetch=default_fetch, notify=notify_route,
        session_maker=live_session, now: dt.datetime | None = None) -> dict:
    """One day's watch. Returns what it found (also written to the log)."""
    now = now or dt.datetime.now()
    today = now.strftime("%Y-%m-%d")
    state.mkdir(parents=True, exist_ok=True)
    run_cli = runner or default_runner(cli)
    installed = _version(run_cli(["--version"])[1])
    try:
        latest = _version(json.loads(fetch(REGISTRY)).get("version", ""))
    except Exception:  # offline: the probes still run
        latest = None
    lines: list[str] = []
    if installed and latest and installed != latest:
        try:
            lines = changelog_lines(fetch(CHANGELOG), min(installed, latest, key=_vkey), max(installed, latest, key=_vkey))
        except Exception as e:
            lines = [f"（CHANGELOG を取れなかった: {type(e).__name__}）"]
    work = Path(tempfile.mkdtemp(prefix="cc-watch-"))
    try:
        session = session_maker(cli, work) if live else None
        shapes = run_probes(P.Context(run=run_cli, session=session))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    saved_path = state / "shapes.json"
    saved = json.loads(saved_path.read_text()) if saved_path.exists() else None
    changed = {} if saved is None else {k: (saved.get(k), v) for k, v in shapes.items() if saved.get(k) != v}
    errors = {k: v for k, v in shapes.items() if isinstance(v, dict) and "error" in v}
    for k, v in errors.items():
        changed.setdefault(k, (saved.get(k) if saved else None, v))
    result = {"at": now.isoformat(timespec="seconds"), "installed": installed, "latest": latest,
              "changelog_lines": len(lines), "changed": sorted(changed), "baseline": saved is None,
              "session": session.result if session is not None else None}   # cost and tokens of the live run
    if changed:
        ticket = write_ticket(repo, today, installed, latest, changed, lines)
        result["ticket"] = str(ticket)
        result["notified"] = notify(ticket)
        if saved is not None:
            (state / f"shapes-{today}-before.json").write_text(json.dumps(saved, ensure_ascii=False, sort_keys=True, indent=1))
    saved_path.write_text(json.dumps(shapes, ensure_ascii=False, sort_keys=True, indent=1))
    with open(state / "watch.log", "a", encoding="utf-8") as log:
        log.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result


# ------------------------------------------------------------------ cd's side: the hook and "seen"
HOOK = HERE / "red_ticket_hook.sh"
UNSEEN = re.compile(r"^status: open\b.*$", re.M)


def mark_seen(ticket: Path, now: dt.datetime | None = None) -> bool:
    """Rewrite the ticket's status line from open to seen (the hook stops naming it). False if it was not open."""
    text = ticket.read_text(encoding="utf-8")
    stamp = (now or dt.datetime.now()).strftime("%Y-%m-%d %H:%M")
    new, n = UNSEEN.subn(f"status: seen {stamp} — cd が読んだ。振り先と結果はこの票に書く", text, count=1)
    if n:
        ticket.write_text(new, encoding="utf-8")
    return bool(n)


def hook_settings(repo: Path) -> dict:
    return {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": f"{HOOK} {repo}"}]}]}}


def add_hook(settings_file: Path, repo: Path) -> bool:
    """Merge the hook into *settings_file* (cd runs this; it is never run for cd). False if it is already there."""
    data = json.loads(settings_file.read_text()) if settings_file.exists() else {}
    entries = data.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    command = hook_settings(repo)["hooks"]["UserPromptSubmit"][0]
    if any(h.get("command") == command["hooks"][0]["command"] for e in entries for h in e.get("hooks", [])):
        return False
    entries.append(command)
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return True


# ------------------------------------------------------------------ launchd
def plist(repo: Path, state: Path, live: bool = False, python: str = sys.executable, hour: int = 8, minute: int = 30) -> bytes:
    """The LaunchAgent. --live (the throwaway session) is opt-in: it has not been run for real yet (ticket: 未測定)."""
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [python, str(HERE / "watch.py"), "run", "--repo", str(repo), "--state", str(state),
                             *(["--live"] if live else [])],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(state / "launchd.out.log"), "StandardErrorPath": str(state / "launchd.err.log"),
        "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    })


def plist_path() -> Path:
    return Path("~/Library/LaunchAgents").expanduser() / f"{LABEL}.plist"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the daily watch over what we rely on in Claude Code")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "print-plist", "install"):
        s = sub.add_parser(name)
        s.add_argument("--repo", required=True, type=lambda p: Path(p).expanduser().resolve())
        s.add_argument("--state", default=DEFAULT_STATE, type=lambda p: Path(p).expanduser())
        s.add_argument("--live", action="store_true", help="also run the throwaway session (uses a little quota)")
        if name == "run":
            s.add_argument("--cli", default="claude")
    sub.add_parser("uninstall")
    sub.add_parser("token-help", help="how to store the login of the throwaway session")
    s = sub.add_parser("seen", help="mark a red ticket as read (the hook stops naming it)")
    s.add_argument("ticket", type=Path)
    for name in ("print-hook", "add-hook"):
        s = sub.add_parser(name, help="the UserPromptSubmit hook for cd's session (add-hook merges it; cd runs it)")
        s.add_argument("--repo", required=True, type=lambda p: Path(p).expanduser().resolve())
        if name == "add-hook":
            s.add_argument("--settings", required=True, type=lambda p: Path(p).expanduser())
    a = ap.parse_args(argv)
    if a.cmd == "token-help":
        print(TOKEN_HELP)
        return 0
    if a.cmd == "seen":
        return 0 if mark_seen(a.ticket) else 1
    if a.cmd == "print-hook":
        print(json.dumps(hook_settings(a.repo), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "add-hook":
        print("added" if add_hook(a.settings, a.repo) else "already there")
        return 0
    if a.cmd == "run":
        print(json.dumps(run(a.repo, a.state, a.live, a.cli), ensure_ascii=False))
        return 0
    if a.cmd == "print-plist":
        sys.stdout.write(plist(a.repo, a.state, a.live).decode())
        return 0
    uid = os.getuid()
    if a.cmd == "install":
        a.state.mkdir(parents=True, exist_ok=True)
        path = plist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plist(a.repo, a.state, a.live))
        return subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(path)]).returncode
    path = plist_path()
    rc = subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"]).returncode
    if path.exists():
        path.unlink()
    return rc


if __name__ == "__main__":
    sys.exit(main())
