"""A key the mock server reads must be a key the tools accept.

`skipRequestValidation` is honoured at serve time — the server checks what
the app SENT against the swagger and records violations, and this key turns
that off for one scenario. It was in neither `VALID_SCENARIO_KEYS` nor
`mock.schema.json`, so a project using it correctly got:

    [WARN] ...scenarios.default: Unknown scenario key: skipRequestValidation

from `validate`, and an invalid marker from any editor honouring the schema.

THE TWO DIRECTIONS ARE NOT THE SAME DEFECT. An unchecked constraint means
"write it and nothing happens" — measured, 12 of the 16 constraints in that
schema are unenforced. An unregistered key means "write it CORRECTLY and be
told you are wrong", and the only way to clear the warning was to stop using
the feature. For a lane running `Warnings: 0` that is a permanent +1 with no
remedy, which is the shape rulings elsewhere in this codebase call
unacceptable in a finding.

It is also the direction a reader of the schema cannot find: you have to
start from the runtime and look back. Enumerating what the schema declares
finds the other twelve and none of these.

So this derives the server's reads FROM ITS SOURCE rather than restating
them. A list here would be a third copy of the same set, and the copy that
does not get updated is how the first one happened.

ONE DIRECTION ONLY, deliberately. "Registered but the server never reads it"
is legitimate: `contractViolations` and `undeclaredStatus` are authoring-time
declarations the contract checker reads and the server has no use for. An
invariant in that direction would fail on two correct keys.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validation.mock import (
    VALID_SCENARIO_KEYS, VALID_SOURCE_KEYS,
)

_PKG = Path(__file__).parent.parent / "jsonui_test_cli"
_SERVER = _PKG / "mock" / "server.py"
_SCHEMA = _PKG / "static" / "mock.schema.json"


def _literal_keys(source: str, subjects: set) -> set:
    """`x.get("k")` and `x["k"]` for x in `subjects`, as a set of k.

    Constant string subscripts only: a computed key cannot be registered
    ahead of time, and pretending to see one would put a `None` in the set.
    """
    found = set()
    for node in ast.walk(ast.parse(source)):
        base = key = None
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            base, key = node.func.value, node.args[0].value
        elif (isinstance(node, ast.Subscript)
              and isinstance(node.slice, ast.Constant)
              and isinstance(node.slice.value, str)):
            base, key = node.value, node.slice.value
        if isinstance(base, ast.Name) and base.id in subjects:
            found.add(key)
    return found


def _server_reads(subjects: set) -> set:
    return _literal_keys(_SERVER.read_text(encoding="utf-8"), subjects)


def _schema_properties_node(*path) -> dict:
    node = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    for step in path:
        node = node[step]
    return node["properties"]


def _schema_properties(*path) -> set:
    return set(_schema_properties_node(*path))


class TestTheScannerReallyReadsSource:
    """The negative control, first.

    A source scan returns an empty set when it cannot read what it was
    pointed at, and an empty set satisfies every "is a subset of" assertion
    below — so the whole file would be vacuously green. This has happened
    here before, which is why it is a test and not a comment.
    """

    def test_it_finds_keys_everyone_agrees_exist(self):
        reads = _server_reads({"scenario"})

        assert {"status", "body"} <= reads, reads

    def test_it_finds_nothing_for_a_name_the_server_never_uses(self):
        """The other half: a scanner that returned every string literal in
        the file would also pass the test above."""
        assert _server_reads({"no_such_local_name"}) == set()

    def test_an_unregistered_key_would_be_caught(self):
        """Fire the invariant itself, on a source the scanner is handed
        rather than on the real one — otherwise "the check works" and "the
        code is clean" are the same green."""
        reads = _literal_keys(
            'scenario.get("status")\nscenario.get("madeUpKey")\n', {"scenario"})

        assert reads - set(VALID_SCENARIO_KEYS) == {"madeUpKey"}


class TestEveryKeyTheServerReadsIsRegistered:
    def test_scenario_keys_are_in_the_validator(self):
        unregistered = _server_reads({"scenario"}) - set(VALID_SCENARIO_KEYS)

        assert unregistered == set(), (
            f"the mock server reads {sorted(unregistered)} but the validator "
            "reports them as unknown scenario keys")

    def test_scenario_keys_are_in_the_editor_schema(self):
        missing = _server_reads({"scenario"}) - _schema_properties(
            "properties", "scenarios", "additionalProperties")

        assert missing == set(), (
            f"the mock server reads {sorted(missing)} but the schema declares "
            "additionalProperties:false, so an editor marks them invalid")

    def test_source_keys_are_registered_in_both(self):
        """The same sweep one level up. Green today — recorded so that
        "we checked scenarios" does not stand in for "we checked the
        document"."""
        reads = _server_reads({"src"})

        assert reads - set(VALID_SOURCE_KEYS) == set()
        assert reads - _schema_properties("properties", "source") == set()


