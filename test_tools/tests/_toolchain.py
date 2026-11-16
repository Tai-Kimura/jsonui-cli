"""Is the compiler here, did it answer, and did the arm actually run.

Four files compile what the generator emits and run it, because whether
emitted code COMPILES and what it DOES are facts about execution that a
string assertion cannot see. Each of them had its own copy of "find a
toolchain", and the copies disagreed in ways that made arms quieter:

- `skipif(shutil.which("swiftc") is None)` on a suite whose CI runner is
  ubuntu turns a whole face into a silent subtraction. Measured on one
  green run: 9 arms across 3 files skipped, and the summary said
  "1636 passed, 9 skipped" — which reads the same as a healthy suite to
  anyone counting failures.
- `skipif(_kotlin_jars() is None)` ties the Android face to a populated
  Gradle cache, which no CI image has. The arms then run ONLY on a
  developer machine, which is the environment least able to notice.
- `[l for l in build.stderr.splitlines() if "error:" in l]` reads a word,
  not the exit code. This JVM reports in Japanese (`エラー:`), so a
  compiler that failed to START read as a clean build and the arm went on
  to measure nothing.

So: one source for the decision, and the decision itself is the policy
`test_emitted_typescript_compiles.py` already set — in CI a missing tool is
a FAILURE, because a skipped gate gates nothing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path

import pytest

JAVA = Path("/opt/homebrew/opt/openjdk@17/bin/java")

#: `StateFlow` and the kotlinx JSON types appear in extracted declarations
#: and are never exercised as themselves. Shimmed so a probe needs nothing
#: but `kotlinc`: requiring the real libraries is what tied these arms to a
#: Gradle cache, and a cache is not something CI has.
KOTLIN_SHIM = """
interface StateFlow<out T> { val value: T }

class JsonElement(private val raw: String) {
  override fun toString(): String = raw
}

object Json {
  fun parseToJsonElement(text: String): JsonElement = JsonElement(text)
}
"""


def tool(name: str) -> str:
    """The tool, or a decision about its absence.

    In CI this FAILS: a skipped gate gates nothing and disappears into a
    green summary. Locally it skips, so the gap lands in the skipped count
    instead of passing silently.

    CALL IT FROM INSIDE THE TEST. A `skipif` decorator cannot fail, only
    skip — which is the outcome this exists to refuse.
    """
    found = shutil.which(name)
    if found:
        return found
    if os.environ.get("CI"):
        pytest.fail(
            f"{name} is not installed and this is CI. The arm that needs it "
            "would go unmeasured, and the job that owns these arms is the "
            "one with the compilers")
    pytest.skip(f"{name} not installed — this face is UNMEASURED here")


@lru_cache(maxsize=1)
def kotlin_jars() -> tuple[str, str] | None:
    """(compiler_cp, target_cp) from the Gradle cache — the LOCAL path.

    A developer machine has the cache and usually not `kotlinc`; the CI job
    that owns these arms installs `kotlinc` and has no cache. Both routes
    exist so that neither environment skips.

    CACHED, and the globs are bounded. `**` over the cache measured at
    147.6s per call and was evaluated at import time by `skipif`; six
    bounded globs still cost 59.7s, because the cost is the walk and there
    were six. One listing plus `fnmatch` is 8.6s.

    Versions matched on purpose: a 2.2 compiler against a 2.4 stdlib fails
    with "incompatible classes were found in dependencies", which reads
    like a defect in the emitted code and is not one.
    """
    cache = Path.home() / ".gradle/caches"
    if not JAVA.exists() or not cache.exists():
        return None

    all_jars = sorted([*cache.glob("modules-2/files-2.1/*/*/*/*/*.jar"),
                       *cache.glob("*/transforms/*/transformed/*.jar")])

    def jars(pattern: str) -> list[Path]:
        return [j for j in all_jars if fnmatch(j.name, pattern)]

    compilers = [c for c in jars("kotlin-compiler-embeddable-*.jar")
                 if "sources" not in c.name]
    for compiler in reversed(compilers):
        version = compiler.name[len("kotlin-compiler-embeddable-"):-len(".jar")]
        std = jars(f"kotlin-stdlib-{version}.jar")
        ref = jars(f"kotlin-reflect-{version}.jar")
        cor = jars("kotlinx-coroutines-core-jvm-*.jar")
        if not (std and ref and cor):
            continue
        # THE COMPILER'S OWN CLASSPATH IS NOT THE TARGET'S. The embeddable
        # compiler runs on the stdlib and on coroutines; handed only its own
        # jar it dies before reading a line of Kotlin (`KMappedMarker`, then
        # `CoroutineScope`), and neither message is a fact about the source
        # under test.
        extra = [str(p) for p in jars("annotations-13.0.jar")[:1]]
        extra += [str(p) for p in jars("trove4j-*.jar")[:1]]
        target = ":".join([str(std[-1]), str(ref[-1])])
        compiler_cp = ":".join(
            [str(compiler), str(std[-1]), str(ref[-1]), str(cor[-1])] + extra)
        return compiler_cp, target
    return None


def compile_and_run_kotlin(tmp_path: Path, source: str,
                           main: str = "ProbeKt") -> subprocess.CompletedProcess:
    """Compile `source` and run `main`, by whichever route this machine has.

    `source` must be self-contained — use `KOTLIN_SHIM` for the kotlinx
    names the emitted declarations mention.
    """
    probe = tmp_path / "probe.kt"
    probe.write_text(source, encoding="utf-8")
    out = tmp_path / "out"
    kotlinc, kotlin = shutil.which("kotlinc"), shutil.which("kotlin")
    jars = kotlin_jars()

    if kotlinc and kotlin:
        _assert_compiled(subprocess.run(
            [kotlinc, str(probe), "-d", str(out)],
            capture_output=True, text=True, timeout=900))
        return subprocess.run([kotlin, "-classpath", str(out), main],
                              capture_output=True, text=True, timeout=180)
    if jars:
        compiler_cp, target_cp = jars
        _assert_compiled(subprocess.run(
            [str(JAVA), "-cp", compiler_cp,
             "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
             "-no-stdlib", "-cp", target_cp, "-d", str(out), str(probe)],
            capture_output=True, text=True, timeout=900))
        return subprocess.run([str(JAVA), "-cp", f"{out}:{target_cp}", main],
                              capture_output=True, text=True, timeout=180)

    # NAME WHAT IS ACTUALLY MISSING. `tool("kotlinc")` RETURNS on a machine
    # that has the compiler but not the runner, and the caller would then
    # raise a message about this function instead of about the toolchain.
    tool("kotlinc" if not kotlinc else "kotlin")
    raise AssertionError("unreachable")  # pragma: no cover


def _assert_compiled(build: subprocess.CompletedProcess) -> None:
    """THE EXIT CODE, not a grep for "error:".

    A word filter is a filter on the compiler's LANGUAGE. This JVM reports
    in Japanese (`エラー:`), so a compiler that failed to start read as a
    clean build — a failure wearing the face of success, after which the
    arm measures nothing and says so in no way.
    """
    assert build.returncode == 0, (
        f"Kotlin did not compile (rc={build.returncode}):\n"
        f"{(build.stdout + build.stderr)[-4000:]}")
