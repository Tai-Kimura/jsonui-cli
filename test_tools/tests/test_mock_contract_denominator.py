"""`validate` says how much of the contract it compared, on every run.

The gate reported findings and never the denominator, and its early return
on a clean report meant a run with nothing wrong printed nothing at all. So
two states looked identical from the outside: "every scenario was compared
to the contract and matched" and "the scenarios were never compared".

That is not hypothetical. A consumer's mock answered a conflict status on
an endpoint whose implementation cannot reach that branch — the contract
declares no such response there — so an E2E test was green on a path
production does not have. The code it had picked was a real one from a
neighbouring endpoint, which is what let it read past review. The check
had measured this and listed it under `mock generate --check`; the gate
people actually run printed four kinds of finding and nothing else, so the
note existed and was structurally unreachable.

The status is the mock's own choice: a branch contract that says `api.X:
"error"` deliberately leaves the concrete code to the mock, and forbidding
that would break the freedom it is designed to give. So the fix counts
rather than constrains — the uncompared number is the one that should be
walking towards zero, and it is on screen either way.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_TOOL))

from jsonui_test_cli.mock.generate import _check, generate  # noqa: E402

TEST_DOC = {
    "type": "screen",
    "source": {"layout": "test.json"},
    "metadata": {"name": "Fixture", "description": "Fixture screen test.",
                 "screen": "fixture"},
    "platform": "web",
    "cases": [{"name": "renders", "description": "Root visible.",
               "steps": [{"assert": "visible", "id": "fixture_root"}]}],
}

BODY = {"type": "object", "required": ["id"],
        "properties": {"id": {"type": "string"}}}
JSON_200 = {"content": {"application/json": {"schema": BODY}}}

SWAGGER = {
    "openapi": "3.0.3",
    "paths": {"/api/items": {"get": {
        "operationId": "listItems",
        "responses": {"200": JSON_200, "404": JSON_200},
    }}},
}


def _mock(scenarios: dict) -> dict:
    return {
        "source": {"operationId": "listItems", "method": "GET",
                   "path": "/api/items"},
        "activeScenario": "default",
        "scenarios": scenarios,
    }


OK = {"status": 200, "body": {"id": "1"}}
GONE = {"status": 404, "body": {"id": "1"}}
#: A status the contract does not declare — compared to nothing.
TEAPOT = {"status": 418, "body": {"id": "1"}}


class TheGateNamesWhatItCompared(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "smoke.test.json").write_text(
            json.dumps(TEST_DOC), encoding="utf-8")
        (self.root / "swagger.json").write_text(json.dumps(SWAGGER),
                                                encoding="utf-8")
        (self.root / "tests" / "mocks").mkdir()
        (self.root / "jui.config.json").write_text(json.dumps({
            "mock": {"swagger": ["swagger.json"], "mockDir": "tests/mocks"},
        }), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def write_mock(self, scenarios: dict, name: str = "items"):
        (self.root / "tests" / "mocks" / f"{name}.mock.json").write_text(
            json.dumps(_mock(scenarios)), encoding="utf-8")

    def validate(self):
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "validate", "tests"],
            cwd=self.root, capture_output=True, text=True,
            env={"PYTHONPATH": str(REPO_TOOL), "PATH": "/usr/bin:/bin"})
        return proc.returncode, proc.stdout + proc.stderr

    def test_a_clean_run_says_how_much_it_compared(self):
        # The early return was before any output, so this is the run that
        # printed nothing — and "nothing" is what a run that compared
        # nothing prints too.
        self.write_mock({"default": OK, "gone": GONE})
        rc, out = self.validate()
        self.assertEqual(rc, 0, out)
        # Four: the two written here plus the two the generated tree holds
        # for this route (`default` and `error_404`). Everything that can
        # serve is counted, which is the point of the number.
        self.assertIn("mock contract: 4 scenario(s) — 4 compared", out)

    def test_the_denominator_counts_scenarios_not_files(self):
        self.write_mock({"default": OK, "gone": GONE, "odd": TEAPOT})
        _rc, out = self.validate()
        # Two files, five scenarios, one of them uncompared. A file-level
        # denominator would say "2 compared" and read as complete — the gap
        # is inside a file that also holds scenarios which were compared.
        self.assertIn("mock contract: 5 scenario(s) — 4 compared, "
                      "1 not compared (status not declared)", out)

    def test_the_uncompared_scenario_is_named(self):
        # The reported defect: the count alone would say a gap exists
        # without saying where, and this path never listed them at all.
        self.write_mock({"default": OK, "odd": TEAPOT})
        _rc, out = self.validate()
        self.assertIn("odd: status 418 not declared", out)
        self.assertIn("not compared", out)

    def test_an_uncompared_scenario_does_not_fail_the_gate(self):
        # Counting, not constraining. A scenario may legitimately declare a
        # status the swagger does not, and a gate that fails on it is a gate
        # a project switches off — taking the real findings with it.
        self.write_mock({"default": OK, "odd": TEAPOT})
        rc, out = self.validate()
        self.assertEqual(rc, 0, out)
        self.assertIn("Result: PASSED", out)

    def test_a_scope_excluded_mock_is_named_as_such_not_as_an_orphan(self):
        """The two have opposite answers: delete it, or declare the path.

        `mock generate --check` has told them apart since the scope was
        introduced. This gate never mentioned the scope at all, so the same
        corpus produced two reports that disagreed about which files exist —
        and the only vocabulary this one had for an unmatched mock said "not
        in swagger", which for these files is false.
        """
        self.write_mock({"default": OK})
        # In the swagger — a shared one declares every realm — and outside
        # the slice this project consumes. That combination is the whole
        # point: "not in swagger" would be a false statement about it.
        shared = json.loads(json.dumps(SWAGGER))
        shared["paths"]["/api/other/thing"] = {"get": {
            "operationId": "other", "responses": {"200": JSON_200}}}
        (self.root / "swagger.json").write_text(json.dumps(shared),
                                                encoding="utf-8")
        (self.root / "tests" / "mocks" / "elsewhere.mock.json").write_text(
            json.dumps({
                "source": {"operationId": "other", "method": "GET",
                           "path": "/api/other/thing"},
                "scenarios": {"default": {"status": 200, "body": {"id": "1"}}}}),
            encoding="utf-8")
        cfg = json.loads((self.root / "jui.config.json").read_text())
        cfg["api"] = {"schemas": {"include_paths": ["/api/items*"]}}
        (self.root / "jui.config.json").write_text(json.dumps(cfg),
                                                   encoding="utf-8")
        rc, out = self.validate()
        self.assertEqual(rc, 0, out)
        self.assertIn("[SCOPE]", out)
        self.assertIn("outside this project's API paths", out)
        self.assertNotIn("[ORPHAN]", out)

    def test_a_route_no_swagger_declares_is_still_an_orphan(self):
        """The distinction the SCOPE line must not blur: with no scope
        declared there is nothing to be outside of, and the file really is
        for a route the contract does not have."""
        self.write_mock({"default": OK})
        (self.root / "tests" / "mocks" / "retired.mock.json").write_text(
            json.dumps({
                "source": {"operationId": "gone", "method": "GET",
                           "path": "/api/retired"},
                "scenarios": {"default": {"status": 200, "body": {}}}}),
            encoding="utf-8")
        rc, out = self.validate()
        self.assertEqual(rc, 1, out)
        self.assertIn("[ORPHAN]", out)
        self.assertNotIn("[SCOPE]", out)

    def test_the_line_is_printed_on_a_failing_run_too(self):
        # Permanent, not an attachment to red output: how much was compared
        # is the context for whatever was found.
        self.write_mock({"default": {"status": 200, "body": {"id": 1}}})
        rc, out = self.validate()
        self.assertEqual(rc, 1, out)
        self.assertIn("mock contract: 3 scenario(s) — 3 compared", out)
        self.assertIn("[BODY]", out)


class TheUncomparedStatusCarriesWhatTheSwaggerKnows(unittest.TestCase):
    """Two facts are cheap and each tells an omission from a decision.

    A mirrored endpoint declaring the status makes the gap look like an
    asymmetry someone forgot; no operation anywhere declaring it means the
    mock introduced a class of failure the contract does not have. Anything
    else — a status many unrelated endpoints declare — says nothing about
    this endpoint, and the clause is omitted rather than filled with the
    absence of information.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "mocks").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, paths: dict, mock_path: str, status: int):
        (self.root / "swagger.json").write_text(json.dumps(
            {"openapi": "3.0.3", "paths": paths}), encoding="utf-8")
        (self.root / "mocks" / "m.mock.json").write_text(json.dumps({
            "source": {"operationId": "act", "method": "POST",
                       "path": mock_path},
            "scenarios": {"failure": {"status": status, "body": {"id": "1"}}},
        }), encoding="utf-8")
        return _check([str(self.root / "swagger.json")], self.root / "mocks")

    def test_a_mirrored_endpoint_declaring_it_is_named(self):
        report = self._run({
            "/api/first/items/archive": {"post": {
                "operationId": "act", "responses": {"200": JSON_200}}},
            "/api/second/items/archive": {"post": {
                "operationId": "secondAct",
                "responses": {"200": JSON_200, "422": JSON_200}}},
        }, "/api/first/items/archive", 422)
        self.assertEqual(len(report.unmatched), 1)
        self.assertIn("(sibling POST /api/second/items/archive declares 422)",
                      report.unmatched[0])

    def test_a_status_no_operation_declares_is_named_as_such(self):
        report = self._run({
            "/api/first/items/archive": {"post": {
                "operationId": "act", "responses": {"200": JSON_200}}},
        }, "/api/first/items/archive", 500)
        self.assertIn("(no operation in this swagger declares 500)",
                      report.unmatched[0])

    def test_an_unrelated_endpoint_declaring_it_says_nothing(self):
        # The silent case, and the common one: a status that belongs
        # to many endpoints in a large swagger and to none of this one's
        # mirrors says nothing about this one.
        report = self._run({
            "/api/first/items/archive": {"post": {
                "operationId": "act", "responses": {"200": JSON_200}}},
            "/api/unrelated/things": {"post": {
                "operationId": "book",
                "responses": {"200": JSON_200, "409": JSON_200}}},
        }, "/api/first/items/archive", 409)
        self.assertEqual(report.unmatched[0].count("("), 0)

    def test_a_differing_last_segment_is_not_a_mirror(self):
        # "one segment differs" alone would pair an endpoint with its
        # neighbour in the same realm, which is a different endpoint, not
        # the same one seen from another realm.
        report = self._run({
            "/api/second/items/archive": {"post": {
                "operationId": "act", "responses": {"200": JSON_200}}},
            "/api/first/items/restore": {"post": {
                "operationId": "remove",
                "responses": {"200": JSON_200, "422": JSON_200}}},
        }, "/api/second/items/archive", 422)
        self.assertNotIn("sibling", report.unmatched[0])


