"""The loop's share of a room's file changes stays small however many specs the room has (ticket
2026-11-13-viz-loop-stalls-on-spec-index): 2.5.31's serve stood 10 to 165 s six times in six hours on a busy machine,
in pathlib's hash under specs_touching (the spec index made again for each changed file) and in specs_for_test_file
(each saved result compared with every spec at a merge).

The arms count the work, not the time: (a) a watcher's change looks no spec up; (b) a robot's write to one spec makes
that spec's paths again, not every spec's; (c) tying many saved results reads each spec's names once. On 2.5.31 each
counts the room's size again per change or per result.
"""
from __future__ import annotations

import json
import pathlib
from pathlib import Path

import pytest

from tests.test_viz_files_off_the_loop import ROBOT, _room, _settle, _world

SPECS = 120
RELATED = 4


@pytest.fixture()
def big(tmp_path):
    root = _room(tmp_path, n=SPECS, related=RELATED)
    world, state, pid = _world(root, True)
    return root, world, world.jsonui[pid], pid


def _rewrite(spec: Path, n: int) -> None:
    data = json.loads(spec.read_text(encoding="utf-8"))
    data["metadata"]["description"] = f"d{n}"
    spec.write_text(json.dumps(data), encoding="utf-8")


def _specs(root: Path) -> list[Path]:
    return sorted((root / "docs" / "screens" / "json").glob("*.spec.json"))


def test_a_watchers_storm_looks_no_spec_up(big, monkeypatch):
    """A build rewriting the room's files: each change was applied on the loop with specs_touching, whose index was
    made again after every spec read (the specs' revision moved). Only a robot's write tags specs; a watcher's
    change (by None) has nothing to tag."""
    root, world, project, pid = big
    looked = []
    real = type(project).specs_touching
    monkeypatch.setattr(type(project), "specs_touching", lambda self, path: looked.append(path) or real(self, path))
    for i, spec in enumerate(_specs(root)[:40]):
        _rewrite(spec, i)
        world.file_changed(pid, str(spec), 1000 + i, by=None)
    _settle(world, 2000)
    assert looked == [], f"{len(looked)} lookups for 40 watcher changes"
    assert all(e.by is None for e in project.specs.values())


def test_a_robots_write_to_one_spec_makes_only_that_specs_paths_again(big, monkeypatch):
    """The index is made from each spec's own paths kept between builds: one spec read again makes its paths
    (relatedFiles under each root) and no other spec's. 2.5.31 made every spec's again: specs x relatedFiles x
    roots Paths joined and hashed on the loop, per write."""
    root, world, project, pid = big
    spec = _specs(root)[7]
    world.file_changed(pid, str(spec), 900, by=ROBOT)   # the index made once, every spec's paths
    _settle(world, 950)
    joins = [0]
    real = pathlib.PurePath.__truediv__

    def counted(self, key):
        joins[0] += 1
        return real(self, key)

    monkeypatch.setattr(pathlib.PurePath, "__truediv__", counted)
    _rewrite(spec, 1)
    world.file_changed(pid, str(spec), 1000, by=ROBOT)
    for job, _apply in list(world._files_jobs):
        job.result(timeout=60)
    joins[0] = 0
    world.tick(1100)                                    # the reading applied on the loop: specs_touching runs here
    monkeypatch.setattr(pathlib.PurePath, "__truediv__", real)
    sid = next(s for s, e in project.specs.items() if e.path == spec)
    assert project.specs[sid].by == ROBOT
    assert joins[0] <= 4 * RELATED, f"{joins[0]} Path joins on the loop for one spec's write ({SPECS} specs)"


def test_tying_saved_results_reads_each_specs_names_once(big, monkeypatch):
    """specs_for_test_file looks the names up in a table made once per change of the specs; 2.5.31 read every
    spec's file name and layoutFile for each saved result, at each merge."""
    root, world, project, pid = big
    reads = [0]
    real = pathlib.PurePath.name

    def counted(self):
        reads[0] += 1
        return real.fget(self)

    monkeypatch.setattr(pathlib.PurePath, "name", property(counted))
    for i in range(300):
        project.specs_for_test_file(f"tests/screens/s{i % SPECS}.test.json")
    monkeypatch.setattr(pathlib.PurePath, "name", real)
    assert reads[0] <= 3 * SPECS + 2 * 300, f"{reads[0]} name reads for 300 results over {SPECS} specs"
    assert project.specs_for_test_file("tests/screens/s3.test.json") == [
        s for s, e in project.specs.items() if e.path.name == "s3.spec.json"]
