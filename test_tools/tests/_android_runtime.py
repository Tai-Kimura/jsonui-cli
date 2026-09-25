"""The emitted Kotlin branch runtime, compiled whole and run on the JVM.

The runtime imports okhttp, mockwebserver, coroutines-test and
serialization, which only a Gradle cache has — no CI image — so the files
that use this are in no CI job; run-suites.sh runs them as their own leg
with JSONUI_REQUIRE_ANDROID_JARS set, and there a missing jar FAILS rather
than skips. The versions are pinned, not the newest found, so a run says
what it compiled against (the leg prints PINNED).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests import _toolchain as tc

CACHE = Path.home() / ".gradle/caches/modules-2/files-2.1"
#: (group/artifact, version) the runtime is compiled and run against.
PINNED = [
    ("com.squareup.okhttp3/okhttp", "4.12.0"),
    ("com.squareup.okhttp3/mockwebserver", "4.12.0"),
    ("com.squareup.okio/okio-jvm", "3.6.0"),
    ("org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm", "1.10.2"),
    ("org.jetbrains.kotlinx/kotlinx-coroutines-test-jvm", "1.10.2"),
    ("org.jetbrains.kotlinx/kotlinx-serialization-core-jvm", "1.9.0"),
    ("org.jetbrains.kotlinx/kotlinx-serialization-json-jvm", "1.9.0"),
    ("junit/junit", "4.13.2"),
    ("org.hamcrest/hamcrest-core", "1.3"),
]


def _missing(why: str) -> None:
    if os.environ.get("CI") or os.environ.get("JSONUI_REQUIRE_ANDROID_JARS"):
        pytest.fail(why)
    pytest.skip(why)


def classpath() -> tuple[str, str]:
    """(compiler classpath, target classpath) — the compiler and its stdlib
    from _toolchain, the rest pinned above."""
    jars = tc.kotlin_jars()
    if jars is None:
        _missing("no Kotlin compiler in the Gradle cache (kotlin-compiler-embeddable)")
    compiler_cp, target_cp = jars
    extra = []
    for artifact, version in PINNED:
        found = sorted(p for p in (CACHE / artifact / version).glob("*/*.jar")
                       if not p.name.endswith("-sources.jar"))
        if not found:
            _missing(f"{artifact}:{version} is not in the Gradle cache")
        extra.append(str(found[0]))
    return compiler_cp, ":".join([target_cp, *extra])


def build(work: Path, runtime: str, probe: str) -> tuple[str, Path]:
    """Compile the runtime template (rendered as the generator renders it:
    `KOTLIN_RUNTIME % {"package": …}`) and *probe*, both in package `probe`."""
    compiler_cp, target_cp = classpath()
    work.mkdir(parents=True, exist_ok=True)
    (work / "Runtime.kt").write_text(runtime % {"package": "probe"}, encoding="utf-8")
    (work / "Probe.kt").write_text(probe, encoding="utf-8")
    out = work / "out"
    done = subprocess.run(
        [str(tc.JAVA), "-cp", compiler_cp, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
         "-no-stdlib", "-cp", target_cp, "-d", str(out), str(work / "Runtime.kt"), str(work / "Probe.kt")],
        capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, f"emitted runtime did not compile:\n{(done.stdout + done.stderr)[-4000:]}"
    return target_cp, out


def run(built: tuple[str, Path], *args: str) -> dict:
    """`probe.ProbeKt` with *args*; its `KEY value` lines as a dict."""
    target_cp, out = built
    done = subprocess.run([str(tc.JAVA), "-cp", f"{out}:{target_cp}", "probe.ProbeKt", *args],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
    return dict(line.split(" ", 1) for line in done.stdout.strip().splitlines() if " " in line)
