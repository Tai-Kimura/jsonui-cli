"""Regression: doc-generate-html-skips-invalid-specs-with-exit-0-and-stale-nav.

`generate html` validated each spec, and on errors printed
`SKIP: <name> (validation errors)` and moved on — exit 0, the page missing
from the navigation it builds out of the pages it wrote, and LAST run's copy
of that page still sitting on disk. A face regenerated its docs, saw 0, and
committed a site whose nav had quietly lost eleven screens while the eleven
stale pages stayed reachable by URL.

`--allow-partial`'s own help text already stated the contract this broke:
"an exit-0 run that quietly dropped a page leaves the index linking to a 404
nobody notices". The machinery to honour it was already here —
`record_page_failure` fails the command, names the input on stderr, and
writes a placeholder so the page on disk says what went wrong. The three
validation skips simply did not use it.

Three, not one. The ticket named the screen-spec loop; component specs and
test files had the same `print(...); continue`. The declaration that names
the population is `is_valid`, so the arms below cover each site that reads
it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli.test_doc import generate_html_directory, get_page_failures


def _spec(name: str, *, broken: bool = False) -> dict:
    spec = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"name": name.title(), "displayName": name.title(),
                     "description": f"{name} screen.", "layoutFile": name},
        "structure": {"components": [], "layout": {}},
        "dataFlow": {"viewModel": {"description": "vm", "methods": [], "vars": []}},
        "stateManagement": {"uiVariables": [], "eventHandlers": []},
    }
    if broken:
        # One error, of a kind unrelated to this change, so the arm does not
        # depend on the ambiguity predicate that moved in the same release.
        spec["branchContracts"] = {"methods": {"onAppear": {"branches": [
            {"when": {"api.A.b.c": "success"}, "then": {"api": "none"}}]}}}
        spec["dataFlow"]["viewModel"]["methods"] = ["onAppear"]
    return spec


def _test_file(*, broken: bool = False) -> dict:
    if broken:
        return {"name": "sample", "cases": []}
    return {
        "type": "screen",
        "metadata": {"name": "sample", "description": "sample."},
        "source": {"layout": "sample"},
        "cases": [{"name": "c", "description": "c.", "steps": []}],
    }


class InvalidInputsAreRecordedFailures(unittest.TestCase):
    def _build(self, root: Path, *, broken_spec=False, broken_test=False,
               spec_names=("alpha", "bravo")) -> Path:
        docs = root / "docs"
        sj = docs / "screens" / "json"
        sj.mkdir(parents=True, exist_ok=True)
        for n in spec_names:
            (sj / f"{n}.spec.json").write_text(
                json.dumps(_spec(n, broken=(broken_spec and n == "bravo"))),
                encoding="utf-8")
        tests = root / "tests"
        tests.mkdir(exist_ok=True)
        (tests / "sample.test.json").write_text(
            json.dumps(_test_file(broken=broken_test)), encoding="utf-8")
        generate_html_directory(tests, root / "html", "repro")
        return docs / "screens" / "html"

    def test_a_clean_run_records_nothing(self):
        """The over-firing control. Without it, an arm that only asserts
        'a failure was recorded' passes for a build that fails everything."""
        with TemporaryDirectory() as td:
            self._build(Path(td))
            self.assertEqual(get_page_failures(), [])

    def test_an_invalid_spec_is_recorded_not_skipped(self):
        with TemporaryDirectory() as td:
            self._build(Path(td), broken_spec=True)
            failures = get_page_failures()
            self.assertEqual(len(failures), 1, failures)
            self.assertEqual(failures[0]["kind"], "screen spec")
            self.assertTrue(
                failures[0]["source"].endswith("bravo.spec.json"),
                failures[0]["source"])

    def test_the_failure_carries_the_errors_not_just_their_existence(self):
        """`(validation errors)` sent the reader back to run the validator by
        hand. The message has to say which errors, because the placeholder
        page and the stderr summary are all the reader gets."""
        with TemporaryDirectory() as td:
            self._build(Path(td), broken_spec=True)
            text = get_page_failures()[0]["error"]
            self.assertIn("1 validation error(s)", text)
            self.assertIn("branchContracts.methods.onAppear", text)

    def test_an_invalid_test_file_is_recorded_too(self):
        """The third site. Found by measuring the other two — this suite's
        own fixture had been silently dropped here for its whole life."""
        with TemporaryDirectory() as td:
            self._build(Path(td), broken_test=True)
            kinds = [f["kind"] for f in get_page_failures()]
            self.assertIn("test", kinds)

    def test_the_stale_page_is_replaced_by_a_placeholder(self):
        """The reported symptom, in its reported order.

        Generate clean, then break the spec and generate again. Before this,
        run 2 left run 1's page byte-for-byte in place while dropping it from
        the nav — the page said nothing about being out of date, and the URL
        still served it.
        """
        with TemporaryDirectory() as td:
            root = Path(td)
            html_dir = self._build(root)
            page = html_dir / "bravo.html"
            self.assertTrue(page.exists())
            first = page.read_text(encoding="utf-8")

            self._build(root, broken_spec=True)
            second = page.read_text(encoding="utf-8")
            self.assertNotEqual(
                first, second,
                "the stale page from the previous run was left in place")
            self.assertIn("could not be generated", second)
            self.assertIn("validation error(s)", second)


class ExitCode(unittest.TestCase):
    """The exit code is a separate claim from the failure list.

    A recorded failure that does not reach the process's status is the same
    silence in a different place, so this drives the real CLI rather than
    asserting on the accounting the CLI happens to read.
    """

    def _run(self, root: Path, *extra: str) -> subprocess.CompletedProcess:
        docs = root / "docs" / "screens" / "json"
        docs.mkdir(parents=True)
        for n, broken in (("alpha", False), ("bravo", True)):
            (docs / f"{n}.spec.json").write_text(
                json.dumps(_spec(n, broken=broken)), encoding="utf-8")
        tests = root / "tests"
        tests.mkdir()
        (tests / "sample.test.json").write_text(
            json.dumps(_test_file()), encoding="utf-8")
        repo = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(repo / "document_tools"), str(repo / "test_tools"),
             env.get("PYTHONPATH", "")])
        return subprocess.run(
            [sys.executable, "-m", "jsonui_doc_cli.cli", "generate", "html",
             str(tests), "-o", str(root / "html"), *extra],
            capture_output=True, text=True, env=env, cwd=str(root))

    def test_an_invalid_spec_fails_the_command(self):
        with TemporaryDirectory() as td:
            p = self._run(Path(td))
            self.assertNotEqual(p.returncode, 0, p.stdout[-2000:])
            self.assertIn("bravo.spec.json", p.stderr)

    def test_allow_partial_still_exits_zero(self):
        """The documented escape hatch must keep working — the change makes
        the default strict, it does not remove the way to accept a partial
        site on purpose."""
        with TemporaryDirectory() as td:
            p = self._run(Path(td), "--allow-partial")
            self.assertEqual(p.returncode, 0, p.stderr[-2000:])
            self.assertIn("bravo.spec.json", p.stderr)


if __name__ == "__main__":
    unittest.main()
