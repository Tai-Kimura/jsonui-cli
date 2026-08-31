"""Mocks are matched to operations on the normalized route.

A swagger edit that renamed path variables — `/api/items/{id}` becoming
`/api/items/{item_id}`, changing no HTTP contract at all — detached 87
hand-written mocks in a reporting project. A detached mock is not reported as
wrong: it is reported as ORPHAN, and its body silently stops being compared to
anything, while the summary line keeps saying PASSED.

The rule is not new here. `builtin:openapi-diff` has paired its two sides on
positionally-normalized paths from the start; this file's parity test is what
keeps the second implementation from becoming a second decision.

The counting tests below are the other half of the same report: `Files:` moved
in *both* directions across environments for one edit, and took two values for
one unchanged input, because generation ran after the count.
"""

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import generate, normalize_path_key, route_key


def _spec(var="id", trailing=""):
    return {
        "openapi": "3.0.3",
        "paths": {
            f"/api/items/{{{var}}}{trailing}": {"get": {
                "operationId": "getItem", "tags": ["Items"],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"type": "object", "required": ["name"],
                               "properties": {"name": {"type": "string"}}}}}}},
            }},
        },
    }


def _write_spec(tmp_path, name, **kwargs):
    path = tmp_path / name
    path.write_text(json.dumps(_spec(**kwargs)), encoding="utf-8")
    return str(path)


def _hand_written(mocks: Path, path: str, body, op="getItem"):
    target = mocks / "items" / f"{op}.mock.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "source": {"method": "GET", "path": path, "operationId": op},
        "scenarios": {"default": {"status": 200, "body": body}},
    }), encoding="utf-8")
    return target


class TestNormalization:
    def test_a_variable_rename_does_not_detach_a_mock(self, tmp_path):
        renamed = _write_spec(tmp_path, "after.json", var="item_id")
        mocks = tmp_path / "mocks"
        _hand_written(mocks, "/api/items/{id}", {"name": "a"})

        report = generate([renamed], mocks, check=True)
        # `has_drift`, not just `orphaned`: without normalization the mock is
        # paired with the operation by operationId and reported as DRIFT
        # instead, so an assertion about ORPHAN alone passes for the wrong
        # reason and stays green with the fix removed.
        assert not report.has_drift, [report.orphaned, report.drifted, report.missing]

    def test_the_body_is_still_checked_after_a_rename(self, tmp_path):
        # The load-bearing one. Detaching a mock does not report its body as
        # wrong -- it stops reporting on the body at all, which is why the
        # symptom was a check that shrank while staying green.
        renamed = _write_spec(tmp_path, "after.json", var="item_id")
        mocks = tmp_path / "mocks"
        _hand_written(mocks, "/api/items/{id}", {"name": 7})  # wrong type

        report = generate([renamed], mocks, check=True)
        assert report.errors, "a violating body must still be reported"
        assert report.has_drift

    def test_the_mock_still_covers_its_normalized_route(self, tmp_path):
        # The subject: a detached mock stops "covering" its route, so
        # normalization must keep the differently-spelt path variable bound
        # to the same route. The observable changed with the overlay model
        # (1.7.22): coverage reads as `overlaid` membership — the generated
        # counterpart is written either way, so `created` no longer
        # discriminates. If normalization broke, `overlaid` comes back
        # empty.
        renamed = _write_spec(tmp_path, "after.json", var="item_id")
        mocks = tmp_path / "mocks"
        _hand_written(mocks, "/api/items/{id}", {"name": "a"})

        built = generate([renamed], mocks)
        assert built.overlaid == ["items/getItem.mock.json"]

    def test_a_trailing_slash_is_absorbed_too(self, tmp_path):
        # Half a normalization is a new bug: whichever side is not absorbed
        # becomes the next silent detach.
        spec = _write_spec(tmp_path, "after.json", var="item_id", trailing="/")
        mocks = tmp_path / "mocks"
        _hand_written(mocks, "/api/items/{id}", {"name": "a"})

        assert not generate([spec], mocks, check=True).has_drift

    def test_a_genuinely_different_route_is_still_an_orphan(self, tmp_path):
        # Normalizing must not turn the check into a rubber stamp. A distinct
        # operationId too: a mock that shares one with a live operation is
        # paired with it and reported as DRIFT, which is the more actionable
        # message and a different code path.
        spec = _write_spec(tmp_path, "after.json", var="item_id")
        mocks = tmp_path / "mocks"
        _hand_written(mocks, "/api/gadgets/{id}", {"name": "a"}, op="getGadget")

        report = generate([spec], mocks, check=True)
        assert report.orphaned, "a different path must not be absorbed"

    def test_the_message_shows_the_spelling_that_was_written(self, tmp_path):
        # A report answering `/api/items/{}` sends the reader looking for a
        # path that appears in neither file.
        spec = _write_spec(tmp_path, "after.json", var="item_id")
        mocks = tmp_path / "mocks"
        _hand_written(mocks, "/api/gadgets/{slug}", {"name": "a"}, op="getGadget")

        orphan = generate([spec], mocks, check=True).orphaned[0]
        assert "/api/gadgets/{slug}" in orphan
        assert "{}" not in orphan

    def test_route_key_pairs_the_two_spellings(self):
        assert route_key("get", "/api/items/{id}") == \
            route_key("GET", "/api/items/{item_id}/")


