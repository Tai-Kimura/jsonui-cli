"""A spec var the Impl declares with an access modifier that narrows its reader
is an ERROR, not an `override` injected after the modifier.

`list_impl_var_names` swallows access modifiers so that `private(set) var`
(Swift) and a trailing `private set` (Kotlin) count as implementing a
`readOnly` var. The pattern accepted a bare `private` too, so a plain
`private var errorMessage` counted as "in the Impl", no ERROR was raised, and
`inject_kotlin_var_override` wrote `private override var errorMessage` —
which Kotlin refuses (a public protocol member cannot be narrowed), with
`jui build` at rc 0 and nothing printed. A consumer met it at the Gradle
compile. Swift's bare `private var` does not satisfy a protocol requirement
either, and was counted the same way.

Now protocol-sync names the key, the modifier and the fix, leaves the line as
it is, and fails. The fix follows the protocol: a `readOnly` var can keep its
setter private (`override var X … private set`, `private(set) var X`; in an
open Kotlin class `final override var X … private set`, as Kotlin prohibits a
private setter on an open property); a settable one needs a public setter; Android's default observable var is a
StateFlow (`override val X: StateFlow<…>` over a private MutableStateFlow).

    Impl declaration                         android            ios
    private / protected / internal var X     ERROR              -
    private val X                            ERROR              -
    private / fileprivate var X              -                  ERROR
    override var X … private set             ok (control)       -
    private(set) var X / public private(set) -                  ok (control)
    var X                                    ok (control)       ok (control)
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.build_cmd import _sync_viewmodel_protocols
from jui_cli.core.protocol_sync import list_impl_narrowed_vars, list_impl_var_names

from tests.test_build_sync_e2e import _build_fixture_project, _load_config, _make_args

KOTLIN_IMPL = "android/app/src/main/kotlin/com/example/app/viewmodel/LoginViewModel.kt"
SWIFT_IMPL = "ios/ViewModel/LoginViewModel.swift"
KOTLIN_LINE = "    var isLoading: Boolean = false\n"
SWIFT_LINE = "    @Published var isLoading: Bool = false\n"


class NarrowedScanTests(unittest.TestCase):
    def test_kotlin_modifiers_that_narrow_the_reader(self):
        for decl, mod in (("private var isLoading: Boolean = false", "private"),
                          ("protected var isLoading: Boolean = false", "protected"),
                          ("internal var isLoading: Boolean = false", "internal"),
                          ("private val isLoading: Boolean = false", "private")):
            src = f"class A {{\n    {decl}\n}}\n"
            self.assertEqual(list_impl_narrowed_vars(src, "android"), {"isLoading": mod}, decl)
            # still counted as declared — the ERROR is its own, not "missing"
            self.assertIn("isLoading", list_impl_var_names(src), decl)

    def test_kotlin_controls(self):
        for decl in ("override var isLoading: Boolean = false\n        private set",
                     "var isLoading: Boolean = false",
                     "override val isLoading: Boolean = false"):
            self.assertEqual(list_impl_narrowed_vars(f"class A {{\n    {decl}\n}}\n", "android"), {}, decl)

    def test_swift_modifiers_that_narrow_the_reader(self):
        for decl, mod in (("private var isLoading: Bool = false", "private"),
                          ("fileprivate var isLoading: Bool = false", "fileprivate"),
                          ("@Published private var isLoading: Bool = false", "private")):
            self.assertEqual(list_impl_narrowed_vars(f"class A {{\n    {decl}\n}}\n", "ios"),
                             {"isLoading": mod}, decl)

    def test_swift_controls(self):
        for decl in ("private(set) var isLoading: Bool = false",
                     "public private(set) var isLoading: Bool = false",
                     "@Published private(set) var isLoading: Bool = false",
                     "var isLoading: Bool = false",
                     "internal var isLoading: Bool = false"):
            self.assertEqual(list_impl_narrowed_vars(f"class A {{\n    {decl}\n}}\n", "ios"), {}, decl)

    def test_a_name_also_declared_open_is_not_narrowed(self):
        src = ("class A {\n    override var isLoading: Boolean = false\n"
               "    private class Inner { private var isLoading = 0 }\n}\n")
        self.assertEqual(list_impl_narrowed_vars(src, "android"), {})


def _sync(root: Path) -> tuple[bool, str]:
    config_mgr, config = _load_config(root)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        ok = _sync_viewmodel_protocols(config_mgr, config, config["platforms"], _make_args())
    return ok, out.getvalue()


def _project(root: Path, *, kotlin: str | None = None, swift: str | None = None,
             read_only: bool = False, observable: bool | None = None) -> Path:
    _build_fixture_project(root)
    spec = root / "docs/screens/json/login.spec.json"
    data = json.loads(spec.read_text())
    if read_only:
        data["dataFlow"]["viewModel"]["vars"][0]["readOnly"] = True
    if observable is not None:
        data["dataFlow"]["viewModel"]["vars"][0]["observable"] = observable
    spec.write_text(json.dumps(data, indent=2))
    for rel, line, new in ((KOTLIN_IMPL, KOTLIN_LINE, kotlin), (SWIFT_IMPL, SWIFT_LINE, swift)):
        if new is None:
            continue
        path = root / rel
        text = path.read_text()
        assert text.count(line) == 1, rel
        path.write_text(text.replace(line, new))
    return root


class BuildSyncTests(unittest.TestCase):
    def test_kotlin_narrowed_var_is_an_error_and_the_line_is_left_alone(self):
        for mod, kw in (("private", "var"), ("protected", "var"), ("internal", "var"), ("private", "val")):
            with self.subTest(mod=mod, kw=kw), tempfile.TemporaryDirectory() as d:
                line = f"    {mod} {kw} isLoading: Boolean = false\n"
                root = _project(Path(d), kotlin=line, observable=False)
                ok, out = _sync(root)
                self.assertIs(ok, False, out)
                self.assertIn(f"dataFlow.viewModel.vars declares 'isLoading' but the Impl declares "
                              f"it `{mod}`", out)
                self.assertIn("write `override var isLoading` — the protocol declares a setter", out)
                impl = (root / KOTLIN_IMPL).read_text()
                self.assertIn(line, impl)
                self.assertNotIn(f"{mod} override", impl)

    def test_kotlin_observable_fix_names_the_state_flow(self):
        """Android's default for a settable var is observable: the protocol
        declares `val isLoading: StateFlow<Boolean>`."""
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), kotlin="    private var isLoading: Boolean = false\n")
            ok, out = _sync(root)
            self.assertIs(ok, False, out)
            self.assertIn("write `override val isLoading: StateFlow<…>` over a private MutableStateFlow", out)

    def test_kotlin_read_only_fix_keeps_the_setter_private(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), kotlin="    private var isLoading: Boolean = false\n", read_only=True)
            ok, out = _sync(root)
            self.assertIs(ok, False, out)
            self.assertIn("write `override var isLoading … private set` (or `override val isLoading`)", out)
            # `override` in an open class is open, and Kotlin prohibits a private
            # setter on an open property — the spelling that compiles there.
            self.assertIn("in an open class, `final override var isLoading … private set`, since "
                          "Kotlin prohibits a private setter on an open property", out)

    def test_control_kotlin_override_with_a_private_setter_passes(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), kotlin="    override var isLoading: Boolean = false\n        private set\n",
                            read_only=True)
            ok, out = _sync(root)
            self.assertIsNot(ok, False, out)
            self.assertNotIn("isLoading", out.split("ERROR")[-1] if "ERROR" in out else "")

    def test_swift_narrowed_var_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), swift="    @Published private var isLoading: Bool = false\n",
                            read_only=True)
            ok, out = _sync(root)
            self.assertIs(ok, False, out)
            self.assertIn("[ios]", out)
            self.assertIn("declares it `private`", out)
            self.assertIn("write `private(set) var isLoading`", out)

    def test_control_swift_private_set_passes(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d), swift="    @Published private(set) var isLoading: Bool = false\n",
                            read_only=True)
            ok, out = _sync(root)
            self.assertIsNot(ok, False, out)


if __name__ == "__main__":
    unittest.main()
