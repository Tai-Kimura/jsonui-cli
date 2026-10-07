# CI workflows

Two workflows keep the renderer-SSoT verification assets (unit suites +
conformance, see `conformance/`) green. Everything here runs on GitHub-hosted
runners; local run procedures (each tool's specs, `conformance/hosts/*/README.md`)
are unchanged and remain the reference — CI only automates them. The
conformance pass/fail judgment itself is a CLI subcommand, not workflow code:
both workflows call `jui conformance gate` (logic:
`jui_tools/jui_cli/conformance/gate.py`, tests: `tests/test_conformance_gate.py`),
so the exact CI judgment is runnable and testable locally.

## `ci.yml` — per push to `main` + every PR

| Job | What | Gate |
|---|---|---|
| `python-suite` | jui_tools unit tests (`python -m pytest`) + protocol-sync idempotency e2e | exit code |
| `rspec (sjui_tools / kjui_tools / rjui_tools)` | Ruby codegen unit suites (Ruby 3.2, the floor from jsonui-cli 1.9.0; kjui/rjui via their Gemfiles, sjui plain rspec) | exit code |
| `ssot-guards` | 1. `jui conformance generate` → zero git diff (fixtures never drift from `shared/core/attribute_definitions.json`) 2. `jui generate attr-bindings --lang all` twice → identical output 3. fresh ruby emit == vendored `rjui_tools/lib/core/generated/attributes/` (README.md excluded) | zero diff |
| `web-conformance` | full fixture suite through rjui codegen → React → headless Chromium (`conformance/hosts/web/`) | `jui conformance gate --platform web --no-visual`: 0 fail / 0 error in `web.results.json` (screenshot checks are the mobile lane's job — the committed baselines are macOS renders, this runner is not) |

Artifacts: `web-conformance` (REPORT.md + web results + screenshots).

### protocol-sync consolidation

The former `protocol-sync.yml` (jui_tools unit tests + sync idempotency) is
**folded into `ci.yml`** as the `python-suite` job — same commands, same
unittest discovery, one workflow per push instead of two. The job split
(tests, then idempotency) is preserved as ordered steps.

## `conformance-mobile.yml` — weekly (Sunday 18:00 UTC) + `workflow_dispatch`

Full 3-platform conformance matrix. iOS/Android are too slow for per-push
(iOS ~30 min incl. Xcode build; Android needs an emulator boot).

Operationally, mobile verification is mostly manual today: the committed
iOS/Android results and screenshot baselines on `main` come from local runs
(pinned-Xcode simulator / API 34 tablet emulator) pushed together with the
change that re-rendered them. The weekly cron and `workflow_dispatch`
re-validate that committed state; between runs, "3 platforms green on main"
reflects the last such run, not a per-push mobile execution.

| Job | Runner | What |
|---|---|---|
| `web` | ubuntu | same suite as ci.yml (rerun so all platforms test the same commit) |
| `ios` | macos-15, Xcode 16.4 pinned | checks out public `Tai-Kimura/SwiftJsonUI` (`ConformanceHost/`) + `Tai-Kimura/jsonui-test-runner`, then `sync_fixtures.sh` → `generate_project.rb` → `run_conformance.sh` on a headless "iPhone 16 Pro" simulator |
| `android` | ubuntu (KVM) | checks out public `Tai-Kimura/KotlinJsonUI` (`conformance-host/`), boots an API 34 `pixel_tablet` emulator via `reactivecircus/android-emulator-runner`, runs `run_conformance.sh --fresh` + `collect_results.sh` |
| `android-library-tests` | ubuntu (KVM) | checks out `Tai-Kimura/KotlinJsonUI` at `kotlinjsonui_ref`, runs `library`, `library-dynamic` and `conformance-host`'s `connectedDebugAndroidTest` (the host's `ConformanceSuiteTest` left out: the `android` jobs run it; its probe classes run here) on an API 35 `pixel_tablet` emulator (not 34: there the IME never shows and the active-window accessibility walk can come back empty — measured in run 36197930038), and judges from the results XML (`.github/scripts/kjui_device_tests.py`): a failure, an error, a module with no results, a class with `@Test` and no case in the results, or a module of the checkout with device tests that the job neither runs nor names (`UNREACHED_MODULES`, with its reason) is red; skips are printed by name |
| `report` | ubuntu | `jui conformance gate --platform ios --platform android --platform web` — renders REPORT.md from the three fresh `*.results.json`, then gates: **0 cross-platform mismatches / 0 fail / 0 error / not stale / screenshots actually compared / no visual or attribute-effect regressions / `missing_artifact` + `no_baseline` within their `conformance/gate_ratchet.json` ceilings** |

Artifacts: `results-{web,ios,android}` (per-platform results + screenshots)
and `conformance-report` (REPORT.md + everything merged).

Pinning decisions:

- **Xcode 16.4 on macos-15** — matches the committed baseline run
  (iOS 18.x simulator runtime, "iPhone 16 Pro" device available). Bump
  deliberately, together with a fresh baseline, not implicitly via runner
  image updates.
- **Android API 34 / `pixel_tablet` / x86_64 google_apis** — tablet profile
  matches the baseline device class (small phone screens can push fixture
  content offscreen and turn visual fixtures into element-not-found errors).

### Manual run

```sh
gh workflow run conformance-mobile.yml           # against main
gh run watch                                     # follow it

# Before a SwiftJsonUI / KotlinJsonUI tag: every mobile job against the
# release branches, with the opt-in probes raised.
gh workflow run conformance-mobile.yml -f swiftjsonui_ref=<sjui-release-branch> -f image_probes=true \
    -f kotlinjsonui_ref=<kjui-release-branch> -f android_probes=true
```

`image_probes` and `android_probes` default to `true` (from jsonui-cli 1.9.8):
a dispatch that forgets them still raises the probes; lower one with
`-f android_probes=false`. The schedule has no inputs and runs without them.

`swiftjsonui_ref` (default `master`) is the SwiftJsonUI ref both iOS jobs
check out, and `kotlinjsonui_ref` (default `main`) the KotlinJsonUI ref the
three Android jobs check out; each job prints the ref and the commit it got.
`android_probes` raises every instrumentation argument a KotlinJsonUI device
test compares to `"1"` — the list is derived from the tests, so a new probe
needs no workflow edit. The schedule has
no inputs and keeps `master`. ConformanceHost's TapIdentifierOnceUITests is
not opt-in: it runs in both iOS jobs whatever the inputs.

One leg alone, for repeating KotlinJsonUI's device tests without the other
six jobs: `-f android_library_only=true -f kotlinjsonui_ref=<ref>` runs only
`android-library-tests` (the report too is off). In that job Gradle runs
under `kjui_device_tests.py watch`: the device's state is saved at the first
failed case (`device-evidence/first-failure`), and a module whose progress
count has not moved for 600 s (`KJUI_IDLE_SECONDS`; 120 s was the longest
wait on five green runs) is stopped with its state saved
(`device-evidence/stopped`) instead of hanging to the step's budget.
Before the tests the job sets `hide_error_dialogs` to 1 (an ANR or crash
closes the app instead of showing a dialog), and every 15 s
(`KJUI_FOCUS_SECONDS`) the watch reads the window focus: a system "isn't
responding" dialog there is saved (`device-evidence/anr-N`), its app
force-stopped unless it is under test, and recorded with its time in
`device-evidence/anr-dialogs.txt`. Run 37618369032: Pixel Launcher's ANR
dialog held the focus for 14 minutes and the IME never showed.
Before the tests the job also asks whether the IME can show at all
(`kjui_device_tests.py ime`): it opens a surface whose field asks for the
IME (Settings search, else the global search) and waits for
`mInputShown=true`, retrying for `KJUI_IME_BUDGET_SECONDS` (120; green runs
saw their first show at most 35 s after their first request). Never shown:
the state is saved (`device-evidence/ime-never-shown`) and the leg fails as
"the IME never showed before the tests" without running them — red for the
environment, not as library's keyboard cases. No surface on the image: a
WARNING that the IME was not checked, and the tests run.

Or: Actions tab → `conformance-mobile` → "Run workflow".

Flaky-run policy: the one `continue-on-error` is the Android emulator's
first attempt, whose failure triggers the in-workflow fresh-emulator retry
(the retry step is not `continue-on-error`, so a second failure fails the
job — a frozen emulator is only recoverable by a fresh one). Everywhere
else: rerun the failed job manually (`gh run rerun <id> --failed`) if a
runner/emulator hiccups.
