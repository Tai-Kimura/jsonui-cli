"""Cross-platform frame parity (frame_parity.py, `gate --frame-parity`).

Ticket conformance-passes-a-wrong-layout-geometry-is-never-compared-across-
platforms. The frames below are built from the declarations, not from a
render: the align fixtures' anchor is 50 x 50 at top / left margin 120 on a
root whose size differs per platform (the CI Android tablet is landscape, iOS
a portrait phone, web a 1024 x 768 page). KotlinJsonUI 2.43.3 measured the
anchor as its margin-inclusive ref box (0..170), 2.43.4 as the box it draws
(120..170). The driver-recorded frames of a real run are the inventory's job.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.conformance import frame_parity as fp
from jui_cli.conformance.gate import judge_frame_parity

SCHEMA = Path(__file__).resolve().parents[2] / "conformance" / "frames.schema.json"

ROOTS = {
    "ios": {"x": 0, "y": 62, "width": 402, "height": 778},
    "android": {"x": 0, "y": 48, "width": 1280, "height": 752},
    "web": {"x": 0, "y": 0, "width": 1024, "height": 768},
}
SOURCE = {"ios": "xcuielement-frame", "android": "a11y-node-bounds", "web": "get-bounding-client-rect"}
ANCHOR = {"x": 120, "y": 120, "width": 50, "height": 50}


def f(x, y, w, h, **extra):
    return {"x": x, "y": y, "width": w, "height": h, **extra}


# The ten spellings: (target size, the frame the declaration means, the frame
# KotlinJsonUI 2.43.3 drew). The far-edge four are the same in both columns:
# the anchor has no margin on its bottom or right, so the ref box and the
# drawn box share those edges and no frame can tell the fix apart there.
ALIGN = {
    "alignTopView": (f(0, 120, 200, 200), f(0, 0, 200, 200)),
    "alignLeftView": (f(120, 0, 200, 200), f(0, 0, 200, 200)),
    "alignCenterVerticalView": (f(0, 45, 200, 200), f(0, -15, 200, 200)),
    "alignCenterHorizontalView": (f(45, 0, 200, 200), f(-15, 0, 200, 200)),
    "alignTopOfView": (f(0, 70, 50, 50), f(0, -50, 50, 50)),
    "alignLeftOfView": (f(70, 0, 50, 50), f(-50, 0, 50, 50)),
    "alignBottomView": (f(0, -30, 200, 200), f(0, -30, 200, 200)),
    "alignRightView": (f(-30, 0, 200, 200), f(-30, 0, 200, 200)),
    "alignBottomOfView": (f(0, 170, 50, 50), f(0, 170, 50, 50)),
    "alignRightOfView": (f(170, 0, 50, 50), f(170, 0, 50, 50)),
}
DISCRIMINATING = {"alignTopView", "alignLeftView", "alignCenterVerticalView",
                  "alignCenterHorizontalView", "alignTopOfView", "alignLeftOfView"}


class Tree:
    """A conformance dir: manifest, layouts, results naming frames files."""

    def __init__(self, root: Path):
        self.root = root
        self.fixtures: list[dict] = []
        self.entries: dict[str, list[dict]] = {p: [] for p in fp.PLATFORMS}

    def fixture(self, fid, layout, platforms=fp.PLATFORMS, cls="visual"):
        rel = f"fixtures/{fid}.layout.json"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(layout))
        self.fixtures.append({"id": fid, "class": cls, "platforms": list(platforms), "layout": rel})

    def frames(self, platform, fid, frames, *, raw=None, duplicates=None, path_only=False):
        name = fid.replace("/", "_")
        rel = f"artifacts/{platform}/{name}.frames.json"
        entry = {"id": fid, "status": "pass", "screenshot": f"artifacts/{platform}/{name}.png", "frames": rel}
        self.entries[platform].append(entry)
        if path_only:
            return
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = raw if raw is not None else {
            "schemaVersion": 1, "fixture": fid, "platform": platform, "source": SOURCE[platform],
            "root": ROOTS[platform],
            "frames": {"root": f(0, 0, ROOTS[platform]["width"], ROOTS[platform]["height"]), **frames},
        }
        if duplicates:
            doc["duplicates"] = duplicates
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc))

    def no_frames(self, platform, fid):
        self.entries[platform].append({"id": fid, "status": "pass",
                                       "screenshot": f"artifacts/{platform}/{fid.replace('/', '_')}.png"})

    def write(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"fixtures": self.fixtures}))
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        (self.root / "results").mkdir(exist_ok=True)
        for p, entries in self.entries.items():
            if entries:
                (self.root / "results" / f"{p}.results.json").write_text(json.dumps(
                    {"platform": p, "manifestHash": digest, "runner": {}, "results": entries}))
        return json.loads(manifest.read_text())

    def results(self):
        return {p: {e["id"]: e for e in entries} for p, entries in self.entries.items()}


def align_layout(attr):
    size = 50 if attr.endswith("OfView") else 200
    return {"type": "View", "id": "root", "child": [
        {"type": "View", "id": "anchor", "width": 50, "height": 50, "topMargin": 120, "leftMargin": 120},
        {"type": "View", "id": "target", "width": size, "height": size, attr: "anchor"},
    ]}


def align_tree(root: Path, android_version: str) -> Tree:
    t = Tree(root)
    for attr, (declared, kjui_2_43_3) in ALIGN.items():
        fid = f"common/{attr}__static"
        t.fixture(fid, align_layout(attr))
        android = kjui_2_43_3 if android_version == "2.43.3" else declared
        for p, target in (("ios", declared), ("web", declared), ("android", android)):
            t.frames(p, fid, {"anchor": ANCHOR, "target": target})
    return t


class SchemaAndReader(unittest.TestCase):
    """validate() is the schema's rules in code. Held to the file key by key."""

    def setUp(self):
        self.schema = json.loads(SCHEMA.read_text())

    def test_the_reader_knows_exactly_the_schemas_keys(self):
        doc_keys = set(self.schema["properties"])
        frame_keys = set(self.schema["$defs"]["frame"]["properties"])
        self.assertEqual(set(self.schema["required"]),
                         {"schemaVersion", "fixture", "platform", "source", "root", "frames"})
        self.assertEqual(set(self.schema["$defs"]["frame"]["required"]), {"x", "y", "width", "height"})
        good = {"schemaVersion": 1, "fixture": "a/b__c", "platform": "ios", "source": "xcuielement-frame",
                "density": 3, "root": f(0, 0, 1, 1), "frames": {"root": f(0, 0, 1, 1)}, "duplicates": []}
        self.assertEqual(set(good), doc_keys)
        self.assertEqual(fp.validate(good), [])
        # Every key the schema names is accepted; one it does not is refused.
        self.assertEqual(fp.validate({**good, "frames": {"root": f(0, 0, 1, 1, clipped=True)}}), [])
        self.assertEqual(frame_keys, {"x", "y", "width", "height", "clipped"})
        self.assertTrue(fp.validate({**good, "extra": 1}))
        self.assertTrue(fp.validate({**good, "frames": {"root": {**f(0, 0, 1, 1), "z": 0}}}))

    def test_enums_and_const_match_the_schema(self):
        self.assertEqual(set(self.schema["properties"]["source"]["enum"]), set(fp.SOURCES))
        self.assertEqual(tuple(self.schema["properties"]["platform"]["enum"]), fp.PLATFORMS)
        self.assertEqual(self.schema["properties"]["schemaVersion"]["const"], fp.FRAMES_SCHEMA_VERSION)

    def test_each_rule_refuses_its_violation(self):
        good = {"schemaVersion": 1, "fixture": "a/b__c", "platform": "ios", "source": "xcuielement-frame",
                "root": f(0, 0, 1, 1), "frames": {"root": f(0, 0, 1, 1)}}
        bad = [
            {k: v for k, v in good.items() if k != "frames"},
            {**good, "schemaVersion": 2},
            {**good, "platform": "watchos"},
            {**good, "source": "pixels"},
            {**good, "frames": {"target": f(0, 0, 1, 1)}},  # no root
            {**good, "frames": {"root": f(0, 0, -1, 1)}},
            {**good, "frames": {"root": {"x": "0", "y": 0, "width": 1, "height": 1}}},
            {**good, "frames": {"root": f(0, 0, 1, 1, clipped=False)}},
            {**good, "duplicates": ["a", "a"]},
            {**good, "fixture": ""},
            {**good, "density": 0},
            {**good, "density": "2"},
        ]
        for doc in bad:
            self.assertTrue(fp.validate(doc), doc)

    def test_the_tolerance_is_declared_once(self):
        # The schema leaves it out; the module holds the one number.
        self.assertNotIn("tolerance", SCHEMA.read_text().lower().replace("the tolerance is not part", ""))
        self.assertEqual(fp.TOLERANCE, 1.5)


