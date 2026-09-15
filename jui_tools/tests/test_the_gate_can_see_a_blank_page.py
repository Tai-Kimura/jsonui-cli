"""A picture that goes blank must stop the gate, even when its hash cannot tell.

THE DEFECT THIS EXISTS FOR

The visual gate is `hamming(dhash(now), committed) > threshold`. A blank page
hashes to all zeros, so its distance from any baseline is exactly that
baseline's popcount — and every entry whose popcount is at or below the
threshold therefore stays green however empty its picture gets. Derived
2026-09-15 from the committed baselines, without opening a single image
(`hamming(h, 0) == popcount(h)`):

    ci/ios     115 of 867 entries blind,  96 of them draw something
    ci/android 106 of 816 entries blind,  97 of them draw something
    ci/web     221 of 818 entries blind, 218 of them draw something

THIS IS NOT HYPOTHETICAL. `visual_stability.py`'s own docstring records it
happening twice in the field: in conformance run 34878202456
`Web_html__static` rendered BLANK while its control rendered "Sample", and an
earlier ci bake caught the same race on the control side, "where
`control_Web.png` hashed to all zeroes". Both sat inside the threshold.

⚠️ LOWERING THE THRESHOLD CANNOT CLOSE IT. These entries are near-uniform by
construction, so no threshold that lets a normal render pass also catches them
emptying out. They need a different predicate — the ink count — asked only of
the population the hashes derive.

THE ARMS BELOW ARE THE CONTROL THAT WAS RUN ON THE REAL CORPUS, in the shape
that makes both conclusions appear in the same table: a blind fixture blanked
must be CAUGHT, a loud fixture blanked must be caught by the OTHER check and
not by this one, and an unchanged corpus must produce nothing at all. Measured
on ci/ios (867 pictures): blind 114, ink-checked 101, exempt 13, and ZERO
false positives on the unmutated corpus.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance.baseline import (
    INK_COLLAPSE_RATIO,
    blind_to_blanking,
    compare_platform,
    ink_file,
    popcount,
    update_baseline,
)

try:
    from PIL import Image

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover
    HAVE_PILLOW = False

BLANK = (255, 255, 255)


def _blank(path: Path) -> None:
    Image.new("RGB", (64, 64), BLANK).save(path)


def _faint(path: Path, ink_pixels: int) -> None:
    """A picture that is nearly uniform — so its hash is nearly all zeros —
    but is unmistakably not empty."""
    img = Image.new("RGB", (64, 64), BLANK)
    for i in range(ink_pixels):
        img.putpixel((i % 64, i // 64), (0, 0, 0))
    img.save(path)


def _loud(path: Path) -> None:
    """High-contrast stripes: a hash with a large popcount, i.e. NOT blind."""
    img = Image.new("RGB", (64, 64), BLANK)
    for x in range(0, 64, 2):
        for y in range(64):
            img.putpixel((x, y), (0, 0, 0))
    img.save(path)


# NOT gated on Pillow, deliberately: the DERIVATION is pure arithmetic on the
# committed hashes, and it is the half most likely to break silently. The
# python-suite job installs without [conformance] on purpose, so gating this
# too would leave CI with no arm on the population at all.
class TheBlindPopulationIsDerivedTests(unittest.TestCase):
    def test_it_is_exactly_the_entries_within_the_threshold_of_a_blank_page(self) -> None:
        hashes = {"faint": "0" * 62 + "1f", "loud": "f" * 64}
        self.assertEqual(popcount(hashes["faint"]), 5)
        self.assertEqual(popcount(hashes["loud"]), 256)
        self.assertEqual(blind_to_blanking(hashes, 8), ["faint"])
        # The boundary is the threshold itself, and it is inclusive: an entry
        # AT the threshold is still within it of a blank page.
        self.assertEqual(blind_to_blanking(hashes, 5), ["faint"])
        self.assertEqual(blind_to_blanking(hashes, 4), [])

    def test_the_population_follows_the_threshold_rather_than_a_list(self) -> None:
        """Nothing here is maintained by hand, so a threshold change moves it."""
        hashes = {f"h{i}": f"{(1 << i) - 1:064x}" for i in range(12)}
        self.assertEqual(len(blind_to_blanking(hashes, 8)), 9)   # popcount 0..8
        self.assertEqual(len(blind_to_blanking(hashes, 11)), 12)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class InkSeparatesBlankFromDrawnTests(unittest.TestCase):
    def test_a_blank_page_of_any_colour_has_zero_ink(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        for shade in ((255, 255, 255), (0, 0, 0), (17, 99, 200)):
            path = tmp / f"{shade[0]}.png"
            Image.new("RGB", (64, 64), shade).save(path)
            self.assertEqual(
                ink_file(path), 0, "ink must read the modal level, not 'not white'"
            )

    def test_a_drawn_page_has_ink(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        _faint(tmp / "f.png", 40)
        self.assertEqual(ink_file(tmp / "f.png"), 40)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class TheComparisonCatchesBlankingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.conf = self.tmp / "conformance"
        self.art = self.conf / "artifacts" / "web"
        self.art.mkdir(parents=True)
        (self.conf / "baselines" / "local").mkdir(parents=True)
        _faint(self.art / "faint.png", 400)
        _blank(self.art / "empty.png")
        _loud(self.art / "loud.png")
        self.names = ["faint.png", "empty.png", "loud.png"]
        update_baseline(self.conf, "web", artifacts_dir=self.art, env="local")
        self.baseline = self.conf / "baselines" / "local" / "web.hashes.json"

    def _compare(self):
        return compare_platform(
            self.conf, "web", self.names, artifacts_dir=self.art, env="local"
        )

    def test_the_bake_records_ink_for_every_entry_it_hashed(self) -> None:
        baked = json.loads(self.baseline.read_text())
        self.assertEqual(sorted(baked["ink"]), sorted(baked["hashes"]))
        self.assertEqual(baked["ink"]["empty.png"], 0)
        self.assertGreater(baked["ink"]["faint.png"], 0)

    def test_an_unchanged_corpus_reports_nothing(self) -> None:
        """The control that makes every arm below mean something."""
        c = self._compare()
        self.assertEqual(c.regressions, [])
        self.assertEqual(c.ink_regressions, [])
        self.assertIn("faint.png", c.blind)
        self.assertNotIn("loud.png", c.blind)
        self.assertGreater(c.ink_checked, 0, "an ink check that judged nothing passes vacuously")

    def test_a_blind_picture_going_blank_is_caught_and_hamming_misses_it(self) -> None:
        """THE TICKET. Both halves asserted together — a pass on the second
        assertion alone would be indistinguishable from the gate simply
        working, which is what the shipped README concluded."""
        _blank(self.art / "faint.png")
        c = self._compare()
        self.assertEqual(
            [r[0] for r in c.regressions],
            [],
            "if Hamming catches this, the fixture is not in the blind population "
            "and this arm is not measuring the defect",
        )
        self.assertEqual([(r[0], r[3]) for r in c.ink_regressions], [("faint.png", "collapsed")])

    def test_a_loud_picture_going_blank_is_left_to_hamming(self) -> None:
        """The boundary: the new predicate must not expand past its population."""
        _blank(self.art / "loud.png")
        c = self._compare()
        self.assertEqual([r[0] for r in c.regressions], ["loud.png"])
        self.assertEqual(c.ink_regressions, [], "loud.png is not blind — this is Hamming's job")

    def test_a_picture_recorded_as_empty_that_starts_drawing_is_caught(self) -> None:
        """The same blindness the other way round, and it costs nothing."""
        _faint(self.art / "empty.png", 300)
        c = self._compare()
        self.assertEqual([(r[0], r[3]) for r in c.ink_regressions], [("empty.png", "appeared")])

    def test_a_partial_collapse_under_the_declared_ratio_is_caught(self) -> None:
        _faint(self.art / "faint.png", 400 // INK_COLLAPSE_RATIO - 1)
        self.assertEqual([r[3] for r in self._compare().ink_regressions], ["collapsed"])

    def test_a_content_change_that_keeps_its_ink_is_not_called_blank(self) -> None:
        """A ratio, not a floor: ordinary redraws must not turn red, or the
        pressure to weaken this check starts on its first real run."""
        _faint(self.art / "faint.png", 380)
        self.assertEqual(self._compare().ink_regressions, [])


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class AbsenceIsReportedNotReadAsZeroTests(unittest.TestCase):
    """A baseline baked before ink existed must not claim coverage it lacks."""

    def test_a_pre_ink_baseline_reports_uncovered_and_judges_nothing(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        conf = tmp / "conformance"
        art = conf / "artifacts" / "web"
        art.mkdir(parents=True)
        (conf / "baselines" / "local").mkdir(parents=True)
        _faint(art / "faint.png", 400)
        # ⚠️ The corpus needs ONE picture that hashes blank, or the lane fails
        # the derivation's own premise and nothing is blind — which is a real
        # state (local/android) but a different one from the one this arm is
        # about. Every real lane that CAN be asked has such entries: 20 on
        # ci/ios, 11 on ci/android, 8 on ci/web.
        _blank(art / "already_empty.png")
        update_baseline(conf, "web", artifacts_dir=art, env="local")
        path = conf / "baselines" / "local" / "web.hashes.json"
        baked = json.loads(path.read_text())
        del baked["ink"]  # exactly what every baseline committed before today looks like
        path.write_text(json.dumps(baked))

        _blank(art / "faint.png")  # and now it goes blank
        c = compare_platform(
            conf, "web", ["faint.png", "already_empty.png"], artifacts_dir=art, env="local"
        )
        self.assertEqual(c.blank_check_unavailable, 0, "the lane must be askable here")
        self.assertEqual(c.ink_checked, 0)
        self.assertIn("faint.png", c.ink_uncovered)
        self.assertEqual(
            c.ink_regressions,
            [],
            "an absent ink record must not be read as zero — that would report a "
            "regression the baseline never measured",
        )
        # …and the uncovered count is what keeps that from reading as a pass.
        self.assertEqual(len(c.blind), 2)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class EveryBlindEntryLandsInExactlyOneBucketTests(unittest.TestCase):
    """Conservation. A blind entry that falls out of all four buckets is an
    entry nobody judged, and nothing else in this file would notice."""

    def test_checked_plus_uncovered_plus_exempt_accounts_for_the_population(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        conf = tmp / "conformance"
        art = conf / "artifacts" / "web"
        art.mkdir(parents=True)
        (conf / "baselines" / "local").mkdir(parents=True)
        (conf / "fixtures").mkdir()
        # One fixture the layout declares as animated, so it is exempt.
        (conf / "fixtures" / "spin.layout.json").write_text(
            json.dumps({"type": "View", "child": [{"type": "Indicator"}]})
        )
        (conf / "manifest.json").write_text(
            json.dumps(
                {
                    "fixtures": [
                        {"id": "Indicator_animating__true", "layout": "fixtures/spin.layout.json"}
                    ]
                }
            )
        )
        _faint(art / "Indicator_animating__true.png", 300)
        _faint(art / "faint.png", 400)
        _loud(art / "loud.png")
        _blank(art / "already_empty.png")   # the lane's proof that blank == zero
        names = sorted(p.name for p in art.glob("*.png"))
        update_baseline(conf, "web", artifacts_dir=art, env="local")

        c = compare_platform(conf, "web", names, artifacts_dir=art, env="local")
        self.assertEqual(
            c.ink_tolerated,
            ["Indicator_animating__true.png"],
            "the exemption must be NAMED — an unstated one is how a check empties out",
        )
        self.assertEqual(
            c.ink_checked + len(c.ink_uncovered) + len(c.ink_tolerated),
            len(c.blind),
            "a blind entry in no bucket is one nothing judged",
        )
        self.assertEqual(len(c.blind), 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class TheDerivationsOwnPremiseIsMeasuredPerLaneTests(unittest.TestCase):
    """`popcount <= threshold` is only the right question where a blank page
    hashes to zero — and that is a property of the LANE, not of dHash.

    🔴 THE DEFECT THIS EXISTS FOR. A lane that keeps chrome in the frame has
    that chrome in every hash, so an emptied fixture lands on the chrome-only
    hash rather than on zero. Measured 2026-09-15 on the committed baselines:
    ci/android crops (48,120) and derives 106 blind of 816; local/android takes
    NO crop, every one of the same 816 hashes sits at popcount >= 14, and the
    derivation returned **0** — which reads as full coverage and means "this
    question cannot be asked here".

    The test is an existence proof rather than a guess about the crop: an entry
    whose committed hash IS all zeros proves a blank picture reaches zero on
    this lane. Guessing from the crop fails in both directions — ci/web takes
    no crop and still reaches zero.
    """

    def _lane(self, painter, extra_blank: bool = False):
        tmp = Path(tempfile.mkdtemp())
        conf = tmp / "conformance"
        art = conf / "artifacts" / "web"
        art.mkdir(parents=True)
        (conf / "baselines" / "local").mkdir(parents=True)
        for i in range(3):
            painter(art / f"f{i}.png")
        if extra_blank:
            _blank(art / "blank.png")
        names = sorted(p.name for p in art.glob("*.png"))
        update_baseline(conf, "web", artifacts_dir=art, env="local")
        return conf, art, names

    def test_a_lane_where_nothing_hashes_blank_reports_unjudged_not_zero(self) -> None:
        conf, art, names = self._lane(_loud)
        c = compare_platform(conf, "web", names, artifacts_dir=art, env="local")
        self.assertEqual(c.blind, [], "the derivation must not run here")
        self.assertEqual(
            c.blank_check_unavailable,
            len(names),
            "an empty blind set on this lane must be reported as UNJUDGED, not as coverage",
        )
        self.assertGreater(c.blank_check_min_popcount, 0, "the evidence must be carried")
        self.assertEqual(c.ink_checked, 0)

    def test_one_blank_hashing_entry_is_enough_to_ask_the_question(self) -> None:
        """The boundary, and the reason the test is an existence proof: the
        SAME painter, plus one picture that does hash blank."""
        conf, art, names = self._lane(_loud, extra_blank=True)
        c = compare_platform(conf, "web", names, artifacts_dir=art, env="local")
        self.assertEqual(c.blank_check_unavailable, 0)
        self.assertIn("blank.png", c.blind)
        self.assertEqual(
            c.already_blank,
            ["blank.png"],
            "an entry whose committed hash IS the blank hash is its own category",
        )

    def test_the_premise_helper_answers_from_the_hashes_alone(self) -> None:
        from jui_cli.conformance.baseline import blanking_premise_holds

        self.assertFalse(blanking_premise_holds({"a": "f" * 64, "b": "1" * 64}))
        self.assertTrue(blanking_premise_holds({"a": "f" * 64, "b": "0" * 64}))
        self.assertFalse(blanking_premise_holds({}), "an empty corpus proves nothing")


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class OnlyNewNeverPairsAFreshInkWithACommittedHashTests(unittest.TestCase):
    """🔴 THE PAIRING THE COMMENT FORBIDS, ON THE VERY OPERATION THAT ADDS INK.

    The guard was `only_new and n not in new_names and n in prior_ink`, which
    stops guarding when the committed baseline has NO ink map — and that is the
    state of every baseline not yet re-baked since ink existed. In it, an
    only-new bake kept each committed hash (an older render) and attached
    today's ink to it, for the whole corpus. A fixture that had gone blank in
    between would have had its blank ink baked in, and the collapse check would
    be permanently blind to it.
    """

    def _bake_ground(self):
        tmp = Path(tempfile.mkdtemp())
        conf = tmp / "conformance"
        art = conf / "artifacts" / "web"
        art.mkdir(parents=True)
        (conf / "baselines" / "local").mkdir(parents=True)
        _faint(art / "old.png", 400)
        _blank(art / "zero.png")
        update_baseline(conf, "web", artifacts_dir=art, env="local")
        path = conf / "baselines" / "local" / "web.hashes.json"
        return conf, art, path

    def test_with_no_committed_ink_an_only_new_bake_leaves_old_entries_absent(self) -> None:
        conf, art, path = self._bake_ground()
        baked = json.loads(path.read_text())
        del baked["ink"]                       # a pre-ink baseline, exactly
        path.write_text(json.dumps(baked))

        _faint(art / "old.png", 12)            # it went nearly blank in between
        _faint(art / "brand_new.png", 300)     # and a new fixture arrived
        update_baseline(conf, "web", artifacts_dir=art, env="local", only_new=True)

        after = json.loads(path.read_text())
        self.assertNotIn(
            "old.png",
            after.get("ink", {}),
            "an entry that kept its COMMITTED hash must not be given TODAY's ink — "
            "that pairs two different renders and bakes the blank in",
        )
        self.assertIn("brand_new.png", after["ink"], "a genuinely new entry is measured")

    def test_with_committed_ink_an_only_new_bake_keeps_it(self) -> None:
        conf, art, path = self._bake_ground()
        committed = json.loads(path.read_text())["ink"]["old.png"]
        _faint(art / "old.png", 12)
        _faint(art / "brand_new.png", 300)
        update_baseline(conf, "web", artifacts_dir=art, env="local", only_new=True)
        after = json.loads(path.read_text())
        self.assertEqual(after["ink"]["old.png"], committed)
        self.assertIn("brand_new.png", after["ink"])

    def test_a_wholesale_bake_still_measures_everything(self) -> None:
        """The boundary: the fix must not have stopped ink being recorded."""
        conf, art, path = self._bake_ground()
        _faint(art / "old.png", 12)
        update_baseline(conf, "web", artifacts_dir=art, env="local")
        after = json.loads(path.read_text())
        self.assertEqual(after["ink"]["old.png"], 12)


@unittest.skipUnless(HAVE_PILLOW, "Pillow not installed (jui-tools[conformance])")
class AnUncoveredEntryIsStillMeasuredTests(unittest.TestCase):
    """Judging needs a committed value. Reporting does not.

    The first version returned from the uncovered branch without calling
    `ink_file`, so a run against a pre-ink baseline left no NUMBER anywhere —
    and a before/after pair across a fix ("does this picture stop being
    blank?") had nothing to subtract, because both sides said only
    "uncovered". That is the shape a lane hit while planning the android
    conformance-mobile run: the fixture it cares about is blind to the hash
    AND uncovered by ink, so neither instrument produced a value.
    """

    def _pre_ink_lane(self):
        tmp = Path(tempfile.mkdtemp())
        conf = tmp / "conformance"
        art = conf / "artifacts" / "web"
        art.mkdir(parents=True)
        (conf / "baselines" / "local").mkdir(parents=True)
        _faint(art / "faint.png", 400)
        _blank(art / "already_empty.png")   # the lane's proof that blank == zero
        update_baseline(conf, "web", artifacts_dir=art, env="local")
        path = conf / "baselines" / "local" / "web.hashes.json"
        baked = json.loads(path.read_text())
        del baked["ink"]
        path.write_text(json.dumps(baked))
        return conf, art, sorted(p.name for p in art.glob("*.png"))

    def test_an_uncovered_entry_reports_a_number(self) -> None:
        conf, art, names = self._pre_ink_lane()
        c = compare_platform(conf, "web", names, artifacts_dir=art, env="local")
        self.assertIn("faint.png", c.ink_uncovered)
        self.assertEqual(
            c.ink_measured_while_uncovered.get("faint.png"),
            400,
            "an uncovered entry must still carry its measured ink — without it a "
            "before/after pair has nothing to subtract",
        )
        self.assertEqual(c.ink_regressions, [], "measuring is not judging")

    def test_the_number_moves_when_the_picture_does(self) -> None:
        """The before/after subtraction this exists for, in one arm."""
        conf, art, names = self._pre_ink_lane()
        before = compare_platform(
            conf, "web", names, artifacts_dir=art, env="local"
        ).ink_measured_while_uncovered["faint.png"]
        _blank(art / "faint.png")
        after = compare_platform(
            conf, "web", names, artifacts_dir=art, env="local"
        ).ink_measured_while_uncovered["faint.png"]
        self.assertEqual((before, after), (400, 0))
