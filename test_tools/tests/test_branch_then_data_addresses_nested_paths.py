"""`then data.<a>.<b>` reads a value inside a nested data structure.

A screen whose Data holds a nested struct — a sheet's own error state — had
no way to state the value the contract is about, so consumers pinned a
neighbouring flag instead and the guarantee never reached the observable
surface.

THE READ SIDE ONLY. `when`, `witness_*` and `'@data.<f>'` stay flat: they
are arranged, not read back, and a dotted name reaching `setState` is
dropped WITHOUT AN ERROR (Kotlin looks the key up by field and then by
`copy` parameter name; Swift's is a hand-written closed map). The validator
refuses those rather than letting a contract pass having arranged nothing.

THESE ARMS EXECUTE THE GENERATED ASSERT against the generated runtime. The
lines are lifted out of the emitted test file and run, so the arm covers the
generator's choice of comparator — Kotlin's `valueMismatches`, NOT its
`partialMismatches`, which takes a JsonElement and is the request-body
comparator — and not only the comparator's own behaviour.

The message text differs per face (Kotlin says "no such property on X"
where Swift says "expected …, got nil"), so every arm checks the VERDICT.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jsonui_test_cli.branch_tests import generate_branch_tests
from tests import _toolchain as tc

_JAVA = Path("/opt/homebrew/opt/openjdk@17/bin/java")

# One row per probe case, on every face. A face that disagrees with another
# shows up as a different row rather than as a different test.
_EXPECTED = {
    "nested-match": True,          # the reported shape
    "nested-mismatch": False,
    "two-level-match": True,
    "two-level-mismatch": False,
    "wrong-spelling": False,       # a typo'd path must not pass in silence
    "nil-intermediate": False,
    "absent-head": False,          # readField found nothing
    "sibling-untouched": True,     # partial, not exact
}


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "docs/specs").mkdir(parents=True, exist_ok=True)
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
            {"when": {"data.x": True},
             "then": {"data.sheet.errorVisibility": "visible",
                      "data.sheet.inner.leaf": "x"}},
        ]}}},
    }
    (root / "docs/specs/s.spec.json").write_text(
        json.dumps(spec), encoding="utf-8")
    return root


def _asserts(source: str) -> list[str]:
    """The generated lines that read a field back — what this fix changes."""
    lines = [l.strip() for l in source.splitlines() if "readField(" in l]
    assert len(lines) == 2, f"expected two read-back asserts, got {lines}"
    assert all('readField("sheet")' in l for l in lines), lines
    return lines


def _results(stdout: str) -> dict[str, bool]:
    out = {}
    for line in stdout.splitlines():
        m = re.match(r"^(PASS|FAIL) (\S+)", line)
        if m:
            out[m.group(2)] = m.group(1) == "PASS"
    return out


def _assert_all(results: dict[str, bool], stdout: str) -> None:
    missing = set(_EXPECTED) - set(results)
    assert not missing, f"probe did not report {sorted(missing)}\n{stdout}"
    bad = [n for n, ok in results.items() if not ok]
    assert not bad, f"generated assert behaved wrongly for {bad}\n{stdout}"


# --------------------------------------------------------------------------
# Generation shape — runs everywhere, names what the toolchain arms execute.
# --------------------------------------------------------------------------

def test_the_dotted_key_reads_the_head_and_compares_the_tail(tmp_path):
    root = _project(tmp_path)
    ts = generate_branch_tests("s", root).test_file.read_text(encoding="utf-8")
    kt = generate_branch_tests(
        "s", root, platform="android", package="com.example.app",
    ).test_file.read_text(encoding="utf-8")
    sw = generate_branch_tests(
        "s", root, platform="ios", module="App",
        out_dir="Tests/Gen", harness_dir="Tests/Gen",
    ).test_file.read_text(encoding="utf-8")

    for source in (ts, kt, sw):
        # The read is of the HEAD: the harnesses resolve a flat name by
        # reflection and know nothing about paths.
        assert 'readField("sheet")' in source
        assert 'readField("sheet.errorVisibility")' not in source
    assert 'partialMismatches(h.readField("sheet")' in ts
    assert 'partialMismatches(h.readField("sheet")' in sw
    # Kotlin has TWO comparators and only one of them takes a live object.
    assert 'valueMismatches(h.readField("sheet")' in kt
    assert "partialMismatches(h.readField" not in kt


def test_a_flat_key_is_emitted_exactly_as_before(tmp_path):
    """The population this change is not for: no existing generated file
    moves, so no face needs a regeneration to accept this."""
    root = _project(tmp_path)
    spec = json.loads((root / "docs/specs/s.spec.json").read_text())
    spec["branchContracts"]["methods"]["onTap"]["branches"][0]["then"] = {
        "data.errorVisibility": "visible"}
    (root / "docs/specs/s.spec.json").write_text(json.dumps(spec))

    ts = generate_branch_tests("s", root).test_file.read_text(encoding="utf-8")
    kt = generate_branch_tests(
        "s", root, platform="android", package="com.example.app",
    ).test_file.read_text(encoding="utf-8")
    sw = generate_branch_tests(
        "s", root, platform="ios", module="App",
        out_dir="Tests/Gen", harness_dir="Tests/Gen",
    ).test_file.read_text(encoding="utf-8")

    assert 'expect(h.readField("errorVisibility")).toEqual("visible");' in ts
    assert 'assertFieldEquals("visible", h.readField("errorVisibility"))' in kt
    assert 'assertFieldEquals("visible", h.readField("errorVisibility"))' in sw
    for source in (ts, kt, sw):
        assert "Mismatches(h.readField" not in source


# --------------------------------------------------------------------------
# Executing arms
# --------------------------------------------------------------------------

def test_web_runs_the_generated_nested_assert(tmp_path):
    tc.tool("node")
    root = _project(tmp_path)
    result = generate_branch_tests("s", root)
    runtime = result.runtime_file
    first, second = _asserts(result.test_file.read_text(encoding="utf-8"))

    cases = {
        "nested-match": ('{ errorVisibility: "visible", sibling: 1 }', first),
        "nested-mismatch": ('{ errorVisibility: "gone" }', first),
        "two-level-match": ('{ inner: { leaf: "x" } }', second),
        "two-level-mismatch": ('{ inner: { leaf: "y" } }', second),
        "wrong-spelling": ('{ errorVisibilty: "visible" }', first),
        "nil-intermediate": ("{ inner: null }", second),
        "absent-head": ("undefined", first),
        "sibling-untouched": ('{ errorVisibility: "visible", other: 9 }', first),
    }
    body = "\n".join(
        f'  run("{name}", {value}, (h) => {{ {line} }});' for name, (value, line) in cases.items()
    )
    probe = runtime.parent / "probe.ts"
    probe.write_text(f'''import {{ partialMismatches }} from "./{runtime.name}";
let ok = true;
function expect(actual: unknown) {{
  return {{ toEqual(want: unknown) {{
    if (JSON.stringify(actual) !== JSON.stringify(want)) ok = false;
  }} }};
}}
function run(name: string, value: unknown, arm: (h: any) => void) {{
  ok = true;
  arm({{ readField: (_n: string) => value }});
  console.log(`${{ok ? "PASS" : "FAIL"}} ${{name}}`);
}}
{body}
''', encoding="utf-8")
    # `expect(...).toEqual([])` is shadowed by the local `expect` above, so
    # the arm records instead of throwing — but the EXPRESSION under test is
    # the generated one, verbatim.
    run = subprocess.run(["node", "--experimental-strip-types", probe.name],
                         cwd=probe.parent, capture_output=True, text=True,
                         timeout=120)
    assert "PASS" in run.stdout or "FAIL" in run.stdout, (
        f"probe produced no rows:\n{run.stdout}\n{run.stderr[:2000]}")
    inverted = {n: (v if _EXPECTED[n] else not v)
                for n, v in _results(run.stdout).items()}
    _assert_all(inverted, run.stdout)


def test_ios_runs_the_generated_nested_assert(tmp_path):
    tc.tool("swiftc")
    root = _project(tmp_path)
    result = generate_branch_tests(
        "s", root, platform="ios", module="App",
        out_dir="Tests/Gen", harness_dir="Tests/Gen")
    emitted = result.runtime_file.read_text(encoding="utf-8")
    assert emitted.count("\nimport XCTest\n") == 1
    (tmp_path / "runtime.swift").write_text(
        emitted.replace("\nimport XCTest\n", "\n", 1), encoding="utf-8")
    first, second = _asserts(result.test_file.read_text(encoding="utf-8"))

    # The recording overload is more specific than the generic one the
    # runtime's own assertFieldEquals resolves to, so both coexist.
    (tmp_path / "shim.swift").write_text('''import Foundation
var ok = true
func XCTFail(_ m: String = "", file: StaticString = #filePath, line: UInt = #line) {}
func XCTAssertEqual<T: Equatable>(_ a: T, _ b: T, _ m: String = "",
  file: StaticString = #filePath, line: UInt = #line) {}
func XCTAssertEqual(_ a: Double, _ b: Double, accuracy: Double, _ m: String = "",
  file: StaticString = #filePath, line: UInt = #line) {}
func XCTAssertEqual(_ a: [String], _ b: [String], _ m: String = "",
  file: StaticString = #filePath, line: UInt = #line) { if a != b { ok = false } }
struct Leaf { var leaf: String }
struct Sheet { var errorVisibility: String; var sibling: Int }
struct SheetTypo { var errorVisibilty: String }
struct Deep { var inner: Leaf }
struct DeepNil { var inner: Leaf? }
struct H { let value: Any?
  func readField(_ name: String) -> Any? { value } }
func run(_ name: String, _ h: H, _ arm: (H) -> Void) {
  ok = true; arm(h); print((ok ? "PASS " : "FAIL ") + name)
}
''', encoding="utf-8")

    cases = [
        ("nested-match", 'Sheet(errorVisibility: "visible", sibling: 1)', first),
        ("nested-mismatch", 'Sheet(errorVisibility: "gone", sibling: 1)', first),
        ("two-level-match", 'Deep(inner: Leaf(leaf: "x"))', second),
        ("two-level-mismatch", 'Deep(inner: Leaf(leaf: "y"))', second),
        ("wrong-spelling", 'SheetTypo(errorVisibilty: "visible")', first),
        ("nil-intermediate", "DeepNil(inner: nil)", second),
        ("absent-head", "nil", first),
        ("sibling-untouched", 'Sheet(errorVisibility: "visible", sibling: 9)', first),
    ]
    body = "\n".join(
        f'run("{name}", H(value: {value})) {{ h in {line} }}'
        for name, value, line in cases)
    (tmp_path / "main.swift").write_text("import Foundation\n" + body + "\n",
                                         encoding="utf-8")
    binary = tmp_path / "probe"
    build = subprocess.run(
        ["swiftc", "-Onone", "-o", str(binary), str(tmp_path / "shim.swift"),
         str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
        capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, (
        f"generated Swift did not compile:\n{build.stderr[:4000]}")
    run = subprocess.run([str(binary)], capture_output=True, text=True,
                         timeout=120)
    inverted = {n: (v if _EXPECTED[n] else not v)
                for n, v in _results(run.stdout).items()}
    _assert_all(inverted, run.stdout)


def test_android_runs_the_generated_nested_assert(tmp_path):
    root = _project(tmp_path)
    result = generate_branch_tests(
        "s", root, platform="android", package="com.example.app")
    emitted = result.runtime_file.read_text(encoding="utf-8")
    first, second = _asserts(result.test_file.read_text(encoding="utf-8"))

    def block(sig: str) -> str:
        i = emitted.index(sig)
        return emitted[i:emitted.index("\n}\n", i) + 3]

    decls = [re.search(r"^.*\bclass Ref\b.*$", emitted, re.M).group(0),
             re.search(r"^private object NoSuchMember.*$", emitted, re.M).group(0)]
    parts = [block(s) for s in ("fun setMismatches(", "fun valueMismatches(",
                                "private fun memberValue(")]
    cases = [
        ("nested-match", 'Sheet("visible", 1)', first),
        ("nested-mismatch", 'Sheet("gone", 1)', first),
        ("two-level-match", 'Deep(Leaf("x"))', second),
        ("two-level-mismatch", 'Deep(Leaf("y"))', second),
        ("wrong-spelling", 'SheetTypo("visible")', first),
        ("nil-intermediate", "DeepNil(null)", second),
        ("absent-head", "null", first),
        ("sibling-untouched", 'Sheet("visible", 9)', first),
    ]
    body = "\n".join(
        f'  run("{name}", {value}) {{ h -> {line} }}' for name, value, line in cases)
    (tmp_path / "probe.kt").write_text(
        tc.KOTLIN_SHIM + "\n" + "\n".join(decls) + "\n\n"
        + "\n\n".join(parts) + f'''

var ok = true
fun assertEquals(expected: Any?, actual: Any?) {{ if (expected != actual) ok = false }}
data class Leaf(val leaf: String)
data class Sheet(val errorVisibility: String, val sibling: Int)
data class SheetTypo(val errorVisibilty: String)
data class Deep(val inner: Leaf)
data class DeepNil(val inner: Leaf?)
class H(val value: Any?) {{ fun readField(name: String): Any? = value }}
fun run(name: String, value: Any?, arm: (H) -> Unit) {{
  ok = true; arm(H(value)); println((if (ok) "PASS " else "FAIL ") + name)
}}
fun main() {{
{body}
}}
''', encoding="utf-8")

    run = tc.compile_and_run_kotlin(
        tmp_path, (tmp_path / "probe.kt").read_text(encoding="utf-8"))
    inverted = {n: (v if _EXPECTED[n] else not v)
                for n, v in _results(run.stdout).items()}
    _assert_all(inverted, run.stdout)