class AxisReadings(unittest.TestCase):
    """Roots differ by platform, so each axis is read four ways."""

    def test_near_far_centre_and_stretch_agree_across_different_roots(self):
        self.assertTrue(fp.axis_agrees(120, 50, 402, 120, 50, 1280))              # from the near edge
        self.assertTrue(fp.axis_agrees(402 - 60, 50, 402, 1280 - 60, 50, 1280))   # from the far edge
        self.assertTrue(fp.axis_agrees(201 - 25, 50, 402, 640 - 25, 50, 1280))    # centred
        self.assertTrue(fp.axis_agrees(16, 402 - 32, 402, 16, 1280 - 32, 1280))   # stretched (16 each side)

    def test_a_misplacement_matches_no_reading(self):
        self.assertFalse(fp.axis_agrees(120, 200, 778, 0, 200, 752))
        self.assertFalse(fp.axis_agrees(45, 200, 778, -15, 200, 752))

    def test_the_tolerance_boundary_on_both_sides(self):
        # Equal roots, so only the 1.5 decides; 1.5 itself agrees.
        self.assertTrue(fp.axis_agrees(120, 50, 400, 121.5, 50, 400))
        self.assertFalse(fp.axis_agrees(120, 50, 400, 121.51, 50, 400))
        self.assertTrue(fp.axis_agrees(120, 50, 400, 120, 51.5, 400))
        self.assertFalse(fp.axis_agrees(120, 50, 400, 120, 51.51, 400))

    def test_outliers(self):
        both = ("android", "ios")
        self.assertEqual(fp.outliers({both: False, ("android", "web"): False, ("ios", "web"): True},
                                     ["android", "ios", "web"]), ["android"])
        self.assertEqual(fp.outliers({both: True, ("android", "web"): True, ("ios", "web"): True},
                                     ["android", "ios", "web"]), [])
        self.assertEqual(fp.outliers({both: False, ("android", "web"): False, ("ios", "web"): False},
                                     ["android", "ios", "web"]), ["android", "ios", "web"])
        self.assertEqual(fp.outliers({both: False}, ["android", "ios"]), ["android", "ios"])


