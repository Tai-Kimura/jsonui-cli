"""Cross-platform frame parity (``jui conformance gate --frame-parity``).

Per-platform baselines compare a platform with its own past, and control diff
asks only whether an attribute changed the picture. Neither asks whether the
platforms drew a view in the same place: Android drew align*View targets at
0 / 85 where iOS and web drew 120 / 145, and the gate was green from the first
bake (ticket conformance-passes-a-wrong-layout-geometry-is-never-compared-
across-platforms). This module compares the frames each driver records beside
a visual fixture's screenshot (``frames.schema.json``, RESULTS_SCHEMA.md
``frames``), id by id, across platforms.

The roots differ: the CI Android emulator is a landscape tablet, iOS a
portrait phone, web a 1024 x 768 page. A frame relative to the root's origin
is therefore the same number on every platform only for a view placed from
the root's top / left edge. Each axis is judged in the four readings a layout
can mean, and agrees if any one of them agrees (:func:`axis_agrees`): placed
from the near edge, from the far edge, centred, or stretched between both.
A wrong placement fails all four: Android's alignTopView target is 0 from the
top where the others are 120, and nowhere near the bottom or the centre
either, because the roots' heights differ.

Nothing that cannot be compared passes silently. Each reason has its own
count in :class:`FrameParityResult.not_compared`, and the ones that name a
platform and an id (an id the frames file of one platform lacks, a duplicate,
a clipped frame) list them.

Disagreements are judged against ``frame_parity.json``, the same ratchet as
``cross_effect.json``: an entry accepts one (fixture, id) disagreement with a
reason and records which platforms are the outliers, so a change in the
measurement makes the entry stale rather than silently still accepted.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

FRAMES_SCHEMA_VERSION = 1
SOURCES = frozenset({"xcuielement-frame", "xcuielement-layout-probe", "a11y-node-bounds",
                     "get-bounding-client-rect", "compose-layout-coordinates"})
PLATFORMS = ("ios", "android", "web")
LEDGER_NAME = "frame_parity.json"

#: THE tolerance, in layout units (iOS pt, Android dp, web CSS px), on every
#: edge and size. Declared here and nowhere else (the schema leaves it out).
#: Why 1.5: frames are layout-engine numbers that reach the driver through
#: device pixels. iOS rounds to 1/3 pt, the CI Android tablet to 1/2 dp at its
#: density, Chromium to sub-pixel CSS px, and drivers write 2 decimals, so two
#: correct renders of a declared integer length can differ by up to about 1
#: unit after both sides round. 1.5 keeps that out. The defect this exists for
#: was 120 units off (alignTopView) and the smallest real miss measured so far
#: is 9 units (alignTopOfView, as a screenshot hamming distance of 9 bits), so a
#: real misplacement is far outside it. Fractions of the root are not used:
#: the roots differ between platforms by design, so a percentage of one root
#: is a different length on another.
TOLERANCE = 1.5

#: Platforms whose drivers write frames. A declared platform whose visual
#: fixture has no frames fails the gate; an undeclared one that writes frames
#: gets a notice to join. Absence of frames must be a named refusal, not a
#: silent state: the run where a driver stops writing frames looks exactly like
#: the run before any driver started (same reasoning as EXPECTED_WEB_MARKER_HOSTS
#: in gate.py). Grow this in the commit that teaches a driver to write frames.
EXPECTED_FRAME_HOSTS: frozenset[str] = frozenset({
    # conformance/hosts/web/scripts/run.ts writes frames beside every
    # screenshot from 2026-10-05.
    "web",
    # KotlinJsonUI conformance-host (ConformanceFrames, compose layout
    # coordinates), from the 2.43.5 train.
    "android",
    # SwiftJsonUI ConformanceHost (canvas-relative XCUIElement frames, the
    # framesUnrecorded reason for a root that does not fill the canvas).
    "ios",
})

# not-compared reasons, each counted on its own line
NO_DECLARED_IDS = "fixture declares no id besides root"
NO_FRAMES_FILE = "platform wrote no frames file for this fixture"
DRIVER_UNRECORDED = "driver could not record frames (results[].framesUnrecorded)"
UNREADABLE = "frames file unreadable or not the schema"
TOO_FEW_PLATFORMS = "fewer than two platforms have frames for this fixture"
ID_ABSENT = "frames file present, declared id absent"
DUPLICATE = "id found on more than one element"
CLIPPED = "frame clipped at the screen edge"
FALLBACK = "driver read the id by a fallback (frames[].fallbacks)"
ROOT_ABSENT = "frames file has no usable root box (clipped, or no root element)"


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def _frame_errors(frame, where: str) -> list[str]:
    if not isinstance(frame, dict):
        return [f"{where}: not an object"]
    errors = []
    allowed = {"x", "y", "width", "height", "clipped"}
    extra = set(frame) - allowed
    if extra:
        errors.append(f"{where}: unknown key(s) {sorted(extra)}")
    for key in ("x", "y", "width", "height"):
        value = frame.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{where}.{key}: not a number")
        elif key in ("width", "height") and value < 0:
            errors.append(f"{where}.{key}: negative")
    if "clipped" in frame and frame["clipped"] is not True:
        errors.append(f"{where}.clipped: must be true or absent")
    return errors


def validate(doc) -> list[str]:
    """The schema's rules (frames.schema.json), checked without a schema library.

    The test suite holds this to the schema file key by key, so the two cannot
    drift: a key the schema adds and this does not know fails a test.
    """
    if not isinstance(doc, dict):
        return ["not an object"]
    errors = []
    allowed = {"schemaVersion", "fixture", "platform", "source", "density", "root", "frames", "duplicates",
               "fallbacks"}
    extra = set(doc) - allowed
    if extra:
        errors.append(f"unknown key(s) {sorted(extra)}")
    for key in ("schemaVersion", "fixture", "platform", "source", "root", "frames"):
        if key not in doc:
            errors.append(f"missing {key}")
    if "schemaVersion" in doc and doc["schemaVersion"] != FRAMES_SCHEMA_VERSION:
        errors.append(f"schemaVersion {doc['schemaVersion']!r} is not {FRAMES_SCHEMA_VERSION}")
    if "fixture" in doc and not (isinstance(doc["fixture"], str) and doc["fixture"]):
        errors.append("fixture: not a non-empty string")
    if "platform" in doc and doc["platform"] not in PLATFORMS:
        errors.append(f"platform {doc['platform']!r} is not one of {list(PLATFORMS)}")
    if "source" in doc and doc["source"] not in SOURCES:
        errors.append(f"source {doc['source']!r} is not one of {sorted(SOURCES)}")
    if "density" in doc:
        d = doc["density"]
        if isinstance(d, bool) or not isinstance(d, (int, float)) or d <= 0:
            errors.append("density: not a positive number")
    if "root" in doc:
        errors.extend(_frame_errors(doc["root"], "root"))
    frames = doc.get("frames")
    if "frames" in doc:
        if not isinstance(frames, dict):
            errors.append("frames: not an object")
        else:
            if "root" not in frames:
                errors.append("frames: no root")
            for name, frame in frames.items():
                if not isinstance(name, str) or not name:
                    errors.append("frames: an empty id")
                errors.extend(_frame_errors(frame, f"frames.{name}"))
    if "fallbacks" in doc:
        fb = doc["fallbacks"]
        if not isinstance(fb, list) or not all(isinstance(d, str) and d for d in fb) or len(set(fb)) != len(fb):
            errors.append("fallbacks: not a list of distinct ids")
    if "duplicates" in doc:
        dups = doc["duplicates"]
        if not isinstance(dups, list) or not all(isinstance(d, str) and d for d in dups):
            errors.append("duplicates: not a list of ids")
        elif len(set(dups)) != len(dups):
            errors.append("duplicates: repeated id")
    return errors


def read_frames(path: Path) -> tuple[dict | None, list[str]]:
    """``(doc, errors)``; ``doc`` is None when the file cannot be used."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ["no such file"]
    except (OSError, ValueError) as exc:
        return None, [f"unreadable: {exc}"]
    errors = validate(doc)
    return (None if errors else doc), errors


