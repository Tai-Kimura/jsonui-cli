# JsonUI conformance — Web host

Minimal Vite + React host that executes the generated conformance fixtures
(`conformance/fixtures/`) through the **real production path**: rjui_tools
static codegen → React runtime → Playwright driver semantics.

## Prerequisites

- Node 20+ (Node ≥ 23 required — `scripts/run.ts` relies on native
  TypeScript type stripping)
- Ruby 3.x (for rjui_tools codegen)
- Fixtures generated: `jui conformance generate` (repo root)

## Run

```sh
npm ci
npx playwright install chromium   # first time only
./generate.sh                     # codegen all fixtures into this host
npm run conformance               # build + serve + execute + write results
```

`npm run conformance` writes `conformance/results/web.results.json`
(RESULTS_SCHEMA.md-conformant) and screenshots under
`conformance/artifacts/web/` (gitignored — the committed regression signal
is `conformance/baselines/local/web.hashes.json`). Then render the matrix with
`jui conformance report`; after reviewing intentional visual changes,
record them with `jui conformance baseline update --platform web`
(see `conformance/baselines/README.md`).

### Options

Every path is overridable — flag, env var, or default:

| Flag | Env | Default |
|---|---|---|
| `--conformance-dir` | `JSONUI_CONFORMANCE_DIR` | `../../..` of the script (repo `conformance/`) |
| `--rjui` (generate) | `RJUI_TOOLS_PATH` | `<conformance>/../rjui_tools` |
| `--ruby` (generate) | `RUBY_BIN` | `ruby` |
| `--results` (run) | `JSONUI_RESULTS_FILE` | `<conformance>/results/web.results.json` |
| `--artifacts` (run) | `JSONUI_ARTIFACTS_DIR` | `<conformance>/artifacts/web` |
| `--port` / `--workers` (run) | — | `4177` / `6` |
| `--skip-build` (run) | — | reuse existing `dist/` |
| `--only <prefix>` (run) | — | run a subset (debugging) |

## How it works

- `scripts/generate.mjs` copies each web-applicable fixture layout to
  `src/Layouts/pages/fx_NNNN.json`, runs `rjui build` (the actual codegen
  used by product apps), and emits:
  - `src/generated/fixtureRegistry.tsx` — fixture id → lazy React route
  - `src/generated/fixture-map.json` — runner metadata (codegen success)
  - `src/generated/conformance-colors.css` — utilities for named colors
    extracted by rjui into `Layouts/Resources/colors.json`
- Routing: single-page host; `/fixture/<Section>/<attr>__<case>` renders
  that fixture's generated component (see `src/main.tsx`). `/` lists all
  fixtures.
- `scripts/run.ts` is manifest-driven: `vite build` + `vite preview`,
  then for every fixture in `manifest.json` it executes the fixture's
  screen-test JSON with the **vendored jsonui-test-runner Playwright
  executors** (`scripts/vendor/`, see `VENDOR.md` for provenance and the
  two import-syntax patches). Fully headless.
- Status mapping (RESULTS_SCHEMA.md): platform not applicable / non-react
  `mode` → `skipped` (with reason); assertion rejection → `fail`;
  missing element / timeout / render crash / codegen failure → `error`;
  `visual` fixtures end in a screenshot step captured to the artifacts
  dir and recorded as `artifacts/web/<name>.png`.
- `class: interactive` fixtures (v2) are routed through the generic
  `StateHost` provider (`src/conformanceState.tsx`): the manifest `state`
  declares vars + handlers, the provider seeds React state from the rjui
  `create<Fx>Data()` defaults, injects the declared literal-set handlers and
  the default two-way write-back setters. No per-fixture host code —
  contract: `conformance/INTERACTIVE_HOST_CONTRACT.md`.

## What is committed vs generated

Committed: scripts, config, `src/main.tsx`, `src/conformanceState.tsx`,
`src/index.css`, `src/Strings/en.json`, `public/` sample assets (fixtures
reference an image asset named `conformance_sample`), lockfile.
Generated (gitignored): `src/Layouts/`, `src/generated/`,
`src/components/`, `src/lib/`, `src/hooks/`, `dist/`, `rjui-build.log`.
