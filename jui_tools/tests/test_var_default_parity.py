"""One declaration, two faces: what `vars` initialize to on each platform.

A list has a zero value on both, so `[]` belongs in the type map rather than
in either generator. These tests hold the faces together so a change to one
is visible as a change to the other.

The Kotlin cases cover the other half: `MutableStateFlow(init ?? "null")` fed
`null` into a non-null `MutableStateFlow<T>` whenever no default resolved, and
a type-nullable-but-not-`optional` var got no initializer at all. Kotlin has
no implicit-null rule the way Swift has implicit-nil, so both were programs
Kotlin refuses to compile.

Web is deliberately absent. It had a third face here — `!` plus a build
warning, because its Base was `@generated` and could not hand the decision to
an author the way an editable scaffold can. That whole path is gone:
rjui_tools owns the web ViewModelBase, so jui_tools no longer emits web var
declarations at all. See `test_web_viewmodel_base_ownership.py`.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.spec_extractor import VarDef
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.android_generator import AndroidGenerator
from jui_cli.generators.ios_generator import IosGenerator


def faces(v: VarDef) -> dict[str, str]:
    """The declaration each generator emits for the same VarDef."""
    tm = TypeMapper(None)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        return {
            "ios": IosGenerator(root, {}, tm)._var_impl_declaration(v).strip(),
            "android": AndroidGenerator(root, {}, tm)
            ._var_impl_declaration(v).strip(),
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

    def test_a_map_is_deliberately_not_covered(self):
        """Scope boundary, stated rather than left to be inferred.

        `Map(K,V)` declares no defaultValue, so it takes the same route as
        any other type that cannot be synthesized. That is a decision, not
        an oversight, and this test fails if someone quietly adds one.
        """
        f = faces(var("index", "Map(String,Item)"))
        self.assertEqual(f["ios"], "var index: [String: Item]")
        self.assertEqual(f["android"], "override var index: Map<String, Item>")


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


class TheEndOfWhatCanBeSynthesized(unittest.TestCase):
    """A custom type with no declared default: a bare declaration.

    Both faces emit one and let the compiler ask the author, which works
    because both files are scaffolds written once and editable afterwards.
    """

    def test_neither_face_invents_a_value(self):
        f = faces(var("profile", "UserProfile"))
        self.assertEqual(f["ios"], "var profile: UserProfile")
        self.assertEqual(f["android"], "override var profile: UserProfile")


if __name__ == "__main__":
    unittest.main()
