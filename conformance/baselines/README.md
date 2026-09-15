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
  Chromium), baked **from CI run artifacts**, never from a local render.
  The iOS toolchain is pinned — see below; `local/` and `ci/` are now on
  **different iOS SDKs**, which is a fact about the pictures, not an oversight

Each manifest records its `environment`; the loader refuses to compare a
manifest under a different env key than it was baked for. Ratchet ceilings
(`../gate_ratchet.json`) nest by the same env keys.

### The toolchain behind `ci/` (iOS)

| | |
|---|---|
| Xcode | **26.3** (`setup-xcode` in conformance-mobile.yml, both iOS jobs) |
| SDK | iphonesimulator **26.2** |
| runtime | iOS **26.2** — `SIMULATOR_OS: "26"`, resolved newest-within-the-pin |
| device | iPhone 16 Pro |

Each run re-measures all four and passes them as `ios.toolchain`, so the
manifest says what drew it rather than this table being the only record.

**Why it is pinned at all.** `simctl` lists every runtime INSTALLED on the
machine, not the ones the selected Xcode shipped with, and the host script took
the newest of them — so the Xcode pin was honoured while the runtime underneath
moved with the runner image. It did move: the committed iOS runner version goes
`18.6 -> 26.2 -> 18.6` across four bakes with the Xcode pin unchanged, and at
one point the two iOS lanes disagreed with each other inside one tree
(`results/ios` = ios-18.6 while `codegen/ios` = ios-26.2 — the pair
`gate --parity` compares). An unmatched pin is now fatal rather than a
fall-through to a neighbouring runtime.

**Why Xcode 26.** iOS-26-only attributes compile out on the 18.5 SDK, and a
fixture that renders as nothing still produces a baseline that matches itself —
it passes while testing nothing. `common/glass__true` was exactly that: both
faces drew the control, parity held at 0, and the agreement was two absences.
On the first run after the move it measured 151 and the defect surfaced.

🔻 **THE SDK, NOT THE RUNTIME, IS WHAT MOVED THE PICTURES.** The 2026-09-14
re-bake moved 61 of 856 entries, and the previous baseline had ALREADY been
drawn on an iOS 26.2 runtime — what changed was the SDK the host links against
(18.5 -> 26.2). The 61 are `26 Switch / 12 TabView / 10 Segment / 6 control_* /
5 Slider / 2 Collection`, and **zero** non-system-drawn fixtures. That zero is
the discriminator: an SDK appearance change touches exactly the controls the
system draws, and a regression in our own code would not respect that line.
So do not read `simulator_os` alone when a bake moves; read all four.

### Availability-gated pictures: `hashes_by_os`

`glass` resolves through `#available(iOS 26.0, *)`, which asks the RUNNING OS —
so the same fixture is a different picture on iOS 25 and 26. Those entries are
keyed by the MAJOR OS that drew them:

```json
"hashes":       { ... 865 entries ... },
"hashes_by_os": { "26": { "common_glass__true.png": "...", "common_glass__false.png": "..." } }
```

**Per entry, not per file.** Splitting the manifest into
`<platform>-<os>.hashes.json` says the whole corpus depends on the running OS,
and the 2026-09-14 re-bake measured that it does not: the 61 entries that moved
are every one a system-DRAWN control (26 Switch / 12 TabView / 10 Segment /
6 control_* / 5 Slider / 2 Collection, and zero others). That is the SDK the
host links against — a different axis. Only the availability-gated entries get
an OS key.

The key comes from the run's own `runner` block (`ios-26.2` -> `26`), read from
the results file NEXT TO the artifacts being baked, not from the checkout —
measured: the checked-out `results/ios.results.json` said ios-18.6 while the
artifacts were drawn on ios-26.2, and taking the checkout's copy would have
filed iOS 26 pictures under key 18. A key that exists and is wrong is worse
than no key. The patch level is dropped on purpose: 26.2 and 26.3 answer
`#available(iOS 26.0, *)` identically, and every split costs a re-bake that
proves nothing.

