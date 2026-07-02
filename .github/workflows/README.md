# CI workflows

Two workflows keep the renderer-SSoT verification assets (unit suites +
conformance, see `conformance/`) green. Everything here runs on GitHub-hosted
runners; local run procedures (each tool's specs, `conformance/hosts/*/README.md`)
are unchanged and remain the reference — CI only automates them.

## `ci.yml` — per push to `main` + every PR

| Job | What | Gate |
|---|---|---|
| `python-suite` | jui_tools unit tests (`python -m unittest discover -s tests`) + protocol-sync idempotency e2e | exit code |
| `rspec (sjui_tools / kjui_tools / rjui_tools)` | Ruby codegen unit suites (Ruby 3.3; kjui/rjui via their Gemfiles, sjui plain rspec) | exit code |
| `ssot-guards` | 1. `jui conformance generate` → zero git diff (fixtures never drift from `shared/core/attribute_definitions.json`) 2. `jui generate attr-bindings --lang all` twice → identical output 3. fresh ruby emit == vendored `rjui_tools/lib/core/generated/attributes/` (README.md excluded) | zero diff |
| `web-conformance` | full fixture suite through rjui codegen → React → headless Chromium (`conformance/hosts/web/`) | 0 fail / 0 error in `web.results.json` |

Artifacts: `web-conformance` (REPORT.md + web results + screenshots).

### protocol-sync consolidation

The former `protocol-sync.yml` (jui_tools unit tests + sync idempotency) is
**folded into `ci.yml`** as the `python-suite` job — same commands, same
unittest discovery, one workflow per push instead of two. The job split
(tests, then idempotency) is preserved as ordered steps.

## `conformance-mobile.yml` — nightly (18:00 UTC) + `workflow_dispatch`

Full 3-platform conformance matrix. iOS/Android are too slow for per-push
(iOS ~30 min incl. Xcode build; Android needs an emulator boot).

| Job | Runner | What |
|---|---|---|
| `web` | ubuntu | same suite as ci.yml (rerun so all platforms test the same commit) |
| `ios` | macos-15, Xcode 16.4 pinned | checks out public `Tai-Kimura/SwiftJsonUI` (`ConformanceHost/`) + `Tai-Kimura/jsonui-test-runner`, then `sync_fixtures.sh` → `generate_project.rb` → `run_conformance.sh` on a headless "iPhone 16 Pro" simulator |
| `android` | ubuntu (KVM) | checks out public `Tai-Kimura/KotlinJsonUI` (`conformance-host/`), boots an API 34 `pixel_tablet` emulator via `reactivecircus/android-emulator-runner`, runs `run_conformance.sh --fresh` + `collect_results.sh` |
| `report` | ubuntu | merges the three fresh `*.results.json` via `jui conformance report`; **gate: 0 cross-platform mismatches / 0 fail / 0 error / no stale results** |

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
```

Or: Actions tab → `conformance-mobile` → "Run workflow".

Flaky-run policy: no `continue-on-error` anywhere — rerun the failed job
manually (`gh run rerun <id> --failed`) if a runner/emulator hiccups.
