"""Hook event → a robot's state and its one-line ``act``. Design: 04 §3.

States match the page's STATES (robot-core.js): idle, thinking, typing, reading,
command, phone, waiting, carry, done. ``thinking`` is set by the world's tick (a busy
session quiet for THINKING_AFTER_MS), not by an event.
"""
from __future__ import annotations

import os
import re
import shlex

TYPING_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
READING_TOOLS = {"Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "ToolSearch"}
# Reading the web (requester 10-20: "WebFetchの時は机で辞書をペラペラめくるアニメーションにして欲しい"; WebSearch too, the
# requester's answer the same morning): still the state 'reading' (its lamp and its tag's 読む as they were), with the
# sub-kind agent["readKind"] = "web", and the page opens a thick dictionary on the desk and flips its pages. One tool a
# line: taking a tool out of the dictionary (or putting one in) is that one line.
WEB_READING_TOOLS = {
    "WebFetch",
    "WebSearch",
}
COMMAND_TOOLS = {"Bash", "BashOutput"}
# Calling a subagent blows a whistle (requester 10-20: "サブエージェント呼ぶのは笛鳴らそうか"): a short signal of a fixed
# length from the moment the call starts, not the call's length (cd measured 3 days: a background Agent ends in
# p50 0.5 s, a foreground one runs p50 74 s — it whistles only at its start, then waits as before). The page's demo
# beats use the same length (30-source-demo.js, DEMO_BEATS.launchSec).
LAUNCH_TOOLS = {"Agent", "Task"}
LAUNCH_WHISTLE_MS = 2_500
READING_MCP = re.compile(r"^mcp__jui-tools__(read_|lookup_|list_|search_|get_)")
COMMAND_MCP = re.compile(r"^mcp__jui-tools__(jui_build|jui_verify|doc_|test_)")
ROLE_BY_TYPE = (
    ("jsonui-define", "define"), ("jsonui-ground", "ground"), ("jsonui-implement", "implement"),
    ("jsonui-navigation-", "navigation"), ("jsonui-test", "test"), ("jsonui-debug", "debug"),
)

ACT_MAX = 120


def role_for(agent_type: str | None, main: bool) -> str:
    if main:
        return "main"
    for prefix, role in ROLE_BY_TYPE:
        if agent_type and (agent_type == prefix or agent_type.startswith(prefix)):
            return role
    return "other"


def _rel(path: str, root: str | None) -> str:
    if root and path.startswith(root.rstrip(os.sep) + os.sep):
        return path[len(root.rstrip(os.sep)) + 1:]
    from .rooms import tilde

    return tilde(path)


def _clip(text: str, n: int = ACT_MAX) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def state_for_tool(tool: str, tool_input: dict) -> str:
    if tool in TYPING_TOOLS:
        return "typing"
    if tool in COMMAND_TOOLS:
        command = str(tool_input.get("command", ""))
        return "phone" if test_platform(command) is not None or drives_a_device(command) else "command"
    if tool in READING_TOOLS or READING_MCP.match(tool):
        return "reading"
    if COMMAND_MCP.match(tool):
        return "command"
    if tool in ("Agent", "Task"):
        return "carry"
    return "command"


def read_kind(tool: str) -> str | None:
    """The kind of reading a tool is: "web" for the dictionary on the desk, None for the book in the hands."""
    return "web" if tool in WEB_READING_TOOLS else None


def act_for_tool(tool: str, tool_input: dict, root: str | None) -> str:
    """The one line under the robot: ``Write docs/screens/json/login.spec.json``."""
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path")
    if tool in TYPING_TOOLS or tool == "Read":
        return _clip(f"{tool} {_rel(str(path), root)}" if path else tool)
    if tool in COMMAND_TOOLS:
        return _clip(f"Bash {tool_input.get('description') or tool_input.get('command') or ''}".rstrip())
    if tool in ("Grep", "Glob"):
        return _clip(f"{tool} {tool_input.get('pattern', '')}")
    if tool in ("Agent", "Task"):
        kind = tool_input.get("subagent_type") or "agent"
        return _clip(f"依頼 {kind}: {tool_input.get('description', '')}")
    if tool.startswith("mcp__"):
        name = tool.split("__", 2)[-1]
        return _clip(f"{name} {_rel(str(path), root)}" if path else name)
    return _clip(tool)


# ---------------------------------------------------------------- test runs (09 §4)

# Counts are read only from a known runner's summary line, matched from the line's start in its own form (ticket
# 2026-10-20-jui-viz-test-run-ios-shows-failed-while-passing: "(\d+) failed" anywhere counted an agent's echoed
# `passed=36 failed=0` as 36 failed). None matching: no counts — unsure is not said.
_XCODE_EXECUTED = re.compile(r"^\s*Executed (\d+) tests?, with (\d+) failures?(?: \((\d+) unexpected\))?", re.M)
_XCODE_CASE = re.compile(r"^\s*Test [Cc]ase '[^'\n]+' (passed|failed) on '", re.M)   # parallel testing: no Executed line
_XCODE_MARK = re.compile(r"^\*\* TEST (?:BUILD )?(SUCCEEDED|FAILED) \*\*\s*$", re.M)
_GRADLE_COUNTS = re.compile(r"^\s*(\d+) tests completed, (\d+) failed", re.M)
# pytest's last summary: "3 failed, 10 passed in 2.1s", or the same inside "=" rules; passed and failed from that line
_PYTEST_LINE = re.compile(r"^=*\s*((?:\d+ (?:failed|passed|skipped|deselected|xfailed|xpassed|errors?|warnings?|subtests passed)(?:, )?)+) in [\d.]+s\b.*$", re.M)
# Playwright: a line that is only "N passed (1.2m)" or "N failed"
_PLAYWRIGHT_LINE = re.compile(r"^\s+(\d+) (passed|failed)(?: \([^)\n]*\))?\s*$", re.M)
# jest: "Tests:       1 failed, 35 passed, 36 total"
_JEST_LINE = re.compile(r"^Tests:\s+(.*\d+ total)\s*$", re.M)
_GRADLE_OK = re.compile(r"BUILD SUCCESSFUL")


# ---------------------------------------------------------------- which Bash commands run tests

# A command runs tests when one of its simple commands is a test runner — judged by the executable and
# its subcommand, never by a word anywhere in the text: `find ~/.local/state/jsonui-test`, `git grep
# connectedAndroidTest` and a python heredoc that edits tests/… were shown as passing test runs (10-18).
# Anything unsure is not a test: a false "passed" misleads more than a missing one.
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_WRAPPERS = {"time", "nohup", "command", "exec", "caffeinate", "stdbuf", "nice"}
_RUNNERS = {"npx", "bunx", "pnpx"}
_GRADLE_TASK = re.compile(r"^(connected\w*AndroidTest|test\w*UnitTest|test)$")


def _without_heredocs(command: str) -> str:
    """The command with every here-document body removed (its lines are data, not commands)."""
    lines, out, end = command.split("\n"), [], None
    for line in lines:
        if end is not None:
            if line.strip() == end:
                end = None
            continue
        out.append(line)
        m = _HEREDOC.search(line)
        if m:
            end = m.group(2)
    return "\n".join(out)


def simple_commands(command: str) -> list[list[str]]:
    """The command's simple commands as word lists (split at ; & | && || and newlines; heredoc bodies dropped).
    [] when the text cannot be split like a shell would (unbalanced quotes): then it runs nothing we can name."""
    lexer = shlex.shlex(_without_heredocs(command).replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    out, current = [], []
    for token in tokens:
        if token and set(token) <= set(";&|()<>"):
            if current:
                out.append(current)
            current = []
        else:
            current.append(token)
    if current:
        out.append(current)
    return out


def _head(words: list[str]) -> list[str]:
    """The words from the program on: leading VAR=value, `env [-u X] [VAR=value]`, timeout N and the like dropped."""
    i = 0
    while i < len(words):
        word = words[i]
        base = os.path.basename(word)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", word):
            i += 1
        elif base == "env":
            i += 1
            while i < len(words) and (words[i].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[i])):
                i += 2 if words[i] in ("-u", "--unset") else 1
        elif base == "timeout":
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 1
            i += 1  # the duration
        elif base in _WRAPPERS:
            i += 1
        else:
            break
    return words[i:]


def _runs_tests(words: list[str]) -> str | None:
    """The platform a simple command runs tests on ('ios', 'android', 'web', 'unknown'), or None."""
    words = _head(words)
    if not words:
        return None
    exe, args = os.path.basename(words[0]), words[1:]
    if exe in _RUNNERS and args:
        exe, args = os.path.basename(args[0]), args[1:]
    if exe == "xcrun" and args:
        exe, args = os.path.basename(args[0]), args[1:]
    if exe in ("bundle", "pnpm", "yarn") and args[:1] == ["exec"]:
        exe, args = os.path.basename(args[1]) if len(args) > 1 else "", args[2:]
    if exe == "xcodebuild":
        return "ios" if {"test", "test-without-building"} & set(args) else None
    if exe in ("gradlew", "gradle"):
        return "android" if any(_GRADLE_TASK.match(a.rsplit(":", 1)[-1]) for a in args if not a.startswith("-")) else None
    if exe == "playwright":
        return "web" if args[:1] == ["test"] else None
    if exe in ("jest", "vitest"):
        return "web"
    if exe in ("npm", "pnpm", "yarn", "bun"):
        if args[:1] in (["test"], ["t"]) or (args[:1] in (["run"], ["run-script"]) and len(args) > 1 and re.match(r"^test(\b|:)", args[1])):
            return "web"
        return None
    if exe == "pytest" or (re.match(r"^python[0-9.]*$", exe) and args[:2] in (["-m", "pytest"], ["-m", "unittest"])):
        return "unknown"
    if exe in ("swift", "flutter", "go", "cargo", "dotnet") and args[:1] == ["test"]:
        return "unknown"
    if exe in ("rspec",) or (exe in ("rake",) and args[:1] == ["test"]):
        return "unknown"
    return None


def test_platform(command: str) -> str | None:
    """The platform the command runs tests on, or None when it runs no tests (the one rule for the test pane)."""
    for words in simple_commands(command):
        platform = _runs_tests(words)
        if platform is not None:
            return platform
    return None


def drives_a_device(command: str) -> bool:
    """A simple command of adb, or of xcrun simctl (the robot holds a phone; not a test run by itself)."""
    for words in simple_commands(command):
        words = _head(words)
        if not words:
            continue
        exe = os.path.basename(words[0])
        if exe == "adb" or (exe == "xcrun" and words[1:2] == ["simctl"]):
            return True
    return False


# ---------------------------------------------------------------- which Bash commands delete files (10-19)

# Claude Code has no delete tool: a deletion is a Bash command. Judged like test runs (above): per simple command, by
# its program and subcommand, never by a word in the text — `echo rm`, `grep -r rm`, a heredoc that mentions rm and
# `git rm -n` delete nothing. The targets are the arguments as written (a glob before the shell expands it; a folder
# removed with -r is one target, how many files were in it is not known). Not seen: a script that deletes from inside
# (Python's os.remove, a Makefile), and anything the user deletes by hand.
_DELETERS = {"rm", "rmdir", "unlink", "trash", "trash-put"}
STDIN_TARGETS = "（標準入力）"   # what xargs hands a deleter: named nowhere in the command
_RECURSIVE = re.compile(r"^-[A-Za-z]*[rR]")


def _strip_sudo(words: list[str]) -> list[str]:
    """`sudo [-u user] [-E] …`, `command …`, and a leading backslash (`\\rm`) are the same program."""
    words = _head(words)
    while words and os.path.basename(words[0]) in ("sudo", "doas"):
        i = 1
        while i < len(words) and words[i].startswith("-"):
            i += 2 if words[i] in ("-u", "-g", "-h", "-p", "-C", "-U") else 1
        words = _head(words[i:])
    if words and words[0].startswith("\\"):
        words = [words[0][1:], *words[1:]]
    return words


def _options(args: list[str]) -> list[str]:
    """Options before `--` (after it, `-weird` is a file name)."""
    return args[:args.index("--")] if "--" in args else [a for a in args if a.startswith("-")]


def _operands(args: list[str]) -> list[str]:
    """Arguments that are not options (everything after `--`)."""
    out, rest = [], False
    for a in args:
        if rest or not a.startswith("-") or a == "-":
            out.append(a)
        elif a == "--":
            rest = True
    return out


def _deletes(words: list[str]) -> dict | None:
    """{"targets", "folder", "how"} when this simple command deletes, else None."""
    words = _strip_sudo(words)
    if not words:
        return None
    exe, args = os.path.basename(words[0]), words[1:]
    if exe in _DELETERS:
        targets = _operands(args)
        if not targets:
            return None
        folder = exe == "rmdir" or any(t.endswith("/") for t in targets) \
            or any(_RECURSIVE.match(a) or a in ("--recursive", "--dir", "-d") for a in _options(args) if a.startswith("-") and a != "--")
        return {"targets": targets, "folder": folder, "how": exe}
    if exe == "git":
        i = 0
        while i < len(args) and args[i].startswith("-"):   # git's own options: -C <dir>, -c <k=v>, --git-dir=…
            i += 2 if args[i] in ("-C", "-c") else 1
        sub, rest = (args[i], args[i + 1:]) if i < len(args) else ("", [])
        if sub == "rm":
            if {"-n", "--dry-run", "--cached"} & set(rest):
                return None   # deletes nothing (a dry run), or only from the index
            targets = _operands(rest)
            return {"targets": targets, "folder": any(_RECURSIVE.match(a) for a in _options(rest) if a != "--"), "how": "git rm"} if targets else None
        if sub == "worktree" and rest[:1] == ["remove"]:
            targets = _operands(rest[1:])
            return {"targets": targets[:1], "folder": True, "how": "git worktree remove"} if targets else None
        return None
    if exe == "xargs":   # `find … | xargs rm`, `xargs rm < list`: the targets come on stdin, so they have no name here
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in ("-n", "-L", "-I", "-P", "-s", "-E", "-d", "-a") else 1
        # judged with a stand-in operand for what stdin brings (rm and git rm want one); find is no xargs target
        inner = _deletes([*args[i:], STDIN_TARGETS]) if i < len(args) and os.path.basename(args[i]) != "find" else None
        if inner is None:
            return None
        return {"targets": [STDIN_TARGETS], "folder": inner["folder"], "how": f"xargs {inner['how']}"}
    if exe == "find":
        k = next((j for j, a in enumerate(args) if a.startswith("-") or a in ("(", "!")), len(args))
        roots, expr = args[:k] or ["."], args[k:]
        by_exec = any(a in ("-exec", "-execdir") and j + 1 < len(expr) and os.path.basename(expr[j + 1]) in _DELETERS
                      for j, a in enumerate(expr))
        if "-delete" not in expr and not by_exec:
            return None
        names = [expr[j + 1] for j, a in enumerate(expr) if a in ("-name", "-iname", "-path") and j + 1 < len(expr)]
        targets = [f"{r.rstrip('/')}/{n}" for r in roots for n in names] if names else roots
        files_only = any(a == "-type" and j + 1 < len(expr) and expr[j + 1] == "f" for j, a in enumerate(expr))
        return {"targets": targets, "folder": not names and not files_only, "how": "find -delete" if "-delete" in expr else "find -exec rm"}
    return None


def deletions(command: str) -> dict | None:
    """What a Bash command deletes: {"targets": [as written], "folder": bool, "how": the program}, or None."""
    targets, folder, hows = [], False, []
    for words in simple_commands(command):
        d = _deletes(words)
        if d is not None:
            targets += [t for t in d["targets"] if t not in targets]
            folder = folder or d["folder"]
            hows.append(d["how"])
    return {"targets": targets, "folder": folder, "how": hows[0]} if targets else None


def deletion_label(d: dict, n: int = 2) -> str:
    """a.txt、b.txt ほか 3 件 — the names (last path segment) of what was deleted, short."""
    names = [os.path.basename(t.rstrip("/")) or t for t in d["targets"]]
    head = "、".join(names[:n])
    return _clip(f"{head} ほか {len(names) - n} 件" if len(names) > n else head, 60)


_NOTHING_THERE = re.compile(r"No such file or directory|did not match any files|is not a working tree|cannot remove", re.I)


def deletion_failed(output: str) -> bool:
    """The command ran but deleted nothing it was asked to (rm's and git's own words)."""
    return bool(_NOTHING_THERE.search(output or ""))


def xcode_verdict(output: str) -> str | None:
    """xcodebuild's own last word: "failed" for ** TEST FAILED ** (or TEST BUILD FAILED), "passed" for ** TEST SUCCEEDED **,
    None when it said neither. It decides over any count and over the exit code (a redirect can end a failed run with 0)."""
    marks = _XCODE_MARK.findall(output or "")
    return ("failed" if marks[-1] == "FAILED" else "passed") if marks else None


def _counted(output: str) -> tuple[int, int] | None:
    m = list(_XCODE_EXECUTED.finditer(output))
    if m:
        last = m[-1]           # the last summary is the run's total; expected failures (XCTExpectFailure) are no failures
        failed = int(last[3]) if last[3] is not None else int(last[2])
        return int(last[1]) - failed, failed
    cases = _XCODE_CASE.findall(output)
    if cases:
        return cases.count("passed"), cases.count("failed")
    m = list(_GRADLE_COUNTS.finditer(output))
    if m:
        return int(m[-1][1]) - int(m[-1][2]), int(m[-1][2])
    m = list(_PYTEST_LINE.finditer(output))
    if m:
        parts = dict((w, int(n)) for n, w in re.findall(r"(\d+) (failed|passed)\b", m[-1][1]))
        if "passed" in parts or "failed" in parts:
            return parts.get("passed", 0), parts.get("failed", 0)
    m = list(_JEST_LINE.finditer(output))
    if m:
        parts = dict((w, int(n)) for n, w in re.findall(r"(\d+) (failed|passed)\b", m[-1][1]))
        return parts.get("passed", 0), parts.get("failed", 0)
    lines = _PLAYWRIGHT_LINE.findall(output)
    if lines:
        last = {w: int(n) for n, w in lines}
        return last.get("passed", 0), last.get("failed", 0)
    return None


def test_summary(output: str) -> tuple[str, int | None, int | None]:
    """(text, passed, failed) read from a test command's output; unknown counts are None. xcodebuild's ** TEST FAILED **
    makes it failed whatever the counts say; its ** TEST SUCCEEDED ** drops counts that say otherwise."""
    output = output or ""
    verdict, counts = xcode_verdict(output), _counted(output)
    if verdict == "passed" and counts and counts[1] > 0:
        counts = None
    if verdict == "failed" and not (counts and counts[1] > 0):
        return "** TEST FAILED **", counts[0] if counts else None, None
    if counts:
        return f"{counts[0]} passed, {counts[1]} failed", counts[0], counts[1]
    if verdict == "passed":
        return "** TEST SUCCEEDED **", None, 0
    if _GRADLE_OK.search(output):
        return "BUILD SUCCESSFUL", None, 0
    return "", None, None
