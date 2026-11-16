"""A relative constraint names a sibling (ticket jui-relative-constraint-target-not-a-sibling).

align*OfView / align*View / alignCenter*View place an element against another
child of the same container. Measured on jsonui-cli 2.5.25 with eight shapes
whose target is not one — the parent, a sibling's child, the parent's
sibling, another container's child, a sibling of the include from inside it,
an id nothing carries, the element itself, an include's root by its spelling
before the include's id prefixed it — `jui build` said nothing, the
generated Compose did not compile for seven of them (Gradle: Unresolved
reference), SwiftUI dropped the constraint (and drew an element against
itself 20pt down), the web found a sibling's child and drew an element
against itself out of its frame.

`jui build` now names each one as an ERROR — with what the target is, and the
prefixed spelling when an include's id prefixed it — records one stage that
did not complete, and exits 1 at its end (0 with --allow-partial); the
platforms are still generated. The forms that are siblings once includes
expand — a partial's root against a sibling of the include, a sibling against
the include's root, two elements of one partial under an include with an id
(their targets take the include's prefix, as the ids do) — are not named.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.commands import build_cmd  # noqa: E402
from jui_cli.core.config_manager import ConfigManager  # noqa: E402
from jui_cli.core.normalizer.include_expander import IncludeExpander  # noqa: E402
from jui_cli.core.normalizer.style_merger import StyleMerger  # noqa: E402
from jui_cli.core.relative_targets import constraint_target_findings, included_stems  # noqa: E402


def box(i, **kw):
    d = {"type": "View", "id": i, "width": 20, "height": 20}
    d.update(kw)
    return d


def frame(i, *kids):
    return {"type": "View", "id": i, "width": 100, "height": 100, "child": list(kids)}


def container(i, *kids):
    return {"type": "View", "id": i, "width": "matchParent", "height": "matchParent", "child": list(kids)}


#: (layouts, {layout: [(element, target, what)]}) — the eight shapes, and the
#: forms that are siblings once includes expand.
WRONG = {
    "screen": {"type": "View", "id": "root", "width": "matchParent", "height": "matchParent", "child": [
        frame("f_sib", box("s_sib", alignTopOfView="a_sib"), box("a_sib")),
        frame("f_parent", container("p_parent", box("s_parent", alignTopOfView="p_parent"), box("x_parent"))),
        frame("f_nephew", box("s_nephew", alignTopOfView="a_nephew"), container("c_nephew", box("a_nephew"), box("g_nephew"))),
        frame("f_uncle", container("c_uncle", box("s_uncle", alignTopOfView="a_uncle"), box("x_uncle")), box("a_uncle")),
        frame("f_cousin", container("c1_cousin", box("s_cousin", alignTopOfView="a_cousin"), box("x_cousin")),
              container("c2_cousin", box("a_cousin"), box("y_cousin"))),
        frame("f_incout", {"include": "parts/incout"}, box("a_incout")),
        frame("f_missing", box("s_missing", alignTopOfView="nowhere"), box("a_missing")),
        frame("f_self", box("s_self", alignTopOfView="s_self"), box("a_self")),
        frame("f_d2raw", {"include": "parts/badge", "id": "inc"}, box("s_d2raw", alignTopOfView="r_badge")),
    ]},
    "parts/incout": container("c_incout", box("s_incout", alignTopOfView="a_incout"), box("x_incout")),
    "parts/badge": box("r_badge"),
}
WRONG_EXPECTED = {
    ("screen", "s_parent", "p_parent", "parent"),
    ("screen", "s_nephew", "a_nephew", "inside c_nephew"),
    ("screen", "s_uncle", "a_uncle", "elsewhere"),
    ("screen", "s_cousin", "a_cousin", "elsewhere"),
    ("parts/incout", "s_incout", "a_incout", "missing"),
    ("screen", "s_missing", "nowhere", "missing"),
    ("screen", "s_self", "s_self", "itself"),
    ("screen", "s_d2raw", "r_badge", "missing"),
}
RIGHT = {
    "screen": {"type": "View", "id": "root", "width": "matchParent", "height": "matchParent", "child": [
        # a partial's root against a sibling of the include (with and without an id)
        frame("f_d1", {"include": "parts/rooted"}, box("anchor_d1")),
        frame("f_d1id", {"include": "parts/rooted_id", "id": "card"}, box("anchor_d1id")),
        # a sibling against the include's root, by the prefixed spelling
        frame("f_d2", {"include": "parts/plain", "id": "inc"}, box("s_d2", alignTopOfView="incPlain")),
        # two elements of one partial, under an include with an id
        frame("f_d4", {"include": "parts/pair", "id": "pair"}),
        # an include node's own attribute names the including layout's element
        frame("f_node", {"include": "parts/plain_two", "alignLeftView": "anchor_node"}, box("anchor_node")),
    ]},
    "parts/rooted": box("rooted", alignTopOfView="anchor_d1"),
    "parts/rooted_id": box("rooted_id", alignLeftView="anchor_d1id"),
    "parts/plain": box("plain"),
    "parts/plain_two": box("plain_two"),
    "parts/pair": container("pair_box", box("s", alignTopOfView="a"), box("a")),
}


def write(root: Path, layouts: dict) -> Path:
    base = root / "docs/screens/layouts"
    for name, tree in layouts.items():
        path = base / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tree), encoding="utf-8")
    return base


def findings(layouts_dir: Path, layouts: dict, platform="android"):
    included = included_stems(layouts)
    out = []
    for name in layouts:
        out += constraint_target_findings(name, platform, layouts_dir=layouts_dir,
                                          styles_dir=layouts_dir, included=name in included)
    return out


class TheShapes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_each_target_that_is_not_a_sibling_is_named_with_what_it_is(self):
        got = {(f.layout, f.element, f.target, f.what) for f in findings(write(self.root, WRONG), WRONG)}
        self.assertEqual(got, WRONG_EXPECTED)

    def test_the_unprefixed_spelling_is_told_the_prefixed_one(self):
        got = [f for f in findings(write(self.root, WRONG), WRONG) if f.element == "s_d2raw"]
        self.assertEqual([f.suggestion for f in got], ["incRBadge"])
        self.assertIn("'incRBadge'", got[0].line(["all"]))

    def test_the_forms_that_are_siblings_once_includes_expand_are_not_named(self):
        for platform in ("ios", "android", "web"):
            self.assertEqual(findings(write(self.root, RIGHT), RIGHT, platform), [], platform)

    def test_a_root_of_a_layout_nothing_includes_has_no_siblings(self):
        layouts = {"screen": box("lonely", alignTopOfView="anywhere")}
        got = findings(write(self.root, layouts), layouts)
        self.assertEqual([(f.element, f.what) for f in got], [("lonely", "root")])


class ThePythonExpander(unittest.TestCase):
    """The expander jui reads layouts with gives a target inside a partial the
    include's prefix, as sjui / kjui do (a52418eaa); without it the D4 form
    above would be named."""

    def test_a_target_inside_the_partial_takes_the_include_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = write(Path(tmp), RIGHT)
            expander = IncludeExpander(base, StyleMerger(base))
            tree = expander.expand({"include": "parts/pair", "id": "pair", "alignTopOfView": "outside"})
            self.assertEqual(tree["alignTopOfView"], "outside")
            inner = {c["id"]: c for c in tree["child"]}
            self.assertEqual(inner["pairS"]["alignTopOfView"], "pairA")


class TheBuild(unittest.TestCase):
    """`_check_relative_constraint_targets` in a project: the ERROR lines, one
    stage in the ledger, exit 1 at the end (0 with --allow-partial)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "jui.config.json").write_text(json.dumps({
            "layouts_directory": "docs/screens/layouts",
            "platforms": {"android": {"root": "android"}, "ios": {"root": "ios"}}}))
        self.ledger = self.root / "stage-failures.json"
        self._env = os.environ.get("JUI_STAGE_FAILURES")
        os.environ["JUI_STAGE_FAILURES"] = str(self.ledger)

    def tearDown(self):
        if self._env is None:
            os.environ.pop("JUI_STAGE_FAILURES", None)
        else:
            os.environ["JUI_STAGE_FAILURES"] = self._env
        self._tmp.cleanup()

    def check(self, layouts: dict):
        write(self.root, layouts)
        cm = ConfigManager(self.root / "jui.config.json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            lines = build_cmd._check_relative_constraint_targets(cm, cm.load().get("platforms", {}))
        return lines, buf.getvalue()

    def test_the_wrong_shapes_are_an_error_a_stage_and_exit_1(self):
        lines, out = self.check(WRONG)
        self.assertIn("ERROR [relative-constraints]", out)
        self.assertEqual(len(lines), len(WRONG_EXPECTED))
        self.assertIn("screen: 's_nephew' alignTopOfView: 'a_nephew' — inside the sibling 'c_nephew', not a sibling", out)
        entries = build_cmd._stage_failures(self.ledger)
        self.assertEqual([e["stage"] for e in entries], ["layouts: relative constraints"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(build_cmd._exit_for_incomplete(entries, argparse.Namespace()), 1)
            self.assertEqual(build_cmd._exit_for_incomplete(entries, argparse.Namespace(allow_partial=True)), 0)

    def test_the_right_forms_say_nothing(self):
        lines, out = self.check(RIGHT)
        self.assertEqual(lines, [])
        self.assertNotIn("relative-constraints", out)
        self.assertEqual(build_cmd._stage_failures(self.ledger), [])


if __name__ == "__main__":
    unittest.main()
