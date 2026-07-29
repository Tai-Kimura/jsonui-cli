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
