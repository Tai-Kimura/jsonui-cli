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
COMMAND_TOOLS = {"Bash", "BashOutput"}
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

_SUMMARY_PATTERNS = (
    # xcodebuild: "Executed 12 tests, with 1 failure (0 unexpected)"
    (re.compile(r"Executed (\d+) tests?, with (\d+) failures?"), lambda m: (int(m[1]) - int(m[2]), int(m[2]))),
    # Gradle: "12 tests completed, 1 failed"
    (re.compile(r"(\d+) tests completed, (\d+) failed"), lambda m: (int(m[1]) - int(m[2]), int(m[2]))),
)
_PLAYWRIGHT_PASSED = re.compile(r"(\d+) passed")
_PLAYWRIGHT_FAILED = re.compile(r"(\d+) failed")
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


def test_summary(output: str) -> tuple[str, int | None, int | None]:
    """(text, passed, failed) read from a test command's output; unknown counts are None."""
    for pattern, counts in _SUMMARY_PATTERNS:
        matches = list(pattern.finditer(output))
        if matches:
            passed, failed = counts(matches[-1])  # the last summary is the run's total
            return f"{passed} passed, {failed} failed", passed, failed
    p = _PLAYWRIGHT_PASSED.findall(output)
    f = _PLAYWRIGHT_FAILED.findall(output)
    if p or f:
        passed = int(p[-1]) if p else 0
        failed = int(f[-1]) if f else 0
        return f"{passed} passed, {failed} failed", passed, failed
    if _GRADLE_OK.search(output):
        return "BUILD SUCCESSFUL", None, 0
    return "", None, None