A picture with no bucket for the running OS is reported as `no_baseline` —
uncovered and visible — never compared against another OS's value and never
silently skipped. Measured both ways against the committed ci baseline:

| os_key | compared | no_baseline |
|---|---|---|
| `26` (the OS that drew them) | 3 of 3 | — |
| `18` / `27` / none | 1 of 3 | the two glass entries |

The OS-agnostic probe is compared in every row; that is the control that says
the key gates the right entries and not the corpus.

### The device behind `local/`

An env key names a class of renderer, and within `local/` the class has to be
narrow enough that a re-bake means something. The iOS manifest now RECORDS its
own toolchain and device in `rendered_by.ios.toolchain`, so that half is no
longer a claim only this file makes; android's is still declared here.

| platform | reference device |
|---|---|
| ios | **iPhone 16 Pro, iOS 26.5, simulator `3B852800-3383-4374-9BB6-F0C486C474A4`** — same device MODEL as the driver gates, moved to iOS 26 on 2026-09-15 |
| android | AVD **`conf_ci`** (android-35 google_apis_playstore_tablet arm64-v8a, 10G data) |

🔻 **A CLAIM THAT STOOD HERE WAS FALSE, AND ITS REFUTATION WAS ALREADY IN THIS
REPOSITORY.** This file said moving `local/` to iOS 26 would also have to
change the device, "because iOS 26 offers no iPhone 16 Pro at all (its runtimes
ship the iPhone 17 family)". Measured 2026-09-15: every installed iOS runtime —
18.6, 26.4, 26.5 **and 27.0** — lists `iPhone 16 Pro` in its
`supportedDeviceTypes`. What is true is narrower: Xcode's DEFAULT DEVICE SET
for iOS 26 contains no iPhone 16 Pro, so `simctl list devices` shows none until
one is created. `simctl create` makes one in a second. And the refutation did
not need that measurement at all: `conformance-mobile.yml` has been running
`SIMULATOR_NAME: iPhone 16 Pro` with `SIMULATOR_OS: "26"` green since
2026-09-14 — the workflow in this repo was already doing the thing this
paragraph called impossible.

⇒ The move changed the OS and NOT the device, so the sentence tying this model
to the driver gates survives intact.

**What the move bought, measured both ways.** `ci/` is iOS 26.2 and `local/`
was iOS 18.6, and the two env keys never compare — but that is a statement
about the gate, not about the pictures, and the pictures were in fact
unrelated:

| | shared entries | identical hash | differing | beyond threshold |
|---|---|---|---|---|
| before (`ci` 26.2 vs `local` 18.6) | 856 | **0** | 856 | 829 |
| after (`ci` 26.2 vs `local` 26.5) | 867 | **846** | 21 | 1 |

Twenty-one of the remaining differences are Label text rasterisation across
26.2 / 26.5 and across two machines. So `local/` and `ci/` now differ by the
MACHINE and a point release, which is what having two env keys was supposed to
isolate; before the move they differed by the whole operating system and the
comparison could not see anything else.

Bake `local/` from that device and no other. Two simulators of the *same*
model and OS version are not interchangeable: `D6A1DD42` and `C13F2A69`, both
"iPhone 16 Pro / iOS 18.6", rendered the same corpus with 849 of 852 hashes
moved while the content was byte-identical below the status bar (2026-09-04).
Since the ios lane now crops that band (`PLATFORM_ENV_CHROME_CROP`), a
sibling device no longer reads as a whole-corpus regression — but everything
outside the band is still a fact about one device, so the declaration stands.

Record what rendered a set with `--rendered-by`, which is the other half of
the same question:

🔑 **`--fail-on-moved` IS IN EVERY RECIPE BELOW ON PURPOSE** — but read the next
paragraph before trusting it. Without the flag the bake prints the `MOVED` list
and exits 0, so the only thing standing between a regression and the baseline is
whether a person read past the end of a long output. The flag makes the exit code
carry the answer, which is what forces the reading.

