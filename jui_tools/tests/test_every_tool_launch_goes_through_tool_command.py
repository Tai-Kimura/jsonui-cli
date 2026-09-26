"""Every place that starts sjui / kjui / rjui picks the tool's ruby one way.

From jsonui-cli 1.9.0 the tools stop below Ruby 3.2, and the ruby a start
gets is decided by how it is started. jui's rule: every start goes through
tool_resolver.tool_command, which resolves the tool and applies its
.ruby-version (build_tool_env). `jui init` did not until 1.9.0 — it ran the
bare name with the parent's env — so a new project's tools ran on rbenv's
global, the system Ruby 2.6 on a Mac where none was set. The tools' own
restarts use RbConfig.ruby, the interpreter that already passed the floor;
kjui's `g` restarted `ruby` from PATH until 1.9.0.

The launch sites are COUNTED, not listed: every process start in the three
Python packages (subprocess.*, os.system / exec* / spawn* / popen,
asyncio.create_subprocess_*, pty.spawn — under any import alias). A site can
start a tool when its argv starts with a tool's name or with anything that
is not a literal (a variable could hold a tool). Such a site passes only if
its argv AND its env are the two values tool_command returned in the same
function; the rest must be named below with the reason they never start a
tool, and that list must match the scan both ways.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES = ("jui_tools/jui_cli", "test_tools/jsonui_test_cli", "document_tools/jsonui_doc_cli")
TOOLS = {"sjui", "kjui", "rjui"}

LAUNCH_FUNCS = {
    "subprocess": {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"},
    "os": {"system", "popen", "execv", "execve", "execvp", "execvpe", "execl", "execle", "execlp", "execlpe",
           "spawnv", "spawnve", "spawnvp", "spawnvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe",
           "posix_spawn", "posix_spawnp"},
    "asyncio": {"create_subprocess_exec", "create_subprocess_shell"},
    "pty": {"spawn"},
}

#: Sites whose argv is not a literal yet never start a platform tool, and why.
#: Keyed by (file, enclosing function, argv as written).
NOT_A_TOOL = {
    ("jui_tools/jui_cli/conformance/codegen_effect.py", "run_probe", "[ruby, script, str(jobs_path), str(out_path)]"):
        "the codegen differential's probe script inside a tool directory (PROBES), not bin/<tool>; maintainer-side",
    ("test_tools/jsonui_test_cli/artifacts.py", "_run", "cmd"):
        "the artifacts seam: its callers pass xcrun xcresulttool / adb argv built in this module",
    ("test_tools/jsonui_test_cli/cli.py", "_pregrant_ios", "cmd"):
        "xcrun simctl privacy — the argv is the literal list built on the line above",
    ("test_tools/jsonui_test_cli/cli.py", "_pregrant_android", "[adb, 'devices']"):
        "adb, located by find_adb",
    ("test_tools/jsonui_test_cli/cli.py", "_pregrant_android", "[adb, '-s', serial, 'shell', 'dumpsys', 'package', app_id]"):
        "adb, located by find_adb",
    ("test_tools/jsonui_test_cli/cli.py", "_pregrant_android", "[adb, '-s', serial, 'shell', 'pm', 'revoke', app_id, permission]"):
        "adb, located by find_adb",
    ("test_tools/jsonui_test_cli/mock/server.py", "_run", "command"):
        "the mock server's run target: a shell command the project wrote in its mock config",
    ("document_tools/jsonui_doc_cli/check/runner.py", "run_subprocess", "argv"):
        "jsonui-doc check's configured commands: an interpreter from _ALLOWED_INTERPRETERS and the project's script",
}

#: The launches that must be found and must conform — the scan's positive side.
KNOWN_TOOL_STARTS = {
    ("jui_tools/jui_cli/commands/build_cmd.py", "_run_tool"),
    ("jui_tools/jui_cli/commands/generate_cmd.py", "_run_converter_direct"),
    ("jui_tools/jui_cli/commands/init_cmd.py", "_run_tool"),
}


def _aliases(tree: ast.Module) -> tuple[dict, dict]:
    """(module alias -> module, bare function name -> (module, function))."""
    modules, functions = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in LAUNCH_FUNCS:
                    modules[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom) and node.module in LAUNCH_FUNCS:
            for a in node.names:
                if a.name in LAUNCH_FUNCS[node.module]:
                    functions[a.asname or a.name] = (node.module, a.name)
    return modules, functions


def _launch_sites(path: Path, source: str) -> list[dict]:
    tree = ast.parse(source, str(path))
    modules, functions = _aliases(tree)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn, launch = node.func, None
        if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id in modules:
            if fn.attr in LAUNCH_FUNCS[modules[fn.value.id]]:
                launch = f"{modules[fn.value.id]}.{fn.attr}"
        elif isinstance(fn, ast.Name) and fn.id in functions:
            launch = ".".join(functions[fn.id])
        if not launch:
            continue
        func, up = None, node
        while up in parents:
            up = parents[up]
            if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = up
                break
        argv = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "args"), None)
        env = next((k.value for k in node.keywords if k.arg == "env"), None)
        first = argv.elts[0] if isinstance(argv, (ast.List, ast.Tuple)) and argv.elts else None
        literal = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
        if literal is None and isinstance(argv, ast.Constant) and isinstance(argv.value, str):
            literal = argv.value.split()[0] if argv.value.split() else ""
        sites.append({"file": str(path.relative_to(REPO)), "line": node.lineno, "launch": launch,
                      "function": func.name if func else "<module>", "func_node": func,
                      "argv": ast.unparse(argv) if argv is not None else "?",
                      "argv_node": argv, "env_node": env, "literal": literal})
    return sites


def _from_tool_command(site: dict) -> bool:
    """argv and env are both names bound, in this function, from tool_command()."""
    func = site["func_node"]
    if func is None or not isinstance(site["argv_node"], ast.Name) or not isinstance(site["env_node"], ast.Name):
        return False
    bound = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            callee = node.value.func
            name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", None)
            if name == "tool_command":
                for target in node.targets:
                    elts = target.elts if isinstance(target, ast.Tuple) else [target]
                    bound |= {e.id for e in elts if isinstance(e, ast.Name)}
    return {site["argv_node"].id, site["env_node"].id} <= bound


def _scan() -> list[dict]:
    sites = []
    for package in PACKAGES:
        for path in sorted((REPO / package).rglob("*.py")):
            sites += _launch_sites(path, path.read_text(encoding="utf-8"))
    return sites


def _may_start_a_tool(site: dict) -> bool:
    literal = site["literal"]
    if literal is None:
        return True
    return Path(literal).name in TOOLS


def test_the_scan_sees_every_spelling_of_a_process_start():
    # The counter's own control: each spelling below is one start.
    probe = REPO / "jui_tools" / "jui_cli" / "_probe.py"
    source = "\n".join([
        "import subprocess as sp",
        "from subprocess import Popen as P",
        "import os, asyncio",
        "def a(c):",
        "    sp.run(c)",
        "    P(['sjui', 'build'])",
        "    os.system('kjui build')",
        "    os.execvp('rjui', ['rjui'])",
        "    asyncio.create_subprocess_exec('git')",
        "    sp.run(['git', 'status'])",
    ])
    sites = _launch_sites(probe, source)
    assert [s["launch"] for s in sites] == ["subprocess.run", "subprocess.Popen", "os.system", "os.execvp",
                                            "asyncio.create_subprocess_exec", "subprocess.run"], sites
    assert [_may_start_a_tool(s) for s in sites] == [True, True, True, True, False, False], sites


def test_every_start_that_can_be_a_tool_goes_through_tool_command():
    sites = _scan()
    table = "\n".join(f"  {s['file']}:{s['line']} {s['function']} {s['launch']}({s['argv']})" for s in sites)
    capable = [s for s in sites if _may_start_a_tool(s)]
    through = {(s["file"], s["function"]) for s in capable if _from_tool_command(s)}
    bypass = {(s["file"], s["function"], s["argv"]) for s in capable if not _from_tool_command(s)}
    assert KNOWN_TOOL_STARTS <= through, (
        f"a known tool start was not found going through tool_command: {sorted(KNOWN_TOOL_STARTS - through)}\n"
        f"every start ({len(sites)}):\n{table}")
    unexplained = sorted(bypass - set(NOT_A_TOOL))
    stale = sorted(set(NOT_A_TOOL) - bypass)
    assert not unexplained and not stale, (
        f"can start a tool and does not go through tool_command: {unexplained}\n"
        f"named here but no longer a bypassing start (drop the line): {stale}\n"
        f"every start ({len(sites)}):\n{table}")


# `ruby` named from PATH in the tools' own code: a launch that picks its ruby by
# PATH instead of the one already running (RbConfig.ruby).
RUBY_BY_NAME = re.compile(
    r"""(\b(system|spawn|exec|popen\w*|capture\w*|pipeline\w*)\s*\(?\s*(\[\s*)?["']ruby\b"""
    r"""|`ruby\b|%x[\(\[{]\s*ruby\b)""")


def _ruby_by_name(text: str) -> list[int]:
    return [i for i, line in enumerate(text.splitlines(), 1)
            if not line.lstrip().startswith("#") and RUBY_BY_NAME.search(line)]


def test_the_ruby_scan_sees_the_spellings_it_forbids():
    lines = [
        'system("ruby #{bin} build")',
        "Open3.capture2e('ruby', bin, 'build')",
        "IO.popen(['ruby', bin])",
        "`ruby -v`",
        "spawn(RbConfig.ruby, bin, 'build')",
        "system(RbConfig.ruby, bin, 'build')",
        "# system(\"ruby old\")",
    ]
    assert _ruby_by_name("\n".join(lines)) == [1, 2, 3, 4]


def test_the_tools_restart_themselves_on_their_own_ruby():
    found = []
    for tool in sorted(TOOLS):
        for sub in ("lib", "bin"):
            for path in sorted((REPO / f"{tool}_tools" / sub).rglob("*")):
                if path.is_file() and (path.suffix == ".rb" or sub == "bin"):
                    for line in _ruby_by_name(path.read_text(encoding="utf-8", errors="replace")):
                        found.append(f"{path.relative_to(REPO)}:{line}")
    assert not found, f"starts `ruby` from PATH rather than RbConfig.ruby: {found}"
