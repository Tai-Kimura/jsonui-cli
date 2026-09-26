"""The three Ruby tools print a problem through their warning logger.

A bare Kernel#warn (or a direct $stderr / STDERR write) goes to stderr with no
warning spelling the tool's own count reads — jui build's comment gives it as
`grep -iE 'warning \\[|warning:|\\[warn|⚠'`. Every such site in sjui / kjui /
rjui's lib is found here by machine and must be one of the sites kept below,
each with its reason; a new one is red, and so is a kept one that is gone.

Measured 2026-09-26 (jsonui-cli 1.9.0): 24 sites. 16 now go through the
tool's logger — font weights and the font table (round 5), rjui's type-map
parse, the type converter's type_mapping.json / colors.json lines (through the
shared core's report_warning hook, which every tool routes to its logger),
its undefined-color line on each tool, sjui's and rjui's Collection lines and
sjui's attribute vocabulary. 8 are kept, below.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

WARN = re.compile(r"(?<![\w.:$@])warn(?![\w?!:=])\s*(\(|[\"'#@a-zA-Z_$%<])")
STDERR = re.compile(r"(\$stderr|STDERR)\s*(\.\s*(puts|print|write|printf)\b|<<)")
NOT_A_CALL = re.compile(r"\bdef\s+(self\.)?warn\b")

#: (file, a fragment of the line) -> why it stays.
KEPT = {
    ("kjui_tools/lib/cli/main.rb", 'warn "kjui watch: not implemented'):
        "a refused command's error, followed by exit 1 — not a build warning",
    **{(f"{tool}_tools/lib/core/type_converter_core.rb", 'warn "[TypeConverter] Warning: #{message}"'):
       "the shared core's report_warning default, for a profile with no logger; every tool "
       "overrides it with its Logger.warn" for tool in ("sjui", "kjui", "rjui")},
    ("sjui_tools/lib/swiftui/converter_factory.rb", 'STDERR.puts "[ConverterFactory] Loaded custom converters'):
        "a debug trace, printed only with DEBUG set",
    ("sjui_tools/lib/swiftui/converter_factory.rb", 'STDERR.puts "[Converter error] Failed to load'):
        "a debug trace, printed only with DEBUG set",
    ("sjui_tools/lib/swiftui/converter_factory.rb", 'STDERR.puts "  Backtrace:'):
        "a debug trace, printed only with DEBUG set",
    ("rjui_tools/lib/cli/commands/build_command.rb", "// which React would warn about on every render."):
        "not a call: text inside a TypeScript comment the build writes",
}


def scan(lines_by_file: dict[str, list[str]]) -> list[tuple[str, str]]:
    found = []
    for path, lines in lines_by_file.items():
        for line in lines:
            s = line.strip()
            if s.startswith("#"):
                continue
            if STDERR.search(line) or (WARN.search(line) and not NOT_A_CALL.search(line)):
                found.append((path, s))
    return found


def _lib() -> dict[str, list[str]]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "sjui_tools/lib", "kjui_tools/lib",
                          "rjui_tools/lib"], capture_output=True, text=True, check=True).stdout.split()
    return {p: (REPO / p).read_text(encoding="utf-8", errors="replace").splitlines()
            for p in out if p.endswith(".rb")}


def test_the_scanner_finds_what_it_is_for_and_not_a_logger_call():
    sample = {"x.rb": ['warn "a bare warning"', "  warn(message)", '$stderr.puts "x"', "STDERR.print x",
                       '$stderr << "x"', 'Core::Logger.warn "x"', "def warn(message)",
                       "add_structural_error(m, warn: true)", "warnings << w", "# warn 'in a comment'",
                       ":warn", "@warned = true"]}
    assert [s for _, s in scan(sample)] == ['warn "a bare warning"', "warn(message)", '$stderr.puts "x"',
                                            "STDERR.print x", '$stderr << "x"']


def test_every_bare_warn_or_stderr_write_in_lib_is_kept_with_its_reason():
    found = scan(_lib())
    matched = {key for key in KEPT for path, s in found if path == key[0] and key[1] in s}
    unexplained = [f"{path}: {s}" for path, s in found
                   if not any(path == k[0] and k[1] in s for k in KEPT)]
    gone = sorted(set(KEPT) - matched)
    assert not unexplained, "a problem printed past the tool's logger:\n" + "\n".join(unexplained)
    assert not gone, f"kept here, no longer in lib: {gone}"
    assert len(found) == len(KEPT), found
