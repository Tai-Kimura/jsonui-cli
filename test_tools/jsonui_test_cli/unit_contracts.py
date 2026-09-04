"""Declare hand-written unit test cases in the spec; check the sets match.

The spec's job here is not to generate a test body — that was tried and
measured: generating branch tests from ``branchContracts`` moves the covered
line count on the contracted methods by 4.3 points, and the untested
declared-method bodies across 32 uncontracted screens are 331 lines, 3.3% of
one face's untouched total. Reaching 80% needs the ViewModel and Model
bodies written by hand, which is roughly 6,000 lines on one face and 8,500
on another.

So the bodies are hand-written, and what the spec carries is the *set*:
which cases exist, and on which platforms. Two faces implementing the same
screen from the same spec otherwise drift apart silently — a case gets
written on one side, renamed on the other, and nothing compares them,
because the only thing that could is a person reading both trees.

Three behaviours, and no more:

1. ``generate`` writes stubs for declared cases that have no implementation,
   in each platform's own convention, and never touches an existing body.
2. ``check`` fails when the sets disagree: declared but unimplemented,
   implemented but undeclared, or declared for two platforms and present on
   one.
3. Both name a denominator. "0 drifted" over an empty scan and "0 drifted"
   over forty cases are the same sentence and opposite facts, and this
   project has shipped wrong findings from instruments that could not tell
   those apart.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .branch_tests import (
    BranchTestGenerationError,
    _is_sub_spec_of_a_parent,
    _load_spec,
    _screen_of,
    _spec_files,
    load_project_config,
    PARENT_SPEC_TYPE,
)


class UnitContractError(RuntimeError):
    """Raised when the contract cannot be evaluated (bad inputs, no config)."""


#: Platforms a case may name, and the file extension its tests live in.
PLATFORM_TEST_SUFFIX = {"ios": ".swift", "android": ".kt", "web": ".ts"}

#: How a test case's name appears in each platform's source. Declared names
#: are explicit strings, so these match the name rather than a convention.
_DECL_PATTERNS = {
    # func sendMessage_whenOffline_setsError() / func test...()
    "ios": lambda n: re.compile(r"\bfunc\s+" + re.escape(n) + r"\s*\("),
    # fun name() or fun `name with spaces`()
    "android": lambda n: re.compile(r"\bfun\s+`?" + re.escape(n) + r"`?\s*\("),
    # it('name') / test("name")
    "web": lambda n: re.compile(r"\b(?:it|test)\s*\(\s*[\'\"]" + re.escape(n) + r"[\'\"]"),
}

#: Every test-method name a file declares, used to find implementations the
#: spec does not know about. Deliberately per-platform: a regex that matched
#: all three would also match things that are not tests in two of them.
#:
#: ⚠️ ios is NOT a bare `func` scan. The first cut was, and it flagged a
#: consumer's file-scope helper `func settle()` as a mis-named test that
#: "never runs" — always wrong for that shape, which is worse than silence:
#: a line that is always wrong teaches the reader to skip it, and the next
#: real finding on it is skipped too. Only functions inside an XCTestCase
#: subclass can be test methods, so only those are scanned.
_ALL_TESTS_PATTERNS = {
    "android": re.compile(r"@Test[\s\S]{0,200}?\bfun\s+`?([^`(\s]+)`?\s*\("),
    "web": re.compile(r"\b(?:it|test)\s*\(\s*[\'\"]([^\'\"]+)[\'\"]"),
}

#: `class Foo: XCTestCase {` / `final class Foo : XCTestCase, Bar {`
_SWIFT_TESTCASE_RE = re.compile(r"\bclass\s+\w+\s*:[^{]*\bXCTestCase\b[^{]*\{")
#: a method declaration inside one. Arguments are not matched at all: the
#: previous pattern used `[^)]*`, which stopped at the first `)` and so
#: silently skipped any function with a closure parameter — the reason the
#: false positive looked like it depended on arity.
_SWIFT_FUNC_RE = re.compile(r"\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _swift_test_methods(text: str) -> list[str]:
    """Method names declared inside XCTestCase subclasses, in order.

    Brace-matched rather than regex-scoped, because a regex cannot tell where
    a class body ends and the file-scope helpers begin — which is exactly the
    distinction the false positive turned on.
    """
    names: list[str] = []
    for match in _SWIFT_TESTCASE_RE.finditer(text):
        depth, i = 0, match.end() - 1
        start = None
        while i < len(text):
            ch = text[i]
            if ch == "{":
                depth += 1
                if start is None:
                    start = i + 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        if start is not None:
            names.extend(m.group(1) for m in _SWIFT_FUNC_RE.finditer(text[start:i]))
    return names


@dataclass(frozen=True)
class UnitCase:
    """One declared case: a name, and the platforms that must carry it."""

    screen: str
    target: str
    name: str
    platforms: tuple[str, ...]
    intent: str = ""


@dataclass
class UnitContractReport:
    """What the scan found, with both halves of every count."""

    cases: list[UnitCase] = field(default_factory=list)
    scanned_specs: list[str] = field(default_factory=list)
    #: platform -> declared case names
    declared: dict[str, set[str]] = field(default_factory=dict)
    #: platform -> case names found in that platform's test sources
    implemented: dict[str, set[str]] = field(default_factory=dict)
    #: platform -> the files that were actually read
    scanned_files: dict[str, list[str]] = field(default_factory=dict)
    #: platforms named by a case but with no configured test root
    unscannable: dict[str, str] = field(default_factory=dict)
    #: specs that carry a `unitContracts` key at all
    declaring_specs: list[str] = field(default_factory=list)
    #: input this scan could not read, one line each
    problems: list[str] = field(default_factory=list)
    #: platform -> method names that exist but the runner will never execute
    undiscoverable: dict[str, list[str]] = field(default_factory=dict)

    def missing(self, platform: str) -> list[str]:
        """Declared for this platform, not implemented on it."""
        return sorted(self.declared.get(platform, set()) - self.implemented.get(platform, set()))

    def undeclared(self, platform: str) -> list[str]:
        """Implemented on this platform, declared nowhere."""
        return sorted(self.implemented.get(platform, set()) - self.declared.get(platform, set()))

    @property
    def platforms(self) -> list[str]:
        return sorted(set(self.declared) | set(self.implemented) | set(self.unscannable))

    @property
    def ok(self) -> bool:
        # Input we could not read fails, and so does a block that declared
        # nothing readable: "0 declared" over specs that DO carry the key is
        # the shape a single misspelling produces, and it is indistinguishable
        # from a clean run unless it is called out here.
        if self.problems or self.unscannable or self.undiscoverable:
            return False
        if self.declaring_specs and not self.cases:
            return False
        return all(
            not self.missing(p) and not self.undeclared(p) for p in self.platforms
        )


def discover_unit_contracts(
    project_root: Path, spec_dir: str | None = None
) -> tuple[list[UnitCase], list[str], list[str], list[str]]:
    """``(cases, specs scanned, specs declaring a block, problems)``.

    Both halves, for the same reason ``discover_branch_screens`` returns
    both: a caller that reports "0 declared" has to be able to say whether
    it read forty specs or none.
    """
    project_root = Path(project_root)
    if spec_dir is None:
        spec_dir = load_project_config(project_root).get("spec_directory")
    if not spec_dir:
        raise UnitContractError(
            "spec_directory is not declared in jui.config.json — cannot "
            "enumerate screens to read unitContracts from"
        )
    spec_path = (project_root / spec_dir).resolve()
    if not spec_path.is_dir():
        raise UnitContractError(f"spec directory not found: {spec_path}")

    cases: list[UnitCase] = []
    scanned: list[str] = []
    declaring: list[str] = []
    problems: list[str] = []
    for path in _spec_files(spec_path):
        screen = _screen_of(path)
        scanned.append(screen)
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            # Unreadable is not "declares nothing". Keeping it in `scanned`
            # keeps the denominator honest, and saying so keeps a spec that
            # cannot be parsed from reading as one that declares nothing.
            problems.append(f"{screen}: spec could not be read ({e})")
            continue
        if raw.get("type") != PARENT_SPEC_TYPE and _is_sub_spec_of_a_parent(path, spec_path):
            continue
        spec = _load_spec(path)
        found, issues = _cases_of(spec, screen)
        cases.extend(found)
        problems.extend(issues)
        if raw.get("unitContracts") is not None:
            declaring.append(screen)
    return cases, scanned, declaring, problems


#: Keys a unitContracts block and a case may carry. Anything else is a
#: typo, and a typo used to make the declaration disappear.
_BLOCK_KEYS = {"target", "cases"}
_CASE_KEYS = {"name", "intent", "platforms"}


def _cases_of(spec: dict, screen: str) -> tuple[list[UnitCase], list[str]]:
    """``(cases, problems)`` for one spec.

    Every path that drops input reports it. The first cut silently skipped
    anything it could not read, so ``"caes"`` for ``"cases"`` made the whole
    declaration vanish and both gates went green: `unit-stubs --check` printed
    "0 case(s) declared" and `validate spec` printed 0 errors. Neither output
    was a lie — the block really did declare nothing the reader could see —
    and that is precisely why it was dangerous. A mechanism whose entire
    purpose is stopping drift must not be removable by one misspelling.
    """
    raw = spec.get("unitContracts")
    if raw is None:
        return [], []
    blocks = [raw] if isinstance(raw, dict) else raw
    if not isinstance(blocks, list):
        return [], [f"{screen}: 'unitContracts' must be an object or an array, got {type(raw).__name__}"]

    out: list[UnitCase] = []
    problems: list[str] = []
    for i, block in enumerate(blocks):
        where = f"{screen}: unitContracts[{i}]"
        if not isinstance(block, dict):
            problems.append(f"{where} must be an object, got {type(block).__name__}")
            continue
        for key in sorted(set(block) - _BLOCK_KEYS):
            problems.append(
                f"{where}: unknown key {key!r} (expected one of {sorted(_BLOCK_KEYS)}) "
                f"— a misspelling here drops the declaration"
            )
        target = str(block.get("target") or "").strip()
        if not target:
            problems.append(f"{where}: 'target' is missing or empty")
        cases = block.get("cases")
        if cases is None:
            problems.append(f"{where}: 'cases' is missing — this block declares nothing")
            continue
        if not isinstance(cases, list):
            problems.append(f"{where}: 'cases' must be an array, got {type(cases).__name__}")
            continue
        for j, case in enumerate(cases):
            spot = f"{where}.cases[{j}]"
            if not isinstance(case, dict):
                problems.append(f"{spot} must be an object, got {type(case).__name__}")
                continue
            for key in sorted(set(case) - _CASE_KEYS):
                problems.append(
                    f"{spot}: unknown key {key!r} (expected one of {sorted(_CASE_KEYS)})"
                )
            name = str(case.get("name") or "").strip()
            if not name:
                problems.append(f"{spot}: 'name' is missing or empty — the case cannot be compared")
                continue
            platforms = case.get("platforms")
            if platforms is not None and not isinstance(platforms, list):
                problems.append(f"{spot}: 'platforms' must be an array, got {type(platforms).__name__}")
                platforms = None
            if not platforms:
                # Unstated means every platform the project builds; the
                # caller resolves that, because this module does not know
                # which platforms a project has.
                platforms = []
            out.append(
                UnitCase(
                    screen=screen,
                    target=target,
                    name=name,
                    platforms=tuple(str(p) for p in platforms),
                    intent=str(case.get("intent") or ""),
                )
            )
    return out, problems


def _test_roots(project_root: Path, config: dict) -> dict[str, Path | None]:
    """``platform -> unit-test directory``, or None when not declared.

    None rather than a guess: scanning the wrong directory finds nothing and
    reports every declared case as unimplemented, which reads like drift and
    is a configuration error.
    """
    roots: dict[str, Path | None] = {}
    for platform, entry in (config.get("platforms") or {}).items():
        if not isinstance(entry, dict):
            continue
        unit_dir = entry.get("unitTestsDir")
        if not unit_dir:
            roots[platform] = None
            continue
        base = project_root / (entry.get("root") or "")
        roots[platform] = (base / unit_dir).resolve()
    return roots


def _discoverable(platform: str, found: str) -> str | None:
    """Map a found method name back to the declared case name it implements.

    Returns None when the method exists but the platform's runner will never
    execute it — an XCTest method without the `test` prefix compiles, reads
    as present to any name-matching scan, and silently never runs.
    """
    if platform != "ios":
        return found
    if found.startswith(IOS_TEST_PREFIX):
        return found[len(IOS_TEST_PREFIX):]
    if found.startswith("test"):
        return found
    return None


def _implemented_names(root: Path, platform: str) -> tuple[set[str], list[str], set[str]]:
    """``(case names found, files read, names present but undiscoverable)``."""
    suffix = PLATFORM_TEST_SUFFIX.get(platform)
    pattern = _ALL_TESTS_PATTERNS.get(platform)
    if suffix is None or not root.is_dir() or (platform != "ios" and pattern is None):
        return set(), [], set()
    names: set[str] = set()
    undiscoverable: set[str] = set()
    read: list[str] = []
    for path in sorted(root.rglob(f"*{suffix}")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        read.append(str(path))
        raws = (_swift_test_methods(text) if platform == "ios"
                else [m.group(1) for m in pattern.finditer(text)])
        for raw in raws:
            mapped = _discoverable(platform, raw)
            if mapped is None:
                undiscoverable.add(raw)
            else:
                names.add(mapped)
    return names, read, undiscoverable


def check_unit_contracts(
    project_root: Path,
    spec_dir: str | None = None,
    project_platforms: list[str] | None = None,
) -> UnitContractReport:
    """Compare declared cases against implemented ones, per platform."""
    project_root = Path(project_root)
    config = load_project_config(project_root)
    cases, scanned, declaring, problems = discover_unit_contracts(project_root, spec_dir)
    roots = _test_roots(project_root, config)
    if project_platforms is None:
        project_platforms = sorted(roots)

    report = UnitContractReport(
        cases=cases, scanned_specs=scanned,
        declaring_specs=declaring, problems=problems,
    )
    for case in cases:
        targets = case.platforms or tuple(project_platforms)
        for platform in targets:
            report.declared.setdefault(platform, set()).add(case.name)

    for platform in sorted(set(report.declared) | set(project_platforms)):
        root = roots.get(platform)
        if root is None:
            if report.declared.get(platform):
                report.unscannable[platform] = (
                    f"platforms.{platform}.unitTestsDir is not declared in "
                    f"jui.config.json, so the {len(report.declared[platform])} case(s) "
                    f"declared for it cannot be compared against anything"
                )
            continue
        if not root.is_dir():
            if report.declared.get(platform):
                report.unscannable[platform] = (
                    f"unit test directory not found: {root} — declared cases for "
                    f"{platform} cannot be compared against anything. This is "
                    f"also what a project looks like before its first stub is "
                    f"generated (git does not track empty directories), so "
                    f"check that before suspecting the path"
                )
            continue
        found, read, undiscoverable = _implemented_names(root, platform)
        report.implemented[platform] = found
        report.scanned_files[platform] = read
        if undiscoverable:
            report.undiscoverable[platform] = sorted(undiscoverable)
    return report


def format_report(report: UnitContractReport) -> list[str]:
    """Human-readable lines, always naming the denominator."""
    lines = [
        f"unit contracts: {len(report.cases)} case(s) declared across "
        f"{len(report.scanned_specs)} spec(s) scanned "
        f"({len(report.declaring_specs)} carrying a unitContracts block)"
    ]
    for problem in report.problems:
        lines.append(f"  PROBLEM  {problem}")
    if report.declaring_specs and not report.cases:
        lines.append(
            f"  PROBLEM  {len(report.declaring_specs)} spec(s) carry a "
            f"'unitContracts' block but no case could be read from any of them "
            f"— a misspelled key drops the declaration silently, which is the "
            f"one failure this mechanism must not have"
        )
    if not report.platforms:
        lines.append("  no platforms to compare — nothing was checked (not: nothing drifted)")
        return lines
    for platform in report.platforms:
        if platform in report.unscannable:
            lines.append(f"  {platform}: NOT CHECKED — {report.unscannable[platform]}")
            continue
        declared = len(report.declared.get(platform, set()))
        implemented = len(report.implemented.get(platform, set()))
        missing = report.missing(platform)
        undeclared = report.undeclared(platform)
        lines.append(
            f"  {platform}: declared {declared}, implemented {implemented}, "
            f"missing {len(missing)}, undeclared {len(undeclared)} "
            f"({len(report.scanned_files.get(platform, []))} file(s) read)"
        )
        for name in missing:
            lines.append(f"    MISSING     {name}  (declared, no implementation)")
        for name in undeclared:
            lines.append(f"    UNDECLARED  {name}  (implemented, declared nowhere)")
        for name in report.undiscoverable.get(platform, []):
            lines.append(
                f"    NEVER RUNS  {name}  (method exists but the runner will not "
                f"discover it — XCTest needs a 'test' prefix; it compiles, reads "
                f"as present, and executes zero times)"
            )
    return lines


#: Marker pair a generated stub file carries. Everything outside it is the
#: author's, and regeneration preserves it — the same contract the kjui view
#: scaffold uses, for the same reason: the body is the part a person wrote.
STUB_BEGIN = "// >>> GENERATED_STUBS_START"
STUB_END = "// <<< GENERATED_STUBS_END"

#: ⚠️ ios method names are prefixed. XCTest discovers only `test`-prefixed
#: methods, so a stub named exactly as declared compiles, is counted by a
#: naive scan, and never runs — the mechanism manufacturing the failure it
#: exists to prevent. Declared names stay platform-neutral; the prefix is
#: added here and understood by the scanner.
IOS_TEST_PREFIX = "test_"

_STUB_BODY = {
    "ios": '    func ' + IOS_TEST_PREFIX + '{name}() throws {{\n        XCTFail("not implemented: {intent}")\n    }}',
    "android": '    @Test\n    fun `{name}`() {{\n        fail("not implemented: {intent}")\n    }}',
    "web": "  it('{name}', () => {{\n    throw new Error('not implemented: {intent}');\n  }});",
}

#: ⚠️ `@testable import` takes the MODULE, and a Kotlin file needs its
#: package. Neither is derivable from `target`, which is a class name — an
#: earlier cut emitted `@testable import <ClassName>` and did not compile.
#: These come from config, and generation refuses without them rather than
#: emitting a file that cannot build.
_STUB_FILE = {
    "ios": "import XCTest\n@testable import {module}\n\nfinal class {target}ContractTests: XCTestCase {{\n"
           + STUB_BEGIN + "\n{body}\n" + STUB_END + "\n}}\n",
    "android": "package {package}\n\nimport org.junit.Test\nimport org.junit.Assert.fail\n\n"
               "class {target}ContractTest {{\n"
               + STUB_BEGIN + "\n{body}\n" + STUB_END + "\n}}\n",
    "web": "describe('{target}', () => {{\n" + STUB_BEGIN + "\n{body}\n" + STUB_END + "\n}});\n",
}


def stub_text(
    platform: str, target: str, cases: list[UnitCase],
    module: str | None = None, package: str | None = None,
) -> str:
    """A stub file for *cases*, in *platform*'s convention.

    The body is a deliberate failure, not a pass: a stub that passes is a
    case that reports success without having been written, which is worse
    than a missing one because it is counted.
    """
    template = _STUB_FILE.get(platform)
    body_template = _STUB_BODY.get(platform)
    if template is None or body_template is None:
        raise UnitContractError(f"no stub convention for platform {platform!r}")
    if platform == "ios" and not module:
        raise UnitContractError(
            "ios stubs need the module for `@testable import`; declare "
            "platforms.ios.testModule in jui.config.json. Emitting the class "
            "name there produces a file that does not compile"
        )
    if platform == "android" and not package:
        raise UnitContractError(
            "android stubs need a package; declare platforms.android.testPackage "
            "in jui.config.json. Without it the class lands in the default "
            "package and drops out of package-scoped test filters"
        )
    body = "\n\n".join(
        body_template.format(name=c.name, intent=(c.intent or c.name).replace('"', "'"))
        for c in cases
    )
    return template.format(
        target=target or "Unit", body=body, module=module or "", package=package or ""
    )


def merge_stubs(existing: str, generated: str) -> str:
    """Replace only the region between the markers; keep everything else.

    A file whose markers are gone is returned untouched: the author removed
    them, and overwriting on that basis would delete work.
    """
    if STUB_BEGIN not in existing or STUB_END not in existing:
        return existing
    head = existing.split(STUB_BEGIN)[0]
    tail = existing.split(STUB_END, 1)[1]
    new_body = generated.split(STUB_BEGIN, 1)[1].split(STUB_END, 1)[0]
    return head + STUB_BEGIN + new_body + STUB_END + tail


#: Where a target's stub file lives, per platform. A convention rather than a
#: declaration: the spec says which cases exist, not where a face keeps its
#: files, and asking it to would put the same fact in two places.
_STUB_FILENAME = {
    "ios": "{target}ContractTests.swift",
    "android": "{target}ContractTest.kt",
    "web": "{target}.contract.test.ts",
}


def write_stubs(
    project_root: Path,
    report: UnitContractReport,
    dry_run: bool = False,
) -> list[tuple[str, str, int]]:
    """Write or refresh stub files for cases with no implementation.

    Returns ``(path, action, case_count)`` per file touched. Only the region
    between the markers is rewritten; a file without them is left alone,
    because the author removed them and overwriting would delete work.
    """
    config = load_project_config(project_root)
    roots = _test_roots(Path(project_root), config)
    written: list[tuple[str, str, int]] = []

    by_platform_target: dict[tuple[str, str], list[UnitCase]] = {}
    for case in report.cases:
        for platform in case.platforms or tuple(report.platforms):
            if platform in report.unscannable or roots.get(platform) is None:
                continue
            if case.name in report.implemented.get(platform, set()):
                continue
            by_platform_target.setdefault((platform, case.target or "Unit"), []).append(case)

    for (platform, target), cases in sorted(by_platform_target.items()):
        root = roots[platform]
        if root is None:
            continue
        filename = _STUB_FILENAME.get(platform)
        if filename is None:
            continue
        path = root / filename.format(target=target)
        entry = (config.get("platforms") or {}).get(platform) or {}
        generated = stub_text(
            platform, target, sorted(cases, key=lambda c: c.name),
            module=entry.get("testModule"), package=entry.get("testPackage"),
        )
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            merged = merge_stubs(existing, generated)
            action = "unchanged" if merged == existing else "updated"
        else:
            merged = generated
            action = "created"
        if not dry_run and action != "unchanged":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(merged, encoding="utf-8")
        written.append((str(path), action, len(cases)))
    return written
