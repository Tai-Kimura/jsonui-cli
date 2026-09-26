"""The Ruby tools stop below Ruby 3.2 with one line, and `jui build` shows it.

jsonui-cli 1.9.0 drops Ruby 2.6 (ruling 2026-09-26). bin/sjui, bin/kjui and
bin/rjui check RUBY_VERSION before they load anything and stop with one ERROR
line naming the ruby that ran (each tool's spec/cli/entry_names_the_ruby_floor
shoots both sides of the boundary on the entry itself). These arms hold the
route a face takes: `jui build` starts each tool from its platform root
through tool_resolver, and

* the tool directory's .ruby-version reaches the child as RBENV_VERSION only
  when rbenv has that version installed (build_tool_env);
* otherwise nothing is passed, and the ruby is whatever `ruby` the
  environment resolves from the platform root — rbenv's walk up for a
  .ruby-version, then rbenv's global (`system` on a Mac where it was never
  set); with no rbenv in front of PATH, PATH's ruby, and RBENV_VERSION
  selects nothing.

The rubies are stand-ins, so the arms run the same everywhere: a `ruby` on
PATH that runs this machine's ruby with RUBY_VERSION replaced before the
entry runs — always 2.6.10 for "a PATH ruby, no rbenv"; for "rbenv", the
version rbenv would pick (RBENV_VERSION, else the nearest .ruby-version, else
`system` = 2.6.10; a version that is not installed is rbenv's own error, not
the floor's line). The entries are the real
bin files; each tool's lib is a stub that prints REACHED, so nothing but the
entry is under test.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = {"ios": "sjui", "android": "kjui", "web": "rjui"}
BEGIN = "# ---- Ruby floor: the same block in bin/sjui, bin/kjui and bin/rjui ----\n"
END = "# ---- end of the Ruby floor ----\n"

STUB = {
    "sjui": "module SjuiTools; module CLI; class Main; def run(_argv); puts 'REACHED sjui'; end; end; end; end\n",
    "kjui": "module KjuiTools; module CLI; class Main; def self.run(_argv); puts 'REACHED kjui'; end; end; end; end\n",
    "rjui": "module RjuiTools; module CLI; class Main; def self.start(_argv); puts 'REACHED rjui'; end; end; end; end\n",
}

FAKE_RB = ("Object.send(:remove_const, :RUBY_VERSION)\n"
           "Object.const_set(:RUBY_VERSION, ENV.fetch('JSONUI_FAKE_RUBY_VERSION').dup.freeze)\n")

# A `ruby` with no rbenv behind it: always the old one, RBENV_VERSION or not.
PLAIN_RUBY = """#!/bin/sh
JSONUI_FAKE_RUBY_VERSION=2.6.10 RUBYOPT="-r{fake} $RUBYOPT" exec "{host}" "$@"
"""

# A `ruby` that picks as rbenv does: RBENV_VERSION, else the nearest
# .ruby-version above the working directory, else the global (`system`, never
# set here). A version that is not installed is an error, as rbenv makes it
# (measured: "rbenv: version `9.9.9' is not installed (set by …)", exit 1) —
# not a fall to system. Like `rbenv exec`, it exports the version it chose.
RBENV_RUBY = r"""#!/bin/sh
v="$RBENV_VERSION"; src="RBENV_VERSION environment variable"
if [ -z "$v" ]; then
  d="$PWD"
  while :; do
    if [ -f "$d/.ruby-version" ]; then v=$(cat "$d/.ruby-version"); src="$d/.ruby-version"; break; fi
    [ "$d" = "/" ] && break
    d=$(dirname "$d")
  done
fi
if [ -z "$v" ] || [ "$v" = system ]; then
  v=system; fake=2.6.10
elif [ -d "$RBENV_ROOT/versions/$v" ]; then
  fake="$v"
else
  echo "rbenv: version \`$v' is not installed (set by $src)" >&2; exit 1
