"""Regression: validate-skips-mocks-outside-the-given-path.

A project's tests and its mocks are routinely different trees, and the gate a
project actually runs points at the tests. The drift check had always resolved
mockDir from config, so it opened mocks the file validator never saw: a mock
with a malformed `$schema` or an unknown key passed `validate <testDir>` and
failed only when someone aimed the command straight at the mocks. The check
was correct and unreachable, which is the same thing as absent.
"""

import json
import subprocess
import sys
from pathlib import Path

TEST_TOOLS = Path(__file__).resolve().parents[1]


def _mock(schema_ref: str) -> str:
    return json.dumps({
        "$schema": schema_ref,
        "source": {"swagger": "s.json", "operationId": "getOrder",
                   "method": "GET", "path": "/api/orders"},
        "activeScenario": "default",
        "scenarios": {"default": {"status": 200, "body": {}}},
    }, indent=2) + "\n"


def _project(tmp_path: Path, schema_ref: str) -> tuple[Path, Path]:
    """Build the shape that hid the bug: mocks under the front, tests beside it."""
    front = tmp_path / "front"
    mocks = front / "tests" / "mocks" / "orders"
    mocks.mkdir(parents=True)
    (mocks / "getOrder.mock.json").write_text(_mock(schema_ref), encoding="utf-8")
    (front / "jui.config.json").write_text(
        json.dumps({"mock": {"swagger": [], "mockDir": "tests/mocks"}}),
        encoding="utf-8")

    tests = tmp_path / "tests" / "user" / "screens"
    tests.mkdir(parents=True)
    (tests / "x.test.json").write_text(json.dumps({
        "type": "screen", "metadata": {"name": "X"},
        "cases": [{"name": "c", "steps": []}],
    }), encoding="utf-8")
    return front, tmp_path / "tests" / "user"


def _validate(cwd: Path, target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "jsonui_test_cli.cli", "validate", str(target)],
        cwd=cwd, capture_output=True, text=True,
        env={"PYTHONPATH": str(TEST_TOOLS), "PATH": "/usr/bin:/bin"},
    )


def test_a_bad_mock_outside_the_given_path_fails_the_gate(tmp_path):
    front, tests = _project(tmp_path, "../.mock.schema.json")
    proc = _validate(front, tests)
    assert proc.returncode == 1, proc.stdout
    # Named, not merely counted — the operator has to know which file.
    assert "getOrder.mock.json" in proc.stdout
    assert "$schema" in proc.stdout


def test_the_same_gate_goes_green_once_the_mock_is_fixed(tmp_path):
    front, tests = _project(tmp_path, "./.mock.schema.json")
    proc = _validate(front, tests)
    assert proc.returncode == 0, proc.stdout


def test_a_mock_is_not_validated_twice_when_its_directory_is_given(tmp_path):
    """Pointing at the mocks directly must not double-count it."""
    front, _ = _project(tmp_path, "./.mock.schema.json")
    proc = _validate(front, front / "tests" / "mocks")
    assert proc.returncode == 0, proc.stdout
    assert "Files: 1," in proc.stdout, proc.stdout


def test_a_project_without_mocks_is_unaffected(tmp_path):
    """No mock config means nothing extra is collected, and no config read fails."""
    tests = tmp_path / "tests" / "user" / "screens"
    tests.mkdir(parents=True)
    (tests / "x.test.json").write_text(json.dumps({
        "type": "screen", "metadata": {"name": "X"},
        "cases": [{"name": "c", "steps": []}],
    }), encoding="utf-8")
    proc = _validate(tmp_path, tmp_path / "tests" / "user")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Files: 1," in proc.stdout, proc.stdout
