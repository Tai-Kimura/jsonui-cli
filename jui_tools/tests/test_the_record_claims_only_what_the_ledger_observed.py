"""The record claims only what the ledger observed — three invariants.

Ticket: record-claims-are-assembled-from-scalars-so-the-record-series-cannot-close.
About sixty trains and thirty tickets between 1.8.8 and 1.8.70 were one
premise failing in different clothes: "the record claims, about the tree it
observed, only what it observed". The mechanism was structural — the numbers
the record stated were computed at their print sites and passed by hand, so
a claim never carried which tree, which roots or how many directories it
stood on, and `0` meant both "counted none" and "never looked".

These arms pin the fold that closes the series, and they are written so that
the POPULATION IS DERIVED, not listed:

  (a) NO SCALAR PORT. `save` and `coverage_line` take the ledger and nothing
      numeric. And every numeric leaf in the summary `save` writes must
      equal the same leaf of `ledger.claims()` — the test walks the summary
      it got, so a key added to the summary tomorrow is checked tomorrow
      without anyone editing a list here.
  (b) NOT OBSERVED IS A VALUE. A ledger that never scanned refuses `save`
      and `claims`, and `coverage_line` says NOT OBSERVED — it does not
      print the 0 that "nothing scanned" and "nothing found" used to share.
  (c) CLAIM ⊆ SCAN. The doc producer's scope is a boundary: a page outside
      it is refused. The build producer's scan is a union of enumerations,
      so there it is recorded instead — `scan.outsideDeclaredRoots` — and
      the count must match what the ledger was actually handed.

Each arm names the mutation that turns it red. Run them with the mutation
applied before trusting them (2026-09-11: all three went red on theirs).
"""

from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core import generation_manifest as gm


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


