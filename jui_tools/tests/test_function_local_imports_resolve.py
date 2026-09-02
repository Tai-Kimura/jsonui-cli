"""Every import written inside a function body must resolve.

A module-level import is checked by importing the module, which every test
does. An import inside a function body is checked by nothing until that
function runs — and `cmd_build` is not called by any test in this suite, so
1.8.6 shipped `from ..core.version import toolchain_version` against a
module that has never existed (the function lives in `jui_cli/version.py`).
Six suites were green; the crash reached every consumer's first `jui build`.

This walks the package instead of the call graph, so it does not depend on
anyone remembering to exercise a command. It resolves the module and looks
up each imported name, which is what the interpreter would do at call time.
"""

from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "jui_cli"
PACKAGE_NAME = "jui_cli"


def _module_name(path: Path) -> str:
    rel = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = [PACKAGE_NAME] + [p for p in rel.parts if p != "__init__"]
    return ".".join(parts)


def _absolute_target(node: ast.ImportFrom, containing_module: str) -> str:
    """Resolve `from ..x import y` the way the interpreter would."""
    if not node.level:
        return node.module or ""
    parts = containing_module.split(".")
    # A relative import counts levels up from the containing PACKAGE, so a
    # module (not a package) spends one level reaching its own directory.
    base = parts[:-node.level] if len(parts) >= node.level else []
    if node.module:
        base = base + node.module.split(".")
    return ".".join(base)


def _function_local_importfroms():
    """(file, lineno, target module, names) for imports nested in a body."""
    found = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module = _module_name(path)
        for parent in ast.walk(tree):
            if not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(parent):
                if isinstance(node, ast.ImportFrom):
                    target = _absolute_target(node, module)
                    if not target.startswith(PACKAGE_NAME):
                        continue  # third-party imports are the environment's problem
                    names = [a.name for a in node.names if a.name != "*"]
                    found.append((path, node.lineno, target, names))
    return found


class FunctionLocalImportsResolve(unittest.TestCase):
    def test_every_function_local_import_resolves(self):
        entries = _function_local_importfroms()

        # An empty scan would pass this test while checking nothing, which is
        # the shape of defect this file exists to catch.
        self.assertGreater(
            len(entries), 0,
            "no function-local imports found — the walk is broken, not the code",
        )

        failures = []
        for path, lineno, target, names in entries:
            try:
                mod = importlib.import_module(target)
            except Exception as exc:  # noqa: BLE001 - report, do not mask
                failures.append(f"{path.name}:{lineno} cannot import {target}: {exc}")
                continue
            for name in names:
                if not hasattr(mod, name):
                    # A submodule is a legitimate `from pkg import mod` target
                    # that has no attribute until it is imported.
                    try:
                        importlib.import_module(f"{target}.{name}")
                    except Exception:
                        failures.append(
                            f"{path.name}:{lineno} {target} has no {name!r}"
                        )

        self.assertEqual(
            [], failures,
            f"{len(failures)} of {len(entries)} function-local import(s) "
            f"do not resolve:\n  " + "\n  ".join(failures),
        )


if __name__ == "__main__":
    unittest.main()
