"""``jui conformance report`` — did the attribute do anything at all?

The visual suite compares every screenshot against *that same platform's*
previous screenshot. So an attribute a platform silently drops renders the
default, matches the default it recorded last time, and passes forever. That
is exactly how ``Button.image`` and ``View.flexWrap`` stayed broken while
every gate was green, and it is why the attribute-coverage ledger had to exist
as a separate static check.

This closes it from the output side. For each visual fixture the generator
also emits a **control**: the same layout with the attribute under test
removed. If a fixture renders identically to its control, nothing the
attribute asked for happened.

Two properties make this cheap and trustworthy:

- **No baseline is involved.** Both images come from the same run on the same
  device, so simulator/emulator drift, OS upgrades and font changes cancel out.
  A fresh checkout with no baselines can still run it. It also means the
  comparison can be pixel-exact rather than perceptual — see
  ``DEFAULT_MIN_PIXELS``.
- **No cross-platform comparison is involved.** That remains out of scope; the
  question here is only "did this platform react to the attribute", which each
  platform answers about itself.

One control serves every fixture sharing its shape (``host`` + anchor), so the
602 visual fixtures need ~30 controls rather than 602.

Not every identical render is a defect, and pretending otherwise would make
this the next check somebody switches off:

- an attribute whose fixture value happens to equal the platform default
  (``enabled: true``, a colour that matches the theme) cannot differ
- the fixture's shape can leave the attribute nothing to do: ``textAlign`` on a
  ``wrapContent`` Label has no slack to align the text within, so it renders
  identically however correct the implementation is

So an identical render is reported as **inert**, and only fixtures listed in
``conformance/control_diff.json`` as *expected to differ* are failed. That
ledger is the ratchet: implementing an attribute means adding its fixture
there, and a fixture that stops differing afterwards fails the build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .baseline import BaselineError, _load_pillow

#: Ledger schema version; bump when the entry shape changes.
SCHEMA_VERSION = 1

#: Differing pixels below which two renders count as the same image.
#:
#: Zero, and that is the point of comparing within a run. The baseline check
#: needs a perceptual hash with a tolerance because it compares across runs,
#: where the simulator clock, an OS upgrade and font rendering all move. Here
#: both screenshots come off the same device in the same run, so rendering is
#: deterministic and any differing pixel is a real difference.
#:
#: Using the perceptual hash here instead was measurably wrong: dhash-64
#: downsamples the whole screen to 9x8, and the fixture's target is one small
#: element on a mostly empty screen, so `cornerRadius` (0.008% of pixels) and
#: `fontColor` (0.05%) both hashed identical to their control. Raise this only
#: if a real render turns out to be nondeterministic within a run — a blinking
#: caret is the plausible one — and say so here when you do.
DEFAULT_MIN_PIXELS = 0

#: Fixtures asserted to render differently from their control. Anything not
#: listed is reported but does not fail — see module docstring.
LEDGER_NAME = "control_diff.json"

#: Bottom strip (px) excluded from the fixture-vs-control comparison, per
#: platform. iOS: the home indicator dims a few seconds after interaction
#: settles, so two captures from the same run can catch different fade
#: frames — measured 2026-08-03 as 14 false actives whose diff bbox was
#: exactly the indicator strip (y 2583–2598 on a 2622px 3x screenshot).
#: 64px covers the strip with margin; fixtures render nowhere near it
#: (full-screen white root, content top/center). Not env-keyed: the
#: indicator is there in every iOS environment.
PLATFORM_IGNORE_BOTTOM = {"ios": 64}


def ignore_bands(platform: str, env: str | None) -> tuple[int, int]:
    """``(top, bottom)`` rows this comparison must not look at.

    The system chrome comes from :data:`baseline.PLATFORM_ENV_CHROME_CROP`,
    read rather than restated. That table already holds the measured bands
    for each (platform, env) — including the android CI status bar, whose
    clock ticks between the two captures of a pair and put 120 fixtures on
    the active side of a comparison that is supposed to be about attributes.

    Reading it from there is the whole fix. "Both screenshots come off the
    same device in the same run, so rendering is deterministic" was the
    assumption in this file, and same-run is not same-instant: the hashing
    lane had already worked that out and cropped for it, while this lane
    kept comparing the clock. Two devices, one repository, opposite beliefs
    about the same pixels.

    The env key carries an asymmetry that matters: locally those rows hold
    real content (tab bar, alignBottom, fill clamps) and must NOT be cropped,
    so `(android, local)` is deliberately absent from the table and this
    returns no top band there.
    """
    from .baseline import chrome_crop

    top, bottom = chrome_crop(platform, env)
    # max, not replace: the two tables were cut for different reasons and
    # happen to share an axis. chrome_crop's bottom is the android CI
    # taskbar; PLATFORM_IGNORE_BOTTOM's is the iOS home indicator. Taking
    # either one alone drops whatever the other knew, and today that would
    # be iOS's 64px — the fade that produced 14 false actives on 2026-08-03.
    # Whichever band is taller covers both claims about the same rows.
    return (top, max(bottom, PLATFORM_IGNORE_BOTTOM.get(platform, 0)))


def ledger_path(conformance_dir) -> Path:
    return Path(conformance_dir) / LEDGER_NAME


@dataclass
class DiffResult:
    """Per-platform outcome of the fixture-vs-control comparison."""

    platform: str
    #: fixtures that differ from their control — the attribute did something
    active: list = field(default_factory=list)
    #: (fixture_id, differing pixel count) that render the same as their control
    inert: list = field(default_factory=list)
    #: inert AND listed as expected-to-differ — these fail
    regressions: list = field(default_factory=list)
    #: expected-to-differ entries that could not be compared at all — no
    #: fixture screenshot, or no control to compare against. Not a pass.
    unmeasured: list = field(default_factory=list)
    #: fixtures whose control produced no screenshot (cannot be compared)
    no_control: list = field(default_factory=list)
    #: fixtures dropped from the comparison by the off-face rule — kept as a
    #: list, never a silent skip: a device that excludes says how many.
    excluded: list = field(default_factory=list)
    #: visual fixtures with no control declared at all, because the attribute
    #: is on `NON_OBSERVABLE_BY_SECTION` — a still capture cannot photograph
    #: it (`TextField.tintColor` IS the caret, and an unfocused field has
    #: none). Legitimate, recorded, and previously invisible: these never
    #: entered the loop, so "compared" silently excluded them and each
    #: rediscovery cost a lane an investigation.
    not_compared_by_design: list = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.regressions and self.error is None


#: Sentinel a 51-E2 adjudication appends to an ``inert_audit`` reason to mark
#: the off-face family. Prose is a poor key and this belongs in a field of its
#: own — raised to E2/orch. Until then it is at least a DELIBERATE marker
#: rather than incidental wording, and :func:`off_face_exclusions` reports the
#: class size every run, so a phrasing drift surfaces as a changed number
#: instead of a quietly smaller exclusion.
OFF_FACE_FAMILY = "Family: off-face-equals-control."


def off_face_exclusions(conformance_dir, manifest: dict) -> tuple[set, set, list]:
    """``(excluded, held, orphaned)`` for the off-face rule — derived, not listed.

    An off-face fixture writes the very state its control renders by omitting
    the attribute, so the pair cannot differ however correctly the platform
    implements it. Comparing them manufactures a permanent inert verdict that
    no amount of implementation work can clear, which is why the orchestrator
    ruled (b-2, 2026-08-07) that the fixtures stay and the COMPARISON drops
    them.

    Nothing here is hand-listed. The class is the ``inert_audit`` rows
    carrying :data:`OFF_FACE_FAMILY`, and whether a member is safe to drop
    follows from the ledgers:

    - a sibling fixture for the same attribute stays in the comparison AND is
      asserted active in ``control_diff.json`` -> **excluded** (the attribute
      still has something reporting on it)
    - siblings stay but none is asserted active anywhere -> **held** (dropping
      it would leave the attribute with nothing that could ever report)
    - no sibling at all -> **orphaned**, returned as a problem and NEVER
      dropped. Excluding is permanent removal from measurement, which is the
      exact failure this whole campaign exists to prevent.

    Verified 2026-08-07 to reproduce E2's independently-audited canonical set
    exactly: 32 excluded, 2 held (``ScrollView/scrollBehavior__auto`` and
    ``TextView/selectable__true``), 0 orphaned, 0 disagreements. The two holds
    are a CONSEQUENCE of the safety rule here, not a special case bolted on.
    """
    conformance_dir = Path(conformance_dir)
    audit_path = conformance_dir / "inert_audit.json"
    if not audit_path.is_file():
        return set(), set(), []

    entries = json.loads(audit_path.read_text(encoding="utf-8")).get("entries", [])
    klass = {
        e["fixture"]
        for e in entries
        if e.get("fixture") and OFF_FACE_FAMILY in (e.get("reason") or "")
    }
    if not klass:
        return set(), set(), []

    # Platform-agnostic, matching how the canonical set was audited: an
    # attribute proven active on ANY platform still has a reporter.
    asserted_active = load_ledger_all(ledger_path(conformance_dir)).keys()

    by_attribute: dict = {}
    for entry in manifest.get("fixtures", []):
        key = (entry.get("component"), entry.get("attribute"))
        if key[0] and key[1]:
            by_attribute.setdefault(key, []).append(entry["id"])
    of_fixture = {
        entry["id"]: (entry.get("component"), entry.get("attribute"))
        for entry in manifest.get("fixtures", [])
    }

    excluded, held, orphaned = set(), set(), []
    for fid in sorted(klass):
        siblings = [
            s
            for s in by_attribute.get(of_fixture.get(fid, (None, None)), [])
            if s != fid and s not in klass
        ]
        if not siblings:
            orphaned.append(fid)
        elif any(s in asserted_active for s in siblings):
            excluded.add(fid)
        else:
            held.add(fid)
    return excluded, held, orphaned


def load_ledger(path, platform: str | None = None) -> set:
    """Fixtures asserted to differ from their control.

    Per platform, because that is what the fact is: `Label.textAlign` moving
    pixels on web says nothing about iOS, where the attribute may not be
    implemented at all. A shared list would either fail every platform for one
    platform's gap or record nothing.
    """
    path = Path(path)
    if not path.is_file():
        return set()
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = set()
    for entry in raw.get("entries", []):
        fixture = entry.get("fixture")
        if not fixture:
            continue
        if platform is None or platform in (entry.get("platforms") or []):
            out.add(fixture)
    return out


def load_ledger_all(path) -> dict:
    """`{fixture_id: {platform}}` for the whole ledger."""
    path = Path(path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict = {}
    for entry in raw.get("entries", []):
        fixture = entry.get("fixture")
        if fixture:
            out.setdefault(fixture, set()).update(entry.get("platforms") or [])
    return out


def render_ledger(by_fixture: dict) -> str:
    """Deterministic ledger JSON for `{fixture_id: {platform, ...}}`."""
    doc = {
        "schemaVersion": SCHEMA_VERSION,
        "_comment": (
            "Visual fixtures asserted to render DIFFERENTLY from their control "
            "(the same layout without the attribute under test), per platform. "
            "A fixture listed for a platform that renders identically there "
            "fails the build: the attribute stopped having an effect. Record an "
            "entry when you implement an attribute; remove it only when the "
            "attribute is removed. Fixtures not listed are reported as inert "
            "without failing — a value equal to the platform default, or a "
            "fixture whose shape leaves the attribute nothing to do, cannot "
            "differ."
        ),
        "entries": [
            {"fixture": f, "platforms": sorted(by_fixture[f])}
            for f in sorted(by_fixture)
            if by_fixture[f]
        ],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def _screenshot_names(results: dict) -> dict:
    """`fixture_id -> screenshot basename` from one platform's results.

    *results* is ``PlatformResults.results`` — already keyed by fixture id.
    The basename is what the artifacts directory holds, matching how the
    baseline comparison resolves its PNGs.
    """
    out: dict = {}
    for fid, entry in (results or {}).items():
        if isinstance(entry, dict) and isinstance(entry.get("screenshot"), str):
            out[str(fid)] = Path(entry["screenshot"]).name
    return out


def diff_pixels(
    path_a: Path, path_b: Path, ignore_bottom: int = 0, ignore_top: int = 0
) -> int:
    """Number of pixels that differ between two PNGs.

    Different dimensions mean the renders cannot be the same image; report the
    whole frame rather than raising, so one odd fixture does not abort the run.
    ``ignore_bottom`` crops that many pixels off BOTH images before comparing
    — see ``PLATFORM_IGNORE_BOTTOM`` for why (ios home-indicator fade).
    """
    Image = _load_pillow()
    from PIL import ImageChops  # noqa: PLC0415 - paired with _load_pillow

    with Image.open(path_a) as ia, Image.open(path_b) as ib:
        a, b = ia.convert("RGB"), ib.convert("RGB")
        if a.size != b.size:
            return a.size[0] * a.size[1]
        if (ignore_top or ignore_bottom) and a.size[1] > ignore_top + ignore_bottom:
            box = (0, ignore_top, a.size[0], a.size[1] - ignore_bottom)
            a, b = a.crop(box), b.crop(box)
        diff = ImageChops.difference(a, b)
        # getbbox() is the C fast path and answers "any pixel at all?" — worth
        # the early exit because most comparisons are one or the other extreme.
        if diff.getbbox() is None:
            return 0
        # Collapse RGB to one band, then count non-zero via the histogram —
        # both are C loops. A per-pixel Python loop over 600 comparisons of
        # full-resolution screenshots is minutes of CI time.
        flat = diff.convert("L").point(lambda v: 255 if v else 0)
        return sum(flat.histogram()[1:])


def compare(
    conformance_dir,
    platform: str,
    manifest: dict,
    results: dict,
    artifacts_dir=None,
    min_pixels: int = DEFAULT_MIN_PIXELS,
    env: str | None = None,
) -> DiffResult:
    """Compare each visual fixture's screenshot against its control's.

    A fixture counts as *active* when more than ``min_pixels`` pixels differ
    from its control. See ``DEFAULT_MIN_PIXELS`` for why that is zero.
    """
    conformance_dir = Path(conformance_dir)
    if artifacts_dir is None:
        artifacts_dir = conformance_dir / "artifacts" / platform
    artifacts_dir = Path(artifacts_dir)

    result = DiffResult(platform=platform)
    _top, _bottom = ignore_bands(platform, env)
    expected = load_ledger(ledger_path(conformance_dir), platform)
    shots = _screenshot_names(results)
    off_face, _held, orphaned = off_face_exclusions(conformance_dir, manifest)
    if orphaned:
        # Never drop these. An off-face fixture whose attribute has no other
        # reporter would leave measurement entirely, and the whole point of
        # the rule is that exclusion must not cost coverage.
        result.error = (
            f"off-face exclusion would orphan {len(orphaned)} attribute(s) — "
            f"no sibling fixture is left to report on them: "
            + ", ".join(sorted(orphaned)[:5])
        )
        return result

    for entry in manifest.get("fixtures", []):
        control_id = entry.get("control")
        if entry.get("isControl"):
            continue
        fid = entry["id"]
        if platform not in (entry.get("platforms") or []):
            continue
        if not control_id:
            if entry.get("class") == "visual":
                result.not_compared_by_design.append(fid)
            continue
        if fid in off_face:
            # Structurally incapable of differing from its control: the value
            # written IS the state the control renders by omitting it.
            result.excluded.append(fid)
            continue

        shot = shots.get(fid)
        control_shot = shots.get(control_id)
        if shot is None:
            if fid in expected:
                result.unmeasured.append(fid)
            continue
        if control_shot is None:
            # A recorded fixture we cannot compare is an unverified assertion,
            # not a pass. Letting it sit in `no_control` would make a run where
            # the controls failed to render report "no regressions" for a
            # comparison that never happened.
            (result.unmeasured if fid in expected else result.no_control).append(fid)
            continue

        png_a, png_b = artifacts_dir / shot, artifacts_dir / control_shot
        if not (png_a.is_file() and png_b.is_file()):
            (result.unmeasured if fid in expected else result.no_control).append(fid)
            continue

        try:
            changed = diff_pixels(
                png_a,
                png_b,
                ignore_top=_top,
                ignore_bottom=_bottom,
            )
        except BaselineError as exc:
            result.error = str(exc)
            return result

        if changed > min_pixels:
            result.active.append(fid)
        else:
            result.inert.append((fid, changed))
            if fid in expected:
                result.regressions.append(fid)

    return result
