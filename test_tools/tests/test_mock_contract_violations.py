"""Tests for `contractViolations` — declared, intentional contract breaks.

Some mock scenarios exist BECAUSE the body breaks the contract: omitting a
required field is how a test proves the client fails closed when the server
omits it. Without a way to declare that, those scenarios read as drift, the
check never reaches zero, and a check that never reaches zero stops being a
gate — the reporting project had exactly two such scenarios left after
fixing twenty real ones, and shelved the gate because of them.

The declaration is deliberately narrow: it names paths, not scenarios. The
tests below are mostly about what still fails — an undeclared violation in
the same scenario, a declaration with no reason, and a declaration that no
longer matches anything (a negative scenario that quietly turned positive).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import (
    GENERATED_DIR,
    ViolationDeclaration,
    generate,
    update_default,
)

SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/crates/{crate_id}": {
            "get": {
                "operationId": "getCrate",
                "tags": ["Crates"],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/Crate"}}}}},
            }
        },
    },
    "components": {"schemas": {
        "Crate": {
            "type": "object",
            "required": ["name", "variants"],
            "properties": {
                "name": {"type": "string"},
                "variants": {"type": "array",
                                "items": {"$ref": "#/components/schemas/Variant"}},
            },
        },
        "Variant": {
            "type": "object",
            "required": ["kind", "spec_digest"],
            "properties": {
                "kind": {"type": "string"},
                "spec_digest": {"type": "string"},
            },
        },
    }},
}


def _setup(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    out = tmp_path / "mocks"
    generate([str(spec)], out)
    for src in sorted((out / GENERATED_DIR).rglob("*.mock.json")):
        dst = out / src.relative_to(out / GENERATED_DIR)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
    return str(spec), out


def _write(path, scenarios):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["scenarios"] = scenarios
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _mock(out):
    return out / "crates" / "getCrate.mock.json"


def _sound_body():
    return {"name": "P", "variants": [
        {"kind": "small", "spec_digest": "abc"},
        {"kind": "large", "spec_digest": "def"},
    ]}


def _body_without_digests():
    return {"name": "P", "variants": [{"kind": "small"}, {"kind": "large"}]}


class TestDeclarationParsing:
    def test_absent_declaration_is_none(self):
        assert ViolationDeclaration.parse(None) is None

    def test_reason_is_required(self):
        decl = ViolationDeclaration.parse({"missing": [".a"]})
        assert any("reason" in e for e in decl.errors)

    def test_unknown_category_is_rejected(self):
        decl = ViolationDeclaration.parse(
            {"absent": [".a"], "reason": "why"})
        assert any("unknown contractViolations key" in e for e in decl.errors)

    def test_empty_declaration_is_rejected(self):
        decl = ViolationDeclaration.parse({"reason": "why"})
        assert any("declares no paths" in e for e in decl.errors)

    def test_a_single_path_may_be_a_bare_string(self):
        decl = ViolationDeclaration.parse({"missing": ".a", "reason": "why"})
        assert decl.errors == []
        assert decl.paths["missing"] == (".a",)


class TestDeclaredViolations:
    def test_a_declared_omission_clears_the_check(self, tmp_path):
        spec, out = _setup(tmp_path)
        _write(_mock(out), {"default": {"status": 200, "body": _sound_body()},
                            "no_digest": {
                                "status": 200,
                                "contractViolations": {
                                    "missing": [".variants[].spec_digest"],
                                    "reason": "refuses to ship when the server "
                                              "omits the digest",
                                },
                                "body": _body_without_digests()}})
        report = generate([spec], out, check=True)
        assert not report.has_drift, [str(b) for b in report.bodies]

    def test_an_index_may_be_pinned(self, tmp_path):
        spec, out = _setup(tmp_path)
        body = _sound_body()
        del body["variants"][1]["spec_digest"]
        _write(_mock(out), {"default": {
            "status": 200,
            "contractViolations": {"missing": [".variants[1].spec_digest"],
                                   "reason": "one mode without a policy"},
            "body": body}})
        assert not generate([spec], out, check=True).has_drift

    def test_an_undeclared_violation_in_the_same_scenario_still_fails(self, tmp_path):
        # The point of naming paths instead of scenarios: a negative
        # scenario is exactly where an accidental drift hides best.
        spec, out = _setup(tmp_path)
        body = _body_without_digests()
        del body["name"]
        _write(_mock(out), {"default": {
            "status": 200,
            "contractViolations": {"missing": [".variants[].spec_digest"],
                                   "reason": "fail-closed check"},
            "body": body}})
        report = generate([spec], out, check=True)
        assert report.has_drift
        assert report.bodies[0].missing == [".name"]

    def test_a_declaration_without_a_reason_fails(self, tmp_path):
        spec, out = _setup(tmp_path)
        _write(_mock(out), {"default": {
            "status": 200,
            "contractViolations": {"missing": [".variants[].spec_digest"]},
            "body": _body_without_digests()}})
        report = generate([spec], out, check=True)
        assert report.has_drift
        assert any("reason" in p for p in report.bodies[0].declaration)

    def test_a_declaration_that_no_longer_matches_fails(self, tmp_path):
        # The quiet half: the body now satisfies the contract, so the
        # scenario no longer exercises the defence it was written for.
        spec, out = _setup(tmp_path)
        _write(_mock(out), {"default": {
            "status": 200,
            "contractViolations": {"missing": [".variants[].spec_digest"],
                                   "reason": "fail-closed check"},
            "body": _sound_body()}})
        report = generate([spec], out, check=True)
        assert report.has_drift
        assert any("no longer violates" in p for p in report.bodies[0].declaration)

    def test_declared_extra_and_value_violations(self, tmp_path):
        spec, out = _setup(tmp_path)
        body = _sound_body()
        body["surprise"] = 1
        body["variants"][0]["spec_digest"] = 7   # wrong type
        _write(_mock(out), {"default": {
            "status": 200,
            "contractViolations": {
                "extra": [".surprise"],
                "violations": [".variants[].spec_digest"],
                "reason": "reproduces a server that sends junk",
            },
            "body": body}})
        assert not generate([spec], out, check=True).has_drift

    def test_a_declaration_in_the_generated_tree_is_reported(self, tmp_path):
        # Regenerating deletes it, silently, and the scenario goes red
        # again with no trace of what was decided.
        spec = tmp_path / "spec.json"
        spec.write_text(json.dumps(SPEC), encoding="utf-8")
        out = tmp_path / "mocks"
        generate([str(spec)], out)
        gen = out / GENERATED_DIR / "crates" / "getCrate.mock.json"
        _write(gen, {"default": {
            "status": 200,
            "contractViolations": {"missing": [".variants[].spec_digest"],
                                   "reason": "fail-closed check"},
            "body": _body_without_digests()}})
        report = generate([str(spec)], out, check=True)
        drift = next(b for b in report.bodies if b.generated)
        assert any("deleted on the next regeneration" in p
                   for p in drift.declaration)


class TestRepairInteraction:
    def test_update_default_does_not_fill_a_declared_omission(self, tmp_path):
        # `--update-default` adds required fields a body lacks. Doing that
        # to a declared omission repairs away the very condition the
        # scenario exists to reproduce — and the test keeps passing while
        # proving nothing.
        spec, out = _setup(tmp_path)
        mock = _mock(out)
        _write(mock, {"default": {
            "status": 200,
            "contractViolations": {"missing": [".variants[].spec_digest"],
                                   "reason": "fail-closed check"},
            "body": _body_without_digests()}})
        update_default([spec], out)
        after = json.loads(mock.read_text(encoding="utf-8"))
        modes = after["scenarios"]["default"]["body"]["variants"]
        assert all("spec_digest" not in m for m in modes)

    def test_update_default_still_fills_an_undeclared_omission(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = _mock(out)
        _write(mock, {"default": {"status": 200,
                                  "body": _body_without_digests()}})
        update_default([spec], out)
        after = json.loads(mock.read_text(encoding="utf-8"))
        modes = after["scenarios"]["default"]["body"]["variants"]
        assert all("spec_digest" in m for m in modes)


class TestValidatorAcceptsTheKey:
    def test_contract_violations_is_not_an_unknown_scenario_key(self, tmp_path):
        from jsonui_test_cli.validation.mock import VALID_SCENARIO_KEYS
        assert "contractViolations" in VALID_SCENARIO_KEYS
