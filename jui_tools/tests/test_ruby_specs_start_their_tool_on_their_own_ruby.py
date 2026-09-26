"""No spec of the three Ruby tools starts a child `ruby` from PATH.

A child started as `ruby` runs on whatever rbenv resolves: RBENV_VERSION,
else the .ruby-version above the child's cwd (a spec's tmpdir: none), else
the global. So the Ruby 2.6 leg ran the tool under test on 3.2.2 or on 2.6
depending on the shell it was launched from, and a 3.2.2 leg could run it on
2.6 — measured 2026-09-26 on sjui's g_commands spec: 0 or 6 failures of 70
on either ruby, by RBENV_VERSION alone. RbConfig.ruby is the interpreter
running the spec. 45 launches in 37 spec files were moved to it in jsonui-cli
1.9.0 (and three before, in the g_commands specs).

The same `ruby` can reach a launch through a name — `r = 'ruby'`, then
`Open3.capture2e(r, bin)` — which the line scan does not see (measured
2026-09-26: an entry spec with `system_ruby = 'ruby'` scanned 0). So a name
that holds the bare string `ruby` and is then launched in the same file is
found too. A name holding a path ('/usr/bin/ruby') is not PATH's ruby and is
left alone; so is RbConfig.ruby.
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


#: A name given the bare string `ruby`: `x = 'ruby'`, `x ||= "ruby"`,
#: `X = 'ruby'.freeze`, `let(:x) { 'ruby' }`, a parameter default
#: `x = 'ruby'` / `x: 'ruby'`. Only the whole string: '/usr/bin/ruby' and
#: 'ruby 3.2' are not held names of PATH's ruby.
HELD_RUBY = re.compile(r"""(?:\blet!?\(\s*:(\w+)\s*\)\s*\{\s*|(?<![\w@$.:])([A-Za-z_]\w*)\s*(?:\|\|=|=|:)\s*)"""
                       r"""(['"])ruby\3(?:\.freeze)?(?=\s*(?:[,)}#]|$))""")
#: What starts a process in a spec with its arguments: Open3.*, system /
#: spawn / exec, IO.popen, PTY.spawn, Process.spawn. A shell string (backticks,
#: %x) starts one too, but only a Ruby interpolation `#{name}` puts a name in
#: it — backticks in a description or a JS template literal are not a launch.
CALL_LAUNCH = re.compile(r"""\bOpen3\.|\b(?:system|spawn|exec)\b\s*\(?|\bIO\.popen|\bPTY\.spawn|\bProcess\.spawn""")
SHELL_LAUNCH = re.compile(r"""`|%x[\(\[{]""")


def held_launches(lines_by_file: dict[str, list[str]]) -> list[str]:
    """`path:N -> M: line` for a name holding the bare string `ruby` (line N)
    that a line M of the same file starts: as an argument of a launch, or as
    the first word of a command array (`[name, bin, ...]`)."""
    found = []
    for path, lines in lines_by_file.items():
        code = [(n, line) for n, line in enumerate(lines, 1) if not line.strip().startswith("#")]
        for n, line in code:
            for match in HELD_RUBY.finditer(line):
                name = match.group(1) or match.group(2)
                use = re.compile(rf"(?<![\w@$.:]){re.escape(name)}(?![\w?!:])")
                interpolated = re.compile(rf"#\{{\s*{re.escape(name)}\s*\}}")
                first_word = re.compile(rf"\[\s*{re.escape(name)}\s*,")
                for m, other in code:
                    if m == n:
                        continue
                    if (CALL_LAUNCH.search(other) and use.search(other)) \
                            or (SHELL_LAUNCH.search(other) and interpolated.search(other)) \
                            or first_word.search(other):
                        found.append(f"{path}:{n} -> {m}: {other.strip()}")
    return found


def findings(lines_by_file: dict[str, list[str]]) -> list[str]:
    """Both scans: `ruby` written at the launch, and a name holding it."""
    return launches(lines_by_file) + held_launches(lines_by_file)


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


def test_a_name_holding_ruby_is_found_where_it_is_launched():
    sample = {"v.rb": [
        "r = 'ruby'",                                              # 1
        "Open3.capture2e(r, File.join(tool, 'bin', 'sjui'))",      # 2  found
        "let(:ruby_bin) { \"ruby\" }",                              # 3
        "system(ruby_bin, bin, 'build')",                          # 4  found
        "child = 'ruby'.freeze",                                   # 5
        "cmd = [child, bin, 'build']",                             # 6  found (a command array)
        "shell_ruby = 'ruby'",                                     # 7
        "out = `#{shell_ruby} #{bin} build`",                      # 8  found
        "system_ruby = '/usr/bin/ruby'",                           # 9  a path: not PATH's ruby
        "Open3.capture3(env, system_ruby, bin)",                   # 10
        "own = RbConfig.ruby",                                     # 11
        "Open3.capture2e(own, bin)",                               # 12
        "label = 'ruby'",                                          # 13 held, never launched
        "expect(label).to eq('ruby')",                             # 14
        "# old = 'ruby'",                                          # 15 a comment
        "Open3.capture2e(old, bin)",                               # 16
    ]}
    assert held_launches(sample) == [
        "v.rb:1 -> 2: Open3.capture2e(r, File.join(tool, 'bin', 'sjui'))",
        "v.rb:3 -> 4: system(ruby_bin, bin, 'build')",
        "v.rb:5 -> 6: cmd = [child, bin, 'build']",
        "v.rb:7 -> 8: out = `#{shell_ruby} #{bin} build`",
    ]
    # The line scan alone sees none of the four: this is what it missed.
    assert launches(sample) == []


def test_no_spec_starts_its_tool_on_the_ruby_path_finds():
    files = subprocess.run(["git", "-C", str(REPO), "ls-files", "sjui_tools/spec", "kjui_tools/spec",
                            "rjui_tools/spec"], capture_output=True, text=True, check=True).stdout.split()
    specs = {p: (REPO / p).read_text(encoding="utf-8", errors="replace").splitlines()
             for p in files if p.endswith(".rb")}
    assert len(specs) > 100, "the scan found the spec trees"
    # One scan over the real specs and two planted ones, one per form: both
    # planted are reported by the same call that judges the tree. No spec holds
    # a bare 'ruby' in a name today, so this is what keeps that half wired here.
    planted = {"planted_line.rb": ["Open3.capture2e('ruby', bin)"],
               "planted_name.rb": ["r = 'ruby'", "Open3.capture2e(r, bin)"]}
    scanned = findings(dict(specs, **planted))
    assert [f.split(":")[0] for f in scanned if f.startswith("planted_")] == ["planted_line.rb", "planted_name.rb"]
    found = [f for f in scanned if not f.startswith("planted_")]
    assert not found, "use RbConfig.ruby — the ruby running this spec:\n" + "\n".join(found)
