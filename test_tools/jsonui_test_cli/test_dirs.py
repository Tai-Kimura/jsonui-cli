"""Where a project's `.test.json` files live, and which of them a driver's `file` names.

The one copy of these rules. `jsonui-test` uses them for the set of declared
test files (the install clean's denominator); `jui viz` loads this file by path
from the same distribution (jui_cli/viz/sources/jsonui_project.py) to count a
spec's tests and to tie a run's results to a test file. Nothing here imports
anything beyond the standard library, so it can be loaded by path from a tool
tree that has no `jsonui_test_cli` package installed.

The test root is `test.testDir` from jui.config.json (default `tests`),
relative to the folder of that config, read recursively: test files sit in
sub-folders per screen (`tests/screens/<screen>/*.test.json`) in real
projects. A project whose tests live elsewhere declares `testDir` (it may
point outside the app's folder, e.g. `../tests/user`).

A driver names a test file differently on each platform (measured 2026-10-18):
iOS the bundled file name only (`login_smoke.test.json`), Android
`tests/login_smoke.test.json`, Web the path from the process's working folder
(`../tests/user/screens/login_smoke.test.json`). `match_test_file` resolves
any of them to the one test file whose path ends with the most of the same
segments — and to nothing when two files tie, rather than guess.
"""
from __future__ import annotations

from pathlib import Path

TEST_DIR_KEY = "testDir"
TEST_DIR_DEFAULT = "tests"
SUFFIX = ".test.json"


def test_root(test_config: dict, project_root: Path) -> Path:
    """The declared test folder: `test.testDir` (default `tests`), relative to *project_root*."""
    value = test_config.get(TEST_DIR_KEY) if isinstance(test_config, dict) else None
    root = Path(value if isinstance(value, str) and value else TEST_DIR_DEFAULT)
    return root if root.is_absolute() else Path(project_root) / root


def test_files(root: Path) -> list[Path]:
    """Every `*.test.json` under *root*, recursively, sorted; [] when *root* is not a folder."""
    root = Path(root)
    return sorted(root.rglob("*" + SUFFIX)) if root.is_dir() else []


def declared_test_files(test_config: dict, project_root: Path) -> set[Path] | None:
    """Every test file under the declared test folder (resolved), or None when the folder is not there.

    None is a different answer from an empty set: the folder could not be looked at."""
    root = test_root(test_config, project_root)
    if not root.is_dir():
        return None
    return {p.resolve() for p in test_files(root)}


def segments(name: str) -> list[str]:
    """A driver's `file` (or a test file's path under its root) as path segments, without `.`, `..` and empties."""
    return [s for s in str(name).replace("\\", "/").split("/") if s not in ("", ".", "..")]


def match_test_file(name: str, keys) -> str | None:
    """The key (a test file's path under its root, '/'-separated) *name* names, or None.

    The key whose trailing segments agree with *name*'s for the longest run wins;
    at least the file name must agree. Two keys with the same longest run: None."""
    wanted = segments(name)
    if not wanted or not wanted[-1].endswith(SUFFIX):
        return None
    best, found = 0, []
    for key in keys:
        have = segments(key)
        n = 0
        while n < min(len(have), len(wanted)) and have[-1 - n] == wanted[-1 - n]:
            n += 1
        if n == 0:
            continue
        if n > best:
            best, found = n, [key]
        elif n == best:
            found.append(key)
    return found[0] if len(found) == 1 else None
