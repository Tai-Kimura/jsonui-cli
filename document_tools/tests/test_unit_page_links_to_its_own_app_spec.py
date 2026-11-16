"""A unit page links back to the spec page of ITS OWN app, or to nothing.

The reporting face saw no back-link at all: 19 unit pages, 19 spec pages, 0
links, and the tool printing "19 target(s) could not be linked". The cause is
an ordering, measured by tracing the real run:

    root-scope spec pages are written  -> spec_files_info
    unit pages are written             -> handed THAT spec_files_info
    app-scope spec pages are written   -> too late to be in it

An app-scoped project (every spec under `--app <name>:<dir>`) leaves the
root-scope list empty, so `by_key` is empty and every lookup misses.

BUT "the link is missing" is only half of it, and the smaller half. The href
is built as `../<root-relative page path>`, which from `<app>/unit/` resolves
into `<app>/specs/`. So the decision is taken against the ROOT tree while the
resolution happens in the APP tree:

    emit decided by     "does the root scope have a page with this key"
    resolution decided by "does <app>/specs/<name>.html exist"

Those are two different predicates that agree only where the names overlap.
On a second face 8 of 25 targets linked, and all 8 were overlapping names —
correct by coincidence. A name the root scope has and the app does not emits
a link that dangles, which is worse than the missing link that was reported.

So the arms below pin BOTH: a target whose own app wrote its spec page gets a
resolving link, and no emitted href may dangle. Links are resolved against
the filesystem, never string-matched — a wrong relative depth and a missing
link are different defects and only resolution separates them.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import generate_html_directory

HREF = re.compile(r"""href\s*=\s*(['"])(.*?)\1""", re.I | re.S)


def _screen_spec(name: str, target: str | None) -> dict:
    spec = {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": name, "name": "Scr", "displayName": "Scr",
                     "description": "A screen."},
        "structure": {"components": [{"type": "View", "id": "root",
                                      "description": "r"}],
                      "layout": {"root": "root", "children": []}},
    }
    if target:
        spec["unitContracts"] = {
            "target": target,
            "cases": [{"name": f"case_{target}", "intent": "does",
                       "platforms": ["ios"]}],
        }
    return spec


class _Site(unittest.TestCase):
    def _root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "tests" / "screens").mkdir(parents=True)
        (root / "tests" / "screens" / "s.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios", "source": {"layout": "s"},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "opens", "description": "opens",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        return root

    def _config(self, root: Path, spec_dir: str) -> None:
        (root / "jui.config.json").write_text(json.dumps({
            "spec_directory": spec_dir,
            "platforms": {"ios": {"root": "ios", "unitTestsDir": "Tests",
                                  "testModule": "App"}},
        }), encoding="utf-8")

    def _impl(self, root: Path, *targets: str) -> None:
        d = root / "ios" / "Tests"
        d.mkdir(parents=True, exist_ok=True)
        for t in targets:
            (d / f"{t}ContractTests.swift").write_text(
                "import XCTest\n@testable import App\n"
                f"final class {t}ContractTests: XCTestCase "
                f"{{ func test_case_{t}() throws {{}} }}\n", encoding="utf-8")

    def hrefs_of(self, page: Path) -> list[str]:
        self.assertTrue(page.is_file(), f"{page} was not generated")
        return [m.group(2) for m in HREF.finditer(page.read_text(encoding="utf-8"))]

    def spec_links(self, page: Path) -> list[tuple[str, Path]]:
        """(href, resolved path) for each link into a specs/ directory."""
        out = []
        for h in self.hrefs_of(page):
            if "specs/" not in h or not h.endswith(".html"):
                continue
            out.append((h, Path(os.path.normpath(page.parent / h))))
        return out

    def assert_no_dangling(self, page: Path) -> None:
        for h, resolved in self.spec_links(page):
            self.assertTrue(
                resolved.is_file(),
                f"{page.name} emits href={h!r}, resolving to {resolved} — "
                "no such file. A dangling back-link is worse than none: the "
                "page claims a spec page exists for this target.")


class AppScopedProjectLinksBack(_Site):
    """park's shape: every spec lives under `--app`, root scope has none."""

    def build(self) -> Path:
        root = self._root()
        admin_docs = root / "docs" / "admin"
        specs = admin_docs / "screens" / "json"
        specs.mkdir(parents=True)
        self._config(root, "docs/admin/screens/json")
        for name, target in (("account_settings", "AccountSettingsHandler"),
                             ("billing", "BillingHandler")):
            (specs / f"{name}.spec.json").write_text(
                json.dumps(_screen_spec(name, target)), encoding="utf-8")
        self._impl(root, "AccountSettingsHandler", "BillingHandler")
        out = root / "out"
        out.mkdir()
        generate_html_directory(
            root / "tests", out, "T",
            apps=[{"name": "admin", "docs_path": str(admin_docs)}],
            unit_roots=[{"app": "admin", "root": str(root)}],
        )
        return out

    def test_each_target_links_to_its_own_apps_spec_page(self):
        out = self.build()
        for target, spec in (("AccountSettingsHandler", "account_settings"),
                             ("BillingHandler", "billing")):
            page = out / "admin" / "unit" / f"{target}.html"
            links = self.spec_links(page)
            self.assertTrue(
                links,
                f"{target}.html has no link to a spec page. Its app wrote "
                f"admin/specs/{spec}.html in the same run.")
            self.assertTrue(
                any(r.is_file() and r.name == f"{spec}.html" for _, r in links),
                f"{target}.html links to {[h for h, _ in links]}, none of "
                f"which resolves to admin/specs/{spec}.html")

    def test_no_unit_page_emits_a_dangling_spec_link(self):
        out = self.build()
        for page in sorted((out / "admin" / "unit").glob("*.html")):
            self.assert_no_dangling(page)


class RootOnlyNameDoesNotBecomeAnAppLink(_Site):
    """The dangling half: a name the ROOT scope has and the app does not.

    The target belongs to `admin`, but its declaring spec page is written at
    root scope, so `admin/specs/<name>.html` is never written. Deciding from
    the root list emits `../specs/<name>.html`, which from `admin/unit/`
    resolves to the app page that does not exist.
    """

    def build(self) -> Path:
        root = self._root()
        root_specs = root / "docs" / "screens" / "json"
        root_specs.mkdir(parents=True)
        self._config(root, "docs/screens/json")
        (root_specs / "ghost.spec.json").write_text(
            json.dumps(_screen_spec("ghost", "GhostHandler")), encoding="utf-8")

        admin_docs = root / "docs" / "admin"
        admin_specs = admin_docs / "screens" / "json"
        admin_specs.mkdir(parents=True)
        (admin_specs / "settings.spec.json").write_text(
            json.dumps(_screen_spec("settings", None)), encoding="utf-8")

        self._impl(root, "GhostHandler")
        out = root / "out"
        out.mkdir()
        generate_html_directory(
            root / "tests", out, "T", docs_dirs=[root / "docs"],
            apps=[{"name": "admin", "docs_path": str(admin_docs)}],
            unit_roots=[{"app": "admin", "root": str(root)}],
        )
        return out

    def test_the_app_page_does_not_link_to_a_root_only_spec(self):
        out = self.build()
        page = out / "admin" / "unit" / "GhostHandler.html"
        self.assert_no_dangling(page)


class SingleRootProjectIsUnchanged(_Site):
    """The population this change is not for — it already worked."""

    def build(self) -> Path:
        root = self._root()
        specs = root / "docs" / "screens" / "json"
        specs.mkdir(parents=True)
        self._config(root, "docs/screens/json")
        (specs / "profile.spec.json").write_text(
            json.dumps(_screen_spec("profile", "ProfileHandler")),
            encoding="utf-8")
        self._impl(root, "ProfileHandler")
        out = root / "out"
        out.mkdir()
        generate_html_directory(root / "tests", out, "T", project_root=root)
        return out

    def test_the_back_link_is_present_and_resolves(self):
        out = self.build()
        page = out / "unit" / "ProfileHandler.html"
        links = self.spec_links(page)
        self.assertTrue(links, "the single-root back-link disappeared")
        self.assertTrue(any(r.is_file() and r.name == "profile.html"
                            for _, r in links), [h for h, _ in links])
        self.assert_no_dangling(page)


class TheAppsOwnPageWinsOverASameNamedRootPage(_Site):
    """Both scopes carry the name; the app's target must reach the app's page.

    This is what makes the precedence load-bearing. `by_key` is filled from
    the root scope first and each app after, so the app's page overwrites the
    root's; reverse that order and this target links out of its own subtree
    to a page about a different screen — which still RESOLVES, so only a test
    that names the expected file can see it.
    """

    def build(self) -> Path:
        root = self._root()
        root_specs = root / "docs" / "screens" / "json"
        root_specs.mkdir(parents=True)
        self._config(root, "docs/admin/screens/json")
        (root_specs / "settings.spec.json").write_text(
            json.dumps(_screen_spec("settings", None)), encoding="utf-8")

        admin_docs = root / "docs" / "admin"
        admin_specs = admin_docs / "screens" / "json"
        admin_specs.mkdir(parents=True)
        (admin_specs / "settings.spec.json").write_text(
            json.dumps(_screen_spec("settings", "SettingsHandler")),
            encoding="utf-8")

        self._impl(root, "SettingsHandler")
        out = root / "out"
        out.mkdir()
        generate_html_directory(
            root / "tests", out, "T", docs_dirs=[root / "docs"],
            apps=[{"name": "admin", "docs_path": str(admin_docs)}],
            unit_roots=[{"app": "admin", "root": str(root)}],
        )
        return out

    def test_it_links_to_the_apps_page_not_the_root_one(self):
        out = self.build()
        page = out / "admin" / "unit" / "SettingsHandler.html"
        links = self.spec_links(page)
        self.assertTrue(links, "no back-link at all")
        resolved = [r for _, r in links if r.is_file()]
        self.assertTrue(resolved, [h for h, _ in links])
        for r in resolved:
            # Both sides resolved: on macOS the temp dir is reached through
            # /var -> /private/var, so comparing one resolved path against
            # one merely normalised one fails on the symlink, not the link.
            self.assertEqual(
                r.resolve(), (out / "admin" / "specs" / "settings.html").resolve(),
                f"linked to {r}, but this target is declared by the app's "
                "own settings.spec.json")
        self.assert_no_dangling(page)


class AMissSaysWhyItMissed(_Site):
    """The warning names the repair, not only the count.

    "19 target(s) could not be linked" sends every reader to trace the run to
    learn which of three unrelated repairs applies: the scope wrote no spec
    pages at all, the contract names no spec file, or the name simply is not
    there. The reporting face traced it; the message should have said it.
    """

    def build(self) -> Path:
        root = self._root()
        # The contracts are read from spec_directory, but that directory is
        # not one the page generator scans, so no spec page is ever written
        # for this scope — the first of the three reasons.
        specs = root / "docs" / "units" / "json"
        specs.mkdir(parents=True)
        self._config(root, "docs/units/json")
        (specs / "orphan.spec.json").write_text(
            json.dumps(_screen_spec("orphan", "OrphanHandler")),
            encoding="utf-8")
        self._impl(root, "OrphanHandler")
        out = root / "out"
        out.mkdir()
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            generate_html_directory(root / "tests", out, "T",
                                    project_root=root)
        self.printed = buf.getvalue()
        return out

    def test_the_warning_carries_a_reason(self):
        self.build()
        lines = [l for l in self.printed.splitlines()
                 if "could not be linked" in l]
        self.assertTrue(lines, "no miss was reported at all:\n" + self.printed)
        self.assertTrue(
            any("(" in l and "scope" in l or "spec file" in l or "name" in l
                for l in lines),
            f"the warning still says only how many: {lines}")
