"""Tests for spec.view_model (methods + vars) merging with Impl markers."""
from __future__ import annotations

import unittest

from jui_cli.core.protocol_sync import (
    collect_protocol_members,
    default_method_signature,
    default_var_signature,
    list_impl_method_names,
    list_impl_var_names,
)
from jui_cli.core.spec_extractor import (
    MethodDef, MethodParam, ScreenSpec, VarDef, ViewModelDef,
)
from jui_cli.core.spec_validator import (
    SpecValidationError,
    validate_screen_spec,
)


def _spec(**kwargs) -> ScreenSpec:
    return ScreenSpec(
        name=kwargs.pop("name", "Foo"),
        display_name=kwargs.pop("display_name", "Foo"),
        description=kwargs.pop("description", ""),
        **kwargs,
    )


class DefaultSignatureTests(unittest.TestCase):
    def test_method_sync(self):
        m = MethodDef(name="onTap", is_async=False)
        self.assertEqual(default_method_signature(m, platform="ios"), "func onTap()")
        self.assertEqual(default_method_signature(m, platform="android"), "fun onTap()")
        self.assertEqual(default_method_signature(m, platform="web"), "onTap(): void")

    def test_method_async(self):
        m = MethodDef(
            name="fetch",
            params=[MethodParam(name="id", type="String")],
            return_type="Bool",
            is_async=True,
        )
        self.assertEqual(
            default_method_signature(m, platform="ios"),
            "func fetch(id: String) async throws -> Bool",
        )
        self.assertEqual(
            default_method_signature(m, platform="android"),
            "suspend fun fetch(id: String): Bool",
        )

    def test_var_observable_default_android_emits_state_flow(self):
        """``observable: true`` is the default — Android Protocol must
        declare the var as ``val StateFlow<T>`` so the Compose canonical
        ``override val ... = _x.asStateFlow()`` Impl can override it.
        iOS / Web are unaffected (Combine ``@Published var`` /
        framework-specific reactive)."""
        v = VarDef(name="isLoading", type="Bool")
        self.assertEqual(
            default_var_signature(v, platform="ios"),
            "var isLoading: Bool { get set }",
        )
        self.assertEqual(
            default_var_signature(v, platform="android"),
            "val isLoading: StateFlow<Bool>",
        )
        self.assertEqual(default_var_signature(v, platform="web"), "isLoading: Bool")

    def test_var_non_observable_android_emits_plain_var(self):
        v = VarDef(name="counter", type="Int", observable=False)
        self.assertEqual(
            default_var_signature(v, platform="android"),
            "var counter: Int",
        )
        # iOS still requires { get set } regardless of observable flag.
        self.assertEqual(
            default_var_signature(v, platform="ios"),
            "var counter: Int { get set }",
        )

    def test_var_read_only(self):
        v = VarDef(name="staticLabel", type="String", read_only=True)
        self.assertIn("{ get }", default_var_signature(v, platform="ios"))
        # read_only short-circuits the observable path → plain ``val``.
        self.assertEqual(default_var_signature(v, platform="android"), "val staticLabel: String")
        self.assertTrue(default_var_signature(v, platform="web").startswith("readonly "))

    def test_var_optional_closure(self):
        v = VarDef(name="onDismiss", type="() -> Void", optional=True, observable=False)
        self.assertIn("(() -> Void)?", default_var_signature(v, platform="ios"))
        self.assertIn("(() -> Void)?", default_var_signature(v, platform="android"))


class PlatformFilterTests(unittest.TestCase):
    def test_method_omitted_goes_everywhere(self):
        spec = _spec(view_model=ViewModelDef(methods=[MethodDef(name="onLogin", is_async=False)]))
        for platform in ("ios", "android", "web"):
            result = collect_protocol_members(spec, platform=platform, impl_source=None)
            self.assertEqual([m.name for m in result.methods], ["onLogin"])

    def test_var_platform_filter(self):
        spec = _spec(view_model=ViewModelDef(vars=[
            VarDef(name="iosOnly", type="Int", platforms=["ios"]),
            VarDef(name="shared", type="Bool"),
        ]))
        r_ios = collect_protocol_members(spec, platform="ios", impl_source=None)
        r_android = collect_protocol_members(spec, platform="android", impl_source=None)
        self.assertEqual([v.name for v in r_ios.vars], ["iosOnly", "shared"])
        self.assertEqual([v.name for v in r_android.vars], ["shared"])


class MarkerMergeTests(unittest.TestCase):
    def test_method_marker_wins(self):
        spec = _spec(view_model=ViewModelDef(methods=[MethodDef(name="onLogin", is_async=False)]))
        impl = """class Foo {
    // @jui:protocol func onLogin() async throws
    func onLogin() async throws {}
}
"""
        result = collect_protocol_members(spec, platform="ios", impl_source=impl)
        self.assertEqual(len(result.methods), 1)
        self.assertEqual(result.methods[0].signature, "func onLogin() async throws")
        self.assertEqual(result.method_override_conflicts, ["onLogin"])

    def test_var_marker_only(self):
        spec = _spec(view_model=ViewModelDef())
        impl = """class Foo {
    // @jui:protocol var selectedIndex: Int { get set }
    @Published var selectedIndex: Int = 0
}
"""
        result = collect_protocol_members(spec, platform="ios", impl_source=impl)
        self.assertEqual(len(result.vars), 1)
        self.assertEqual(result.vars[0].name, "selectedIndex")
        self.assertEqual(result.vars[0].source, "marker")

    def test_method_and_var_extraction_from_same_impl(self):
        spec = _spec(view_model=ViewModelDef())
        impl = """class Foo {
    // @jui:protocol func fetchUser() async throws -> User
    func fetchUser() async throws -> User { fatalError() }

    // @jui:protocol var onDismiss: (() -> Void)? { get set }
    var onDismiss: (() -> Void)?
}
"""
        result = collect_protocol_members(spec, platform="ios", impl_source=impl)
        self.assertEqual([m.name for m in result.methods], ["fetchUser"])
        self.assertEqual([v.name for v in result.vars], ["onDismiss"])


