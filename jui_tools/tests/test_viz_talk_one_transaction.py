"""talk.db is written in one transaction a step, and a step with nothing new writes nothing (ticket
2026-11-24-viz-talk-db-autocommit-floods-fsevents).

talk.db keeps SQLite's rollback journal (DELETE): every transaction makes and removes talk.db-journal, and a statement
outside BEGIN is a transaction of its own. The registry's names and sockets, the deaths and each file's offset were
written that way, row by row and every step even when nothing had changed, and fseventsd recorded each journal (about
230 a second, 58 % of the machine's file events). Arms: every write of a step is inside its transaction; a step with
nothing new changes no row and leaves talk.db as it was; a new name is still written, once; a step that fails is
rolled back and what it read is read again by the next one.
"""
from __future__ import annotations

import re

import pytest

from jui_cli.viz import talk as T
from tests.test_viz_talk import A, B, NAMES, T0, Box

WRITE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|REPLACE)\b", re.I)


class Writes:
    """The write statements the index runs, each with whether a transaction was open."""

    def __init__(self, db):
        self.db = db
        self.got: list[tuple[str, bool]] = []
        db.set_trace_callback(self.on)

    def on(self, sql: str) -> None:
        if WRITE.match(sql):
            self.got.append((sql.split()[0].upper() + " " + " ".join(sql.split()[1:5]), self.db.in_transaction))

    def take(self) -> list[tuple[str, bool]]:
        got, self.got = self.got, []
        return got


@pytest.fixture
def box(tmp_path):
    b = Box(tmp_path)
    b.step(T0)
    b.writes = Writes(b.index.db)
    yield b
    b.index.db.set_trace_callback(None)
    b.index.close()


def _talk(box, at):
    box.write(box.files[A], box.send(A, f"toolu_{at}", NAMES[B], "やあ", at),
              box.result(A, f"toolu_{at}", at + 100, msg_id=f"m{at}"))
    box.write(box.files[B], box.read_meta(B, at + 200, f"m{at}", A, "やあ"))


def test_every_write_of_a_step_is_inside_its_transaction(box):
    _talk(box, T0 + 1_000)
    box.alive.discard(B)                      # a death too: _deaths writes gone
    box.step(T0 + 2_000)
    got = box.writes.take()
    assert got, "the step wrote nothing: the arm reaches nothing"
    assert [s for s, inside in got if not inside] == []


def test_a_step_with_nothing_new_writes_nothing(box):
    _talk(box, T0 + 1_000)
    box.step(T0 + 2_000)
    box.writes.take()
    before, mtime = box.index.db.total_changes, box.db.stat().st_mtime_ns
    for i in range(3):
        box.step(T0 + 4_000 + i * 2_000)
    # statements that match no row (parts' names already as they are) may run; no row is changed, no page written
    assert [s for s, _ in box.writes.take() if not s.startswith("UPDATE parts SET name=")] == []
    assert box.index.db.total_changes == before and box.db.stat().st_mtime_ns == mtime


def test_a_new_name_is_written_once(box):
    box.writes.take()
    rows = box.rows
    box.index.read_registry = lambda: [dict(r, name="renamed-a1") if r["sessionId"] == A else r for r in rows()]
    box.step(T0 + 2_000)
    names = [s for s, _ in box.writes.take() if s.startswith("INSERT OR REPLACE INTO names")]
    assert len(names) == 1
    assert box.index.db.execute("SELECT sid FROM names WHERE kind='name' AND value='renamed-a1'").fetchone() == (A,)
    before = box.index.db.total_changes
    box.step(T0 + 4_000)
    assert [s for s, _ in box.writes.take() if s.startswith("INSERT")] == [] and box.index.db.total_changes == before


def test_a_failed_step_is_rolled_back_and_read_again(box, monkeypatch):
    _talk(box, T0 + 1_000)
    real = T.TalkIndex._apply
    monkeypatch.setattr(T.TalkIndex, "_apply", lambda self, obs, now: (_ for _ in ()).throw(RuntimeError("once")))
    with pytest.raises(RuntimeError):
        box.index.step(T0 + 2_000)
    assert box.index.db.in_transaction is False
    assert box.index.db.execute("SELECT count(*) FROM messages").fetchone() == (0,)
    monkeypatch.setattr(T.TalkIndex, "_apply", real)
    box.step(T0 + 3_000)
    [m] = box.messages(A, B)
    assert (m["id"], m["state"]) == (f"m-m{T0 + 1_000}", "read")
