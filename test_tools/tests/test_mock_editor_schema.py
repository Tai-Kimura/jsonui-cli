"""Tests for the editor schema `mock generate` places next to the mocks.

Every generated mock has carried `"$schema": "./.mock.schema.json"` since the
beginning, and nothing ever wrote that file: the reference resolved nowhere, in
any project, so the schema was never doing the job it was named for. The
canonical copy lives in jsonui-test-runner and the CLI ships one in
`static/`; these tests are about the third step — the copy actually landing
beside the file that names it.

The load-bearing test is `test_the_schema_reference_resolves`: it follows the
reference the way an editor does instead of asserting the file exists at a path
the test itself spells, which is what makes it able to fail if either half of
the pair moves.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import (
    EDITOR_SCHEMA_FILENAME,
    EDITOR_SCHEMA_REF,
    GENERATED_DIR,
    editor_schema_text,
    generate,
    update_default,
)

SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/v1/widgets": {
            "get": {
                "operationId": "listWidgets",
                "tags": ["Widgets"],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"type": "object",
                               "properties": {"total": {"type": "integer"}}}}}}},
            }
        },
        "/v1/gadgets": {
            "get": {
                "operationId": "listGadgets",
                "tags": ["Gadgets"],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"type": "object",
                               "properties": {"total": {"type": "integer"}}}}}}},
            }
        },
    },
}


@pytest.fixture
def spec(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(SPEC), encoding="utf-8")
    return str(path)


def _resolve(mock_file: Path) -> Path:
    """Resolve a mock's `$schema` the way an editor would: relative to itself."""
    reference = json.loads(mock_file.read_text(encoding="utf-8"))["$schema"]
    return (mock_file.parent / reference).resolve()


def test_the_schema_reference_resolves(spec, tmp_path):
    out = tmp_path / "mocks"
    generate([spec], out)

    mocks = sorted(out.rglob("*.mock.json"))
    assert mocks, "fixture assumption: the spec scaffolds mocks"
    for mock in mocks:
        target = _resolve(mock)
        assert target.is_file(), f"{mock.name} points at {target}, which is absent"
        assert json.loads(target.read_text(encoding="utf-8"))["$id"].endswith(
            "mock.schema.json")


def test_the_placed_copy_is_the_shipped_one(spec, tmp_path):
    out = tmp_path / "mocks"
    generate([spec], out)
    placed = _resolve(next(out.rglob("*.mock.json")))
    assert placed.read_text(encoding="utf-8") == editor_schema_text()


def test_every_directory_holding_mocks_gets_one(spec, tmp_path):
    # Two tags means two directories, each one deeper than mockDir — which is
    # why the reference is a sibling and not a computed `../..` path.
    out = tmp_path / "mocks"
    report = generate([spec], out)
    holders = {p.parent for p in out.rglob("*.mock.json")}
    assert len(holders) == 2
    for directory in holders:
        assert (directory / EDITOR_SCHEMA_FILENAME).is_file()
    assert len(report.schemas) == 2


def _hand_written(out: Path, name="widgets", op="listWidgets",
                  route="/v1/widgets", schema_ref=True) -> Path:
    """A mock authored by hand, in a directory `generate` does not own."""
    target = out / "hand" / f"{name}.mock.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "source": {"method": "GET", "path": route, "operationId": op},
        "scenarios": {"default": {"status": 200, "body": {"total": 1}}},
    }
    if schema_ref:
        body = {"$schema": f"./{EDITOR_SCHEMA_FILENAME}", **body}
    target.write_text(json.dumps(body), encoding="utf-8")
    return target


def test_a_hand_written_mock_directory_gets_one_too(spec, tmp_path):
    # Hand-written mocks live outside generated/ and are never rewritten, so
    # the only thing that can put a schema beside them is this placement.
    out = tmp_path / "mocks"
    hand = _hand_written(out)

    generate([spec], out)
    assert _resolve(hand).is_file()


def test_update_default_places_it(spec, tmp_path):
    # `--update-default` is the half a project runs after hand-writing a mock,
    # in a directory `generate` has no reason to visit again.
    out = tmp_path / "mocks"
    hand = _hand_written(out, name="gadgets", op="listGadgets",
                         route="/v1/gadgets", schema_ref=False)

    report = update_default([spec], out)
    assert (hand.parent / EDITOR_SCHEMA_FILENAME).is_file()
    assert report.schemas


