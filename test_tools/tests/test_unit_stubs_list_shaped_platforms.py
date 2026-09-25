"""`platforms` written as a list does not crash `generate unit-stubs`.

`jui init` writes `platforms` as an object (`{"ios": {...}}`), and that is the
only shape that can carry `unitTestsDir`. The test_tools readers — `contracts
coverage`, branch tests, `_project_platforms` — also accept a list of names,
and their own fixtures use it. `_test_roots` called `.items()` on the value and
died with an AttributeError: the run printed a traceback and nothing it had
checked, which is the one outcome `--check` must never produce.

The rule kept here: a list names the platforms and nothing else, so every
platform it names is NOT CHECKED — the same verdict as an object entry without
`unitTestsDir` — and the message says the list is why, and which shape to write.
The control arm pins that the two spellings reach the same verdict.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import unit_contracts as uc

TEST_TOOLS = Path(__file__).parent.parent


def _project(tmp_path, platforms):
    (tmp_path / "docs" / "screens").mkdir(parents=True)
    (tmp_path / "docs" / "screens" / "chat.spec.json").write_text(json.dumps({
        "type": "screen",
        "unitContracts": {"target": "ChatViewModel", "cases": [{"name": "alpha"}]},
    }), encoding="utf-8")
    (tmp_path / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens", "platforms": platforms,
    }), encoding="utf-8")
    return tmp_path


def _run_check(root):
    env = dict(os.environ, PYTHONPATH=str(TEST_TOOLS))
    return subprocess.run(
        [sys.executable, "-m", "jsonui_test_cli.cli", "generate", "unit-stubs", "--check"],
        cwd=root, env=env, capture_output=True, text=True)


def test_list_shaped_platforms_are_reported_not_checked_not_a_traceback(tmp_path):
    root = _project(tmp_path, ["web", "android", "ios"])
    run = _run_check(root)
    out = run.stdout + run.stderr
    assert "Traceback" not in out, out
    for platform in ("web", "android", "ios"):
        line = next((l for l in out.splitlines() if l.strip().startswith(f"{platform}: NOT CHECKED")), None)
        assert line is not None, out
        assert "as a list" in line and "platforms.<platform>.unitTestsDir" in line, line


def test_list_and_object_without_unit_tests_dir_reach_the_same_verdict(tmp_path):
    """Control: the list is one more way to leave unitTestsDir undeclared."""
    as_list = _run_check(_project(tmp_path / "a", ["web", "ios"]))
    as_object = _run_check(_project(tmp_path / "b", {"web": {"root": "web"}, "ios": {"root": "ios"}}))
    assert "Traceback" not in as_object.stdout + as_object.stderr
    assert as_list.returncode == as_object.returncode
    not_checked = lambda r: sorted(l.split(":")[0].strip() for l in r.stdout.splitlines() if "NOT CHECKED" in l)
    assert not_checked(as_list) == not_checked(as_object) == ["ios", "web"]


def test_test_roots_reads_a_list_as_names_without_directories(tmp_path):
    assert uc._test_roots(tmp_path, {"platforms": ["web", "ios"]}) == {"web": None, "ios": None}
    # Neither an object nor a list: nothing is declared, and nothing crashes.
    assert uc._test_roots(tmp_path, {"platforms": "web"}) == {}