class AlignControls(unittest.TestCase):
    """The control the gate was asked for: red on 2.43.3, green on 2.43.4."""

    def _measure(self, version):
        with tempfile.TemporaryDirectory() as d:
            t = align_tree(Path(d), version)
            manifest = t.write()
            return fp.measure(Path(d), manifest, t.results(), list(fp.PLATFORMS))

    def test_kjui_2_43_3_puts_the_six_discriminating_targets_on_android_alone(self):
        result = self._measure("2.43.3")
        red = {d.fixture.split("/")[1].split("__")[0]: d for d in result.disagreed}
        self.assertEqual(set(red), DISCRIMINATING)
        for d in red.values():
            self.assertEqual(d.id, "target")
            self.assertEqual(d.outliers, ["android"])
        # The far-edge four agree, as they must: no frame tells them apart.
        agreed_targets = {fid.split("/")[1].split("__")[0] for fid, i in result.agreed if i == "target"}
        self.assertEqual(agreed_targets, set(ALIGN) - DISCRIMINATING)
        self.assertEqual(result.fixtures_compared, 10)

    def test_kjui_2_43_4_agrees_everywhere(self):
        result = self._measure("2.43.4")
        self.assertEqual(result.disagreed, [])
        self.assertEqual(len(result.agreed), 20)  # anchor + target, ten fixtures

    def test_the_gate_fails_2_43_3_and_passes_2_43_4(self):
        for version, want_red in (("2.43.3", True), ("2.43.4", False)):
            with tempfile.TemporaryDirectory() as d:
                align_tree(Path(d), version).write()
                problems, notices = judge_frame_parity(Path(d), list(fp.PLATFORMS), expected_hosts=frozenset())
                self.assertEqual(bool(problems), want_red, (version, problems))
                if want_red:
                    self.assertIn("6 id(s) drawn in different places", problems[0])
                    self.assertIn("android* x=0 y=0 w=200 h=200", problems[0])
                self.assertTrue(any(n.startswith("frame parity (") for n in notices))


