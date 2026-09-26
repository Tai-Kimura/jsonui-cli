"""No spec of the three Ruby tools starts a child `ruby` from PATH.

A child started as `ruby` runs on whatever rbenv resolves: RBENV_VERSION,
else the .ruby-version above the child's cwd (a spec's tmpdir: none), else
the global. So the Ruby 2.6 leg ran the tool under test on 3.2.2 or on 2.6
depending on the shell it was launched from, and a 3.2.2 leg could run it on
2.6 — measured 2026-09-26 on sjui's g_commands spec: 0 or 6 failures of 70
on either ruby, by RBENV_VERSION alone. RbConfig.ruby is the interpreter
running the spec. 45 launches in 37 spec files were moved to it in jsonui-cli
1.9.0 (and three before, in the g_commands specs).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: `ruby` as the program: an argument list's first word ('ruby', / "ruby",),
#: a %w[] list, backticks, system(), or a command string that begins with it
#: and goes on with an interpolation, a flag or a path (not text like
#: 'ruby 3.2').
PATH_RUBY = re.compile(r"""(['"])ruby\1\s*,|%w\[\s*ruby\b|`ruby\s|(["'])ruby\s+(#\{|-|/|\w+/)"""
                       r"""|\bsystem\(\s*(['"])ruby\b""")


def launches(lines_by_file: dict[str, list[str]]) -> list[str]:
    return [f"{path}:{n}: {line.strip()}"
            for path, lines in lines_by_file.items()
            for n, line in enumerate(lines, 1)
            if not line.strip().startswith("#") and PATH_RUBY.search(line)]


def test_the_scanner_finds_every_spelling_and_not_rbconfig():
    sample = {"s.rb": [
        "Open3.capture2e('ruby', File.join(tool, 'bin', 'sjui'), 'build')",
        'cmd = ["ruby", bin, *args]',
        "Open3.capture2e(env, 'ruby', bin)",
        "system('ruby', '-e', script)",
        "out = `ruby #{bin} build`",
        "Open3.capture2e(\"ruby #{bin} build\")",
        "%w[ruby -e 1]",
        "Open3.capture2e(RbConfig.ruby, bin)",
        "# 'ruby', in a comment",
        "expect(said).to include('ruby 3.2')",
        "RUBY_VERSION",
    ]}
    assert [line.split(": ", 1)[1] for line in launches(sample)] == sample["s.rb"][:7]


def test_no_spec_starts_its_tool_on_the_ruby_path_finds():
    files = subprocess.run(["git", "-C", str(REPO), "ls-files", "sjui_tools/spec", "kjui_tools/spec",
                            "rjui_tools/spec"], capture_output=True, text=True, check=True).stdout.split()
    specs = {p: (REPO / p).read_text(encoding="utf-8", errors="replace").splitlines()
             for p in files if p.endswith(".rb")}
    assert len(specs) > 100, "the scan found the spec trees"
    found = launches(specs)
    assert not found, "use RbConfig.ruby — the ruby running this spec:\n" + "\n".join(found)
