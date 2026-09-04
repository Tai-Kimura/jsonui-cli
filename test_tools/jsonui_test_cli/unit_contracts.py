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
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .branch_tests import (
    BranchTestGenerationError,
    _is_sub_spec_of_a_parent,
    _load_spec,
    _parent_declaring,
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
#: a method declaration inside one, with the modifiers that precede it and
#: whether its parameter list is empty.
#:
#: The parameter list is deliberately probed one character deep — `\(\s*\)?`
#: — rather than matched. An earlier pattern used `[^)]*`, which stops at the
#: first `)` and so skipped any function with a closure parameter, which made
#: a false positive look as though it depended on arity. Emptiness is all
#: that is needed and it cannot be fooled by nesting.
_SWIFT_FUNC_RE = re.compile(
    r"(?P<mods>(?:\b(?:private|fileprivate|internal|public|open|final|static|class|override|mutating|nonisolated)\b\s+|@\w+(?:\([^)]*\))?\s+)*)"
    r"\bfunc\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(?P<empty>\))?"
)

#: Modifiers that put a method outside XCTest's reach whatever it is called.
#: XCTest enumerates NO-ARGUMENT INSTANCE methods through the ObjC runtime, so
#: `private` hides it and `static`/`class` makes it not an instance method.
_UNREACHABLE_MODIFIERS = ("private", "fileprivate", "static", "class")

#: XCTest's own lifecycle hooks. They take no arguments and are not private,
#: so the reachability test above admits them — and they legitimately carry no
#: `test` prefix, which would make every file that overrides one report a
#: method that "never runs" while XCTest calls it on every single case. Found
#: by reading the predicate rather than from a report: it is the same false
#: positive as the three already fixed here, one shape further along.
_XCTEST_LIFECYCLE = frozenset({
    "setUp", "setUpWithError", "tearDown", "tearDownWithError",
    "addTeardownBlock", "record", "invokeTest", "perform",
    "continueAfterFailure", "setUpTestCaseWithError", "tearDownTestCaseWithError",
})


def _could_ever_run(mods: str, empty_params: bool) -> bool:
    """Could XCTest discover this method if it were named `test…`?

    Reported by a consumer on the third false positive from this one warning:
    a method taking parameters, or marked `private`, CANNOT be a mis-named
    test — the name is not what stops it — so telling its author that it
    "never runs" gives them nothing they can act on. They declined to rename
    round it, correctly: renaming would not change the predicate, only make
    the source worse to suit the tool.

    So the warning now covers exactly the set it was written for: methods that
    WOULD run if they carried the prefix, and do not.
    """
    if not empty_params:
        return False
    return not any(re.search(rf"\b{m}\b", mods) for m in _UNREACHABLE_MODIFIERS)


def _swift_test_methods(text: str) -> list[str]:
    """Method names declared inside XCTestCase subclasses, in order.

    Only methods XCTest could actually execute are returned: brace-matched to
    the class body (a regex cannot tell where the body ends and the
    file-scope helpers begin), then filtered by `_could_ever_run`.
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
            names.extend(
                m.group("name")
                for m in _SWIFT_FUNC_RE.finditer(text[start:i])
                if m.group("name") not in _XCTEST_LIFECYCLE
                and _could_ever_run(m.group("mods"), m.group("empty") is not None)
            )
    return names


@dataclass(frozen=True)
class UnitCase:
    """One declared case: a name, and the platforms that must carry it."""

    screen: str
    target: str
    name: str
    platforms: tuple[str, ...]
    intent: str = ""
    #: Path of the spec this case was read from, relative to the spec root
    #: and POSIX-separated. For a split screen this is the PARENT: the cases
    #: arrive through the merged view, which is also the page a reader has to
    #: get back to. A screen id cannot stand in for it — the docs site builds
    #: spec URLs from the path, so a nested spec is unreachable from the id.
    spec_file: str = ""


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
    #: SCREENS whose merged view carries a `unitContracts` key. Kept because
    #: `declared_in_sub` compares against it to catch a sub-spec block that
    #: never reached its parent. Not the reported denominator — see below.
    declaring_specs: list[str] = field(default_factory=list)
    #: FILES whose raw JSON carries a `unitContracts` key, spec-root-relative.
    #: This is what the summary line reports, because it is the count a reader
    #: can check independently: `grep -l unitContracts` over the spec tree
    #: returns exactly these. The screen count cannot be checked that way — it
    #: folds a parent and its sub-specs into one, so reproducing it means
    #: knowing the folding rule, and a reader who does not ends up comparing
    #: two different units and reading the difference as a missing block.
    declaring_files: list[str] = field(default_factory=list)
    #: input this scan could not read, one line each
    problems: list[str] = field(default_factory=list)
    #: FILES that could not be parsed, spec-root-relative. Collected at the
    #: parse site, NOT derived from `problems`: `problems` also carries
    #: malformed-block and never-landed-sub-spec lines, so its length answers
    #: a different question and would drift the moment any other problem is
    #: reported. These files stay in `scanned` — unreadable is not "declares
    #: nothing" — which is exactly why they need naming somewhere: otherwise
    #: they widen `scanned - declaring` silently.
    unreadable_files: list[str] = field(default_factory=list)
    #: platform -> method names that exist but the runner will never execute
    undiscoverable: dict[str, list[str]] = field(default_factory=dict)
    #: platform -> case name -> the file(s) that implement it
    implemented_files: dict[str, dict[str, list[str]]] = field(default_factory=dict)

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
    """``(cases, scanned, screens declaring, problems, files declaring, unreadable)``.

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
    declaring_files: list[str] = []
    unreadable_files: list[str] = []
    problems: list[str] = []
    # Sub-specs that declare a block, by the parent that owns them. They are
    # skipped AS SCREENS (parent + subs is one screen), and their blocks are
    # meant to arrive through the parent's merged view. When they do not, the
    # loss used to be silent — the reported defect — so the two are compared
    # after the sweep and a block that never landed is named.
    declared_in_sub: dict[str, list[str]] = {}
    for path in _spec_files(spec_path):
        screen = _screen_of(path)
        scanned.append(screen)
        try:
            rel_file = path.resolve().relative_to(spec_path).as_posix()
        except ValueError:
            rel_file = path.name
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            # Unreadable is not "declares nothing". Keeping it in `scanned`
            # keeps the denominator honest, and saying so keeps a spec that
            # cannot be parsed from reading as one that declares nothing.
            problems.append(f"{screen}: spec could not be read ({e})")
            unreadable_files.append(rel_file)
            continue
        # Counted off the RAW file, before the sub-spec skip and before the
        # merge: a file declares a block or it does not, and that is the fact
        # `grep -l` reproduces. A parent that only RECEIVES blocks from its
        # subs does not carry one itself, so it is not counted here — its subs
        # are. A file that could not be parsed is not counted either; it is
        # still in `scanned`, because unreadable is not "declares nothing".
        if raw.get("unitContracts") is not None:
            declaring_files.append(rel_file)
        if raw.get("type") != PARENT_SPEC_TYPE and _is_sub_spec_of_a_parent(path, spec_path):
            if raw.get("unitContracts") is not None:
                parent = _parent_declaring(path, spec_path)
                if parent is not None:
                    declared_in_sub.setdefault(_screen_of(parent), []).append(screen)
            continue
        spec = _load_spec(path)
        try:
            rel = path.resolve().relative_to(spec_path).as_posix()
        except ValueError:
            rel = path.name
        found, issues = _cases_of(spec, screen, rel)
        cases.extend(found)
        problems.extend(issues)
        # Read off the spec AS READ, not the raw file. A parent may not
        # declare `unitContracts` itself (the merger refuses it), so counting
        # raw declarations reported "0 carrying" for a split screen whose
        # sub-specs had just contributed every case in `cases` — a summary
        # line that contradicted its own numerator.
        if spec.get("unitContracts") is not None:
            declaring.append(screen)
    for parent_screen, subs in sorted(declared_in_sub.items()):
        if parent_screen in declaring:
            continue
        problems.append(
            f"{parent_screen}: {len(subs)} sub-spec(s) declare unitContracts "
            f"({', '.join(sorted(subs))}) but the merged parent carries none "
            f"— the declaration was not read. This is a tool defect, not a "
            f"spec error; the cases are NOT being checked."
        )
    return cases, scanned, declaring, problems, declaring_files, unreadable_files


#: Keys a unitContracts block and a case may carry. Anything else is a
#: typo, and a typo used to make the declaration disappear.
_BLOCK_KEYS = {"target", "cases"}
_CASE_KEYS = {"name", "intent", "platforms"}


def _cases_of(spec: dict, screen: str, spec_file: str = "") -> tuple[list[UnitCase], list[str]]:
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
                    spec_file=spec_file,
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


def _implemented_names(
    root: Path, platform: str
) -> tuple[set[str], list[str], set[str], dict[str, list[str]]]:
    """``(case names found, files read, undiscoverable names, name -> files)``.

    The name -> files map is what lets a caller link a case to the file that
    implements it. The scan used to collapse every file into one set of names
    and return only a flat list of files read, so "which file carries this
    case" was not answerable from the result at all -- a doc page could only
    have guessed it from the filename convention, which is exactly the guess
    that breaks for a project that does not follow it.
    """
    suffix = PLATFORM_TEST_SUFFIX.get(platform)
    pattern = _ALL_TESTS_PATTERNS.get(platform)
    if suffix is None or not root.is_dir() or (platform != "ios" and pattern is None):
        return set(), [], set()
    names: set[str] = set()
    undiscoverable: set[str] = set()
    read: list[str] = []
    by_name: dict[str, list[str]] = {}
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
                where = by_name.setdefault(mapped, [])
                if str(path) not in where:
                    where.append(str(path))
    return names, read, undiscoverable, by_name


def check_unit_contracts(
    project_root: Path,
    spec_dir: str | None = None,
    project_platforms: list[str] | None = None,
) -> UnitContractReport:
    """Compare declared cases against implemented ones, per platform."""
    project_root = Path(project_root)
    config = load_project_config(project_root)
    (cases, scanned, declaring, problems, declaring_files,
     unreadable_files) = discover_unit_contracts(project_root, spec_dir)
    roots = _test_roots(project_root, config)
    if project_platforms is None:
        project_platforms = sorted(roots)

    report = UnitContractReport(
        cases=cases, scanned_specs=scanned,
        declaring_specs=declaring, problems=problems,
        declaring_files=declaring_files,
        unreadable_files=unreadable_files,
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
        found, read, undiscoverable, by_name = _implemented_names(root, platform)
        report.implemented[platform] = found
        report.scanned_files[platform] = read
        report.implemented_files[platform] = by_name
        if undiscoverable:
            report.undiscoverable[platform] = sorted(undiscoverable)
    return report


def summary_line_for(cases: int, scanned: int, declaring: int) -> str:
    """The denominator sentence, from counts alone.

    Takes numbers rather than a report because the docs index says the same
    thing about a whole RUN — several scans, one line — and it has no report
    to hand. Composing that sentence there would put the wording in two
    places, which is the shape this line was extracted to avoid: the index and
    `--check` would then be able to disagree about how a count is phrased
    while agreeing about the count.
    """
    return (
        f"unit contracts: {cases} case(s) declared across "
        f"{scanned} spec file(s) scanned "
        f"({declaring} spec file(s) carrying a unitContracts block)"
    )


def summary_line(report: UnitContractReport) -> str:
    """The denominator line for one scan.

    `--check` prints it and the generated docs index shows it. Requirement 3
    of the docs ticket is that the two carry the SAME numbers, and the only
    way two call sites cannot drift is for there to be one call site.
    """
    return summary_line_for(
        len(report.cases), len(report.scanned_specs), len(report.declaring_files)
    )


#: Keys `aggregate_unit_totals` adds up. Named so a new total added to
#: `unit_contract_pages` fails loudly here rather than being dropped from an
#: aggregate that silently keeps reporting the old set.
_SUMMABLE_TOTALS = ("cases", "specs_scanned", "specs_declaring",
                    "specs_unreadable", "targets")


def aggregate_unit_totals(totals_list: list[dict]) -> dict:
    """One run's totals from several scans' totals.

    A multi-app site scans once per app and shows ONE denominator. Summing
    those in the docs generator would mean composing the sentence there too,
    so the sum and its wording both live here.

    `targets` is summed like the rest: each scan reads a different app's
    specs, so two scans naming a target the same way are two targets, not one
    seen twice. `unreadable_files` is concatenated rather than counted again,
    so the names survive into the warning the generator prints.
    """
    out = {key: 0 for key in _SUMMABLE_TOTALS}
    unreadable: list[str] = []
    for totals in totals_list:
        for key in _SUMMABLE_TOTALS:
            out[key] += totals.get(key, 0)
        unreadable.extend(totals.get("unreadable_files", []))
    out["unreadable_files"] = unreadable
    out["summary_line"] = summary_line_for(
        out["cases"], out["specs_scanned"], out["specs_declaring"]
    )
    return out


def format_report(report: UnitContractReport) -> list[str]:
    """Human-readable lines, always naming the denominator."""
    lines = [summary_line(report)]
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


#: Per-case status on one face. `missing` and `not_declared_for_face` are
#: kept apart deliberately: a case declared for ios only is NOT an android
#: failure, and collapsing the two makes a correct project's page read red.
CASE_IMPLEMENTED = "implemented"
CASE_MISSING = "missing"
CASE_NOT_DECLARED_FOR_FACE = "not_declared_for_face"
#: Written, compiles, reads as present -- and executes zero times, because
#: the runner will not discover it (XCTest needs a `test` prefix). It is NOT
#: `missing`: a reader told "missing" goes and writes a test that already
#: exists, and it still will not run. `--check` has a dedicated NEVER RUNS
#: line for it, so collapsing it here would lose on the site what the CLI
#: already says.
CASE_NEVER_RUNS = "never_runs"


def _relative_to_project(path: str, project_root: Path) -> str:
    """A project-relative, POSIX path — never an absolute one.

    `_test_roots` resolves its roots, so every implementing file arrives here
    absolute even when the caller passed a relative project root. Handing that
    to the docs generator bakes the developer's home directory — username and
    all — into a generated site that consumers commit. `spec_file` is already
    relativised at its source; this is the same rule for the other half.

    A root configured outside the project still relativises (`../sibling/...`),
    which keeps the link usable without naming anyone's home. Only a path with
    no relative expression at all (a different Windows drive) falls back, and
    it falls back to the bare filename rather than to something absolute.
    """
    try:
        return Path(os.path.relpath(Path(path), project_root)).as_posix()
    except ValueError:
        return Path(path).name


def unit_contract_pages(
    project_root: Path,
    spec_dir: str | None = None,
    project_platforms: list[str] | None = None,
) -> dict:
    """The `unit-stubs --check` judgment, grouped by target, as plain data.

    For `document_tools`, which generates one page per target and needs the
    per-face implementation state on it. Returns JSON-safe values only (no
    sets; every list sorted) so the caller can serialise or template it
    directly.

    The judgment itself is NOT reimplemented here -- this calls
    `check_unit_contracts` and regroups its result. Two generations of
    "is this case implemented" is exactly the drift the unitContracts
    mechanism exists to prevent, and a second copy living in the docs
    generator would be invisible to `--check`'s own tests.

    `undeclared` is returned at the TOP LEVEL, not under a target: a case
    that is implemented but declared nowhere has no target by definition,
    so there is no page it could belong to.
    """
    project_root = Path(project_root)
    report = check_unit_contracts(project_root, spec_dir, project_platforms)
    platforms = report.platforms

    by_target: dict[str, dict] = {}
    for case in report.cases:
        entry = by_target.setdefault(
            case.target,
            {"target": case.target, "screens": [], "cases": [],
             "spec_files": [],
             "faces": {p: {"declared": [], "implemented": [], "missing": [],
                           "never_runs": [], "files": []}
                       for p in platforms}},
        )
        if case.screen not in entry["screens"]:
            entry["screens"].append(case.screen)
        if case.spec_file and case.spec_file not in entry["spec_files"]:
            entry["spec_files"].append(case.spec_file)
        faces = case.platforms or tuple(platforms)
        status = {}
        for platform in platforms:
            if platform not in faces:
                status[platform] = CASE_NOT_DECLARED_FOR_FACE
                continue
            implemented = case.name in report.implemented.get(platform, set())
            never_runs = case.name in report.undiscoverable.get(platform, [])
            if implemented:
                status[platform] = CASE_IMPLEMENTED
            elif never_runs:
                status[platform] = CASE_NEVER_RUNS
            else:
                status[platform] = CASE_MISSING
            bucket = entry["faces"][platform]
            bucket["declared"].append(case.name)
            if implemented:
                bucket["implemented"].append(case.name)
            elif never_runs:
                bucket["never_runs"].append(case.name)
            else:
                bucket["missing"].append(case.name)
            for path in report.implemented_files.get(platform, {}).get(case.name, []):
                rel = _relative_to_project(path, project_root)
                if rel not in bucket["files"]:
                    bucket["files"].append(rel)
        entry["cases"].append({
            "name": case.name,
            "intent": case.intent,
            "platforms": sorted(faces),
            "status": status,
        })

    targets = []
    for target in sorted(by_target):
        entry = by_target[target]
        entry["screens"] = sorted(entry["screens"])
        entry["spec_files"] = sorted(entry["spec_files"])
        entry["cases"] = sorted(entry["cases"], key=lambda c: c["name"])
        for bucket in entry["faces"].values():
            for key in ("declared", "implemented", "missing", "never_runs", "files"):
                bucket[key] = sorted(set(bucket[key]))
        targets.append(entry)

    return {
        "totals": {
            "cases": len(report.cases),
            "specs_scanned": len(report.scanned_specs),
            "specs_declaring": len(report.declaring_files),
            "specs_unreadable": len(report.unreadable_files),
            "unreadable_files": sorted(report.unreadable_files),
            "targets": len(targets),
            "summary_line": summary_line(report),
        },
        "platforms": platforms,
        "ok": report.ok,
        "problems": list(report.problems),
        "unscannable": dict(report.unscannable),
        "undiscoverable": {p: list(v) for p, v in sorted(report.undiscoverable.items())},
        "undeclared": {p: report.undeclared(p) for p in platforms if report.undeclared(p)},
        "targets": targets,
    }


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
