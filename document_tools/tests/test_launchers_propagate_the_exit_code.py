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
