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
import re
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


class TheOwnersFindAnAppsFlowTestsWhereItsConfigSaysTheyAre(unittest.TestCase):
    """A split tree keeps each app's tests beside the app (`<app>/tests`,
    declared by `test.src`), not under the run's input directory. The first
    owner resolution looked only at `<input>/<app>/flows` and checked 0 of a
    face's 59 flow tests — which reads as "no violations". Measured by a
    triage lane on an isolated copy, 2026-09-10."""

    def test_flow_tests_declared_by_test_src_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "alpha"
            _write(app / "jui.config.json", {
                "spec_directory": "../docs/alpha/screens/json",
                "layouts_directory": "../docs/alpha/screens/layouts",
                "test": {"src": "tests"}})
            for name, dests in (("login", ["Mypage"]), ("mypage", [])):
                _write(root / "docs" / "alpha" / "screens" / "layouts" / f"{name}.json", {"type": "View"})
                _write(root / "docs" / "alpha" / "screens" / "json" / f"{name}.spec.json", {
                    "type": "screen_spec", "version": "1.0",
                    "metadata": {"name": name, "displayName": name, "description": "d"},
                    "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                                  "layout": {"root": "root", "children": []}},
                    "transitions": [{"trigger": "t", "condition": "c", "destination": d} for d in dests]})
            # the app's own flow test, beside the app — with an absent transition
            _write(app / "tests" / "flows" / "nav.test.json",
                   {"type": "flow", "metadata": {"name": "Round trip"},
                    "steps": [_s("login"), _s("mypage"), _s("login")]})
            # the run's input is a DIFFERENT tests directory (another app's)
            _write(root / "beta" / "tests" / "screens" / "x.test.json",
                   {"type": "screen", "source": {"layout": "x.json"}, "metadata": {"name": "X"},
                    "cases": [{"name": "c", "steps": []}]})
            buf = io.StringIO()
            with redirect_stdout(buf):
                generate_html_directory(
                    root / "beta" / "tests", root / "out", title="Split",
                    apps=[{"name": "alpha", "docs_path": root / "docs" / "alpha"}],
                    unit_roots=[{"app": "alpha", "root": app}],
                    test_roots=[{"app": "alpha", "root": app / "tests"}])
            log = buf.getvalue()
            self.assertIn("flow tests 1 in", log, log)
            self.assertIn("(declared test root)", log)
            self.assertEqual([(e["owner"], e["from"], e["to"]) for e in get_diagram_errors()],
                             [("alpha", "mypage", "login")])

    def test_an_app_with_no_test_root_says_so_instead_of_naming_a_directory_it_never_looked_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "beta" / "jui.config.json", {
                "spec_directory": "../docs/beta/screens/json",
                "layouts_directory": "../docs/beta/screens/layouts"})
            _write(root / "docs" / "beta" / "screens" / "layouts" / "login.json", {"type": "View"})
            _write(root / "docs" / "beta" / "screens" / "json" / "login.spec.json", {
                "type": "screen_spec", "version": "1.0",
                "metadata": {"name": "login", "displayName": "login", "description": "d"},
                "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                              "layout": {"root": "root", "children": []}},
                "transitions": [{"trigger": "t", "condition": "c", "destination": "外部ブラウザ（https://x/）"}]})
            _write(root / "alpha" / "tests" / "screens" / "x.test.json",
                   {"type": "screen", "source": {"layout": "x.json"}, "metadata": {"name": "X"},
                    "cases": [{"name": "c", "steps": []}]})
            buf = io.StringIO()
            with redirect_stdout(buf):
                generate_html_directory(
                    root / "alpha" / "tests", root / "out", title="NoRoot",
                    apps=[{"name": "beta", "docs_path": root / "docs" / "beta"}],
                    unit_roots=[{"app": "beta", "root": root / "beta"}])
            log = buf.getvalue()
            self.assertIn("no test root for beta", log, log)
            self.assertNotIn("flow tests 0 in", log)
            line = [l for l in log.splitlines() if "no test root for beta" in l][0]
            self.assertIn("(nothing declared;", line)
            self.assertNotIn("(declared ", line)

    def test_a_declared_but_absent_test_src_is_named_by_its_declared_path(self):
        # A face read the fallback path as "where its tests are supposed to
        # live". An app that declares test.src is judged by that path.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "beta" / "jui.config.json", {
                "spec_directory": "../docs/beta/screens/json",
                "layouts_directory": "../docs/beta/screens/layouts",
                "test": {"src": "tests"}})
            _write(root / "docs" / "beta" / "screens" / "layouts" / "login.json", {"type": "View"})
            _write(root / "docs" / "beta" / "screens" / "json" / "login.spec.json", {
                "type": "screen_spec", "version": "1.0",
                "metadata": {"name": "login", "displayName": "login", "description": "d"},
                "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                              "layout": {"root": "root", "children": []}},
                "transitions": [{"trigger": "t", "condition": "c", "destination": "外部ブラウザ（https://x/）"}]})
            _write(root / "alpha" / "tests" / "screens" / "x.test.json",
                   {"type": "screen", "source": {"layout": "x.json"}, "metadata": {"name": "X"},
                    "cases": [{"name": "c", "steps": []}]})
            buf = io.StringIO()
            with redirect_stdout(buf):
                generate_html_directory(
                    root / "alpha" / "tests", root / "out", title="Declared",
                    apps=[{"name": "beta", "docs_path": root / "docs" / "beta"}],
                    unit_roots=[{"app": "beta", "root": root / "beta"}])
            log = buf.getvalue()
            line = [l for l in log.splitlines() if "no test root for beta" in l][0]
            self.assertIn(f"declared {(root / 'beta' / 'tests').resolve()} absent", line)
            self.assertNotIn("alpha", line)

    def test_without_test_roots_the_shared_tests_app_shape_still_works(self):
        # 陰性対照 for the arm above: the `tests/<app>/` shape has no test.src
        # and is found under the input directory, as before.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "alpha" / "jui.config.json", {
                "spec_directory": "../docs/alpha/screens/json",
                "layouts_directory": "../docs/alpha/screens/layouts"})
            for name, dests in (("login", ["Mypage"]), ("mypage", [])):
                _write(root / "docs" / "alpha" / "screens" / "layouts" / f"{name}.json", {"type": "View"})
                _write(root / "docs" / "alpha" / "screens" / "json" / f"{name}.spec.json", {
                    "type": "screen_spec", "version": "1.0",
                    "metadata": {"name": name, "displayName": name, "description": "d"},
                    "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                                  "layout": {"root": "root", "children": []}},
                    "transitions": [{"trigger": "t", "condition": "c", "destination": d} for d in dests]})
            _write(root / "tests" / "alpha" / "flows" / "nav.test.json",
                   {"type": "flow", "metadata": {"name": "Round trip"},
                    "steps": [_s("login"), _s("mypage"), _s("login")]})
            with redirect_stdout(io.StringIO()):
                generate_html_directory(
                    root / "tests", root / "out", title="Shared",
                    apps=[{"name": "alpha", "docs_path": root / "docs" / "alpha"}],
                    unit_roots=[{"app": "alpha", "root": root / "alpha"}])
            self.assertEqual([(e["owner"], e["from"], e["to"]) for e in get_diagram_errors()],
                             [("alpha", "mypage", "login")])


