"""The gone-anchor fixture (canonical visibility.goneModel).

A constraint that names a gone element does not apply (ruling 2026-11-10,
ticket kjui-align-to-view-in-visibility-wrapper-and-margin-sign). The fixture
draws children aligned to a gone anchor; its control is the same children with
no anchor. These tests pin what makes the pair a measurement: the two layouts
differ only by the anchor and the constraint naming it, the ledger's
observable names the fixture the generator writes, and the committed
conformance/ tree carries it.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.conformance.gone_fixtures import build_gone_fixtures  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CONSTRAINT_KEYS = {"alignTopView", "alignBottomOfView"}


def _frames(layout: dict) -> dict:
    target = next(c for c in layout["child"] if c["id"] == "target")
    return {frame["id"]: frame["child"] for frame in target["child"]}


class TheGoneAnchorPair(unittest.TestCase):
    def setUp(self):
        files, self.entries = build_gone_fixtures("test")
        self.files = dict(files)
        self.target = next(e for e in self.entries if e["id"] == "common/visibility__gone_anchor")
        self.control = next(e for e in self.entries if e.get("isControl"))

    def test_the_target_names_its_control(self):
        self.assertEqual(self.target["control"], self.control["id"])
        self.assertEqual(self.target["attribute"], "visibility")
        self.assertEqual(self.target["value"], "gone")

    def test_the_target_differs_from_the_control_by_the_gone_anchor_and_its_constraint_only(self):
        target = _frames(self.files[self.target["layout"]])
        control = _frames(self.files[self.control["layout"]])
        self.assertEqual(target.keys(), control.keys())
        for frame_id, children in target.items():
            anchors = [c for c in children if c.get("visibility") == "gone"]
            self.assertEqual(len(anchors), 1, frame_id)
            rest = [c for c in children if c not in anchors]
            stripped = [{k: v for k, v in c.items() if k not in CONSTRAINT_KEYS} for c in rest]
            self.assertEqual(stripped, control[frame_id], frame_id)
            self.assertTrue(any(c.get(k) == anchors[0]["id"] for c in rest for k in CONSTRAINT_KEYS), frame_id)

    def test_the_ledger_observes_the_fixture_ios_divergent(self):
        semantics = json.loads((REPO / "shared/core/attribute_semantics.json").read_text(encoding="utf-8"))
        observable = semantics["semantics"]["visibility"]["observable"]
        self.assertEqual(observable, {self.target["id"]: {"ios": "active", "android": "inert", "web": "inert"}})

    def test_the_committed_manifest_carries_the_pair(self):
        manifest = json.loads((REPO / "conformance/manifest.json").read_text(encoding="utf-8"))
        ids = {f["id"] for f in manifest["fixtures"]}
        self.assertIn(self.target["id"], ids)
        self.assertIn(self.control["id"], ids)


if __name__ == "__main__":
    unittest.main()
