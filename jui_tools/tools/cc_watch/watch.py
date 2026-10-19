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


def live_session(cli: str, work: Path, timeout: int = 180) -> P.Session:
    """One short session in a temporary config folder, its own hooks recording their input, then one SIGTERM'd run.
    Uses a little of the account's quota. Nothing outside *work* is written (CLAUDE_CONFIG_DIR, --setting-sources "")."""
    config, cap = work / "config", work / "captured"
    config.mkdir()
    cap.mkdir()
    script = work / "capture.py"
    script.write_text(CAPTURE)
    hook = lambda kind: [{"hooks": [{"type": "command", "command": f"{sys.executable} {script} {cap} {kind}"}]}]  # noqa: E731
    settings = {"hooks": {e: hook(e) for e in ("SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")},
                "statusLine": {"type": "command", "command": f"{sys.executable} {script} {cap} statusline"}}
    (work / "settings.json").write_text(json.dumps(settings))
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
    env.update(CLAUDE_CONFIG_DIR=str(config))
    base = [cli, "--setting-sources", "", "--settings", str(work / "settings.json")]
    subprocess.run([*base, "-p", "Run the shell command `true`, then reply with the single word ok."],
                   cwd=work, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    session = P.Session(config_dir=config)
    # SIGTERM: a second run, stopped by us once its SessionStart hook ran (only this process, which we started)
    before = {p.name for p in cap.iterdir()}
    proc = subprocess.Popen([*base, "-p", "Count from 1 to 200, one number per line."], cwd=work, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not any(n.startswith("SessionStart") for n in {p.name for p in cap.iterdir()} - before):
            time.sleep(0.5)
        proc.send_signal(signal.SIGTERM)
        session.sigterm_exit = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    after = {p.name for p in cap.iterdir()} - before
    session.sigterm_session_end = any(n.startswith("SessionEnd") for n in after)
    for f in sorted(cap.iterdir()):
        rec = json.loads(f.read_text())
        if f.name in after:
            continue
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


def notify_route(ticket: Path) -> list[str]:
    """Tell the orchestrator. Measured 10-19: a script has no way to send a cross-session message (the CLI has no such
    command; that channel exists only inside a running session), and viz has no notice endpoint (its /hook would make
    a robot). What reaches cd from a script: the ticket in docs/bugs (cd's queue), and the desktop notification the
    user sees (they forward it). Returns what was done."""
    done = [f"ticket {ticket}"]
    if shutil.which("osascript"):
        msg = f"Claude Code の依存の見張り: 赤。票 {ticket.name}"
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
    led = {e["probe"]: e for e in load()["entries"]}
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
              "changelog_lines": len(lines), "changed": sorted(changed), "baseline": saved is None}
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
    a = ap.parse_args(argv)
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