class InferredNoneIsListedNotHidden(unittest.TestCase):
    """`none` is a positive declaration — but today every `none` is INFERRED
    from wording, so a screen name that happens to contain 画面内 or SPA
    would vanish with the same silence. Listed, not warned (a consumer lane's
    proposal, 2026-09-10)."""

    def test_nones_are_counted_listed_on_the_page_and_not_drawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("mypage", ["request モード（画面内状態）", "Settings"])
            face.spec("settings", [])
            out = face.root / "diagram.html"
            result = generate_mermaid_html(face.specs, out, "T", face.screens, face.layouts, flows_dir=face.flows)
            self.assertEqual([(n.source, n.raw) for n in result.nones], [("mypage", "request モード（画面内状態）")])
            self.assertEqual(result.stats["none_inferred"], 1)
            self.assertEqual(result.unresolved, [])
            page = out.read_text(encoding="utf-8")
            self.assertIn("read as &ldquo;no screen transition&rdquo; from their wording", page)
            self.assertIn("request モード", page)
            self.assertNotIn("mypage --> request", result.combined)

    def test_an_empty_destination_is_unresolved_not_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("mypage", [""])
            result = face.build()
            self.assertEqual(result.nones, [])
            self.assertEqual([u.kind for u in result.unresolved], ["unknown"])


