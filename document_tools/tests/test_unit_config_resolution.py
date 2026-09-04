"""Where `generate html` reads unitContracts from, in a split tree.

1.8.40 resolved one config by walking up from the tests directory. A split
tree keeps each app's spec config beside the app, and its repository root
commonly holds a DIFFERENT config carrying only `checks` — legitimate for
`jsonui-doc check`, and with no `spec_directory` it can enumerate nothing. The
walk-up stops at that one from anywhere in the tree, so the apps' contracts
were unreachable however the command was invoked: exit 0, no Unit section, and
nothing in the output distinguishing that from a project declaring none.

Three ways in, in order of how directly they say what to read: `--config`
names the file, `--app` resolves one root per app, and otherwise the original
walk-up is unchanged. When none of them finds a usable config the run says so
in the spelling the zero-warnings gate counts, because silence here is exactly
what could not be told apart from a correct zero.
"""
from __future__ import annotations

import io
import json
import contextlib
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.cli import _resolve_unit_roots
from jsonui_doc_cli.test_doc.generator import generate_html_directory

#: The expression the zero-warnings gate counts with. Asserting against THIS
#: rather than the literal text ties the test to what the gate sees: a
#: rewording that stops being counted fails here.
WARNING_RE = r"warning \[|warning:|\[warn|⚠"


class _SplitTree(unittest.TestCase):
    """Root config holds only `checks`; the spec config lives beside the app."""

    def build(self) -> Path:
        # Resolved: the resolver returns resolved paths, and on macOS an
        # unresolved temp dir differs from it by a /private prefix.
        root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "jui.config.json").write_text(
            json.dumps({"checks": {"doc": {"command": "echo ok"}}}), encoding="utf-8")

        app = root / "admin"
        specs = app / "docs" / "screens" / "json"
        specs.mkdir(parents=True)
        (app / "ios" / "Tests").mkdir(parents=True)
        (app / "jui.config.json").write_text(json.dumps({
            "spec_directory": "docs/screens/json",
            "platforms": {"ios": {"root": "ios", "unitTestsDir": "Tests",
                                  "testModule": "App"}},
        }), encoding="utf-8")
        (specs / "dashboard.spec.json").write_text(json.dumps({
            "type": "screen_spec", "version": "1.0",
            "metadata": {"screenName": "dashboard", "name": "Dash",
                         "displayName": "Dash", "description": "d."},
            "structure": {"components": [{"type": "View", "id": "root",
                                          "description": "r"}],
                          "layout": {"root": "root", "children": []}},
            "unitContracts": {"target": "DashboardViewModel",
                              "cases": [{"name": "loads", "intent": "i",
                                         "platforms": ["ios"]}]},
        }), encoding="utf-8")
        (app / "ios" / "Tests" / "DashboardViewModelContractTests.swift").write_text(
            "import XCTest\n@testable import App\n"
            "final class DashboardViewModelContractTests: XCTestCase "
            "{ func test_loads() throws {} }\n", encoding="utf-8")

        (root / "tests" / "screens").mkdir(parents=True)
        (root / "tests" / "screens" / "s.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios", "source": {"layout": "s"},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "opens", "description": "o",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        return root

    def generate(self, root: Path, *, config=None, apps=None) -> tuple[Path, str]:
        roots = _resolve_unit_roots(config, apps, root / "tests")
        out = root / "out"
        out.mkdir(exist_ok=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            generate_html_directory(
                root / "tests", out, "T", apps=apps,
                unit_roots=[{"app": e.get("app"), "root": e["root"]} for e in roots])
        return out, buf.getvalue()


class ResolutionPicksTheConfigThatDeclaresSpecs(_SplitTree):
    def test_the_bare_walk_up_still_lands_on_the_checks_only_root(self):
        # Not a regression to fix by changing the walk-up: a config holding
        # only `checks` is a legitimate terminus. It is why an explicit way in
        # was needed rather than a cleverer search.
        root = self.build()
        got = _resolve_unit_roots(None, None, root / "tests")
        self.assertEqual([e["config"] for e in got], [root / "jui.config.json"])

    def test_app_resolves_the_config_beside_that_app(self):
        root = self.build()
        got = _resolve_unit_roots(
            None, [{"name": "admin", "docs_path": root / "admin" / "docs"}],
            root / "tests")
        self.assertEqual([(e["app"], e["config"]) for e in got],
                         [("admin", root / "admin" / "jui.config.json")])

    def test_config_names_the_file_and_skips_the_walk_up(self):
        root = self.build()
        got = _resolve_unit_roots(
            str(root / "admin" / "jui.config.json"), None, root / "tests")
        self.assertEqual([e["config"] for e in got],
                         [root / "admin" / "jui.config.json"])


class TheAppsContractsBecomeReachable(_SplitTree):
    def test_app_enumerates_the_apps_specs_and_writes_a_real_page(self):
        root = self.build()
        out, _ = self.generate(
            root, apps=[{"name": "admin", "docs_path": root / "admin" / "docs"}])
        page = out / "admin" / "unit" / "DashboardViewModel.html"
        self.assertTrue(page.is_file(), "no unit page for the app's target")
        body = page.read_text(encoding="utf-8")
        # A failed write leaves a placeholder AT THE SAME PATH, so existence
        # alone does not distinguish a generated page from a failed one.
        self.assertNotIn("could not be generated", body)
        self.assertIn("DashboardViewModel", body)

    def test_config_reaches_the_same_contracts(self):
        root = self.build()
        out, _ = self.generate(
            root, config=str(root / "admin" / "jui.config.json"))
        self.assertTrue((out / "unit" / "DashboardViewModel.html").is_file())

    def test_with_neither_the_run_warns_in_the_counted_spelling(self):
        root = self.build()
        out, printed = self.generate(root)
        self.assertRegex(printed.lower(), WARNING_RE)
        self.assertIn("spec_directory", printed)
        self.assertEqual(list(out.rglob("unit/*.html")), [],
                         "no config declares specs, so there is nothing to enumerate")


if __name__ == "__main__":
    unittest.main()