fi
RBENV_VERSION="$v" JSONUI_FAKE_RUBY_VERSION="$fake" RUBYOPT="-r{fake} $RUBYOPT" exec "{host}" "$@"
"""


def _host_ruby() -> str:
    """The real interpreter behind `ruby` here (a stand-in runs it)."""
    found = shutil.which("ruby")
    assert found, "no ruby on PATH — these arms run the tools' real entries"
    said = subprocess.run([found, "-rrbconfig", "-e", "print RbConfig.ruby"],
                          capture_output=True, text=True, check=True)
    return said.stdout.strip()


def _floor_block(text: str) -> str:
    assert text.count(BEGIN) == 1 and text.count(END) == 1, "the floor block's markers"
    return text[text.index(BEGIN):text.index(END) + len(END)]


def test_the_three_entries_carry_one_floor_block_before_anything_loads():
    blocks = {}
    for tool in TOOLS.values():
        text = (REPO / f"{tool}_tools" / "bin" / tool).read_text(encoding="utf-8")
        block = _floor_block(text)
        blocks[tool] = block
        before = text[:text.index(BEGIN)]
        assert not re.search(r"^\s*(require|\$LOAD_PATH|Encoding\.)", before, re.M), (
            f"bin/{tool} runs something before the floor")
    assert len(set(blocks.values())) == 1, "bin/sjui, bin/kjui and bin/rjui carry different floor blocks"
    assert "(RUBY_VERSION.split('.').map(&:to_i) <=> [3, 2, 0]) < 0" in blocks["sjui"]


def _project(tmp: Path, *, pins: dict, root_pins: dict, installed: list) -> Path:
    project = tmp / "project"
    (project / "docs" / "screens" / "layouts").mkdir(parents=True)
    (project / "docs" / "screens" / "layouts" / "home.json").write_text('{"type": "View", "child": []}\n')
    (project / "jui.config.json").write_text(
        '{"project_name": "Probe", "layouts_directory": "docs/screens/layouts", "platforms": '
        '{"ios": {"root": "ios"}, "android": {"root": "android"}, "web": {"root": "web"}}}\n')
    for platform, tool in TOOLS.items():
        tool_dir = project / platform / f"{tool}_tools"
        (tool_dir / "bin").mkdir(parents=True)
        (tool_dir / "lib" / "cli").mkdir(parents=True)
        shutil.copy2(REPO / f"{tool}_tools" / "bin" / tool, tool_dir / "bin" / tool)
        (tool_dir / "lib" / "cli" / "main.rb").write_text(STUB[tool])
        if tool in pins:
            (tool_dir / ".ruby-version").write_text(pins[tool] + "\n")
        if platform in root_pins:
            (project / platform / ".ruby-version").write_text(root_pins[platform] + "\n")
    for version in installed:
        (tmp / "rbenv" / "versions" / version).mkdir(parents=True)
    (tmp / "rbenv" / "versions").mkdir(parents=True, exist_ok=True)
    return project


def _jui_build(tmp: Path, project: Path, ruby_script: str) -> tuple[int, str, str]:
    host = _host_ruby()
    fake = tmp / "fake_ruby_version.rb"
    fake.write_text(FAKE_RB)
    fake_bin = tmp / "bin"
    fake_bin.mkdir(exist_ok=True)
    ruby = fake_bin / "ruby"
    ruby.write_text(ruby_script.format(fake=fake, host=host))
    ruby.chmod(0o755)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("RBENV_", "RUBY", "BUNDLE", "GEM_"))}
    env.update(PATH=f"{fake_bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
               PYTHONPATH=str(REPO / "jui_tools"), RBENV_ROOT=str(tmp / "rbenv"),
               LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8")
    run = subprocess.run([sys.executable, "-c", "import sys; from jui_cli.cli import main; sys.exit(main(['build']))"],
                         cwd=project, env=env, capture_output=True, text=True, timeout=300)
    return run.returncode, run.stdout + run.stderr, host


def _floor_line(log: str, tool: str) -> list[str]:
    return [l for l in log.splitlines() if l.startswith(f"ERROR: {tool} needs Ruby 3.2 or later (jsonui-cli 1.9.0)")]


def test_with_only_a_path_ruby_every_tool_names_it_and_a_pin_is_said_to_have_selected_nothing(tmp_path):
    project = _project(tmp_path, pins={"sjui": "3.2.2", "rjui": "3.2.2"}, root_pins={}, installed=["3.2.2"])
    rc, log, host = _jui_build(tmp_path, project, PLAIN_RUBY)
    assert rc == 1, log
    assert "ERROR: Build failed for: ios, android, web" in log, log
    assert "REACHED" not in log, log
    for platform, tool in TOOLS.items():
        lines = _floor_line(log, tool)
        assert len(lines) == 1, log
        root = (project / platform).resolve()
        assert f"and this is Ruby 2.6.10 at {host}" in lines[0], lines[0]
        assert f"Put a .ruby-version naming Ruby 3.2 or later in {root} " in lines[0], lines[0]
        # jui passed the tool's pin (3.2.2 is "installed"); with no rbenv it chose nothing.
        pinned = tool in ("sjui", "rjui")
        note = " (RBENV_VERSION=3.2.2, but rbenv did not start this ruby)"
        assert (f"at {host}{note}." in lines[0]) is pinned, lines[0]
        assert (f"at {host}." in lines[0]) is not pinned, lines[0]


def test_under_rbenv_a_tool_directory_without_a_pin_falls_to_system_and_is_named(tmp_path):
    # kjui_tools carries no .ruby-version today; sjui_tools and rjui_tools pin 3.2.2.
    project = _project(tmp_path, pins={"sjui": "3.2.2", "rjui": "3.2.2"}, root_pins={}, installed=["3.2.2"])
    rc, log, host = _jui_build(tmp_path, project, RBENV_RUBY)
    assert rc == 1, log
    assert "ERROR: Build failed for: android" in log, log
    assert "REACHED sjui" in log and "REACHED rjui" in log, log
    assert not _floor_line(log, "sjui") and not _floor_line(log, "rjui"), log
    lines = _floor_line(log, "kjui")
    assert len(lines) == 1 and f"and this is Ruby 2.6.10 at {host} (rbenv chose system)." in lines[0], log
    assert "REACHED kjui" not in log, log


def test_under_rbenv_a_pin_that_is_not_installed_falls_to_system_too(tmp_path):
    # build_tool_env passes a pin only when rbenv has it: 3.2.2 is not installed here.
    project = _project(tmp_path, pins={"sjui": "3.2.2", "rjui": "3.2.2"}, root_pins={}, installed=[])
    rc, log, host = _jui_build(tmp_path, project, RBENV_RUBY)
    assert rc == 1 and "ERROR: Build failed for: ios, android, web" in log, log
    for tool in TOOLS.values():
        lines = _floor_line(log, tool)
        assert len(lines) == 1 and "(rbenv chose system)." in lines[0], log


def test_under_rbenv_a_ruby_version_in_the_platform_root_is_what_a_face_writes_to_pass(tmp_path):
    # The remedy the line names: a .ruby-version where the tool is started.
    project = _project(tmp_path, pins={"sjui": "3.2.2", "rjui": "3.2.2"}, root_pins={"android": "3.3.1"},
                       installed=["3.2.2", "3.3.1"])
    rc, log, _host = _jui_build(tmp_path, project, RBENV_RUBY)
    assert rc == 0, log
    assert all(f"REACHED {tool}" in log for tool in TOOLS.values()), log
    assert not any(_floor_line(log, tool) for tool in TOOLS.values()), log
