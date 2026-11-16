"""dev-guide/release/compile-emitted-kotlin.sh compiles with the versions CI pins.

Until 1.9.10 the release gate took the newest compiler in the Gradle cache
(`find ~/.gradle/caches … | sort -V | tail -1`): 2.4.20 on the release
machine where CI pins 2.1.0 (ticket kjui-spec-kotlinc-harness-globs-the-
whole-gradle-cache-and-picks-the-newest-compiler). It now reads the pins from
.github/scripts/fetch_kotlin_compiler_jars.sh and takes that exact version;
without it the gate fails (exit 2) rather than falling back.

The arms run the script over a temporary GRADLE_USER_HOME of empty jars: it
prints the jars it took (its target libraries are pinned in the same list)
before it reaches a JVM, and an empty jar then
fails the compile — what is read is the printed line.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "dev-guide" / "release" / "compile-emitted-kotlin.sh"
FETCH = REPO / ".github" / "scripts" / "fetch_kotlin_compiler_jars.sh"

def pins(script: Path = FETCH) -> list[tuple[str, str, str]]:
    return re.findall(r'^\s+"(\S+) (\S+) (\S+) [0-9a-f]{64}"$', script.read_text(), re.M)


def place(home: Path, group: str, artifact: str, version: str) -> None:
    d = home / "caches" / "modules-2" / "files-2.1" / group / artifact / version / "f00d"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{artifact}-{version}.jar").write_bytes(b"")


def run_gate(home: Path, pins_file: Path | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "GRADLE_USER_HOME": str(home)}
    if pins_file:
        env["JSONUI_KOTLIN_PINS"] = str(pins_file)
    return subprocess.run(["bash", str(GATE)], capture_output=True, text=True, env=env, timeout=120)


class ReleaseKotlinGateTakesThePinnedCompiler(unittest.TestCase):
    def full_cache(self, home: Path, compiler_versions: list[str]) -> None:
        for group, artifact, version in pins():
            if artifact != "kotlin-compiler-embeddable":
                place(home, group, artifact, version)
        for version in compiler_versions:
            place(home, "org.jetbrains.kotlin", "kotlin-compiler-embeddable", version)

    def compiler_line(self, r: subprocess.CompletedProcess) -> str:
        line = next((l for l in r.stdout.splitlines() if l.startswith("kotlin-compiler-embeddable ")), "")
        self.assertTrue(line, f"no compiler line\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        return line

    def test_takes_the_pinned_compiler_beside_a_newer_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.full_cache(home, ["2.4.20", "2.1.0"])
            line = self.compiler_line(run_gate(home))
            self.assertTrue(line.startswith("kotlin-compiler-embeddable 2.1.0 (pinned): "), line)
            self.assertTrue(line.endswith("kotlin-compiler-embeddable-2.1.0.jar"), line)

    def test_takes_1_10_when_1_10_is_pinned_and_1_9_is_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.full_cache(home, ["1.9", "1.10"])
            pins_file = home / "pins.sh"
            text = FETCH.read_text()
            pins_file.write_text(re.sub(r"(kotlin-compiler-embeddable )\S+", r"\g<1>1.10", text, count=1))
            line = self.compiler_line(run_gate(home, pins_file))
            self.assertTrue(line.endswith("kotlin-compiler-embeddable-1.10.jar"), line)

    def test_fails_without_the_pinned_compiler_and_says_how_to_fetch_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.full_cache(home, ["2.4.20"])
            r = run_gate(home)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("kotlin-compiler-embeddable:2.1.0 (pinned) is not in the Gradle cache", r.stderr)
            self.assertIn("fetch_kotlin_compiler_jars.sh", r.stderr)


if __name__ == "__main__":
    unittest.main()
