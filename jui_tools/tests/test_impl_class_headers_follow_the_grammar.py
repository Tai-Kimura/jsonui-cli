"""Protocol sync finds a ViewModel class written any way the language allows.

Ticket jui-protocol-sync-kotlin-class-header-rejects-visibility-modified-
primary-constructor (a consumer lane, 2026-09-25): `KOTLIN_CLASS_HEADER_RE` accepted
only `@Ann constructor` before a primary constructor's parameters, so
`class A internal constructor(…)` — the usual way to hand a test its own
dependencies — stopped `jui build` with "Kotlin class 'A' not found in
source". 4f reproduced it and found `class A constructor(…)` failing too.

Measured on the same regexes before the fix, the Swift side had the same
kind of hole: an attribute on the class's own line (`@MainActor final class`,
`@Observable final class`), and `package`. And a default argument nested
deeper than one call (`x: Foo = foo(bar(baz()))`) hid a Kotlin class.

Each form below must be found, get the protocol appended once, and give a
zero diff on the second pass; the boundary forms must not be read as a class
header with a primary constructor.
"""
from __future__ import annotations

import pytest

from jui_cli.core.impl_updater import ensure_kotlin_inheritance, ensure_swift_inheritance

KOTLIN_FOUND = [
    "class A @Inject constructor(x: Int) : B() {",                 # the control
    "class A(x: Int) : B() {",                                      # the control
    "class A internal constructor(x: Int) : B() {",                 # the ticket
    "class A private constructor(x: Int) : B() {",
    "class A @Inject internal constructor(x: Int) : B() {",
    "class A constructor(x: Int) : B() {",                          # 4f's
    "class A protected constructor(x: Int) : B() {",
    "class A public constructor(x: Int) : B() {",
    "class A @Inject @JvmOverloads constructor(x: Int) : B() {",
    'class A @param:Named("a") constructor(x: Int) : B() {',
    "class A @Inject internal @Suppress(\"x\") constructor(x: Int) : B() {",
    "class A(private val x: Foo = foo(bar(baz()))) : B() {",
    "@HiltViewModel class A @Inject constructor(x: Int) : B() {",
    "class A<T : Any> internal constructor(x: T) : B() {",
    ("class A internal constructor(\n    application: Application,\n    private val r: R,\n"
     ") : AndroidViewModel(application), Other {"),
]

KOTLIN_NOT_A_HEADER = [
    "class A constructorX(x: Int) : B() {",           # another word, not the keyword
    "class A internal private constructor(x: Int) : B() {",   # two visibilities
]

SWIFT_FOUND = [
    "final class AViewModel: ObservableObject {",                   # the control
    "@MainActor\nfinal class AViewModel: ObservableObject {",       # the control
    "@MainActor final class AViewModel: ObservableObject {",
    "@Observable final class AViewModel {",
    "@MainActor public final class AViewModel: ObservableObject {",
    "package final class AViewModel: ObservableObject {",
    "final public class AViewModel: ObservableObject {",
    "@objc(AVM) class AViewModel: NSObject {",
]


@pytest.mark.parametrize("header", KOTLIN_FOUND)
def test_kotlin_every_primary_constructor_form_is_found_once(header):
    source = f"package p\n\n{header}\n    fun f() {{}}\n}}\n"
    once = ensure_kotlin_inheritance(source, "A", "AProtocol")
    assert once.count("AProtocol") == 1, once
    assert ensure_kotlin_inheritance(once, "A", "AProtocol") == once
    assert "B()" in once or "AndroidViewModel(application), Other" in once


@pytest.mark.parametrize("header", KOTLIN_NOT_A_HEADER)
def test_boundary_what_is_not_a_primary_constructor_is_not_read_as_one(header):
    with pytest.raises(ValueError, match="Kotlin class 'A' not found"):
        ensure_kotlin_inheritance(f"{header}\n}}\n", "A", "AProtocol")


@pytest.mark.parametrize("header", SWIFT_FOUND)
def test_swift_every_attribute_and_modifier_form_is_found_once(header):
    source = f"import Foundation\n\n{header}\n    func f() {{}}\n}}\n"
    once = ensure_swift_inheritance(source, "AViewModel", "AViewModelProtocol")
    assert once.count("AViewModelProtocol") == 1, once
    assert ensure_swift_inheritance(once, "AViewModel", "AViewModelProtocol") == once
    assert header.split("class AViewModel")[0] in once        # attributes kept as written
