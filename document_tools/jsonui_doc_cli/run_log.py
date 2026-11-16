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
import sys

#: Quoted from `jui_cli/commands/build_cmd.py`, which calls it "the only thing
#: that counts". Not redefined — an expression of our own would be a second
#: opinion about what a warning looks like.
COUNTING_RE = re.compile(r"warning \[|warning:|\[warn|⚠", re.I)

_emitted: list[str] = []
#: Of the emitted lines, those a mouth declared STRUCTURAL — fired by design on
#: every run of a given shape, not by anything going wrong — keyed by kind.
#: They stay in `_emitted` (the gate's expression counts them, so the total
#: must too); this only lets the closing line say how many of N are that kind,
#: so a multi-app face can read `N − M == 0` as clean. Reported 2026-09-10 by
#: such a face: with `--app`, N was never 0.
_structural: dict[str, int] = {}
#: True between `begin()` and `end()` — a CLI command owns the tally, and a
#: `reset()` from inside the run (generate_html_directory's accounting
#: reset) must not throw away what the command already emitted.
_open: bool = False
#: Every line the command wrote to stdout/stderr between `begin()` and `end()`
#: — the window the reader's grep sees. The gate's expression also matches
#: DATA: a face's test NAME carrying "warning:" was printed by the shared-slot
#: listing, the reader counted 2 where the closing line said 1, and no
#: fixture's name had ever carried the token (2026-09-10). Bending the data
#: so the expression misses it would dull the instrument; instead the tool
#: applies the reader's expression to its own output and the closing line
#: says how many lines the gate will count that are not warnings.
_captured: list[str] = []
#: Physical lines `warn()` printed, so a captured line is not counted twice.
_warned_lines: set[str] = set()
_tees: list[tuple[str, "_Tee"]] = []


class _Tee:
    """Passes every write through and keeps each completed line."""

    def __init__(self, stream):
        self._stream = stream
        self._partial = ""

    def write(self, s):
        n = self._stream.write(s)
        self._partial += s
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            _captured.append(line)
        return n

    def flush(self):
        self._stream.flush()

    def close_partial(self) -> None:
        if self._partial:
            _captured.append(self._partial)
            self._partial = ""

    def __getattr__(self, name):
        return getattr(self._stream, name)


def begin() -> None:
    """Start a command's tally. Called first thing by the CLI command, BEFORE
    any warning it prints on its own (`--figma` missing, a config that will
    not read, no jui.config.json): those fired ahead of
    `generate_html_directory`, whose reset then dropped them, and the
    closing line printed a confident number one to two short of the gate's
    (measured over 4 runs by a verification lane, 2026-09-10)."""
    global _open
    _emitted.clear()
    _structural.clear()
    _captured.clear()
    _warned_lines.clear()
    _open = True
    for attr in ("stdout", "stderr"):
        stream = getattr(sys, attr)
        if not isinstance(stream, _Tee):
            tee = _Tee(stream)
            setattr(sys, attr, tee)
            _tees.append((attr, tee))


def end() -> None:
    global _open
    _open = False
    # Unwrap only what is still ours: a test harness that swapped the stream
    # in between must get its own object back, not a stale tee.
    for attr, tee in _tees:
        tee.close_partial()
        if getattr(sys, attr) is tee:
            setattr(sys, attr, tee._stream)
    _tees.clear()


def warn(line: str, *, structural: str | None = None) -> None:
    """Print *line* and count it. Callers keep their own indentation and tag.

    `structural=<kind>` marks a line that fires by design on every run of some
    shape (today: the outside-writes notice on any `--app` run). It is still
    counted — the gate counts it — but the closing line can then show the
    breakdown. ⚠️ A declaration at the emit site, deliberately not a list here:
    a second mouth calling itself structural would let a real warning hide
    inside the "clean" reading, so an arm pins the number of such sites to one.
    """
    print(line)
    _emitted.append(line)
    _warned_lines.update(line.split("\n"))
    if structural:
        _structural[structural] = _structural.get(structural, 0) + 1


def count() -> int:
    """Warnings emitted since the last `reset()`."""
    return len(_emitted)


def emitted() -> list[str]:
    return list(_emitted)


def structural() -> dict[str, int]:
    """Structural warnings emitted since the tally began, by kind."""
    return dict(_structural)


def data_hits() -> list[str]:
    """Lines the command printed that the gate's expression matches and that
    did not go through `warn()` — printed DATA the reader's grep will count.

    Empty outside a command (`begin()`/`end()`): a library call has no window
    on the reader's stream and makes no claim about it.
    """
    return [ln for ln in _captured if COUNTING_RE.search(ln) and ln not in _warned_lines]


def reset() -> None:
    """Clear the tally — unless a command opened it with `begin()`, in which
    case the command's own warnings are part of this run and stay."""
    if not _open:
        _emitted.clear()
        _structural.clear()
        _captured.clear()
        _warned_lines.clear()
