"""`Generated N HTML files this run` is derived from the ledgers, not tallied.

Closure of `record-claims-are-assembled-from-scalars-so-the-record-series-
cannot-close`: after the fold (1.8.73) the manifest was derived from
`GenerationRun`, but the closing line still read a module counter that no
ledger had seen — the last place a count could disagree with the record
about the same run. Now the manifest writer fills a per-run record from what
the ledgers KEYED (`recorded` under some declared root, `outside` under
none) and the line reads that. What the ledger gained for this closure:
`GenerationRun.record_document_slots` derives the slot count, the first-20
listing and the "first 20 of N" note from the full key list, and
`generator._run_record` carries the ledgers' keying to the line.

🔻 THE KILL CONDITION IS A MUTATION OF THE COUNTER. Add a ghost to the page
counter after the run: the old line followed the counter (N+1), this one
follows the record (N). An arm that only compared the two on a clean run
would be green for the fixtures' reason.

⚠️ THE LINE SAYS WHICH SOURCE IT USED. With a record it carries `outside
declared roots K` (printed at zero); without one (no project root, no
`shared/core`) it falls back to the counter and carries no such clause — the
absence is the limit's name, not a silent fallback.
"""
from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))
sys.path.insert(0, str(REPO / "jui_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402

try:
    from jsonui_doc_cli import shared_core  # noqa: E402
    gm = shared_core.load("generation_manifest")
except Exception:  # pragma: no cover - the arm below names the skip
    gm = None


def _build_face(root: Path, screens: int = 3) -> tuple[Path, Path]:
    tests = root / "tests"
    tests.mkdir()
    docs = root / "docs" / "user"
    for i in range(screens):
        name = f"s{i}"
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
    return tests, docs


def _run(tests: Path, out: Path, root: Path | None, docs: Path) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen.generate_html_directory(
            tests, out, "T",
            apps=[{"name": "user", "docs_path": str(docs)}],
            project_root=root)
    return buf.getvalue()


def _n(line: str) -> int:
    m = re.search(r"Generated (\d+) HTML files this run", line)
    assert m, line
    return int(m.group(1))


def _outside(line: str) -> int | None:
    m = re.search(r"outside declared roots (\d+)", line)
    return int(m.group(1)) if m else None


def _manifest(root: Path) -> dict:
    return json.loads((root / ".jsonui-cli" / "generation-manifest.json")
                      .read_text(encoding="utf-8"))


needs_core = pytest.mark.skipif(gm is None, reason="shared/core not in this tree")


@needs_core
class TestTheLineReadsTheRecord:
    def test_on_a_clean_run_line_record_and_manifest_agree(self, tmp_path):
        tests, docs = _build_face(tmp_path)
        _run(tests, tmp_path / "out", tmp_path, docs)
        line = gen.generation_summary_line()
        rec = dict(gen._run_record)
        assert rec, "the manifest writer filled no record on a run with a root"
        assert _n(line) == rec["recorded"] + rec["outside"]
        assert _outside(line) == 0 == rec["outside"], line
        # The same number the manifest carries, from the same keying: the
        # scan block's `observed` is what `observe_written` was handed.
        # The doc producer's scan lives in ITS block (`summary.run.scan`);
        # `summary.scan` is the build's and a doc run must not write it.
        summary = _manifest(tmp_path)["summary"]
        assert summary["run"]["scan"]["observed"] == rec["recorded"] == gen.get_pages_written()
        assert summary["run"]["scan"]["outsideDeclaredRoots"] == 0
        assert "scan" not in summary, "a doc run wrote the build's scan slot"

    def test_a_ghost_in_the_counter_does_not_move_the_line(self, tmp_path):
        """The kill condition: the old line followed the counter."""
        tests, docs = _build_face(tmp_path)
        _run(tests, tmp_path / "out", tmp_path, docs)
        before = _n(gen.generation_summary_line())
        gen._pages_written.add((tmp_path / "ghost.html").resolve())
        assert gen.get_pages_written() == before + 1, "the mutation did not land"
        assert _n(gen.generation_summary_line()) == before, (
            "the closing line followed the page counter, not the ledgers' keying")

    def test_pages_under_no_declared_root_are_counted_as_outside(self, tmp_path):
        """`-o` outside the project: every page is written, none is keyed."""
        face = tmp_path / "face"
        face.mkdir()
        tests, docs = _build_face(face)
        elsewhere = tmp_path / "elsewhere"
        _run(tests, elsewhere, face, docs)
        line = gen.generation_summary_line()
        n = _n(line)
        assert n > 0
        assert _outside(line) == n, line
        assert gen._run_record == {"recorded": 0, "outside": n}
        assert _manifest(face)["summary"]["run"]["scan"]["observed"] == 0

    def test_without_a_record_the_line_falls_back_and_says_so(self, tmp_path):
        """No project root → no manifest → counter, and no `outside` clause."""
        tests, docs = _build_face(tmp_path)
        _run(tests, tmp_path / "out", None, docs)
        assert not gen._run_record
        line = gen.generation_summary_line()
        assert _n(line) == gen.get_pages_written()
        assert _outside(line) is None, line


@needs_core
class TestTheLedgerDerivesTheSlotFacts:
    """What was added to the ledger for this closure, exercised directly."""

    def _slots(self, keys):
        run = gm.GenerationRun(project_root=Path("/x"), version="t")
        run.record_document_slots(paths=40, declarations=50, shared_keys=keys)
        return run.run_facts()["documentSlots"]

    def test_more_than_twenty_shared_keys_are_truncated_and_noted(self):
        keys = [f"docs/p{i:02d}.html" for i in range(25)]
        s = self._slots(reversed(keys))
        assert s["sharedPaths"] == 25
        assert s["sharedPathKeys"] == sorted(keys)[:20]
        assert s["sharedPathKeysNote"] == "first 20 of 25"
        assert s["paths"] == 40 and s["declarations"] == 50

    def test_twenty_or_fewer_carry_no_note(self):
        s = self._slots(["b", "a", "c"])
        assert s["sharedPathKeys"] == ["a", "b", "c"]
        assert s["sharedPaths"] == 3
        assert "sharedPathKeysNote" not in s

    def test_zero_shared_is_an_explicit_zero(self):
        s = self._slots([])
        assert s["sharedPaths"] == 0 and s["sharedPathKeys"] == []

    def test_the_producer_no_longer_writes_the_note_itself(self):
        src = (REPO / "document_tools" / "jsonui_doc_cli" / "test_doc"
               / "generator.py").read_text(encoding="utf-8")
        assert "sharedPathKeysNote" not in src, (
            "the generator assembles the slot note beside the ledger again")
        assert "first 20 of" not in src.split("def _report_document_slots")[-1][:4000] \
            if "def _report_document_slots" in src else True
