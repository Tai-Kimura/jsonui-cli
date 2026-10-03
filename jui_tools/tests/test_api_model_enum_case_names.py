"""API model enums: one distinct case name per value on every face, or a build error that says so.

jui-api-model-swift-negative-integer-enum-cases-collide: an integer enum
[-1, 0, 1] gave Swift ``value1`` / ``value0`` / ``value1`` — the default case
name ``value_-1`` lost its sign in snake_to_camel — so 7 generated Swift files
did not compile (rc 65) while jui build reported warning 0. Kotlin kept the
sign as a second underscore (``VALUE__1``). A number's minus sign is spelled
``minus`` now on both (``valueMinus1`` / ``VALUE_MINUS_1``); TS emits the
values themselves (``-1 | 0 | 1``) and names no case.

The same naming step collapsed other values too (measured on 1.9.5): string
values that differ in case only (``active`` / ``ACTIVE``) or in separator
only (``foo_bar`` / ``fooBar`` / ``foo-bar``), and values that are no name at
all (``+``, ``""``, ``1st``, ``a.b``). Those cannot be named by a rule without
guessing, so the build stops on them by name and points at
``x-enum-varnames``.

The conservation law each face is held to: distinct emitted case names ==
values. And the faces are held to each other: Swift's camelCase and Kotlin's
UPPER_SNAKE name the same words, and TS's union is the value list.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from functools import lru_cache
from pathlib import Path

from jui_cli.core.openapi_loader import OpenAPILoadError, parse_swagger
from jui_cli.generators.android_api_model_generator import AndroidApiModelGenerator, AndroidApiPlatformConfig
from jui_cli.generators.ios_api_model_generator import IosApiModelGenerator, IosApiPlatformConfig
from jui_cli.generators.web_api_model_generator import WebApiModelGenerator, WebApiPlatformConfig


def _doc(schemas: dict) -> dict:
    return {"openapi": "3.0.3", "info": {"title": "T", "version": "1.0.0"}, "components": {"schemas": schemas}}


# Enums every face can name: the values, and what each face must call them.
NAMEABLE = {
    "Trend": {"type": "integer", "enum": [-1, 0, 1]},
    "Offset": {"type": "integer", "enum": [-10, -1, 1, 10]},
    "Status": {"type": "string", "enum": ["active", "inactive", "on_hold"]},
    "Sign": {"type": "string", "enum": ["-1", "up"]},
    "Severity": {"type": "integer", "enum": [-1, 1], "x-enum-varnames": ["low", "high"]},
    "Visibility": {"type": "string", "enum": ["public", "private", "internal"]},
}

# Values the naming step cannot keep apart (or cannot name), measured on
# 1.9.5, and the faces that stop on each. Swift keeps `active` / `ACTIVE`
# apart (`active` / `aCTIVE`); Kotlin's UPPER_SNAKE does not.
BOTH = ("Swift", "Kotlin")
UNNAMEABLE = {
    "CaseOnly": ({"type": "string", "enum": ["active", "ACTIVE"]}, ("Kotlin",)),
    "Separators": ({"type": "string", "enum": ["foo_bar", "fooBar", "foo-bar"]}, BOTH),
    "Symbols": ({"type": "string", "enum": ["+", "*"]}, BOTH),
    "Blank": ({"type": "string", "enum": ["", "x"]}, BOTH),
    "LeadingDigit": ({"type": "string", "enum": ["1st", "2nd"]}, BOTH),
    "Dotted": ({"type": "string", "enum": ["a.b", "c"]}, BOTH),
    "DigitString": ({"type": "string", "enum": ["-1", "1"]}, BOTH),
}


def _generators(tmp: Path):
    ios = IosApiModelGenerator(IosApiPlatformConfig(sources_root=tmp))
    android = AndroidApiModelGenerator(AndroidApiPlatformConfig(
        sources_root=tmp, domain_package="com.example.model",
        dto_package="com.example.model.generated", serializer="none"))
    web = WebApiModelGenerator(WebApiPlatformConfig(sources_root=tmp, model_dir="models", dto_subdir="generated"))
    return ios, android, web


def _swift_cases(src: str) -> list[str]:
    return re.findall(r"^\s+case (\S+?)(?: =|$)", src, re.M)


def _kotlin_cases(src: str) -> list[str]:
    return re.findall(r"^\s+(?:@SerialName\(\S+\) )?(`?\w+`?)\(", src, re.M)


def _ts_values(src: str) -> list[str]:
    union = re.search(r"export type \w+ = (.*);", src).group(1)
    return [v.strip().strip('"') for v in union.split("|")]


def _letters(name: str) -> str:
    """A case name without its casing and separators: what both faces must agree on."""
    return name.strip("`").replace("_", "").lower()


class NameableEnumsTests(unittest.TestCase):
    def setUp(self):
        self.doc = parse_swagger(_doc(NAMEABLE), "test.json")
        self.tmp = tempfile.TemporaryDirectory()
        self.ios, self.android, self.web = _generators(Path(self.tmp.name))
        self.by_name = {e.name: e for e in self.doc.enums}

    def tearDown(self):
        self.tmp.cleanup()

    def _sources(self, name):
        enum = self.by_name[name]
        return (self.ios.generate_enum_source(enum, self.doc),
                self.android.generate_enum_source(enum, self.doc),
                self.web.generate_enum_source(enum, self.doc))

    def test_every_face_names_each_value_once(self):
        # Conservation: distinct case names == values, on each face.
        self.assertEqual(set(self.by_name), set(NAMEABLE))
        for name, schema in NAMEABLE.items():
            swift, kotlin, ts = self._sources(name)
            n = len(schema["enum"])
            self.assertEqual(len(set(_swift_cases(swift))), n, f"{name}: {_swift_cases(swift)}")
            self.assertEqual(len(set(_kotlin_cases(kotlin))), n, f"{name}: {_kotlin_cases(kotlin)}")
            self.assertEqual(_ts_values(ts), [str(v) for v in schema["enum"]], name)

    def test_the_faces_name_the_same_words(self):
        for name in NAMEABLE:
            swift, kotlin, _ = self._sources(name)
            self.assertEqual([_letters(s) for s in _swift_cases(swift)],
                             [_letters(k) for k in _kotlin_cases(kotlin)], name)

    def test_a_minus_sign_is_spelled_minus(self):
        swift, kotlin, ts = self._sources("Trend")
        # Through 1.9.5: `case value1 = -1` beside `case value1 = 1`, and VALUE__1(-1).
        self.assertIn("case valueMinus1 = -1", swift)
        self.assertIn("case value1 = 1", swift)
        self.assertIn("VALUE_MINUS_1(-1)", kotlin)
        self.assertIn("-1 | 0 | 1", ts)
        # A string value "-1": through 1.9.5 Swift named it `1` (no identifier).
        swift, kotlin, _ = self._sources("Sign")
        self.assertIn('case minus1 = "-1"', swift)
        self.assertIn('MINUS_1("-1")', kotlin)

    def test_declared_varnames_are_kept(self):
        # Control: x-enum-varnames names the cases; no rule touches them.
        swift, kotlin, _ = self._sources("Severity")
        self.assertIn("case low = -1", swift)
        self.assertIn("LOW(-1)", kotlin)


class UnnameableEnumsTests(unittest.TestCase):
    def test_the_build_stops_on_each_by_name(self):
        doc = parse_swagger(_doc({k: v for k, (v, _) in UNNAMEABLE.items()}), "test.json")
        self.assertEqual({e.name for e in doc.enums}, set(UNNAMEABLE))
        with tempfile.TemporaryDirectory() as tmp:
            ios, android, _ = _generators(Path(tmp))
            for enum in doc.enums:
                stops = UNNAMEABLE[enum.name][1]
                for face, gen in (("Swift", ios), ("Kotlin", android)):
                    with self.subTest(enum=enum.name, face=face):
                        if face not in stops:
                            gen.generate_enum_source(enum, doc)
                            continue
                        with self.assertRaises(OpenAPILoadError) as ctx:
                            gen.generate_enum_source(enum, doc)
                        self.assertEqual(ctx.exception.code, "enum-case-names")
                        self.assertIn(f"Enum '{enum.name}' ({face})", str(ctx.exception))
                        self.assertIn("x-enum-varnames", str(ctx.exception))

    def test_varnames_name_them(self):
        # Control: the same values named by x-enum-varnames build.
        named = {k: dict(v, **{"x-enum-varnames": [f"v{i}" for i in range(len(v["enum"]))]}) for k, (v, _) in UNNAMEABLE.items()}
        doc = parse_swagger(_doc(named), "test.json")
        with tempfile.TemporaryDirectory() as tmp:
            ios, android, _ = _generators(Path(tmp))
            for enum in doc.enums:
                ios.generate_enum_source(enum, doc)
                android.generate_enum_source(enum, doc)


FETCH_SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "fetch_kotlin_compiler_jars.sh"
FETCH_HINT = "bash .github/scripts/fetch_kotlin_compiler_jars.sh"


def _pinned(script: Path = FETCH_SCRIPT) -> dict[tuple[str, str], str]:
    """The versions CI compiles with — the fetch script's `jars=(...)` list (group, artifact, version, sha256)."""
    if not script.is_file():
        return {}
    block = re.search(r"^jars=\((.*?)^\)", script.read_text(), re.M | re.S)
    rows = re.findall(r'"(\S+) (\S+) (\S+) [0-9a-f]{64}"', block.group(1)) if block else []
    return {(group, artifact): version for group, artifact, version in rows}


