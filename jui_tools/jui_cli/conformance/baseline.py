"""Screenshot baseline hashing + same-platform visual regression detection.

Plan 12 §3: the visual fixtures' screenshots were capture-only in v1; v2
turns them into a *same-platform* regression signal. PNGs are never
committed — only a perceptual-hash manifest per render environment and
platform:

```
conformance/baselines/<env>/<platform>.hashes.json   # @generated, committed
conformance/artifacts/<platform>/*.png               # local / CI artifact only
```

The *environment* key exists because a baseline is a fact about one
renderer: the 2026-08-01 full CI run proved a locally-baked baseline and a
fresh CI render disagree wholesale (ios 534/534, android 506/506 compared
screenshots over the dhash-64 threshold) while the CI render was internally
healthy (0 fail / 0 error, ratchets exactly on their ceilings). Comparing
across render environments measures the environment, not the change under
test. ``local`` is the developer-machine set; CI lanes pass their own key
(``ci``) and compare only against baselines baked from CI artifacts.

Algorithm: **dHash (difference hash), 64x64 grid = 4096 bits**.

- grayscale -> resize to 65x64 (LANCZOS) -> compare horizontal neighbours;
  each bit encodes "left pixel brighter than right".
- the grid is deliberately fine: conformance screenshots are full-page
  captures where the component under test often covers only ~1% of the
  frame. A coarse 16x16 dHash averaged such a component into a single cell
  and *missed a deliberately injected rendering change entirely* (measured
  distance 0); at 64x64 the same change measured 34 bits while repeat-run
  noise stayed at <= 2 bits.
- distance = Hamming distance between the 4096-bit hashes. The comparison
  threshold is calibrated against measured repeat-run variance of the web
  host (see ``conformance/baselines/README.md``) — not guessed.

Dependency: Pillow (image decode + resample), an *optional* extra — see
``jui_tools/setup.py`` ``extras_require["conformance"]``. Everything doing
baseline work degrades with a clear error when Pillow is missing; the rest
of the conformance harness never imports it.

Cross-platform comparison is explicitly NOT done (fonts/renderers differ by
construction); a baseline only ever compares against the same platform.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..core.generated_marker import json_marker
from .visual_stability import unstable_screenshots
from .os_dependence import os_dependent_screenshots_for

GENERATOR_NAME = "jui conformance baseline update"

#: Default render-environment key. Baselines live under
#: ``baselines/<env>/`` and only ever compare within one environment;
#: everything defaults to the developer-machine set.
DEFAULT_ENV = "local"

#: dHash grid size: NxN bits per row comparison -> N*N bit hash.
HASH_SIZE = 64

#: Algorithm identifier stored in baseline manifests; bump when the hashing
#: parameters change (stale-algorithm baselines are reported, not compared).
ALGORITHM = f"dhash-{HASH_SIZE}"

#: Maximum Hamming distance treated as "same rendering".
#:
#: Calibrated 2026-07-02 against repeat-run variance of the web host
#: (Playwright/chromium headless, 466 visual screenshots, independent full
#: suite runs): 458 screenshots at distance 0, 2 at distance 1, 6 at
#: distance 2 (Slider / number-input anti-aliasing flicker) — measured max
#: noise 2. Threshold 8 = 4x the measured max, while a deliberately
#: injected rendering change (gradient direction flip inside a 100x100
#: component on the 1024x768 page) measured distance 34.
#: Rationale + raw numbers: conformance/baselines/README.md.
DEFAULT_THRESHOLD = 8


class BaselineMoved(RuntimeError):
    """Raised INSTEAD OF writing, when entries moved and the caller refused that.

    Carries the classification so the caller can print every MOVED line — the
    reading the flag exists to force — without the file having changed.
    """

    def __init__(self, out_path: "Path", moved: "tuple[tuple[str, int], ...]"):
        self.out_path = out_path
        self.moved = moved
        super().__init__(
            f"{len(moved)} entr(y/ies) moved; {out_path} was NOT written"
        )


class BaselineError(RuntimeError):
    """Raised when baseline work cannot proceed (missing Pillow / inputs)."""


def _load_pillow():
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise BaselineError(
            "Pillow is required for screenshot baselines — "
            "install with: pip install 'jui-tools[conformance]' (or pip install Pillow)"
        ) from exc
    return Image


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #


#: Rows of the frame that belong to system chrome rather than to the fixture,
#: keyed by ``(platform, env)`` as ``(top, bottom)`` pixel counts.
#:
#: The CI android emulator runs the pixel_tablet profile, whose launcher draws
#: an opaque status bar across the top and an opaque taskbar across the bottom,
#: over an app that is inset away from both (``systemBarsPadding``). Neither
#: band can carry fixture pixels there — but both move on their own: the
#: taskbar's predicted-apps row reorders between boots and promotes the host app
#: into itself, and the status-bar clock ticks when SystemUI drops the demo-mode
#: broadcast. Measured on run 30874627862, that noise put 478/478 fixtures over
#: the threshold with a mean distance of 16.45; excluding the two bands brings
#: the same comparison to 0/478 at mean 0.36.
#:
#: ANDROID local runs are NOT cropped and must not be: that AVD has no
#: taskbar, so the same rows hold real content there (the TabView tab bar,
#: alignBottom, fill clamps). This is exactly the asymmetry the env key exists
#: to carry — baselines never cross environments, so the crop never has to
#: either. Measured 2026-09-04, one android fixture: inverting every row of
#: both bands moves the hash by 9 against a threshold of 8, so the exposure
#: is real in principle — but across every local android run pair taken this
#: cycle (two library revisions, two full 804-shot runs on conf_ci) the bands
#: were byte-identical, and the 48/120 rows carry 6 and 13 distinct values
#: across the corpus. Nothing has ridden; cropping would trade those away for
#: no measured gain. Revisit if the local AVD is ever replaced.
#: Bounds come from the measured bands (status bar 11–36, taskbar 1495–1583)
#: with margin, and stop short of the tab bar at 1300–1450.
#:
#: The CI ios simulator draws its status bar glyphs (clock, cellular, wifi,
#: battery) at rows 78–116 of the 1206x2622 frame, and their COLOR is not a
#: function of the fixture: UIKit infers light/dark status-bar content from
#: the luminance behind the bar, and on a fixture that lands near the decision
#: boundary the inference races the render and flips run to run. Measured on
#: runs 32657361988/33333136630 (same image, same code, same library pins):
#: the codegen host drew effectStyle__regular's clock black on one run and
#: white on the next — dhash 23 vs 0 with every non-glyph pixel identical —
#: while the dynamic host held white on both. The battery glyph also renders
#: the host's charging state, a second flake the fixture cannot control.
#:
#: Unlike android, the ios app is edge-to-edge, so this band DOES carry
#: fixture pixels (safe-area backgrounds reach the top edge). Cropping trades
#: them away deliberately: a codegen deviation confined to rows 0–159 with no
#: trace below is invisible after the crop. That loss is accepted because the
#: OS glyphs inside the band are unfixably nondeterministic, and measured on
#: run 33333136630 it costs nothing today: the crop flips not one control-diff
#: verdict (494 active / 111 inert, unchanged) — backgrounds that reach the
#: top edge continue below it. Neither the Dynamic Island nor the home
#: indicator is rendered in these captures (measured, same runs), so the
#: bottom stays 0.
#:
#: ios LOCAL takes the same crop, for the same glyphs. The band is not stable
#: across simulator INSTANCES either: two "iPhone 16 Pro / iOS 18.6" devices
#: differing only in UDID rendered the same corpus with 849 of 852 hashes
#: moved (distance median 18, max 255) while the content was identical —
#: cropped to (160, 0) the same pairs fall to 0–4, and the differing pixels
#: sit at rows 78–117 with a few at 2595 (measured 2026-09-04, D6A1DD42 vs
#: C13F2A69, both frozen to 9:41). Uncropped, a local baseline is a fact
#: about one simulator instance rather than about the renderer: the same
#: library re-rendered on a sibling device reads as a whole-corpus
#: regression, which is how two bakes were spent this cycle. The trade is the
#: one the ci entry already makes and it is not free here either: 139 of 852
#: fixtures draw something inside those rows (SafeAreaView_direction is the
#: sharpest case — the top edge IS its subject), so a deviation confined to
#: rows 0–159 is invisible on this lane too. Prefer the assertable arms for
#: those; a picture cannot carry both this band and a stable baseline.
PLATFORM_ENV_CHROME_CROP: dict[tuple[str, str], tuple[int, int]] = {
    ("android", "ci"): (48, 120),
    ("ios", "ci"): (160, 0),
    ("ios", "local"): (160, 0),
}


def chrome_crop(platform: str | None, env: str | None) -> tuple[int, int]:
    """``(top, bottom)`` rows to exclude from the hash for this lane."""
    if platform is None or env is None:
        return (0, 0)
    return PLATFORM_ENV_CHROME_CROP.get((platform, env), (0, 0))


def dhash_file(path: Path, crop: tuple[int, int] = (0, 0)) -> str:
    """256-bit dHash of one image file, as a 64-char lowercase hex string.

    ``crop`` excludes ``(top, bottom)`` rows before hashing — see
    :data:`PLATFORM_ENV_CHROME_CROP`. A hash taken with a crop is only ever
    comparable to another taken with the same crop, which the ``(platform,
    env)`` keying guarantees.
    """
    Image = _load_pillow()
    with Image.open(path) as img:
        top, bottom = crop
        if top or bottom:
            width, height = img.size
            if height > top + bottom:
                img = img.crop((0, top, width, height - bottom))
        gray = img.convert("L").resize(
            (HASH_SIZE + 1, HASH_SIZE), Image.Resampling.LANCZOS
        )
        # tobytes() on mode-L images is the raw 8-bit pixel row-major buffer
        # (stable across Pillow versions, unlike the deprecated getdata()).
        pixels = gray.tobytes()

    bits = 0
    for row in range(HASH_SIZE):
        offset = row * (HASH_SIZE + 1)
        for col in range(HASH_SIZE):
            bits = (bits << 1) | (1 if pixels[offset + col] > pixels[offset + col + 1] else 0)
    return f"{bits:0{HASH_SIZE * HASH_SIZE // 4}x}"


def hamming(hex_a: str, hex_b: str) -> int:
    """Hamming distance between two same-length hex hash strings."""
    if len(hex_a) != len(hex_b):
        raise ValueError(f"hash length mismatch: {len(hex_a)} != {len(hex_b)}")
    return (int(hex_a, 16) ^ int(hex_b, 16)).bit_count()


def popcount(hex_hash: str) -> int:
    """Set bits in a hex hash.

    ``popcount(h) == hamming(h, 0)``, and an all-zero dHash is what a
    perfectly uniform image produces — so this is the distance from *this*
    picture to a blank page, derivable without opening a single file.
    """
    return int(hex_hash, 16).bit_count()


def blind_to_blanking(hashes: dict[str, str], threshold: int) -> list[str]:
    """Names whose committed hash cannot tell their picture from a blank page.

    🔻 THE HOLE THIS NAMES. The visual gate passes anything within *threshold*
    of the committed hash. A picture that goes completely blank hashes to all
    zeros, so its distance from the baseline is exactly ``popcount(baseline)``
    — and every entry whose popcount is at or below the threshold therefore
    stays green no matter how empty it gets.

    Measured 2026-09-15 at threshold 8: **115 of 867 ci/ios entries**, 106 of
    816 on android, 221 of 818 on web. Of the iOS 115, **96 draw something**
    (ink > 0) — those are the ones with real coverage to lose; the other 19
    are already blank on purpose and nothing can distinguish them.

    The population is DERIVED from the committed hashes rather than listed,
    so it follows the corpus and the threshold without being maintained.
    """
    return sorted(n for n, h in hashes.items() if popcount(h) <= threshold)


#: A picture has "gone blank" when its ink falls below this fraction of the
#: ink the baseline recorded. DECLARED as a ratio, not calibrated to a
#: measurement: a per-fixture floor taken from today's render would turn every
#: legitimate content change red and create pressure to lower it, which is how
#: a ratchet stops meaning anything. A ratio is scale-free — it asks "did this
#: collapse by an order of magnitude", which is the question, and it degrades
#: gracefully: a fixture with 12 ink pixels needs to reach 1 to pass, i.e. the
#: rule becomes "went to zero", which is still exactly the defect.
INK_COLLAPSE_RATIO = 8


def ink_file(path: Path, crop: tuple[int, int] = (0, 0)) -> int:
    """Pixels that are not the picture's single most common grey level.

    A blank page — of any colour — has one level and therefore **zero ink**.
    Anything drawn on top of a uniform background has ink above zero. That is
    the whole claim; this is not a similarity measure and is never compared
    across fixtures, only against the same fixture's recorded value.

    ⚠️ It reads the *modal* level rather than "not white", so a dark-mode or
    tinted capture is measured the same way, and it takes the SAME ``crop`` as
    :func:`dhash_file` so the two describe the same rectangle. Computed from
    the 256-bucket histogram, which Pillow builds in C: the whole blind
    population of one face is ~1.4 s (measured, 115 images of 1206x2622).

    🔻 KNOWN LIMIT, STATED RATHER THAN HIDDEN: luminance collapses colour, so
    two different hues at the same grey level read as one. A picture that
    changes colour without changing brightness has no ink change — that case
    belongs to dHash and the control diff, not here.
    """
    Image = _load_pillow()
    with Image.open(path) as img:
        top, bottom = crop
        if top or bottom:
            width, height = img.size
            if height > top + bottom:
                img = img.crop((0, top, width, height - bottom))
        histogram = img.convert("L").histogram()
    return sum(histogram) - max(histogram)


# --------------------------------------------------------------------------- #
# Baseline manifest I/O
# --------------------------------------------------------------------------- #


def baseline_path(conformance_dir: Path, platform: str, env: str = DEFAULT_ENV) -> Path:
    return Path(conformance_dir) / "baselines" / env / f"{platform}.hashes.json"


def load_baseline(
    conformance_dir: Path, platform: str, env: str = DEFAULT_ENV
) -> dict | None:
    """Parsed baseline manifest, or None when none has been recorded."""
    path = baseline_path(conformance_dir, platform, env)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class BaselineUpdateSummary:
    out_path: Path
    platform: str
    hashed: int = 0
    env: str = DEFAULT_ENV
    #: Classification against the baseline that was already committed. Always
    #: computed, because "what else would this write have changed" is the
    #: question a bake cannot answer after the fact.
    new: tuple[str, ...] = ()
    same: tuple[str, ...] = ()
    moved: tuple[tuple[str, int], ...] = ()   # (name, hamming distance)
    #: Differences accepted WITHOUT failing the exact check, because the
    #: fixture's own layout says its picture is not stable (animated /
    #: async). Reported so the tolerance is visible every run rather than
    #: being an unstated exemption: the count and the names are printed, and
    #: any of these at or above the threshold is in `moved` instead.
    tolerated: tuple[tuple[str, int, str], ...] = ()
    #: How many screenshots are exempt from the EXACT check at all, whether
    #: or not any of them moved this run. Printed unconditionally: an
    #: exemption that only appears when it fires is invisible on the runs
    #: where it matters least and unreviewable on the rest.
    unstable_total: int = 0
    dropped: tuple[str, ...] = ()
    only_new: bool = False

    @property
    def written(self) -> int:
        return self.hashed


def update_baseline(
    conformance_dir: Path,
    platform: str,
    artifacts_dir: Path | None = None,
    env: str = DEFAULT_ENV,
    threshold: int | None = None,
    rendered_by: dict[str, str] | None = None,
    os_key: str | None = None,
    only_new: bool = False,
    refuse_if_moved: bool = False,
) -> BaselineUpdateSummary:
    """Hash every PNG under the platform's artifacts dir into the manifest.

    Deterministic: keys are sorted artifact filenames, no timestamps.
    *threshold* overrides the stored comparison threshold for this manifest —
    per-(env, platform) recalibration is the anticipated path when a
    renderer's measured repeat-run noise differs from the shared default
    (baselines/README.md records each calibration; measure before changing).

    *only_new* inserts entries the baseline does not have and touches nothing
    else. Without it this rewrites the manifest wholesale, which is the right
    thing for a recalibration and the wrong thing for "the four new fixtures
    never got baselines" — the wholesale write absorbs every drifted picture
    into the baseline at the same time, and a regression that gets absorbed
    stops being a regression. That default cost two lanes a hand-written merge
    script and a `git diff --numstat` check on 2026-09-04; the check was what
    made those bakes safe, not the command.

    Either way the summary carries the full classification (new / same / moved
    / dropped) so the caller can see what a wholesale write *would* have
    changed, before deciding it wanted one.
    """
    conformance_dir = Path(conformance_dir)
    if artifacts_dir is None:
        artifacts_dir = conformance_dir / "artifacts" / platform
    artifacts_dir = Path(artifacts_dir)
    if not artifacts_dir.is_dir():
        raise BaselineError(
            f"artifacts directory not found: {artifacts_dir} — run the {platform} suite first"
        )

    pngs = sorted(artifacts_dir.glob("*.png"))
    if not pngs:
        raise BaselineError(f"no screenshots under {artifacts_dir} — nothing to baseline")

    crop = chrome_crop(platform, env)
    measured = {png.name: dhash_file(png, crop) for png in pngs}
    # Measured for EVERY picture, not only the ones the ink check will read.
    # Which entries are blind to blanking is a function of the hash and the
    # threshold, so it moves when either does — recording ink only for
    # today's blind set would leave the next threshold change with no data
    # and no way to tell "never measured" from "measured as zero".
    measured_ink = {png.name: ink_file(png, crop) for png in pngs}

    # Classify against what is already committed, whichever mode we are in.
    previous = load_baseline(conformance_dir, platform, env) or {}
    # 🔻 WHAT THIS RUN IS COMPARED AGAINST: the OS-agnostic entries plus THIS
    # OS's bucket. An entry filed under a different OS is deliberately not
    # prior — separating those is the whole point of the key, and folding them
    # in here would reintroduce the cross-runtime comparison one level down.
    previous_by_os: dict = {k: dict(v) for k, v in (previous.get("hashes_by_os") or {}).items()}
    prior: dict[str, str] = dict(previous.get("hashes") or {})
    if os_key:
        prior.update(previous_by_os.get(os_key) or {})
    new_names = sorted(n for n in measured if n not in prior)
    same_names = sorted(n for n in measured if n in prior and prior[n] == measured[n])
    # A fixture whose picture is not a function of the code — a spinning
    # Indicator, an image still arriving — differs run to run on a correct
    # machine (measured: four runs, four pictures, one host). Holding those
    # to an EXACT match makes `--fail-on-moved` fire every time, and a gate
    # that always fires is one the operator learns to switch off. They are
    # judged at the same threshold the visual gate uses instead: still
    # caught when they move for real, not caught for existing.
    #
    # Everything else stays exact. A fixture outside this set that wobbles
    # fails by name, so the narrow set costs a named refusal, not silence.
    unstable = unstable_screenshots(conformance_dir)
    limit = DEFAULT_THRESHOLD if threshold is None else int(threshold)
    moved_pairs = tuple(
        (n, hamming(prior[n], measured[n]))
        for n in sorted(measured)
        if n in prior
        and prior[n] != measured[n]
        and (n not in unstable or hamming(prior[n], measured[n]) >= limit)
    )
    tolerated_pairs = tuple(
        (n, hamming(prior[n], measured[n]), unstable[n])
        for n in sorted(measured)
        if n in prior
        and prior[n] != measured[n]
        and n in unstable
        and hamming(prior[n], measured[n]) < limit
    )
    dropped_names = sorted(n for n in prior if n not in measured)

    if only_new:
        # Existing entries keep their committed hash; nothing is removed.
        hashes = dict(prior)
        hashes.update({n: measured[n] for n in new_names})
        hashes = {k: hashes[k] for k in sorted(hashes)}
    else:
        hashes = measured

    # Carve the availability-gated pictures into a per-OS bucket. Only these
    # move: the corpus at large is NOT a function of the running OS (measured
    # on the 2026-09-14 re-bake — the 61 entries that moved were every one a
    # system-DRAWN control, which is the SDK the host links against, a
    # different axis). Keying the whole file by OS would assert the stronger
    # thing and make every re-bake answer a question it did not ask.
    by_os = {k: dict(v) for k, v in previous_by_os.items()}
    os_dependent = os_dependent_screenshots_for(conformance_dir)
    carved = {n: hashes.pop(n) for n in sorted(hashes) if n in os_dependent}
    if carved:
        if not os_key:
            raise BaselineError(
                "these pictures resolve through an availability check, so they cannot be "
                "filed without the OS that drew them: "
                + ", ".join(sorted(carved))
                + " — pass the run's `runner` (os_key) so they land under "
                "hashes_by_os.<os>. Baking them OS-agnostically is the comparison this "
                "key exists to prevent, and dropping them silently would remove them "
                "from visual coverage."
            )
        bucket = dict(by_os.get(os_key) or {})
        bucket.update(carved)
        by_os[os_key] = {k: bucket[k] for k in sorted(bucket)}

    # Ink follows whatever `hashes` / `by_os` ended up holding, so the two
    # can never describe different key sets. In only-new mode an entry that
    # kept its committed hash keeps its committed ink with it: re-measuring it
    # would pair a fresh ink with a stale hash, which is the one combination
    # that makes the collapse check compare two different renders.
    prior_ink: dict[str, int] = dict(previous.get("ink") or {})
    if os_key:
        prior_ink.update((previous.get("ink_by_os") or {}).get(os_key) or {})

    def _ink_for(names) -> dict[str, int]:
        out: dict[str, int] = {}
        for n in sorted(names):
            if only_new and n not in new_names and n in prior_ink:
                out[n] = int(prior_ink[n])
            elif n in measured_ink:
                out[n] = measured_ink[n]
            # else: no measurement and nothing committed — left ABSENT, which
            # the comparison reports as uncovered rather than as zero ink.
        return out

    ink_by_os = {k: _ink_for(v) for k, v in by_os.items()}

    out_path = baseline_path(conformance_dir, platform, env)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_generated": json_marker(
            source=f"conformance/artifacts/{platform}", generator=GENERATOR_NAME
        ),
        "platform": platform,
        "environment": env,
        "algorithm": ALGORITHM,
        "threshold": DEFAULT_THRESHOLD if threshold is None else int(threshold),
        # Which library drew these pixels. The manifest already recorded how
        # the measurement was taken (platform, env, algorithm, threshold) and
        # nothing about what was measured: conformance-mobile checks the
        # libraries out at `master` / `main`, so two bakes at the same
        # jsonui-cli commit can legitimately hold different pictures, and the
        # baseline could not say why. Thirteen regressions in one run were
        # neither fixture nor codegen; two lanes reached "the library moved"
        # by elimination because the device could not point at it.
        #
        # Metadata only — deliberately outside `hashes` so it never
        # participates in a comparison. Folding it in would make a library
        # bump read as "the picture changed", which is the confusion this
        # exists to end.
        # An additive bake did not re-draw the pictures that were already
        # here, so it must not restate who drew them. Passing nothing in
        # only-new mode keeps the committed provenance rather than blanking it.
        "rendered_by": (
            dict(sorted(rendered_by.items()))
            if rendered_by
            else dict(sorted((previous.get("rendered_by") or {}).items()))
            if only_new
            else {}
        ),
        "hashes": hashes,
        # Availability-gated pictures, keyed by the MAJOR OS that drew them.
        # Empty for every platform whose runner does not name an OS (android
        # reports a uiautomator version, web a playwright one).
        "hashes_by_os": {k: by_os[k] for k in sorted(by_os)},
        # Non-background pixel counts, in the same key sets as `hashes`. Read
        # only for the entries `blind_to_blanking` derives — where the hash
        # cannot tell the picture from a blank page — and never compared
        # across fixtures. See `ink_file` and `INK_COLLAPSE_RATIO`.
        "ink": _ink_for(hashes),
        "ink_by_os": {k: ink_by_os[k] for k in sorted(ink_by_os)},
    }
    # 🔻 THE REFUSAL HAS TO HAPPEN BEFORE THE WRITE, AND IT DID NOT.
    # `--fail-on-moved` used to be checked by the CLI on the summary this
    # function returns — i.e. AFTER the line below had already replaced the
    # file. The exit code was honest and the baseline was gone: measured
    # 2026-09-15, baking two android entries with the flag on landed 797
    # insertions / 800 deletions and then exited 1, so the flag performed the
    # very thing it exists to prevent. Worse, the run printed "a wholesale bake
    # rewrote the moved entries above" one line ABOVE the error, so the two
    # statements that contradicted each other were in the same output.
    #
    # ⚠️ The measurement that vouched for the flag was the symptom: a second
    # run against the already-baked set reported `moved 0`, and that was read
    # as "it fires on the thing and not on everything". It is evidence the
    # FIRST run wrote. A flag that refused would report the same N twice.
    if refuse_if_moved and moved_pairs:
        raise BaselineMoved(out_path, moved_pairs)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return BaselineUpdateSummary(
        out_path=out_path,
        platform=platform,
        hashed=len(hashes),
        env=env,
        new=tuple(new_names),
        same=tuple(same_names),
        moved=moved_pairs,
        dropped=tuple(dropped_names),
        only_new=only_new,
        tolerated=tolerated_pairs,
        unstable_total=len(unstable),
    )


# --------------------------------------------------------------------------- #
# Comparison (consumed by the report)
# --------------------------------------------------------------------------- #


@dataclass
class VisualComparison:
    """Outcome of comparing one platform's artifacts against its baseline."""

    platform: str
    baseline_exists: bool = False
    algorithm_mismatch: str | None = None  # baseline algorithm when incompatible
    threshold: int = DEFAULT_THRESHOLD
    compared: int = 0
    regressions: list[tuple[str, int]] = field(default_factory=list)  # (name, distance)
    no_baseline: list[str] = field(default_factory=list)  # screenshot without baseline hash
    missing_artifact: list[str] = field(default_factory=list)  # baseline hash without PNG
    error: str | None = None  # e.g. Pillow missing

    #: Entries whose committed hash is within the threshold of a blank page,
    #: so the Hamming comparison above cannot see them empty out. DERIVED
    #: every run from the committed hashes — see `blind_to_blanking`.
    blind: list[str] = field(default_factory=list)
    #: How many of `blind` the ink check actually judged. Printed whether or
    #: not it is zero: a check that only appears when it fires is invisible
    #: on exactly the runs that are supposed to prove it is alive.
    ink_checked: int = 0
    #: (name, baseline ink, measured ink, what happened). `collapsed` is the
    #: ticketed defect; `appeared` is the same blindness the other way round
    #: — a fixture recorded as empty that has started drawing — and costs
    #: nothing extra to catch.
    ink_regressions: list[tuple[str, int, int, str]] = field(default_factory=list)
    #: Blind entries with no committed ink. A baseline baked before this
    #: existed has none, so these are NOT passes: they are reported as
    #: uncovered and counted separately until the face is re-baked.
    ink_uncovered: list[str] = field(default_factory=list)
    #: Blind entries whose picture is not a function of the code (a spinning
    #: Indicator, an image still arriving). Their ink legitimately varies run
    #: to run, so they are exempt from the collapse check — and named, so the
    #: exemption is visible rather than assumed.
    ink_tolerated: list[str] = field(default_factory=list)


