# Screenshot baselines (same-platform visual regression)

This directory holds the committed visual-regression signal for the
conformance suite: one perceptual-hash manifest per platform
(`<platform>.hashes.json`, `@generated` by `jui conformance baseline update`).
**PNG screenshots are never committed** — they live under
`conformance/artifacts/<platform>/` locally and as CI artifacts only.

## Workflow

```sh
# after a green suite run on <platform>:
jui conformance baseline update --platform web     # record current rendering
jui conformance report                             # compares artifacts vs baseline
```

The report's *Visual regression* section shows, per platform: compared /
regressions (distance > threshold) / **no-baseline** (screenshot without a
recorded hash — reported, never a silent pass) / missing-artifact. Update the
baseline only after reviewing that a visual change is intentional.

Baselines only ever compare **within the same platform**. Cross-platform
pixel comparison is out of scope by design (fonts and rasterizers differ).

## Algorithm

`dhash-64`: grayscale → LANCZOS resize to 65x64 → each bit = "pixel brighter
than its right neighbour" → 4096-bit hash (1024 hex chars). Distance =
Hamming distance. Implementation:
`jui_tools/jui_cli/conformance/baseline.py` (Pillow required — optional
extra `jui-tools[conformance]`).

### Why a 64x64 grid (and not the classic 8x8/16x16)

Conformance screenshots are full-page 1024x768 captures where the component
under test often covers ~1% of the frame (e.g. a 100x100 box). During
calibration (2026-07-02) a deliberately injected rendering change (gradient
direction flip inside a 100x100 GradientView) measured:

| grid | Hamming distance of the injected change |
|---|---|
| 16x16 | **0 — undetected** (the component averages into a single cell) |
| 32x32 | 5 |
| 64x64 | **34** |

### Threshold: 8 (measured, not guessed)

Repeat-run variance at 64x64, measured over two independent full web suite
runs (Playwright / headless chromium, 466 visual screenshots):

| distance | screenshots |
|---|---|
| 0 | 458 (431 byte-identical PNGs) |
| 1 | 2 |
| 2 | 6 (Slider / `input type=number` anti-aliasing flicker) |

Measured max noise = 2. Threshold **8** = 4x the measured noise ceiling and
~4x below the smallest genuine change we injected (34). The threshold is
stored in each baseline manifest, so recalibration is per-platform when the
iOS/Android hosts land (expect more anti-aliasing variance on device
renderers; measure before changing).

### iOS calibration (2026-07-03)

SwiftJsonUI SwiftUI dynamic host (ConformanceHost), iPhone 16 Pro simulator,
490 visual screenshots, two independent full suite runs.

**The dominant iOS noise source is NOT the renderer — it is the simulator
status-bar clock.** A first calibration pair with a live clock measured
distances up to 31 across ~490 screenshots (the full-page captures include
the status bar; changing clock digits flip a band of 64x64 cells). Freezing
the status bar first (`xcrun simctl status_bar <udid> override --time 9:41
--batteryLevel 100 --cellularBars 4 --wifiBars 3`) collapses that entirely:

| distance | screenshots |
|---|---|
| 0 | 486 (440 byte-identical PNGs) |
| 1 | 3 (Indicator activity-spinner frames) |
| 6 | 1 (`SelectBox_selectedValue` — anti-aliasing on a near-full-frame card edge + thin chevron) |

Measured max noise = **6** (frozen clock), still below the committed
threshold **8**, so iOS keeps the shared threshold — no per-platform value
needed. The two distance-1 outliers are `Indicator` fixtures (an animated
`UIActivityIndicatorView` spinner has no fixed frame); the distance-6
`SelectBox` outlier is sub-pixel AA on a card that fills most of the frame,
not a rendering regression (verified by eye). The committed
`ios.hashes.json` was recorded from a verified-good run (533 pass / 110
skipped / 0 fail) with the status bar frozen.

Runner prerequisite: freeze the status bar before `run_conformance.sh`, or
per-run clock drift will exceed the threshold on the status-bar band.

## File format

```json
{
  "_generated": { "sentinel": "@generated", "...": "..." },
  "platform": "web",
  "algorithm": "dhash-64",
  "threshold": 8,
  "hashes": { "<Screenshot name>.png": "<1024 hex chars>" }
}
```

Keys are artifact filenames (`<Section>_<attr>__<case>.png` — the
`screenshot` step names from the generated tests), sorted; no timestamps.
An `algorithm` mismatch with the current implementation marks the whole
baseline stale in the report (re-run `baseline update`) instead of comparing
incompatible hashes.
