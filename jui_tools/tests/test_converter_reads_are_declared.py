"""Every attribute the three generators' converters read is declared for its component (2.3.22, ticket
rjui-textfield-autofocus-read-but-not-defined: rjui read TextField.autoFocus and nothing declared it, so `jui build` warned
"Unknown attribute" on a layout that used what the converter draws, and a warnings-0 gate could not write it).

The other direction — declared, and no converter reads it — is `jui conformance coverage` (coverage.json). This one reads
the same sources the same way (coverage.scan_reads: `attributes['x']` / `json_data['x']` / alias helpers / `case key`,
per component file), and holds what is left as a closed table: each entry names why it is not a layout attribute. Both
directions are red: a read the table does not hold, and an entry whose read is gone or is declared now.

Also checked here, the decisions of 2.3.22 that keep it closed:
  - a spelling a converter used to read as a fallback beside a declared attribute (retired_attribute_spellings.json)
    is read by no converter, and the name it points at is declared on its component;
  - an attribute declared for one or two platforms only (`platform` narrowed) is `warn_outside_mode`, so a layout that
    writes it on another platform is warned "<Platform> only", not silently dropped (an INFO a default build never
    prints).
"""
from __future__ import annotations

import json
from pathlib import Path

from jui_cli.conformance import coverage as cv

ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS = json.loads((ROOT / "shared/core/attribute_definitions.json").read_text(encoding="utf-8"))
RETIRED = json.loads((ROOT / "shared/core/retired_attribute_spellings.json").read_text(encoding="utf-8"))["spellings"]

# The converters a node of every type runs through: checked against what any component declares (a base converter
# reads fontColor for the Label it draws and for every other type).
BASES = {"ios": ["swiftui/views/base_view_converter.rb"], "web": ["react/converters/base_converter.rb"]}

INTERNAL = "a key the generator writes on the node itself, not a layout attribute"
NESTED = "a key of a nested object the component declares as one attribute (its properties are not attributes)"
DEFINITION = "a key of the attribute definitions themselves, read by the converter, not of the layout"

# (platform, component or base file, key) -> why. Closed: a new undeclared read is declared, renamed to the declared
# spelling, or argued here; an entry whose read is gone fails until it is removed.
NOT_ATTRIBUTES = {
    ("ios", "Button", "parent_orientation"): INTERNAL + " (view_converter hands each child its parent's orientation)",
    ("ios", "Label", "parent_orientation"): INTERNAL + " (as Button)",
    ("ios", "View", "parent_orientation"): INTERNAL + " (view_converter.rb writes child['parent_orientation'])",
    ("ios", "View", "_skip_trailing_spacer"): INTERNAL + " (the stack's own trailing Spacer decision)",
    ("web", "View", "_overlay"): INTERNAL + " (view_converter marks an overlay child 'stack')",
    ("ios", "SelectBox", "src"): NESTED + ": caretAttributes.src (selectbox_converter caret_literal)",
    ("ios", "Switch", "color"): NESTED + ": labelAttributes.color (toggle_converter)",
    ("ios", "TextField", "color"): NESTED + ": hintAttributes.color (textfield_converter)",
    ("ios", "TextField", "lineHeightMultiple"): NESTED + ": hintAttributes.lineHeightMultiple",
    ("ios", "TextView", "color"): NESTED + ": hintAttributes.color (textview_converter)",
    ("ios", "TextView", "lineHeightMultiple"): NESTED + ": hintAttributes.lineHeightMultiple",
    ("web", "SelectBox", "textAlign"): NESTED + ": labelAttributes.textAlign, which takes the base's text-align class off",
    ("ios", "base_view_converter.rb", "description"): DEFINITION + " (the glass definition's description)",
    ("ios", "base_view_converter.rb", "properties"): DEFINITION + " (the glass definition's shape enum)",
    ("web", "base_converter.rb", "_attribute_definitions"): DEFINITION + " (the config's definitions table)",
    ("web", "base_converter.rb", "_overlay"): INTERNAL + " (as View)",
    ("web", "base_converter.rb", "_parent_distribution"): INTERNAL + " (the parent's distribution, annotated per child)",
    ("web", "base_converter.rb", "_parent_orientation"): INTERNAL + " (the parent's orientation, annotated per child)",
}


def _canonical(component: str) -> str:
    section = DEFINITIONS.get(component)
    return section.get("_alias_of", component) if isinstance(section, dict) else component


def _declared(component: str) -> set:
    names = {k for k in DEFINITIONS.get(_canonical(component), {}) if not k.startswith("_")}
    return names | cv.alias_names(DEFINITIONS).get(_canonical(component), set())


def _undeclared_reads() -> set:
    common = _declared("common")
    anywhere = set().union(*(_declared(c) for c in DEFINITIONS if not c.startswith("_")))
    found = set()
    for platform, source in cv.SOURCE_ROOTS.items():
        reads = cv.scan_reads(ROOT / source, DEFINITIONS, platform)
        for component, keys in reads.items():
            if component == cv.SHARED:
                continue
            found |= {(platform, _canonical(component), k) for k in keys - _declared(component) - common}
        for base in BASES.get(platform, []):
            keys = cv._reads_in_source((ROOT / source / base).read_text(encoding="utf-8"))
            found |= {(platform, Path(base).name, k) for k in keys - anywhere}
    return found