🔴 **IT DOES NOT STOP THE BAKE. IT REPORTS AFTER WRITING.** An earlier version of
this page said "the bake STOPS and names the count" — measured 2026-09-15, that is
false. `update_baseline` writes the file unconditionally (`baseline.py:425`) and the
flag is checked on the summary it returns (`conformance_cmd.py:1380`), so the
baseline on disk has ALREADY absorbed every moved entry by the time you read the
error. The tool says so itself, one line above the error: *"a wholesale bake rewrote
the moved entries above — every one of them is now the baseline, including any that
were regressions."* Filed as
`docs/bugs/2026-09-15-fail-on-moved-writes-the-baseline-before-it-refuses.md`.

```sh
jui conformance baseline update --platform ios --env local --fail-on-moved \
  --artifacts <run>/artifacts/ios --rendered-by swiftjsonui=<sha>
```

```sh
# bake the ci set from downloaded CI artifacts:
jui conformance baseline update --platform ios --env ci --fail-on-moved \
  --artifacts <downloaded>/artifacts/ios
```

**When it exits non-zero** (`ERROR: --fail-on-moved and N entr(y/ies) moved`),
the very first thing to do is **undo the write**:

```sh
git restore conformance/baselines/<env>/<platform>.hashes.json
```

That restore is the actual refusal; the exit code is only the notification. Then
read every `MOVED` line — each carries its own hamming distance — and decide per
entry whether that picture SHOULD have changed. `unstable` lines are a different
list and never enter `N`. Only then write, choosing deliberately:

- **new entries only** — `--only-new` (leaves every moved entry at its committed hash)
- **a few named entries** — edit those hashes by hand and assert the count
  (`changed=N / added=0 / removed=0` against `HEAD`); this is the only way to take
  two entries and leave 786 alone
- **wholesale** — re-run without the flag, knowing it absorbs *every* moved entry

⚠️ **`N` IS NOT THE NUMBER THAT GETS WRITTEN.** `N` counts entries over the visual
gate's threshold; the bake rewrites every entry whose hash changed at all. Measured
2026-09-15 on android: the gate called it **2 regressions**, the bake reported **788
moved**, and the file took 797 insertions / 800 deletions.

🔴 **A RETRACTED MEASUREMENT USED TO SIT HERE.** It read: *"the flag exits 1 with
'2 entr(y/ies) moved', and on a re-run against the already-baked set it exits 0 with
`moved 0`. It fires on the thing and not on everything."* That second run is not
evidence the flag discriminates — **it is evidence the first run wrote**. A flag that
truly refused would report the same `N` both times, because nothing would have
changed between them. The observation was correct and the inference was backwards.
⭐ That comparison is therefore the right arm for the fix: **run the same bake twice
and require the same `N`.**

## Workflow

```sh
# after a green suite run on <platform> (local machine):
jui conformance baseline update --platform web --fail-on-moved   # under baselines/local/
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

### Fixtures whose picture is not stable (2026-09-05)

Two shapes do not draw the same thing twice, so `baseline update
--fail-on-moved` cannot hold them to an exact match. Measured on ONE host
(`Sources/` = f4cca50), ONE device (iPhone 16 Pro `C13F2A69`), ONE corpus,
four runs — hamming against the committed baseline:

| fixture | run 1 | run 2 | run 3 | run 4 |
|---|---|---|---|---|
| `Indicator/color__alias_tint` | 1 | 0 | 3 | 3 |
| `__control/NetworkImage__no-defaultImage_url-efd3e3a7` | 1 | 0 | 0 | 2 |

Raw PNG bytes differed in every run. The NetworkImage control matched the
baseline EXACTLY on one run and differed on the next, so a single
observation cannot separate "flaky" from "the library moved it one bit" —
both predict that reading. Two runs is the minimum.

This is the second sighting of the class, not the first: the iOS calibration
above measured distance 1 on **3 Indicator activity-spinner frames** out of
490 on 2026-07-03, with the clock already frozen.

**The set, and what is NOT in it.** `visual_stability.py` derives it from
what each fixture's layout DECLARES — an `Indicator` anywhere (animated), or
a `NetworkImage` with no `defaultImage` (async) — never from a list of
names, so a rename cannot drop a fixture out and a new fixture of the same
shape joins without maintenance. On the current corpus that is **18
screenshots**.

⚠️ **Two of those 18 are measured; the other 16 are unmeasured members of a
measured class.** `SelectBox_selectedValue` sits at distance 6 in the
07-03 calibration — ONE observation, not reproduced on 09-05 — and is
deliberately NOT in the set. It is named here so the next person sees it.

**What the narrow set costs.** A fixture outside it that wobbles still fails
the exact check, by name. The next unstable class arrives as a named
refusal, not as a repeat of the 09-05 investigation.

🔻 **"SMALL DISTANCE" IS NOT A MEMBERSHIP TEST — AND THE BAKE NEVER ASKED YOU
TO GUESS.** Its output already separates the two, with different words and
different counters:

```
  new 0  same 861  moved 2  dropped 0
    MOVED    common_glass__true.png  hamming=151  -> REWRITTEN
    MOVED    control_Web.png         hamming=2    -> REWRITTEN
  visual-stability: 18 screenshot(s) exempt from the exact check; 4 differed this run
    unstable Indicator_color__static.png  hamming=2  (not exact-checked: animated …)
    …
