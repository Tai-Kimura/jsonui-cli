"""A baseline is judged only with the hashing library that made its hashes.

🔻 THE INCIDENT. dHash resamples every screenshot to 65x64 through Pillow's
LANCZOS. Pillow 13.0.0 resamples differently: conformance-mobile run
39012627109 read 99 byte-identical iOS screenshots as regressions, while the
same artifacts under Pillow 12.3.0 read 0. The distance measured the library,
not the screenshots — and nothing said so, because the manifest recorded how
the hash was SHAPED (`algorithm: dhash-64`) and not WHAT computed it.

Measured 2026-10-17 on that run's artifacts (ci: ios 946 / android 898 /
web 894 hashed pictures): Pillow 10.4.0, 11.3.0, 12.0.0, 12.1.0, 12.1.1,
12.2.0 and 12.3.0 produce bit-identical dHash and vdHash on every one of
2738 pictures; 13.0.0 changes the horizontal hash of 843 of 946 iOS pictures
(max 46 bits) and none on android or web. So the identity is the MAJOR
(`pillow-12`): no minor in the measured window moved a bit, and a full-version
pin would turn every patch upgrade into a stop the evidence does not support.

The arms:
  * mismatch STOPS — the comparison reports an error naming both identities
    and how to resolve it, and compares nothing (no regressions, no passes);
  * a match compares exactly as before;
  * a baseline that records no identity also stops (absence cannot be told
    from "made by another library"), with its own message;
  * every bake writes the identity, and a bake on top of a baseline made by
    another library refuses unless asked to rehash — which in turn refuses
    when nothing changed, so it cannot become a way around --fail-on-moved;
  * parity stops the same way (its deviation ledger and threshold come from
    the same hasher: 13.0.0 adds one unrecorded iOS deviation on that run).

Every arm fakes the CURRENT identity by patching ``PIL.__version__`` — the
one thing the code reads — so the arms run on whatever Pillow is installed.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import PIL
    from PIL import Image

    HAVE_PIL = True
except ImportError:  # pragma: no cover - environment dependent
    HAVE_PIL = False

from jui_cli.conformance import baseline, parity

try:
    from tests.test_conformance_shared_core_is_read_or_refused import (
        conformance_with_shared_core,
    )
except ImportError:  # pragma: no cover - run from inside tests/
    from test_conformance_shared_core_is_read_or_refused import (  # type: ignore
        conformance_with_shared_core,
    )


def _png(path: Path, shade: int) -> None:
    img = Image.new("L", (40, 30), 255)
    for x in range(10, 10 + shade):
        for y in range(5, 25):
            img.putpixel((x, y), 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(path)


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.conf = conformance_with_shared_core(self._tmp.name)
        self.art = self.conf / "artifacts" / "web"
        _png(self.art / "A.png", 8)
        _png(self.art / "B.png", 14)

    def _as(self, version: str):
        return mock.patch.object(PIL, "__version__", version)

    def _bake(self, version: str, **kw):
        with self._as(version):
            return baseline.update_baseline(self.conf, "web", env="ci", **kw)

    def _manifest(self) -> dict:
        return json.loads(baseline.baseline_path(self.conf, "web", "ci").read_text())

    def _rewrite(self, **fields) -> None:
        path = baseline.baseline_path(self.conf, "web", "ci")
        doc = json.loads(path.read_text())
        for k, v in fields.items():
            if v is None:
                doc.pop(k, None)
            else:
                doc[k] = v
        path.write_text(json.dumps(doc))

    def _compare(self, version: str) -> baseline.VisualComparison:
        with self._as(version):
            return baseline.compare_platform(self.conf, "web", ["A.png", "B.png"], env="ci")


class TheIdentityIsTheMajor(_Base):
    def test_patch_and_minor_versions_share_one_identity(self):
        for v in ("12.0.0", "12.1.1", "12.3.0", "12.3.0.dev0"):
            with self._as(v):
                self.assertEqual(baseline.hasher_identity(), "pillow-12", v)
        with self._as("13.0.0"):
            self.assertEqual(baseline.hasher_identity(), "pillow-13")


class TheBakeWritesTheIdentity(_Base):
    def test_a_fresh_bake_records_the_running_major(self):
        self._bake("12.3.0")
        self.assertEqual(self._manifest()[baseline.HASHER_FIELD], "pillow-12")

    def test_the_field_sits_beside_the_algorithm_not_inside_rendered_by(self):
        # rendered_by is caller-supplied provenance of the PICTURE; the hasher
        # is a fact about the MEASUREMENT, computed here, never passed in.
        self._bake("12.3.0", rendered_by={"rjui.src": "tree:abc"})
        doc = self._manifest()
        self.assertEqual(doc["rendered_by"], {"rjui.src": "tree:abc"})
        keys = list(doc)
        self.assertEqual(keys.index(baseline.HASHER_FIELD), keys.index("algorithm") + 1)

    def test_an_only_new_bake_keeps_it(self):
        self._bake("12.3.0")
        _png(self.art / "C.png", 20)
        self._bake("12.1.0", only_new=True)
        self.assertEqual(self._manifest()[baseline.HASHER_FIELD], "pillow-12")


class TheGateStopsOnAnotherHasher(_Base):
    def test_mismatch_stops_and_names_both_and_the_way_out(self):
        self._bake("12.3.0")
        c = self._compare("13.0.0")
        self.assertIsNotNone(c.error)
        self.assertIn("pillow-12", c.error)
        self.assertIn("pillow-13", c.error)
        self.assertIn("Pillow 13.0.0", c.error)
        self.assertIn("cannot measure", c.error)
        self.assertIn("setup.py", c.error)
        self.assertIn("--rehash", c.error)
        # Nothing was compared — not "0 regressions", not passes.
        self.assertEqual(c.compared, 0)
        self.assertEqual(c.regressions, [])

    def test_the_stop_reaches_the_gate_as_a_failure(self):
        # The report files a comparison error under baseline_errors and the
        # gate turns that into a problem; this arm carries the real message
        # through the real judge, so a stop the gate ignored would be red.
        from jui_cli.conformance import gate
        from jui_cli.conformance.report import ReportSummary

        self._bake("12.3.0")
        c = self._compare("13.0.0")
        summary = ReportSummary(out_path=self.conf / "REPORT.md", platforms=["web"])
        summary.baseline_errors = {"web": c.error}
        outcome = gate.judge(summary, ["web"], visual=True, env="ci")
        self.assertFalse(outcome.ok)
        hits = [p for p in outcome.problems if "screenshots were not compared" in p]
        self.assertEqual(len(hits), 1, outcome.problems)
        self.assertIn("pillow-13", hits[0])

    def test_a_match_compares_normally(self):
        self._bake("12.3.0")
        c = self._compare("12.1.1")
        self.assertIsNone(c.error)
        self.assertEqual(c.compared, 2)
        self.assertEqual(c.regressions, [])

    def test_a_match_still_finds_a_real_regression(self):
        self._bake("12.3.0")
        _png(self.art / "A.png", 30)
        c = self._compare("12.3.0")
        self.assertIsNone(c.error)
        self.assertEqual([n for n, _ in c.regressions], ["A.png"])

    def test_a_baseline_without_the_identity_stops(self):
        self._bake("12.3.0")
        self._rewrite(**{baseline.HASHER_FIELD: None})
        c = self._compare("12.3.0")
        self.assertIsNotNone(c.error)
        self.assertIn("does not record", c.error)
        self.assertIn("pillow-12", c.error)
        self.assertEqual(c.compared, 0)


class TheBakeRefusesToMixHashers(_Base):
    def test_a_bake_over_another_hasher_refuses_without_rehash(self):
        self._bake("12.3.0")
        before = baseline.baseline_path(self.conf, "web", "ci").read_bytes()
        with self.assertRaises(baseline.BaselineError) as cm:
            self._bake("13.0.0")
        self.assertIn("pillow-12", str(cm.exception))
        self.assertIn("pillow-13", str(cm.exception))
        self.assertEqual(baseline.baseline_path(self.conf, "web", "ci").read_bytes(), before)

    def test_only_new_over_another_hasher_refuses_even_with_rehash(self):
        self._bake("12.3.0")
        with self.assertRaises(baseline.BaselineError):
            self._bake("13.0.0", only_new=True)
        with self.assertRaises(baseline.BaselineError):
            self._bake("13.0.0", only_new=True, rehash=True)

    def test_rehash_moves_the_whole_file_and_reports_it(self):
        self._bake("12.3.0")
        s = self._bake("13.0.0", rehash=True, refuse_if_moved=True)
        self.assertEqual(self._manifest()[baseline.HASHER_FIELD], "pillow-13")
        self.assertEqual(s.rehashed_from, "pillow-12")
        self.assertEqual(s.rehashed, ("A.png", "B.png"))
        self.assertEqual(s.moved, ())

    def test_rehash_over_the_same_hasher_refuses(self):
        # Otherwise --rehash would be a way to absorb moved pictures past
        # --fail-on-moved.
        self._bake("12.3.0")
        _png(self.art / "A.png", 30)
        with self.assertRaises(baseline.BaselineError) as cm:
            self._bake("12.2.0", rehash=True, refuse_if_moved=True)
        self.assertIn("already", str(cm.exception))

    def test_a_baseline_without_the_identity_needs_rehash(self):
        self._bake("12.3.0")
        self._rewrite(**{baseline.HASHER_FIELD: None})
        with self.assertRaises(baseline.BaselineError):
            self._bake("12.3.0")
        self._bake("12.3.0", rehash=True)
        self.assertEqual(self._manifest()[baseline.HASHER_FIELD], "pillow-12")

    def test_rehash_drops_other_os_buckets_rather_than_relabel_them(self):
        self._bake("12.3.0")
        self._rewrite(hashes_by_os={"25": {"Old.png": "0" * 1024}})
        s = self._bake("13.0.0", rehash=True)
        self.assertEqual(self._manifest()["hashes_by_os"], {})
        self.assertEqual(s.dropped_os_buckets, ("25",))


class TheCommandCarriesTheFlag(_Base):
    """`jui conformance baseline update --rehash` reaches update_baseline."""

    def _cli(self, version: str, *extra: str) -> tuple[int, str]:
        import contextlib
        import io

        from jui_cli.cli import main

        buf = io.StringIO()
        argv = ["conformance", "baseline", "update", "--platform", "web", "--env", "ci",
                "--dir", str(self.conf), *extra]
        with self._as(version), contextlib.redirect_stdout(buf):
            try:
                rc = main(argv)
            except SystemExit as exc:  # argparse / main may exit
                rc = exc.code
        return int(rc or 0), buf.getvalue()

    def test_without_the_flag_the_command_refuses_and_names_both(self):
        self._bake("12.3.0")
        rc, out = self._cli("13.0.0", "--fail-on-moved")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("pillow-12", out)
        self.assertIn("pillow-13", out)
        self.assertEqual(self._manifest()[baseline.HASHER_FIELD], "pillow-12")

    def test_with_the_flag_the_command_rehashes(self):
        self._bake("12.3.0")
        rc, out = self._cli("13.0.0", "--rehash", "--fail-on-moved")
        self.assertEqual(rc, 0, out)
        self.assertIn("rehashed 2 from pillow-12 to pillow-13", out)
        self.assertEqual(self._manifest()[baseline.HASHER_FIELD], "pillow-13")


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class ParityStopsOnAnotherHasher(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.conf = self.tmp / "conformance"
        for side in ("ios", "ios-codegen"):
            _png(self.conf / "artifacts" / side / "A.png", 8)
        (self.conf / "baselines" / "ci").mkdir(parents=True)

    def _baseline(self, **extra) -> None:
        doc = {"platform": "ios", "environment": "ci", "algorithm": "dhash-64",
               "threshold": 8, "hashes": {}}
        doc.update(extra)
        (self.conf / "baselines" / "ci" / "ios.hashes.json").write_text(json.dumps(doc))

    def _measure(self, version: str):
        with mock.patch.object(PIL, "__version__", version):
            return parity.measure(self.conf, "ios", env="ci")

    def test_mismatch_stops(self):
        self._baseline(**{baseline.HASHER_FIELD: "pillow-12"})
        r = self._measure("13.0.0")
        self.assertIsNotNone(r.error)
        self.assertIn("pillow-12", r.error)
        self.assertIn("pillow-13", r.error)
        self.assertEqual(r.matched, [])
        self.assertFalse(parity.check(r, {}).ok)

    def test_match_measures(self):
        self._baseline(**{baseline.HASHER_FIELD: "pillow-12"})
        r = self._measure("12.3.0")
        self.assertIsNone(r.error)
        self.assertEqual(r.matched, ["A.png"])

    def test_missing_identity_stops(self):
        self._baseline()
        r = self._measure("12.3.0")
        self.assertIsNotNone(r.error)
        self.assertIn("does not record", r.error)


class TheCommittedBaselinesRecordTheIdentity(unittest.TestCase):
    """Every committed manifest names its hasher, and all of them the major
    the setup.py cap admits. A manifest added without it would stop the gate
    on first use; this says so at commit time instead."""

    REPO = Path(__file__).resolve().parents[2]

    def test_every_committed_manifest_records_one_major(self):
        paths = sorted((self.REPO / "conformance" / "baselines").glob("*/*.hashes.json"))
        self.assertGreaterEqual(len(paths), 6, "the scan found almost nothing")
        seen = {p.relative_to(self.REPO).as_posix(): json.loads(p.read_text()).get(baseline.HASHER_FIELD)
                for p in paths}
        self.assertEqual({k: v for k, v in seen.items() if v != "pillow-12"}, {})

    def test_the_extra_admits_exactly_the_recorded_major(self):
        setup = (self.REPO / "jui_tools" / "setup.py").read_text()
        self.assertIn('"Pillow>=12.0.0,<13"', setup)


if __name__ == "__main__":
    unittest.main()
