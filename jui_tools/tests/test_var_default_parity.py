"""One declaration, three faces: what `vars` initialize to on each platform.

A list has a zero value everywhere, so `[]` belongs in the type map rather
than in any one generator — putting it in `web_generator` alone would have
made web the loosest of the three faces, accepting a declaration the other
two still refuse. These tests hold the three faces together so a change to
one is visible as a change to all.

The Kotlin cases cover the other half: `MutableStateFlow(init ?? "null")` fed
`null` into a non-null `MutableStateFlow<T>` whenever no default resolved, and
a type-nullable-but-not-`optional` var got no initializer at all. Kotlin has
no implicit-null rule the way Swift has implicit-nil, so both were programs
Kotlin refuses to compile.

Where no value can be named at all, the three differ by necessity and not by
accident: iOS/Kotlin write a scaffold once and leave it editable, so they can
hand the decision to the author in the file; the web Base is `@generated` and
rewritten every build, so it has to say the same thing with `!` and a build
warning. That asymmetry is the point of `TheEndOfWhatCanBeSynthesized`.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.spec_extractor import VarDef
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.android_generator import AndroidGenerator
from jui_cli.generators.ios_generator import IosGenerator
from jui_cli.generators.web_generator import WebGenerator


def faces(v: VarDef) -> dict[str, str]:
    """The declaration each generator emits for the same VarDef."""
    tm = TypeMapper(None)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        web = WebGenerator(root, {}, tm)
        return {
            "ios": IosGenerator(root, {}, tm)._var_impl_declaration(v).strip(),
            "android": AndroidGenerator(root, {}, tm)
            ._var_impl_declaration(v).strip(),
            "web": web._var_base_declaration(v, "S").strip(),
        }


def var(name="v", type="String", **kw) -> VarDef:
    kw.setdefault("observable", False)
    return VarDef(name=name, type=type, **kw)


class AListHasAZeroValueOnEveryPlatform(unittest.TestCase):
    SPELLINGS = ("[Item]", "List(Item)", "Array(Item)")

    def test_all_three_spellings_initialize_on_all_three_platforms(self):
        for spelling in self.SPELLINGS:
            with self.subTest(spelling=spelling):
                f = faces(var("items", spelling))
                self.assertEqual(f["ios"], "var items: [Item] = []")
                self.assertEqual(f["android"],
                                 "override var items: List<Item> = listOf()")
                self.assertEqual(f["web"], "public items: Item[] = [];")

    def test_no_face_is_left_uninitialized(self):
        """The failure this closes: three uninitialized declarations."""
        for spelling in self.SPELLINGS:
            for face, decl in faces(var("items", spelling)).items():
                with self.subTest(spelling=spelling, face=face):
                    self.assertIn("=", decl)

    def test_an_optional_list_is_not_given_an_empty_list(self):
        """`optional: true` means absent, which is not the same as empty."""
        f = faces(var("items", "[Item]", optional=True))
        self.assertEqual(f["ios"], "var items: [Item]? = nil")
        self.assertEqual(f["android"], "override var items: List<Item>? = null")
        self.assertEqual(f["web"], "public items?: Item[];")

    def test_a_map_is_deliberately_not_covered(self):
        """Scope boundary, stated rather than left to be inferred.

        `Map(K,V)` declares no defaultValue, so it takes the same route as
        any other type that cannot be synthesized. That is a decision, not
        an oversight, and this test fails if someone quietly adds one.
        """
        f = faces(var("index", "Map(String,Item)"))
        self.assertEqual(f["ios"], "var index: [String: Item]")
        self.assertEqual(f["web"], "public index!: Record<string, Item>;")


class KotlinInitializesWhatItDeclares(unittest.TestCase):
    """Kotlin has no implicit-null rule; every property needs a value."""

    def test_an_observable_list_gets_the_empty_list_not_null(self):
        """It fed `null` into a `MutableStateFlow<List<Item>>`."""
        decl = faces(var("items", "[Item]", observable=True))["android"]
        self.assertIn("MutableStateFlow(listOf())", decl)
        self.assertNotIn("MutableStateFlow(null)", decl)

    def test_an_observable_optional_still_gets_null(self):
        decl = faces(var("profile", "UserProfile", optional=True,
                         observable=True))["android"]
        self.assertIn("MutableStateFlow<UserProfile?>", decl)
        self.assertIn("MutableStateFlow(null)", decl)

    def test_an_observable_non_null_custom_type_never_gets_null(self):
        """`MutableStateFlow<UserProfile>(null)` does not compile."""
        decl = faces(var("profile", "UserProfile", observable=True))["android"]
        self.assertNotIn("MutableStateFlow(null)", decl)
        self.assertIn("TODO(", decl)
        self.assertIn("profile", decl)

    def test_a_type_nullable_var_is_initialized_even_without_the_flag(self):
        """`"type": "[Item]?"` with `optional` unset.

        Swift gives optionals an implicit nil so iOS was quietly fine here;
        Kotlin does not, and emitted a property it refuses to compile.
        """
        f = faces(var("maybe", "[Item]?"))
        self.assertEqual(f["android"], "override var maybe: List<Item>? = null")
        self.assertEqual(f["ios"], "var maybe: [Item]?")
        self.assertEqual(f["web"],
                         "public maybe: Item[] | undefined = undefined;")


class TheEndOfWhatCanBeSynthesized(unittest.TestCase):
    """A custom type with no declared default: each face says so its own way."""

    def test_the_three_faces_of_an_unsynthesizable_type(self):
        f = faces(var("profile", "UserProfile"))
        # iOS/Kotlin: a bare declaration in a scaffold the author may edit —
        # the compiler asks them, and they can answer in place.
        self.assertEqual(f["ios"], "var profile: UserProfile")
        self.assertEqual(f["android"], "override var profile: UserProfile")
        # Web: the same question, asked where an @generated file can ask it.
        self.assertEqual(f["web"], "public profile!: UserProfile;")

    def test_only_the_web_face_raises_a_build_warning(self):
        """Because only the web face emits a promise nothing verifies."""
        tm = TypeMapper(None)
        with tempfile.TemporaryDirectory() as tmp:
            gen = WebGenerator(Path(tmp), {}, tm)
            gen._var_base_declaration(var("profile", "UserProfile"), "S")
            self.assertEqual(len(gen.warnings), 1)
            gen.warnings.clear()
            gen._var_base_declaration(var("items", "[Item]"), "S")
            self.assertEqual(gen.warnings, [])


if __name__ == "__main__":
    unittest.main()
