"""Ruled 2026-09-10: the flow diagram is drawn from the SPECS only; a flow-test
transition the specs do not declare is an ERROR; a destination that cannot be
resolved is treated as absent.

⚠️ THE INVERSION. Until v1.8.66 the generator drew from flow tests only and
returned "No flow tests found" on a face with 48 specs — while the canon
declared two sources. `test_specs_alone_draw_the_diagram` is the arm that was
red on every version before this one (three trees: old generator 0 edges,
this one non-zero, the distributed copy non-zero after the release), and
`test_a_flow_only_transition_is_not_drawn` is the one that pins the other
direction, because a generator that drew from BOTH sources would pass the
first arm and still be wrong.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import generate_html_directory, get_diagram_errors
from jsonui_doc_cli.test_doc.mermaid.generator import (
    NO_SPECS_DIAGRAM,
    build_diagram,
    generate_mermaid_diagram,
    generate_mermaid_html,
)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class _Face:
    """A minimal face: specs + layouts + tests + jui.config.json."""

    def __init__(self, root: Path):
        self.root = root
        self.specs = root / "docs" / "screens" / "json"
        self.layouts = root / "docs" / "screens" / "layouts"
        self.flows = root / "tests" / "flows"
        self.screens = root / "tests" / "screens"
        for d in (self.specs, self.layouts, self.flows, self.screens):
            d.mkdir(parents=True, exist_ok=True)
        self.config({})

    def config(self, extra: dict) -> None:
        data = {"spec_directory": "docs/screens/json", "layouts_directory": "docs/screens/layouts",
                "test": {"src": "tests"}}
        data.update(extra)
        _write(self.root / "jui.config.json", data)

    def layout(self, name: str) -> None:
        _write(self.layouts / f"{name}.json", {"type": "View"})

    def spec(self, name: str, destinations: list[str], display: str | None = None) -> None:
        """A spec the SpecValidator accepts — the site run validates every
        spec page, and an invalid fixture would fail the run for the wrong
        reason (measured: 4 page failures hid the exit code under test)."""
        self.layout(name)
        metadata = {"name": name.title().replace("_", ""), "description": f"{name} screen",
                    "displayName": display or name.title().replace("_", " ")}
        _write(self.specs / f"{name}.spec.json", {
            "type": "screen_spec", "version": "1.0",
            "metadata": metadata,
            "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                          "layout": {"root": "root", "children": []}},
            "transitions": [{"trigger": "tap", "condition": "always", "destination": d} for d in destinations],
        })

    def flow(self, name: str, steps: list[dict], flow_name: str | None = None) -> Path:
        path = self.flows / f"{name}.test.json"
        _write(path, {"type": "flow", "metadata": {"name": flow_name or name}, "steps": steps})
        return path

    def build(self, **kwargs):
        return build_diagram(self.specs, flows_dir=self.flows, screens_dir=self.screens,
                             layouts_dir=self.layouts, **kwargs)


def _s(screen: str, action: str | None = None) -> dict:
    """A step the test validator accepts (`visible` needs an `id`)."""
    step = {"screen": screen, "assert": "visible", "id": "root"}
    if action:
        step["action"] = action
    return step


class TheSpecsAreTheSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.face = _Face(Path(self.tmp.name))

    def test_specs_alone_draw_the_diagram(self):
        """No flow test at all. The old generator returned NO_FLOWS here."""
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", ["Settings"])
        self.face.spec("settings", [])
        result = self.face.build()
        self.assertIn("login --> mypage", result.combined)
        self.assertIn("mypage --> settings", result.combined)
        self.assertNotIn("NO_FLOWS", result.combined)
        self.assertEqual(result.errors, [])

    def test_a_flow_only_transition_is_not_drawn(self):
        """A generator that drew from BOTH sources passes the arm above."""
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", [])
        self.face.flow("nav", [_s("login"), _s("mypage"), _s("login")])
        result = self.face.build()
        self.assertIn("login --> mypage", result.combined)
        self.assertNotIn("mypage --> login", result.combined)

    def test_no_specs_is_the_no_specs_placeholder_not_the_old_no_flows_one(self):
        self.face.flow("nav", [_s("login"), _s("mypage")])
        out = generate_mermaid_diagram(self.face.specs, self.face.screens, self.face.layouts)
        self.assertEqual(out, NO_SPECS_DIAGRAM)
        self.assertIn("NO_SPECS", out)

    def test_the_label_comes_from_the_spec_when_no_screen_test_names_it(self):
        self.face.spec("login", ["Mypage"], display="ログイン")
        self.face.spec("mypage", [])
        result = self.face.build()
        self.assertIn('login["ログイン"]', result.combined)

    def test_a_back_declaration_draws_a_dotted_return_edge_to_each_pusher(self):
        self.face.spec("mypage", ["Settings"])
        self.face.spec("chat", ["Settings"])
        self.face.spec("settings", ["Previous screen (pop)"])
        result = self.face.build()
        self.assertIn("settings -.-> mypage", result.combined)
        self.assertIn("settings -.-> chat", result.combined)

    def test_external_is_a_terminal_node_and_none_draws_nothing(self):
        self.face.spec("mypage", ["外部ブラウザ（https://example.test/）", "なし（画面内のタブ切替）"])
        result = self.face.build()
        self.assertIn(":::externalNode", result.combined)
        self.assertIn("https://example.test/", result.combined)
        # `none` is a positive declaration: no node, no edge, no report.
        self.assertEqual(result.unresolved, [])
        self.assertEqual(result.combined.count("-->"), 1, "exactly the external edge")


class FlowTestsAreCheckedAgainstTheSpecs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.face = _Face(Path(self.tmp.name))
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", [])

    def test_a_transition_the_spec_does_not_declare_is_an_error_that_names_everything(self):
        path = self.face.flow("nav", [_s("login"), _s("mypage"), _s("login")], flow_name="Login round trip")
        result = self.face.build()
        self.assertEqual(len(result.errors), 1)
        err = result.errors[0]
        self.assertEqual((err.from_id, err.to_id), ("mypage", "login"))
        self.assertEqual(err.flow_name, "Login round trip")
        self.assertEqual(err.flow_file, str(path))
        self.assertIn("mypage's spec declares no transition to login", err.reason)
        self.assertEqual(result.stats["absent"], 1)

    def test_a_declared_transition_is_not_an_error(self):
        self.face.flow("nav", [_s("login"), _s("mypage")])
        self.assertEqual(self.face.build().errors, [])

    def test_a_back_step_is_exempt(self):
        self.face.flow("nav", [_s("login"), _s("mypage", action="back"), _s("login")])
        result = self.face.build()
        self.assertEqual(result.errors, [], "a return through the stack is not a declared transition")

    def test_the_same_absent_pair_in_two_flows_is_reported_once_with_the_first_flow(self):
        self.face.flow("a", [_s("login"), _s("mypage"), _s("login")], flow_name="A")
        self.face.flow("b", [_s("login"), _s("mypage"), _s("login")], flow_name="B")
        result = self.face.build()
        self.assertEqual([(e.from_id, e.to_id) for e in result.errors], [("mypage", "login")])

    def test_a_source_with_no_spec_says_so(self):
        self.face.layout("chat")  # a real screen, no spec
        self.face.flow("nav", [_s("chat"), _s("login")])
        result = self.face.build()
        self.assertEqual(len(result.errors), 1)
        self.assertIn("chat has no spec", result.errors[0].reason)


class UnresolvableDestinationsAreAbsent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.face = _Face(Path(self.tmp.name))
        self.face.spec("settings", ["LicensesView"])
        self.face.spec("licenses", [])

    def test_listed_and_not_drawn_and_not_an_error_by_itself(self):
        result = self.face.build()
        self.assertEqual([(u.source, u.raw, u.kind) for u in result.unresolved],
                         [("settings", "LicensesView", "unknown")])
        self.assertNotIn("settings --> licenses", result.combined)
        self.assertEqual(result.errors, [])

    def test_a_flow_that_performs_it_is_an_error_naming_the_unresolved_destination(self):
        self.face.flow("nav", [_s("settings"), _s("licenses")])
        result = self.face.build()
        self.assertEqual(len(result.errors), 1)
        self.assertIn("'LicensesView'", result.errors[0].reason)
        self.assertIn("could not be resolved", result.errors[0].reason)

    def test_a_declared_alias_resolves_it(self):
        self.face.flow("nav", [_s("settings"), _s("licenses")])
        result = self.face.build(aliases=[("suffix", "View")])
        self.assertEqual(result.unresolved, [])
        self.assertIn("settings --> licenses", result.combined)
        self.assertEqual(result.errors, [])

    def test_the_alias_position_matters(self):
        result = self.face.build(aliases=[("prefix", "View")])
        self.assertEqual(len(result.unresolved), 1, "a suffix declared as a prefix must not fire")


class AppOwnedScreensDeclareTheirTransitionsInTheConfig(unittest.TestCase):
    """An app-owned screen has no layout and no spec, so the diagram — drawn
    from specs only — would otherwise make every flow test that leaves one an
    error with no way to comply (measured: 2 on one face, a footer link)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.face = _Face(Path(self.tmp.name))
        self.face.spec("login", [])
        self.face.layout("licenses")

    def test_declared_transitions_are_drawn_and_accepted(self):
        self.face.flow("footer", [_s("company"), _s("licenses")])
        result = self.face.build(app_owned=["company"], app_owned_transitions={"company": ["Licenses"]})
        self.assertIn("company --> licenses", result.combined)
        self.assertEqual(result.errors, [])

    def test_an_undeclared_one_is_an_error_that_points_at_the_config_key(self):
        self.face.flow("footer", [_s("company"), _s("login")])
        result = self.face.build(app_owned=["company"], app_owned_transitions={"company": ["Licenses"]})
        self.assertEqual(len(result.errors), 1)
        self.assertIn("test.appOwnedScreens[].transitions", result.errors[0].reason)

    def test_without_the_declaration_the_reason_is_no_spec(self):
        # 陰性対照 on the reason text: the config-key hint must not appear for
        # an ordinary screen that merely lacks a spec.
        self.face.layout("chat")
        self.face.flow("nav", [_s("chat"), _s("login")])
        result = self.face.build()
        self.assertNotIn("appOwnedScreens", result.errors[0].reason)


