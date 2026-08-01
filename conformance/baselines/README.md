# Screenshot baselines (same-platform visual regression)

This directory holds the committed visual-regression signal for the
conformance suite: one perceptual-hash manifest per **render environment and
platform** (`<env>/<platform>.hashes.json`, `@generated` by
`jui conformance baseline update`). **PNG screenshots are never committed** —
they live under `conformance/artifacts/<platform>/` locally and as CI
artifacts only.

## Environments (`<env>/`)

A baseline is a fact about one renderer. The 2026-08-01 full CI run
(30689985386) proved it wholesale: against locally-baked baselines a fresh,
internally-healthy CI render (0 fail / 0 error, ratchets exactly on their
ceilings) mismatched **every** compared screenshot on ios (534) and android
(506) at the calibrated dhash-64 threshold 8. Comparing across render
environments measures the environment, not the change under test — so each
environment gets its own baseline set and only ever compares against itself:

- `local/` — developer-machine renders (the pre-env-key baselines live on
  here unchanged; local gate runs default to this set)
- `ci/` — GitHub Actions runners (macos-15 simulator / emulator / ubuntu
  Chromium), baked **from CI run artifacts**, never from a local render

Each manifest records its `environment`; the loader refuses to compare a
manifest under a different env key than it was baked for. Ratchet ceilings
(`../gate_ratchet.json`) nest by the same env keys.

```sh
# bake the ci set from downloaded CI artifacts:
jui conformance baseline update --platform ios --env ci --artifacts <downloaded>/artifacts/ios
```

## Workflow

```sh
# after a green suite run on <platform> (local machine):
jui conformance baseline update --platform web     # records under baselines/local/
jui conformance report                             # compares artifacts vs baselines/local/
```

The report's *Visual regression* section shows, per platform: compared /
regressions (distance > threshold) / **no-baseline** (screenshot without a
recorded hash — reported, never a silent pass) / missing-artifact. Update the
baseline only after reviewing that a visual change is intentional.

Baselines only ever compare **within the same platform and environment**.
Cross-platform pixel comparison is out of scope by design (fonts and
rasterizers differ).

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

### Android calibration (2026-07-03)

Pixel_Tablet emulator (API 35, 2560x1600), Compose dynamic host,
`UiDevice.takeScreenshot`, 467 visual screenshots per run.

Naive repeat-run variance (two independent full runs, no host stabilization):

| distance | screenshots |
|---|---|
| 0 | 403 (1 byte-identical PNG) |
| 1 | 61 |
| 3 | 1 |
| 10 / 24 | 1 each — host races, see below |

The 61x distance-1 population was the **live status-bar clock** (full-screen
captures). The 10/24 outliers were **frame-settle races after the host's
in-place fixture swap** (a stale drop shadow from the previous fixture; a
`flexible` TextView captured mid-height-settle) — host bugs, not renderer
noise. Both sources were fixed in `conformance-host` (SystemUI demo-mode
clock freeze in `run_conformance.sh`; 150ms compositor settle before visual
steps in the suite).

Stabilized repeat-run variance (two independent full runs):

| distance | screenshots |
|---|---|
| 0 | **467 of 467** (all byte-identical PNGs) |

Measured noise ceiling = **0**. Threshold stays at the cross-platform **8**
(any nonzero distance on this host is already signal; 8 keeps headroom for
emulator image / GPU driver drift between machines while remaining ~4x below
the smallest genuine change measured on the 64x64 grid).

### Android **ci-env** calibration (2026-08-02) — threshold 12

The local numbers above are one quiet AVD talking to itself. CI is a fresh
emulator instance per run, and cross-**instance** variance was measured over
four full CI runs (30692120530 / 30699392057 / 30704621712 / 30706830607):

| distance | screenshots (pairwise, common set) |
|---|---|
| 0 | 455 of 468 |
| 3 | 12 |
| 9–11 | the SafeAreaView / TabView family (14 shots incl. their controls) |

The 9–11 band is not the renderer: the API-34 tablet **taskbar** (drawn over
every capture) shows recents whose order depends on instrumentation-attempt
relaunches — two stable orders, so any fixture range can flap by ~9–11 when
an attempt boundary moves between runs. `ci/android.hashes.json` therefore
stores **threshold 12** (measured noise ceiling 11 + 1, still 1.5x below the
smallest genuine change measured on this host: 18). The root fix is
host-side — hide/exclude the taskbar from capture — and drops the threshold
back to 8 when it lands. `CheckBox_isOn__true.png` stays excluded from the
manifest entirely (fixture-swap race, see gate_ratchet.json).

The committed `android.hashes.json` was recorded from a verified-good run:
511 pass / 132 skipped (not android-applicable) / 0 fail / 0 error on the
v2 manifest (643 fixtures, 19 interactive).

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
  "environment": "local",
  "algorithm": "dhash-64",
  "threshold": 8,
  "hashes": { "<Screenshot name>.png": "<1024 hex chars>" }
}
```

(`environment` is absent from manifests baked before the env key existed —
their location under `baselines/<env>/` is the claim; the next
`baseline update` writes the field.)

Keys are artifact filenames (`<Section>_<attr>__<case>.png` — the
`screenshot` step names from the generated tests), sorted; no timestamps.
An `algorithm` mismatch with the current implementation marks the whole
baseline stale in the report (re-run `baseline update`) instead of comparing
incompatible hashes.