class MissingInImplTests(unittest.TestCase):
    def test_method_missing(self):
        spec = _spec(view_model=ViewModelDef(
            methods=[MethodDef(name="onLogin", is_async=False), MethodDef(name="onCancel", is_async=False)]
        ))
        impl = "class Foo {\n    func onLogin() {}\n}\n"
        result = collect_protocol_members(
            spec, platform="ios", impl_source=impl,
            impl_method_names=list_impl_method_names(impl),
        )
        self.assertIn("onCancel", result.missing_methods_in_impl)
        self.assertNotIn("onLogin", result.missing_methods_in_impl)

    def test_var_missing(self):
        spec = _spec(view_model=ViewModelDef(
            vars=[VarDef(name="isLoading", type="Bool"), VarDef(name="ghost", type="String")]
        ))
        impl = "class Foo {\n    @Published var isLoading: Bool = false\n}\n"
        result = collect_protocol_members(
            spec, platform="ios", impl_source=impl,
            impl_var_names=list_impl_var_names(impl),
        )
        self.assertIn("ghost", result.missing_vars_in_impl)
        self.assertNotIn("isLoading", result.missing_vars_in_impl)


class AnnotationSuffixValidatorTests(unittest.TestCase):
    def test_ui_variable_with_computed_annotation(self):
        from jui_cli.core.spec_extractor import UIVariableDef
        spec = _spec(
            ui_variables=[UIVariableDef(name="x", type="Bool (computed)")]
        )
        with self.assertRaises(SpecValidationError) as ctx:
            validate_screen_spec(spec)
        self.assertIn("computed", str(ctx.exception).lower())

    def test_view_model_var_with_localized_annotation(self):
        from jui_cli.core.spec_extractor import VarDef
        spec = _spec(view_model=type(_spec().view_model)(
            vars=[VarDef(name="x", type="String (localized)")],
        ))
        with self.assertRaises(SpecValidationError):
            validate_screen_spec(spec)

    def test_view_model_method_param_annotation(self):
        from jui_cli.core.spec_extractor import MethodParam
        spec = _spec(view_model=type(_spec().view_model)(
            methods=[MethodDef(
                name="foo",
                params=[MethodParam(name="x", type="Bool (computed)")],
            )],
        ))
        with self.assertRaises(SpecValidationError):
            validate_screen_spec(spec)

    def test_generic_paren_is_fine(self):
        """`Map(String, String)` must NOT be flagged — generics are allowed."""
        from jui_cli.core.spec_extractor import VarDef
        spec = _spec(view_model=type(_spec().view_model)(
            vars=[VarDef(name="m", type="Map(String, String)")],
        ))
        self.assertEqual(validate_screen_spec(spec), [])


class SpecValidatorTests(unittest.TestCase):
    def test_invalid_var_platform(self):
        spec = _spec(view_model=ViewModelDef(
            vars=[VarDef(name="bad", type="Bool", platforms=["mac"])]
        ))
        with self.assertRaises(SpecValidationError):
            validate_screen_spec(spec)

    def test_empty_var_platforms_warns(self):
        spec = _spec(view_model=ViewModelDef(
            vars=[VarDef(name="x", type="Bool", platforms=[])]
        ))
        warnings = validate_screen_spec(spec)
        self.assertEqual(len(warnings), 1)

    def test_duplicate_var_name(self):
        spec = _spec(view_model=ViewModelDef(
            vars=[VarDef(name="x", type="Bool"), VarDef(name="x", type="Int")]
        ))
        with self.assertRaises(SpecValidationError):
            validate_screen_spec(spec)

    def test_duplicate_method_name(self):
        spec = _spec(view_model=ViewModelDef(
            methods=[MethodDef(name="foo"), MethodDef(name="foo")]
        ))
        with self.assertRaises(SpecValidationError):
            validate_screen_spec(spec)


class SpecParserTests(unittest.TestCase):
    def test_vars_and_methods_round_trip(self):
        from jui_cli.core.spec_extractor import extract_screen_spec
        spec_data = {
            "metadata": {"name": "Login"},
            "dataFlow": {
                "viewModel": {
                    "methods": [
                        {"name": "onLogin"},
                        {"name": "fetchProducts", "returnType": "Array(Product)", "isAsync": True},
                    ],
                    "vars": [
                        {"name": "isLoading", "type": "Bool"},
                        {"name": "onDismiss", "type": "() -> Void", "optional": True},
                        {"name": "staticLabel", "type": "String", "readOnly": True, "observable": False},
                    ],
                }
            },
        }
        ss = extract_screen_spec(spec_data)
        self.assertEqual([m.name for m in ss.view_model.methods], ["onLogin", "fetchProducts"])
        # ViewModel methods default to sync
        self.assertFalse(ss.view_model.methods[0].is_async)
        # Explicit isAsync: true is respected
        self.assertTrue(ss.view_model.methods[1].is_async)
        self.assertEqual([v.name for v in ss.view_model.vars], ["isLoading", "onDismiss", "staticLabel"])
        self.assertTrue(ss.view_model.vars[1].optional)
        self.assertTrue(ss.view_model.vars[2].read_only)
        self.assertFalse(ss.view_model.vars[2].observable)


if __name__ == "__main__":
    unittest.main()
