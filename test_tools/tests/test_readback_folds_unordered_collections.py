"""The VM read-back folds unordered collections and compares them as sets.

A contract writes `state.selectedIds: ["a"]`; the view model holds a `Set`.
iOS demanded `[Any]` and failed by construction, and web would have failed
the same way had a face used a JS `Set`. Kotlin looked correct — it folded
with `toList()` — but then compared BY INDEX, so it passed on the reported
screen only because the seed had one element. With two it is the set's
iteration order: insertion order for `setOf` (LinkedHashSet), unspecified for
`hashSetOf`. That is a green shaped like a pass.

So all three faces move, and the rule is the same everywhere: when the live
value is unordered, compare membership; when it is a list, keep comparing by
index. A recorded JSON body is never a Set — JSONSerialization, JSON.parse
and kotlinx JsonElement all produce arrays — so the request-body path cannot
reach the new branch.

THESE ARMS EXECUTE THE EMITTED RUNTIME. The same family has now been
reported three times (asDouble treating JSON 0/1 as Bool, object-valued
seeds, this), and each previous fix was pinned by asserting the emitted
TEXT. Text arms cannot see an ordering rule. The probes below compile the
emitted source and run it, and skip visibly where the toolchain is absent.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli.branch_tests import generate_branch_tests
from tests import _toolchain as tc

# Every arm asserts the same eight properties, so a face that disagrees with
# another shows up as a different row rather than a different test.
_EXPECTED = {
    "set1": True,                  # the reported shape: one element
    "set2-orderA": True,           # two elements, contract order
    "set2-orderB": True,           # two elements, reversed — the ordering arm
    "set-size": False,             # folded, not waved through
    "set-member": False,           # membership actually checked
    "list-order-sensitive": False,  # a list is still ordered
    "list-same-order": True,
}


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    (root / "jui.config.json").write_text(
        json.dumps({"spec_directory": "docs/specs"}), encoding="utf-8")
    spec = {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "S", "displayName": "S", "description": "d",
                     "layoutFile": "s"},
        "structure": {"components": [], "layout": {}},
        "dataFlow": {"viewModel": {"methods": [{"name": "onTap"}], "vars": []}},
        "stateManagement": {"uiVariables": []},
        "branchContracts": {"methods": {"onTap": {"branches": [
            {"when": {"data.x": True}, "then": {"api": "none"}}]}}},
    }
    p = root / "docs/specs/s.spec.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(spec), encoding="utf-8")
    return root


def _results(stdout: str) -> dict[str, bool]:
    out = {}
    for line in stdout.splitlines():
        m = re.match(r"^(PASS|FAIL) (\S+) ", line)
        if m:
            out[m.group(2)] = m.group(1) == "PASS"
    return out


def _assert_all(results: dict[str, bool], stdout: str) -> None:
    missing = set(_EXPECTED) - set(results)
    assert not missing, f"probe did not report {sorted(missing)}\n{stdout}"
    bad = [name for name, ok in results.items() if not ok]
    assert not bad, f"emitted runtime failed {bad}\n{stdout}"



def test_ios_folds_a_set_and_compares_membership(tmp_path):
    tc.tool("swiftc")
    root = _project(tmp_path)
    emitted = generate_branch_tests(
        "s", root, platform="ios", module="App",
        out_dir="Tests/Gen", harness_dir="Tests/Gen",
    ).runtime_file.read_text(encoding="utf-8")
    # Checked rather than assumed: if the emit stops importing XCTest this
    # strip becomes a silent no-op and the probe measures nothing.
    assert emitted.count("\nimport XCTest\n") == 1
    (tmp_path / "runtime.swift").write_text(
        emitted.replace("\nimport XCTest\n", "\n", 1), encoding="utf-8")
    (tmp_path / "shim.swift").write_text(
        "import Foundation\n"
        "func XCTFail(_ m: String = \"\", file: StaticString = #filePath, line: UInt = #line) {}\n"
        "func XCTAssertEqual<T: Equatable>(_ a: T, _ b: T, _ m: String = \"\",\n"
        "  file: StaticString = #filePath, line: UInt = #line) {}\n"
        "func XCTAssertEqual(_ a: Double, _ b: Double, accuracy: Double, _ m: String = \"\",\n"
        "  file: StaticString = #filePath, line: UInt = #line) {}\n", encoding="utf-8")
    (tmp_path / "main.swift").write_text('''import Foundation
func check(_ n: String, _ got: [String], _ wantEmpty: Bool) {
  print("\\((got.isEmpty == wantEmpty) ? "PASS" : "FAIL") \\(n) -> \\(got)")
}
let one: Set<String> = ["a"]
let two: Set<String> = ["a", "b"]
check("set1", partialMismatches(one, ["a"]), true)
check("set2-orderA", partialMismatches(two, ["a", "b"]), true)
check("set2-orderB", partialMismatches(two, ["b", "a"]), true)
check("set-size", partialMismatches(two, ["a"]), false)
check("set-member", partialMismatches(two, ["a", "z"]), false)
check("list-order-sensitive", partialMismatches(["a", "b"] as [Any], ["b", "a"]), false)
check("list-same-order", partialMismatches(["a", "b"] as [Any], ["a", "b"]), true)
check("nsset", partialMismatches(NSSet(array: ["a", "b"]), ["b", "a"]), true)
''', encoding="utf-8")
    binary = tmp_path / "probe"
    build = subprocess.run(
        ["swiftc", "-Onone", "-o", str(binary), str(tmp_path / "shim.swift"),
         str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
        capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, f"emitted Swift did not compile:\n{build.stderr[:4000]}"
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    results = _results(run.stdout)
    _assert_all(results, run.stdout)
    # NSSet is the other spelling a view model can hold.
    assert results.get("nsset") is True, run.stdout


def test_web_folds_a_set_and_compares_membership(tmp_path):
    tc.tool("node")
    root = _project(tmp_path)
    runtime = generate_branch_tests("s", root).runtime_file
    probe = runtime.parent / "probe.ts"
    probe.write_text(f'''import {{ partialMismatches }} from "./{runtime.name}";
function check(n: string, got: string[], wantEmpty: boolean) {{
  console.log(`${{(got.length === 0) === wantEmpty ? "PASS" : "FAIL"}} ${{n}} -> ${{JSON.stringify(got)}}`);
}}
const two = new Set(["a", "b"]);
check("set1", partialMismatches(new Set(["a"]), ["a"]), true);
check("set2-orderA", partialMismatches(two, ["a", "b"]), true);
check("set2-orderB", partialMismatches(two, ["b", "a"]), true);
check("set-size", partialMismatches(two, ["a"]), false);
check("set-member", partialMismatches(two, ["a", "z"]), false);
check("list-order-sensitive", partialMismatches(["a", "b"], ["b", "a"]), false);
check("list-same-order", partialMismatches(["a", "b"], ["a", "b"]), true);
''', encoding="utf-8")
    run = subprocess.run(
        ["node", "--experimental-strip-types", probe.name],
        cwd=probe.parent, capture_output=True, text=True, timeout=120)
    assert "PASS" in run.stdout or "FAIL" in run.stdout, (
        f"probe produced no result rows:\n{run.stdout}\n{run.stderr[:2000]}")
    _assert_all(_results(run.stdout), run.stdout)


def test_android_compares_a_set_by_membership_not_by_index(tmp_path):
    """Kotlin already folded; it compared the folded list by index.

    `hashSetOf` is in the probe deliberately: `setOf` is a LinkedHashSet and
    keeps insertion order, so a probe built only from `setOf` would agree
    with the old index comparison and report no problem.
    """
    root = _project(tmp_path)
    emitted = generate_branch_tests(
        "s", root, platform="android", package="com.example.app",
    ).runtime_file.read_text(encoding="utf-8")

    def block(sig: str) -> str:
        i = emitted.index(sig)
        return emitted[i:emitted.index("\n}\n", i) + 3]

    decls = [re.search(r"^.*\bclass Ref\b.*$", emitted, re.M).group(0),
             re.search(r"^private object NoSuchMember.*$", emitted, re.M).group(0)]
    parts = [block(s) for s in ("fun setMismatches(", "fun valueMismatches(",
                                "private fun memberValue(")]
    (tmp_path / "probe.kt").write_text(
        tc.KOTLIN_SHIM + "\n" + "\n".join(decls) + "\n\n"
        + "\n\n".join(parts) + '''

fun check(n: String, got: List<String>, wantEmpty: Boolean) {
  println((if (got.isEmpty() == wantEmpty) "PASS" else "FAIL") + " " + n + " -> " + got)
}
fun main() {
  val two: Set<String> = setOf("a", "b")
  val hashTwo: Set<String> = hashSetOf("a", "b")
  check("set1", valueMismatches(setOf("a"), listOf("a")), true)
  check("set2-orderA", valueMismatches(two, listOf("a", "b")), true)
  check("set2-orderB", valueMismatches(two, listOf("b", "a")), true)
  check("hashset-orderB", valueMismatches(hashTwo, listOf("b", "a")), true)
  check("set-size", valueMismatches(two, listOf("a")), false)
  check("set-member", valueMismatches(two, listOf("a", "z")), false)
  check("list-order-sensitive", valueMismatches(listOf("a", "b"), listOf("b", "a")), false)
  check("list-same-order", valueMismatches(listOf("a", "b"), listOf("a", "b")), true)
}
''', encoding="utf-8")

    run = tc.compile_and_run_kotlin(
        tmp_path, (tmp_path / "probe.kt").read_text(encoding="utf-8"))
    results = _results(run.stdout)
    _assert_all(results, run.stdout)
    assert results.get("hashset-orderB") is True, run.stdout


def test_the_request_body_path_is_untouched(tmp_path):
    """The widening must not reach JSON-body matching.

    A body arrives as parsed JSON — arrays, never a Set — so the new branch
    is unreachable there by construction. This pins the construction: Kotlin
    keeps two comparators and only the read-back one learned about sets.
    """
    root = _project(tmp_path)
    android = generate_branch_tests(
        "s", root, platform="android", package="com.example.app",
    ).runtime_file.read_text(encoding="utf-8")

    i = android.index("fun partialMismatches(actual: JsonElement?")
    body_matcher = android[i:android.index("\n}\n", i)]
    assert "setMismatches" not in body_matcher
    assert "is Set<*>" not in body_matcher
    # ...and it still compares arrays by index.
    assert "exp.indices.flatMap" in body_matcher