```

`moved` is **2**. The four exempt ones are counted separately and never enter
that number. On 2026-09-15 this output was read with `tail -5`, which showed
three `unstable` lines and the closing warning; from those three the reader
generalised "the small ones are all animated/async" over SIX hash differences —
a denominator taken from a JSON diff rather than from the tool, and a
classification invented to fit it. `control_Web.png` is printed as `MOVED`.

It moved because its picture is nearly blank, so few bits can change — the same
small hamming number a spinner produces for the opposite reason.

⇒ Membership is answered by `visual_stability.unstable_screenshots()`, which
returns the names. Ask it; do not infer it from a hamming column.

🔴 **AND THE SENTENCE THAT STOOD HERE READ `control_diff.json` BACKWARDS.** It
said `Web/html` being "indistinguishable from its control on ios" was an
"already-accepted fact — recorded in control_diff.json". That ledger records
the OPPOSITE: fixtures **asserted to render DIFFERENTLY** from their control,
where **a listed fixture that renders identically FAILS the build**. Being
listed is the strongest possible claim about a fixture, not an amnesty; the
record of an accepted indistinguishability is ABSENCE from this ledger (or a
row in `inert_audit.json`).

🔻 **The claim it was defending was also wrong, and for an instrument reason
this file should state once.** `Web/html__static` measures **active** on ios —
`control_diff.compare` puts it in `active`, not `inert`, on both a CI run and a
local one. The dHash said distance 2 because **dHash is the wrong instrument
for fixture-vs-control**, and `control_diff.py` says so in its own constant:
dhash-64 downsamples the screen to 9x8, so `cornerRadius` (0.008% of pixels)
and `fontColor` (0.05%) both hash IDENTICAL to their control. That check uses
`diff_pixels` with a threshold of ZERO differing pixels, because both
screenshots come off the same device in the same run.

⚠️ **`Web` IS ASYNC AND IS NOT IN THE UNSTABLE SET — measured, two runs.**
Opening the pictures rather than the hashes: the fixture declares
`html: "<p>Conformance Sample</p>"` and its control declares `"<p>Sample</p>"`.
In run 34878202456 (iOS 26.2) the FIXTURE rendered **blank** and the control
rendered "Sample"; in a local run (iOS 26.5, same corpus) the fixture rendered
"Conformance Sample" and the control rendered "Sample". Both runs report
`active` — but the CI one satisfies "differs from its control" because ONE SIDE
FAILED TO RENDER, not because the attribute was honoured. The same race hit the
control in the previous bake, whose `control_Web.png` hash was all zeroes.

⇒ `visual_stability` exempts `NetworkImage` for exactly this reason ("the frame
depends on load timing") and does NOT exempt `Web`, which loads its HTML the
same way. Two observations is not a calibration, so no entry is added here on
that basis — but the next `moved` on a Web screenshot should be read as this,
not as a regression, and the check that decides it is "open the picture", not
"look at the distance".

⇒ Two different questions, two different instruments, and they are not
interchangeable:

| question | instrument | tolerance |
|---|---|---|
| did this picture change since the last run? | dhash-64 | 8 |
| does this fixture differ from its control? | `diff_pixels` | 0 differing px |

A dHash distance says nothing about the second question in either direction.

**Procedure when `moved > 0`.** Attribute before baking. Re-run the SAME
corpus and device on the library the baseline was drawn from; entries that
move there too are environment drift, not a regression. On 2026-09-05 that
separated 84 into 82 drift (identical hamming on both libraries: 1x3, 2x6,
4x73, 7x2 — families margin / align / weight / min-max / center, and not one
Collection fixture) and 2 flaky. Then rebake wholesale from a run of that
same library, so `rendered_by` is true of every entry, and check the bake
against the run it came from (expect regressions 0 / no_baseline 0).

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

**2026-09-04, ci env, run 33807187183.** Baking the four new flow fixtures
into `ci/ios.hashes.json` re-hashed all 852 existing entries against that
run's artifacts. 846 reproduced exactly; six moved, every one below the
threshold, so the gate counted no regressions (`ios: 0 fail / 0 error`, both
before and after the four were added):

| distance | screenshot |
|---|---|
| 4 | `control_NetworkImage__no-defaultImage_url-efd3e3a7.png` |
| 3 | `Indicator_indicatorStyle__large.png` |
| 2 | `Indicator_color__static.png` |
| 2 | `Indicator_indicatorStyle__medium.png` |
| 2 | `control_Web.png` |
| 1 | `Indicator_color__binding.png` |

The max, 4, is inside the measured ceiling of 6 above — but **the set is not
the one recorded there**, and that is the part worth keeping. `Indicator`
went from three screenshots at distance 1 to four spanning 1–3;
`control_NetworkImage__no-defaultImage` and `control_Web` do not appear in
the calibration at all; and `SelectBox_selectedValue`, the distance-6 entry,
did not move this time. **Cause undetermined** — this is a single run's
observation, not a re-calibration, and no attempt was made here to explain
why these six and not others. None of the six was re-baked: they keep their
committed hashes, so anything that reads this file still compares against
the calibrated pictures. Recorded so that if any of them later crosses 8,
the reader knows it was already moving on 2026-09-04.

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

### ⚠️ `dhash_file` の既定は crop なし。門が渡す crop とは別物

```python
dhash_file(path, crop: tuple[int, int] = (0, 0))     # 既定は crop 無し
chrome_crop('ios', 'ci') == (160, 0)                 # 門が実際に渡す値
baseline.py:532-545   crop = chrome_crop(platform, env); hamming(dhash_file(png, crop), expected)
```

**既定のまま呼ぶと uncropped の hash が出て、committed hash（cropped）と比べた距離は
意味を持ちません。** 2026-09-15 にこれを踏み、`Web_html__static.png` を
`hamming=32 / MOVED` と読みました。正しくは:

```
                       uncropped   CROPPED   threshold
Web_html__static.png        32          5         8      ⇒ MOVED していない
control_Web.png             32          0         8      ⇒ 焼き直し不要
```

🔻 **そして 2 つのレーンが独立に 32 を出し、一致を「予測が当たった」と読みました。**
出所が違っても**既定引数が同じなら独立ではありません**。値が一致したときこそ、
相手と同じ既定を踏んでいないかを撃ってください。

⇒ **距離を自分で計算せず、`compare_platform` を使う。**それが門の呼び方です。
自分で呼ぶなら `chrome_crop(platform, env)` を渡す。

📌 関連して、**dHash は白っぽい絵の白紙化を見られません**。`hamming(h, 0) == popcount(h)`
なので、committed hash の popcount が threshold 以下の fixture は、絵が完全な白紙に
戻っても閾値の内側に収まります（ci/ios で 867 中 115、うち 21 は popcount 0）。
「絵が空でない」を dHash で撃たないこと — `diff_pixels` を使う。
起票: `docs/bugs/2026-09-15-the-visual-gate-cannot-see-a-mostly-white-fixture-go-blank.md`
