"""A scenario's `bodyFile` is its response body (ticket 2026-10-25-jsonui-test-mock-bodyfile-is-never-read).

Read relative to the mock file that declares the scenario, by `mock serve` (the bytes) and by the branch-test
runtimes (the text, embedded); validate names one that would not be sent. The runtimes are RUN in
test_branch_scenario_body_file.py (web, iOS: the compilers) and _android.py (the Android leg).
"""
from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli.branch_tests import BranchTestGenerationError, generate_branch_tests
from jsonui_test_cli.mock.server import MockServer, MockStore, RunManager
from jsonui_test_cli.validation.mock import MockValidator
from jsonui_test_cli.validation.models import ValidationResult
from tests.test_branch_tests_generator import BASIC, _project

#: A CSV export as the reporting lane's API sends it: UTF-8 with a BOM, CRLF rows.
CSV = "﻿id,name\r\n1,山崎\r\n2,白州\r\n".encode("utf-8")


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _csv_mock(directory: Path, scenario: dict, name="get_export.mock.json", path="/export") -> Path:
    return _write(directory / name, {
        "source": {"method": "GET", "path": path},
        "activeScenario": "csv",
        "scenarios": {"csv": scenario, "empty": {"status": 200, "body": []}},
    })


# ------------------------------------------------------------------ validate

def _problems(mock_file: Path) -> list[str]:
    result = ValidationResult(file_path=mock_file)
    MockValidator().validate(json.loads(mock_file.read_text(encoding="utf-8")), str(mock_file), result)
    return [m.message for m in result.errors if ".bodyFile" in (m.path or "")]


def test_validate_takes_a_bodyfile_that_is_there(tmp_path):
    _write(tmp_path / "files/export.csv", CSV)
    assert _problems(_csv_mock(tmp_path, {"status": 200, "contentType": "text/csv",
                                          "bodyFile": "files/export.csv"})) == []


@pytest.mark.parametrize("scenario,words", [
    ({"status": 200, "contentType": "text/csv", "bodyFile": "files/nowhere.csv"}, "is not a file"),
    ({"status": 200, "contentType": "text/csv", "bodyFile": "/abs/export.csv"}, "absolute path"),
    ({"status": 200, "contentType": "text/csv", "bodyFile": ""}, "must be a path"),
    ({"status": 200, "contentType": "text/csv", "bodyFile": 3}, "must be a path"),
    ({"status": 200, "body": "a,b", "bodyFile": "files/export.csv"}, "are both set"),
], ids=["missing", "absolute", "empty", "not-a-string", "beside-a-body"])
def test_validate_names_a_bodyfile_that_is_not_sent(tmp_path, scenario, words):
    _write(tmp_path / "files/export.csv", CSV)
    problems = _problems(_csv_mock(tmp_path, scenario))
    assert len(problems) == 1 and words in problems[0], problems


def test_a_null_bodyfile_is_no_declaration(tmp_path):
    # What `mock generate` writes for a file response: not an error.
    assert _problems(_csv_mock(tmp_path, {"status": 200, "contentType": "text/csv", "bodyFile": None})) == []


# ---------------------------------------------------------------- mock serve

def _serve(mock_dir: Path) -> MockServer:
    srv = MockServer(MockStore.load(mock_dir), RunManager({}, Path(mock_dir)), port=0)
    srv.bind()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _get(srv: MockServer, path: str):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.port}{path}", timeout=5) as res:
            return res.status, res.headers.get("Content-Type"), res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()


def test_mock_serve_sends_the_files_bytes(tmp_path):
    _write(tmp_path / "files/export.csv", CSV)
    _csv_mock(tmp_path, {"status": 200, "contentType": "text/csv; charset=utf-8", "bodyFile": "files/export.csv"})
    srv = _serve(tmp_path)
    try:
        status, ctype, body = _get(srv, "/export")
    finally:
        srv.shutdown()
    assert (status, ctype) == (200, "text/csv; charset=utf-8")
    assert body == CSV  # the BOM and the CRLFs included


def test_mock_serve_reads_the_file_per_request(tmp_path):
    csv = _write(tmp_path / "files/export.csv", CSV)
    _csv_mock(tmp_path, {"status": 200, "contentType": "text/csv", "bodyFile": "files/export.csv"})
    srv = _serve(tmp_path)
    try:
        _get(srv, "/export")
        csv.write_bytes(b"id\r\n")
        assert _get(srv, "/export")[2] == b"id\r\n"
    finally:
        srv.shutdown()


def test_a_bodyfile_is_relative_to_the_file_that_declares_the_scenario(tmp_path):
    # Two files for one route: each scenario's bodyFile is beside its own
    # file, and the route's last file (the hand-written overlay) is not the
    # one that declares the generated scenario.
    _write(tmp_path / "generated/files/export.csv", CSV)
    _write(tmp_path / "generated/get_export.mock.json", {
        "source": {"method": "GET", "path": "/export", "operationId": "export"},
        "scenarios": {"default": {"status": 200, "contentType": "text/csv", "bodyFile": "files/export.csv"}}})
    _write(tmp_path / "admin/files/short.csv", b"id\r\n")
    _write(tmp_path / "admin/get_export.mock.json", {
        "source": {"method": "GET", "path": "/export"}, "activeScenario": "default",
        "scenarios": {"short": {"status": 200, "contentType": "text/csv", "bodyFile": "files/short.csv"}}})
    # A second overlay, sorting last, so the route's last file declares
    # neither scenario above.
    _write(tmp_path / "zz/get_export.mock.json", {
        "source": {"method": "GET", "path": "/export"},
        "scenarios": {"other": {"status": 204, "body": None}}})
    srv = _serve(tmp_path)
    try:
        assert _get(srv, "/export")[2] == CSV
        srv.store.activate("export", "short")
        assert _get(srv, "/export")[2] == b"id\r\n"
    finally:
        srv.shutdown()


