"""afterFirstDraw: the generator declares it, the gate refuses an unfired stamp.

conformance-collection-scrollanchor-family-does-not-discriminate (2026-10-14):
a scrollTo request is a CHANGE of the value after the first draw, so the
scrollAnchor fixtures declare one in their manifest state and the hosts fire
it (INTERACTIVE_HOST_CONTRACT.md "afterFirstDraw"). A host that never fires
leaves a first-draw screenshot that every other check reads as the fixture,
so the result is stamped and :mod:`after_first_draw` fails a declaring
fixture whose stamp is missing or not ``fired``.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import after_first_draw, rules
from jui_cli.conformance.fixture_generator import generate_conformance

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "shared" / "core" / "attribute_definitions.json"

DECL = {"name": "conformanceAfterFirstDraw", "set": {"var": "scrollTarget", "value": "Beta"}}


def _write(root: Path, results: dict[str, list[dict]], fixtures: list[dict]) -> None:
    (root / "results").mkdir(parents=True)
    (root / "codegen").mkdir()
    (root / "manifest.json").write_text(json.dumps({"fixtures": fixtures}), encoding="utf-8")
    for rel, entries in results.items():
        (root / rel).write_text(json.dumps({"results": entries}), encoding="utf-8")


def _fixture(fid: str, decl: dict | None = DECL, platforms=("ios", "android", "web")) -> dict:
    return {
        "id": fid,
        "class": "visual",
        "platforms": list(platforms),
        "state": {"vars": [], "handlers": [], "afterFirstDraw": decl} if decl else None,
    }


FIRED = {"name": "conformanceAfterFirstDraw", "status": "fired", "firedAtMs": 0, "appliedAtMs": 16,
         "landing": "2 reading(s) (still 1s at 1.25s)"}


class TheGeneratorDeclaresIt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        generate_conformance(DEFINITIONS, Path(cls.tmp.name))
        cls.manifest = json.loads((Path(cls.tmp.name) / "manifest.json").read_text())
        cls.by_id = {f["id"]: f for f in cls.manifest["fixtures"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_scroll_anchor_fixture_and_its_control_declare_the_change(self):
        ids = ["Collection/scrollAnchor__top", "Collection/scrollAnchor__center",
               "Collection/scrollAnchor__bottom", "Collection/scrollAnchor__binding"]
        controls = {self.by_id[i]["control"] for i in ids}
        self.assertEqual(len(controls), 1, controls)
        for fid in ids + sorted(controls):
            self.assertEqual(self.by_id[fid]["state"]["afterFirstDraw"], DECL, fid)
            self.assertEqual(
                self.by_id[fid]["state"]["vars"],
                [{"name": "scrollTarget", "class": "String", "defaultValue": ""}], fid,
            )

    def test_only_layouts_that_bind_the_var_declare_it(self):
        declaring = sorted(after_first_draw.declared(self.manifest))
        for fid in declaring:
            layout = (Path(self.tmp.name) / self.by_id[fid]["layout"]).read_text()
            self.assertIn('"@{scrollTarget}"', layout, fid)
        self.assertEqual(len(declaring), 5, declaring)

    def test_the_changed_value_names_a_cell_and_the_first_draw_names_none(self):
        layout = json.loads((Path(self.tmp.name) / self.by_id["Collection/scrollAnchor__top"]["layout"]).read_text())
        collection = layout["child"][0]
        self.assertEqual(collection["cellIdProperty"], "title")
        items = next(d for d in layout["data"] if d["name"] == "items")["defaultValue"]
        titles = [cell["title"] for cell in items]
        target_title = rules.AFTER_FIRST_DRAW["scrollTarget"]["value"]
        self.assertIn(target_title, titles)
        target = next(d for d in layout["data"] if d["name"] == "scrollTarget")
        self.assertEqual((target["class"], target["defaultValue"]), ("String", ""))
        # Every landing moves the list and none is clamped: the target's top
        # is below 0 at the first draw, and top / center / bottom ask for
        # offsets inside the content's scroll range.
        cell, view = collection["cellHeight"], collection["height"]
        start = titles.index(target_title) * cell
        room = len(titles) * cell - view
        offsets = [start, start - (view - cell) / 2, start - (view - cell)]
        self.assertGreater(min(offsets), 0, offsets)
        self.assertLessEqual(max(offsets), room, offsets)
        self.assertEqual(len(set(offsets)), 3, offsets)
        # The cell's content (28 high, at its top) stays in view at every landing.
        self.assertLessEqual(view - cell + 28, view)


class TheGateRefusesAnUnfiredStamp(unittest.TestCase):
    def judge(self, results, fixtures, platforms=("ios",), codegen=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, results, fixtures)
            return after_first_draw.judge(root, platforms, codegen=codegen)

    def test_a_fired_stamp_passes(self):
        problems, notices = self.judge(
            {"results/ios.results.json": [{"id": "f", "status": "pass", "afterFirstDraw": FIRED}]},
            [_fixture("f")],
        )
        self.assertEqual(problems, [])
        self.assertEqual(notices, ["ios: afterFirstDraw fired on 1 of 1 declaring fixture(s)"])

    def test_no_stamp_fails(self):
        problems, _ = self.judge(
            {"results/ios.results.json": [{"id": "f", "status": "pass"}]}, [_fixture("f")]
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("carries no stamp", problems[0])

    def test_not_fired_fails_and_says_why(self):
        stamp = {"name": "conformanceAfterFirstDraw", "status": "not-fired", "landing": "no applied stamp within 10000 ms"}
        problems, _ = self.judge(
            {"results/ios.results.json": [{"id": "f", "status": "pass", "afterFirstDraw": stamp}]},
            [_fixture("f")],
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("'not-fired'", problems[0])
        self.assertIn("no applied stamp", problems[0])

    def test_a_failed_fixture_is_still_judged(self):
        problems, _ = self.judge(
            {"results/ios.results.json": [{"id": "f", "status": "fail"}]}, [_fixture("f")]
        )
        self.assertEqual(len(problems), 1)

    def test_skipped_and_undeclared_entries_are_not_judged(self):
        problems, notices = self.judge(
            {"results/ios.results.json": [{"id": "f", "status": "skipped"}, {"id": "g", "status": "pass"}]},
            [_fixture("f"), _fixture("g", decl=None)],
        )
        self.assertEqual(problems, [])
        self.assertEqual(notices, ["ios: afterFirstDraw fired on 0 of 0 declaring fixture(s)"])

    def test_a_platform_the_fixture_does_not_run_on_is_not_judged(self):
        problems, _ = self.judge(
            {"results/web.results.json": [{"id": "f", "status": "pass"}]},
            [_fixture("f", platforms=("ios",))], platforms=("web",),
        )
        self.assertEqual(problems, [])

    def test_the_codegen_face_is_judged_with_parity(self):
        results = {
            "results/ios.results.json": [{"id": "f", "status": "pass", "afterFirstDraw": FIRED}],
            "codegen/ios.results.json": [{"id": "f", "status": "pass"}],
        }
        problems, _ = self.judge(results, [_fixture("f")], codegen=True)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("ios codegen: f"), problems[0])
        problems, _ = self.judge(results, [_fixture("f")], codegen=False)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