#: Weight keys and the axis they divide (`weight` is widthWeight's shorthand).
WEIGHT_AXES = {"weight": "x", "widthWeight": "x", "heightWeight": "y"}


def weighted_axes(layout) -> dict[str, set[str]]:
    """``{id: axes}`` for every declared id whose own node or an ancestor
    declares a weight: on those axes the declared readings are the two a
    weight produces — PROPORTIONAL to the root (see :func:`proportional_agrees`)
    when the weights share the whole root, STRETCHED (the same gap at both
    ends) when fixed-size siblings take their part first — and nothing else. An id after
    a weighted sibling is not included — a fixed-size view pushed to the far
    edge is placed from that edge, not proportionally."""
    out: dict[str, set[str]] = {}

    def walk(node, inherited: frozenset) -> None:
        if isinstance(node, dict):
            own = {axis for key, axis in WEIGHT_AXES.items() if node.get(key) not in (None, 0, "0")}
            axes = inherited | own
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id and node_id != "root" and axes:
                out.setdefault(node_id, set()).update(axes)
            for key, value in node.items():
                if key != "_generated":
                    walk(value, frozenset(axes))
        elif isinstance(node, list):
            for item in node:
                walk(item, inherited)

    walk(layout, frozenset())
    return out


def proportional_agrees(start_a: float, size_a: float, root_a: float,
                        start_b: float, size_b: float, root_b: float) -> bool:
    """The declared reading of a weighted axis: the start is the same fraction
    of the root on both, and the size is either the same fraction (the
    weighted view itself) or the same length (a fixed-size child inside it).
    Compared in b's units: a's numbers scaled by root_b / root_a."""
    if root_a <= 0 or root_b <= 0:
        return False
    scale = root_b / root_a
    return _near(start_a * scale, start_b) and (_near(size_a * scale, size_b) or _near(size_a, size_b))


