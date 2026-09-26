#!/usr/bin/env bash
# conformance-mobile's android-library-tests job, run inside the emulator
# action. The action's `script:` runs one line at a time, so the logic lives
# here.
#
# Runs library's and library-dynamic's connectedDebugAndroidTest on the booted
# emulator, then judges from the results XML (kjui_device_tests.py judge).
# Gradle's exit code alone is not the verdict: a class that never ran is not a
# failure to Gradle.
#
# ANDROID_PROBES=true raises every opt-in switch the tests declare
# (kjui_device_tests.py flags).
set -uo pipefail
kjui=${1:?usage: kjui_device_tests.sh <KotlinJsonUI checkout>}
here=$(cd "$(dirname "$0")" && pwd)

args=()
if [ "${ANDROID_PROBES:-false}" = true ]; then
  while IFS= read -r name; do
    [ -n "$name" ] && args+=("-Pandroid.testInstrumentationRunnerArguments.${name}=1")
  done < <(python3 "$here/kjui_device_tests.py" flags "$kjui")
  echo "opt-in probes raised: ${#args[@]}${args[*]+ — ${args[*]}}"
  [ "${#args[@]}" = 0 ] && echo "warning: android_probes=true, and no test declares a switch"
else
  echo "opt-in probes: off (dispatch with android_probes=true to raise them)"
fi

rc=0
(cd "$kjui" && ./gradlew --no-daemon --continue \
  :library:connectedDebugAndroidTest :library-dynamic:connectedDebugAndroidTest \
  ${args[@]+"${args[@]}"}) || rc=$?
echo "gradle exit: $rc"

python3 "$here/kjui_device_tests.py" judge "$kjui" || rc=1
exit "$rc"
