"""A spec method the Impl declares with a modifier that narrows its reader is
an ERROR, not an `override` injected after the modifier — the methods' side of
test_protocol_sync_narrowed_vars.py.

`list_impl_method_names` swallows access modifiers, so `private fun onLogin()`
counted as implementing `onLogin`, no ERROR was raised, and
`inject_kotlin_override` wrote `private override fun onLogin()` — which
Kotlin refuses — with `jui build` at rc 0. Swift's `private func` /
`fileprivate func` meet no protocol requirement and were counted the same
way. Now protocol-sync names the method, the modifier and the fix, leaves the
line as it is, and fails.

    Impl declaration                         android      ios
    private / protected / internal fun X     ERROR        -
    private / fileprivate func X             -            ERROR
    fun X / override fun X / suspend fun X   ok           -
    func X / internal func X / @MainActor    -            ok
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.core.protocol_sync import list_impl_method_names, list_impl_narrowed_methods

from tests.test_build_sync_e2e import _build_fixture_project
from tests.test_protocol_sync_narrowed_vars import KOTLIN_IMPL, SWIFT_IMPL, _sync

KOTLIN_LINE = "    fun onLogin() {}\n"
SWIFT_LINE = "    func onLogin() {}\n"


class NarrowedMethodScanTests(unittest.TestCase):
    def test_kotlin_modifiers_that_narrow_the_reader(self):
        for mod in ("private", "protected", "internal"):
            src = f"class A {{\n    {mod} fun onLogin() {{}}\n}}\n"
            self.assertEqual(list_impl_narrowed_methods(src, "android"), {"onLogin": mod}, mod)
            self.assertIn("onLogin", list_impl_method_names(src), mod)   # present, so not "missing"

    def test_kotlin_controls(self):
        for decl in ("fun onLogin() {}", "override fun onLogin() {}", "suspend fun onLogin() {}",
                     "override suspend fun onLogin() {}", "open fun onLogin() {}"):
            self.assertEqual(list_impl_narrowed_methods(f"class A {{\n    {decl}\n}}\n", "android"), {}, decl)

    def test_swift_modifiers_that_narrow_the_reader(self):
        for decl, mod in (("private func onLogin() {}", "private"),
                          ("fileprivate func onLogin() {}", "fileprivate"),
                          ("@MainActor private func onLogin() {}", "private")):
            self.assertEqual(list_impl_narrowed_methods(f"class A {{\n    {decl}\n}}\n", "ios"),
                             {"onLogin": mod}, decl)

    def test_swift_controls(self):
        for decl in ("func onLogin() {}", "internal func onLogin() {}", "@MainActor func onLogin() {}",
                     "public func onLogin() {}", "nonisolated func onLogin() {}"):
            self.assertEqual(list_impl_narrowed_methods(f"class A {{\n    {decl}\n}}\n", "ios"), {}, decl)

    def test_an_overload_declared_open_is_not_narrowed(self):
        src = "class A {\n    func onLogin() {}\n    private func onLogin(_ x: Int) {}\n}\n"
        self.assertEqual(list_impl_narrowed_methods(src, "ios"), {})


def _project(root: Path, *, kotlin: str | None = None, swift: str | None = None) -> Path:
    _build_fixture_project(root)
    for rel, line, new in ((KOTLIN_IMPL, KOTLIN_LINE, kotlin), (SWIFT_IMPL, SWIFT_LINE, swift)):
        if new is None:
            continue
        path = root / rel
        text = path.read_text()
        assert text.count(line) == 1, rel
        path.write_text(text.replace(line, new))
    return root


class NarrowedMethodBuildSyncTests(unittest.TestCase):
    def test_kotlin_narrowed_method_is_an_error_and_the_line_is_left_alone(self):
        for mod in ("private", "protected", "internal"):
            with self.subTest(mod=mod), tempfile.TemporaryDirectory() as d:
                line = f"    {mod} fun onLogin() {{}}\n"
                root = _project(Path(d), kotlin=line)
                ok, out = _sync(root)
                self.assertIs(ok, False, out)
                self.assertIn(f"dataFlow.viewModel.methods declares 'onLogin' but the Impl declares "
                              f"it `{mod}` — a protocol member cannot be narrowed; write "
                              f"`override fun onLogin(…)`.", out)
                impl = (root / KOTLIN_IMPL).read_text()
                self.assertIn(line, impl)
                self.assertNotIn(f"{mod} override", impl)
                self.assertIn("override fun onCancel()", impl)     # the other method still gets it

    def test_swift_narrowed_method_is_an_error(self):
        for mod in ("private", "fileprivate"):
            with self.subTest(mod=mod), tempfile.TemporaryDirectory() as d:
                root = _project(Path(d), swift=f"    {mod} func onLogin() {{}}\n")
                ok, out = _sync(root)
                self.assertIs(ok, False, out)
                self.assertIn(f"[ios]", out)
                self.assertIn(f"declares it `{mod}` — a protocol member cannot be narrowed; write "
                              f"`func onLogin(…)` (internal, as the protocol is).", out)

    def test_control_plain_declarations_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root = _project(Path(d))
            ok, out = _sync(root)
            self.assertIsNot(ok, False, out)
            self.assertIn("override fun onLogin()", (root / KOTLIN_IMPL).read_text())


if __name__ == "__main__":
    unittest.main()