def test_a_dry_run_writes_nothing(spec, tmp_path):
    out = tmp_path / "mocks"
    generate([spec], out)
    for path in out.rglob(EDITOR_SCHEMA_FILENAME):
        path.unlink()
    update_default([spec], out, dry_run=True)
    assert not list(out.rglob(EDITOR_SCHEMA_FILENAME))


def test_an_unchanged_copy_is_left_alone(spec, tmp_path):
    # Only meaningful outside generated/: that tree is wiped and rewritten on
    # every run by design, so its copies are rewritten with the mocks. A
    # hand-written directory is authored space — a re-run must not touch it.
    out = tmp_path / "mocks"
    hand = _hand_written(out)
    generate([spec], out)
    placed = hand.parent / EDITOR_SCHEMA_FILENAME
    stamp = placed.stat().st_mtime_ns

    second = generate([spec], out)
    assert str(placed.relative_to(out)) not in second.schemas
    assert placed.stat().st_mtime_ns == stamp


def test_a_stale_copy_is_refreshed(spec, tmp_path):
    out = tmp_path / "mocks"
    hand = _hand_written(out)
    generate([spec], out)
    placed = hand.parent / EDITOR_SCHEMA_FILENAME
    placed.write_text("{}", encoding="utf-8")

    report = generate([spec], out)
    assert placed.read_text(encoding="utf-8") == editor_schema_text()
    assert str(placed.relative_to(out)) in report.schemas


def test_a_directory_that_lost_its_mocks_is_still_pruned(spec, tmp_path):
    # The placed copy is tool output. Left behind, it would keep a tag
    # directory that no longer has any mocks alive forever.
    out = tmp_path / "mocks"
    generate([spec], out)
    gadgets = out / GENERATED_DIR / "gadgets"
    assert gadgets.is_dir()

    shrunk = dict(SPEC, paths={"/v1/widgets": SPEC["paths"]["/v1/widgets"]})
    smaller = tmp_path / "smaller.json"
    smaller.write_text(json.dumps(shrunk), encoding="utf-8")
    generate([str(smaller)], out)

    assert not gadgets.exists()


def test_a_broken_install_warns_and_still_generates(spec, tmp_path, monkeypatch):
    # The schema is an authoring aid; the mocks are the work. A packaging
    # fault must degrade, not fail the generation.
    from jsonui_test_cli.mock import generate as gen

    def boom():
        raise FileNotFoundError("static/mock.schema.json")

    monkeypatch.setattr(gen, "editor_schema_text", boom)
    report = gen.generate([spec], tmp_path / "mocks")

    assert report.created, "mocks must still be written"
    assert report.schemas == []
    assert any("editor schema not placed" in w for w in report.warnings)


# --- the spelling of the reference -------------------------------------------
# Two spellings were in the wild (`./` and `../`). While no copy existed
# anywhere both resolved to nothing, so the split cost nothing and stayed
# invisible; placing the copies is what turns `../` into the only half that
# still silently fails.

def _validate(tmp_path, ref):
    from jsonui_test_cli.validation.validator import TestValidator

    target = tmp_path / "x.mock.json"
    body = {"source": {"method": "GET", "path": "/v1/widgets"},
            "scenarios": {"default": {"status": 200, "body": {}}}}
    if ref is not None:
        body = {"$schema": ref, **body}
    target.write_text(json.dumps(body), encoding="utf-8")
    return TestValidator().validate_file(target)


def test_a_parent_directory_reference_fails_validation(tmp_path):
    result = _validate(tmp_path, f"../{EDITOR_SCHEMA_FILENAME}")
    assert not result.is_valid
    message = " ".join(e.message for e in result.errors)
    assert EDITOR_SCHEMA_REF in message, "the error must name the canonical value"


def test_the_sibling_reference_passes(tmp_path):
    assert _validate(tmp_path, EDITOR_SCHEMA_REF).is_valid


def test_an_absent_reference_passes(tmp_path):
    # Generated mocks carry one; a hand-written mock may leave it out.
    assert _validate(tmp_path, None).is_valid


def test_the_check_does_not_require_the_file_to_exist(tmp_path):
    # A project may gitignore the placed copies. If existence were the test,
    # a fresh CI checkout would fail on every mock it has.
    result = _validate(tmp_path, EDITOR_SCHEMA_REF)
    assert not (tmp_path / EDITOR_SCHEMA_FILENAME).exists()
    assert result.is_valid


def test_what_generate_writes_is_what_validate_accepts(spec, tmp_path):
    from jsonui_test_cli.validation.validator import TestValidator

    out = tmp_path / "mocks"
    generate([spec], out)
    for mock in out.rglob("*.mock.json"):
        assert TestValidator().validate_file(mock).is_valid, mock