class Readings(unittest.TestCase):
    """Which reading an agreement rests on, so a lucky root size that lets a
    wrong placement through the far edge or the centre can be found."""

    def test_each_reading_is_named(self):
        self.assertEqual(fp.axis_readings(120, 50, 402, 120, 50, 1280), {"near"})
        self.assertEqual(fp.axis_readings(342, 50, 402, 1220, 50, 1280), {"far"})
        self.assertEqual(fp.axis_readings(176, 50, 402, 615, 50, 1280), {"centred"})
        self.assertEqual(fp.axis_readings(16, 370, 402, 16, 1248, 1280), {"stretched"})
        # Equal roots: the readings collapse onto one placement.
        self.assertEqual(fp.axis_readings(120, 50, 400, 120, 50, 400), {"near", "far", "centred", "stretched"})

    def test_the_align_fixtures_agree_from_the_near_edge_only(self):
        with tempfile.TemporaryDirectory() as d:
            t = align_tree(Path(d), "2.43.4")
            manifest = t.write()
            r = fp.measure(Path(d), manifest, t.results(), list(fp.PLATFORMS))
        counts = fp.reading_counts(r)
        self.assertEqual(counts["x"]["near"], 20)
        self.assertEqual(counts["y"]["near"], 20)
        self.assertEqual(fp.not_near_agreements(r), [])

    def test_an_agreement_that_holds_only_from_the_far_edge_is_listed(self):
        with tempfile.TemporaryDirectory() as d:
            t = Tree(Path(d))
            t.fixture("a/pinRight__x", {"type": "View", "id": "root", "child": [{"type": "View", "id": "badge"}]})
            for p in ("ios", "android", "web"):
                w = ROOTS[p]["width"]
                t.frames(p, "a/pinRight__x", {"badge": f(w - 60, 10, 50, 20)})
            manifest = t.write()
            r = fp.measure(Path(d), manifest, t.results(), list(fp.PLATFORMS))
        self.assertEqual(r.disagreed, [])
        self.assertEqual(fp.not_near_agreements(r), ["a/pinRight__x #badge (x=far)"])
        self.assertEqual(fp.reading_counts(r)["x"]["far"], 1)


    def test_the_reading_named_is_the_one_every_pair_shares(self):
        # iOS and web the same width (every reading holds between them), the
        # Android tablet wider (only the far edge holds against either). The
        # agreement rests on the far edge; the iOS-web pair alone would say
        # "near" and hide it.
        with tempfile.TemporaryDirectory() as d:
            t = Tree(Path(d))
            t.fixture("a/pinRight__x", {"type": "View", "id": "root", "child": [{"type": "View", "id": "badge"}]})
            for p, w in (("ios", 402), ("web", 402), ("android", 1280)):
                root = f(0, 0, w, 778)
                t.frames(p, "a/pinRight__x", {}, raw={
                    "schemaVersion": 1, "fixture": "a/pinRight__x", "platform": p, "source": SOURCE[p],
                    "root": root, "frames": {"root": root, "badge": f(w - 60, 10, 50, 20)}})
            manifest = t.write()
            r = fp.measure(Path(d), manifest, t.results(), list(fp.PLATFORMS))
        self.assertEqual(fp.not_near_agreements(r), ["a/pinRight__x #badge (x=far)"])


    def test_web_measures_from_its_container_where_margin_collapse_moves_root(self):
        # Measured on the web host (alignTopView, 2026-10-05): the anchor's top
        # margin collapses through #root (and #app-root), so #root's own box
        # starts at y=120 while its children sit where iOS draws them. Frames
        # are relative to the page, and the gate takes the root's size from
        # the top-level root, so the shifted #root moves nothing.
        with tempfile.TemporaryDirectory() as d:
            t = Tree(Path(d))
            fid = "common/alignTopView__static"
            t.fixture(fid, align_layout("alignTopView"))
            for p in ("ios", "android"):
                t.frames(p, fid, {"anchor": ANCHOR, "target": ALIGN["alignTopView"][0]})
            web_root = f(0, 0, 1024, 768)
            t.frames("web", fid, {}, raw={
                "schemaVersion": 1, "fixture": fid, "platform": "web", "source": SOURCE["web"],
                "root": web_root, "frames": {"root": f(0, 120, 1024, 768), "anchor": ANCHOR,
                                             "target": ALIGN["alignTopView"][0]}})
            manifest = t.write()
            r = fp.measure(Path(d), manifest, t.results(), list(fp.PLATFORMS))
        self.assertEqual(r.disagreed, [])
        self.assertEqual(sorted(i for _, i in r.agreed), ["anchor", "target"])


