"""selectOption's three selectors, and the one step shape that fooled a driver.

`value`, `label` and `index` are three ways to name ONE option. The schema
(jsonui-test-runner 169ad16) declares their precedence — index, then value,
then label — and that a lower one is ignored when a higher one is present.
Before it did, the three drivers resolved them in three orders, and a
consumer step carrying `index` plus a free-text `label` meant as the step
note (which `label` is on every other action) set the iOS picker wheel to
the note and failed, while Android passed (2026-09-03).

The place an author actually sees this is `jsonui-test validate`, so the
validator warns on two or more selectors. One selector is silent — a lone
`label` included, since that step selects by text exactly as the schema
says. The order the warning names is read back from the vendored schema, so
the two cannot drift apart without this file going red.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.cli import main
from jsonui_test_cli.validation.models import ValidationResult
from jsonui_test_cli.validation.step import StepValidator
from jsonui_test_cli.validation.validator import TestValidator

FIXTURES = Path(__file__).parent / "schema_fixtures"
PRECEDENCE_PHRASE = "precedence is index, then value, then label"


def outcome(step: dict):
    validator = StepValidator()
    result = ValidationResult("f.test.json")
    validator.validate_step(dict(step), "s", result, is_flow=False)
    return [m.message for m in result.errors], [m for m in result.warnings]


def select(**selectors) -> dict:
    return {"action": "selectOption", "id": "vintage_select", **selectors}


class TestTwoOrMoreSelectorsWarn:
    def test_the_reported_shape_index_plus_a_note_in_label(self):
        errors, warnings = outcome(select(index=1, label="step 3: pick the vintage (note)"))
        assert errors == []
        assert len(warnings) == 1
        message = warnings[0].message
        assert warnings[0].level == "warning"
        assert PRECEDENCE_PHRASE in message
        assert "'index' selects" in message and "'label' is ignored" in message
        # the sentence an author needs: this key is not the note here
        assert "not a step note" in message

    def test_value_plus_label_names_value_as_the_winner(self):
        _, warnings = outcome(select(value="2024", label="2024"))
        assert len(warnings) == 1
        assert "'value' selects" in warnings[0].message
        assert "'label' is ignored" in warnings[0].message

    def test_index_plus_value(self):
        _, warnings = outcome(select(index=0, value="2024"))
        assert len(warnings) == 1
        assert "'index' selects" in warnings[0].message
        assert "'value' is ignored" in warnings[0].message

    def test_all_three_name_index_and_both_losers(self):
        _, warnings = outcome(select(value="a", label="b", index=2))
        assert len(warnings) == 1
        assert "3 selectors (index, value, label)" in warnings[0].message
        assert "'value' and 'label' are ignored" in warnings[0].message

    def test_it_is_a_warning_not_an_error(self):
        errors, warnings = outcome(select(index=1, label="note"))
        assert errors == []
        assert all(w.level == "warning" for w in warnings)


class TestOneSelectorIsSilent:
    def test_index_alone(self):
        assert outcome(select(index=1)) == ([], [])

    def test_value_alone(self):
        assert outcome(select(value="2024")) == ([], [])

    def test_label_alone_even_if_it_was_meant_as_a_note(self):
        # That step selects by text; the schema says so, and the driver does
        # exactly that. Nothing to warn about — the author's intent is not
        # visible from the file, and a warning on every lone label would fire
        # on every correct by-text step.
        assert outcome(select(label="Spring Release 2026")) == ([], [])


class TestTheLintIsSelectOptionOnly:
    """Control: on every other action `label` IS the note, and `index` is not
    a selector. The same two keys on tapItem must stay silent."""

    def test_tap_item_with_index_and_a_label_note(self):
        errors, warnings = outcome({"action": "tapItem", "id": "list", "index": 1, "label": "tap the 2nd"})
        assert errors == []
        assert [w for w in warnings if PRECEDENCE_PHRASE in w.message] == []

    def test_select_tab_with_index_and_a_label_note(self):
        errors, warnings = outcome({"action": "selectTab", "id": "tabs", "index": 0, "label": "home tab"})
        assert errors == []
        assert [w for w in warnings if PRECEDENCE_PHRASE in w.message] == []


class TestTheOrderIsTheSchemas:
    """The warning's order and the vendored schema's order are one fact.

    Asserted against the vendored copy, not a literal: if the canonical
    schema ever re-declares the order, re-vendoring turns this red and the
    validator's constant has to move with it.
    """

    def test_the_constant_matches_the_schema_description(self):
        schema = json.loads((FIXTURES / "actions.schema.json").read_text("utf-8"))
        # Located by its `action` const, the way test_schema_drift reads the
        # file — the definition's key is not part of the contract.
        props = next(
            d["properties"] for d in schema["definitions"].values()
            if d.get("properties", {}).get("action", {}).get("const") == "selectOption"
        )
        # Each selector's description spells the three names in order
        # ("index, then value, then label" / "order: index, value, label").
        names = StepValidator.SELECT_OPTION_PRECEDENCE
        declared = re.compile(r"\b" + r",? (?:then )?".join(names) + r"\b")
        for key in names:
            assert declared.search(props[key]["description"]), (
                f"schema's selectOption.{key} no longer declares the order {names}; "
                "the validator's SELECT_OPTION_PRECEDENCE and the warning text must follow the schema"
            )
        # and the order is not also declared the other way round anywhere
        reversed_order = re.compile(r"\blabel,? (?:then )?value,? (?:then )?index\b")
        assert not any(reversed_order.search(props[k]["description"]) for k in names)
        # and the message the author reads names that same order
        _, warnings = outcome(select(index=0, label="x"))
        assert PRECEDENCE_PHRASE in warnings[0].message


class TestItReachesTheAuthor:
    """Through the file validator and the CLI's stdout, not only the unit."""

    def _file(self, step: dict) -> str:
        data = {
            "type": "screen",
            "source": {"layout": "release.json"},
            "metadata": {"name": "release"},
            "cases": [{"name": "pick", "steps": [step]}],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".test.json", delete=False) as f:
            json.dump(data, f)
            return f.name

    def test_validate_file_carries_the_warning(self):
        path = self._file(select(index=1, label="note"))
        try:
            result = TestValidator().validate_file(Path(path))
            assert result.errors == []
            assert [w for w in result.warnings if PRECEDENCE_PHRASE in w.message]
        finally:
            Path(path).unlink()

    def test_the_cli_prints_it_and_still_exits_zero(self, capsys):
        path = self._file(select(index=1, label="note"))
        try:
            with patch("sys.argv", ["jsonui-test", "validate", path]):
                code = main()
            out = capsys.readouterr().out
            assert code == 0
            assert PRECEDENCE_PHRASE in out
        finally:
            Path(path).unlink()
