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
#: Local runs are NOT cropped and must not be: that AVD has no taskbar, so the
#: same rows hold real content there (the TabView tab bar, alignBottom, fill
#: clamps). This is exactly the asymmetry the env key exists to carry —
#: baselines never cross environments, so the crop never has to either.
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
PLATFORM_ENV_CHROME_CROP: dict[tuple[str, str], tuple[int, int]] = {
    ("android", "ci"): (48, 120),
    ("ios", "ci"): (160, 0),
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


def update_baseline(
    conformance_dir: Path,
    platform: str,
    artifacts_dir: Path | None = None,
    env: str = DEFAULT_ENV,
    threshold: int | None = None,
    rendered_by: dict[str, str] | None = None,
) -> BaselineUpdateSummary:
    """Hash every PNG under the platform's artifacts dir into the manifest.

    Deterministic: keys are sorted artifact filenames, no timestamps.
    *threshold* overrides the stored comparison threshold for this manifest —
    per-(env, platform) recalibration is the anticipated path when a
    renderer's measured repeat-run noise differs from the shared default
    (baselines/README.md records each calibration; measure before changing).
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
    hashes = {png.name: dhash_file(png, crop) for png in pngs}

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
        "rendered_by": dict(sorted((rendered_by or {}).items())),
        "hashes": hashes,
    }
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return BaselineUpdateSummary(
        out_path=out_path, platform=platform, hashed=len(hashes), env=env
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


def compare_platform(
    conformance_dir: Path,
    platform: str,
    screenshot_names: list[str],
    artifacts_dir: Path | None = None,
    env: str = DEFAULT_ENV,
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
    stored_env = baseline.get("environment")
    if stored_env is not None and stored_env != env:
        comparison.error = (
            f"baseline {baseline_path(conformance_dir, platform, env).name} records "
            f"environment '{stored_env}' but this comparison is for '{env}' — "
            f"re-bake with `jui conformance baseline update --platform {platform} --env {env}`"
        )
        return comparison

    if baseline.get("algorithm") != ALGORITHM:
        comparison.algorithm_mismatch = str(baseline.get("algorithm"))
        return comparison

    hashes: dict = baseline.get("hashes", {})
    crop = chrome_crop(platform, env)
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
