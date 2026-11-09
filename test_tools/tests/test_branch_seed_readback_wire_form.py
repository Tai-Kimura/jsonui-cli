"""A seeded object is read back in its wire form — EXECUTED on iOS and web.

seedableState values are written as the value's wire JSON (the form a
harness decodes from), and seedState read them back by member name: Mirror
on iOS, plain properties on web. Measured on 2.5.17's emitted runtimes
(docs/bugs 2026-11-09-test-branch-seed-readback-object-wire-vs-domain):

    seed (wire)                       iOS before   web before
    wire type, snake keys             red          ok   (a web DTO keeps wire keys)
    wire type, nested + array         red          ok
    jui Domain { dto }, any key       red          red  (Mirror / props see only dto)
    Optional<Domain>, [Domain]        red          red
    generated enum ("in_progress")    red          ok
    scalars, one-word keys, nil       ok           ok

Every row of the Domain shape was a false red the harness could not fix.
Now the value is read through its own encoding — iOS its Encodable, web a
toJSON or the Domain's dto — and a value that has none is read as before;
either way the failure says which way it was read ("in the wire form" /
"by reflection" / "the Domain's dto, unwrapped"), so a false red on the
fallback is told apart from a real one. Android's arm needs real kotlinx
serializers and is in test_branch_seed_readback_wire_android.py.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from jsonui_test_cli.branch_tests import generate_branch_tests
from tests import _toolchain as tc

# name -> (passes?, a word the failure must carry, or None)
_EXPECTED = {
    "scalar": (True, None),
    "wire-snake": (True, None),
    "wire-nested": (True, None),
    "domain-one-word": (True, None),
    "domain-snake": (True, None),
    "optional-domain": (True, None),
    "domain-list": (True, None),
    "domain-wrong-value": (False, "answer_key: expected"),
    "nil-object": (False, None),
}
_IOS_ONLY = {
    "enum-generated": (True, None),
    "plain-camel": (True, None),
    "plain-snake-reflection": (False, "by reflection: PlainQuestion is not Encodable"),
    "domain-wrong-value-via": (False, "in the wire form (Question's Encodable)"),
}
_WEB_ONLY = {
    "domain-wrong-value-via": (False, "in the wire form (the Domain's dto, unwrapped)"),
    "tojson": (True, None),
    "seed-names-dto": (True, None),
}


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    (root / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/specs"}), encoding="utf-8")
    spec = {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "S", "displayName": "S", "description": "d", "layoutFile": "s"},
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


def _rows(stdout: str) -> dict[str, tuple[bool, str]]:
    out = {}
    for line in stdout.splitlines():
        m = re.match(r"^ROW (\S+) (PASS|FAIL) ?(.*)$", line)
        if m:
            out[m.group(1)] = (m.group(2) == "PASS", m.group(3))
    return out


def _assert_rows(rows: dict, expected: dict, stdout: str) -> None:
    missing = set(expected) - set(rows)
    assert not missing, f"probe did not report {sorted(missing)}\n{stdout}"
    wrong = []
    for name, (passes, word) in expected.items():
        ok, message = rows[name]
        if ok != passes or (word and word not in message):
            wrong.append(f"{name}: passed={ok} ({message})")
    assert not wrong, "\n".join(wrong) + "\n\n" + stdout


_SWIFT_MAIN = r'''import Foundation
nonisolated struct SliderDto: Codable {
  let key: String?; let minValue: Int?
  enum CodingKeys: String, CodingKey { case key; case minValue = "min_value" }
}
nonisolated struct QuestionDto: Codable {
  let text: String?; let inputType: String?; let answerKey: String?; let sliders: [SliderDto]?
  enum CodingKeys: String, CodingKey {
    case text; case inputType = "input_type"; case answerKey = "answer_key"; case sliders
  }
}
/// jui's Domain proxy: Codable through its dto.
nonisolated struct Question: Codable {
  let dto: QuestionDto
  init(dto: QuestionDto) { self.dto = dto }
  init(from decoder: Decoder) throws { dto = try QuestionDto(from: decoder) }
  func encode(to encoder: Encoder) throws { try dto.encode(to: encoder) }
}
nonisolated struct PlainQuestion { let text: String; let inputType: String }
nonisolated enum Status: String, Codable { case inProgress = "in_progress"; case done }

final class VM {
  let dto = QuestionDto(text: "q", inputType: "slider", answerKey: "k", sliders: [SliderDto(key: "a", minValue: 1)])
  var count = 5
  var status = Status.inProgress
  var missing: Question? = nil
  var dtoQ: QuestionDto
  var domainQ: Question
  var optDomainQ: Question?
  var domainList: [Question]
  var plainQ = PlainQuestion(text: "q", inputType: "slider")
  init() { dtoQ = dto; domainQ = Question(dto: dto); optDomainQ = Question(dto: dto); domainList = [Question(dto: dto)] }
}
final class H: BaseBranchHarness {
  override func setState(_ state: [String: Any]) {}
}
func row(_ name: String, _ field: String, _ want: Any) {
  failures = []
  seedState(H(vm: VM()), [field: want])
  print("ROW \(name) " + (failures.isEmpty ? "PASS" : "FAIL " + failures.joined(separator: " | ")))
}
let snake: [String: Any] = ["input_type": "slider", "answer_key": "k"]
row("scalar", "count", 5)
row("wire-snake", "dtoQ", snake)
row("wire-nested", "dtoQ", ["sliders": [["key": "a", "min_value": 1]]])
row("domain-one-word", "domainQ", ["text": "q"])
row("domain-snake", "domainQ", snake)
row("optional-domain", "optDomainQ", snake)
row("domain-list", "domainList", [snake])
row("domain-wrong-value", "domainQ", ["answer_key": "other"])
row("domain-wrong-value-via", "domainQ", ["answer_key": "other"])
row("nil-object", "missing", snake)
row("enum-generated", "status", "in_progress")
row("plain-camel", "plainQ", ["inputType": "slider"])
row("plain-snake-reflection", "plainQ", ["input_type": "slider"])
'''

_SWIFT_SHIM = '''import Foundation
nonisolated(unsafe) var failures: [String] = []
func XCTFail(_ m: String = "", file: StaticString = #filePath, line: UInt = #line) { failures.append(m) }
func XCTAssertEqual<T: Equatable>(_ a: T, _ b: T, _ m: String = "",
  file: StaticString = #filePath, line: UInt = #line) {}
func XCTAssertEqual(_ a: Double, _ b: Double, accuracy: Double, _ m: String = "",
  file: StaticString = #filePath, line: UInt = #line) {}
'''


def test_ios_reads_a_seeded_object_back_in_its_wire_form(tmp_path):
    tc.tool("swiftc")
    root = _project(tmp_path)
    emitted = generate_branch_tests("s", root, platform="ios", module="App",
                                    out_dir="Tests/Gen", harness_dir="Tests/Gen").runtime_file.read_text("utf-8")
    assert emitted.count("\nimport XCTest\n") == 1
    (tmp_path / "runtime.swift").write_text(emitted.replace("\nimport XCTest\n", "\n", 1), encoding="utf-8")
    (tmp_path / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (tmp_path / "main.swift").write_text(_SWIFT_MAIN, encoding="utf-8")
    binary = tmp_path / "probe"
    build = subprocess.run(["swiftc", "-Onone", "-o", str(binary), str(tmp_path / "shim.swift"),
                            str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
                           capture_output=True, text=True, timeout=900)
    assert build.returncode == 0, f"emitted Swift did not compile:\n{build.stderr[:4000]}"
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    _assert_rows(_rows(run.stdout), {**_EXPECTED, **_IOS_ONLY}, run.stdout + run.stderr[-2000:])


def test_web_reads_a_seeded_domain_through_its_dto(tmp_path):
    tc.tool("node")
    root = _project(tmp_path)
    runtime = generate_branch_tests("s", root).runtime_file
    probe = runtime.parent / "probe.ts"
    probe.write_text(f'''import {{ seedState }} from "./{runtime.name}";
const dto = {{ text: "q", input_type: "slider", answer_key: "k", sliders: [{{ key: "a", min_value: 1 }}] }};
const domain = {{ dto }};
class Selfish {{ private inner = {{ input_type: "slider" }}; toJSON() {{ return this.inner; }} }}
function vm(): Record<string, unknown> {{
  return {{ count: 5, missing: null, dtoQ: dto, domainQ: domain, optDomainQ: domain, domainList: [domain],
           selfish: new Selfish(), wrapped: {{ dto: {{ id: 1 }}, tag: "x" }} }};
}}
function row(name: string, field: string, want: unknown) {{
  try {{
    seedState({{ vm: vm(), setState() {{}} }}, {{ [field]: want }});
    console.log(`ROW ${{name}} PASS`);
  }} catch (e) {{
    console.log(`ROW ${{name}} FAIL ${{(e as Error).message}}`);
  }}
}}
const snake = {{ input_type: "slider", answer_key: "k" }};
row("scalar", "count", 5);
row("wire-snake", "dtoQ", snake);
row("wire-nested", "dtoQ", {{ sliders: [{{ key: "a", min_value: 1 }}] }});
row("domain-one-word", "domainQ", {{ text: "q" }});
row("domain-snake", "domainQ", snake);
row("optional-domain", "optDomainQ", snake);
row("domain-list", "domainList", [snake]);
row("domain-wrong-value", "domainQ", {{ answer_key: "other" }});
row("domain-wrong-value-via", "domainQ", {{ answer_key: "other" }});
row("nil-object", "missing", snake);
row("tojson", "selfish", {{ input_type: "slider" }});
row("seed-names-dto", "wrapped", {{ dto: {{ id: 1 }}, tag: "x" }});
''', encoding="utf-8")
    run = subprocess.run(["node", "--experimental-strip-types", probe.name],
                         cwd=probe.parent, capture_output=True, text=True, timeout=120)
    _assert_rows(_rows(run.stdout), {**_EXPECTED, **_WEB_ONLY}, run.stdout + run.stderr[-2000:])
