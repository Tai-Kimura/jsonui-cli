"""Web ViewModelBase var declarations must be valid, initialized TypeScript.

Two reported defects, one cause. `web_generator` carried a private five-word
type table (`_TS_TYPE_OVERRIDES`) instead of routing through the `TypeMapper`
that iOS and Android use — and that this same file already used for method
signatures. The table only matched exact spellings, so every canonical
spelling that was not one of the five words reached the output verbatim:

    public token?: String?;    // TS17019 — reported
    public rows: List(Item);   // same family, found by A/B
    public onDone: callback;   // TS2304, same family

The fix is the table's removal, not a `?`-stripping branch added to it: a
second implementation of "what is this type here" is what let the two answers
drift apart in the first place.

The second defect is the initializer: a non-optional field with no initializer
is a TS2564 under `strict`, and unlike iOS/Kotlin — whose scaffolds are
written once and stay editable — this file is `@generated` and rewritten every
build, so the consumer cannot clear it.

The declarations here were checked against tsc 5.9.3 under `--strict` while
the fix was developed (8 errors before, 0 after); these tests pin the emitted
shapes, and `NoOutputIsInvalidTypeScript` generalizes what tsc taught us so a
new type spelling cannot reintroduce either shape unnoticed.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.spec_extractor import ScreenSpec, VarDef, ViewModelDef
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.web_generator import WebGenerator


def _gen(root: Path, type_map: dict | None = None) -> WebGenerator:
    path = None
    if type_map is not None:
        path = root / ".jsonui-type-map.json"
        path.write_text(json.dumps({"types": type_map}), encoding="utf-8")
    return WebGenerator(root, {}, TypeMapper(path))


def declare(*vars_: VarDef, type_map: dict | None = None) -> tuple[list[str], list[str]]:
    """Return (declaration lines, warning messages) for *vars_*."""
    spec = ScreenSpec(
        name="AccountSetup", display_name="", description="",
        layout_file="account_setup",
        view_model=ViewModelDef(vars=list(vars_)),
    )
    with tempfile.TemporaryDirectory() as tmp:
        gen = _gen(Path(tmp), type_map)
        out = gen.generate_viewmodel_protocol(spec)
        return (
            [ln.strip() for ln in out.splitlines() if ln.startswith("  public ")],
            [w.message for w in gen.warnings],
        )


def one(*args, **kw) -> str:
    lines, _ = declare(*args, **kw)
    assert len(lines) == 1, lines
    return lines[0]


def var(name="v", type="String", **kw) -> VarDef:
    kw.setdefault("observable", False)
    return VarDef(name=name, type=type, **kw)


class OptionalSuffixIsMappedNotPassedThrough(unittest.TestCase):
    """The reported defect: `String?` reaching TS as `String?`."""

    def test_the_reported_declaration(self):
        """`optional: true` *and* a `?` in the type — both faces survive.

        The member's `?:` and the type's `| undefined` are two different
        declarations, so both are emitted. Collapsing either would silence
        something the spec said; the redundancy is deliberate.
        """
        self.assertEqual(
            one(var("token", "String?", optional=True)),
            "public token?: string | undefined;",
        )

    def test_the_optional_flag_path_still_works(self):
        """Lane B's A/B established this half was already healthy."""
        self.assertEqual(
            one(var("session", "String", optional=True)),
            "public session?: string;",
        )

    def test_an_optional_type_on_a_non_optional_member(self):
        """The other half of the pair: the type face alone."""
        self.assertEqual(
            one(var("token", "String?")),
            "public token: string | undefined = undefined;",
        )

    def test_the_siblings_the_report_predicted(self):
        for spec_type, expected in [
            ("Int?", "number | undefined"),
            ("Double?", "number | undefined"),
            ("Bool?", "boolean | undefined"),
            ("[String]?", "string[] | undefined"),
            ("Map(String,String)?", "Record<string, string> | undefined"),
        ]:
            with self.subTest(spec_type=spec_type):
                self.assertEqual(
                    one(var("v", spec_type, optional=True)),
                    f"public v?: {expected};",
                )


