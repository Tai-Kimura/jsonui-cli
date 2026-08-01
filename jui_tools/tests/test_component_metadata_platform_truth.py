"""component_metadata.json platform claims vs. the real dispatch tables.

``shared/core/component_metadata.json`` feeds jsonui-mcp-server's
``lookup_component`` / ``search_components`` — its ``platforms`` block is
what an agent consults before writing ``type: X`` into a layout aimed at
platform P. A true-but-undispatched cell sends that agent straight into a
renderer fallback (sjui codegen: red "Unsupported component" Text;
SwiftJsonUI dynamic: red error box; kjui codegen: custom-component lookup
miss; rjui: *silent* plain-View degrade), so every cell must equal what
the dispatch tables actually accept. The 2026-08-01 truth audit (P18)
found 16 cells of drift, CircleView being declared on all five surfaces
while only the Kotlin dynamic runtime dispatches it.

One source of truth per facet:

  swift_generated   sjui_tools/lib/swiftui/converter_factory.rb   ``when '...'``
  kotlin_generated  kjui_tools/lib/compose/compose_builder.rb     ``when '...'``
  react             rjui_tools/lib/react/react_generator.rb       ``CONVERTERS``
  swift_dynamic     SwiftJsonUI Sources/.../Dynamic/DynamicComponentBuilder.swift
  kotlin_dynamic    KotlinJsonUI library-dynamic/.../DynamicView.kt

The two dynamic tables live in sibling library checkouts (the same layout
``jui generate attr-bindings`` vendoring assumes). When a checkout is
absent — a bare CI clone of jsonui-cli — those two facets are skipped;
the three in-repo facets are always enforced.

Semantic rule: an rjui ``CONVERTERS`` entry that maps a non-View type to
the generic ``ViewConverter`` (today: SafeAreaView) drops the component's
semantics entirely, so it does NOT count as support — the honest cell is
false. Mapping to a *specific* converter that implements the semantics
under another name (EditText -> TextFieldConverter, Toggle ->
SwitchConverter) does count.
"""
from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
METADATA = REPO_ROOT / "shared" / "core" / "component_metadata.json"
SJUI_FACTORY = REPO_ROOT / "sjui_tools" / "lib" / "swiftui" / "converter_factory.rb"
KJUI_BUILDER = REPO_ROOT / "kjui_tools" / "lib" / "compose" / "compose_builder.rb"
RJUI_GENERATOR = REPO_ROOT / "rjui_tools" / "lib" / "react" / "react_generator.rb"


def _sibling_repo(env_var: str, name: str) -> Path | None:
    """Resolve a library checkout: env override first, then ../<name>."""
    override = os.environ.get(env_var)
    if override:
        path = Path(override)
        return path if path.exists() else None
    path = REPO_ROOT.parent / name
    return path if path.exists() else None


SWIFT_DYNAMIC_BUILDER = None
_swift_repo = _sibling_repo("JSONUI_SWIFTJSONUI_PATH", "SwiftJsonUI")
if _swift_repo:
    _candidate = (
        _swift_repo / "Sources" / "SwiftJsonUI" / "Classes" / "SwiftUI"
        / "Dynamic" / "DynamicComponentBuilder.swift"
    )
    SWIFT_DYNAMIC_BUILDER = _candidate if _candidate.exists() else None

KOTLIN_DYNAMIC_VIEW = None
_kotlin_repo = _sibling_repo("JSONUI_KOTLINJSONUI_PATH", "KotlinJsonUI")
if _kotlin_repo:
    _candidate = (
        _kotlin_repo / "library-dynamic" / "src" / "main" / "kotlin"
        / "com" / "kotlinjsonui" / "dynamic" / "DynamicView.kt"
    )
    KOTLIN_DYNAMIC_VIEW = _candidate if _candidate.exists() else None


# ---------------------------------------------------------------------------
# Dispatch-table extraction


def sjui_codegen_types() -> set[str]:
    """``when 'A', 'B'`` spellings inside create_converter's case."""
    body = SJUI_FACTORY.read_text(encoding="utf-8").split("def create_converter", 1)[1]
    types: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped == "else" and types:
            break
        if stripped.startswith("when "):
            types.update(re.findall(r"'([^']+)'", stripped))
    return types


def kjui_codegen_types() -> set[str]:
    """``when 'A', 'B'`` spellings inside generate_component's case."""
    body = KJUI_BUILDER.read_text(encoding="utf-8").split("def generate_component", 1)[1]
    body = body.split("case component_type", 1)[1]
    types: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped == "else" and types:
            break
        if stripped.startswith("when "):
            types.update(re.findall(r"'([^']+)'", stripped))
    return types


def rjui_converter_map() -> dict[str, str]:
    """``'Type' => Converters::Klass`` entries of the CONVERTERS literal."""
    body = RJUI_GENERATOR.read_text(encoding="utf-8").split("CONVERTERS = {", 1)[1]
    body = body.split("}.freeze", 1)[0]
    return dict(re.findall(r"'(\w+)'\s*=>\s*Converters::(\w+)", body))


def rjui_supports(component: str, table: dict[str, str]) -> bool:
    """Mapped, and not the semantics-dropping generic-View degrade."""
    klass = table.get(component)
    if klass is None:
        return False
    return not (klass == "ViewConverter" and component != "View")


