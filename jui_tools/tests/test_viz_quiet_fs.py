"""The viz readers ask about paths through quiet_fs (ticket 2026-10-23-viz-data-docs-is-file-raises-einval-during-a-swap).

On macOS a stat of a path swapped between a file and a symlink fails with EINVAL, and Python 3.11 to 3.13's
Path.is_file / is_dir / exists / is_symlink raise it: one swap ended data_docs.read. quiet_fs answers False instead, as
3.14 does. The readers of files other programs write (READERS, a closed list, and every module under viz/sources) do not
call those Path methods themselves.
"""
from __future__ import annotations

import ast
import errno
import os
from pathlib import Path

import pytest

from jui_cli.viz import quiet_fs

VIZ = Path(__file__).resolve().parents[1] / "jui_cli" / "viz"
CALLS = {"is_file", "is_dir", "exists", "is_symlink"}
# the modules that read what a person, an editor, a test runner or a session writes
READERS = {"data_docs.py", "infra_cost.py", "ingest.py", "sheet.py", "spirits.py", "talk.py"}


def _reader_files() -> list[Path]:
    return sorted([VIZ / name for name in READERS] + list((VIZ / "sources").glob("*.py")))


def test_every_reader_named_is_there():
    assert all(p.is_file() for p in _reader_files()), [p for p in _reader_files() if not p.is_file()]


def test_no_reader_asks_a_path_directly():
    found = []
    for path in _reader_files():
        src = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in CALLS):
                continue
            receiver = ast.get_source_segment(src, node.func.value) or ""
            if receiver in ("quiet_fs", "os.path") or node.args or node.keywords:   # os.path and DirEntry(…=False) never raise it
                continue
            found.append(f"{path.relative_to(VIZ)}:{node.lineno} {receiver}.{node.func.attr}()")
    assert found == [], "use quiet_fs.<call>(path): " + ", ".join(found)


def test_the_guard_finds_a_direct_call(tmp_path, monkeypatch):
    """The positive control: a reader calling Path.is_file() itself is found."""
    fake = tmp_path / "viz"
    (fake / "sources").mkdir(parents=True)
    for name in READERS:
        (fake / name).write_text("")
    (fake / "sources" / "x.py").write_text("from pathlib import Path\nok = Path('a').is_file()\n")
    monkeypatch.setitem(globals(), "VIZ", fake)
    with pytest.raises(AssertionError, match=r"sources/x.py:2 Path\('a'\).is_file\(\)"):
        test_no_reader_asks_a_path_directly()


@pytest.mark.parametrize("call", sorted(CALLS))
def test_an_error_from_the_stat_is_not_there(call, tmp_path, monkeypatch):
    real = tmp_path / "doc.json"
    real.write_text("{}")
    link = tmp_path / "link"
    link.symlink_to(real)
    present = link if call == "is_symlink" else (tmp_path if call == "is_dir" else real)
    assert getattr(quiet_fs, call)(present) is True

    def einval(*args, **kwargs):
        raise OSError(errno.EINVAL, "Invalid argument", str(args[0]))

    monkeypatch.setattr(os, "stat", einval)
    monkeypatch.setattr(os, "lstat", einval)
    assert getattr(quiet_fs, call)(present) is False
