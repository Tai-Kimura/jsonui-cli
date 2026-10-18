"""Which Bash commands are test runs (10-18 ticket 2026-10-18-jui-viz-non-test-commands-shown-as-test-runs).

Until 2.3.0 a command was a test run when `jsonui-test`, `connectedAndroidTest`, `adb` or `xcrun simctl`
appeared anywhere in its text: a `find` of the results folder, a `git grep` for a task name and a python
heredoc that edits a test file were listed as passing test runs. The rule now reads the executable and its
subcommand of each simple command. Both sides are specimens: a rule tightened on one side only drops real
test runs, and one loosened only fakes them.
"""
from __future__ import annotations

import pytest

from jui_cli.viz import robots
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState

RUNS_TESTS = [
    ("xcodebuild test -scheme App -destination 'id=0000'", "ios"),
    ("cd ios && xcodebuild -workspace A.xcworkspace -scheme A test-without-building", "ios"),
    ("env -u JSONUI_TEST_PROGRESS_DIR xcrun xcodebuild test -scheme A", "ios"),
    ("./gradlew connectedDebugAndroidTest", "android"),
    ("ANDROID_SERIAL=emulator-5554 ./gradlew :app:connectedDevDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=X", "android"),
    ("./gradlew :jsonuitestrunner:testDebugUnitTest", "android"),
    ("cd app && ./gradlew test --rerun", "android"),
    ("npx playwright test", "web"),
    ("npx playwright test tests/playwright/jsonui.spec.ts --project=chromium", "web"),
    ("npm test", "web"),
    ("npm run test:e2e", "web"),
    ("pnpm exec playwright test", "web"),
    ("npx jest src/runner", "web"),
    ("python3 -m pytest -q tests/test_viz_ingest.py", "unknown"),
    ("cd jui_tools && pytest -q tests", "unknown"),
    ("timeout 600 swift test", "unknown"),
    ("flutter test", "unknown"),
    ("bundle exec rspec spec/core", "unknown"),
]

NOT_TESTS = [
    # the four commands of the screenshot (21:50), word for word as far as the card showed them
    "python3 - <<'EOF'\np='jsonui_project.py'; s=open(p).read()\nold='xcodebuild test'\nEOF",
    "R=/srv/some-project; ls $R/tests/web/screens | head",
    "find ~/.local/state/jsonui-test -maxdepth 3 -type d | head; find ~/.local/state/jsonui-test -type f | wc -l",
    'cd /x/wt/tr-prune; git grep -n "jsonui-test/results\\|JSONUI_TEST_RESULTS_DIR\\|connectedAndroidTest"',
    # the 18:25 / 18:30 ones
    "cd /x/wt/tr-web-results; cat > /tmp/msg.txt <<'EOF'\ntests: npx playwright test now writes\nEOF",
    "cd /x/wt/viz-results/jui_tools; python3 - <<'EOF'\np='tests/test_viz_test_results.py'\nEOF",
    # a heredoc whose body IS a test command, being written to a file — data, not a run
    "cat > run_ui.sh <<'EOF'\nxcodebuild test -scheme App\n./gradlew connectedDebugAndroidTest\nEOF\nchmod +x run_ui.sh",
    # more of the same family
    "grep -rn 'playwright test' docs/",
    "cat tests/screens/login.test.json",
    "jsonui-test validate tests/screens",
    "jsonui-test generate test screen login",
    "echo xcodebuild test",
    "ls tests/ && wc -l tests/*.json",
    "git log --oneline -- tests/",
    "npm run build",
    "npm install",
    "./gradlew assembleDebug",
    "xcodebuild build -scheme App",
    "python3 -c \"print('pytest')\"",
    "adb -s emulator-5554 shell ls /data/local/tmp",
    "xcrun simctl list devices booted",
    "sed -n '1,40p' tests/test_viz_ingest.py",
    "printf 'run xcodebuild test'",
    "echo 'unbalanced",
]


@pytest.mark.parametrize("command,platform", RUNS_TESTS)
def test_a_real_test_command_is_a_test_run(command, platform):
    assert robots.test_platform(command) == platform
    assert robots.state_for_tool("Bash", {"command": command}) == "phone"


@pytest.mark.parametrize("command", NOT_TESTS)
def test_a_command_that_only_mentions_tests_is_not_a_test_run(command):
    assert robots.test_platform(command) is None


def test_device_commands_hold_a_phone_but_are_no_test_run():
    for command in ("adb -s emulator-5554 shell ls", "xcrun simctl io booted screenshot x.png"):
        assert robots.state_for_tool("Bash", {"command": command}) == "phone"
        assert robots.test_platform(command) is None
    assert robots.state_for_tool("Bash", {"command": "readb file"}) == "command"


def test_only_test_commands_reach_the_test_pane(tmp_path):
    state = VizState()
    world = World(state)
    base = {"session_id": "s1", "cwd": str(tmp_path)}
    world.apply_hook({**base, "hook_event_name": "SessionStart"}, 0)
    devices = ["adb -s emulator-5554 shell ls /data/local/tmp", "xcrun simctl list devices booted"]
    commands = [c for c, _ in RUNS_TESTS[:3]] + NOT_TESTS[:4] + devices
    for i, command in enumerate(commands):
        world.apply_hook({**base, "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": f"b{i}",
                          "tool_input": {"command": command}}, 10 + i)
        world.apply_hook({**base, "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_use_id": f"b{i}",
                          "tool_input": {"command": command}, "tool_response": {"stdout": "", "stderr": ""}}, 11 + i)
    world.publish()
    assert sorted(t["command"] for t in state.slices["tests"]) == sorted(commands[:3])
