"""Every distributed launcher exits with what `main()` returned.

One of three ended with a bare `main()`, so a check that printed
`✗ MISMATCH` still exited 0 and gated nothing. Measured through both
routes against the same input: the distributed launcher exited 0 and the
pip-installed console script exited 1, with byte-identical output.

CI never saw it because `[project.scripts]` wraps `main` in `sys.exit(...)`
for whoever installs the package, and CI installs. The launcher's own
docstring already said a green CI says nothing about whether the
distributed copy works — the scope was named, and the one line inside that
scope was still wrong. Naming a gap is not checking inside it.

THE DENOMINATOR IS PART OF THE TEST. A sweep for this ran with
`-maxdepth 2` and found two launchers, missing `jui_tools/bin/jui` at
depth three; it happened to be the correct one, so the conclusion held and
the count was wrong. So the set is defined here by what a launcher IS
rather than by where it sits, and the definition is checked for finding
anything at all before anything is asserted about the members.
"""
from __future__ import annotations

import os
import re
import stat
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Directories that hold other people's executables, or build output.
SKIP = {".git", "node_modules", "build", "dist", "__pycache__", ".venv",
        "venv", "coverage", ".pytest_cache", "vendor", "Pods"}


def _launchers() -> list[Path]:
    """Executable, extensionless, python shebang. No depth limit."""
    found = []
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix:
                continue
            try:
                if not path.stat().st_mode & stat.S_IXUSR:
                    continue
                head = path.open("rb").readline(200)
            except OSError:
                continue
            if head.startswith(b"#!") and b"python" in head:
                found.append(path)
    return sorted(found)


def _entry_point(launcher: Path) -> str:
    """The `module:main` the launcher itself calls."""
    body = launcher.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"from ([\w.]+) import main", body)
    return f"{match.group(1)}:main" if match else ""


def _declared_console_scripts(package: Path) -> dict:
    """The console scripts a package declares, however it declares them.

    Two spellings are in use here, and checking only one is the mistake
    this file already made once with directory depth: `[project.scripts]`
    in pyproject.toml covers two of the packages, and the third declares
    `entry_points={"console_scripts": [...]}` in setup.py. An arm looking
    only for the first reports the third as undeclared, which is false.
    """
    pyproject = package / "pyproject.toml"
    if pyproject.exists():
        import tomllib

        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
        return (data.get("project") or {}).get("scripts") or {}
    setup = package / "setup.py"
    if setup.exists():
        text = setup.read_text(encoding="utf-8", errors="replace")
        return dict(re.findall(r'"([\w.-]+)\s*=\s*([\w.:]+)"', text))
    return {}


def _package_of(launcher: Path) -> Path:
    for candidate in (launcher.parent, launcher.parent.parent):
        if (candidate / "pyproject.toml").exists() or \
                (candidate / "setup.py").exists():
            return candidate
    return launcher.parent


class ConsoleScriptRouteTests(unittest.TestCase):
    """The other route exists and runs the same entry point.

    There are two ways to invoke each of these, and the defect above lived
    in exactly the gap between them: CI installs the package and gets a
    console script that pip wraps in `sys.exit(...)`, so CI was green while
    the distributed launcher gated nothing. A regression arm on one route
    only would sit on whichever route its author happens to use.

    WHAT THIS DOES NOT CHECK: the generated console script itself. It is
    produced by pip at install time and is not in the tree, so what is
    checked is the declaration that makes pip produce it — and that both
    routes name the same `module:main`, so they cannot drift into running
    different code. Saying that here because the defect above was a scope
    that had been named and never checked inside; repeating the shape in
    the arm that fixes it would be the same mistake one level up.
    """

    def setUp(self):
        self.launchers = _launchers()
        self.assertTrue(self.launchers, "no launchers found to check")

    def test_each_launcher_has_a_console_script_declared(self):
        for launcher in self.launchers:
            rel = launcher.relative_to(REPO).as_posix()
            with self.subTest(launcher=rel):
                declared = _declared_console_scripts(_package_of(launcher))
                self.assertIn(
                    launcher.name, declared,
                    f"{rel} has no console script, so the only way to run "
                    f"it is this launcher — and its exit-code handling is "
                    f"then the only one anybody gets",
                )

    def test_both_routes_run_the_same_entry_point(self):
        for launcher in self.launchers:
            rel = launcher.relative_to(REPO).as_posix()
            with self.subTest(launcher=rel):
                declared = _declared_console_scripts(_package_of(launcher))
                self.assertEqual(
                    _entry_point(launcher), declared.get(launcher.name),
                    f"{rel} and its console script call different code, so "
                    f"a check passing through one says nothing about the "
                    f"other",
                )


class LauncherExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.launchers = _launchers()

    def test_the_sweep_finds_launchers_at_all(self):
        # The check the maxdepth sweep did not have. An empty set makes
        # every assertion below vacuously true, and the output of that is
        # a pass.
        self.assertGreaterEqual(len(self.launchers), 3, self.launchers)

    def test_the_sweep_reaches_past_the_shallow_ones(self):
        # `jui_tools/bin/jui` sits one level deeper than the other two and
        # is exactly what a depth-limited sweep drops.
        names = {p.relative_to(REPO).as_posix() for p in self.launchers}
        self.assertIn("jui_tools/bin/jui", names)
        self.assertIn("document_tools/jsonui-doc", names)
        self.assertIn("test_tools/jsonui-test", names)

    def test_every_launcher_propagates_the_exit_code(self):
        for path in self.launchers:
            with self.subTest(launcher=path.relative_to(REPO).as_posix()):
                body = path.read_text(encoding="utf-8", errors="replace")
                last = [l.strip() for l in body.splitlines() if l.strip()][-1]
                self.assertIn(
                    "sys.exit(", last,
                    f"{path.relative_to(REPO)} ends with {last!r}; a "
                    f"non-zero return from main() is discarded, so the "
                    f"command prints its failure and exits 0",
                )


if __name__ == "__main__":
    unittest.main()
