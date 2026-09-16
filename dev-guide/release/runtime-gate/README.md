# The gate that RUNS the emitted branch runtime

Four releases (1.8.96 … 1.8.99) measured `swiftc -typecheck` on the emitted
`JsonuiBranchRuntime.swift` in three configurations and drove it to zero. A
consumer then ran it and 127 of 248 tests died with `signal trap`.

Type-checking and executing are **different gates**. This package is the second
one: a SwiftPM test target at `swiftLanguageMode(.v6)` with
`defaultIsolation(MainActor.self)` — the shape a consumer's unit-test target
has — into which the generator's runtime is dropped and RUN.

What it catches, by construction:

    @objc static NSURLSessionConfiguration.branchTestEphemeral()
      -> _checkExpectedExecutor -> swift_task_isCurrentExecutor
      -> dispatch_assert_queue -> SIGTRAP

The swizzled `@objc` getters are called by the ObjC runtime from whatever
thread wanted a session — a third-party SDK's background uploader, in the
consumer's case. Left at the target's default isolation they are MainActor,
and Swift 6 checks the executor on entry. Swift 5 mode only warns, which is
why the consumer's 5.0 target was green through all of it.

⚠️ The test therefore calls the swizzled getter FROM A BACKGROUND QUEUE. A
repro that only drives the harness on the main actor passes with the defect
present — measured; that was the first two versions of this file.

## Running it

    dev-guide/release/run-suites.sh          # includes this leg
    # or, standalone:
    python3 - <<'PY'
    import sys; sys.path.insert(0, "test_tools")
    from jsonui_test_cli.branch_tests import SWIFT_RUNTIME
    open("dev-guide/release/runtime-gate/Tests/RTTests/JsonuiBranchRuntime.swift", "w").write(SWIFT_RUNTIME)
    PY
    (cd dev-guide/release/runtime-gate && swift test)

`JsonuiBranchRuntime.swift` is written by the leg before it runs and is not
committed — the subject is whatever the generator emits today.