class _Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.gen = self.root / "app" / "Generated"
        self.files = [
            _write(self.root, "app/Generated/A.swift", "a"),
            _write(self.root, "app/Generated/B.swift", "b"),
            _write(self.root, "app/Views/HomeGeneratedView.swift", "h"),
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def _observed_ledger(self, *, roots=None) -> gm.GenerationRun:
        run = gm.GenerationRun(project_root=self.root, version="1.8.73")
        run.observe(self.files, roots=roots if roots is not None else (self.gen,))
        return run


class TestA_NoScalarPort(_Tree):
    """(a) numbers cannot be handed to the record; they are derived once."""

    def test_the_two_claim_functions_take_no_number(self):
        """Mutation: add `written: int = 0` to `coverage_line` → red.

        Signature-level, so the port cannot come back quietly: a parameter
        that a caller could fill with a number it computed at the print
        site is exactly what the series was made of.
        """
        for fn in (gm.save, gm.coverage_line):
            sig = inspect.signature(fn)
            params = list(sig.parameters.values())
            self.assertEqual(params[0].name, "ledger", fn.__name__)
            numeric = [p.name for p in params[1:]
                       if p.annotation in (int, "int", "int | None", float)]
            self.assertEqual(numeric, [], f"{fn.__name__} accepts a number: {numeric}")
            self.assertEqual(
                [p.name for p in params[1:] if p.kind is p.POSITIONAL_OR_KEYWORD],
                [], f"{fn.__name__} has positional slots after the ledger")

    def test_every_numeric_leaf_of_the_saved_summary_is_the_ledgers_own(self):
        """Mutation: in `save`, write `"tracked": len(files) + 1` → red.

        THE POPULATION IS THE SUMMARY ITSELF. The arm walks every key the
        saved summary contains (minus the producer's `run` block, which is
        the doc generator's own facts) and demands the same key with the
        same value from `ledger.claims()["summary"]`. A summary key that
        `claims()` does not derive is a number with a second source, and
        the arm fails on it by construction — no list to maintain here.
        """
        run = self._observed_ledger()
        run.written(self.files, known=set())
        run.note_distributed([self.files[0]])
        saved = gm.save(run, generated_by="test")
        summary = {k: v for k, v in saved["summary"].items() if k not in ("run",)}
        claimed = run.claims()["summary"]
        claimed["scan"] = run.claims()["scan"]
        for key, value in summary.items():
            if key.endswith("Note"):
                # "first 20 of N" — derived in save from the same lengths.
                continue
            self.assertIn(key, claimed, f"summary.{key} has no ledger derivation")
            self.assertEqual(claimed[key], value, f"summary.{key} differs from the ledger")
        # And the file on disk is what was returned, not a third copy.
        on_disk = json.loads(gm.manifest_path(self.root).read_text())
        self.assertEqual(on_disk["summary"], saved["summary"])

    def test_the_closing_lines_carry_the_same_numbers_as_the_summary(self):
        """Mutation: in `coverage_line`, print `s['tracked'] + 1` → red."""
        run = self._observed_ledger()
        run.written(self.files, known=set())
        run.note_distributed(self.files[:2])
        gm.save(run, generated_by="test")
        c = run.claims()
        text = gm.coverage_line(run)
        self.assertIn(f"{c['summary']['tracked']} tracked generated file(s)", text)
        self.assertIn(f"distributed to platforms: {c['run']['distributed']} file(s)", text)
        self.assertIn(f"recorded/updated {c['run']['written']}", text)

    def test_what_save_learns_lands_on_the_ledger_not_only_in_the_json(self):
        """Mutation: delete `ledger.dropped = dropped` in `save` → red.

        `jui build` used to read `dropped` / `untracked` / `collisions` back
        out of the JSON it had just written and pass them to the closing
        line. Now the line reads the ledger, so the ledger must be told.
        """
        run = self._observed_ledger()
        run.written(self.files, known=set())
        gm.save(run, generated_by="test")
        # Second run: one file gone.
        self.files[1].unlink()
        again = gm.GenerationRun(project_root=self.root, version="1.8.73")
        again.observe(self.files, roots=(self.gen,))
        again.written(self.files, known=set(gm.load_migrated(self.root)))
        saved = gm.save(again, generated_by="test")
        self.assertEqual(saved["summary"]["dropped"], 1)
        self.assertEqual(again.dropped, ["app/Generated/B.swift"])
        self.assertIn("dropped 1 entr(y/ies)", gm.coverage_line(again))


class TestB_NotObservedIsAValue(_Tree):
    """(b) a run that never scanned makes no claim, and says so."""

    def test_a_never_observed_ledger_refuses_to_save(self):
        """Mutation: make `observed` default to 0 instead of None → red."""
        run = gm.GenerationRun(project_root=self.root, version="1.8.73")
        self.assertIsNone(run.observed)
        with self.assertRaises(gm.NotObserved):
            gm.save(run)
        with self.assertRaises(gm.NotObserved):
            run.claims()
        with self.assertRaises(gm.NotObserved):
            run.written(self.files)

    def test_the_closing_line_says_not_observed_and_prints_no_zero(self):
        """Mutation: return the normal block with tracked=0 instead → red.

        `0 tracked generated file(s)` is the sentence every 1.8.69 ticket
        was about: the same zero from two different reasons.
        """
        run = gm.GenerationRun(project_root=self.root, version="1.8.73")
        text = gm.coverage_line(run)
        self.assertIn("NOT OBSERVED", text)
        self.assertNotIn("0 tracked", text)
        self.assertNotIn("recorded/updated", text)

    def test_an_observed_but_empty_scan_is_a_zero_with_a_denominator(self):
        """The other side of (b): a scan that ran and found nothing is 0,
        and the record says the scan ran (`scan.observed == 0`), so the
        two zeros are told apart IN THE RECORD, not by the reader.
        Mutation: drop `"scan"` from the saved summary → red."""
        run = gm.GenerationRun(project_root=self.root, version="1.8.73")
        run.observe([], roots=(self.gen,))
        run.written([], known=set())
        saved = gm.save(run, generated_by="test")
        self.assertEqual(saved["summary"]["tracked"], 0)
        self.assertEqual(saved["summary"]["scan"]["observed"], 0)
        self.assertEqual(saved["summary"]["scan"]["roots"], ["app/Generated"])


class TestC_ClaimWithinScan(_Tree):
    """(c) the record cannot claim wider than the run looked."""

    def test_the_doc_producer_refuses_a_page_outside_its_scope(self):
        """Mutation: remove `self._refuse_outside_roots(keys)` from
        `observe_written` → red."""
        run = gm.GenerationRun(project_root=self.root, version="1.8.73")
        with self.assertRaises(ValueError) as ctx:
            run.observe_written(["app/Generated/A.swift", "elsewhere/page.html"],
                                roots=(self.gen,))
        self.assertIn("elsewhere/page.html", str(ctx.exception))
        # The same keys inside the scope are accepted.
        run.observe_written(["app/Generated/A.swift"], roots=(self.gen,))
        self.assertEqual(run.written_keys, ["app/Generated/A.swift"])

    def test_the_build_producer_records_how_much_stands_outside_the_walked_dirs(self):
        """Mutation: in `written`, set `self.outside_roots = []` → red.

        The build's scan is a union of enumerations, so a present file
        outside the DIRECTORIES it walked is normal (the per-screen
        `*GeneratedView.swift` files). It is not refused; it is counted, so
        the record says how much of `tracked` the walked roots do not cover.
        """
        run = self._observed_ledger(roots=(self.gen,))
        run.written(self.files, known=set())
        self.assertEqual(run.outside_roots, ["app/Views/HomeGeneratedView.swift"])
        saved = gm.save(run, generated_by="test")
        self.assertEqual(saved["summary"]["scan"]["outsideDeclaredRoots"], 1)
        self.assertEqual(saved["summary"]["tracked"], 3)

    def test_undeclared_roots_are_recorded_as_undeclared_not_as_everything(self):
        """Mutation: make `roots` default to `(".",)` → red.

        A caller that declares nothing gets "not declared" in the record.
        Defaulting to the project root would make every claim look covered.
        """
        run = gm.GenerationRun(project_root=self.root, version="1.8.73")
        run.observe(self.files)
        run.written(self.files, known=set())
        saved = gm.save(run, generated_by="test")
        self.assertEqual(saved["summary"]["scan"]["roots"], "not declared")
        self.assertEqual(saved["summary"]["scan"]["outsideDeclaredRoots"], 0)


class TestTheVocabularyHasOneOwner(_Tree):
    """§3-4: a quantity's name is defined once, on the ledger."""

    def test_the_doc_run_facts_are_derived_from_collections(self):
        """Mutation: in `record_leftovers`, write `len(stale) + 1` → red.

        Seventeen `facts[...]` lines used to compute these in the doc
        generator. The ledger is handed the lists and derives the counts,
        the 20-item cuts and the "first 20 of N" notes itself.
        """
        run = gm.GenerationRun(project_root=self.root, version="1.8.73")
        run.observe_written(["app/Generated/A.swift"], roots=(self.gen,))
        stale = [self.root / f"app/Generated/old{i}.html" for i in range(25)]
        outside = [(self.root / "app/Generated/x.html", ["copy1"]),
                   (self.root / "other/y.html", ["copy2"])]
        run.record_leftovers(stale, outside, walked_dirs=["d1", "d2", "d3", "d4"],
                             colliding_sources=["dup"], referrers={})
        f = run.run_facts()
        self.assertEqual(f["leftovers"], 25)
        self.assertEqual(len(f["leftoverPaths"]), 20)
        self.assertEqual(f["leftoverPathsNote"], "first 20 of 25")
        self.assertEqual(f["leftoversOutside"], 1)           # under app/Generated
        self.assertEqual(f["leftoversOutsideElsewhere"], 1)  # other/
        self.assertEqual(f["leftoversOutsideScanned"], 4)
        self.assertEqual(f["collidingSourceNames"], ["dup"])

    def test_a_producer_with_no_facts_carries_the_previous_block(self):
        """Mutation: in `save`, treat `run_facts is None` as `{}` → red."""
        doc = gm.GenerationRun(project_root=self.root, version="1.8.73")
        doc.observe_written(["app/Generated/A.swift"], roots=(self.gen,))
        doc.record_apps(["web"])
        doc.record_time("2026-09-11T00:00:00Z")
        gm.save(doc, generated_by="jsonui-doc generate html")
        build = self._observed_ledger()
        build.written(self.files, known=set(gm.load_migrated(self.root)))
        saved = gm.save(build, generated_by="jui build")
        self.assertEqual(saved["summary"]["run"]["apps"], ["web"])
        self.assertEqual(saved["summary"]["run"]["recordedBy"], "jsonui-doc generate html")


if __name__ == "__main__":
    unittest.main()
