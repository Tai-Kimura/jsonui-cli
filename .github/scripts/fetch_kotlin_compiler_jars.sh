#!/usr/bin/env bash
# Puts the jars kjui_tools/spec/support/kotlin_compiler.rb reads into a
# Gradle-cache layout, so the kjui compile / run arms have a compiler on a
# machine that never ran Gradle (CI's `rspec (kjui_tools)` leg). Without them
# every such arm is pending (ticket kjui-rspec-ci-job-has-no-kotlin-compiler).
#
#   fetch_kotlin_compiler_jars.sh [GRADLE_USER_HOME]   (default ~/.gradle)
#
# Layout: <home>/caches/modules-2/files-2.1/<group>/<artifact>/<version>/
# <sha1>/<artifact>-<version>.jar — what Gradle writes and what the helper's
# globs read. Versions are pinned and every jar is checked against the
# SHA-256 written here, so a cached or re-fetched jar is the jar measured.
# Idempotent: a jar already present with the right digest is not fetched.
set -euo pipefail

home=${1:-${GRADLE_USER_HOME:-$HOME/.gradle}}
modules="$home/caches/modules-2/files-2.1"
repo=${MAVEN_REPO:-https://repo1.maven.org/maven2}

# group artifact version sha256
jars=(
  "org.jetbrains.kotlin kotlin-compiler-embeddable 2.1.0 c1b139a6f251c3b99e92befa326cb75d93a001d74c3ac601155a8cdb0d253783"
  "org.jetbrains.kotlin kotlin-stdlib 2.1.0 d6f91b7b0f306cca299fec74fb7c34e4874d6f5ec5b925a0b4de21901e119c3f"
  "org.jetbrains.kotlin kotlin-reflect 2.1.0 b5f608edfa98a8cfa2372cc12d18ada974be1c56c1093eff06cc061f4fc088b2"
  "org.jetbrains annotations 13.0 ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478"
  "org.jetbrains.kotlinx kotlinx-coroutines-core-jvm 1.10.2 5ca175b38df331fd64155b35cd8cae1251fa9ee369709b36d42e0a288ccce3fd"
  "org.jetbrains.intellij.deps trove4j 1.0.20200330 c5fd725bffab51846bf3c77db1383c60aaaebfe1b7fe2f00d23fe1b7df0a439d"
  "com.google.code.gson gson 2.13.1 94855942d4992f112946d3de1c334e709237b8126d8130bf07807c018a4a2120"
)

sha256() { sha256sum "$1" | cut -d' ' -f1; }
sha1() { sha1sum "$1" | cut -d' ' -f1; }

for line in "${jars[@]}"; do
  read -r group artifact version want <<<"$line"
  name="$artifact-$version.jar"
  existing=$(find "$modules/$group/$artifact/$version" -name "$name" 2>/dev/null | head -n 1 || true)
  if [ -n "$existing" ] && [ "$(sha256 "$existing")" = "$want" ]; then
    echo "cached   $group:$artifact:$version"
    continue
  fi
  tmp=$(mktemp)
  url="$repo/${group//.//}/$artifact/$version/$name"
  curl -fsSL --retry 5 --retry-delay 5 -o "$tmp" "$url"
  got=$(sha256 "$tmp")
  if [ "$got" != "$want" ]; then
    echo "error: $url has sha256 $got, pinned $want" >&2
    rm -f "$tmp"
    exit 1
  fi
  dir="$modules/$group/$artifact/$version/$(sha1 "$tmp")"
  mkdir -p "$dir"
  mv "$tmp" "$dir/$name"
  echo "fetched  $group:$artifact:$version"
done
