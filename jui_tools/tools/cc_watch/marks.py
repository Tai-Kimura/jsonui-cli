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
    # a path under the config folder, or the global config file: ".claude/…", "~/.claude", / ".claude" / "x"
    "config-path": r"""\.claude(?:/|\.json\b|["'`])""",
    # the CLI started with an argument the code relies on (also inside shell lines and help text)
    "cli": r"""(?<![\w.-])claude(?:\s+(?:-n\b|-p\b|-r\b|--[a-z][\w-]*|plugin\b|mcp\b|config\b|agents\b|auth\b"""
           r"""|setup-token\b|update\b))|["']claude["']\s*[,\]]|["']agents["']\s*,\s*["']--json["']""",
    # the CLI's name used as a value: looked up on PATH, compared with a process or file name; its npm package
    "identity": r"""\bwhich\(\s*["']claude["']|(?:===?|!==?|\bin)\s*["']claude["']|["']claude["']\s*(?:===?|!==?)"""
                r"""|@anthropic-ai/claude-code""",
    # the CLI's environment
    "env": r"\bCLAUDE_[A-Z][A-Z_]*",
    # hook events: the distinctive names anywhere; the generic two quoted, as an object key, or compared with
    "hook-event": r"\b(?:SessionStart|SessionEnd|PreToolUse|PostToolUse|UserPromptSubmit|PermissionRequest|SubagentStop"
                  r"|SubagentStart|PreCompact|TaskCreated|TaskCompleted)\b|[\"'](?:Stop|Notification)[\"']|hook_event_name"
                  r"|\b(?:Stop|Notification)\s*:\s*[\[{]|(?:event|hook)\w*\s*(?:===?|!==?)\s*(?:Stop|Notification)\b",
    # fields of the hook payloads we read (tool_name alone is too common a word in this repository: see the survey)
    "hook-field": r"\b(?:tool_input|tool_response|tool_use_id|permission_mode|transcript_path)\b",
    # the transcripts: the folder glob and the record fields only they have
    "transcript": r"\*/\*\.jsonl\b|\b(?:isSidechain|parentUuid|isMeta|cache_creation_input_tokens|cache_read_input_tokens)\b"
                  r"|[\"']tool_(?:use|result)[\"']",
    # the CLI's tool names we key on (the generic ones — Bash, Edit, Read — are caught through hook-field / the areas)
    "tool-name": r"\b(?:AskUserQuestion|ExitPlanMode|EnterPlanMode|TodoWrite|NotebookEdit|MultiEdit|WebFetch|WebSearch"
                 r"|BashOutput|KillShell|SlashCommand)\b|\bmcp__",
    # settings keys we read or write
    "settings-key": r"\b(?:statusLine|mcpServers|enabledPlugins|extraKnownMarketplaces|apiKeyHelper|allowedTools"
                    r"|permissionMode)\b|setting-sources",
    # channels: the flags, the managed setting, the notification
    "channels": r"--channels\b|--dangerously-load-development-channels|allowedChannelPlugins|channelsEnabled"
                r"|notifications/claude/channel",
    # code that reads or writes the plugin and marketplace manifests
    "plugin-manifest": r"plugin\.json|marketplace\.json",
}
#: Marks on the path itself: the manifests (their own text does not name them).
PATH_MARKS: dict[str, str] = {"plugin-path": r"(^|/)\.claude-plugin/"}

#: Not scanned by the marks: files that check or describe the reliance (they do not break the product when it changes).
EXCLUDE = re.compile(r"(^|/)(tests?|spec|specs|fixtures)/|^jui_tools/tools/viz_e2e/|^dev-guide/|\.md$|^conformance/")

#: The areas that face the CLI directly. Default-deny: every tracked file here is either in a ledger entry or in
#: ledger.json's not_relying with a reason, whatever the marks say (the marks are a net and miss shapes; 10-19 dd
#: found seven files they missed). viz (server, sources, page), the jui-viz plugin, the marketplace manifest, the
#: `jui viz` command, and this watch. viz_e2e is the browser-test harness (tests only), so it is not an area.
FACING = re.compile(r"^(?:jui_tools/jui_cli/viz/|plugins/jui-viz/|\.claude-plugin/|jui_tools/tools/cc_watch/"
                    r"|jui_tools/jui_cli/commands/viz_cmd\.py$)")
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
    "identity": ("tool/g.py", "exe = which('claude')\n"),
    "hook-field": ("tool/h.py", "use = payload.get('tool_use_id')\n"),
    "transcript": ("tool/i.py", "for f in root.glob('*/*.jsonl'):\n"),
    "tool-name": ("tool/j.js", "if (name === 'AskUserQuestion') ask();\n"),
    "settings-key": ("tool/k.py", "conf['statusLine'] = cmd\n"),
}

#: Realistic one-line shapes of relying on the CLI (dd's survey of 10-19, and the ones found while widening): each
#: must hit some mark, so a narrowed regex that drops one turns the gate test red.
SURVEY: list[str] = [
    'SESSIONS = Path.home() / ".claude" / "sessions"',
    'base = os.path.expanduser("~/.claude")',
    'local = root / ".claude" / "settings.local.json"',
    "cfg = HOME / '.claude.json'",
    "ROOT = '~/.claude/projects'",
    'exe = shutil.which("claude")',
    'if os.path.basename(argv[0]) == "claude":',
    "if Path(a).name == 'claude':",
    'cmd = [exe, "agents", "--json"]',
    "proc = run(['claude', '-p', prompt])",
    'npm install -g @anthropic-ai/claude-code',
    'run claude agents --json',
    'if tool == "AskUserQuestion":',
    'if name.startswith("mcp__"):',
    'servers = conf.get("mcpServers", {})',
    'settings["statusLine"] = {"type": "command"}',
    'files = sorted(projects.glob("*/*.jsonl"))',
    'use_id = rec.get("tool_use_id")',
    'mode = payload["permission_mode"]',
    'if block.get("type") == "tool_use":',
    'hooks: { Stop: [cmd] }',
    'if (event === Stop) end();',
    'if ev == "Notification":',
    'case "SessionStart":',
    'cd "$CLAUDE_PROJECT_DIR"',
    'exec claude -n "$NAME"',
    'claude --dangerously-load-development-channels server:jui-viz',
    "MANIFEST = root / '.claude-plugin' / 'plugin.json'",
]

#: Lines that must hit nothing: plain words in prose and the generic names this repository uses for itself.
NOT_RELYING: list[str] = [
    "# Claude wrote this summary of the plan.",
    "Ask claude about it later.",
    'tool_name = "sjui"',
    "Stop the server before you rebuild.",
    "Notification sounds are off.",
    'TITLE = "claude-like"',
    'for line in path.glob("*.jsonl"):',
]

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
