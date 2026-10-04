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
SOURCES = frozenset({"xcuielement-frame", "a11y-node-bounds", "get-bounding-client-rect"})
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
EXPECTED_FRAME_HOSTS: frozenset[str] = frozenset()

# not-compared reasons, each counted on its own line
NO_DECLARED_IDS = "fixture declares no id besides root"
NO_FRAMES_FILE = "platform wrote no frames file for this fixture"
UNREADABLE = "frames file unreadable or not the schema"
TOO_FEW_PLATFORMS = "fewer than two platforms have frames for this fixture"
ID_ABSENT = "frames file present, declared id absent"
DUPLICATE = "id found on more than one element"
CLIPPED = "frame clipped at the screen edge"
ROOT_ABSENT = "frames file has no usable root frame"


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
    allowed = {"schemaVersion", "fixture", "platform", "source", "root", "frames", "duplicates"}
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


#: The readings, in the order a report names the one that held: the near
#: edge first, because that is the reading a root-relative frame states
#: directly. An agreement held ONLY by a later reading is the one to check
#: against the declaration — roots of a lucky size can let a wrong placement
#: through the far edge or the centre.
READINGS = ("near", "stretched", "centred", "far")


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
        if not ids:
            out._name(NO_DECLARED_IDS, fid)
            continue

        docs: dict[str, dict] = {}
        for p in scope:
            entry = results.get(p, {}).get(fid)
            path = _frames_path(conformance_dir, entry) if entry else None
            if path is None or not path.is_file():
                out.missing_by_platform[p] = out.missing_by_platform.get(p, 0) + 1
                out._name(NO_FRAMES_FILE, f"{p}: {fid}")
                continue
            doc, errors = read_frames(path)
            if doc is None:
                out._name(UNREADABLE, f"{p}: {fid} ({'; '.join(errors[:2])})")
                continue
            root = doc["frames"].get("root")
            if root is None or root.get("clipped"):
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
            held = {"x": frozenset(READINGS), "y": frozenset(READINGS)}
            for i, p in enumerate(names):
                for q in names[i + 1:]:
                    x, y = frame_readings(present[p], docs[p]["frames"]["root"],
                                          present[q], docs[q]["frames"]["root"])
                    agree[(p, q)] = bool(x) and bool(y)
                    held = {"x": held["x"] & x, "y": held["y"] & y}
            odd = outliers(agree, names)
            if odd:
                out.disagreed.append(Disagreement(
                    fixture=fid, id=element_id, outliers=odd, frames=present,
                    roots={p: docs[p]["frames"]["root"] for p in present},
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
    for reason in (NO_DECLARED_IDS, NO_FRAMES_FILE, UNREADABLE, ROOT_ABSENT, TOO_FEW_PLATFORMS,
                   ID_ABSENT, DUPLICATE, CLIPPED):
        count = result.not_compared.get(reason, 0)
        line = f"not compared — {reason}: {count}"
        names = result.named.get(reason) or []
        if names and reason in (ID_ABSENT, DUPLICATE, CLIPPED, UNREADABLE):
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
