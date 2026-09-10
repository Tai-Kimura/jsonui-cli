"""One tally for every warning `jsonui-doc` prints, so the closing line can count them.

The closing line of `generate html` never carried a warning count. What a face
read as "warning 5" at 1.8.63 was its own `grep` over the log, and the count
"disappeared" when five lines were respelled `Warning:` → `WARNING [doc-…]:`
and the face's expression matched the old spelling only. A count that lives in
the reader's grep changes whenever the writer changes a word. So the writer
counts: every warning goes through `warn()` here, and `generation_summary_line`
prints the total — 0 included, because "0 warnings" and "nobody counted" must
not print the same.

⚠️ THE SPELLING IS THE GATE'S, NOT OURS. `jui build`'s rulebook counts with
`grep -iE 'warning \\[|warning:|\\[warn|⚠'`. A line that `warn()` emits but
that expression would not count is a warning the gate cannot see, and the two
totals would drift apart in exactly the way this module exists to stop; the
arm that checks every emitted line against COUNTING_RE is that contract. It
cuts the other way too: the `⚠️ Also written OUTSIDE` notice IS counted by the
gate, so it goes through here whether or not anyone thought of it as a warning.

A leaf module on purpose. `test_doc/generator.py`, `test_doc/mermaid/generator.py`
and `cli.py` all emit, and the first imports the second.
"""

from __future__ import annotations

import re

#: Quoted from `jui_cli/commands/build_cmd.py`, which calls it "the only thing
#: that counts". Not redefined — an expression of our own would be a second
#: opinion about what a warning looks like.
COUNTING_RE = re.compile(r"warning \[|warning:|\[warn|⚠", re.I)

_emitted: list[str] = []
#: True between `begin()` and `end()` — a CLI command owns the tally, and a
#: `reset()` from inside the run (generate_html_directory's accounting
#: reset) must not throw away what the command already emitted.
_open: bool = False


def begin() -> None:
    """Start a command's tally. Called first thing by the CLI command, BEFORE
    any warning it prints on its own (`--figma` missing, a config that will
    not read, no jui.config.json): those fired ahead of
    `generate_html_directory`, whose reset then dropped them, and the
    closing line printed a confident number one to two short of the gate's
    (measured over 4 runs by a verification lane, 2026-09-10)."""
    global _open
    _emitted.clear()
    _open = True


def end() -> None:
    global _open
    _open = False


def warn(line: str) -> None:
    """Print *line* and count it. Callers keep their own indentation and tag."""
    print(line)
    _emitted.append(line)


def count() -> int:
    """Warnings emitted since the last `reset()`."""
    return len(_emitted)


def emitted() -> list[str]:
    return list(_emitted)


def reset() -> None:
    """Clear the tally — unless a command opened it with `begin()`, in which
    case the command's own warnings are part of this run and stay."""
    if not _open:
        _emitted.clear()