class Weighted(unittest.TestCase):
    """A weighted axis is judged by its declared reading, proportional."""

    LAYOUT = {"type": "View", "id": "root", "orientation": "horizontal", "child": [
        {"type": "View", "id": "rival", "width": 0, "height": 200, "weight": 1},
        {"type": "View", "id": "target", "width": 0, "height": 200, "weight": 1,
         "child": [{"type": "View", "id": "box_a", "width": 40, "height": 40}]},
    ]}

    def _measure(self, web_target_x, android_target_x=640):
        with tempfile.TemporaryDirectory() as d:
            t = Tree(Path(d))
            t.fixture("common/weight__static", self.LAYOUT)
            for p in ("android", "web"):
                w = ROOTS[p]["width"]
                tx = android_target_x if p == "android" else web_target_x
                t.frames(p, "common/weight__static", {
                    "rival": f(0, 0, tx, 200), "target": f(tx, 0, w - tx, 200), "box_a": f(tx, 0, 40, 40)})
            manifest = t.write()
            return fp.measure(Path(d), manifest, t.results(), ["android", "web"])

    def test_the_weighted_ids_and_their_children_are_named_from_the_declaration(self):
        self.assertEqual(fp.weighted_axes(self.LAYOUT), {"rival": {"x"}, "target": {"x"}, "box_a": {"x"}})

    def test_an_even_split_agrees_by_proportion(self):
        r = self._measure(512)  # web root 1024, android 1280: both halves
        self.assertEqual(r.disagreed, [])
        self.assertEqual(r.readings[("common/weight__static", "box_a")]["x"], {"proportional"})

    def test_a_split_that_agrees_only_by_a_lucky_reading_is_red(self):
        # box_a 40 wide at 620 of 1280 and at 492 of 1024: both centred
        # (620 + 20 - 640 = 0, 492 + 20 - 512 = 0), so the four readings agree;
        # by proportion 620 is 496 of 1024, 4 away from 492, so it is red.
        self.assertTrue(fp.axis_agrees(620, 40, 1280, 492, 40, 1024))
        r = self._measure(492, android_target_x=620)
        self.assertIn("box_a", {d.id for d in r.disagreed})

    def test_a_split_that_disagrees_everywhere_is_red(self):
        r = self._measure(412)
        self.assertEqual({d.id for d in r.disagreed}, {"rival", "target", "box_a"})

    def test_weight__static_box_no_longer_rests_on_centred(self):
        r = self._measure(512)
        self.assertNotIn("centred", r.readings[("common/weight__static", "box_a")]["x"])

    def test_a_weight_beside_a_fixed_sibling_agrees_by_stretch(self):
        # triage's case: rival weight 1, width 0, beside a fixed 200 —
        # root - 200 on both (1080 of 1280, 824 of 1024). Not proportional;
        # the same gap at both ends.
        layout = {"type": "View", "id": "root", "orientation": "horizontal", "child": [
            {"type": "View", "id": "rival", "width": 0, "height": 200, "weight": 1},
            {"type": "View", "id": "fixed", "width": 200, "height": 200}]}
        with tempfile.TemporaryDirectory() as d:
            t = Tree(Path(d))
            t.fixture("a/fixedSibling__x", layout)
            for p in ("android", "web"):
                w = ROOTS[p]["width"]
                t.frames(p, "a/fixedSibling__x", {"rival": f(0, 0, w - 200, 200), "fixed": f(w - 200, 0, 200, 200)})
            manifest = t.write()
            r = fp.measure(Path(d), manifest, t.results(), ["android", "web"])
        self.assertEqual(r.disagreed, [])
        self.assertEqual(r.readings[("a/fixedSibling__x", "rival")]["x"], {"stretched"})

    def test_proportional_agrees_scales_by_the_roots(self):
        self.assertTrue(fp.proportional_agrees(640, 640, 1280, 512, 512, 1024))
        self.assertTrue(fp.proportional_agrees(640, 40, 1280, 512, 40, 1024))   # fixed child
        self.assertFalse(fp.proportional_agrees(640, 640, 1280, 412, 612, 1024))