def test_an_unreadable_bodyfile_is_a_500_that_names_it(tmp_path):
    _csv_mock(tmp_path, {"status": 200, "contentType": "text/csv", "bodyFile": "files/nowhere.csv"})
    srv = _serve(tmp_path)
    try:
        status, _, body = _get(srv, "/export")
    finally:
        srv.shutdown()
    assert status == 500 and json.loads(body)["bodyFile"] == "files/nowhere.csv"


# -------------------------------------------------------------- branch tests

def _branch_project(tmp_path: Path, file_bytes: bytes = CSV) -> Path:
    root = _project(tmp_path, BASIC, scenarios={
        "success": {"status": 200, "body": {"order": {"id": "o1"}}},
        "conflict": {"status": 409, "contentType": "text/csv", "bodyFile": "files/conflict.csv"},
    })
    _write(root / "tests/mocks/orders/files/conflict.csv", file_bytes)
    return root


def test_kotlin_and_swift_embed_the_files_text(tmp_path):
    root = _branch_project(tmp_path)
    kotlin = generate_branch_tests("checkout", root, platform="android", package="com.example.x",
                                   out_dir="app/src/test/java", harness_dir="app/src/test/java")
    swift = generate_branch_tests("checkout", root, platform="ios", module="checkout_app",
                                  out_dir="Tests/Generated", harness_dir="Tests/Generated")
    text = CSV.decode("utf-8")
    assert f'Triple(409, {bt._kt_str(text)}, "text/csv")' in kotlin.test_file.read_text(encoding="utf-8")
    assert f'(409, {bt._swift_str(text)}, "text/csv")' in swift.test_file.read_text(encoding="utf-8")


def test_a_branch_tests_bodyfile_is_relative_to_the_file_that_declares_it(tmp_path):
    # The scenario is declared by the first file; an overlay that sorts after
    # it (the route's last file) adds another scenario and no files.
    root = _branch_project(tmp_path)
    _write(root / "tests/mocks/zz/post_api-user-orders.mock.json", {
        "source": {"method": "POST", "path": "/api/user/orders"},
        "scenarios": {"drained": {"status": 204, "body": None}}})
    kotlin = generate_branch_tests("checkout", root, platform="android", package="com.example.x",
                                   out_dir="app/src/test/java", harness_dir="app/src/test/java")
    assert bt._kt_str(CSV.decode("utf-8")) in kotlin.test_file.read_text(encoding="utf-8")


def test_an_overlays_bodyfile_is_relative_to_the_overlay_not_the_last_file(tmp_path):
    # generated/ declares the route; the first hand-written overlay adds the
    # file response beside itself; a second overlay, sorting last, adds a
    # scenario and no files.
    root = _project(tmp_path, BASIC)
    _write(root / "tests/mocks/generated/post_api-user-orders.mock.json", {
        "source": {"method": "POST", "path": "/api/user/orders", "operationId": "createOrder"},
        "scenarios": {"success": {"status": 200, "body": {"order": {"id": "o1"}}}}})
    _write(root / "tests/mocks/orders/post_api-user-orders.mock.json", {
        "source": {"method": "POST", "path": "/api/user/orders"},
        "scenarios": {"conflict": {"status": 409, "contentType": "text/csv", "bodyFile": "files/conflict.csv"}}})
    _write(root / "tests/mocks/orders/files/conflict.csv", CSV)
    _write(root / "tests/mocks/zz/post_api-user-orders.mock.json", {
        "source": {"method": "POST", "path": "/api/user/orders"},
        "scenarios": {"drained": {"status": 204, "body": None}}})
    kotlin = generate_branch_tests("checkout", root, platform="android", package="com.example.x",
                                   out_dir="app/src/test/java", harness_dir="app/src/test/java")
    assert bt._kt_str(CSV.decode("utf-8")) in kotlin.test_file.read_text(encoding="utf-8")


def test_web_embeds_the_files_text_as_the_body(tmp_path):
    report = generate_branch_tests("checkout", _branch_project(tmp_path))
    test = report.test_file.read_text(encoding="utf-8")
    assert json.dumps(CSV.decode("utf-8"), ensure_ascii=False) in test
    assert "conflict.csv" not in test  # the path is not embedded, so --check does not move per machine


def test_a_file_that_is_not_utf8_is_refused_by_name(tmp_path):
    root = _branch_project(tmp_path, file_bytes=b"%PDF-1.7\n\xff\xfe\x00binary")
    with pytest.raises(BranchTestGenerationError, match=r"conflict.*not UTF-8 text"):
        generate_branch_tests("checkout", root)