_SWIFT_CASE = re.compile(r'^\s*case ((?:"[a-z0-9]+",\s*)*"[a-z0-9]+"):\s*$')
# Leaf arms call FooConverter.convert(...); container arms construct a
# DynamicFooContainer(...) view directly.
_SWIFT_CONVERT = re.compile(r"\w+Converter\.convert\(|Dynamic\w+Container\(")


def swift_dynamic_types() -> set[str]:
    """Lowercased ``case "a", "b":`` arms whose body calls a converter."""
    lines = SWIFT_DYNAMIC_BUILDER.read_text(encoding="utf-8").splitlines()
    types: set[str] = set()
    for i, line in enumerate(lines):
        match = _SWIFT_CASE.match(line)
        if not match:
            continue
        lookahead = "".join(lines[i + 1 : i + 4])
        if _SWIFT_CONVERT.search(lookahead):
            types.update(re.findall(r'"([a-z0-9]+)"', match.group(1)))
    return types


_KOTLIN_ARM = re.compile(
    r'^\s*((?:"[a-z0-9]+"\s*,\s*)*"[a-z0-9]+")\s*->\s*Dynamic\w+Component\.create\('
)


def kotlin_dynamic_types() -> set[str]:
    """Lowercased ``"a", "b" -> DynamicXComponent.create(...)`` arms."""
    types: set[str] = set()
    for line in KOTLIN_DYNAMIC_VIEW.read_text(encoding="utf-8").splitlines():
        match = _KOTLIN_ARM.match(line)
        if match:
            types.update(re.findall(r'"([a-z0-9]+)"', match.group(1)))
    return types


def metadata_rows() -> dict[str, dict[str, bool]]:
    with open(METADATA, encoding="utf-8") as f:
        data = json.load(f)
    return {
        name: entry["platforms"]
        for name, entry in data.items()
        if not name.startswith("_") and isinstance(entry, dict)
    }


# ---------------------------------------------------------------------------
# Tests


class ParserSanity(unittest.TestCase):
    """A regex that silently matches nothing would vacuously pass the
    audit below — pin each extractor to known-stable sentinels first."""

    def test_sjui_extraction(self) -> None:
        types = sjui_codegen_types()
        self.assertGreater(len(types), 15, types)
        self.assertIn("Label", types)
        self.assertIn("Embed", types)

    def test_kjui_extraction(self) -> None:
        types = kjui_codegen_types()
        self.assertGreater(len(types), 15, types)
        self.assertIn("Label", types)
        self.assertIn("Embed", types)

    def test_rjui_extraction(self) -> None:
        table = rjui_converter_map()
        self.assertGreater(len(table), 15, table)
        self.assertEqual(table.get("Label"), "LabelConverter")
        self.assertEqual(table.get("View"), "ViewConverter")

    @unittest.skipUnless(SWIFT_DYNAMIC_BUILDER, "SwiftJsonUI checkout not found")
    def test_swift_dynamic_extraction(self) -> None:
        types = swift_dynamic_types()
        self.assertGreater(len(types), 15, types)
        self.assertIn("label", types)
        self.assertIn("embed", types)

    @unittest.skipUnless(KOTLIN_DYNAMIC_VIEW, "KotlinJsonUI checkout not found")
    def test_kotlin_dynamic_extraction(self) -> None:
        types = kotlin_dynamic_types()
        self.assertGreater(len(types), 15, types)
        self.assertIn("label", types)
        self.assertIn("embed", types)


class ComponentMetadataPlatformTruth(unittest.TestCase):
    """Every ``platforms`` cell equals its dispatch table, both directions:
    a true cell without a dispatch arm misleads agents into fallbacks, and
    a false cell with a dispatch arm hides a working component."""

    def _assert_facet(self, facet: str, supports) -> None:
        mismatches = []
        for name, declared in sorted(metadata_rows().items()):
            actual = supports(name)
            if bool(declared.get(facet)) != actual:
                mismatches.append(
                    f"  {name}.{facet}: declared={bool(declared.get(facet))} "
                    f"dispatch={actual}"
                )
        self.assertFalse(
            mismatches,
            "component_metadata.json diverges from the dispatch table for "
            f"'{facet}' — fix the metadata (or the dispatch) so both tell "
            "the same story:\n" + "\n".join(mismatches),
        )

    def test_swift_generated(self) -> None:
        types = sjui_codegen_types()
        self._assert_facet("swift_generated", lambda name: name in types)

    def test_kotlin_generated(self) -> None:
        types = kjui_codegen_types()
        self._assert_facet("kotlin_generated", lambda name: name in types)

    def test_react(self) -> None:
        table = rjui_converter_map()
        self._assert_facet("react", lambda name: rjui_supports(name, table))

    @unittest.skipUnless(SWIFT_DYNAMIC_BUILDER, "SwiftJsonUI checkout not found")
    def test_swift_dynamic(self) -> None:
        types = swift_dynamic_types()
        self._assert_facet("swift_dynamic", lambda name: name.lower() in types)

    @unittest.skipUnless(KOTLIN_DYNAMIC_VIEW, "KotlinJsonUI checkout not found")
    def test_kotlin_dynamic(self) -> None:
        types = kotlin_dynamic_types()
        self._assert_facet("kotlin_dynamic", lambda name: name.lower() in types)


if __name__ == "__main__":
    unittest.main()