class TestParityWithTheDocSide:
    """One decision, two implementations — the tools cannot import each other.

    Loaded by file path rather than by package import: `jsonui_doc_cli` is
    installed as an editable pointing at the distributed copy, and a test that
    skips when an import fails is exactly how the sibling-dependent test in
    `jui_tools` stayed skipped through the documented run. This finds the
    checkout's own file or fails.
    """

    @staticmethod
    def _doc_side():
        source = (Path(__file__).resolve().parents[2] / "document_tools" /
                  "jsonui_doc_cli" / "check" / "openapi_normalize.py")
        assert source.is_file(), f"sibling source not found at {source}"
        if "_doc_openapi_normalize" in sys.modules:
            return sys.modules["_doc_openapi_normalize"]
        spec = importlib.util.spec_from_file_location("_doc_openapi_normalize", source)
        module = importlib.util.module_from_spec(spec)
        # Registered before executing: `@dataclass` resolves annotations
        # through `sys.modules[cls.__module__]`, which is None for a module
        # that is only being executed.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    @pytest.mark.parametrize("path", [
        "/api/items/{id}",
        "/api/items/{item_id}",
        "/api/items/{id}/",
        "/api/{realm}/items/{item_id}/children/{child_id}",
        "/",
        "",
        "/api/items",
        "/api/items/",
        "/api/{a}{b}/x",          # not a whole-segment variable
    ])
    def test_normalize_path_key_parity(self, path):
        assert normalize_path_key(path) == self._doc_side().normalize_path_key(path)


class TestSummaryCounts:
    """`Files:` and the orphan count, through the CLI entry point."""

    def _project(self, tmp_path, var="id"):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "spec.json").write_text(json.dumps(_spec(var=var)), encoding="utf-8")
        proj = tmp_path / "proj"
        (proj / "tests").mkdir(parents=True)
        (proj / "tests" / "mocks").mkdir()
        (proj / "tests" / "sample.test.json").write_text(json.dumps({
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "sample_test", "description": "d"},
            "cases": [{"name": "c", "description": "d",
                       "steps": [{"assert": "visible", "id": "root"}]}],
        }), encoding="utf-8")
        (proj / "jui.config.json").write_text(json.dumps({
            "mock": {"swagger": "../docs/spec.json", "mockDir": "tests/mocks"},
        }), encoding="utf-8")
        return proj

    def _validate(self, proj, monkeypatch, **flags):
        from jsonui_test_cli.cli import cmd_validate

        monkeypatch.chdir(proj)
        args = type("Args", (), {
            "files": ["tests"], "verbose": False, "quiet": True,
            "config": None, "no_install": True, "no_mock_check": False,
            **flags,
        })()
        out = io.StringIO()
        with redirect_stdout(out):
            code = cmd_validate(args)
        return code, out.getvalue()

    @staticmethod
    def _files(output):
        line = next(l for l in output.splitlines() if l.startswith("Files:"))
        return int(line.split(",")[0].split(":")[1])

    def test_files_is_the_same_for_the_same_input(self, tmp_path, monkeypatch):
        # The reported symptom: `generated/` deleted, then two runs of an
        # unchanged project printed 267 and then 306.
        proj = self._project(tmp_path)
        first = self._files(self._validate(proj, monkeypatch)[1])
        second = self._files(self._validate(proj, monkeypatch)[1])
        assert first == second

    def test_files_survives_deleting_the_generated_tree(self, tmp_path, monkeypatch):
        import shutil

        proj = self._project(tmp_path)
        # Warm first: on a cold project the old order also counts a tree that
        # is not there yet, so both runs agree for the wrong reason and the
        # test stays green with the fix removed.
        self._validate(proj, monkeypatch)
        baseline = self._files(self._validate(proj, monkeypatch)[1])
        shutil.rmtree(proj / "tests" / "mocks" / "generated")
        assert self._files(self._validate(proj, monkeypatch)[1]) == baseline

    def test_files_survives_a_variable_rename(self, tmp_path, monkeypatch):
        # The third state in the report's table: the edit that started it.
        proj = self._project(tmp_path)
        baseline = self._files(self._validate(proj, monkeypatch)[1])
        (tmp_path / "docs" / "spec.json").write_text(
            json.dumps(_spec(var="item_id")), encoding="utf-8")
        assert self._files(self._validate(proj, monkeypatch)[1]) == baseline

    def test_the_orphan_count_is_in_the_summary(self, tmp_path, monkeypatch):
        proj = self._project(tmp_path)
        _hand_written(proj / "tests" / "mocks", "/api/gone/{id}", {"name": "a"},
                      op="getGone")
        code, output = self._validate(proj, monkeypatch)
        assert "Orphan mocks: 1" in output
        assert code == 1

    def test_the_headline_follows_the_mock_gate(self, tmp_path, monkeypatch):
        # It always counted toward the exit code; printing PASSED beside a
        # failing gate is what let a reader believe the run was clean.
        proj = self._project(tmp_path)
        _hand_written(proj / "tests" / "mocks", "/api/gone/{id}", {"name": "a"},
                      op="getGone")
        code, output = self._validate(proj, monkeypatch)
        assert code == 1
        assert "Result: FAILED" in output
        assert "Result: PASSED" not in output

    def test_a_clean_project_reports_zero_orphans(self, tmp_path, monkeypatch):
        proj = self._project(tmp_path)
        code, output = self._validate(proj, monkeypatch)
        assert "Orphan mocks: 0" in output
        assert code == 0

    def test_the_count_is_omitted_when_the_check_did_not_run(self, tmp_path, monkeypatch):
        # "Orphan mocks: 0" from a run that never looked reads exactly like a
        # clean result.
        proj = self._project(tmp_path)
        _, output = self._validate(proj, monkeypatch, no_mock_check=True)
        assert "Orphan mocks" not in output