class AParentSpecsTransitionsLiveInItsSubSpecs(unittest.TestCase):
    """`chat.spec.json` (screen_parent_spec) carries no transitions; its 15
    live in `chat/chat-core.spec.json` (screen_sub_spec). Reading the parent
    alone said "chat's spec declares no transition to mypage" for 42 flow
    tests on one face (reported by that face, 2026-09-10)."""

    def _parent(self, face: _Face) -> None:
        face.layout("chat")
        _write(face.specs / "chat.spec.json", {
            "type": "screen_parent_spec", "version": "1.0",
            "metadata": {"name": "Chat", "displayName": "Chat", "description": "d"},
            "subSpecs": [{"file": "chat/chat-core.spec.json", "name": "core"}],
        })
        _write(face.specs / "chat" / "chat-core.spec.json", {
            "type": "screen_sub_spec", "version": "1.0",
            "metadata": {"name": "ChatCore", "description": "d"},
            "transitions": [{"trigger": "t", "condition": "c", "destination": "Mypage"}],
        })

    def test_the_sub_specs_transitions_are_the_parents(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("mypage", [])
            self._parent(face)
            face.flow("nav", [_s("chat"), _s("mypage")])
            result = face.build()
            self.assertIn("chat --> mypage", result.combined)
            self.assertEqual(result.errors, [])
            origin = [t.spec_file for t in result.transitions_of("chat")] if hasattr(result, "transitions_of") else None

    def test_a_sub_spec_file_is_not_a_screen_of_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("mypage", [])
            self._parent(face)
            result = face.build()
            self.assertNotIn("chat-core", result.combined)
            self.assertNotIn("chat_core", result.combined)


class ADestinationNamingSeveralScreensDeclaresEach(unittest.TestCase):
    def test_chat_or_mypage_is_two_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("chat", [])
            face.spec("mypage", [])
            face.spec("profiling", ["Chat or Mypage（source依存。onDismissコールバックで遷移元に戻る）"])
            face.flow("nav", [_s("profiling"), _s("mypage")])
            result = face.build()
            self.assertIn("profiling --> chat", result.combined)
            self.assertIn("profiling --> mypage", result.combined)
            self.assertEqual(result.errors, [])

    def test_one_resolving_part_is_the_classifiers_single_answer(self):
        # 陰性対照: "Chat / Nowhere" resolves one screen — the classifier's
        # answer stands and no second edge appears.
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("chat", [])
            face.spec("profiling", ["Chat / Nowhere"])
            result = face.build()
            self.assertIn("profiling --> chat", result.combined)
            self.assertEqual(result.combined.count("profiling -->"), 1)


class TheRunShapeDoesNotChangeWhatIsChecked(unittest.TestCase):
    """Measured by triage 2026-09-10 on one corpus: no --app → 59 flow tests /
    36 errors; `--app client` → 0 / 0 and exit 0. The rule was silently never
    applied in the shape the face uses to build its site."""

    def _face(self, root: Path) -> _Face:
        face = _Face(root)
        face.spec("login", ["Mypage"])
        face.spec("mypage", [])
        face.flow("nav", [_s("login"), _s("mypage"), _s("login")], flow_name="Round trip")
        return face

    def _run(self, face: _Face, with_app: bool) -> tuple[str, list[dict]]:
        buf = io.StringIO()
        kwargs = {}
        if with_app:
            kwargs = dict(apps=[{"name": "face", "docs_path": face.root / "docs"}],
                          unit_roots=[{"app": "face", "root": face.root}],
                          test_roots=[{"app": "face", "root": face.root / "tests"}])
        with redirect_stdout(buf):
            generate_html_directory(face.root / "tests", face.root / "out", title="Shape", **kwargs)
        return buf.getvalue(), get_diagram_errors()

    def test_no_app_and_app_check_the_same_flow_tests(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            log0, errors0 = self._run(self._face(Path(a)), with_app=False)
            log1, errors1 = self._run(self._face(Path(b)), with_app=True)
            n0 = re.search(r"flow tests (\d+) in", log0).group(1)
            n1 = re.search(r"flow tests (\d+) in", log1).group(1)
            self.assertEqual((n0, n1), ("1", "1"))
            self.assertEqual([(e["from"], e["to"]) for e in errors0], [("mypage", "login")])
            self.assertEqual([(e["from"], e["to"]) for e in errors1], [("mypage", "login")])


class TheClosingLineCountsTheWholeCommand(unittest.TestCase):
    """Warnings the CLI prints BEFORE generate_html_directory (no
    jui.config.json, a missing --figma) were dropped by the accounting reset
    inside it, and the closing line printed a confident number one to two
    short of the gate's expression (verification lane, 4 runs, 2026-09-10).
    The only window that sees this is the command itself, in-process."""

    def test_closing_line_equals_the_gates_expression_over_the_output(self):
        import contextlib
        from jsonui_doc_cli.cli import cmd_generate_html
        from jsonui_doc_cli.run_log import COUNTING_RE
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "tests" / "flows" / "nav.test.json",
                   {"type": "flow", "metadata": {"name": "nav"}, "steps": [_s("login"), _s("mypage")]})
            args = Namespace(input=str(root / "tests"), output=str(root / "out"), title="Bare",
                             docs=None, figma=str(root / "no-such-figma"), app=None, layouts_dir=None,
                             config=None, with_checks=False, allow_partial=False)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), contextlib.redirect_stderr(err):
                cmd_generate_html(args)
            text = out.getvalue() + err.getvalue()
            gate = sum(1 for line in text.splitlines() if COUNTING_RE.search(line))
            closing = re.search(r"warnings (\d+)\)", text)
            self.assertIsNotNone(closing, text)
            self.assertIn("WARNING [doc-figma]", text)
            self.assertEqual(int(closing.group(1)), gate, text)

    def test_a_warning_printed_after_generation_is_counted_too(self):
        """The specimen the arm above cannot reach: `generation_warnings()`
        fires only when a spec directory was scanned and held nothing, which
        happens AFTER generate_html_directory. Putting the closing line ahead
        of that warning left every other arm green (verification lane's
        surviving mutation M1c, 2026-09-10, measured: gate 2 / closing 1)."""
        import contextlib
        from jsonui_doc_cli.cli import cmd_generate_html
        from jsonui_doc_cli.run_log import COUNTING_RE
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "tests" / "screens" / "x.test.json",
                   {"type": "screen", "source": {"layout": "x.json"}, "metadata": {"name": "X"},
                    "cases": [{"name": "c", "steps": []}]})
            (root / "specs").mkdir()  # declared, scanned, empty
            _write(root / "jui.config.json", {"spec_directory": "specs"})
            args = Namespace(input=str(root / "tests"), output=str(root / "out"), title="Empty",
                             docs=None, figma=None, app=None, layouts_dir=None,
                             config=str(root / "jui.config.json"), with_checks=False, allow_partial=False)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), contextlib.redirect_stderr(err):
                cmd_generate_html(args)
            text = out.getvalue() + err.getvalue()
            # 陽性対照 on the specimen: the after-generation warning did fire.
            self.assertIn("WARNING [doc]: 0 spec file(s) scanned", text, text)
            gate = sum(1 for line in text.splitlines() if COUNTING_RE.search(line))
            closing = re.search(r"warnings (\d+)\)", text)
            self.assertIsNotNone(closing, text)
            self.assertEqual(int(closing.group(1)), gate, text)
            # and the closing line comes AFTER that warning, not before it
            self.assertLess(text.index("WARNING [doc]: 0 spec file(s) scanned"), text.index("warnings "))


