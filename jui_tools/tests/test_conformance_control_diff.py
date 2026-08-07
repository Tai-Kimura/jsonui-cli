"""Fixture-vs-control comparison: did the attribute change anything?

The baseline check cannot answer this. It compares each screenshot against
that platform's previous screenshot, so an attribute the platform drops
renders the default, matches the default it recorded last time, and passes
forever — the exact hole that let `Button.image` ship broken on two platforms
with every gate green.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.conformance import baseline as baseline_mod
from jui_cli.conformance import control_diff as cd


def _png(path: Path, colour) -> None:
    """Write a solid-colour PNG, or skip the test when Pillow is absent."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - environment dependent
        raise unittest.SkipTest("Pillow not installed")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 24), colour).save(path)


def _gradient(path: Path, shift: int) -> None:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        raise unittest.SkipTest("Pillow not installed")
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (24, 24))
    img.putdata([
        ((x * 10 + shift * 120) % 256, 0, 0) for _ in range(24) for x in range(24)
    ])
    img.save(path)


MANIFEST = {
    "fixtures": [
        {
            "id": "Label/fontColor__static",
            "class": "visual",
            "platforms": ["ios", "android", "web"],
            "control": "__control/Label",
        },
        {
            "id": "Label/lineBreakMode__static",
            "class": "visual",
            "platforms": ["ios", "android", "web"],
            "control": "__control/Label",
        },
        {
            "id": "Button/text__static",
            "class": "visual",
            "platforms": ["ios"],
            "control": "__control/Button",
        },
        {
            "id": "__control/Label",
            "class": "visual",
            "platforms": ["ios", "android", "web"],
            "control": None,
            "isControl": True,
        },
        {
            "id": "__control/Button",
            "class": "visual",
            "platforms": ["ios", "android", "web"],
            "control": None,
            "isControl": True,
        },
    ]
}


class ControlDiffTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.artifacts = self.root / "artifacts" / "ios"
        self.artifacts.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _results(self, *ids):
        return {i: {"id": i, "screenshot": f"{i.replace('/', '_')}.png"} for i in ids}

    def _shot(self, fixture_id):
        return self.artifacts / f"{fixture_id.replace('/', '_')}.png"

    # -- the load-bearing case ------------------------------------------- #

    def test_identical_render_is_inert(self):
        """A dropped attribute renders exactly like the control."""
        _png(self._shot("__control/Label"), (10, 20, 30))
        _png(self._shot("Label/fontColor__static"), (10, 20, 30))

        r = cd.compare(
            self.root, "ios", MANIFEST,
            self._results("__control/Label", "Label/fontColor__static"),
            artifacts_dir=self.artifacts,
        )
        self.assertEqual(r.active, [])
        self.assertEqual([f for f, _ in r.inert], ["Label/fontColor__static"])

    def test_different_render_is_active(self):
        _gradient(self._shot("__control/Label"), 0)
        _gradient(self._shot("Label/fontColor__static"), 1)

        r = cd.compare(
            self.root, "ios", MANIFEST,
            self._results("__control/Label", "Label/fontColor__static"),
            artifacts_dir=self.artifacts,
        )
        self.assertEqual(r.active, ["Label/fontColor__static"])
        self.assertEqual(r.inert, [])

    def test_inert_fails_only_when_recorded(self):
        """The ratchet: implementing an attribute records it, and it may not
        silently stop working afterwards. An unrecorded inert fixture is
        reported but does not fail — a value equal to the platform default
        cannot differ, and failing on that is how a check gets switched off."""
        _png(self._shot("__control/Label"), (10, 20, 30))
        _png(self._shot("Label/fontColor__static"), (10, 20, 30))
        results = self._results("__control/Label", "Label/fontColor__static")

        unrecorded = cd.compare(
            self.root, "ios", MANIFEST, results, artifacts_dir=self.artifacts
        )
        self.assertEqual(unrecorded.regressions, [])
        self.assertTrue(unrecorded.ok)

        cd.ledger_path(self.root).write_text(
            cd.render_ledger({"Label/fontColor__static": {"ios"}}), encoding="utf-8"
        )
        recorded = cd.compare(
            self.root, "ios", MANIFEST, results, artifacts_dir=self.artifacts
        )
        self.assertEqual(recorded.regressions, ["Label/fontColor__static"])
        self.assertFalse(recorded.ok)

    # -- honesty about what was not measured ----------------------------- #

    def test_missing_control_screenshot_is_not_a_pass(self):
        _png(self._shot("Label/fontColor__static"), (10, 20, 30))
        r = cd.compare(
            self.root, "ios", MANIFEST,
            self._results("Label/fontColor__static"),
            artifacts_dir=self.artifacts,
        )
        self.assertEqual(r.no_control, ["Label/fontColor__static"])
        self.assertEqual(r.active, [])
        self.assertEqual(r.inert, [])

    def test_recorded_fixture_without_a_screenshot_is_unmeasured(self):
        cd.ledger_path(self.root).write_text(
            cd.render_ledger({"Label/fontColor__static": {"ios"}}), encoding="utf-8"
        )
        _png(self._shot("__control/Label"), (10, 20, 30))
        r = cd.compare(
            self.root, "ios", MANIFEST,
            self._results("__control/Label"),
            artifacts_dir=self.artifacts,
        )
        self.assertEqual(r.unmeasured, ["Label/fontColor__static"])
        self.assertEqual(r.inert, [])

    def test_a_recorded_fixture_with_no_control_is_unmeasured_not_ignored(self):
        """Otherwise a run whose controls failed to render reports
        "no regressions" for a comparison that never happened."""
        cd.ledger_path(self.root).write_text(
            cd.render_ledger({"Label/fontColor__static": {"ios"}}), encoding="utf-8"
        )
        _png(self._shot("Label/fontColor__static"), (10, 20, 30))
        r = cd.compare(
            self.root, "ios", MANIFEST,
            self._results("Label/fontColor__static"),
            artifacts_dir=self.artifacts,
        )
        self.assertEqual(r.unmeasured, ["Label/fontColor__static"])
        self.assertEqual(r.no_control, [])

    def test_platform_scoped_fixture_is_skipped_elsewhere(self):
        _png(self._shot("__control/Button"), (1, 2, 3))
        _png(self._shot("Button/text__static"), (1, 2, 3))
        r = cd.compare(
            self.root, "android", MANIFEST,
            self._results("__control/Button", "Button/text__static"),
            artifacts_dir=self.artifacts,
        )
        self.assertEqual(r.inert, [])
        self.assertEqual(r.active, [])

    def test_controls_are_not_compared_to_themselves(self):
        _png(self._shot("__control/Label"), (10, 20, 30))
        r = cd.compare(
            self.root, "ios", MANIFEST,
            self._results("__control/Label"),
            artifacts_dir=self.artifacts,
        )
        self.assertEqual(r.active, [])
        self.assertEqual(r.inert, [])
        self.assertEqual(r.no_control, [])

    # -- ledger ---------------------------------------------------------- #

    def test_ledger_roundtrips_and_is_deterministic(self):
        by_fixture = {"b/x__static": {"ios", "web"}, "a/y__static": {"web"}}
        first = cd.render_ledger(by_fixture)
        self.assertEqual(first, cd.render_ledger(by_fixture))
        path = cd.ledger_path(self.root)
        path.write_text(first, encoding="utf-8")
        self.assertEqual(cd.load_ledger_all(path), by_fixture)
        doc = json.loads(first)
        self.assertEqual(
            [e["fixture"] for e in doc["entries"]], ["a/y__static", "b/x__static"]
        )

    def test_a_ledger_entry_binds_only_the_platform_it_names(self):
        """web proving textAlign moves pixels says nothing about iOS, where the
        attribute may not be implemented at all."""
        path = cd.ledger_path(self.root)
        path.write_text(
            cd.render_ledger({"Label/fontColor__static": {"web"}}), encoding="utf-8"
        )
        self.assertEqual(cd.load_ledger(path, "web"), {"Label/fontColor__static"})
        self.assertEqual(cd.load_ledger(path, "ios"), set())

    def test_missing_ledger_reads_as_empty(self):
        self.assertEqual(cd.load_ledger(cd.ledger_path(self.root)), set())


if __name__ == "__main__":
    unittest.main()


class IgnoreBottomTest(unittest.TestCase):
    """ios home-indicator strip exclusion (PLATFORM_IGNORE_BOTTOM)."""

    def test_bottom_strip_difference_is_ignored(self):
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover - environment dependent
            raise unittest.SkipTest("Pillow not installed")
        import tempfile as _tf
        from pathlib import Path as _P
        from jui_cli.conformance.control_diff import diff_pixels

        with _tf.TemporaryDirectory() as tmp:
            a = Image.new("RGB", (100, 200), (255, 255, 255))
            b = Image.new("RGB", (100, 200), (255, 255, 255))
            for x in range(100):
                for y in range(190, 200):
                    b.putpixel((x, y), (0, 0, 0))
            pa, pb = _P(tmp) / "a.png", _P(tmp) / "b.png"
            a.save(pa)
            b.save(pb)
            self.assertGreater(diff_pixels(pa, pb), 0)
            self.assertEqual(diff_pixels(pa, pb, ignore_bottom=16), 0)

    def test_content_difference_still_detected_with_crop(self):
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover - environment dependent
            raise unittest.SkipTest("Pillow not installed")
        import tempfile as _tf
        from pathlib import Path as _P
        from jui_cli.conformance.control_diff import diff_pixels

        with _tf.TemporaryDirectory() as tmp:
            a = Image.new("RGB", (100, 200), (255, 255, 255))
            b = Image.new("RGB", (100, 200), (255, 255, 255))
            b.putpixel((50, 50), (255, 0, 0))
            pa, pb = _P(tmp) / "a.png", _P(tmp) / "b.png"
            a.save(pa)
            b.save(pb)
            self.assertEqual(diff_pixels(pa, pb, ignore_bottom=16), 1)