def declared_ids(layout) -> list[str]:
    """Every ``id`` a layout declares, in document order, ``root`` excluded."""
    out: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id and node_id != "root" and node_id not in out:
                out.append(node_id)
            for key, value in node.items():
                if key != "_generated":
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(layout)
    return out


# --------------------------------------------------------------------------- #
# Comparing
# --------------------------------------------------------------------------- #


def _near(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE


#: The readings, in the order a report names the one that held. `proportional`
#: is never one of the alternatives an axis may agree by: it is the declared
#: reading of a weighted axis, required there and only there (measure()). The near
#: edge first, because that is the reading a root-relative frame states
#: directly. An agreement held ONLY by a later reading is the one to check
#: against the declaration — roots of a lucky size can let a wrong placement
#: through the far edge or the centre.
READINGS = ("near", "proportional", "stretched", "centred", "far")


def axis_readings(start_a: float, size_a: float, root_a: float,
                  start_b: float, size_b: float, root_b: float) -> frozenset[str]:
    """Which readings put both frames in the same place on one axis.

    Each frame is relative to its own root (origin and size). From the near
    edge, from the far edge, centred in the root, or stretched between both
    edges. When the roots are the same size the four collapse to "same start,
    same size".
    """
    same_size = _near(size_a, size_b)
    end_gap_a = root_a - (start_a + size_a)
    end_gap_b = root_b - (start_b + size_b)
    held = set()
    if same_size and _near(start_a, start_b):
        held.add("near")
    if same_size and _near(end_gap_a, end_gap_b):
        held.add("far")
    if same_size and _near(start_a + size_a / 2 - root_a / 2, start_b + size_b / 2 - root_b / 2):
        held.add("centred")
    if _near(start_a, start_b) and _near(end_gap_a, end_gap_b):
        held.add("stretched")
    return frozenset(held)


def axis_agrees(start_a: float, size_a: float, root_a: float,
                start_b: float, size_b: float, root_b: float) -> bool:
    """Agrees when any reading holds (:func:`axis_readings`)."""
    return bool(axis_readings(start_a, size_a, root_a, start_b, size_b, root_b))


def frame_readings(a: dict, root_a: dict, b: dict, root_b: dict) -> tuple[frozenset, frozenset]:
    """``(x readings, y readings)`` that hold for two frames."""
    return (axis_readings(a["x"], a["width"], root_a["width"], b["x"], b["width"], root_b["width"]),
            axis_readings(a["y"], a["height"], root_a["height"], b["y"], b["height"], root_b["height"]))


def frames_agree(a: dict, root_a: dict, b: dict, root_b: dict) -> bool:
    x, y = frame_readings(a, root_a, b, root_b)
    return bool(x) and bool(y)


def outliers(agree: dict[tuple[str, str], bool], platforms: Sequence[str]) -> list[str]:
    """The platforms that disagree, given pairwise agreement.

    A platform that agrees with nobody while some other pair agrees is the
    outlier. With no agreeing pair at all, every platform is named: there is
    no majority to measure against.
    """
    agreeing = {p: [q for q in platforms if q != p and agree.get(tuple(sorted((p, q))), False)]
                for p in platforms}
    if all(agreeing[p] for p in platforms):
        return []
    lonely = [p for p in platforms if not agreeing[p]]
    if len(lonely) < len(platforms):
        return lonely
    return list(platforms)


@dataclass
class Disagreement:
    fixture: str
    id: str
    outliers: list[str]
    frames: dict[str, dict]
    roots: dict[str, dict]

    @property
    def key(self) -> tuple[str, str]:
        return (self.fixture, self.id)

    def table(self) -> str:
        cells = []
        for p in sorted(self.frames):
            f = self.frames[p]
            r = self.roots[p]
            mark = "*" if p in self.outliers else ""
            cells.append(f"{p}{mark} x={f['x']:g} y={f['y']:g} w={f['width']:g} h={f['height']:g} "
                         f"(root {r['width']:g}x{r['height']:g})")
        return f"{self.fixture} #{self.id}: " + " | ".join(cells)


@dataclass
class FrameParityResult:
    platforms: list[str]
    fixtures_compared: int = 0
    #: (fixture, id) pairs compared on two or more platforms that agree
    agreed: list[tuple[str, str]] = field(default_factory=list)
    #: (fixture, id) -> {"x": readings, "y": readings} that held for EVERY
    #: compared pair of platforms — the reading the agreement rests on
    readings: dict[tuple[str, str], dict[str, frozenset]] = field(default_factory=dict)
    disagreed: list[Disagreement] = field(default_factory=list)
    #: reason -> count, every reason on its own line
    not_compared: Counter = field(default_factory=Counter)
    #: reason -> named items ("<platform>: <fixture> #<id>" or "<platform>: <fixture>")
    named: dict[str, list[str]] = field(default_factory=dict)
    #: platform -> fixtures with a frames file this run (for the declaration check)
    frames_by_platform: dict[str, int] = field(default_factory=dict)
    #: platform -> visual fixtures in scope that had no frames file
    missing_by_platform: dict[str, int] = field(default_factory=dict)
    #: "<platform>: <fixture> #<id>" read by a driver fallback — the gate fails on any
    fallbacks: list[str] = field(default_factory=list)

    def _name(self, reason: str, item: str) -> None:
        self.not_compared[reason] += 1
        self.named.setdefault(reason, []).append(item)


def _frames_path(conformance_dir: Path, entry: dict) -> Path | None:
    rel = entry.get("frames") if isinstance(entry, dict) else None
    return (conformance_dir / rel) if isinstance(rel, str) and rel else None


def measure(
    conformance_dir: Path,
    manifest: dict,
    results: dict[str, dict[str, dict]],
    platforms: Sequence[str],
) -> FrameParityResult:
    """Compare frames across *platforms*.

    *results* is ``{platform: {fixture_id: result entry}}``. Only visual
    fixtures are judged, and only on the platforms the manifest scopes each
    one to.
    """
    conformance_dir = Path(conformance_dir)
    selected = [p for p in dict.fromkeys(platforms)]
    out = FrameParityResult(platforms=selected)

    for fixture in manifest.get("fixtures", []):
        if fixture.get("class") != "visual":
            continue
        fid = fixture["id"]
        scope = [p for p in selected if p in (fixture.get("platforms") or [])]
        if len(scope) < 2:
            continue
        layout_rel = fixture.get("layout")
        try:
            layout = json.loads((conformance_dir / layout_rel).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            layout = None
        ids = declared_ids(layout) if layout is not None else []
        weighted = weighted_axes(layout) if layout is not None else {}
        if not ids:
            out._name(NO_DECLARED_IDS, fid)
            continue

        docs: dict[str, dict] = {}
        for p in scope:
            entry = results.get(p, {}).get(fid)
            path = _frames_path(conformance_dir, entry) if entry else None
            unrecorded = entry.get("framesUnrecorded") if isinstance(entry, dict) else None
            if path is not None and unrecorded:
                # Both a file and a reason it could not be written: the entry
                # contradicts itself, which is unreadable, not a choice.
                out._name(UNREADABLE, f"{p}: {fid} (frames and framesUnrecorded both set)")
                continue
            if path is None and isinstance(unrecorded, str) and unrecorded:
                out._name(DRIVER_UNRECORDED, f"{p}: {fid} ({unrecorded})")
                continue
            if path is None or not path.is_file():
                out.missing_by_platform[p] = out.missing_by_platform.get(p, 0) + 1
                out._name(NO_FRAMES_FILE, f"{p}: {fid}")
                continue
            doc, errors = read_frames(path)
            if doc is None:
                out._name(UNREADABLE, f"{p}: {fid} ({'; '.join(errors[:2])})")
                continue
            # The reference box is the top-level root (the root element on
            # iOS / Android, the fixture's container on web — see the schema).
            if doc["root"].get("clipped") or "root" not in doc["frames"]:
                out._name(ROOT_ABSENT, f"{p}: {fid}")
                continue
            out.frames_by_platform[p] = out.frames_by_platform.get(p, 0) + 1
            docs[p] = doc

        if len(docs) < 2:
            out._name(TOO_FEW_PLATFORMS, f"{fid} ({', '.join(sorted(docs)) or 'none'})")
            continue
        out.fixtures_compared += 1

        for element_id in ids:
            present: dict[str, dict] = {}
            for p, doc in docs.items():
                if element_id in (doc.get("fallbacks") or []):
                    out._name(FALLBACK, f"{p}: {fid} #{element_id}")
                    out.fallbacks.append(f"{p}: {fid} #{element_id}")
                    continue
                if element_id in (doc.get("duplicates") or []):
                    out._name(DUPLICATE, f"{p}: {fid} #{element_id}")
                    continue
                frame = doc["frames"].get(element_id)
                if frame is None:
                    out._name(ID_ABSENT, f"{p}: {fid} #{element_id}")
                    continue
                if frame.get("clipped"):
                    out._name(CLIPPED, f"{p}: {fid} #{element_id}")
                    continue
                present[p] = frame
            if len(present) < 2:
                continue
            names = sorted(present)
            agree = {}
            held: dict[str, frozenset | None] = {"x": None, "y": None}
            for i, p in enumerate(names):
                for q in names[i + 1:]:
                    x, y = frame_readings(present[p], docs[p]["root"],
                                          present[q], docs[q]["root"])
                    # A weighted axis must agree by its declared reading,
                    # whatever else agrees: two roots of a lucky size can make
                    # a proportional split look centred (weight__static's
                    # boxes did, 2026-10-05).
                    for axis, readings in (("x", x), ("y", y)):
                        if axis in weighted.get(element_id, ()):
                            pos, size = ("x", "width") if axis == "x" else ("y", "height")
                            ok = proportional_agrees(
                                present[p][pos], present[p][size], docs[p]["root"][size],
                                present[q][pos], present[q][size], docs[q]["root"][size])
                            # A weighted view beside fixed-size siblings takes
                            # what the root leaves after them: the same gap at
                            # both ends, not the same fraction (triage,
                            # 2026-10-05: a weight-1 view next to a fixed 200
                            # read root - 200 on both). That is "stretched",
                            # the other reading a weight declares.
                            held_w = frozenset({"proportional"}) if ok else frozenset()
                            if "stretched" in readings:
                                held_w = held_w | {"stretched"}
                            readings = held_w
                            if axis == "x":
                                x = readings
                            else:
                                y = readings
                    agree[(p, q)] = bool(x) and bool(y)
                    held = {"x": x if held["x"] is None else held["x"] & x,
                            "y": y if held["y"] is None else held["y"] & y}
            odd = outliers(agree, names)
            if odd:
                out.disagreed.append(Disagreement(
                    fixture=fid, id=element_id, outliers=odd, frames=present,
                    roots={p: docs[p]["root"] for p in present},
                ))
            else:
                out.agreed.append((fid, element_id))
                out.readings[(fid, element_id)] = held
    return out


def first_reading(held: frozenset) -> str:
    """The reading a report names for an agreement: the first in READINGS that
    held. ``"mixed"`` when the pairs agreed by different readings and none
    held for all of them."""
    for name in READINGS:
        if name in held:
            return name
    return "mixed"


def reading_counts(result: FrameParityResult) -> dict[str, Counter]:
    """``{"x": Counter(reading -> ids), "y": …}`` over the agreed ids."""
    counts = {"x": Counter(), "y": Counter()}
    for held in result.readings.values():
        for axis in ("x", "y"):
            counts[axis][first_reading(held[axis])] += 1
    return counts


def not_near_agreements(result: FrameParityResult) -> list[str]:
    """Agreed ids where an axis agreed only by a reading other than the near
    edge. These are the ones to hold against the declaration: an agreement a
    lucky pair of root sizes could have made."""
    out = []
    for (fid, element_id), held in sorted(result.readings.items()):
        axes = [f"{axis}={first_reading(held[axis])}" for axis in ("x", "y") if "near" not in held[axis]]
        if axes:
            out.append(f"{fid} #{element_id} ({', '.join(axes)})")
    return out


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


def ledger_path(conformance_dir) -> Path:
    return Path(conformance_dir) / LEDGER_NAME


def load_ledger(path) -> dict[tuple[str, str], dict]:
    """``{(fixture, id): entry}``; a missing file is an empty ledger."""
    path = Path(path)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for entry in data.get("entries", []):
        out[(entry["fixture"], entry["id"])] = entry
    return out


@dataclass
class FrameParityCheck:
    accepted: int = 0
    unrecorded: list[Disagreement] = field(default_factory=list)
    #: entries the measurement no longer supports (agrees now, or other outliers)
    stale: list[str] = field(default_factory=list)
    #: entries whose (fixture, id) was not compared this run
    unverified: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unrecorded and not self.stale


def check(result: FrameParityResult, ledger: dict[tuple[str, str], dict]) -> FrameParityCheck:
    verdict = FrameParityCheck()
    for d in result.disagreed:
        entry = ledger.get(d.key)
        if entry is not None and sorted(entry.get("outliers") or []) == sorted(d.outliers):
            verdict.accepted += 1
        else:
            verdict.unrecorded.append(d)
    agreed = set(result.agreed)
    disagreed = {d.key: d for d in result.disagreed}
    for key, entry in sorted(ledger.items()):
        if key in agreed:
            verdict.stale.append(f"{key[0]} #{key[1]} (now agrees)")
        elif key in disagreed:
            measured = sorted(disagreed[key].outliers)
            if sorted(entry.get("outliers") or []) != measured:
                verdict.stale.append(
                    f"{key[0]} #{key[1]} (records outliers {sorted(entry.get('outliers') or [])}, "
                    f"measured {measured})"
                )
        else:
            verdict.unverified.append(f"{key[0]} #{key[1]}")
    return verdict


def not_compared_lines(result: FrameParityResult, limit: int = 8) -> list[str]:
    """One line per reason, with its count and — where a platform and id are
    involved — the names. Every reason is printed even at zero, so a reader
    sees the whole population and a reason that disappears is visible."""
    lines = []
    for reason in (NO_DECLARED_IDS, NO_FRAMES_FILE, DRIVER_UNRECORDED, UNREADABLE, ROOT_ABSENT,
                   TOO_FEW_PLATFORMS, ID_ABSENT, DUPLICATE, CLIPPED, FALLBACK):
        count = result.not_compared.get(reason, 0)
        line = f"not compared — {reason}: {count}"
        names = result.named.get(reason) or []
        if names and reason in (ID_ABSENT, DUPLICATE, CLIPPED, UNREADABLE, DRIVER_UNRECORDED, FALLBACK):
            line += ": " + "; ".join(names[:limit]) + (" …" if len(names) > limit else "")
        lines.append(line)
    return lines


def summarize(result: FrameParityResult, verdict: FrameParityCheck) -> str:
    return (f"frame parity ({', '.join(result.platforms)}): {result.fixtures_compared} fixture(s) "
            f"compared, {len(result.agreed)} id(s) agree, {len(result.disagreed)} disagree "
            f"({verdict.accepted} accepted on {LEDGER_NAME}, {len(verdict.unrecorded)} unrecorded), "
            f"{sum(result.not_compared.values())} not compared")


def results_by_platform(platform_results: Iterable) -> dict[str, dict[str, dict]]:
    """``{platform: {fixture_id: entry}}`` from report.PlatformResults objects."""
    return {pr.platform: pr.results for pr in platform_results}


def report_section(conformance_dir: Path, manifest: dict, platform_results: Iterable) -> str:
    """The REPORT.md section: every disagreement with the frames side by side,
    then the not-compared population. Judges against the ledger like the gate,
    so the report and the gate cannot tell different stories."""
    loaded = list(platform_results)
    result = measure(conformance_dir, manifest, results_by_platform(loaded),
                     [p.platform for p in loaded])
    verdict = check(result, load_ledger(ledger_path(conformance_dir)))
    lines = ["## Frame parity", "", summarize(result, verdict), ""]
    if result.disagreed:
        accepted = {d.key for d in result.disagreed} - {d.key for d in verdict.unrecorded}
        lines += ["| fixture | id | " + " | ".join(result.platforms) + " | outliers | ledger |",
                  "|---|---|" + "---|" * len(result.platforms) + "---|---|"]
        for d in result.disagreed:
            cells = []
            for p in result.platforms:
                f = d.frames.get(p)
                cells.append(f"{f['x']:g},{f['y']:g} {f['width']:g}x{f['height']:g}" if f else "—")
            lines.append(f"| {d.fixture} | {d.id} | " + " | ".join(cells)
                         + f" | {', '.join(d.outliers)} | {'accepted' if d.key in accepted else 'UNRECORDED'} |")
        lines.append("")
    counts = reading_counts(result)
    lines.append("Agreements by reading (the first that held for every pair, per axis): "
                 + "; ".join(f"{axis}: " + ", ".join(f"{name} {counts[axis].get(name, 0)}"
                                                    for name in (*READINGS, "mixed"))
                             for axis in ("x", "y")))
    lines.append("")
    off_near = not_near_agreements(result)
    lines.append(f"Agreed other than from the near edge on some axis: {len(off_near)}"
                 + (" — " + "; ".join(off_near[:20]) + (" …" if len(off_near) > 20 else "") if off_near else ""))
    lines.append("")
    lines += [f"- {line}" for line in not_compared_lines(result)]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Ledger from rules
# --------------------------------------------------------------------------- #

RULES_NAME = "frame_parity_rules.json"
FIELDS = ("x", "y", "width", "height")


def rules_path(conformance_dir) -> Path:
    return Path(conformance_dir) / RULES_NAME


def load_rules(path, manifest: dict | None = None) -> list[dict]:
    """The hand-written half: which disagreements are a platform idiom, on
    which fields, and why. Each rule: ``fixture`` (fnmatch glob over the
    fixture id), ``id`` (glob, default ``*``), ``fields`` (the fields allowed
    to differ — any other field that differs keeps the id OUT of the ledger),
    ``reason`` (required, one line).

    ``expected`` (optional) narrows a rule to a known amount: ``{host: {field:
    value}}``. Each named host's field must be within TOLERANCE of the value,
    and the hosts it does not name must agree among themselves, or the id is
    refused. It is for a difference the rulings accept by a stated amount
    (iOS lineHeightMultiple: no multiple on the first line, so (m - 1) x L
    short) — "height may differ" would also accept any other height.

    A rule's faces are those of the visual fixtures its ``fixture`` glob
    matches in *manifest* (each fixture's ``platforms``, generated from the
    SSoT platform declaration): an Indicator has no web face, so naming ios
    and android leaves nothing unchecked. Without a manifest, or when the
    glob matches no fixture, every EXPECTED_FRAME_HOSTS face counts."""
    path = Path(path)
    if not path.is_file():
        return []
    rules = json.loads(path.read_text(encoding="utf-8")).get("rules", [])
    for i, rule in enumerate(rules):
        missing = [k for k in ("fixture", "reason") if not rule.get(k)] + (["fields"] if "fields" not in rule else [])
        bad = [f for f in rule.get("fields", []) if f not in FIELDS]
        for host, values in (rule.get("expected") or {}).items():
            if not isinstance(values, dict):
                bad.append(f"expected.{host}")
                continue
            bad += [f"expected.{host}.{f}" for f, v in values.items()
                    if f not in rule.get("fields", []) or not isinstance(v, (int, float))]
        # Naming all faces but one leaves that one compared with nothing: it
        # could draw any value and still be ledgered. Name one face, or all.
        named = set(rule.get("expected") or {})
        faces = _rule_faces(rule, manifest)
        if named and len(faces - named) == 1:
            bad.append(f"expected names {sorted(named)}, leaving {sorted(faces - named)} unchecked")
        if missing or bad:
            raise ValueError(f"{RULES_NAME} rule {i}: missing {missing}, unknown fields {bad}")
    return rules


def differing_fields(d: "Disagreement", hosts: Iterable[str] | None = None) -> set[str]:
    """Fields on which the faces' frames are more than TOLERANCE apart.
    Position fields are compared by the readings (a far-edge view differs in
    x between roots of different sizes and still agrees), sizes directly.
    ``hosts`` limits the comparison to those faces."""
    out = set()
    names = sorted(h for h in d.frames if hosts is None or h in hosts)
    for i, p in enumerate(names):
        for q in names[i + 1:]:
            a, b, ra, rb = d.frames[p], d.frames[q], d.roots[p], d.roots[q]
            x, y = frame_readings(a, ra, b, rb)
            if not _near(a["width"], b["width"]):
                out.add("width")
            if not _near(a["height"], b["height"]):
                out.add("height")
            # A position differs when no reading places it, or — sizes
            # differing — when neither its start nor its far-edge gap agrees.
            for pos, size, readings in (("x", "width", x), ("y", "height", y)):
                if readings:
                    continue
                if _near(a[size], b[size]):
                    out.add(pos)
                elif not (_near(a[pos], b[pos])
                          or _near(ra[size] - a[pos] - a[size], rb[size] - b[pos] - b[size])):
                    out.add(pos)
    return out


def _rule_faces(rule: dict, manifest: dict | None) -> set[str]:
    """The frame-writing faces of the visual fixtures *rule* matches; every
    EXPECTED_FRAME_HOSTS face when there is no manifest or no match."""
    from fnmatch import fnmatchcase

    faces: set[str] = set()
    for fixture in (manifest or {}).get("fixtures", []):
        if fixture.get("class") == "visual" and fnmatchcase(fixture.get("id", ""), rule.get("fixture", "")):
            faces |= set(fixture.get("platforms") or []) & EXPECTED_FRAME_HOSTS
    return faces or set(EXPECTED_FRAME_HOSTS)


def ledger_from_rules(result: FrameParityResult, rules: list[dict]) -> tuple[list[dict], list[str]]:
    """``(entries, refused)``. An entry per disagreement a rule matches whose
    differing fields are all within the rule's ``fields``; ``refused`` names
    the matched ones that also differ outside them (a defect must not be
    ledgered along with an idiom on the same id)."""
    from fnmatch import fnmatchcase

    entries, refused = [], []
    for d in sorted(result.disagreed, key=lambda d: d.key):
        rule = next((r for r in rules
                     if fnmatchcase(d.fixture, r["fixture"]) and fnmatchcase(d.id, r.get("id", "*"))), None)
        if rule is None:
            continue
        outside = differing_fields(d) - set(rule["fields"])
        if outside:
            refused.append(f"{d.fixture} #{d.id}: differs in {sorted(outside)} outside the rule's {rule['fields']}")
            continue
        if (off := _off_expected(d, rule.get("expected") or {})):
            refused.append(f"{d.fixture} #{d.id}: {off}")
            continue
        entries.append({"fixture": d.fixture, "id": d.id, "outliers": sorted(d.outliers),
                        "fields": sorted(differing_fields(d)), "reason": rule["reason"]})
    return entries, refused


def _off_expected(d: "Disagreement", expected: dict) -> str | None:
    """Why a rule's ``expected`` does not hold for ``d``, or None."""
    for host, values in sorted(expected.items()):
        frame = d.frames.get(host)
        if frame is None:
            return f"no {host} frame for the rule's expected {values}"
        for field, value in sorted(values.items()):
            if not _near(frame[field], value):
                return f"{host} {field} {frame[field]:g} is not the rule's expected {value:g} (tolerance {TOLERANCE:g})"
    if expected and (rest := differing_fields(d, [h for h in d.frames if h not in expected])):
        return f"the faces the rule's expected does not name differ in {sorted(rest)}"
    return None


def write_ledger(path, entries: list[dict]) -> None:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schemaVersion": 1}
    data["entries"] = entries
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