class EveryResolvedEdgeIsDrawnSomewhere(unittest.TestCase):
    """The group tabs draw edges within a group; an edge between two groups
    was drawn in no tab and listed nowhere (a face counted 29 resolved and
    19 drawn, 2026-09-10). The All tab draws all of them, first."""

    def test_a_cross_group_edge_is_in_the_all_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("mypage", ["Catalog"])
            face.spec("catalog", [])
            _write(face.screens / "mypage_t.test.json", {
                "type": "screen", "metadata": {"name": "Mypage", "group": "account"},
                "source": {"layout": "Layouts/mypage.json"}, "cases": []})
            _write(face.screens / "catalog_t.test.json", {
                "type": "screen", "metadata": {"name": "Catalog", "group": "catalog"},
                "source": {"layout": "Layouts/catalog.json"}, "cases": []})
            out = face.root / "diagram.html"
            result = generate_mermaid_html(face.specs, out, "T", face.screens, face.layouts, flows_dir=face.flows)
            self.assertEqual(list(result.diagrams)[0], "All")
            self.assertIn("mypage --> catalog", result.diagrams["All"])
            # and in no group tab — that is what made it invisible
            self.assertNotIn("mypage --> catalog", result.diagrams["account"])
            self.assertNotIn("mypage --> catalog", result.diagrams["catalog"])
            page = out.read_text(encoding="utf-8")
            self.assertLess(page.index(">All<"), page.index(">account<"))