class TheSiteRunReportsAndFails(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.face = _Face(Path(self.tmp.name))
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", ["LicensesView"])
        self.face.spec("licenses", [])
        self.face.flow("nav", [_s("login"), _s("mypage"), _s("login")], flow_name="Round trip")
        self.out = self.face.root / "out"

    def _run(self) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            generate_html_directory(self.face.root / "tests", self.out, title="Face")
        return buf.getvalue()

    def test_error_lines_are_printed_and_tallied(self):
        log = self._run()
        self.assertIn("ERROR [doc-diagram]:", log)
        self.assertIn("mypage -> login", log)
        errors = get_diagram_errors()
        self.assertEqual([(e["from"], e["to"], e["flow"]) for e in errors], [("mypage", "login", "Round trip")])

    def test_the_unresolved_destination_is_a_warning_with_its_raw_value(self):
        log = self._run()
        self.assertIn("WARNING [doc-diagram]:", log)
        self.assertIn("'LicensesView'", log)

    def test_the_diagram_page_is_still_written_and_lists_the_errors(self):
        self._run()
        page = (self.out / "diagram.html").read_text(encoding="utf-8")
        self.assertIn("mypage &rarr; login", page)
        self.assertIn("Round trip", page)
        self.assertIn("LicensesView", page)
        self.assertIn("login --> mypage", page)

    def test_the_cli_exits_1_on_an_absent_transition_and_0_without(self):
        from argparse import Namespace
        from jsonui_doc_cli.cli import cmd_generate_html
        args = Namespace(input=str(self.face.root / "tests"), output=str(self.out), title="Face",
                         docs=None, figma=None, app=None, layouts_dir=None, config=None,
                         with_checks=False, allow_partial=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cmd_generate_html(args), 1)
        # Declare it and the same run passes.
        self.face.spec("mypage", ["Login", "LicensesView"])
        with redirect_stdout(buf):
            self.assertEqual(cmd_generate_html(args), 0)

    def test_allow_partial_does_not_cover_a_wrong_spec(self):
        from argparse import Namespace
        from jsonui_doc_cli.cli import cmd_generate_html
        args = Namespace(input=str(self.face.root / "tests"), output=str(self.out), title="Face",
                         docs=None, figma=None, app=None, layouts_dir=None, config=None,
                         with_checks=False, allow_partial=True)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cmd_generate_html(args), 1)


