"""One finding, one line, one label that names it.

Two reports from two consumers, one cause:

* `[NOTE]` was printed for two unrelated findings — a scenario whose status
  the contract does not declare, and a body that merely spells out fewer
  optional fields than the schema has. The only thing separating them was
  whether the line happened to end in " — not compared". A consumer with 93
  of them could not split its own count between the two and nearly filed
  them all as the wrong kind.

* A generated scenario for an undeclared status was printed **twice**: once
  as `[EXTRA]` (which gates) and once as `[NOTE] … — not compared` (which
  says the opposite about the same line). `unmatched_generated` is a subset
  of `unmatched`, and it was added to the first without being taken out of
  the second.

Both are the same defect in different clothes: the reader is asked to make a
distinction the output does not carry. The counts stay whole — `unmatched`
is still the denominator — and only the reporting splits.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.cli import _print_uncompared
from jsonui_test_cli.mock.generate import generate

SPEC = {"openapi": "3.0.3", "paths": {"/api/items": {"get": {
    "operationId": "listItems",
    "responses": {"200": {"content": {"application/json": {"schema": {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "string"},
                       "note": {"type": "string"}},
    }}}}}}}}}


@pytest.fixture
def swagger(tmp_path):
    path = tmp_path / "api.json"
    path.write_text(json.dumps(SPEC), encoding="utf-8")
    return str(path)


def _generated_with(mock_dir, swagger, extra_scenarios):
    generate([swagger], mock_dir)
    target = next(mock_dir.rglob("generated/**/*.mock.json"))
    doc = json.loads(target.read_text(encoding="utf-8"))
    doc["scenarios"].update(extra_scenarios)
    target.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return target


def test_an_undeclared_generated_status_is_reported_once(swagger, tmp_path,
                                                         capsys):
    mock_dir = tmp_path / "mocks"
    _generated_with(mock_dir, swagger,
                    {"error_422": {"status": 422, "body": {"id": "1"}}})

    report = generate([swagger], mock_dir, check=True)
    _print_uncompared(report)
    printed = capsys.readouterr().out

    # Still counted: it is one of the scenarios the run opened.
    assert len(report.unmatched) == 1
    assert len(report.unmatched_generated) == 1
    # But the gating printer owns it, so the not-compared channel is silent.
    assert report.unmatched_notes == []
    assert "422" not in printed


def test_a_hand_written_undeclared_status_is_still_reported_here(swagger,
                                                                 tmp_path,
                                                                 capsys):
    """The control. Emptying `unmatched_notes` unconditionally would pass the
    test above and silence the finding this channel exists for."""
    mock_dir = tmp_path / "mocks"
    hand = mock_dir / "items.mock.json"
    hand.parent.mkdir(parents=True, exist_ok=True)
    hand.write_text(json.dumps({
        "source": {"method": "GET", "path": "/api/items",
                   "operationId": "listItems"},
        "scenarios": {"default": {"status": 200, "body": {"id": "1"}},
                      "teapot": {"status": 418, "body": {}}},
    }), encoding="utf-8")

    report = generate([swagger], mock_dir, check=True)
    _print_uncompared(report)
    printed = capsys.readouterr().out

    # 418 is form B here — no operation in this swagger declares it — so it
    # is a warning, and the label says so.
    assert len(report.unmatched_notes) == 1
    assert "[WARN]" in printed and "418" in printed
    assert "[NOTE]" not in printed
    assert not report.has_drift


def test_the_two_kinds_of_note_no_longer_share_a_label(swagger, tmp_path,
                                                       capsys):
    """A body omitting only optional fields, and a scenario with an
    undeclared status, in one run. They answer different questions and are
    acted on differently, so a reader has to be able to separate them
    without parsing the end of the line."""
    from jsonui_test_cli.cli import cmd_mock_generate

    mock_dir = tmp_path / "mocks"
    hand = mock_dir / "items.mock.json"
    hand.parent.mkdir(parents=True, exist_ok=True)
    hand.write_text(json.dumps({
        "source": {"method": "GET", "path": "/api/items",
                   "operationId": "listItems"},
        "scenarios": {
            "default": {"status": 200, "body": {"id": "1"}},  # omits `note`
            "teapot": {"status": 418, "body": {}},
        },
    }), encoding="utf-8")

    class Args:
        swagger = None
        out = str(mock_dir)
        check = True
        strict = False
        config = None
        update_default = False

    Args.swagger = [swagger]
    cmd_mock_generate(Args())
    printed = capsys.readouterr().out

    optional = [ln for ln in printed.splitlines() if "[OPTIONAL]" in ln]
    warned = [ln for ln in printed.splitlines() if "[WARN]" in ln]
    assert len(optional) == 1 and len(warned) == 1
    assert "418" in warned[0]
    assert "[NOTE]" not in printed