class AReturnDeclaredAsBackAcceptsTheFlowsForwardStep(unittest.TestCase):
    """A sheet's spec says `dismiss`; the flow taps "save" and lands on the
    opener as a forward step. The spec declared that return (as back, drawn
    dotted to each pusher) — the check must accept it. Asked by a face
    2026-09-10; corpus count after their edit: 0, so this pins the rule's
    reading rather than a live failure."""

    def test_forward_step_onto_a_pusher_of_a_back_declaring_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("settings", ["ChangeEmailSheet"])
            face.spec("change_email_sheet", ["dismiss（保存後に閉じる）"])
            face.flow("save", [_s("settings"), _s("change_email_sheet"), _s("settings")])
            result = face.build()
            self.assertIn("change_email_sheet -.-> settings", result.combined)
            self.assertEqual(result.errors, [])

    def test_a_forward_step_onto_a_screen_that_never_pushed_it_is_still_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("settings", ["ChangeEmailSheet"])
            face.spec("change_email_sheet", ["dismiss（保存後に閉じる）"])
            face.spec("mypage", [])
            face.flow("odd", [_s("settings"), _s("change_email_sheet"), _s("mypage")])
            result = face.build()
            self.assertEqual([(e.from_id, e.to_id) for e in result.errors], [("change_email_sheet", "mypage")])


