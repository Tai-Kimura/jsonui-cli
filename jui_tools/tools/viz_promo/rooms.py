"""The rooms and the throwaway HOME a capture runs in (ticket 2026-10-21-viz-promo-replay-and-capture-tool §2).

    demo-shop    the tracked files of the jsonui-demo-shop workdir (`git archive HEAD`), a fresh git repository of one
                 commit by a neutral author (the source's history carries its author's name and address, which the
                 room's git box could show). For --lang en, docs/infra is rewritten by the project's own
                 tools/make_infra.py --lang en and tools/make_load.py --lang en, and committed, so the tree is clean.
    demo-admin   a near-empty git workdir (a README of WORDS[lang]), as is demo-docs: rooms for the floor's bustle.

The HOME holds the viz's folder (config.json: the question window long enough for a capture that runs slower than
the video), the agent CLI's session entries (the names on the robots' tags) and the transcripts. bin/ holds stand-ins for
xcrun and adb that list no device, put first on the server's PATH: the device pane must not show this machine's
simulators. Nothing here reads or writes the real HOME.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

from viz_promo.timeline import ROOMS, SESSIONS, WORDS, session_id, session_pid

DEMO_SHOP = Path(os.environ.get("JUI_PROMO_DEMO_SHOP", Path.home() / "resource" / "jsonui-demo-shop"))
# the author of every commit in the rooms: neutral, never the machine's git identity
GIT_ENV = {"GIT_AUTHOR_NAME": "demo", "GIT_AUTHOR_EMAIL": "demo@example.invalid", "GIT_COMMITTER_NAME": "demo",
           "GIT_COMMITTER_EMAIL": "demo@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
# the viz's settings for a capture: a question waits as long as the capture of its chapter can take
CONFIG = {"askWaitSec": 600, "askMaxSec": 1800, "decideWaitSec": 600, "notifyPresenceSec": 3600, "talkGraceSec": 3600}
XCRUN = """#!/bin/sh
# a stand-in: no simulator is booted (the capture's server must not list this machine's)
if [ "$1" = simctl ]; then echo '{"devices": {}}'; exit 0; fi
exit 1
"""
ADB = """#!/bin/sh
# a stand-in: no device is attached
echo "List of devices attached"
echo
"""


def git(cwd: Path, *args: str) -> str:
    env = dict(os.environ, **GIT_ENV)
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def commit_all(root: Path, message: str) -> None:
    git(root, "add", "-A")
    if git(root, "status", "--porcelain").strip():
        git(root, "commit", "-q", "--no-verify", "--no-gpg-sign", "-m", message)


def copy_demo_shop(dest: Path, lang: str, src: Path = DEMO_SHOP) -> Path:
    """The demo-shop room: src's tracked files at HEAD in a fresh repository of one commit."""
    if not (src / "jui.config.json").is_file():
        raise SystemExit(f"demo-shop not found at {src} (set JUI_PROMO_DEMO_SHOP)")
    dest.mkdir(parents=True, exist_ok=False)
    tar = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=src, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")
        else:   # an older 3.11 patch release: our own archive of tracked files
            tf.extractall(dest)
    git(dest, "init", "-q", "-b", "main")
    commit_all(dest, "demo-shop")
    if lang == "en":
        # the project's own generators, with the copy's own scripts, into the copy's docs/infra
        for script, out in (("make_infra.py", dest / "docs" / "infra"), ("make_load.py", dest / "docs" / "infra" / "load")):
            subprocess.run([sys.executable, str(dest / "tools" / script), "--lang", "en", "--out", str(out)],
                           cwd=dest, check=True, capture_output=True)
        commit_all(dest, "English labels")
    return dest


def small_room(dest: Path, name: str, lang: str) -> Path:
    dest.mkdir(parents=True, exist_ok=False)
    (dest / "README.md").write_text(WORDS[lang]["room_readme"][name], encoding="utf-8")
    git(dest, "init", "-q", "-b", "main")
    commit_all(dest, name)
    return dest


def make_rooms(work: Path, lang: str, src: Path = DEMO_SHOP) -> dict:
    """{room name: its folder} under work/ (the folder's name is the room's name on the floor)."""
    rooms = {"demo-shop": copy_demo_shop(work / "demo-shop", lang, src)}
    for name in ROOMS[1:]:
        rooms[name] = small_room(work / name, name, lang)
    return rooms


def project_slug(cwd: Path) -> str:
    """The transcripts' folder name the agent CLI gives a cwd (every / and . a -)."""
    return str(cwd).replace("/", "-").replace(".", "-")


def make_home(home: Path) -> dict:
    """The throwaway HOME's folders: {viz, sessions, projects, progress, bin}."""
    viz = home / ".local" / "state" / "jui-viz"
    paths = {"viz": viz, "sessions": home / ".claude" / "sessions", "projects": home / ".claude" / "projects",
             "progress": viz / "test-progress", "bin": home / "bin"}
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    (viz / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    for name, text in (("xcrun", XCRUN), ("adb", ADB)):
        f = paths["bin"] / name
        f.write_text(text, encoding="utf-8")
        f.chmod(0o755)
    return paths


def write_sessions(paths: dict, rooms: dict, lang: str) -> dict:
    """The CLI's sessions/<pid>.json for every session (its name is the robot's tag) and an empty transcript.
    Returns {key: transcript path}."""
    now = int(time.time() * 1000)
    transcripts = {}
    for key, _, room in SESSIONS:
        cwd = rooms[room]
        sid = session_id(key)
        entry = {"pid": session_pid(key), "sessionId": sid, "cwd": str(cwd), "kind": "interactive", "entrypoint": "cli",
                 "status": "busy", "name": WORDS[lang]["names"][key], "startedAt": now - 1_800_000,
                 "messagingSocketPath": f"/tmp/promo-socks/{session_pid(key)}.sock"}
        (paths["sessions"] / f"{session_pid(key)}.json").write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        folder = paths["projects"] / project_slug(cwd)
        folder.mkdir(parents=True, exist_ok=True)
        transcripts[key] = folder / f"{sid}.jsonl"
        transcripts[key].touch()
    return transcripts


def cleanup(base: Path) -> None:
    shutil.rmtree(base, ignore_errors=True)
