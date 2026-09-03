"""`@canonical` resolves a string enum to `String`, and now says so.

A method whose `params` is `"@canonical"` gets its arguments from the API
canon. A request-body field declared as a string `enum` resolves to `String`
— the type vocabulary specs are written in — while the DTO generated from
that same schema holds a generated enum. So a repository written against
both converts at the boundary, and the conversion a consumer writes is
`Enum(rawValue:)`, which returns nil for anything unexpected. Dropping the
value there is the exact failure this family of work exists to remove.

Reported from a consumer:

    login.spec.json  AuthRepository.snsLogin  params: "@canonical"
      protocol   func snsLogin(provider: String, ...)
      generated  SnsLoginRequestDto(provider: SnsLoginRequestProvider, ...)

This does NOT change the signature. Typing the argument would change
generated protocols, which forces hand-written repositories to change in the
same commit — measured at 7 routes on one project alone (admin 3 / user 4),
plus the reporting project — and there is a second hole under it: the enum
name is derivable, but nothing here guarantees that schema is in the
codegen's output, so a typed signature could name a type that is never
emitted. That is worse than `String`. Both are why this release names the
gap and leaves the type alone.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.core import shared_core  # noqa: E402

oc = shared_core.openapi_canonical()

SCHEMAS = {
    "SnsLoginRequest": {
        "type": "object",
        "required": ["provider", "id_token"],
        "properties": {
            "provider": {"type": "string", "enum": ["google", "apple"]},
            "id_token": {"type": "string"},
            "display_name": {"type": "string"},
        },
    },
    "Named": {
        "type": "object",
        "required": ["kind"],
        "properties": {
            "kind": {"type": "string", "enum": ["a"], "x-jui-name": "KindOverride"},
        },
    },
    "ByRef": {
        "type": "object",
        "required": ["provider"],
        "properties": {"provider": {"$ref": "#/components/schemas/Provider"}},
    },
    "Provider": {"type": "string", "enum": ["google", "apple"]},
    "NotAnEnum": {
        "type": "object",
        "required": ["count"],
        "properties": {"count": {"type": "integer"}},
    },
    # An array of enums widens to `[String]`, and the DTO holds an array of
    # a derived enum — the same gap, one level in.
    "BarRecommendedServingsRequest": {
        "type": "object",
        "required": ["recommended_servings"],
        "properties": {"recommended_servings": {
            "type": "array", "items": {"type": "string", "enum": ["neat", "rock"]}}},
    },
    "PlainArray": {
        "type": "object",
        "required": ["tags"],
        "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    },
    "IntEnum": {
        "type": "object",
        "required": ["level"],
        "properties": {"level": {"type": "integer", "enum": [1, 2]}},
    },
}


def operation_for(schema_name: str, required: bool = True):
    op = {"requestBody": {"required": required, "content": {"application/json": {
        "schema": {"$ref": f"#/components/schemas/{schema_name}"}}}}}
    return oc.CanonicalOperation(
        path="/api/x", method="POST",
        params=tuple(oc._operation_params(op, SCHEMAS)),
    )


def warnings_for(schema_name: str, declared="@canonical", convention=None):
    """`(arg, expanded type, enum the DTO holds)` for one operation."""
    return oc.resolve_params(
        declared, operation_for(schema_name), convention).widened_enums


def described(schema_name: str) -> str:
    return " ".join(f"{n} {t} {e}" for n, t, e in warnings_for(schema_name))


class TheGapIsNamed(unittest.TestCase):
    def test_a_string_enum_body_field_is_reported(self):
        found = warnings_for("SnsLoginRequest")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], "provider")

    def test_the_message_carries_the_type_the_dto_would_hold(self):
        # The name is what makes the warning countable AND actionable: a
        # project can grep for it and see what typing would produce.
        self.assertEqual(warnings_for("SnsLoginRequest")[0][2], "SnsLoginRequestProvider")

    def test_it_records_the_type_the_expansion_actually_produced(self):
        # Both halves of the gap in one row, so a reader never has to pair
        # them up from two places.
        self.assertEqual(warnings_for("SnsLoginRequest")[0][1], "String")

    def test_x_jui_name_wins_the_way_it_does_for_the_dto(self):
        self.assertEqual(warnings_for("Named")[0][2], "KindOverride")

    def test_an_integer_enum_counts_too(self):
        # The loader derives for `string` OR `integer`; counting only
        # strings would under-report against the DTO it is compared with.
        self.assertEqual(warnings_for("IntEnum")[0][2], "IntEnumLevel")

    def test_an_array_of_enums_counts(self):
        # `[String]` in the protocol, `[<derived>Item]` in the DTO. The
        # neighbouring project pre-registered this exact name before the
        # implementation existed, which is why it is spelled out here.
        found = warnings_for("BarRecommendedServingsRequest")
        self.assertEqual(len(found), 1)
        self.assertEqual(
            found[0][2], "BarRecommendedServingsRequestRecommendedServingsItem")

    def test_the_array_case_reports_the_array_type_it_expanded_to(self):
        self.assertEqual(
            warnings_for("BarRecommendedServingsRequest")[0][1], "[String]")


class TheSignatureIsUntouched(unittest.TestCase):
    """The whole point of shipping this and not the typing."""

    def test_the_expanded_params_are_byte_for_byte_what_they_were(self):
        res = oc.resolve_params("@canonical", operation_for("SnsLoginRequest"), None)
        self.assertEqual(res.params, [
            {"name": "provider", "type": "String"},
            {"name": "id_token", "type": "String"},
            {"name": "display_name", "type": "String?"},
        ])

    def test_a_warning_is_not_an_error(self):
        res = oc.resolve_params("@canonical", operation_for("SnsLoginRequest"), None)
        self.assertEqual(res.errors, [])


class ThingsThatMustStaySilent(unittest.TestCase):
    def test_a_body_with_no_enum_says_nothing(self):
        self.assertEqual(warnings_for("NotAnEnum"), [])

    def test_a_ref_to_a_named_enum_is_not_a_gap(self):
        # `$ref` already resolves to the schema's own name, so the protocol
        # and the DTO agree. Warning here would be a false positive on the
        # shape the reporter is being asked to move toward.
        self.assertEqual(operation_for("ByRef").params[0].type, "Provider")
        self.assertEqual(warnings_for("ByRef"), [])

    def test_a_hand_written_entry_replacing_the_field_is_the_author_s_call(self):
        declared = [{"name": "provider", "type": "AuthProvider"}, "@canonical"]
        self.assertEqual(warnings_for("SnsLoginRequest", declared), [])

    def test_an_inline_body_with_no_schema_name_is_not_guessed_at(self):
        """A known blind spot, pinned so it is a decision and not an accident.

        The DTO enum name is `{BodySchema}{Field}`. A body written inline
        (no `$ref`, e.g. a bare `allOf` composition) has no schema name here,
        so there is nothing to name the enum after — and a warning naming a
        type that is not what the generator emits is worse than silence.
        Such a body under-counts. Say so rather than report a guess.
        """
        op = {"requestBody": {"required": True, "content": {"application/json": {
            "schema": {"type": "object", "required": ["provider"], "properties": {
                "provider": {"type": "string", "enum": ["a"]}}}}}}}
        operation = oc.CanonicalOperation(
            path="/api/x", method="POST",
            params=tuple(oc._operation_params(op, SCHEMAS)))
        self.assertEqual(operation.params[0].type, "String")
        self.assertEqual(
            oc.resolve_params("@canonical", operation, None).widened_enums, [])

    def test_a_method_with_no_mark_is_not_walked(self):
        declared = [{"name": "provider", "type": "String"}]
        self.assertEqual(warnings_for("SnsLoginRequest", declared), [])


class TheInventoryReachesTheCaller(unittest.TestCase):
    """Without this the feature is data nobody reads. `iter_widened_enums` is
    the only public way in, and it must not disturb what it inspects."""

    DOC = {
        "openapi": "3.0.0",
        "paths": {"/api/x": {"post": {"requestBody": {
            "required": True,
            "content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/SnsLoginRequest"}}}}}}},
        "components": {"schemas": SCHEMAS},
    }

    def _spec(self, n=1):
        return {"dataFlow": {"repositories": [{"name": "AuthRepository", "methods": [
            {"name": f"m{i}", "endpoint": "POST /api/x", "params": "@canonical"}
            for i in range(n)]}]}}

    def _found(self, spec):
        return oc.iter_widened_enums(spec, oc.index_documents([("d.json", self.DOC)]), None)

    def test_it_finds_the_argument_and_names_the_method(self):
        found = self._found(self._spec())
        self.assertEqual(len(found), 1)
        label, arg, expanded, enum_name = found[0]
        self.assertEqual(label, "dataFlow.repositories[0].methods[0]")
        self.assertEqual((arg, expanded, enum_name),
                         ("provider", "String", "SnsLoginRequestProvider"))

    def test_the_two_counts_differ_and_both_are_available(self):
        # One route declared by three methods is three expansions and one
        # gap. A project comparing its number with another's has to know
        # which it is holding, so the caller can compute both — measured on
        # a real project as 13 expansions over 4 routes.
        found = self._found(self._spec(3))
        self.assertEqual(len(found), 3)
        self.assertEqual(len({(f[1], f[3]) for f in found}), 1)

    def test_it_does_not_rewrite_the_spec(self):
        # `resolve_spec_marks` expands in place; this must not, or asking for
        # the inventory would change what the build then generates.
        spec = self._spec()
        self._found(spec)
        self.assertEqual(
            spec["dataFlow"]["repositories"][0]["methods"][0]["params"],
            "@canonical")

    def test_it_stays_off_the_warning_channel(self):
        # A project gating at zero warnings cannot act on this finding —
        # typing the argument means giving up `@canonical`. Putting it on
        # that channel would raise their accepted baseline and hide the next
        # real warning behind it.
        spec = self._spec()
        errors, warnings = oc.resolve_spec_marks(
            spec, oc.index_documents([("d.json", self.DOC)]), None)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


class TheNameMatchesTheGeneratorS(unittest.TestCase):
    """`shared/core` sits below `jui_tools` and cannot import the loader, so
    the derivation is written twice. If they drift, the warning names a type
    that does not exist — which is the same defect as typing the signature
    wrongly, just quieter. This is the seam that holds them together."""

    def test_the_derived_name_agrees_with_the_loader_for_every_shape(self):
        from jui_cli.core.openapi_loader import _pascal

        for field in ("provider", "id_token", "display-name", "displayName",
                      "a", "two__words", "trailing_", "n1_x"):
            prop = {"type": "string", "enum": ["x"]}
            self.assertEqual(
                oc._derived_enum_name("Req", field, prop),
                f"Req{_pascal(field)}",
                f"derivation drifted for {field!r}",
            )

    def test_the_array_element_name_agrees_too(self):
        # The loader recurses into `items` with `field_name + "_item"`, so
        # the element enum is named off that, not off the field. A neighbour
        # predicted this exact name from the generator before the code
        # existed, which is the only independent check either of us has.
        from jui_cli.core.openapi_loader import _pascal

        for field in ("recommended_servings", "tags", "someList"):
            prop = {"type": "array", "items": {"type": "string", "enum": ["x"]}}
            self.assertEqual(
                oc._derived_enum_name("Req", field, prop),
                f"Req{_pascal(field + '_item')}",
                f"array derivation drifted for {field!r}",
            )


if __name__ == "__main__":
    unittest.main()


class TheNoteActuallyPrints(unittest.TestCase):
    """Drives the real entry point, in the real order.

    Every arm above calls `iter_widened_enums` on a spec straight from a
    literal. The CLI never has one: `resolve_canonical_marks` runs
    `resolve_spec_marks` first, which expands `params` IN PLACE, so a method
    that carried a mark stops looking like one. Shipped in 1.8.17 with the
    call below that line — the function returned 13 on a real project's
    specs and the build printed nothing, and 20 green arms said nothing
    about it because none of them had been through resolution.

    So this one asserts on stdout from `extract_screen_spec`. It is the
    order that has to be tested, and the order only exists here.
    """

    SWAGGER = {
        "openapi": "3.0.3",
        "paths": {"/api/me/locale": {"put": {"requestBody": {
            "required": True, "content": {"application/json": {"schema": {
                "$ref": "#/components/schemas/LocaleUpdateRequest"}}}}}}},
        "components": {"schemas": {"LocaleUpdateRequest": {
            "type": "object", "required": ["locale"],
            "properties": {"locale": {"type": "string", "enum": ["ja", "en"]}}}}},
    }

    def _spec(self, methods):
        return {
            "type": "screen",
            "metadata": {"name": "MyPage", "description": "F.", "screen": "my_page"},
            "dataFlow": {"repositories": [
                {"name": "UserRepository", "methods": methods}]},
        }

    def _run(self, methods):
        import contextlib
        import io
        import json
        from tempfile import TemporaryDirectory

        from jui_cli.core.spec_extractor import extract_screen_spec

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "api").mkdir(parents=True)
            (root / "docs" / "api" / "swagger.json").write_text(
                json.dumps(self.SWAGGER), encoding="utf-8")
            (root / "docs" / "screens").mkdir(parents=True)
            spec_path = root / "docs" / "screens" / "my_page.spec.json"
            spec_path.write_text(json.dumps(self._spec(methods)), encoding="utf-8")
            (root / "jui.config.json").write_text("{}", encoding="utf-8")

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                spec = extract_screen_spec(
                    json.loads(spec_path.read_text()), spec_path)
            return out.getvalue(), spec

    METHOD = {"name": "updateLocale", "endpoint": "PUT /api/me/locale",
              "params": "@canonical"}

    def test_the_note_reaches_stdout(self):
        printed, _ = self._run([dict(self.METHOD)])
        self.assertIn("NOTE:", printed)
        self.assertIn("LocaleUpdateRequestLocale", printed)

    def test_it_reports_both_counts_from_the_real_walk(self):
        # The shape that made this worth two numbers: one route, three
        # methods declaring it — the real project had ten.
        printed, _ = self._run([
            dict(self.METHOD, name=f"updateLocale{i}") for i in range(3)])
        self.assertIn("1 argument(s) in 3 '@canonical' expansion(s)", printed)

    def test_the_mark_still_expanded_alongside_it(self):
        # The inventory must not cost the expansion, and running it first
        # must not leave the mark unresolved.
        _, spec = self._run([dict(self.METHOD)])
        params = spec.repositories[0].methods[0].params
        self.assertEqual([(p.name, p.type) for p in params], [("locale", "String")])

    def test_a_spec_with_nothing_to_report_prints_no_note(self):
        method = {"name": "updateLocale", "endpoint": "PUT /api/me/locale",
                  "params": [{"name": "locale", "type": "String"}]}
        printed, _ = self._run([method])
        self.assertNotIn("NOTE:", printed)