class NotCompared(unittest.TestCase):
    """Everything that cannot be compared is counted on its own line."""

    def test_each_reason_counts_and_names(self):
        with tempfile.TemporaryDirectory() as d:
            t = Tree(Path(d))
            t.fixture("a/noIds__x", {"type": "View", "id": "root"})
            t.fixture("a/oneIdMissing__x", align_layout("alignTopView"))
            for p in ("ios", "web"):
                t.frames(p, "a/oneIdMissing__x", {"anchor": ANCHOR, "target": ALIGN["alignTopView"][0]})
            t.frames("android", "a/oneIdMissing__x", {"anchor": ANCHOR})  # target absent
            t.fixture("a/noFile__x", align_layout("alignLeftView"))
            t.frames("ios", "a/noFile__x", {"anchor": ANCHOR, "target": ALIGN["alignLeftView"][0]})
            t.frames("web", "a/noFile__x", {"anchor": ANCHOR, "target": ALIGN["alignLeftView"][0]})
            t.no_frames("android", "a/noFile__x")
            t.fixture("a/dup__x", align_layout("alignTopView"))
            t.frames("ios", "a/dup__x", {"anchor": ANCHOR}, duplicates=["target"])
            t.frames("web", "a/dup__x", {"anchor": ANCHOR, "target": ALIGN["alignTopView"][0]})
            t.frames("android", "a/dup__x", {"anchor": ANCHOR, "target": f(0, 0, 200, 200, clipped=True)})
            t.fixture("a/broken__x", align_layout("alignTopView"))
            t.frames("ios", "a/broken__x", {}, raw="{not json")
            t.frames("web", "a/broken__x", {"target": ALIGN["alignTopView"][0]})
            t.frames("android", "a/broken__x", {}, path_only=True)
            t.fixture("a/clippedRoot__x", align_layout("alignTopView"))
            for p in ("ios", "web"):
                t.frames(p, "a/clippedRoot__x", {"anchor": ANCHOR, "target": ALIGN["alignTopView"][0]})
            t.frames("android", "a/clippedRoot__x", {}, raw={
                "schemaVersion": 1, "fixture": "a/clippedRoot__x", "platform": "android",
                "source": SOURCE["android"], "root": f(0, 48, 1280, 752, clipped=True),
                "frames": {"root": f(0, 0, 1280, 752), "anchor": ANCHOR, "target": ALIGN["alignTopView"][1]}})
            manifest = t.write()
            r = fp.measure(Path(d), manifest, t.results(), list(fp.PLATFORMS))
        nc = r.not_compared
        self.assertEqual(nc[fp.NO_DECLARED_IDS], 1)
        self.assertEqual(nc[fp.ID_ABSENT], 1)
        self.assertEqual(r.named[fp.ID_ABSENT], ["android: a/oneIdMissing__x #target"])
        self.assertEqual(nc[fp.NO_FRAMES_FILE], 2)  # android noFile (no field) + android broken (no file)
        self.assertEqual(nc[fp.DUPLICATE], 1)
        self.assertEqual(r.named[fp.DUPLICATE], ["ios: a/dup__x #target"])
        self.assertEqual(nc[fp.CLIPPED], 1)
        self.assertEqual(r.named[fp.CLIPPED], ["android: a/dup__x #target"])
        self.assertEqual(nc[fp.UNREADABLE], 1)
        self.assertEqual(nc[fp.TOO_FEW_PLATFORMS], 1)  # broken: only web left
        # A clipped root cannot anchor relative frames: android's wrong target
        # in that fixture is not judged, and says so.
        self.assertEqual(r.named[fp.ROOT_ABSENT], ["android: a/clippedRoot__x"])
        self.assertNotIn("a/clippedRoot__x", {d.fixture for d in r.disagreed})
        # A file without the id and no file at all are separate lines.
        lines = fp.not_compared_lines(r)
        self.assertIn(f"not compared — {fp.ID_ABSENT}: 1: android: a/oneIdMissing__x #target", lines)
        self.assertIn(f"not compared — {fp.NO_FRAMES_FILE}: 2", lines)
        self.assertEqual(len(lines), 9)  # every reason printed, zero or not

    def test_a_reason_the_driver_gives_is_its_own_line(self):
        # iOS cannot read the canvas of a root that does not fill it; the host
        # says so in the results entry instead of writing a guess.
        with tempfile.TemporaryDirectory() as d:
            t = Tree(Path(d))
            fid = "a/sized__x"
            t.fixture(fid, align_layout("alignTopView"))
            t.frames("web", fid, {"anchor": ANCHOR, "target": ALIGN["alignTopView"][0]})
            t.frames("android", fid, {"anchor": ANCHOR, "target": ALIGN["alignTopView"][0]})
            t.entries["ios"].append({"id": fid, "status": "pass", "framesUnrecorded": "root-not-fill"})
            t.fixture("a/both__x", align_layout("alignTopView"))
            t.frames("ios", "a/both__x", {"anchor": ANCHOR, "target": ALIGN["alignTopView"][0]})
            t.entries["ios"][-1]["framesUnrecorded"] = "root-not-fill"
            for p in ("web", "android"):
                t.frames(p, "a/both__x", {"anchor": ANCHOR, "target": ALIGN["alignTopView"][0]})
            manifest = t.write()
            r = fp.measure(Path(d), manifest, t.results(), list(fp.PLATFORMS))
        self.assertEqual(r.named[fp.DRIVER_UNRECORDED], ["ios: a/sized__x (root-not-fill)"])
        self.assertEqual(r.not_compared[fp.NO_FRAMES_FILE], 0)
        self.assertEqual(r.named[fp.UNREADABLE], ["ios: a/both__x (frames and framesUnrecorded both set)"])
        # The other two platforms still compare the fixture.
        self.assertIn(("a/sized__x", "target"), r.agreed)

    def test_a_run_that_compares_nothing_fails(self):
        with tempfile.TemporaryDirectory() as d:
            t = Tree(Path(d))
            t.fixture("a/x__y", align_layout("alignTopView"))
            for p in fp.PLATFORMS:
                t.no_frames(p, "a/x__y")
            t.write()
            problems, notices = judge_frame_parity(Path(d), list(fp.PLATFORMS), expected_hosts=frozenset())
        self.assertTrue(any("0 fixtures compared" in p for p in problems), problems)

    def test_one_platform_selected_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            align_tree(Path(d), "2.43.4").write()
            problems, _ = judge_frame_parity(Path(d), ["ios"], expected_hosts=frozenset())
        self.assertIn("at least two selected platforms", problems[0])


