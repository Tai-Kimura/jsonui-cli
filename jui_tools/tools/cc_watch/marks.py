"""The marks of relying on Claude Code, and the scan the ledger gate runs.

A file that matches a mark relies on Claude Code (a path under its config folder, its CLI, its environment, its hook
events, its channels, its plugin manifests). Every such file in the scanned part of the repository must be listed by
an entry of ledger.json, so a new feature that relies on Claude Code cannot land without saying so (requester, 10-19:
"必ず新機能追加したら頼ってる部分があるかどうか検出してあればリストに追加").

What is scanned (SCOPE): the tracked files of the repository, less the files that check or document the reliance
rather than rely on it — tests and their fixtures, the browser-test harness, this watch, the maintainer guide,
Markdown — and the conformance corpus. Each mark has a specimen only it finds (SPECIMENS); the gate test proves a narrowed mark list
leaks it.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

MARKS: dict[str, str] = {
    # a path under the config folder, or the global config file
    "config-path": r"\.claude/|\.claude\.json",
    # the CLI started with an argument the code relies on (also inside shell lines and help text)
    "cli": r"""(?<![\w.-])claude(?:\s+(?:-n\b|-p\b|-r\b|--[a-z][\w-]*|plugin\b|mcp\b|config\b))|["']claude["']\s*[,\]]""",
    # the CLI's environment
    "env": r"\bCLAUDE_[A-Z][A-Z_]*",
    # hook events: the distinctive names anywhere, the generic two only as a quoted name, and the payload's field
    "hook-event": r"\b(?:SessionStart|SessionEnd|PreToolUse|PostToolUse|UserPromptSubmit|PermissionRequest|SubagentStop"
                  r"|SubagentStart|PreCompact)\b|[\"'](?:Stop|Notification)[\"']|hook_event_name",
    # channels: the flags, the managed setting, the notification
    "channels": r"--channels\b|--dangerously-load-development-channels|allowedChannelPlugins|channelsEnabled"
                r"|notifications/claude/channel",
    # code that reads or writes the plugin and marketplace manifests
    "plugin-manifest": r"plugin\.json|marketplace\.json",
}
#: Marks on the path itself: the manifests (their own text does not name them).
PATH_MARKS: dict[str, str] = {"plugin-path": r"(^|/)\.claude-plugin/"}

#: Not scanned: files that check or describe the reliance (they do not break the product when it changes), this
#: watch itself among them (it names every mark, and its probes are what tell when the reliance changed).
EXCLUDE = re.compile(r"(^|/)(tests?|spec|specs|fixtures)/|^jui_tools/tools/viz_e2e/|^jui_tools/tools/cc_watch/|^dev-guide/"
                     r"|\.md$|^conformance/")
BINARY = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".zip", ".jar", ".pdf")

#: mark -> (a planted file's path, its text) that this mark alone finds. The gate test plants each one, scans it with
#: every mark (found) and with that mark taken out (missed): a narrowed list leaks a known hit.
SPECIMENS: dict[str, tuple[str, str]] = {
    "config-path": ("tool/a.py", "SETTINGS = HOME / '.claude/settings.json'\n"),
    "cli": ("tool/b.sh", "exec claude -n worker\n"),
    "env": ("tool/c.sh", 'cd "$CLAUDE_PROJECT_DIR"\n'),
    "hook-event": ("tool/d.py", "if event == 'SessionStart':\n"),
    "channels": ("tool/e.sh", "run --dangerously-load-development-channels server:x\n"),
    "plugin-manifest": ("tool/f.py", "MANIFEST = 'plugin.json'\n"),
    "plugin-path": ("x/.claude-plugin/manifest.json", "{}\n"),
}

COMPILED = {k: re.compile(v) for k, v in MARKS.items()}
COMPILED_PATHS = {k: re.compile(v) for k, v in PATH_MARKS.items()}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def tracked_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout
        return [x for x in out.splitlines() if x]
    except (OSError, subprocess.CalledProcessError):   # not a checkout: every file under the root
        return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]


def in_scope(path: str) -> bool:
    return not EXCLUDE.search(path) and not path.lower().endswith(BINARY)


def scan(root: Path, marks: dict[str, re.Pattern] | None = None, files: list[str] | None = None,
         path_marks: dict[str, re.Pattern] | None = None) -> dict[str, list[tuple[str, int, str]]]:
    """file -> [(mark, line number, line)] for every scanned file a mark finds (the first line per mark; a path mark
    reports line 0)."""
    marks = COMPILED if marks is None else marks
    path_marks = COMPILED_PATHS if path_marks is None else path_marks
    hits: dict[str, list[tuple[str, int, str]]] = {}
    for rel in (files if files is not None else tracked_files(root)):
        if not in_scope(rel):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found = [(name, 0, rel) for name, rx in path_marks.items() if rx.search(rel)]
        for name, rx in marks.items():
            m = rx.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                found.append((name, line, text.splitlines()[line - 1].strip()[:160]))
        if found:
            hits[rel] = found
    return hits