def _judge_ink(
    comparison: VisualComparison,
    name: str,
    png: Path,
    crop: tuple[int, int],
    committed: dict,
    unstable: dict,
) -> None:
    """Rule on one blind entry. Every one lands in exactly one bucket."""
    if name in unstable:
        # Its picture is not a function of the code, so its ink is not either
        # — an Indicator mid-animation can legitimately be near-empty. Named,
        # not silently dropped.
        comparison.ink_tolerated.append(name)
        return
    recorded = committed.get(name)
    if recorded is None:
        # ABSENCE IS AMBIGUOUS HERE — a baseline baked before ink existed
        # looks exactly like one whose entry was deleted — so it is reported,
        # never read as zero. Reading it as zero would make every pre-ink
        # baseline claim full coverage it does not have.
        comparison.ink_uncovered.append(name)
        return
    recorded = int(recorded)
    measured = ink_file(png, crop)
    comparison.ink_checked += 1
    if recorded > 0 and measured * INK_COLLAPSE_RATIO < recorded:
        comparison.ink_regressions.append((name, recorded, measured, "collapsed"))
    elif recorded == 0 and measured > 0:
        comparison.ink_regressions.append((name, recorded, measured, "appeared"))


def compare_platform(
    conformance_dir: Path,
    platform: str,
    screenshot_names: list[str],
    artifacts_dir: Path | None = None,
    env: str = DEFAULT_ENV,
    os_key: str | None = None,
) -> VisualComparison:
    """Compare the current artifacts of *screenshot_names* to the baseline.

    ``screenshot_names`` are PNG filenames (the report derives them from the
    ``screenshot`` fields in the platform's results). Every name ends up in
    exactly one bucket — a missing baseline is reported, never a silent pass.
    """
    conformance_dir = Path(conformance_dir)
    if artifacts_dir is None:
        artifacts_dir = conformance_dir / "artifacts" / platform
    artifacts_dir = Path(artifacts_dir)

    comparison = VisualComparison(platform=platform)

    baseline = load_baseline(conformance_dir, platform, env)
    if baseline is None:
        comparison.no_baseline = list(screenshot_names)
        return comparison
    comparison.baseline_exists = True
    comparison.threshold = int(baseline.get("threshold", DEFAULT_THRESHOLD))

    # A manifest that records which environment baked it must match the
    # environment this comparison is for — comparing across renderers is
    # exactly the wholesale-mismatch failure the env key exists to prevent.
    # (Manifests from before the env key have no field; their location under
    # baselines/<env>/ is the claim.)
    # 🔑 THE RE-BAKE LINE BELOW CARRIES `--fail-on-moved`, AND IT IS THE ONE
    # RECIPE NO DOCUMENT CAN COVER. This string is handed to the operator by
    # the tool, at the moment a comparison stopped because the baseline no
    # longer matches — i.e. immediately before a bake, to the reader who is
    # following the tool rather than the README. Without the flag the bake it
    # names rewrites every changed picture and exits 0.
    #
    # ⚠️ KEPT ON ONE SOURCE LINE even though it is long: split across two
    # f-strings the recipe stops being greppable, and every scanner for it
    # — this repo's gate, a person's grep, another lane's audit — is line
    # oriented. The gate caught exactly that when this fix was first written
    # across two lines.
    stored_env = baseline.get("environment")
    if stored_env is not None and stored_env != env:
        comparison.error = (
            f"baseline {baseline_path(conformance_dir, platform, env).name} records "
            f"environment '{stored_env}' but this comparison is for '{env}' — "
            f"re-bake with `jui conformance baseline update --platform {platform} --env {env} --fail-on-moved`"
        )
        return comparison

    if baseline.get("algorithm") != ALGORITHM:
        comparison.algorithm_mismatch = str(baseline.get("algorithm"))
        return comparison

    hashes: dict = dict(baseline.get("hashes", {}))
    # An availability-gated picture is only ever compared against one drawn on
    # the same major OS. With no os_key — or with a baseline that holds no
    # bucket for this one — those names simply have no expected value, so they
    # land in `no_baseline` and are REPORTED as uncovered. That is the correct
    # answer: we have no baseline for this OS. Falling back to another OS's
    # bucket would be the cross-runtime comparison the key exists to prevent,
    # and falling back to silence would drop them out of coverage unseen.
    if os_key:
        hashes.update(baseline.get("hashes_by_os", {}).get(os_key) or {})
    crop = chrome_crop(platform, env)

    # 🔻 THE SECOND PREDICATE, AND WHY IT IS NOT A SECOND THRESHOLD.
    # Lowering the Hamming threshold would not close this: the entries below
    # are within it of a BLANK PAGE, so no threshold that lets a normal render
    # pass can also catch them emptying out. They need a different question
    # asked of them, on a population derived from the same hashes the gate
    # already trusts.
    ink_committed: dict = dict(baseline.get("ink") or {})
    if os_key:
        ink_committed.update((baseline.get("ink_by_os") or {}).get(os_key) or {})
    blind = set(blind_to_blanking(hashes, comparison.threshold))
    comparison.blind = sorted(blind)
    unstable = unstable_screenshots(conformance_dir)

    seen = set()
    for name in screenshot_names:
        seen.add(name)
        expected = hashes.get(name)
        if expected is None:
            comparison.no_baseline.append(name)
            continue
        png = artifacts_dir / name
        if not png.is_file():
            comparison.missing_artifact.append(name)
            continue
        try:
            distance = hamming(dhash_file(png, crop), expected)
            if name in blind:
                _judge_ink(comparison, name, png, crop, ink_committed, unstable)
        except BaselineError as exc:
            comparison.error = str(exc)
            return comparison
        comparison.compared += 1
        if distance > comparison.threshold:
            comparison.regressions.append((name, distance))

    # Baseline entries whose fixture no longer produced a screenshot.
    for name in hashes:
        if name not in seen:
            comparison.missing_artifact.append(name)

    return comparison