class NoSpecDirectoryIsAWarningNotAPileOfErrors(unittest.TestCase):
    def test_flows_without_any_spec_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "tests" / "flows" / "nav.test.json",
                   {"type": "flow", "metadata": {"name": "nav"}, "steps": [_s("login"), _s("mypage")]})
            buf = io.StringIO()
            with redirect_stdout(buf):
                generate_html_directory(root / "tests", root / "out", title="Bare")
            log = buf.getvalue()
            self.assertIn("WARNING [doc-diagram]: no spec directory", log)
            self.assertIn("1 flow test file(s) not checked", log)
            self.assertEqual(get_diagram_errors(), [])
            self.assertFalse((root / "out" / "diagram.html").exists())


class TheHtmlEntryPointReturnsTheResult(unittest.TestCase):
    def test_nothing_drawable_writes_no_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("login", ["なし（タブ切替）"])
            out = face.root / "diagram.html"
            result = generate_mermaid_html(face.specs, out, "T", face.screens, face.layouts, flows_dir=face.flows)
            self.assertEqual(result.combined, "")
            self.assertFalse(out.exists())

    def test_something_drawable_writes_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("login", ["Mypage"])
            face.spec("mypage", [])
            out = face.root / "diagram.html"
            result = generate_mermaid_html(face.specs, out, "T", face.screens, face.layouts, flows_dir=face.flows)
            self.assertTrue(result.combined)
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
