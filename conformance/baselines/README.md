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