class TheBackToIndexLinkResolves(unittest.TestCase):
    """Every per-app diagram since v1.8.64 linked to `index.html` beside
    itself — `<app>/index.html`, which does not exist. Reported by the user
    2026-09-10 on a distributed site."""

    def test_href_for_root_and_nested_pages(self):
        from jsonui_doc_cli.test_doc.mermaid.generator import index_href_for
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(index_href_for(root / "diagram.html", root), "index.html")
            self.assertEqual(index_href_for(root / "user" / "diagram.html", root), "../index.html")
            self.assertEqual(index_href_for(root / "a" / "b" / "diagram.html", root), "../../index.html")
            self.assertEqual(index_href_for(root / "x" / "diagram.html", None), "index.html")

    def test_an_apps_diagram_page_links_to_the_real_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "alpha"
            _write(app / "jui.config.json", {
                "spec_directory": "../docs/alpha/screens/json",
                "layouts_directory": "../docs/alpha/screens/layouts",
                "test": {"src": "tests"}})
            for name, dests in (("login", ["Mypage"]), ("mypage", [])):
                _write(root / "docs" / "alpha" / "screens" / "layouts" / f"{name}.json", {"type": "View"})
                _write(root / "docs" / "alpha" / "screens" / "json" / f"{name}.spec.json", {
                    "type": "screen_spec", "version": "1.0",
                    "metadata": {"name": name, "displayName": name, "description": "d"},
                    "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                                  "layout": {"root": "root", "children": []}},
                    "transitions": [{"trigger": "t", "condition": "c", "destination": d} for d in dests]})
            _write(app / "tests" / "screens" / "x.test.json",
                   {"type": "screen", "source": {"layout": "x.json"}, "metadata": {"name": "X"},
                    "cases": [{"name": "c", "steps": []}]})
            out = root / "out"
            with redirect_stdout(io.StringIO()):
                generate_html_directory(
                    app / "tests", out, title="Site",
                    apps=[{"name": "alpha", "docs_path": root / "docs" / "alpha"}],
                    unit_roots=[{"app": "alpha", "root": app}],
                    test_roots=[{"app": "alpha", "root": app / "tests"}])
            page = out / "alpha" / "diagram.html"
            self.assertTrue(page.exists())
            href = re.search(r'<a href="([^"]+)">Back to Index</a>', page.read_text(encoding="utf-8")).group(1)
            self.assertEqual(href, "../index.html")
            self.assertTrue((page.parent / href).resolve().exists(), "the link must land on a file")

    def test_a_root_diagram_page_still_links_beside_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("login", ["Mypage"])
            face.spec("mypage", [])
            face.flow("nav", [_s("login"), _s("mypage")])  # the run needs at least one test file
            with redirect_stdout(io.StringIO()):
                generate_html_directory(face.root / "tests", face.root / "out", title="Root")
            page = face.root / "out" / "diagram.html"
            href = re.search(r'<a href="([^"]+)">Back to Index</a>', page.read_text(encoding="utf-8")).group(1)
            self.assertEqual(href, "index.html")
            self.assertTrue((page.parent / href).exists())

    def test_no_template_in_the_module_hard_codes_the_index_link(self):
        """A second, tab-less template kept the literal `href="index.html"`
        with zero callers — dead code with a known 404 in it, which no arm
        can turn red until someone wires it up again. Removed; this pins
        that the literal does not come back."""
        import jsonui_doc_cli
        import jsonui_doc_cli.test_doc.mermaid.generator as gen
        package = Path(jsonui_doc_cli.__file__).parent
        offenders = [str(f.relative_to(package)) for f in package.rglob("*.py")
                     if 'href="index.html"' in f.read_text(encoding="utf-8")]
        self.assertEqual(offenders, [], "a hard-coded index link (package-wide; f325efeb had 1)")
        self.assertIn('href="{index_href}"', Path(gen.__file__).read_text(encoding="utf-8"))


