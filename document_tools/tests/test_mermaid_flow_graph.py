"""Flow-diagram extraction tests.

The diagram is derived from flow tests through the canonical pipeline
(``shared/core/screen_identity.json`` → ``diagram``):

    resolve → canonicalize → collapse consecutive duplicates → build edges

These tests pin the parts that are easy to regress silently: inline steps
becoming nodes, ``file:`` references landing in the SAME id space, cells
being dropped instead of drawn, back edges staying distinguishable, and
node ids surviving values that are not valid diagram identifiers.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.mermaid.flow_graph import (
    EDGE_BACK,
    EDGE_FORWARD,
    ScreenResolver,
    flow_edges,
    normalize_screen_ref,
)
from jsonui_doc_cli.test_doc.mermaid.generator import (
    generate_grouped_mermaid_diagrams,
    generate_mermaid_diagram,
    generate_mermaid_html,
)


def _step(screen: str, **kw) -> dict:
    return {"screen": screen, **kw}


class NormalizeRefTests(unittest.TestCase):
    def test_strips_path_and_test_suffix(self):
        self.assertEqual(normalize_screen_ref("../screens/home/home.test.json"), "home")

    def test_strips_json_suffix(self):
        self.assertEqual(normalize_screen_ref("Layouts/mypage/settings.json"), "settings")

    def test_variant_normalizes_to_base(self):
        self.assertEqual(normalize_screen_ref("home@regular"), "home")

    def test_plain_value_is_unchanged(self):
        self.assertEqual(normalize_screen_ref("mypage"), "mypage")


class FlowEdgeTests(unittest.TestCase):
    def setUp(self):
        self.resolver = ScreenResolver()

    def test_inline_steps_become_nodes_and_edges(self):
        steps = [
            _step("login", action="tap", id="sign_in"),
            _step("mypage", action="tap", id="settings_button"),
            _step("settings", assert_="visible"),
        ]
        nodes, edges = flow_edges(steps, self.resolver)
        self.assertEqual(nodes, ["login", "mypage", "settings"])
        self.assertEqual(
            edges, [("login", "mypage", EDGE_FORWARD), ("mypage", "settings", EDGE_FORWARD)]
        )

    def test_consecutive_same_screen_collapses(self):
        steps = [
            _step("login", action="input", id="email"),
            _step("login", action="input", id="password"),
            _step("login", action="tap", id="sign_in"),
            _step("mypage", assert_="visible"),
        ]
        nodes, edges = flow_edges(steps, self.resolver)
        self.assertEqual(nodes, ["login", "mypage"])
        self.assertEqual(len(edges), 1)

    def test_file_reference_shares_the_inline_id_space(self):
        # A mixed flow must not produce two nodes for one screen.
        steps = [
            {"file": "../screens/login/login.test.json"},
            _step("login", action="tap", id="sign_in"),
            _step("mypage", assert_="visible"),
        ]
        nodes, _edges = flow_edges(steps, self.resolver)
        self.assertEqual(nodes, ["login", "mypage"])

    def test_back_action_produces_a_back_edge(self):
        steps = [
            _step("mypage", action="tap", id="settings_button"),
            _step("settings", action="back"),
            _step("mypage", assert_="visible"),
        ]
        _nodes, edges = flow_edges(steps, self.resolver)
        self.assertEqual(
            edges,
            [("mypage", "settings", EDGE_FORWARD), ("settings", "mypage", EDGE_BACK)],
        )

    def test_first_screen_is_never_marked_as_arrived_via_back(self):
        steps = [_step("login", action="back"), _step("mypage")]
        _nodes, edges = flow_edges(steps, self.resolver)
        self.assertEqual(edges[0][2], EDGE_BACK)  # back action caused this one
        self.assertEqual(_nodes[0], "login")

    def test_screenless_step_continues_the_current_screen(self):
        steps = [
            _step("login", action="tap", id="sign_in"),
            {"block": "wait for load", "steps": []},
            _step("mypage", assert_="visible"),
        ]
        nodes, edges = flow_edges(steps, self.resolver)
        self.assertEqual(nodes, ["login", "mypage"])
        self.assertEqual(len(edges), 1)

    def test_no_self_loops(self):
        steps = [_step("login"), _step("login")]
        _nodes, edges = flow_edges(steps, self.resolver)
        self.assertEqual(edges, [])

    def test_non_dict_steps_are_ignored(self):
        nodes, _edges = flow_edges(["oops", _step("login")], self.resolver)
        self.assertEqual(nodes, ["login"])


class CellClassificationTests(unittest.TestCase):
    """A Collection cell is a sub-area of the screen the step already runs
    on. Drawing it invents edges (chat → message_cell) and hides the real
    ones (chat → item_detail)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "chat").mkdir(parents=True)
        (root / "chat.json").write_text(
            json.dumps({"type": "Collection", "cellClasses": ["chat/message_cell"]}), encoding="utf-8"
        )
        (root / "chat" / "message_cell.json").write_text(
            json.dumps({"type": "View"}), encoding="utf-8"
        )
        (root / "item_detail.json").write_text(json.dumps({"type": "View"}), encoding="utf-8")
        self.layouts = root

    def test_cell_steps_do_not_become_nodes(self):
        resolver = ScreenResolver(self.layouts)
        steps = [
            _step("chat", action="tap", id="input"),
            _step("message_cell", action="scrollUntilVisible", id="item_chip"),
            _step("item_detail", assert_="visible"),
        ]
        nodes, edges = flow_edges(steps, resolver)
        self.assertEqual(nodes, ["chat", "item_detail"])
        self.assertEqual(edges, [("chat", "item_detail", EDGE_FORWARD)])

    def test_without_layouts_every_value_is_a_node(self):
        resolver = ScreenResolver()
        steps = [_step("chat"), _step("message_cell"), _step("item_detail")]
        nodes, _edges = flow_edges(steps, resolver)
        self.assertEqual(nodes, ["chat", "message_cell", "item_detail"])

    def test_unknown_ids_are_kept(self):
        # Enforcing screen-unknown is the validator's job; the diagram must
        # not silently drop screens it cannot classify.
        resolver = ScreenResolver(self.layouts)
        nodes, _edges = flow_edges([_step("chat"), _step("not_a_layout")], resolver)
        self.assertIn("not_a_layout", nodes)


class DiagramRenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.flows = self.root / "flows"
        self.screens = self.root / "screens"
        self.flows.mkdir()
        self.screens.mkdir()

    def _write_flow(self, name: str, steps: list[dict], flow_name: str | None = None):
        payload = {
            "type": "flow",
            "metadata": {"name": flow_name or name},
            "steps": steps,
        }
        (self.flows / f"{name}.test.json").write_text(json.dumps(payload), encoding="utf-8")

    def _write_screen_test(self, name: str, layout: str, metadata: dict, document: str | None = None):
        source = {"layout": f"Layouts/{layout}.json"}
        if document:
            source["document"] = document
        payload = {"type": "screen", "metadata": metadata, "source": source, "cases": []}
        (self.screens / f"{name}.test.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_diagram_has_nodes_and_edges_from_inline_steps(self):
        self._write_flow("nav", [_step("login"), _step("mypage")])
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn("login --> mypage", out)

    def test_back_edge_uses_a_dotted_arrow(self):
        self._write_flow(
            "roundtrip",
            [_step("mypage", action="tap", id="x"), _step("settings", action="back"), _step("mypage")],
        )
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn("mypage --> settings", out)
        self.assertIn("settings -.-> mypage", out)

    def test_screen_test_metadata_is_resolved_by_layout_basename(self):
        self._write_flow("nav", [_step("login"), _step("mypage")])
        self._write_screen_test(
            "login_smoke", "login", {"name": "ログイン", "entry_screen": True}, "login.html"
        )
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn('login(["ログイン"]):::entryNode', out)
        self.assertIn('click login "login.html"', out)

    def test_conflicting_names_fall_back_to_the_derived_title(self):
        # Two tests cover one screen with different names — picking the first
        # would label the node with an unrelated test's name.
        self._write_flow("nav", [_step("login"), _step("mypage")])
        self._write_screen_test("a", "login", {"name": "Login Smoke"})
        self._write_screen_test("b", "login", {"name": "Forgot Password Reach"})
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn('login["Login"]', out)

    def test_node_ids_are_sanitized(self):
        self._write_flow("odd", [_step("my page"), _step("ログイン")])
        out = generate_mermaid_diagram(self.flows, self.screens)
        for line in out.splitlines():
            if "-->" in line:
                left, _, right = line.strip().partition(" --> ")
                for token in (left, right):
                    self.assertNotIn(" ", token)
                    self.assertTrue(token.isascii(), token)

    def test_mermaid_keyword_ids_are_escaped(self):
        self._write_flow("kw", [_step("end"), _step("mypage")])
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn("end_node", out)

    def test_grouped_diagrams_use_group_metadata(self):
        self._write_flow("nav", [_step("login"), _step("mypage")])
        self._write_screen_test("login_t", "login", {"name": "Login", "entry_screen": True})
        self._write_screen_test("mypage_t", "mypage", {"name": "MyPage", "group": ["account"]})
        groups = generate_grouped_mermaid_diagrams(self.flows, self.screens)
        self.assertIn("account", groups)

    def test_no_flows_directory_content_reports_no_flows(self):
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn("NO_FLOWS", out)

    def test_flow_without_screens_yields_no_groups(self):
        # A flow whose steps carry no screen produces no nodes: callers use
        # the empty mapping to suppress the diagram link entirely.
        payload = {"type": "flow", "metadata": {"name": "empty"}, "steps": [{"block": "x", "steps": []}]}
        (self.flows / "empty.test.json").write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(generate_grouped_mermaid_diagrams(self.flows, self.screens), {})

    def test_html_generation_is_skipped_when_there_is_nothing_to_draw(self):
        payload = {"type": "flow", "metadata": {"name": "empty"}, "steps": [{"block": "x", "steps": []}]}
        (self.flows / "empty.test.json").write_text(json.dumps(payload), encoding="utf-8")
        out_file = self.root / "diagram.html"
        result = generate_mermaid_html(self.flows, out_file, "Flow Diagram", self.screens)
        self.assertEqual(result, "")
        self.assertFalse(out_file.exists())

    def test_html_is_written_when_there_are_screens(self):
        self._write_flow("nav", [_step("login"), _step("mypage")])
        out_file = self.root / "diagram.html"
        result = generate_mermaid_html(self.flows, out_file, "Flow Diagram", self.screens)
        self.assertTrue(result)
        self.assertTrue(out_file.exists())


class FileReferenceResolutionTests(unittest.TestCase):
    """A ``file:`` step names a FILE, and a file name is not a screen id.

    One screen routinely has several test files (``login_smoke``,
    ``booking_complete--bank_pending``), so naming the node after the file
    splits one screen into several — and the split-off node loses the group
    its test declared, landing in 'その他'.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.flows = self.root / "flows"
        self.screens = self.root / "screens"
        self.flows.mkdir()
        self.screens.mkdir()

    def _write_flow(self, name: str, steps: list[dict]):
        payload = {"type": "flow", "metadata": {"name": name}, "steps": steps}
        (self.flows / f"{name}.test.json").write_text(json.dumps(payload), encoding="utf-8")

    def _write_screen_test(self, name: str, layout: str, metadata: dict, subdir: str = ""):
        payload = {
            "type": "screen",
            "metadata": metadata,
            "source": {"layout": f"Layouts/{layout}.json"},
            "cases": [],
        }
        directory = self.screens / subdir if subdir else self.screens
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{name}.test.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_variant_test_file_folds_onto_the_screen_it_covers(self):
        self._write_screen_test(
            "booking_complete--bank_pending", "booking_complete", {"name": "銀行振込"}
        )
        self._write_flow(
            "bank",
            [
                _step("booking_confirm", action="tap", id="submit"),
                {"file": "booking_complete--bank_pending", "case": "bank_transfer_block"},
            ],
        )
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn("booking_confirm --> booking_complete", out)
        self.assertNotIn("booking_complete__bank_pending", out)

    def test_file_reference_inherits_the_referenced_tests_group(self):
        self._write_screen_test(
            "booking_complete--bank_pending",
            "booking_complete",
            {"name": "銀行振込", "group": "booking"},
        )
        self._write_screen_test("booking_confirm_t", "booking_confirm", {"group": "booking"})
        self._write_flow(
            "bank",
            [
                _step("booking_confirm", action="tap", id="submit"),
                {"file": "booking_complete--bank_pending"},
            ],
        )
        groups = generate_grouped_mermaid_diagrams(self.flows, self.screens)
        self.assertEqual(sorted(groups), ["booking"])

    def test_a_differently_named_test_file_also_folds_onto_its_screen(self):
        # The bug is not specific to the `--variant` spelling: any test file
        # whose name is not the screen id used to become its own node.
        self._write_screen_test("login_smoke", "login", {"name": "ログイン"})
        self._write_flow("nav", [{"file": "login_smoke"}, _step("mypage")])
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn("login --> mypage", out)
        self.assertNotIn("login_smoke", out)

    def test_unresolvable_reference_still_draws_the_basename(self):
        # Nothing indexed under that name (a broken reference, or a test
        # with no source.layout): keep drawing something rather than
        # dropping the edge.
        self._write_flow("nav", [{"file": "../screens/ghost.test.json"}, _step("mypage")])
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn("ghost --> mypage", out)

    def test_one_file_name_claiming_two_screens_is_not_resolved(self):
        # Resolving would pick one at random and silently mislabel the node.
        self._write_screen_test("home", "user_home", {}, subdir="user")
        self._write_screen_test("home", "admin_home", {}, subdir="admin")
        self._write_flow("nav", [{"file": "home"}, _step("mypage")])
        out = generate_mermaid_diagram(self.flows, self.screens)
        self.assertIn("home --> mypage", out)


class AppOwnedScreenGroupTests(unittest.TestCase):
    """An app-owned screen has no layout, so it has no test file — and
    ``metadata.group`` lives in test files. Its jui.config.json declaration
    is the only place it can name a group, so without this it is pinned to
    'その他' forever, where genuinely ungrouped screens need to be visible."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.flows = self.root / "tests" / "flows"
        self.screens = self.root / "tests" / "screens"
        self.flows.mkdir(parents=True)
        self.screens.mkdir(parents=True)

    def _write_config(self, app_owned: list):
        (self.root / "jui.config.json").write_text(
            json.dumps({"test": {"appOwnedScreens": app_owned}}), encoding="utf-8"
        )

    def _write_flow(self, steps: list[dict]):
        payload = {"type": "flow", "metadata": {"name": "footer_nav"}, "steps": steps}
        (self.flows / "footer_nav.test.json").write_text(json.dumps(payload), encoding="utf-8")

    def _write_screen_test(self, name: str, layout: str, metadata: dict):
        payload = {
            "type": "screen",
            "metadata": metadata,
            "source": {"layout": f"Layouts/{layout}.json"},
            "cases": [],
        }
        (self.screens / f"{name}.test.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_declared_group_is_used(self):
        self._write_config([{"id": "tokushoho", "group": "static"}])
        self._write_screen_test("top_t", "top", {"group": "booking"})
        self._write_flow([_step("top", action="tap", id="footer"), _step("tokushoho")])
        groups = generate_grouped_mermaid_diagrams(self.flows, self.screens)
        self.assertIn("static", groups)
        self.assertNotIn("その他", groups)

    def test_a_bare_id_declares_no_group(self):
        # The negative half: the object form is what adds a group, so the
        # string form must still land in 'その他' rather than inventing one.
        self._write_config(["tokushoho"])
        self._write_screen_test("top_t", "top", {"group": "booking"})
        self._write_flow([_step("top", action="tap", id="footer"), _step("tokushoho")])
        groups = generate_grouped_mermaid_diagrams(self.flows, self.screens)
        self.assertIn("その他", groups)

    def test_a_tests_own_group_wins_over_the_declaration(self):
        # One screen, one place to look: a declaration must not silently
        # override what a test file says.
        self._write_config([{"id": "top", "group": "static"}])
        self._write_screen_test("top_t", "top", {"group": "booking"})
        self._write_flow([_step("top", action="tap", id="x"), _step("mypage")])
        groups = generate_grouped_mermaid_diagrams(self.flows, self.screens)
        self.assertIn("booking", groups)
        self.assertNotIn("static", groups)

    def test_multiple_groups_may_be_declared(self):
        self._write_config([{"id": "tokushoho", "group": ["static", "legal"]}])
        self._write_flow([_step("top", action="tap", id="footer"), _step("tokushoho")])
        groups = generate_grouped_mermaid_diagrams(self.flows, self.screens)
        self.assertIn("static", groups)
        self.assertIn("legal", groups)


if __name__ == "__main__":
    unittest.main()