if __name__ == "__main__":
    unittest.main()


class TheBucketsClose(unittest.TestCase):
    """Every scenario the run opened lands in exactly one named bucket.

    A file response (`bodyFile` + `contentType`, no JSON body) was counted
    as neither compared nor not-compared, so the line read as a full
    account of a corpus it was one short of. Both consumer projects hit it
    independently — a PDF receipt in one, five CSV exports in the other —
    which is what makes it structural rather than one project's shape: it
    follows from the payload type, not from the project.
    """

    def _doc_with_file_response(self, tmp):
        spec = {
            "openapi": "3.0.3",
            "paths": {
                "/api/items": {"get": {
                    "operationId": "listItems", "tags": ["I"],
                    "responses": {"200": {"content": {"application/json": {
                        "schema": {"type": "object",
                                   "properties": {"id": {"type": "string"}}}}}}}}},
                "/api/export": {"get": {
                    "operationId": "exportCsv", "tags": ["I"],
                    "responses": {"200": {"content": {"text/csv": {
                        "schema": {"type": "string", "format": "binary"}}}}}}},
            },
        }
        (tmp / "swagger.json").write_text(json.dumps(spec), encoding="utf-8")
        return str(tmp / "swagger.json")

    def test_a_file_response_is_counted_as_not_compared(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            swagger = self._doc_with_file_response(tmp)
            mocks = tmp / "mocks"
            generate([swagger], mocks)
            report = generate([swagger], mocks, check=True)

            # Split by reason, not merged: a declared-but-unschema'd
            # status is a debt someone can fix, a file response is
            # correct silence, and one number cannot be acted on.
            self.assertEqual(len(report.non_json), 1, report.non_json)
            self.assertIn("declared non-JSON response",
                          report.contract_summary)
            # The whole point: the parts add up to the total on screen.
            self.assertEqual(
                report.scenarios_seen,
                report.compared + len(report.unmatched)
                + len(report.no_schema) + len(report.non_json)
                + len(report.malformed))
            self.assertIn(f"{report.scenarios_seen} scenario(s)",
                          report.contract_summary)

    def test_the_total_matches_the_scenarios_on_disk(self):
        """Counted from the files, not from the report's own arithmetic —
        a report that agrees with itself proves nothing about the corpus."""
        with TemporaryDirectory() as d:
            tmp = Path(d)
            swagger = self._doc_with_file_response(tmp)
            mocks = tmp / "mocks"
            generate([swagger], mocks)
            on_disk = sum(
                len(json.loads(p.read_text(encoding="utf-8")).get("scenarios", {}))
                for p in mocks.rglob("*.mock.json"))
            report = generate([swagger], mocks, check=True)
            self.assertEqual(report.scenarios_seen, on_disk)

    def test_a_declared_status_with_no_schema_is_the_other_bucket(self):
        """The debt half. A consumer measured 94 of 105 in one project and
        22 of 22 in another as this — merged with the file responses, the
        number named no action; split, it is a swagger to-do list."""
        with TemporaryDirectory() as d:
            tmp = Path(d)
            spec = {
                "openapi": "3.0.3",
                "paths": {"/api/items": {"get": {
                    "operationId": "listItems", "tags": ["I"],
                    "responses": {
                        "200": {"content": {"application/json": {
                            "schema": {"type": "object",
                                       "properties": {"id": {"type": "string"}}}}}},
                        # declared, but the contract stops before the payload
                        "403": {"description": "forbidden"}}}}},
            }
            (tmp / "swagger.json").write_text(json.dumps(spec), encoding="utf-8")
            mocks = tmp / "mocks"
            generate([str(tmp / "swagger.json")], mocks)
            report = generate([str(tmp / "swagger.json")], mocks, check=True)

            self.assertEqual(len(report.no_schema), 1, report.no_schema)
            self.assertEqual(report.non_json, [])
            self.assertIn("no response body declared", report.contract_summary)
            self.assertNotIn("non-JSON", report.contract_summary)