class CanonicalSpellingsReachTypeScript(unittest.TestCase):
    """Not in either report — found by A/B, same cause, same fix."""

    def test_collection_spellings_are_translated(self):
        for spec_type in ("[Item]", "List(Item)", "Array(Item)"):
            with self.subTest(spec_type=spec_type):
                self.assertEqual(
                    one(var("rows", spec_type)), "public rows: Item[] = [];")

    def test_callback_is_translated(self):
        self.assertEqual(
            one(var("onDone", "callback")),
            "public onDone: (() => void) | undefined = undefined;",
        )

    def test_swift_closure_spelling_becomes_an_arrow(self):
        self.assertEqual(
            one(var("onTap", "(() -> Void)?")),
            "public onTap: (() => void) | undefined = undefined;",
        )


class NonOptionalFieldsAreInitialized(unittest.TestCase):
    """The second report: TS2564 on a file the consumer cannot edit."""

    def test_scalars_take_the_declared_zero_value(self):
        for spec_type, expected in [
            ("Bool", "boolean = false"),
            ("Int", "number = 0"),
            ("Double", "number = 0.0"),
            ("String", 'string = ""'),
        ]:
            with self.subTest(spec_type=spec_type):
                self.assertEqual(
                    one(var("v", spec_type)), f"public v: {expected};")

    def test_the_reported_declaration(self):
        self.assertEqual(
            one(var("isSubmitting", "Bool")),
            "public isSubmitting: boolean = false;",
        )

    def test_a_list_takes_the_empty_list(self):
        self.assertEqual(one(var("rows", "[String]")),
                         "public rows: string[] = [];")

    def test_an_optional_member_takes_no_initializer(self):
        """`?:` already admits absence; an initializer would contradict it."""
        self.assertEqual(one(var("memo", "String", optional=True)),
                         "public memo?: string;")

    def test_a_type_that_admits_undefined_is_initialized_with_undefined(self):
        """Not the `!` branch: `undefined` is inside the declared type.

        The member is not declared optional, so it gets no `?:` — but its
        type says `undefined` is a legal value, so naming that value invents
        nothing and no promise is needed.
        """
        self.assertEqual(one(var("tags", "[String]?")),
                         "public tags: string[] | undefined = undefined;")

    def test_a_string_default_is_quoted(self):
        line = one(var("mode", "Visibility"))
        self.assertEqual(line, 'public mode: string = "gone";')

    def test_a_default_containing_a_quote_is_escaped(self):
        lines, _ = declare(
            var("label", "Caption"),
            type_map={"Caption": {"class": "string", "defaultValue": 'a"b'}},
        )
        self.assertEqual(lines[0], 'public label: string = "a\\"b";')


class NoSynthesizableValueIsSaidOutLoud(unittest.TestCase):
    """A custom type with no declared default: `!`, and never silently."""

    def test_the_declaration_uses_definite_assignment(self):
        self.assertEqual(one(var("profile", "UserProfile")),
                         "public profile!: UserProfile;")

    def test_a_warning_names_the_var_and_both_remedies(self):
        _, warnings = declare(var("profile", "UserProfile"))
        self.assertEqual(len(warnings), 1)
        msg = warnings[0]
        self.assertIn("profile", msg)
        self.assertIn("UserProfile", msg)
        self.assertIn("defaultValue", msg)
        self.assertIn(".jsonui-type-map.json", msg)
        self.assertIn('"optional": true', msg)

    def test_declaring_a_default_removes_both_the_bang_and_the_warning(self):
        """The remedy the warning names actually works."""
        lines, warnings = declare(
            var("profile", "UserProfile"),
            type_map={"UserProfile": {"class": "UserProfile",
                                      "defaultValue": {}}},
        )
        self.assertEqual(warnings, [])
        self.assertNotIn("!", lines[0])

    def test_the_other_remedy_works_too(self):
        lines, warnings = declare(var("profile", "UserProfile", optional=True))
        self.assertEqual(warnings, [])
        self.assertEqual(lines[0], "public profile?: UserProfile;")

    def test_a_var_that_can_be_initialized_raises_nothing(self):
        _, warnings = declare(var("a", "Bool"), var("b", "[String]"),
                              var("c", "String?"))
        self.assertEqual(warnings, [])