class Declaration(unittest.TestCase):
    def _run(self, hosts, android_frames=True):
        with tempfile.TemporaryDirectory() as d:
            t = align_tree(Path(d), "2.43.4")
            if not android_frames:
                t.entries["android"] = [{k: v for k, v in e.items() if k != "frames"} for e in t.entries["android"]]
            t.write()
            return judge_frame_parity(Path(d), list(fp.PLATFORMS), expected_hosts=hosts)

    def test_a_declared_host_without_frames_fails(self):
        problems, _ = self._run(frozenset({"android"}), android_frames=False)
        self.assertTrue(any("android is a declared frames host" in p for p in problems), problems)

    def test_an_undeclared_host_with_frames_is_told_to_join(self):
        problems, notices = self._run(frozenset({"ios", "web"}))
        self.assertEqual(problems, [])
        self.assertTrue(any("android wrote frames for 10" in n for n in notices), notices)

    def test_the_declaration_names_the_drivers_that_write_frames(self):
        # Grown in the commit that teaches a driver to write frames: web (the
        # conformance host's run.ts) first; ios and android join with theirs.
        self.assertEqual(fp.EXPECTED_FRAME_HOSTS, frozenset({"web"}))
        run_ts = (SCHEMA.parent / "hosts" / "web" / "scripts" / "run.ts").read_text()
        self.assertIn(".frames.json", run_ts)
        self.assertIn("source: 'get-bounding-client-rect'", run_ts)