class TestTheTwoRegistriesAgree:
    """The validator and the schema are two statements of one set.

    Measured when this was written: they agreed exactly, and both were
    missing the same key — so agreement between them is not evidence that
    either is right. It is still worth pinning, because the fix touched both
    and a fix that touched one would leave the editor and the CLI disagreeing
    about the same file.
    """

    @pytest.mark.parametrize("registry,path", [
        (VALID_SCENARIO_KEYS,
         ("properties", "scenarios", "additionalProperties")),
        (VALID_SOURCE_KEYS, ("properties", "source")),
    ])
    def test_they_declare_the_same_keys(self, registry, path):
        assert set(registry) == _schema_properties(*path)


class TestTheKeyThatStartedIt:
    def test_a_scenario_using_it_validates_clean(self, tmp_path):
        """End to end, in the words the reporter saw."""
        from jsonui_test_cli.validation.validator import TestValidator

        mock = tmp_path / "getX.mock.json"
        mock.write_text(json.dumps({
            "source": {"method": "GET", "path": "/api/x"},
            "scenarios": {"default": {"status": 200, "body": {},
                                      "skipRequestValidation": True}},
        }), encoding="utf-8")

        result = TestValidator().validate_file(mock)

        assert result.errors == []
        assert [str(w) for w in result.warnings] == []

    def test_an_actually_unknown_key_is_still_warned_about(self, tmp_path):
        """The control. Registering one key must not have turned the check
        off — "no warning" and "no check" read identically."""
        from jsonui_test_cli.validation.validator import TestValidator

        mock = tmp_path / "getX.mock.json"
        mock.write_text(json.dumps({
            "source": {"method": "GET", "path": "/api/x"},
            "scenarios": {"default": {"status": 200, "body": {},
                                      "skipRequestValidatoin": True}},
        }), encoding="utf-8")

        result = TestValidator().validate_file(mock)

        assert any("Unknown scenario key" in str(w) for w in result.warnings)


class TestTheSchemaAcceptsWhatTheToolsAccept:
    """The other direction of the same family: input the tools take that the
    schema calls invalid.

    `skipRequestValidation` was a key the server honoured and neither
    registry declared. `method` was the same shape one level along — the CLI
    uppercases before matching (`validation/mock.py`) and so does the mock
    server on both the read and the route match (`server.py`), so `"get"`
    works everywhere and only the schema's uppercase-only enum marked it
    invalid.

    Derived from `VALID_METHODS` rather than restated, for the reason the
    file above exists: a second list is a second thing to forget.
    """

    def _method_enum(self) -> set:
        return set(_schema_properties_node("properties", "source")["method"]["enum"])

    def test_every_method_is_accepted_in_either_case(self):
        from jsonui_test_cli.validation.mock import VALID_METHODS

        enum = self._method_enum()
        missing = {m for m in VALID_METHODS if m not in enum or m.lower() not in enum}

        assert missing == set(), (
            f"the CLI accepts {sorted(missing)} in any case, but the schema's "
            "enum does not list both spellings")

    def test_it_does_not_accept_a_method_the_cli_rejects(self):
        """The control. Listing both cases must not have turned into listing
        anything — an enum of every string would satisfy the test above."""
        from jsonui_test_cli.validation.mock import VALID_METHODS

        enum = self._method_enum()

        assert "TRACE" not in enum and "trace" not in enum
        assert enum == ({m for m in VALID_METHODS} |
                        {m.lower() for m in VALID_METHODS})


class TestTheInertKeyIsGone:
    """`headers` was declared in both registries and read by nobody.

    Measured three ways before removing it: the mock server never reads it
    (the scenario walk in `server.py` copies scenarios verbatim and `_send`
    writes only Content-Type, Content-Length and CORS), the contract checker
    never reads it, and the three drivers do not parse mock documents at
    all. Zero occurrences across every consumer face.

    A key that can be written and is then ignored is the same defect as one
    that cannot be written at all — both are the tool disagreeing with
    itself about what the document means.
    """

    def test_it_is_absent_from_both_registries(self):
        from jsonui_test_cli.validation.mock import VALID_SCENARIO_KEYS

        assert "headers" not in VALID_SCENARIO_KEYS
        assert "headers" not in _schema_properties(
            "properties", "scenarios", "additionalProperties")

    def test_a_scenario_using_it_is_now_told_so(self, tmp_path):
        """Removing it has to be VISIBLE, not silent: a project that still
        writes it must hear that nothing reads it, rather than carrying a
        key with no effect for another release."""
        from jsonui_test_cli.validation.validator import TestValidator

        mock = tmp_path / "getX.mock.json"
        mock.write_text(json.dumps({
            "source": {"method": "GET", "path": "/api/x"},
            "scenarios": {"default": {"status": 200, "body": {},
                                      "headers": {"X-Trace": "1"}}},
        }), encoding="utf-8")

        result = TestValidator().validate_file(mock)

        assert any("Unknown scenario key: headers" in str(w)
                   for w in result.warnings)
        assert result.errors == []
