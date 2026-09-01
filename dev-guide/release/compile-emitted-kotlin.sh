#!/bin/bash
#
# Compile the Kotlin that branch-tests emits, before a release.
#
# Two blockers in one day were emitted Kotlin that did not compile: an
# untyped empty `listOf()` that broke a whole test source set, and a
# collapsed `\"` inside a non-raw Python literal. Both reached consumers
# because the Kotlin emitter is the only one of the three whose output no
# check on this machine ever compiled — `tsc --noEmit` and `swiftc -parse`
# run in the suite, and nothing answers for Kotlin.
#
# This is a RELEASE PROCEDURE, not a CI step and not a shipped feature:
# compiling generated artifacts is something the toolchain must eliminate
# before shipping, not something it offers its consumers. It runs on a
# maintainer's machine, from the Gradle cache that is already there.
#
# WHAT IT DOES NOT COVER — read before quoting a green from it:
# only KOTLIN_RUNTIME is compiled. The per-screen test file and the harness
# skeleton are not, because they pull Robolectric and androidx, which the
# cache here does not carry. One of the two blockers above (the untyped
# `listOf()`) lived in the PER-SCREEN TEST FILE, so this script would not
# have caught it where it actually happened. It closes the escaping class
# and the runtime's own type inference; it is not "Kotlin is compiled".
#
# Red-checked in both historical forms, injected into the runtime:
#   an unescaped `"`      -> 8 errors, exit 1
#   an untyped `listOf()` -> 7 errors, exit 1
#   unmodified            -> exit 0
#
# Exit codes: 0 compiled, 1 did not compile, 2 could not be attempted
# (missing compiler or dependency — say so rather than pass).
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

G="$HOME/.gradle/caches/modules-2/files-2.1"
newest() {  # group artifact -> newest cached jar, or empty
    find "$G/$1/$2" -name "$2-*.jar" 2>/dev/null \
        | grep -v -e sources -e javadoc | sort -V | tail -1
}
need() {
    local jar; jar="$(newest "$1" "$2")"
    if [ -z "$jar" ]; then
        echo "CANNOT ATTEMPT: $1:$2 is not in the Gradle cache" >&2
        echo "  (build an Android consumer once, or add the dependency)" >&2
        exit 2
    fi
    printf '%s' "$jar"
}

# The compiler runs on the JVM and needs its own dependencies on its own
# classpath; the emitted file needs a different set on the target one. They
# are separate, and conflating them is how the first attempt at this failed
# with NoClassDefFoundError inside the compiler rather than a diagnostic
# about the file.
KOTLINC="$(find "$HOME/.gradle/caches" -name 'kotlin-compiler-embeddable-*.jar' 2>/dev/null | sort -V | tail -1)"
[ -n "$KOTLINC" ] || { echo "CANNOT ATTEMPT: no kotlin-compiler-embeddable in the Gradle cache" >&2; exit 2; }
KOTLIN_VERSION="$(basename "$KOTLINC" .jar | sed 's/kotlin-compiler-embeddable-//')"

STDLIB="$(need org.jetbrains.kotlin kotlin-stdlib)"
REFLECT="$(need org.jetbrains.kotlin kotlin-reflect)"
ANNOTATIONS="$(need org.jetbrains annotations)"
COROUTINES="$(need org.jetbrains.kotlinx kotlinx-coroutines-core-jvm)"
TROVE="$(newest org.jetbrains.intellij.deps trove4j)"

COMPILER_CP="$KOTLINC:$STDLIB:$REFLECT:$COROUTINES:$ANNOTATIONS${TROVE:+:$TROVE}"

TARGET_CP="$STDLIB:$REFLECT:$ANNOTATIONS:$COROUTINES"
for pair in \
    "org.jetbrains.kotlinx kotlinx-coroutines-test-jvm" \
    "org.jetbrains.kotlinx kotlinx-serialization-json-jvm" \
    "org.jetbrains.kotlinx kotlinx-serialization-core-jvm" \
    "com.squareup.okhttp3 mockwebserver" \
    "com.squareup.okhttp3 okhttp" \
    "com.squareup.okio okio-jvm" \
    "junit junit" \
    "org.hamcrest hamcrest-core" ; do
    TARGET_CP="$TARGET_CP:$(need $pair)"
done

JAVA_HOME_21="$(/usr/libexec/java_home -v 21 2>/dev/null || /usr/libexec/java_home -v 17 2>/dev/null)"
[ -n "$JAVA_HOME_21" ] || { echo "CANNOT ATTEMPT: no JDK 17+ found" >&2; exit 2; }

PYTHONPATH="$REPO/test_tools" python3 - "$WORK" <<'PY'
import sys
from jsonui_test_cli.branch_tests import KOTLIN_RUNTIME
out = sys.argv[1] + "/JsonuiBranchRuntime.kt"
open(out, "w").write(KOTLIN_RUNTIME % {"package": "release.probe"})
PY
[ -s "$WORK/JsonuiBranchRuntime.kt" ] || { echo "CANNOT ATTEMPT: the runtime did not render" >&2; exit 2; }

# -jvm-target is not optional. Without it the backend crashes on a JDK 21
# default rather than reporting anything about the file, which reads as
# "the emitted Kotlin is broken" when it is not.
"$JAVA_HOME_21/bin/java" -cp "$COMPILER_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
    -no-stdlib -jvm-target 17 -classpath "$TARGET_CP" \
    -d "$WORK/out" "$WORK/JsonuiBranchRuntime.kt" > "$WORK/log" 2>&1
status=$?

grep -v '^warning: unable to find' "$WORK/log"
if [ "$status" -eq 0 ]; then
    echo "OK: emitted Kotlin compiles (kotlinc $KOTLIN_VERSION, jvm-target 17)"
    exit 0
fi
echo "FAILED: the emitted Kotlin does not compile (kotlinc $KOTLIN_VERSION)" >&2
exit 1