class ASubgraphNeverSharesAnIdWithANode(unittest.TestCase):
    """Mermaid keeps subgraphs and nodes in one id space. A group named after
    its screen — the most natural naming — made the node its own parent and
    the whole All tab refused to render ("would create a cycle"); 2 of 3 and
    2 of 5 subgraphs on two faces, the day the All tab shipped (2026-09-10).
    The CLI said edges 29 / ERROR 0 / exit 0 throughout."""

    def _face(self, root: Path) -> _Face:
        face = _Face(root)
        face.spec("mypage", ["Settings"])
        face.spec("settings", [])
        _write(face.screens / "mypage_t.test.json", {
            "type": "screen", "metadata": {"name": "Mypage", "group": "mypage"},
            "source": {"layout": "Layouts/mypage.json"}, "cases": []})
        _write(face.screens / "settings_t.test.json", {
            "type": "screen", "metadata": {"name": "Settings", "group": "mypage"},
            "source": {"layout": "Layouts/settings.json"}, "cases": []})
        return face

    def test_the_subgraph_id_is_namespaced_and_the_label_is_not(self):
        from jsonui_doc_cli.test_doc.mermaid.generator import mermaid_id_problems
        with tempfile.TemporaryDirectory() as tmp:
            result = self._face(Path(tmp)).build()
            self.assertIn('subgraph sg_mypage["mypage"]', result.combined)
            self.assertIn('mypage["Mypage"]', result.combined)
            self.assertEqual(mermaid_id_problems(result.combined), [])
            self.assertIn("mypage --> settings", result.combined)

    def test_the_checker_sees_the_old_shape(self):
        # 陽性対照 on the tripwire: the exact text the two faces rendered.
        from jsonui_doc_cli.test_doc.mermaid.generator import mermaid_id_problems
        old = 'flowchart LR\n\n    subgraph mypage["mypage"]\n        mypage["Mypage"]\n    end\n\n    mypage --> settings'
        self.assertEqual(mermaid_id_problems(old), ["mypage"])

    def test_group_tabs_use_no_subgraph_and_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._face(Path(tmp)).build()
            self.assertNotIn("subgraph", result.diagrams["mypage"])

    def test_a_screen_id_in_the_namespace_is_pushed_out_of_it(self):
        from jsonui_doc_cli.test_doc.mermaid.generator import _emit_node_id
        self.assertEqual(_emit_node_id("sg_home"), "sg_home_node")
        self.assertEqual(_emit_node_id("home"), "home")

    def test_a_group_named_all_does_not_overwrite_the_all_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("mypage", ["Settings"])
            face.spec("settings", [])
            _write(face.screens / "mypage_t.test.json", {
                "type": "screen", "metadata": {"name": "Mypage", "group": "All"},
                "source": {"layout": "Layouts/mypage.json"}, "cases": []})
            result = face.build()
            self.assertEqual(list(result.diagrams)[0], "All")
            self.assertIn("All (group)", result.diagrams)
            self.assertIn("subgraph sg_All", result.diagrams["All"])


