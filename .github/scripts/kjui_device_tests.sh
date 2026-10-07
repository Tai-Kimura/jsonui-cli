#!/usr/bin/env bash
# conformance-mobile's android-library-tests job, run inside the emulator
# action. The action's `script:` runs one line at a time, so the logic lives
# here.
#
# Runs library's, library-dynamic's and conformance-host's
# connectedDebugAndroidTest on the booted emulator, then judges from the
# results XML (kjui_device_tests.py judge). conformance-host's suite class is
# left out (notClass): the android jobs run it; its probes run here (ticket
# kjui-conformance-host-androidtest-probes-never-run-in-ci).
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
#
# Gradle runs under kjui_device_tests.py watch: at the first failed case it
# saves the device's state (device-evidence/first-failure), and when a
# module's progress count has not moved for KJUI_IDLE_SECONDS (default 600;
# the longest wait on five green runs was 120 s) it saves it again
# (device-evidence/stopped) and stops Gradle with exit 124, instead of hanging
# to the step's budget, which kills this script before the evidence below is
# taken (ticket ci-android-library-tests-emulator-dies-in-the-keyboard-tests-
# and-the-run-hangs: two runs sat at "Tests 0/203" for 99 minutes).
set -uo pipefail
kjui=${1:?usage: kjui_device_tests.sh <KotlinJsonUI checkout>}
here=$(cd "$(dirname "$0")" && pwd)
# Absolute: Gradle and the watch run from inside the checkout.
evidence="$(cd "$kjui" && pwd)/device-evidence"
test_packages=(com.kotlinjsonui.test com.kotlinjsonui.dynamic.test
               com.kotlinjsonui.conformance com.kotlinjsonui.conformance.test)

# Best effort: a bigger ring buffer so a ~15-minute run's early lines survive
# to the dump, and a clean start so the dump is this run's.
# `-b all`: without it -G leaves the events buffer at 256 KiB (measured on an
# API 35 AVD), and run 37630837392's events at the end reached back only to
# 14:12 of a run that started 13:45 — the am_anr count was of the last 8
# minutes. What the boot left in it (an ANR right after boot, before the
# setting below) is saved before the clear.
mkdir -p "$evidence"
adb logcat -d -b events -v threadtime >"$evidence/logcat-events-before-run.txt" 2>&1 || true
adb logcat -b all -G 16M >/dev/null 2>&1 || echo "warning: could not resize the logcat buffers"
adb logcat -b all -c >/dev/null 2>&1 || true

# No "isn't responding" / "keeps stopping" dialog: the system closes the app
# instead (measured on an API 35 tablet AVD, 2026-10-07: with the setting an
# app whose main thread is blocked ANRs and no dialog takes the focus; without
# it the dialog holds it). Run 37618369032: Pixel Launcher's ANR dialog held
# the focus for 14 minutes, the IME never showed, library's keyboard cases
# timed out and library-dynamic did not start a case (ticket ci-android-
# library-tests-emulator-dies-in-the-keyboard-tests-and-the-run-hangs). The
# watch below closes such a dialog if one shows anyway.
adb shell settings put global hide_error_dialogs 1 >/dev/null 2>&1 \
  || echo "warning: could not set hide_error_dialogs"
echo "hide_error_dialogs: $(adb shell settings get global hide_error_dialogs 2>/dev/null | tr -d '\r')"

collect_evidence() {
  mkdir -p "$evidence" || return 0
  adb logcat -d -v threadtime >"$evidence/logcat.txt" 2>&1 \
    || echo "warning: adb logcat -d failed (see $evidence/logcat.txt)"
  adb logcat -d -b crash -v threadtime >"$evidence/logcat-crash.txt" 2>&1 || true
  # am_anr lands in the events buffer, not main: with hide_error_dialogs an
  # ANR shows no dialog and the run can stay green, so the count is how a run
  # says one happened.
  adb logcat -d -b events -v threadtime >"$evidence/logcat-events.txt" 2>&1 || true
  # Each count names the window it read: a buffer that rolled over reads
  # as fewer ANRs, not as none.
  local window
  window=$(grep -oE '^[0-9]{2}-[0-9]{2} [0-9:.]+' "$evidence/logcat-events.txt" 2>/dev/null | sed -n '1p;$p' | tr '\n' ' ')
  echo "ANRs on the device (am_anr): before the run $(grep -c ' am_anr ' "$evidence/logcat-events-before-run.txt" 2>/dev/null || true), during the run $(grep -c ' am_anr ' "$evidence/logcat-events.txt" 2>/dev/null || true) (events read from ${window:-nothing})"
  local pkg
  for pkg in "${test_packages[@]}"; do
    adb shell dumpsys activity exit-info "$pkg" >"$evidence/exit-info-$pkg.txt" 2>&1 \
      || echo "warning: exit-info for $pkg failed"
  done
  adb shell dumpsys activity exit-info >"$evidence/exit-info-all.txt" 2>&1 || true
  adb shell dumpsys input_method >"$evidence/input_method.txt" 2>&1 || true
  adb shell dumpsys window >"$evidence/window.txt" 2>&1 || true
  adb exec-out screencap -p >"$evidence/screen.png" 2>/dev/null || true
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

# The classes another job runs (kjui_device_tests.py RUN_ELSEWHERE).
not_class=$(python3 "$here/kjui_device_tests.py" not-class "$kjui") || exit 2
echo "left out here (run by another job): $not_class"

rc=0
(cd "$kjui" && python3 "$here/kjui_device_tests.py" watch \
  --idle "${KJUI_IDLE_SECONDS:-600}" --focus "${KJUI_FOCUS_SECONDS:-15}" --evidence "$evidence" -- \
  ./gradlew --no-daemon --continue \
  :library:connectedDebugAndroidTest :library-dynamic:connectedDebugAndroidTest \
  :conformance-host:connectedDebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.notClass="$not_class" \
  -Pandroid.injected.androidTest.leaveApksInstalledAfterRun=true \
  ${args[@]+"${args[@]}"}) || rc=$?
echo "gradle exit: $rc$([ "$rc" = 124 ] && echo ' (stopped by the watch: the cases stopped moving)')"

collect_evidence || echo "warning: evidence collection failed; the verdict is unchanged"

python3 "$here/kjui_device_tests.py" judge "$kjui" || rc=1
exit "$rc"