class Ledger(unittest.TestCase):
    def _result(self, version):
        with tempfile.TemporaryDirectory() as d:
            t = align_tree(Path(d), version)
            manifest = t.write()
            return fp.measure(Path(d), manifest, t.results(), list(fp.PLATFORMS))

    def test_accepted_stale_and_unverified(self):
        red = self._result("2.43.3")
        top = ("common/alignTopView__static", "target")
        ledger = {top: {"fixture": top[0], "id": top[1], "outliers": ["android"], "reason": "r"}}
        v = fp.check(red, ledger)
        self.assertEqual(v.accepted, 1)
        self.assertEqual(len(v.unrecorded), 5)
        # Fixed: the entry no longer measures.
        v = fp.check(self._result("2.43.4"), ledger)
        self.assertEqual(v.stale, ["common/alignTopView__static #target (now agrees)"])
        # Other outliers than recorded: stale, and the finding is unrecorded again.
        v = fp.check(red, {top: {**ledger[top], "outliers": ["ios"]}})
        self.assertEqual(v.accepted, 0)
        self.assertTrue(v.stale and "records outliers ['ios'], measured ['android']" in v.stale[0])
        # Not compared this run.
        v = fp.check(red, {("a/gone__x", "target"): {"outliers": ["web"]}})
        self.assertEqual(v.unverified, ["a/gone__x #target"])

    def test_the_committed_ledger_is_empty_and_readable(self):
        path = SCHEMA.parent / fp.LEDGER_NAME
        self.assertEqual(fp.load_ledger(path), {})


class Report(unittest.TestCase):
    def test_the_section_shows_the_frames_side_by_side(self):
        from jui_cli.conformance.report import load_platform_results, manifest_identity

        with tempfile.TemporaryDirectory() as d:
            t = align_tree(Path(d), "2.43.3")
            manifest = t.write()
            digest, eq = manifest_identity(Path(d) / "manifest.json", Path(d))
            loaded = load_platform_results(Path(d) / "results", digest, eq)
            section = fp.report_section(Path(d), manifest, loaded)
        self.assertIn("## Frame parity", section)
        self.assertIn("| common/alignTopView__static | target |", section)
        self.assertIn("0,0 200x200", section)
        self.assertIn("UNRECORDED", section)
        self.assertIn(f"- not compared — {fp.ID_ABSENT}: 0", section)
        self.assertIn("Agreements by reading (the first that held for every pair, per axis): "
                      "x: near 14, proportional 0, stretched 0, centred 0, far 0, mixed 0", section)
        self.assertIn("Agreed other than from the near edge on some axis: 0", section)


if __name__ == "__main__":
    unittest.main()