class OffFaceExclusionTest(unittest.TestCase):
    """The off-face rule: derived from the ledgers, never a hand list.

    An off-face fixture writes the very state its control renders by omitting
    the attribute, so the pair cannot differ however correctly the platform
    implements it — comparing them manufactures a permanent inert verdict no
    implementation work can clear. The orchestrator ruled (b-2) that the
    fixtures stay and the comparison drops them.
    """

    def _tree(self, tmp, audit_rows, control_rows, fixtures):
        conf = Path(tmp)
        (conf / "inert_audit.json").write_text(json.dumps({"entries": audit_rows}))
        (conf / "control_diff.json").write_text(json.dumps({"entries": control_rows}))
        return conf, {"fixtures": fixtures}

    @staticmethod
    def _fx(fid, component, attribute):
        return {"id": fid, "component": component, "attribute": attribute}

    def test_a_member_whose_sibling_is_active_is_excluded(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            conf, man = self._tree(
                tmp,
                [{"fixture": "C/a__false", "reason": "x " + cd.OFF_FACE_FAMILY}],
                [{"fixture": "C/a__true", "platforms": ["web"]}],
                [self._fx("C/a__false", "C", "a"), self._fx("C/a__true", "C", "a")],
            )
            excluded, held, orphaned = cd.off_face_exclusions(conf, man)
            self.assertEqual(excluded, {"C/a__false"})
            self.assertEqual(held, set())
            self.assertEqual(orphaned, [])

    def test_a_member_with_no_active_sibling_is_held_not_dropped(self):
        """Nothing else could ever report on the attribute — keep measuring it."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            conf, man = self._tree(
                tmp,
                [{"fixture": "C/a__false", "reason": "x " + cd.OFF_FACE_FAMILY}],
                [],  # no sibling asserted active anywhere
                [self._fx("C/a__false", "C", "a"), self._fx("C/a__true", "C", "a")],
            )
            excluded, held, orphaned = cd.off_face_exclusions(conf, man)
            self.assertEqual(excluded, set())
            self.assertEqual(held, {"C/a__false"})

    def test_a_member_with_no_sibling_at_all_is_orphaned_and_never_dropped(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            conf, man = self._tree(
                tmp,
                [{"fixture": "C/a__false", "reason": "x " + cd.OFF_FACE_FAMILY}],
                [],
                [self._fx("C/a__false", "C", "a")],
            )
            excluded, held, orphaned = cd.off_face_exclusions(conf, man)
            self.assertEqual(excluded, set())
            self.assertEqual(orphaned, ["C/a__false"])

    def test_the_committed_ledgers_derive_a_safe_exclusion(self):
        """The safety properties, asserted from VERSION-CONTROLLED data only.

        The sibling test below and the canonical cross-check both used to
        carry this, but the canonical set lives under `docs/`, which is
        gitignored — so on CI and in any fresh clone that check skips and
        asserts nothing. A skip reads exactly like a pass, which is the
        "green because it measured nothing" failure this campaign is named
        after, and it was in this lane's own test. The invariants that must
        never break are pinned here, where the data always exists.
        """
        root = Path(__file__).resolve().parents[2]
        conf = root / "conformance"
        if not (conf / "inert_audit.json").is_file():
            self.skipTest("no committed conformance dir")
        manifest = json.loads((conf / "manifest.json").read_text(encoding="utf-8"))
        excluded, held, orphaned = cd.off_face_exclusions(conf, manifest)

        self.assertEqual(
            orphaned, [], "excluding these would remove an attribute from measurement"
        )
        self.assertTrue(excluded, "the off-face class derived empty — sentinel drift?")
        self.assertEqual(
            held,
            {"ScrollView/scrollBehavior__auto", "TextView/selectable__true"},
            "the orchestrator's two holds are a consequence of the safety rule; "
            "if this set moved, a sibling's active assertion changed",
        )

    def test_the_repository_derivation_matches_the_audited_canonical_set(self):
        """Bonus cross-check against 51-E2's hand audit, when it is present.

        Skips where the canonical set is absent (it lives under gitignored
        `docs/`), so the safety properties are pinned by the test above
        instead of by this one.
        """
        root = Path(__file__).resolve().parents[2]
        conf = root / "conformance"
        canonical = (
            root
            / "docs/plans/2026-08-01-ecosystem-hardening/report"
            / "51-E2-off-face-exclusion-set.json"
        )
        if not canonical.is_file() or not conf.is_dir():
            self.skipTest("no committed conformance dir / canonical set")
        manifest = json.loads((conf / "manifest.json").read_text(encoding="utf-8"))
        excluded, held, orphaned = cd.off_face_exclusions(conf, manifest)

        entries = json.loads(canonical.read_text(encoding="utf-8"))["entries"]
        self.assertEqual(
            excluded, {e["fixture"] for e in entries if e["disposition"] == "exclude"}
        )
        self.assertEqual(
            held,
            {e["fixture"] for e in entries if e["disposition"] != "exclude"},
            "the two holds are a consequence of the safety rule, not a special case",
        )
        self.assertEqual(orphaned, [], "orphaned must be zero before excluding")

    def test_excluding_costs_no_attribute_its_coverage(self):
        """The replacement verification the orchestrator asked for.

        Dropping the class must leave every affected attribute with a sibling
        still in the comparison AND asserted active — otherwise the exclusion
        buys a quiet loss of measurement, which is the failure this campaign
        exists to prevent.
        """
        root = Path(__file__).resolve().parents[2]
        conf = root / "conformance"
        if not conf.is_dir():
            self.skipTest("no committed conformance dir")
        manifest = json.loads((conf / "manifest.json").read_text(encoding="utf-8"))
        excluded, _held, _orphaned = cd.off_face_exclusions(conf, manifest)
        if not excluded:
            self.skipTest("no off-face class recorded")

        by_id = {f["id"]: f for f in manifest["fixtures"]}
        active = set(cd.load_ledger_all(cd.ledger_path(conf)))
        for fid in sorted(excluded):
            key = (by_id[fid].get("component"), by_id[fid].get("attribute"))
            survivors = [
                f["id"]
                for f in manifest["fixtures"]
                if (f.get("component"), f.get("attribute")) == key
                and f["id"] not in excluded
                and not f.get("isControl")
            ]
            self.assertTrue(survivors, f"{fid}: exclusion leaves {key} unmeasured")
            self.assertTrue(
                any(s in active for s in survivors),
                f"{fid}: {key} keeps fixtures but none is asserted active",
            )


class NotComparedByDesignTest(unittest.TestCase):
    """A visual fixture with no control never entered the loop at all.

    142 of them in the repo, every one explained by NON_OBSERVABLE_BY_SECTION
    — but `compared` counted them nowhere and said nothing, so each
    rediscovery ("why is this fixture's comparison母数 zero?") cost a lane an
    investigation. TextField.tintColor is the one that surfaced it: its tint
    IS the caret, and an unfocused field has no caret.
    """

    def test_a_visual_fixture_without_a_control_is_named_not_skipped(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp)
            manifest = {
                "fixtures": [
                    {
                        "id": "TextField/tintColor__static",
                        "class": "visual",
                        "platforms": ["web"],
                        "control": None,
                    }
                ]
            }
            result = cd.compare(conf, "web", manifest, {"results": []})
            self.assertEqual(result.not_compared_by_design, ["TextField/tintColor__static"])
            self.assertEqual(result.active, [])
            self.assertEqual(result.inert, [])

    def test_every_uncontrolled_visual_fixture_in_the_repo_has_a_recorded_reason(self):
        """Nothing may sit outside the comparison without a ledger entry."""
        from jui_cli.conformance import rules

        root = Path(__file__).resolve().parents[2]
        manifest_path = root / "conformance" / "manifest.json"
        if not manifest_path.is_file():
            self.skipTest("no committed conformance dir")
        fixtures = json.loads(manifest_path.read_text(encoding="utf-8"))["fixtures"]
        unexplained = [
            f["id"]
            for f in fixtures
            if f.get("class") == "visual"
            and not f.get("control")
            and not f.get("isControl")
            and not rules.is_non_observable(f.get("component"), f.get("attribute"))
        ]
        self.assertEqual(
            unexplained,
            [],
            "visual fixture(s) outside the control comparison with no recorded "
            "reason — either give them a control or record why a still capture "
            "cannot photograph them",
        )
