"""How a generated XCTestCase is declared, so it compiles under either
default actor isolation.

Two generators write Swift test classes — `generate branch-tests` and
`generate unit-stubs` — and they had drifted: branch-tests wrote the shape
below, unit-stubs a plain `final class`, and a consumer whose test target
builds with `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` fixed the declaration
by hand in every new contract-test file (30 of 30). One declaration, read by
both, so the next measurement lands in both.

A test target built with Swift 6 and `SWIFT_DEFAULT_ACTOR_ISOLATION =
MainActor` — what an app built @MainActor needs, or its tests cannot call the
app synchronously — makes a plain test class MainActor, and its IMPLICIT init
overrides then disagree with XCTestCase's nonisolated ones:

    error: main actor-isolated initializer 'init()' has different actor
    isolation from nonisolated overridden declaration   (x3 per class)

BOTH HALVES ARE LOAD-BEARING: the class `nonisolated`, each test method
`@MainActor`. Measured with swiftc 6.4 (Xcode 27.0 RC) one file per shape,
typechecked against XCTest — branch-tests' emitted file (2026-09-16), and a
unit stub with its XCTFail body and with a body that calls one method of a
type in the app's module (2026-09-25). Errors under sw6 + MainActor default
(plain sw6: 0 for every shape):

    shape                                branch test   stub   stub calling the app
    final class / func                        3           3        -
    nonisolated class / func                  3 (*)       0        1 (*)
    final class / @MainActor func             3           -        -
    nonisolated class / @MainActor func       0           0        0   <- this

    3 = the init overrides; (*) = a MainActor call from a nonisolated context

`nonisolated` on the class is harmless where the default is nonisolated, and
a MainActor method may call either kind of code.
"""
from __future__ import annotations

#: Each generated test method's isolation: its body calls the app, which is
#: MainActor wherever the app builds @MainActor.
TEST_METHOD_ISOLATION = "@MainActor"


def xctest_class_header(name: str) -> str:
    """`nonisolated final class <name>: XCTestCase {` — the opening line."""
    return f"nonisolated final class {name}: XCTestCase {{"