class CustomTypeImports(unittest.TestCase):
    MAP = {"ItemImage": {"class": "ItemImage", "imports": ["@/types/ItemImage"]}}

    def _imports(self, *vars_) -> list[str]:
        spec = ScreenSpec(name="S", display_name="", description="",
                          layout_file="s", view_model=ViewModelDef(vars=list(vars_)))
        with tempfile.TemporaryDirectory() as tmp:
            out = _gen(Path(tmp), self.MAP).generate_viewmodel_protocol(spec)
        return [ln for ln in out.splitlines() if "@/types/ItemImage" in ln]

    def test_an_optional_custom_type_imports_the_bare_identifier(self):
        """It used to import `{ ItemImage? }` — the same suffix passthrough."""
        self.assertEqual(self._imports(var("hero", "ItemImage?", optional=True)),
                         ['import { ItemImage } from "@/types/ItemImage";'])

    def test_optional_and_non_optional_share_one_import(self):
        """They produced two lines, one of them invalid."""
        self.assertEqual(
            self._imports(var("hero", "ItemImage?", optional=True),
                          var("thumb", "ItemImage")),
            ['import { ItemImage } from "@/types/ItemImage";'],
        )

    def test_a_collection_of_a_custom_type_imports_its_element(self):
        self.assertEqual(self._imports(var("shots", "[ItemImage]")),
                         ['import { ItemImage } from "@/types/ItemImage";'])


class NoOutputIsInvalidTypeScript(unittest.TestCase):
    """The two rejected shapes, generalized over the type vocabulary.

    An example test pins the spellings we thought of. These two pin the
    property tsc actually enforces, so a type added to the map later cannot
    reintroduce either defect while every example test stays green.
    """

    TYPES = [
        "String", "Int", "Double", "Bool", "Visibility", "URL", "Date",
        "String?", "Int?", "Bool?", "[String]", "[String]?", "[String?]",
        "List(Item)", "Array(Item)", "Map(String,String)", "Map(String,String)?",
        "callback", "callback(String)", "(() -> Void)?", "Data",
        "UserProfile", "UserProfile?",
    ]

    def test_no_declared_type_ends_with_a_question_mark(self):
        """TS17019 — `'?' at the end of a type is not valid TypeScript`."""
        for spec_type in self.TYPES:
            for optional in (False, True):
                with self.subTest(spec_type=spec_type, optional=optional):
                    line = one(var("v", spec_type, optional=optional))
                    declared = line.split(":", 1)[1].split("=")[0].strip()
                    self.assertFalse(
                        declared.rstrip(";").strip().endswith("?"), line)

    def test_every_non_optional_field_is_initialized_or_asserted(self):
        """TS2564 — a strict-mode property needs a value or a promise."""
        for spec_type in self.TYPES:
            with self.subTest(spec_type=spec_type):
                line = one(var("v", spec_type))
                self.assertTrue("=" in line or line.startswith("public v!:"),
                                line)

    def test_no_boxed_wrapper_type_survives_into_the_output(self):
        """`String` is a legal TS type and the wrong one.

        The first report named this as a consequence of the suffix defect.
        It was not: `Visibility` mapped to the Swift spelling with no `web`
        override, and no amount of suffix handling would have reached it.
        Nothing downstream can tell this leak from an intended mapping —
        it type-checks — so it is pinned here rather than left to eslint.
        """
        for spec_type in self.TYPES:
            with self.subTest(spec_type=spec_type):
                declared = one(var("v", spec_type)).split(":", 1)[1]
                for boxed in ("String", "Number", "Boolean", "Object"):
                    self.assertNotIn(boxed, declared)

    def test_no_canonical_spelling_survives_into_the_output(self):
        """`List(Item)` / `Array(Foo)` / `callback` are not TS type names."""
        for spec_type in self.TYPES:
            with self.subTest(spec_type=spec_type):
                declared = one(var("v", spec_type)).split(":", 1)[1]
                for spelling in ("List(", "Array(", "callback", "Void"):
                    self.assertNotIn(spelling, declared)


if __name__ == "__main__":
    unittest.main()
