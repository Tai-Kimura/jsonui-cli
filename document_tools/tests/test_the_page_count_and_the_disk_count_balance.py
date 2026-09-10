"""`Generated N HTML files` and the `.html` on disk are different quantities.

Reported as "the two differ by one". They are not supposed to be equal: N is
what THIS run wrote, and the disk holds whatever is there — including pages a
previous run wrote and this one did not. The run already names that remainder
(`WARNING [doc-stale]` and `summary.run.leftovers`), so the difference has a
name before anyone goes looking for it.

🔻 THE ARM IS A CONSERVATION LAW, NOT AN EQUALITY.

    disk == tool - collisions + leftovers

An equality arm passes only on a pristine tree and goes red on every dirty
one, which teaches the reader to ignore it. Under the law the remainder is
always attributed to a term that exists in the record.

⚠️ THIS LAW ONLY REACHES THE `tool <= disk` SIDE. v1.8.67 reported tool 1066
against disk 1064 — the opposite sign, a different mechanism, still
unidentified, and deliberately NOT explained by this ticket (triage,
2026-09-11). An arm that quietly covered both signs would let that one be
read as closed.

📌 The two sides must come from different producers or the arm proves nothing:
`tool` is read from the run's own closing line, `disk` from a filesystem walk
that never consults the generator.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402


def _build_face(root: Path, screens: int = 3) -> tuple[Path, Path, list[str]]:
    """A small site: N screen tests, each with its own document page."""
    tests = root / "tests"
    tests.mkdir()
    docs = root / "docs" / "user"
    names = []
    for i in range(screens):
        name = f"s{i}"
        names.append(name)
        doc_rel = f"docs/user/screens/html/{name}.html"
        (tests / f"{name}.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios",
            "source": {"layout": name, "document": doc_rel},
            "metadata": {"name": f"{name} test", "description": "d"},
            "cases": [{"name": "c", "description": "c",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        page = root / doc_rel
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(f"<html><head><title>{name}</title></head>"
                        f"<body>{name}</body></html>", encoding="utf-8")
    (docs / "screens" / "json").mkdir(parents=True, exist_ok=True)
    return tests, docs, names


def _run(tests: Path, out: Path, root: Path, docs: Path,
         manifest_roots: list[dict] | None = None) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen.generate_html_directory(
            tests, out, "T",
            apps=[{"name": "user", "docs_path": str(docs)}],
            project_root=root, manifest_roots=manifest_roots)
        print(gen.generation_summary_line())
    return buf.getvalue()


def _tool_count(log: str) -> int:
    """The number the RUN printed. Not a recount — that is the whole point."""
    m = re.search(r"Generated (\d+) HTML files", log)
    assert m, f"the closing line is missing from the run's own output:\n{log}"
    return int(m.group(1))


def _disk_count(out: Path) -> int:
    """What is on disk under `-o`, walked without asking the generator."""
    return sum(1 for _ in out.rglob("*.html"))


def _manifest(root: Path) -> dict:
    path = root / ".jsonui-cli" / "generation-manifest.json"
    assert path.is_file(), f"no manifest at {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _terms(root: Path) -> tuple[int, int]:
    summary = _manifest(root)["summary"]
    run = summary.get("run") or {}
    assert "leftovers" in run, (
        "summary.run.leftovers is absent. Since 1.8.69 a zero is written "
        "explicitly, so an absent key means the record is older than this "
        "run — the law cannot be evaluated against it.")
    return int(summary["collisions"]), int(run["leftovers"])


def _assert_balances(log: str, out: Path, root: Path) -> tuple[int, int, int, int]:
    tool, disk = _tool_count(log), _disk_count(out)
    collisions, leftovers = _terms(root)
    residual = disk - (tool - collisions + leftovers)
    assert residual == 0, (
        "the page counts do not balance, and the remainder has no name:\n"
        f"  tool       {tool:4d}  (the run's own closing line, pages it wrote)\n"
        f"  disk       {disk:4d}  (rglob('*.html') under -o, {out})\n"
        f"  collisions {collisions:4d}  (manifest summary.collisions)\n"
        f"  leftovers  {leftovers:4d}  (manifest summary.run.leftovers)\n"
        f"  residual   {residual:+d}  = disk - (tool - collisions + leftovers)")
    return tool, disk, collisions, leftovers


def test_a_clean_run_balances_and_its_leftover_term_is_zero(tmp_path):
    """Baseline. On a pristine tree the law degenerates to equality — and it
    is asserted as a zero TERM, not as an absent one, so this arm can tell
    "nothing left over" from "leftovers were never measured"."""
    root = tmp_path
    tests, docs, _ = _build_face(root)
    out = root / "out"
    out.mkdir()
    log = _run(tests, out, root, docs)
    tool, disk, collisions, leftovers = _assert_balances(log, out, root)
    assert leftovers == 0, f"a pristine tree reported {leftovers} leftover(s)"
    assert tool == disk, (
        f"with every term zero the two counts must agree: tool {tool}, disk {disk}")
    assert tool > 0, "the run wrote nothing — the arm would balance vacuously"


def test_one_planted_leftover_moves_the_difference_by_exactly_one(tmp_path):
    """Positive control. The reported symptom, built on purpose.

    Without this, `test_a_clean_run_balances…` would also pass against an
    implementation that had no leftovers term at all.
    """
    root = tmp_path
    tests, docs, _ = _build_face(root)
    out = root / "out"
    out.mkdir()
    clean = _run(tests, out, root, docs)
    clean_tool, clean_disk = _tool_count(clean), _disk_count(out)

    stale = out / "screens" / "html" / "gone.html"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("<html><body>a page no test names</body></html>",
                     encoding="utf-8")
    # ⚠️ AND IT HAS TO BE OLD. `_is_leftover` requires both "not written by
    # this run" AND an mtime older than the run's start, so a page being
    # written by a concurrent process is not called a leftover. A file
    # planted a millisecond before the run fails the second condition — the
    # first fixture here did exactly that, balanced at leftovers 0, and the
    # arm read a correct implementation as a defect. A leftover is by
    # definition from an EARLIER run; the fixture has to be that shape.
    old = time.time() - 3600
    os.utime(stale, (old, old))

    log = _run(tests, out, root, docs)
    tool, disk, _collisions, leftovers = _assert_balances(log, out, root)

    assert leftovers == 1, f"the planted page was not named as a leftover: {leftovers}"
    assert disk - tool == 1, (
        f"the difference did not move by exactly one: "
        f"clean tool {clean_tool}/disk {clean_disk}, planted tool {tool}/disk {disk}")
    assert "not written by this run" in log, (
        "the run balanced but never said the leftover out loud:\n" + log)


def test_the_two_sides_come_from_different_producers(tmp_path):
    """A law whose sides share a source is arithmetic, not a measurement.

    `tool` is parsed out of the text the run printed; `disk` is a filesystem
    walk. Deleting a page after the run moves `disk` and leaves `tool` where
    it was — which is only true if they are measured separately.
    """
    root = tmp_path
    tests, docs, _ = _build_face(root)
    out = root / "out"
    out.mkdir()
    log = _run(tests, out, root, docs)
    tool_before, disk_before = _tool_count(log), _disk_count(out)

    victim = next(out.rglob("*.html"))
    victim.unlink()

    assert _tool_count(log) == tool_before, "the printed line changed under us"
    assert _disk_count(out) == disk_before - 1, (
        "the disk walk did not see the deletion, so it is not reading the disk")


# ------------------------------------------------------------ many roots ----
# ⚠️ EVERYTHING ABOVE IS A SINGLE-ROOT SHAPE, AND THE NEXT DEFECT IS NOT
# VISIBLE IN IT. One `-o` site is shared by every face in a run, and the
# leftover scan walks that one site — so EVERY root's manifest records the
# SAME leftover. Summing the term across faces counts one page as many.
# Measured on a real two-app tree: one planted page, `leftovers=1` in both
# manifests, same `leftoverPaths` entry, sum 2 (triage, 2026-09-11). The
# synthetic single-face fixture cannot produce it, which is why it is here.


def _two_manifest_roots(root: Path) -> list[dict]:
    a, b = root / "face_a", root / "face_b"
    for r in (a, b):
        (r / "docs").mkdir(parents=True, exist_ok=True)
    return [{"app": "face_a", "root": str(a)}, {"app": "face_b", "root": str(b)}]


def _plant_aged_leftover(out: Path, name: str = "gone.html") -> Path:
    stale = out / "screens" / "html" / name
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("<html><body>a page no test names</body></html>",
                     encoding="utf-8")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    return stale


def test_every_root_records_the_same_leftover_not_one_each(tmp_path):
    """The site is shared, so the term is a property of the run, not of a face."""
    root = tmp_path
    tests, docs, _ = _build_face(root)
    out = root / "out"
    out.mkdir()
    roots = _two_manifest_roots(root)
    _run(tests, out, root, docs, manifest_roots=roots)
    _plant_aged_leftover(out)
    _run(tests, out, root, docs, manifest_roots=roots)

    per_root = {}
    for entry in roots:
        run = _manifest(Path(entry["root"]))["summary"]["run"]
        per_root[entry["app"]] = (run["leftovers"], tuple(run.get("leftoverPaths", ())))
    assert len(set(per_root.values())) == 1, (
        f"the roots disagree about the run's leftovers, so the term is "
        f"ambiguous: {per_root}")
    (count, paths), = set(per_root.values())
    assert count == 1, f"one page was planted; the roots report {count}"
    assert len(roots) > 1, "this arm needs more than one root to mean anything"


def test_the_term_is_the_runs_value_and_summing_the_roots_breaks_the_law(tmp_path):
    """Negative control for the unit. Pins the trap, so nobody re-derives it.

    🔻 Read the term from ONE root (they agree, asserted above) rather than
    from a union of `leftoverPaths`: that list is capped at 20 per root, so a
    union is exact only below the cap and would undercount silently above it.
    """
    root = tmp_path
    tests, docs, _ = _build_face(root)
    out = root / "out"
    out.mkdir()
    roots = _two_manifest_roots(root)
    _run(tests, out, root, docs, manifest_roots=roots)
    _plant_aged_leftover(out)
    log = _run(tests, out, root, docs, manifest_roots=roots)

    tool, disk = _tool_count(log), _disk_count(out)
    runs = [_manifest(Path(e["root"]))["summary"]["run"] for e in roots]
    collisions = int(_manifest(Path(roots[0]["root"]))["summary"]["collisions"])
    shared = int(runs[0]["leftovers"])
    summed = sum(int(r["leftovers"]) for r in runs)

    assert disk == tool - collisions + shared, (
        f"the law does not close on the run's own value: tool {tool}, "
        f"disk {disk}, collisions {collisions}, leftovers {shared}")
    assert summed == shared * len(roots), (
        f"the double-count this arm exists for did not happen: "
        f"summed {summed}, shared {shared}, roots {len(roots)}")
    assert disk != tool - collisions + summed, (
        "summing the term across roots balanced, so this arm is no longer "
        "measuring the trap it was written for")
