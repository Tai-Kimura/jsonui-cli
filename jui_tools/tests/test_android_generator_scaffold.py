"""Tests for AndroidGenerator's ViewModel scaffold output.

Covers two regressions:

1. The scaffold must declare a `package` consistent with the existing
   files in the destination directory. Projects that ended up with
   ``<root>.viewmodels`` (plural) on Impl files (because the kjui_tools
   Ruby Compose builder hard-codes that path) should keep producing
   plural Impl scaffolds, not silently switch to ``<root>.viewmodel``
   (singular) when invoked from `jui generate project`.

2. ``override val data`` must declare ``StateFlow<XData>`` and initialise
   with ``_data.asStateFlow()``. The previous scaffold used
   ``override val data: XData get() = _data.value`` which is a Kotlin
   compile error against the Protocol's ``val data: StateFlow<XData>``.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.spec_extractor import ScreenSpec, VarDef, ViewModelDef
from jui_cli.core.type_mapper import TypeMapper
from jui_cli.generators.android_generator import AndroidGenerator


def _make_spec(
    name: str = "FilterSheet",
    *,
    vars: list[VarDef] | None = None,
) -> ScreenSpec:
    return ScreenSpec(
        name=name,
        display_name=name,
        description="",
        view_model=ViewModelDef(vars=vars or []),
    )


def _make_generator(root: Path, package: str = "com.example.consumer_app") -> AndroidGenerator:
    config = {"package_name": package}
    type_mapper = TypeMapper.empty() if hasattr(TypeMapper, "empty") else TypeMapper({})
    return AndroidGenerator(root=root, config=config, type_mapper=type_mapper)


class ViewModelScaffoldTypeTests(unittest.TestCase):
    """Bug 2: override val data must be StateFlow<X>, not X.

    The Bug 3 follow-up made `_data` a swappable `var` so the override is
    a custom getter (`get() = _data.asStateFlow()`) rather than a direct
    property assignment. Both forms route through StateFlow correctly,
    but the getter form is what the new scaffold emits.
    """

    def test_override_val_data_uses_state_flow_getter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gen = _make_generator(root)
            code = gen.generate_viewmodel_impl(_make_spec("FooSheet"))

            self.assertIn(
                "override val data: StateFlow<FooSheetData> get() = _data.asStateFlow()",
                code,
            )
            self.assertNotIn(
                "override val data: FooSheetData get() = _data.value",
                code,
            )

    def test_scaffold_imports_asStateFlow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gen = _make_generator(root)
            code = gen.generate_viewmodel_impl(_make_spec("FooSheet"))

            self.assertIn("import kotlinx.coroutines.flow.asStateFlow", code)


class ObservableVarProtocolTests(unittest.TestCase):
    """Bug regression: ``_var_proto_signature`` in android_generator was
    bypassing the StateFlow path baked into ``protocol_sync``. The
    Android Protocol must declare observable vars as
    ``val name: StateFlow<T>`` even when invoked through the platform-
    specific signature builder (which the Android generator passes to
    ``collect_protocol_members``)."""

    def test_observable_var_emits_state_flow_in_protocol_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gen = _make_generator(root)
            spec = _make_spec(
                "HistoryList",
                vars=[
                    VarDef(
                        name="filterSheetData",
                        type="HistoryFilterSheetData",
                        observable=True,
                    ),
                    VarDef(
                        name="counter",
                        type="Int",
                        observable=False,
                    ),
                ],
            )
            code = gen.generate_viewmodel_protocol(spec, impl_source=None)
        # Observable var → StateFlow getter.
        self.assertIn(
            "val filterSheetData: StateFlow<HistoryFilterSheetData>",
            code,
        )
        # Non-observable stays as plain `var`.
        self.assertIn("var counter: Int", code)


class ObservableVarScaffoldTests(unittest.TestCase):
    """Bug fix: ``observable: true`` vars emit Compose canonical
    ``private MutableStateFlow + override val StateFlow.asStateFlow()``
    on the Impl scaffold. The Protocol declares them as
    ``val name: StateFlow<T>`` (verified in test_protocol_sync.py)."""

    def test_observable_var_emits_state_flow_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gen = _make_generator(root)
            spec = _make_spec(
                "HistoryList",
                vars=[
                    VarDef(
                        name="filterSheetData",
                        type="HistoryFilterSheetData",
                        observable=True,
                    ),
                ],
            )
            code = gen.generate_viewmodel_impl(spec)
        self.assertIn(
            "private val _filterSheetData: MutableStateFlow<HistoryFilterSheetData>",
            code,
        )
        self.assertIn(
            "override val filterSheetData: StateFlow<HistoryFilterSheetData> "
            "= _filterSheetData.asStateFlow()",
            code,
        )

    def test_non_observable_var_emits_plain_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gen = _make_generator(root)
            spec = _make_spec(
                "Foo",
                vars=[VarDef(name="counter", type="Int", observable=False)],
            )
            code = gen.generate_viewmodel_impl(spec)
        self.assertIn("override var counter: Int", code)
        self.assertNotIn("MutableStateFlow<Int>", code)


class ViewModelScaffoldBindTests(unittest.TestCase):
    """Bug 3: stub VMs (especially modalBottomSheet sheets) need a way to
    redirect their `_data` to a parent-owned MutableStateFlow so writes
    from Generated View land in the parent VM's source-of-truth, mirroring
    iOS's SwiftUI Binding<T> semantics.

    The scaffold emits a `bind(parentFlow:)` method and makes `_data` a
    swappable `var`. The parent View calls `sheetVm.bind(parentVm.mutableXFlow)`
    once after instantiation."""

    def test_data_field_is_var_to_allow_rebind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gen = _make_generator(root)
            code = gen.generate_viewmodel_impl(_make_spec("FilterSheet"))

            self.assertIn(
                "private var _data: MutableStateFlow<FilterSheetData> = MutableStateFlow(FilterSheetData())",
                code,
            )

    def test_bind_method_is_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gen = _make_generator(root)
            code = gen.generate_viewmodel_impl(_make_spec("FilterSheet"))

            self.assertIn(
                "fun bind(parentFlow: MutableStateFlow<FilterSheetData>) {",
                code,
            )
            self.assertIn(
                "if (_data === parentFlow) return",
                code,
            )
            self.assertIn(
                "_data = parentFlow",
                code,
            )


class ViewModelScaffoldPackageDetectionTests(unittest.TestCase):
    """Bug 1: scaffold must follow whatever package convention the existing
    Impl files in the destination dir already use, not always emit the
    hard-coded ``<root>.viewmodel``."""

    def _seed_existing(self, root: Path, package_decl: str) -> None:
        vm_dir = root / "app/src/main/kotlin/com/example/consumer_app/viewmodel"
        vm_dir.mkdir(parents=True, exist_ok=True)
        (vm_dir / "ExistingViewModel.kt").write_text(
            f"package {package_decl}\n\nclass ExistingViewModel\n",
            encoding="utf-8",
        )

    def test_picks_existing_plural_package_when_repo_uses_viewmodels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_existing(root, "com.example.consumer_app.viewmodels")
            gen = _make_generator(root)

            code = gen.generate_viewmodel_impl(_make_spec("NewSheet"))
            self.assertIn("package com.example.consumer_app.viewmodels", code)
            self.assertNotIn("package com.example.consumer_app.viewmodel\n", code)

    def test_falls_back_to_plural_default_when_dir_is_empty(self):
        # Fresh project with no impls yet: default to PLURAL `viewmodels`,
        # matching what the kjui Compose builder hard-codes in every
        # `import <pkg>.viewmodels.XViewModel`. (Was singular `viewmodel`,
        # which produced impls the GeneratedView could never import.)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gen = _make_generator(root)

            code = gen.generate_viewmodel_impl(_make_spec("FreshSheet"))
            self.assertIn("package com.example.consumer_app.viewmodels", code)


class ViewModelImplDirTargetTests(unittest.TestCase):
    """Regression: kjui-generate-project-emits-singular-viewmodel-package-duplicates.

    Real consumer layout (bar): impls physically in plural ``viewmodels/``
    (package ``<pkg>.viewmodels``, what every GeneratedView imports), while
    protocols live in singular ``viewmodel/protocol/``. The old generator
    hard-coded the singular ``viewmodel/`` for impls, so `jui generate project`
    wrote a *duplicate* impl set into a dir the build never imports — diverging
    from the canonical impls and breaking ``:app:compileDevDebugKotlin``. The
    impl path + package must follow the directory that actually holds the
    impls.
    """

    _SRC = "app/src/main/kotlin/com/example/consumer_app"

    def _seed_plural_impls(self, root: Path) -> Path:
        vm_dir = root / self._SRC / "viewmodels"
        vm_dir.mkdir(parents=True, exist_ok=True)
        (vm_dir / "HomeViewModel.kt").write_text(
            "package com.example.consumer_app.viewmodels\n\nclass HomeViewModel\n",
            encoding="utf-8",
        )
        return vm_dir

    def test_impl_path_targets_existing_plural_viewmodels_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_plural_impls(root)
            gen = _make_generator(root)

            path = gen.viewmodel_impl_path("NewSheet")
            # Lands in plural viewmodels/, NOT a divergent singular viewmodel/.
            self.assertEqual(path.parent.name, "viewmodels")
            self.assertFalse(
                (root / self._SRC / "viewmodel" / "NewSheetViewModel.kt").exists()
            )

    def test_impl_package_follows_plural_dir_even_when_singular_only_holds_protocols(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_plural_impls(root)
            # Singular dir exists but only carries protocol/ (no *ViewModel.kt) —
            # exactly the bar layout that previously defeated detection.
            proto_dir = root / self._SRC / "viewmodel" / "protocol"
            proto_dir.mkdir(parents=True, exist_ok=True)
            (proto_dir / "HomeViewModelProtocol.kt").write_text(
                "package com.example.consumer_app.viewmodel.protocol\n\n"
                "interface HomeViewModelProtocol\n",
                encoding="utf-8",
            )
            gen = _make_generator(root)

            code = gen.generate_viewmodel_impl(_make_spec("NewSheet"))
            self.assertIn("package com.example.consumer_app.viewmodels", code)
            self.assertNotIn("package com.example.consumer_app.viewmodel\n", code)

    def test_honours_existing_singular_impl_dir_when_that_is_where_impls_live(self):
        # Backward-compat: a project that genuinely keeps impls in singular
        # viewmodel/ keeps getting singular scaffolds (no forced migration).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vm_dir = root / self._SRC / "viewmodel"
            vm_dir.mkdir(parents=True, exist_ok=True)
            (vm_dir / "HomeViewModel.kt").write_text(
                "package com.example.consumer_app.viewmodel\n\nclass HomeViewModel\n",
                encoding="utf-8",
            )
            gen = _make_generator(root)

            path = gen.viewmodel_impl_path("NewSheet")
            self.assertEqual(path.parent.name, "viewmodel")
            code = gen.generate_viewmodel_impl(_make_spec("NewSheet"))
            self.assertIn("package com.example.consumer_app.viewmodel\n", code)

    def test_protocol_fqn_follows_existing_protocol_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proto_dir = (
                root
                / "app/src/main/kotlin/com/example/consumer_app/viewmodel/protocol"
            )
            proto_dir.mkdir(parents=True, exist_ok=True)
            (proto_dir / "ExistingViewModelProtocol.kt").write_text(
                "package com.example.consumer_app.viewmodel.protocol\n\n"
                "interface ExistingViewModelProtocol\n",
                encoding="utf-8",
            )
            gen = _make_generator(root)

            fqn = gen.viewmodel_protocol_fqn("NewSheet")
            self.assertEqual(
                fqn,
                "com.example.consumer_app.viewmodel.protocol.NewSheetViewModelProtocol",
            )


if __name__ == "__main__":
    unittest.main()
