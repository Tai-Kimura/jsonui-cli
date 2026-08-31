"""The rebuild trigger asked whether ANY generated file was fresh.

`_regenerate_stale_mocks` decides whether `generated/` needs rebuilding by
comparing mtimes. The aggregate was `max`:

    generated_at = max(mtime for every generated mock)
    if generated_at >= newest_input: return 0

which asks "has anything been generated since the inputs changed". One
file answers that for the whole directory, so a single fresh mock kept
every stale sibling stale.

The worst case is not a stale sibling, though. Editing or corrupting a
generated file RAISES its mtime, so the very act that breaks the tree
switches off the rebuild that would have repaired it — measured on a
consumer, who touched a hand-written mock (making the inputs newer) and
then damaged a generated one, and watched the gate stay green because the
damage was newer still.

`min` asks the question the caller means: is all of it at least as new as
the inputs.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.cli import _regenerate_stale_mocks
from jsonui_test_cli.mock.generate import GENERATED_DIR, generate

SPEC = {
    "openapi": "3.0.3",
    "paths": {
        f"/api/user/r{i}": {"get": {
            "operationId": f"op{i}",
            "responses": {"200": {"content": {"application/json": {"schema": {
                "type": "object", "properties": {"a": {"type": "string"}},
                "required": ["a"]}}}}},
        }} for i in range(3)
    },
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    swagger = tmp_path / "swagger.json"
    swagger.write_text(json.dumps(SPEC), encoding="utf-8")
    mocks = tmp_path / "tests" / "mocks"
    mocks.mkdir(parents=True)
    (tmp_path / "jui.config.json").write_text(json.dumps({
        "mock": {"swagger": ["swagger.json"], "mockDir": "tests/mocks"},
    }), encoding="utf-8")
    generate([str(swagger)], mocks)
    monkeypatch.chdir(tmp_path)
    return swagger, mocks


def _generated(mocks: Path) -> list[Path]:
    return sorted((mocks / GENERATED_DIR).rglob("*.mock.json"))


def _age(paths, seconds_ago: float) -> None:
    when = time.time() - seconds_ago
    for p in paths:
        os.utime(p, (when, when))


def _touch(path: Path, seconds_ahead: float = 10) -> None:
    when = time.time() + seconds_ahead
    os.utime(path, (when, when))


def test_a_current_tree_is_not_rebuilt(project):
    swagger, mocks = project
    _age([swagger], 3600)
    _age(_generated(mocks), 60)
    before = {p: p.stat().st_mtime for p in _generated(mocks)}

    assert _regenerate_stale_mocks(None) == 0
    assert {p: p.stat().st_mtime for p in _generated(mocks)} == before


def test_a_wholly_stale_tree_is_rebuilt(project):
    swagger, mocks = project
    _age(_generated(mocks), 3600)
    _touch(swagger, 0)

    _regenerate_stale_mocks(None)

    newest_input = swagger.stat().st_mtime
    assert all(p.stat().st_mtime >= newest_input for p in _generated(mocks))


def test_one_fresh_file_does_not_certify_its_stale_siblings(project):
    """`max` returned here, leaving two of three files a version behind."""
    swagger, mocks = project
    files = _generated(mocks)
    assert len(files) == 3
    _age(files, 3600)
    _touch(swagger, 0)
    _touch(files[0])  # one file newer than the swagger

    _regenerate_stale_mocks(None)

    newest_input = swagger.stat().st_mtime
    stale = [p.name for p in _generated(mocks)
             if p.stat().st_mtime < newest_input]
    assert stale == []


def test_damaging_a_generated_file_does_not_suppress_the_rebuild(project):
    """The reported shape: the write that breaks the tree is also the write
    that makes it look fresh."""
    swagger, mocks = project
    files = _generated(mocks)
    _age(files, 3600)
    _touch(swagger, 0)

    victim = files[1]
    data = json.loads(victim.read_text(encoding="utf-8"))
    data["scenarios"].pop("default")
    victim.write_text(json.dumps(data), encoding="utf-8")  # mtime now newest
    assert victim.stat().st_mtime > swagger.stat().st_mtime

    _regenerate_stale_mocks(None)

    restored = json.loads(victim.read_text(encoding="utf-8"))
    assert "default" in restored["scenarios"], "the damage survived the gate"


def test_an_empty_generated_tree_is_rebuilt(project):
    swagger, mocks = project
    for p in _generated(mocks):
        p.unlink()

    _regenerate_stale_mocks(None)

    assert len(_generated(mocks)) == 3


def test_a_deleted_file_is_restored_even_when_the_rest_are_fresh(project):
    """`max` could not see this either: the survivors were newer than the
    swagger, so the directory read as current while one route had no mock
    at all."""
    swagger, mocks = project
    files = _generated(mocks)
    _age([swagger], 3600)
    gone = files[2]
    gone.unlink()

    _regenerate_stale_mocks(None)

    assert gone.exists()
