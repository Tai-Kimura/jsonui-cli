"""Flow-graph and diagram-rendering tests.

Ruled 2026-09-10: the diagram is drawn from the SPECS; flow tests are
CHECKED against it. The flow-test walk (``flow_graph.py``) still runs the
canonical pipeline — resolve → canonicalize → collapse consecutive
duplicates → build edges — to obtain what the tests DO, so the arms on that
walk (``FlowEdgeTests``, ``CellClassificationTests``, file references) are
kept; what changed is what they prove. A ``file:`` step landing in the same
id space used to mean "one node, not two"; it now means "the check compares
the screen the test covers, not the file's name". The rendering arms feed
specs, and the one that used to assert "No flow tests found" now asserts
its inverse, with the date.
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
    build_diagram,
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

    def test_platform_exclusive_sibling_steps_are_not_consecutive(self):
        """iOS lands on chat, Android on confirm — the same
        step position, two devices. Read as one sequence they produced
        chat -> confirm, which no platform performs
        (2 of a face's 36 absent transitions, 2026-09-10)."""
        resolver = ScreenResolver()
        steps = [
            _step("input_form", action="tap", id="register"),
            _step("chat", id="message_input", when={"platform": "ios"}),
            _step("confirm", id="question", when={"platform": "android"}),
        ]
        _nodes, edges = flow_edges(steps, resolver)
        self.assertIn(("input_form", "chat", EDGE_FORWARD), edges)
        self.assertIn(("input_form", "confirm", EDGE_FORWARD), edges)
        self.assertNotIn(("chat", "confirm", EDGE_FORWARD), edges)

    def test_responsive_siblings_are_not_consecutive_either(self):
        """Third shape from the same face: two-pane `regular` vs `compact`."""
        resolver = ScreenResolver()
        steps = [
            _step("following_bar_list", action="tap", id="row"),
            _step("tablet_detail", when={"responsive": "regular"}),
            _step("tablet_detail", id="sort", when={"responsive": "regular"}),
            _step("detail", when={"responsive": "compact"}),
        ]
        _nodes, edges = flow_edges(steps, resolver)
        self.assertIn(("following_bar_list", "tablet_detail", EDGE_FORWARD), edges)
        self.assertIn(("following_bar_list", "detail", EDGE_FORWARD), edges)
        self.assertNotIn(("tablet_detail", "detail", EDGE_FORWARD), edges)

    def test_two_when_keys_combine(self):
        resolver = ScreenResolver()
        steps = [
            _step("a"),
            _step("b", when={"platform": "ios"}),
            _step("c", when={"responsive": "compact"}),
            _step("d", when={"platform": "android", "responsive": "regular"}),
        ]
        _nodes, edges = flow_edges(steps, resolver)
        # ios+compact: a→b→c ; ios+regular: a→b ; android+compact: a→c ; android+regular: a→d
        self.assertEqual(sorted(edges), sorted([
            ("a", "b", EDGE_FORWARD), ("b", "c", EDGE_FORWARD),
            ("a", "c", EDGE_FORWARD), ("a", "d", EDGE_FORWARD)]))

    def test_an_ungated_step_after_gated_siblings_follows_each_platform(self):
        resolver = ScreenResolver()
        steps = [
            _step("a"),
            _step("b", when={"platform": "ios"}),
            _step("c", when={"platform": "android"}),
            _step("d"),
        ]
        _nodes, edges = flow_edges(steps, resolver)
        self.assertEqual(sorted(edges), sorted([
            ("a", "b", EDGE_FORWARD), ("b", "d", EDGE_FORWARD),
            ("a", "c", EDGE_FORWARD), ("c", "d", EDGE_FORWARD)]))

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


class _Tree:
    """specs + layouts + tests for the rendering arms."""

    def __init__(self, root: Path):
        self.root = root
        self.specs = root / "docs" / "screens" / "json"
        self.layouts = root / "docs" / "screens" / "layouts"
        self.flows = root / "tests" / "flows"
        self.screens = root / "tests" / "screens"
        for d in (self.specs, self.layouts, self.flows, self.screens):
            d.mkdir(parents=True, exist_ok=True)

    def spec(self, name: str, destinations: list[str], display: str | None = None) -> None:
        (self.layouts / f"{name}.json").write_text(json.dumps({"type": "View"}), encoding="utf-8")
        metadata = {"displayName": display} if display else {}
        (self.specs / f"{name}.spec.json").write_text(json.dumps({
            "type": "screen_spec", "metadata": metadata,
            "transitions": [{"trigger": "t", "condition": "c", "destination": d} for d in destinations],
        }, ensure_ascii=False), encoding="utf-8")

    def flow(self, name: str, steps: list[dict], flow_name: str | None = None) -> None:
        payload = {"type": "flow", "metadata": {"name": flow_name or name}, "steps": steps}
        (self.flows / f"{name}.test.json").write_text(json.dumps(payload), encoding="utf-8")

    def screen_test(self, name: str, layout: str, metadata: dict, document: str | None = None,
                    subdir: str = "") -> None:
        source = {"layout": f"Layouts/{layout}.json"}
        if document:
            source["document"] = document
        payload = {"type": "screen", "metadata": metadata, "source": source, "cases": []}
        directory = self.screens / subdir if subdir else self.screens
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{name}.test.json").write_text(json.dumps(payload), encoding="utf-8")

    def config(self, app_owned: list) -> None:
        (self.root / "jui.config.json").write_text(
            json.dumps({"test": {"appOwnedScreens": app_owned}}), encoding="utf-8")

    def diagram(self, **kwargs) -> str:
        return generate_mermaid_diagram(self.specs, self.screens, self.layouts,
                                        flows_dir=self.flows, **kwargs)

    def grouped(self, **kwargs) -> dict[str, str]:
        return generate_grouped_mermaid_diagrams(self.specs, self.screens, self.layouts,
                                                 flows_dir=self.flows, **kwargs)

    def build(self, **kwargs):
        return build_diagram(self.specs, flows_dir=self.flows, screens_dir=self.screens,
                             layouts_dir=self.layouts, **kwargs)


class DiagramRenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tree = _Tree(Path(self.tmp.name))

    def test_diagram_has_nodes_and_edges_from_spec_transitions(self):
        self.tree.spec("login", ["Mypage"])
        self.tree.spec("mypage", [])
        self.assertIn("login --> mypage", self.tree.diagram())

    def test_a_spec_back_declaration_uses_a_dotted_arrow(self):
        self.tree.spec("mypage", ["Settings"])
        self.tree.spec("settings", ["Previous screen (pop)"])
        out = self.tree.diagram()
        self.assertIn("mypage --> settings", out)
        self.assertIn("settings -.-> mypage", out)

    def test_screen_test_metadata_is_resolved_by_layout_basename(self):
        self.tree.spec("login", ["Mypage"])
        self.tree.spec("mypage", [])
        self.tree.screen_test("login_smoke", "login", {"name": "ログイン", "entry_screen": True}, "login.html")
        out = self.tree.diagram()
        self.assertIn('login(["ログイン"]):::entryNode', out)
        self.assertIn('click login "login.html"', out)

    def test_conflicting_names_fall_back_to_the_derived_title(self):
        # Two tests cover one screen with different names — picking the first
        # would label the node with an unrelated test's name.
        self.tree.spec("login", ["Mypage"])
        self.tree.spec("mypage", [])
        self.tree.screen_test("a", "login", {"name": "Login Smoke"})
        self.tree.screen_test("b", "login", {"name": "Forgot Password Reach"})
        self.assertIn('login["Login"]', self.tree.diagram())

    def test_node_ids_are_sanitized(self):
        self.tree.spec("my page", ["ログイン"])
        self.tree.spec("ログイン", [])
        out = self.tree.diagram()
        self.assertIn("-->", out)
        for line in out.splitlines():
            if "-->" in line:
                left, _, right = line.strip().partition(" --> ")
                for token in (left, right):
                    self.assertNotIn(" ", token)
                    self.assertTrue(token.isascii(), token)

    def test_mermaid_keyword_ids_are_escaped(self):
        self.tree.spec("end", ["Mypage"])
        self.tree.spec("mypage", [])
        self.assertIn("end_node", self.tree.diagram())

    def test_grouped_diagrams_use_group_metadata(self):
        self.tree.spec("login", ["Mypage"])
        self.tree.spec("mypage", [])
        self.tree.screen_test("login_t", "login", {"name": "Login", "entry_screen": True})
        self.tree.screen_test("mypage_t", "mypage", {"name": "MyPage", "group": ["account"]})
        self.assertIn("account", self.tree.grouped())

    def test_no_specs_reports_no_specs(self):
        self.assertIn("NO_SPECS", self.tree.diagram())

    def test_no_flow_tests_still_draws_from_the_specs(self):
        """INVERTED 2026-09-10. This arm used to be
        `test_no_flows_directory_content_reports_no_flows`: an empty flows
        directory produced "No flow tests found" even with specs present."""
        self.tree.spec("login", ["Mypage"])
        self.tree.spec("mypage", [])
        out = self.tree.diagram()
        self.assertIn("login --> mypage", out)
        self.assertNotIn("NO_FLOWS", out)

    def test_specs_without_a_resolvable_transition_yield_no_groups(self):
        # `none` draws nothing, so nothing is drawable: callers use the empty
        # mapping to suppress the diagram link entirely.
        self.tree.spec("login", ["なし（画面内のタブ切替）"])
        self.assertEqual(self.tree.grouped(), {})

    def test_html_generation_is_skipped_when_there_is_nothing_to_draw(self):
        self.tree.spec("login", ["なし（画面内のタブ切替）"])
        out_file = self.tree.root / "diagram.html"
        result = generate_mermaid_html(self.tree.specs, out_file, "Flow Diagram", self.tree.screens,
                                       self.tree.layouts, flows_dir=self.tree.flows)
        self.assertEqual(result.combined, "")
        self.assertFalse(out_file.exists())

    def test_html_is_written_when_there_are_screens(self):
        self.tree.spec("login", ["Mypage"])
        self.tree.spec("mypage", [])
        out_file = self.tree.root / "diagram.html"
        result = generate_mermaid_html(self.tree.specs, out_file, "Flow Diagram", self.tree.screens,
                                       self.tree.layouts, flows_dir=self.tree.flows)
        self.assertTrue(result.combined)
        self.assertTrue(out_file.exists())


class FileReferenceResolutionTests(unittest.TestCase):
    """A ``file:`` step names a FILE, and a file name is not a screen id.

    The check compares the screen the referenced test COVERS (its
    ``source.layout``) against the spec — a file name would have produced
    "login_smoke has no spec" for a screen whose spec declares the
    transition perfectly well.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tree = _Tree(Path(self.tmp.name))
        self.tree.spec("booking_confirm", ["BookingComplete"])
        self.tree.spec("booking_complete", [])
        self.tree.spec("login", ["Mypage"])
        self.tree.spec("mypage", [])

    def test_variant_test_file_folds_onto_the_screen_it_covers(self):
        self.tree.screen_test("booking_complete--bank_pending", "booking_complete", {"name": "銀行振込"})
        self.tree.flow("bank", [
            _step("booking_confirm", action="tap", id="submit"),
            {"file": "booking_complete--bank_pending", "case": "bank_transfer_block"},
        ])
        result = self.tree.build()
        self.assertEqual(result.errors, [])
        self.assertIn("booking_confirm --> booking_complete", result.combined)

    def test_file_reference_inherits_the_referenced_tests_group(self):
        self.tree.screen_test("booking_complete--bank_pending", "booking_complete",
                              {"name": "銀行振込", "group": "booking"})
        self.tree.screen_test("booking_confirm_t", "booking_confirm", {"group": "booking"})
        self.tree.screen_test("login_t", "login", {"group": "auth"})
        self.tree.screen_test("mypage_t", "mypage", {"group": "auth"})
        self.assertEqual(sorted(self.tree.grouped()), ["auth", "booking"])

    def test_a_differently_named_test_file_also_folds_onto_its_screen(self):
        self.tree.screen_test("login_smoke", "login", {"name": "ログイン"})
        self.tree.flow("nav", [{"file": "login_smoke"}, _step("mypage")])
        self.assertEqual(self.tree.build().errors, [])

    def test_without_the_covering_test_the_file_name_is_what_gets_checked(self):
        # 陰性対照 for the arm above: the SAME flow, no screen test to resolve
        # through, is checked under the file's name and fails as such.
        self.tree.flow("nav", [{"file": "login_smoke"}, _step("mypage")])
        errors = self.tree.build().errors
        self.assertEqual([(e.from_id, e.to_id) for e in errors], [("login_smoke", "mypage")])
        self.assertIn("login_smoke has no spec", errors[0].reason)

    def test_unresolvable_reference_is_checked_under_its_basename(self):
        self.tree.flow("nav", [{"file": "../screens/ghost.test.json"}, _step("mypage")])
        errors = self.tree.build().errors
        self.assertEqual([(e.from_id, e.to_id) for e in errors], [("ghost", "mypage")])

    def test_one_file_name_claiming_two_screens_is_not_resolved(self):
        # Resolving would pick one at random and silently check the wrong screen.
        self.tree.screen_test("home", "user_home", {}, subdir="user")
        self.tree.screen_test("home", "admin_home", {}, subdir="admin")
        self.tree.flow("nav", [{"file": "home"}, _step("mypage")])
        errors = self.tree.build().errors
        self.assertEqual([e.from_id for e in errors], ["home"])


class AppOwnedScreenGroupTests(unittest.TestCase):
    """An app-owned screen has no layout, so it has no test file — and
    ``metadata.group`` lives in test files. Its jui.config.json declaration
    is the only place it can name a group, so without this it is pinned to
    'その他' forever, where genuinely ungrouped screens need to be visible.

    Since 2026-09-10 the node itself comes from a spec transition INTO the
    app-owned screen (or from its own declared ``transitions``)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tree = _Tree(Path(self.tmp.name))
        self.tree.spec("top", ["Tokushoho"])
        self.tree.spec("mypage", [])

    def test_declared_group_is_used(self):
        self.tree.config([{"id": "tokushoho", "group": "static"}])
        self.tree.screen_test("top_t", "top", {"group": "booking"})
        groups = self.tree.grouped(app_owned=["tokushoho"])
        self.assertIn("static", groups)
        self.assertNotIn("その他", groups)

    def test_a_bare_id_declares_no_group(self):
        # The negative half: the object form is what adds a group, so the
        # string form must still land in 'その他' rather than inventing one.
        self.tree.config(["tokushoho"])
        self.tree.screen_test("top_t", "top", {"group": "booking"})
        self.assertIn("その他", self.tree.grouped(app_owned=["tokushoho"]))

    def test_a_tests_own_group_wins_over_the_declaration(self):
        # One screen, one place to look: a declaration must not silently
        # override what a test file says.
        self.tree.spec("top", ["Mypage"])
        self.tree.config([{"id": "top", "group": "static"}])
        self.tree.screen_test("top_t", "top", {"group": "booking"})
        self.tree.screen_test("mypage_t", "mypage", {"group": "booking"})
        groups = self.tree.grouped()
        self.assertIn("booking", groups)
        self.assertNotIn("static", groups)

    def test_multiple_groups_may_be_declared(self):
        self.tree.config([{"id": "tokushoho", "group": ["static", "legal"]}])
        self.tree.screen_test("top_t", "top", {"group": "booking"})
        groups = self.tree.grouped(app_owned=["tokushoho"])
        self.assertIn("static", groups)
        self.assertIn("legal", groups)

    def test_its_own_declared_transitions_are_drawn(self):
        self.tree.spec("licenses", [])
        self.tree.config([{"id": "tokushoho", "group": "static", "transitions": ["Licenses"]}])
        out = self.tree.diagram(app_owned=["tokushoho"], app_owned_transitions={"tokushoho": ["Licenses"]})
        self.assertIn("tokushoho --> licenses", out)


if __name__ == "__main__":
    unittest.main()