class ASpecCanDeclareItsGroup(unittest.TestCase):
    """The diagram is drawn from specs, but a node's group came only from a
    screen test (or an app-owned declaration). A screen with a spec and a
    layout and no test — a sheet, say — had nowhere to declare one and sat
    in "その他": 22 of 31 drawn nodes on one face (2026-09-10)."""

    def _spec_with_group(self, face: _Face, name: str, dests: list[str], group) -> None:
        face.spec(name, dests)
        path = face.specs / f"{name}.spec.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["metadata"]["group"] = group
        _write(path, data)

    def test_a_spec_only_screen_lands_in_the_group_its_spec_declares(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            self._spec_with_group(face, "store_info", ["StoreEditSheet"], "store")
            self._spec_with_group(face, "store_edit_sheet", [], "store")
            result = face.build()
            self.assertIn("store", result.diagrams)
            self.assertIn("store_edit_sheet", result.diagrams["store"])
            self.assertNotIn("その他", result.diagrams)

    def test_a_screen_tests_group_wins_over_the_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            self._spec_with_group(face, "store_info", ["Settings"], "store")
            face.spec("settings", [])
            _write(face.screens / "store_info_t.test.json", {
                "type": "screen", "metadata": {"name": "Store", "group": "catalog"},
                "source": {"layout": "Layouts/store_info.json"}, "cases": []})
            result = face.build()
            self.assertIn("store_info", result.diagrams["catalog"])
            self.assertNotIn("store", result.diagrams)

    def test_a_list_of_groups_and_the_undeclared_bucket_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            self._spec_with_group(face, "store_info", ["Settings"], ["store", "legal"])
            face.spec("settings", [])  # declares nothing -> その他
            result = face.build()
            self.assertIn("store", result.diagrams)
            self.assertIn("legal", result.diagrams)
            self.assertIn("settings", result.diagrams["その他"])


class TwoIdsThatNormalizeAlikeAreOneScreen(unittest.TestCase):
    """A layout `forgot_password.json` and a spec `forgotpassword.spec.json`
    normalize to one key. The classifier saw whichever the set yielded
    last, the winner followed PYTHONHASHSEED (one face: 3 of 6 seeds each
    way, 31 or 32 nodes), and the round trip split across two nodes with no
    warning. The winner is now decided by provenance — layout first — every
    loser is redirected, and the pair is reported."""

    def _face(self, root: Path) -> _Face:
        face = _Face(root)
        face.spec("login", ["ForgotPassword"])
        face.layout("forgot_password")                      # the layout's id
        _write(face.specs / "forgotpassword.spec.json", {   # the spec's file name
            "type": "screen_spec", "version": "1.0",
            "metadata": {"name": "ForgotPassword", "displayName": "パスワードリセット依頼", "description": "d"},
            "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                          "layout": {"root": "root", "children": []}},
            "transitions": [{"trigger": "t", "condition": "c", "destination": "Login"}]})
        return face

    def test_one_node_is_drawn_and_the_pair_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._face(Path(tmp)).build()
            self.assertEqual(result.id_collisions,
                             [("forgot_password", [("forgot_password", "layout"), ("forgotpassword", "spec")])])
            self.assertIn("login --> forgot_password", result.combined)
            self.assertIn("forgot_password --> login", result.combined)
            # The loser id must not be DRAWN — not "must not appear as text".
            # Since 2026-09-10 a node with no `source.document` links to its
            # spec page, and that page is named by the spec FILE, so the
            # loser spelling is the correct content of the href
            # (`specs/forgotpassword.html` is the file on disk;
            # `specs/forgot_password.html` does not exist). Widening the old
            # text predicate to cover the href would demand a dangling link.
            # So: exclude click lines, which name files, and assert the
            # winner separately on the one click line that exists.
            structure = "\n".join(l for l in result.combined.splitlines()
                                   if not l.strip().startswith("click "))
            self.assertNotIn("forgotpassword", structure.replace("forgot_password", ""))
            self.assertIn('click forgot_password "specs/forgotpassword.html"', result.combined)
            # the spec's label rides on the winner
            self.assertIn('forgot_password["パスワードリセット依頼"]', result.combined)

    def test_the_output_is_the_same_on_every_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = self._face(Path(tmp))
            first = face.build().combined
            for _ in range(5):
                self.assertEqual(face.build().combined, first)

    def test_no_collision_reports_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = _Face(Path(tmp))
            face.spec("login", ["Mypage"])
            face.spec("mypage", [])
            self.assertEqual(face.build().id_collisions, [])

    def test_the_site_run_names_both_ids_and_their_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            face = self._face(Path(tmp))
            face.flow("nav", [_s("login"), _s("forgot_password")])
            buf = io.StringIO()
            with redirect_stdout(buf):
                generate_html_directory(face.root / "tests", face.root / "out", title="Face")
            log = buf.getvalue()
            self.assertIn("WARNING [doc-diagram]", log)
            self.assertIn("'forgot_password' (layout) and 'forgotpassword' (spec)", log)
            self.assertEqual(get_diagram_errors(), [], "the flow reaches the winner's id")
