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
#
# After Gradle it saves crash evidence into <checkout>/device-evidence/ (the
# workflow uploads it): the whole logcat and `dumpsys activity exit-info`
# (ApplicationExitInfo) for the test packages and for every package. A
# "Process crashed" instrumentation failure otherwise leaves nothing to read
# once the emulator stops (ticket
# kjui-androidtest-process-crash-in-dynamic-collection-declared-rows-test).
# The library androidTest APKs are self-instrumenting, so the test package
# is both the instrumentation and the app under test. The test APKs are kept
# installed after the run, because the system drops a package's exit-info
# when it is uninstalled. Evidence collection never changes the exit status.
set -uo pipefail
kjui=${1:?usage: kjui_device_tests.sh <KotlinJsonUI checkout>}
here=$(cd "$(dirname "$0")" && pwd)
evidence="$kjui/device-evidence"
test_packages=(com.kotlinjsonui.test com.kotlinjsonui.dynamic.test)

# Best effort: a bigger ring buffer so a ~15-minute run's early lines survive
# to the dump, and a clean start so the dump is this run's.
adb logcat -G 16M >/dev/null 2>&1 || echo "warning: could not resize the logcat buffer"
adb logcat -c >/dev/null 2>&1 || true

collect_evidence() {
  mkdir -p "$evidence" || return 0
  adb logcat -d -v threadtime >"$evidence/logcat.txt" 2>&1 \
    || echo "warning: adb logcat -d failed (see $evidence/logcat.txt)"
  adb logcat -d -b crash -v threadtime >"$evidence/logcat-crash.txt" 2>&1 || true
  local pkg
  for pkg in "${test_packages[@]}"; do
    adb shell dumpsys activity exit-info "$pkg" >"$evidence/exit-info-$pkg.txt" 2>&1 \
      || echo "warning: exit-info for $pkg failed"
  done
  adb shell dumpsys activity exit-info >"$evidence/exit-info-all.txt" 2>&1 || true
  adb shell cat /proc/meminfo >"$evidence/meminfo-device.txt" 2>&1 || true
  free -m >"$evidence/meminfo-host.txt" 2>&1 || true
  echo "device evidence saved: $evidence"
}

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
  -Pandroid.injected.androidTest.leaveApksInstalledAfterRun=true \
  ${args[@]+"${args[@]}"}) || rc=$?
echo "gradle exit: $rc"

collect_evidence || echo "warning: evidence collection failed; the verdict is unchanged"

python3 "$here/kjui_device_tests.py" judge "$kjui" || rc=1
exit "$rc"
