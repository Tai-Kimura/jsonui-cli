"""No browser-test fixture writes a fixed date (2.3.5; ticket 2026-10-20-jui-viz-hist-wide-robot-margin-red-on-integrate).

A session's start is its transcript's first record, and the page draws a robot tired 8 hours after it (a wider pose).
hist-wide's transcript was dated 2026-10-19 09:00Z: from 02:00 JST on 10-20 its robots were tired and the margin arms
went red on every tree — what a suite checked depended on the clock. Fixtures under tools/viz_e2e write their times
through common.stamp() (09:00 plus an offset → that offset after an hour before the run) or common.ago() (a session
meant to be old: ago(hours=9)). This arm reads the suites as text and fails on an ISO date-time or an epoch-ms literal
that is not the argument of stamp( on its line, unless it is in ALLOWED with the reason it does not reach a session's
start.
"""
from __future__ import annotations

import re
from pathlib import Path

E2E = Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
EPOCH_MS = re.compile(r"\b1_?[5-9]\d{2}(?:_?\d{3}){3}\b")
IN_STAMP = re.compile(r"stamp\(f?\"\d{4}-\d{2}-\d{2}T")
# (file, a piece of the line) -> why that fixed time never becomes a session's start
ALLOWED = {
    ("scenarios.py", "T0 = 1_760_000_000_000"): "the fake server's event and slice times; no session gets a start (since) "
                                                 "from them — the building scenario's tired sessions use now - 9 h",
    ("hooks.py", "T0 = 1_760_000_000_000"): "the replay record's clock: the server replays the gaps between records, and "
                                             "the replayed sessions have no transcript, so no start",
    ("common.py", '("2026-10-19T09:47:10Z")'): "stamp()'s own docstring, the example of a time it moves",
    ("talk_demo_gen.py", "BASE = 1_792_300_000_000"): "the talk view's demo data's base: the demo page moves every time by "
                                                       "(its clock - base) (30-source-demo.js talkStandIn), and the file must "
                                                       "be the same each time it is generated; no session, no transcript",
}


def offenders(folder: Path = E2E) -> list[tuple[str, int, str]]:
    out = []
    for path in sorted(folder.glob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            iso = [m for m in ISO.finditer(line)]
            bare_iso = len(iso) > len(IN_STAMP.findall(line))
            if not (bare_iso or EPOCH_MS.search(line)):
                continue
            if any(path.name == f and piece in line for f, piece in ALLOWED):
                continue
            out.append((path.name, n, line.strip()[:120]))
    return out


def test_no_fixture_writes_a_fixed_date():
    assert offenders() == []


def test_every_allowance_still_names_a_line():
    """An allowance whose line is gone is removed, not kept as a hole."""
    for (f, piece), why in ALLOWED.items():
        assert why and piece in (E2E / f).read_text(encoding="utf-8"), (f, piece)


def test_the_check_catches_a_fixed_date(tmp_path):
    (tmp_path / "suite.py").write_text('rec = {"timestamp": "2026-10-19T09:00:00Z"}\nok = stamp("2026-10-19T09:00:01Z")\n'
                                       'T1 = 1_760_000_000_000\nT2 = 1760000000000\n', encoding="utf-8")
    assert [n for _, n, _ in offenders(tmp_path)] == [1, 3, 4]
