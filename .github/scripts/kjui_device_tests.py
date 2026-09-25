#!/usr/bin/env python3
"""KotlinJsonUI's device tests, judged from their results.

conformance-mobile's `android-library-tests` job runs this through
kjui_device_tests.sh.

Why it exists (2026-09-26): `library` and `library-dynamic` keep instrumented
tests in src/androidTest, and no CI job ran them. KotlinJsonUI's ci.yml runs
the JVM units, and this workflow's `android` job runs only the conformance
host's suite. Arms written for a fix (a tap gate, a choice kept across a data
change, a badge a screen reader reads) were green on a developer's emulator and
nowhere else.

Two commands:

  flags <KotlinJsonUI>   The opt-in switches, one name per line. A switch is
                         any instrumentation argument that a test compares to
                         "1" (`getArguments().getString("x") == "1"`). The
                         list is derived from the tests, so a new probe needs no
                         edit here.
  judge <KotlinJsonUI>   Reads each module's connected-test XML. Fails on any
                         of these:
                         - a failed case, or a case with an error;
                         - a module with no results;
                         - a class that has @Test in source but no case in the
                           results. Such a class did not run: a filter, a crash
                           before it, or a module that was not built. Gradle
                           can exit 0 over it.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MODULES = ("library", "library-dynamic")

FLAG = re.compile(r'getArguments\(\)\s*\.getString\("([A-Za-z0-9_]+)"\)\s*==\s*"1"')
# Top-level classes only: a declaration at column 0. A nested helper declared
# above the tests (`private class Reading(...)` inside the test class) would
# otherwise take their @Test and name a class the results never contain.
CLASS = re.compile(
    r"^((?:(?:public|internal|private|open|abstract|final|data)\s+)*)"
    r"class\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)
TEST = re.compile(r"^[ \t]*@Test\b", re.M)


def _sources(kjui: Path, module: str) -> list[Path]:
    root = kjui / module / "src" / "androidTest"
    return sorted(root.rglob("*.kt")) if root.is_dir() else []


def flags(kjui: Path) -> list[str]:
    found: set[str] = set()
    for module in MODULES:
        for path in _sources(kjui, module):
            found |= set(FLAG.findall(path.read_text(encoding="utf-8")))
    return sorted(found)


def test_classes(kjui: Path, module: str) -> set[str]:
    """Simple names of the classes whose body holds an @Test.

    Each @Test is assigned to the last top-level `class` declared before it in
    the file. An abstract class runs only through its subclasses, so it is left
    out.
    """
    names: set[str] = set()
    for path in _sources(kjui, module):
        text = path.read_text(encoding="utf-8")
        decls = [(m.start(), m.group(2), "abstract" in m.group(1)) for m in CLASS.finditer(text)]
        for t in TEST.finditer(text):
            owner = [d for d in decls if d[0] < t.start()]
            if owner and not owner[-1][2]:
                names.add(owner[-1][1])
    return names


def _results(kjui: Path, module: str) -> list[Path]:
    root = kjui / module / "build" / "outputs" / "androidTest-results" / "connected"
    return sorted(root.rglob("TEST-*.xml")) if root.is_dir() else []


def judge(kjui: Path) -> int:
    problems: list[str] = []
    for module in MODULES:
        files = _results(kjui, module)
        declared = test_classes(kjui, module)
        passed = failed = skipped = 0
        failures: list[str] = []
        skips: list[str] = []
        seen: set[str] = set()
        cases = 0
        for path in files:
            for case in ET.parse(path).getroot().iter("testcase"):
                cases += 1
                cls = case.get("classname", "")
                name = f"{cls.rsplit('.', 1)[-1]}.{case.get('name', '')}"
                seen.add(cls.rsplit(".", 1)[-1])
                bad = case.find("failure")
                if bad is None:
                    bad = case.find("error")
                skip = case.find("skipped")
                if bad is not None:
                    failed += 1
                    first = (bad.get("message") or bad.text or "").strip().splitlines()
                    failures.append(f"{name}: {first[0][:160] if first else '(no message)'}")
                elif skip is not None:
                    skipped += 1
                    reason = (skip.get("message") or skip.text or "").strip().splitlines()
                    skips.append(f"{name}: {reason[0][:160] if reason else '(no reason)'}")
                else:
                    passed += 1
        # The breakdown must add up to the total, or a branch above dropped cases.
        assert passed + failed + skipped == cases, (module, passed, failed, skipped, cases)
        not_run = sorted(declared - seen)
        print(f"== {module}: {cases} case(s) from {len(files)} result file(s) — "
              f"{passed} passed, {failed} failed, {skipped} skipped; "
              f"classes with @Test in source {len(declared)}, seen in results "
              f"{len(declared & seen)}")
        for line in skips:
            print(f"   skipped  {line}")
        for line in failures:
            print(f"   FAILED   {line}")
        for cls in not_run:
            print(f"   NOT RUN  {cls} (has @Test in source, no case in the results)")
        if not files:
            problems.append(f"{module}: no results — the tests did not run, or the module was not built")
        if failed:
            problems.append(f"{module}: {failed} failed")
        if not_run:
            problems.append(f"{module}: {len(not_run)} class(es) with @Test did not run")
    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("flags", "judge"):
        print("usage: kjui_device_tests.py flags|judge <KotlinJsonUI checkout>", file=sys.stderr)
        return 2
    kjui = Path(argv[1])
    if not (kjui / "library").is_dir():
        print(f"error: {kjui} is not a KotlinJsonUI checkout (no library/)", file=sys.stderr)
        return 2
    if argv[0] == "flags":
        for name in flags(kjui):
            print(name)
        return 0
    return judge(kjui)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