def _pinned_jar(home: Path, group: str, artifact: str, pinned: dict[tuple[str, str], str]) -> str | None:
    """The jar at its pinned version, or None — an exact version, never the newest present
    (until 1.9.10 this took `sorted(...)[-1]`: 2.4.20 beside a pinned 2.1.0, and 1.9 over 1.10 as strings)."""
    version = pinned.get((group, artifact))
    if version is None:
        return None
    found = sorted((home / "caches" / "modules-2" / "files-2.1" / group / artifact / version).glob(f"*/{artifact}-{version}.jar"))
    return str(found[0]) if found else None


@lru_cache(maxsize=1)
def _kotlin_compiler():
    """java + the Kotlin compiler at the versions CI pins, as kjui_tools' spec/support/kotlin_compiler.rb takes them.

    (java, compiler classpath, stdlib, compiler version), or (None, reason) when a compile cannot be attempted."""
    home = Path(os.environ.get("GRADLE_USER_HOME", Path.home() / ".gradle"))
    pinned = _pinned()
    names = [("org.jetbrains.kotlin", "kotlin-compiler-embeddable"), ("org.jetbrains.kotlin", "kotlin-stdlib"),
             ("org.jetbrains.kotlin", "kotlin-reflect"), ("org.jetbrains.kotlinx", "kotlinx-coroutines-core-jvm"),
             ("org.jetbrains", "annotations"), ("org.jetbrains.intellij.deps", "trove4j")]
    jars = {name: _pinned_jar(home, *name, pinned) for name in names}
    missing = [f"{g}:{a}:{pinned.get((g, a))}" for (g, a), j in jars.items() if j is None]
    java = next((j for j in ("/opt/homebrew/opt/openjdk@17/bin/java", shutil.which("java")) if j and os.path.exists(j)), None)
    if missing:
        return None, f"not in the Gradle cache at the pinned version: {', '.join(missing)} — fetch: {FETCH_HINT}"
    if java is None:
        return None, "no java"
    version = pinned[("org.jetbrains.kotlin", "kotlin-compiler-embeddable")]
    return java, ":".join(jars.values()), jars[("org.jetbrains.kotlin", "kotlin-stdlib")], version


