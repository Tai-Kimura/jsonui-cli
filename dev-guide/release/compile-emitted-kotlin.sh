#!/bin/bash
#
# Compile the Kotlin that branch-tests emits, before a release.
#
# Two blockers in one day were emitted Kotlin that did not compile: an
# untyped empty `listOf()` that broke a whole test source set, and a
# collapsed `\"` inside a non-raw Python literal. Both reached consumers
# because no check on this machine compiled emitted Kotlin.
#
# ⚠️ This header used to add "— `tsc --noEmit` and `swiftc -parse` run in the
# suite, and nothing answers for Kotlin." Measured 2026-09-05: FALSE on both
# counts, and in the direction that reassures.
#
#   tsc     rjui had no matcher, no spec/support directory, and no spec that
#           invoked a compiler. Its one check parsed JSX with @babel/parser,
#           env-gated so it skipped by default. Zero files type-checked.
#   swiftc  sjui did run it — but `-parse`, and parse is not the check that
#           matters. `-parse` accepts
#           `data.collectionDataSource.getCellData(for: "X")` with zero
#           errors: a property nothing declares calling a method that exists
#           nowhere. Only `-typecheck` rejects it, and it sat behind three
#           passing specs for years.
#
# Both faces now have real type-check arms and a source gate naming what is
# still unconverted (spec/emitted_{swift,typescript}_reaches_a_compiler_spec.rb,
# and the Kotlin one beside them). The sentence is corrected rather than
# deleted because a script that justifies itself by what other faces cover
# should be checkable, and this one was not.
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

G="${GRADLE_USER_HOME:-$HOME/.gradle}/caches/modules-2/files-2.1"
FETCH="${JSONUI_KOTLIN_PINS:-$REPO/.github/scripts/fetch_kotlin_compiler_jars.sh}"  # override: the gate's own test only
FETCH_HINT="bash .github/scripts/fetch_kotlin_compiler_jars.sh"

# The compiler and its core jars are taken at the versions CI pins — the
# fetch script's `jars=(...)` list, the one source — at that exact version.
# Until 1.9.10 this took the newest in the cache (`find ~/.gradle/caches`
# over the whole cache, then `sort -V | tail -1`): kotlin-compiler-embeddable
# 2.4.20 on the release machine where CI compiles with 2.1.0. A gate that is
# missing its pinned compiler FAILS (exit 2); it does not fall back.
pinned_version() {  # group artifact -> the version the fetch script pins, or empty
    sed -n '/^jars=(/,/^)/p' "$FETCH" | awk -v g="$1" -v a="$2" '{ gsub(/"/, ""); if ($1 == g && $2 == a) print $3 }'
}
pinned() {  # group artifact -> the jar at its pinned version, or exit 2
    local version jar
    version="$(pinned_version "$1" "$2")"
    if [ -z "$version" ]; then
        echo "CANNOT ATTEMPT: $1:$2 has no pinned version in $FETCH" >&2
        exit 2
    fi
    jar="$(ls "$G/$1/$2/$version"/*/"$2-$version.jar" 2>/dev/null | head -1)"
    if [ -z "$jar" ]; then
        echo "CANNOT ATTEMPT: $1:$2:$version (pinned) is not in the Gradle cache — fetch: $FETCH_HINT" >&2
        exit 2
    fi
    printf '%s' "$jar"
}
# The compiler runs on the JVM and needs its own dependencies on its own
# classpath; the emitted file needs a different set on the target one. They
# are separate, and conflating them is how the first attempt at this failed
# with NoClassDefFoundError inside the compiler rather than a diagnostic
# about the file.
KOTLINC="$(pinned org.jetbrains.kotlin kotlin-compiler-embeddable)" || exit 2
KOTLIN_VERSION="$(pinned_version org.jetbrains.kotlin kotlin-compiler-embeddable)"

STDLIB="$(pinned org.jetbrains.kotlin kotlin-stdlib)" || exit 2
REFLECT="$(pinned org.jetbrains.kotlin kotlin-reflect)" || exit 2
ANNOTATIONS="$(pinned org.jetbrains annotations)" || exit 2
COROUTINES="$(pinned org.jetbrains.kotlinx kotlinx-coroutines-core-jvm)" || exit 2
TROVE="$(pinned org.jetbrains.intellij.deps trove4j)" || exit 2

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
    jar="$(pinned $pair)" || exit 2
    echo "target: $(basename "$jar") (pinned)"
    TARGET_CP="$TARGET_CP:$jar"
done
echo "kotlin-compiler-embeddable $KOTLIN_VERSION (pinned): $KOTLINC"

JAVA_HOME_21="$(/usr/libexec/java_home -v 21 2>/dev/null || /usr/libexec/java_home -v 17 2>/dev/null)"
[ -n "$JAVA_HOME_21" ] || { echo "CANNOT ATTEMPT: no JDK 17+ found" >&2; exit 2; }

PYTHONPATH="$REPO/test_tools" python3 - "$WORK" <<'PY'
import sys
from jsonui_test_cli.branch_tests import KOTLIN_RUNTIME
out = sys.argv[1] + "/JsonuiBranchRuntime.kt"
open(out, "w").write(KOTLIN_RUNTIME % {"package": "release.probe"})
PY
[ -s "$WORK/JsonuiBranchRuntime.kt" ] || { echo "CANNOT ATTEMPT: the runtime did not render" >&2; exit 2; }

# Non-empty is not the same as having something to check. Measured: a file
# containing only `package release.probe` compiles with exit 0 and produces
# ZERO class files, and this script would have called that "emitted Kotlin
# compiles". So require the source to carry the things this check exists to
# protect -- the diagnostic and the per-language quoting -- before running
# a compiler over it at all.
for marker in 'resolveString(' 'quotedValue' 'class '; do
    grep -qF "$marker" "$WORK/JsonuiBranchRuntime.kt" || {
        echo "CANNOT ATTEMPT: the rendered runtime has no '$marker'" >&2
        echo "  Compiling it would pass by having nothing in it." >&2
        exit 2
    }
done

# -jvm-target is not optional. Without it the backend crashes on a JDK 21
# default rather than reporting anything about the file, which reads as
# "the emitted Kotlin is broken" when it is not.
"$JAVA_HOME_21/bin/java" -cp "$COMPILER_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
    -no-stdlib -jvm-target 17 -classpath "$TARGET_CP" \
    -d "$WORK/out" "$WORK/JsonuiBranchRuntime.kt" > "$WORK/log" 2>&1
status=$?

grep -v '^warning: unable to find' "$WORK/log"
classes=$(find "$WORK/out" -name '*.class' 2>/dev/null | wc -l | tr -d ' ')
if [ "$status" -eq 0 ] && [ "${classes:-0}" -gt 0 ]; then
    echo "OK: emitted Kotlin compiles (kotlinc $KOTLIN_VERSION, jvm-target 17)" \
         "— $classes class file(s)"
    exit 0
fi
if [ "$status" -eq 0 ]; then
    echo "CANNOT ATTEMPT: the compiler succeeded and emitted no classes." >&2
    echo "  A green with nothing compiled is the failure this guards." >&2
    exit 2
fi
echo "FAILED: the emitted Kotlin does not compile (kotlinc $KOTLIN_VERSION)" >&2
exit 1