def test_every_read_is_declared_or_named_in_the_closed_table():
    found = _undeclared_reads()
    unexplained = sorted(found - set(NOT_ATTRIBUTES))
    stale = sorted(set(NOT_ATTRIBUTES) - found)
    assert not unexplained, (
        "a converter reads an attribute no definition declares — declare it (narrowing `platform` if one face draws it,"
        f" with warn_outside_mode), read the declared spelling instead, or say here why it is not an attribute: {unexplained}")
    assert not stale, f"the table names a read that is gone or declared now — remove it: {stale}"


def test_the_scan_sees_the_case_that_opened_this():
    """Positive control: rjui's TextField reads autoFocus, and the scan counts that read as one (were the scan blind to
    the converters, the table above would be satisfied by an empty set)."""
    reads = cv.scan_reads(ROOT / cv.SOURCE_ROOTS["web"], DEFINITIONS, "web")
    assert "autoFocus" in reads["TextField"] and "autoFocus" in _declared("TextField")
    assert len(_undeclared_reads()) == len(NOT_ATTRIBUTES) > 0


def test_no_converter_reads_a_retired_spelling_and_each_points_at_a_declared_name():
    read_by = {}
    for platform, source in cv.SOURCE_ROOTS.items():
        for component, keys in cv.scan_reads(ROOT / source, DEFINITIONS, platform).items():
            read_by.setdefault(_canonical(component), set()).update((platform, k) for k in keys)
    assert set(RETIRED) <= {c for c in DEFINITIONS if not c.startswith("_")}, sorted(set(RETIRED) - set(DEFINITIONS))
    still_read, undeclared_target, declared_spelling = [], [], []
    for component, spellings in RETIRED.items():
        declared = _declared(component) | _declared("common")
        for spelling, target in spellings.items():
            still_read += [(p, component, spelling) for p, k in read_by.get(component, ()) if k == spelling]
            if target not in declared:
                undeclared_target.append((component, spelling, target))
            if spelling in declared:
                declared_spelling.append((component, spelling))
    assert not still_read, f"a converter still reads a retired spelling: {sorted(still_read)}"
    assert not undeclared_target, f"a retired spelling points at a name its component does not declare: {undeclared_target}"
    assert not declared_spelling, f"a retired spelling is declared again (the warning would never fire): {declared_spelling}"


# The attributes 2.3.22 declared for the faces that draw them (and those it declares for all): a layout written for
# another face is warned. Every other narrowed declaration predates this and keeps its own reasons.
NARROWED_IN_2_3_22 = {
    ("Blur", "intensity"), ("Button", "href"), ("CircleView", "size"), ("Collection", "flowAlignment"),
    ("GradientView", "angle"), ("GradientView", "gradientType"), ("GradientView", "orientation"),
    ("IconLabel", "contentDescription"), ("IconLabel", "fontWeight"), ("IconLabel", "strikethrough"),
    ("IconLabel", "underline"), ("Image", "size"), ("Indicator", "halfSpinner"), ("Indicator", "size"),
    ("Indicator", "strokeWidth"), ("Indicator", "trackColor"), ("NetworkImage", "circle"), ("NetworkImage", "size"),
    ("Progress", "maximumValue"), ("Progress", "progressHeight"), ("ScrollView", "contentInset"), ("Segment", "fontSize"),
    ("SelectBox", "cancelButtonBackgroundColor"), ("SelectBox", "cancelButtonTextColor"), ("Slider", "thumbTintColor"),
    ("TextField", "editable"), ("TextField", "name"), ("TextField", "outlined"), ("TextView", "maxLines"),
    ("TextView", "name"), ("Web", "allowCamera"), ("Web", "allowDownloads"), ("Web", "allowGeolocation"),
    ("Web", "allowMicrophone"), ("Web", "allowModals"), ("Web", "allowPopupsToEscapeSandbox"), ("Web", "allowZoom"),
    ("Web", "allowsFullScreen"), ("Web", "allowsInlineMediaPlayback"), ("Web", "javaScriptCanOpenWindowsAutomatically"),
    ("Web", "javaScriptEnabled"), ("Web", "lazyLoad"), ("Web", "scrollEnabled"), ("Web", "title"), ("Web", "userAgent"),
    ("common", "zIndex"),
}


def test_the_attributes_declared_for_one_face_warn_on_the_others():
    tags = {"ios": "swift", "android": "kotlin", "web": "react"}
    wrong = []
    for component, attribute in sorted(NARROWED_IN_2_3_22):
        defn = DEFINITIONS[component][attribute]
        platforms = set(defn["platform"] if isinstance(defn["platform"], list) else [defn["platform"]])
        reading = {tags[p] for p, source in cv.SOURCE_ROOTS.items()
                   if attribute in cv.scan_reads(ROOT / source, DEFINITIONS, p).get(component if component != "common" else cv.SHARED, set())
                   or (component == "common" and any(attribute in cv._reads_in_source((ROOT / source / b).read_text(encoding="utf-8")) for b in BASES.get(p, [])))}
        if defn.get("warn_outside_mode") is not True or platforms != reading:
            wrong.append((component, attribute, sorted(platforms), sorted(reading), defn.get("warn_outside_mode")))
    assert not wrong, f"declared platforms differ from the faces that read it, or no warning elsewhere: {wrong}"