class GeneratedSourceCompilesTests(unittest.TestCase):
    """The names compile — `swiftc -typecheck` (``-parse`` does not see a redeclaration) and kotlinc."""

    def _write(self, tmp: Path, face: str):
        doc = parse_swagger(_doc(NAMEABLE), "test.json")
        ios, android, _ = _generators(tmp)
        paths = []
        for enum in doc.enums:
            if face == "swift":
                p = tmp / f"{enum.name}.swift"
                p.write_text(ios.generate_enum_source(enum, doc))
            else:
                p = tmp / f"{enum.name}.kt"
                p.write_text(android.generate_enum_source(enum, doc))
            paths.append(str(p))
        return paths

    @unittest.skipUnless(shutil.which("swiftc"), "swiftc not installed")
    def test_swift_typechecks(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write(Path(tmp), "swift")
            r = subprocess.run(["swiftc", "-typecheck", *paths], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_kotlin_compiles(self):
        found = _kotlin_compiler()
        if found[0] is None:
            self.skipTest(found[1])
        java, compiler_cp, stdlib, version = found
        print(f"[kotlinc] kotlin-compiler-embeddable {version} on {java}")
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write(Path(tmp), "kotlin")
            r = subprocess.run([java, "-cp", compiler_cp, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                                "-no-stdlib", "-cp", stdlib, "-d", str(Path(tmp) / "out"), *paths],
                               capture_output=True, text=True)
            errors = [l for l in (r.stdout + r.stderr).splitlines() if "error:" in l]
            self.assertEqual(errors, [], f"kotlin-compiler-embeddable {version}")
            self.assertTrue(list((Path(tmp) / "out").rglob("*.class")), "kotlinc wrote no class")


class PinnedResolverTests(unittest.TestCase):
    """The resolver takes the pinned version, not the newest present."""

    def _place(self, home: Path, group: str, artifact: str, version: str) -> None:
        d = home / "caches" / "modules-2" / "files-2.1" / group / artifact / version / "f00d"
        d.mkdir(parents=True)
        (d / f"{artifact}-{version}.jar").write_bytes(b"")

    def test_reads_the_fetch_scripts_pins(self):
        pinned = _pinned()
        self.assertEqual(pinned[("org.jetbrains.kotlin", "kotlin-compiler-embeddable")], "2.1.0")
        self.assertEqual(len(pinned), len(re.findall(r'^\s+"\S+ \S+ \S+ [0-9a-f]{64}"$', FETCH_SCRIPT.read_text(), re.M)))

    def test_takes_the_pinned_compiler_beside_a_newer_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._place(home, "org.jetbrains.kotlin", "kotlin-compiler-embeddable", "2.4.20")
            self._place(home, "org.jetbrains.kotlin", "kotlin-compiler-embeddable", "2.1.0")
            got = _pinned_jar(home, "org.jetbrains.kotlin", "kotlin-compiler-embeddable", _pinned())
            self.assertTrue(got.endswith("kotlin-compiler-embeddable-2.1.0.jar"), got)

    def test_takes_1_10_over_1_9_when_1_10_is_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._place(home, "g", "lib", "1.9")
            self._place(home, "g", "lib", "1.10")
            self.assertTrue(_pinned_jar(home, "g", "lib", {("g", "lib"): "1.10"}).endswith("lib-1.10.jar"))
            self.assertTrue(_pinned_jar(home, "g", "lib", {("g", "lib"): "1.9"}).endswith("lib-1.9.jar"))

    def test_finds_nothing_when_only_another_version_is_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self._place(home, "org.jetbrains.kotlin", "kotlin-compiler-embeddable", "2.4.20")
            self.assertIsNone(_pinned_jar(home, "org.jetbrains.kotlin", "kotlin-compiler-embeddable", _pinned()))


if __name__ == "__main__":
    unittest.main()
