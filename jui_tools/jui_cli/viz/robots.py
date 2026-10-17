"""Hook event → a robot's state and its one-line ``act``. Design: 04 §3.

States match the page's STATES (robot-core.js): idle, typing, reading,
command, phone, waiting, carry, done.
"""
from __future__ import annotations

import os
import re

TYPING_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
READING_TOOLS = {"Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "ToolSearch"}
COMMAND_TOOLS = {"Bash", "BashOutput"}
READING_MCP = re.compile(r"^mcp__jui-tools__(read_|lookup_|list_|search_|get_)")
COMMAND_MCP = re.compile(r"^mcp__jui-tools__(jui_build|jui_verify|doc_|test_)")
PHONE_COMMAND = re.compile(
    r"xcodebuild\s+test|connectedAndroidTest|connected\w*AndroidTest|playwright\s+test|jsonui-test|xcrun\s+simctl|(^|[\s;&|(])adb(\s|$)"
)

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
        return "phone" if PHONE_COMMAND.search(command) else "command"
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


def test_platform(command: str) -> str:
    if "xcodebuild" in command or "simctl" in command:
        return "ios"
    if "gradlew" in command or re.search(r"(^|[\s;&|(])adb(\s|$)", command):
        return "android"
    if "playwright" in command or "jest" in command:
        return "web"
    return "unknown"


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
