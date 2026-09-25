# JsonUI Test CLI

CLI tool for validating, generating test files, descriptions, and documentation from JsonUI test files.

## Requirements

- Python 3.10 or higher

## Installation

### Quick Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash
```

### Install Specific Version

```bash
# Install from a specific tag
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- -v v1.0.0

# Install from a specific branch
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- -v feature-branch
```

### Install with Development Dependencies

```bash
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- --dev
```

### Manual Install

```bash
cd test_tools
pip install -e .
```

### Python Version Setup (if needed)

If you don't have Python 3.10+, use mise (recommended):

```bash
# Install mise (if not installed)
curl https://mise.run | sh

# Install and use Python 3.11
mise install python@3.11
mise use python@3.11

# Verify
python --version
```

Or use pyenv:

```bash
pyenv install 3.11.0
pyenv local 3.11.0
```

## Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `validate` | `v` | Validate test files |
| `generate test screen` | `g t screen` | Generate screen test file template |
| `generate test flow` | `g t flow` | Generate flow test file template |
| `generate description screen` | `g d screen` | Generate description JSON for screen test case |
| `generate description flow` | `g d flow` | Generate description JSON for flow test case |
| `generate doc` | `g doc` | Generate HTML/MD documentation for single file |
| `generate html` | `g html` | Generate HTML directory with index for all test files |
| `artifacts pull` | `a pull` | Pull test artifacts (screenshots/recordings) from devices and xcresults |
| `artifacts status` | `a status` | Show resolved artifacts config and existing artifact files |
| `artifacts prune-legacy` | `a prune-legacy` | List (default) or delete (`--yes`) the suites left in the flat legacy Android mirror |
| `contracts coverage` | — | Every response status the OpenAPI declares for an operation a screen reaches, bucketed by who answers it — `validate` reports it, and fails on it from the release its section names |
| `contracts baseline` | — | Record today's coverage entries once in `contracts_coverage_baseline.json`, then only shrink the file as they close — the gate passes on what it holds |

### validate (v)

Validate `.test.json` files for cross-platform compatibility.

```bash
# Validate single file
jsonui-test validate path/to/test.test.json
jsonui-test v path/to/test.test.json

# Validate directory (recursive)
jsonui-test v tests/

# Verbose output (show all details)
jsonui-test v -v tests/

# Quiet mode (show only errors, hide warnings)
jsonui-test v -q tests/
```

**Exit codes:**
- `0`: All files valid
- `1`: Validation errors found

**Install side effect, and when it cleans.** A successful `validate` flatten-installs
the validated tests into every destination in `test.install`. That install removes
installed tests whose source is gone — but only on a FULL SYNC, because a run given
a narrower set cannot tell a deleted test from one it was simply not passed.

A run is a full sync when it covered every `*.test.json` under the project's test
directory (`test.testDir`, default `tests`). Otherwise the run installs what it was
given, removes nothing, and says so:

```
Installed 1 test file(s) → 1 target(s) (cleaned 0 stale):
  partial run — stale files left in place: this run covered 1 of 3 declared test(s),
  so a missing one may simply not have been passed to this command
```

Declare `test.testDir` when your tests do not live under `tests/`; without it the
run cannot establish the full set and declines the clean.

**Element ids the steps name.** Every id a step names — `id`, `ids`, `container`,
`cropId`, and `visible` / `notVisible` under `when` and `while`, nested `steps`
included — is looked up in the layouts of the project whose config the run read:
every layout, each resolved on every platform with its includes expanded (a test
moves between screens without saying which one each step is on, and the runner finds
an id wherever it is), through the classifier the spec validator uses.

| the id | reported as |
|---|---|
| on a layout, or declared in `test.appOwnedIds` | nothing |
| on no layout and not declared | INFO below the release `LAYOUT_ID_GATE_FROM` names (the spec validator's), WARNING from it — never an error; while a release is announced, one line names it. The message names the layout ids a person may have meant |
| web's spelling of an id inside an include with an id, before `INCLUDE_ID_PREFIX_GATE_FROM` | `cannot check: … inside includes …`, naming what web spells it as from that release (`'hint' -> 'sideHint'`); from that release it is checked like any other id |
| UIKit's spelling of it (`<include id>_<id>`) | `cannot check` |
| derived by the generated code from a layout id: a Collection's cells `<id>_item_<n>`, a Segment's or TabView's tabs `<id>_tab_<n>` | `cannot check` (the layout id must be on a layout) |
| a part of a component the project defines (`<id>_…` under a node whose type is not a built-in one) | `cannot check` — its own converter names them |
| web's CSS descendant form `A #B` | `cannot check` when each part is on a layout; otherwise the part is reported |
| a character outside `[A-Za-z0-9_]` (the OS's own UI, an id built from data) | `cannot check` |
| built from a case argument (`@{…}`) | `cannot check` |

One line counts them — `element ids: N named in the steps — N on a layout, N declared
in test.appOwnedIds, N on no layout, N cannot check, N not checked` — and INFO never
moves `Warnings:` or the exit code (`Info: N (not counted)` on the summary line).

Ids the app draws outside every layout — a native navigation bar's menu item, an app
toast — are declared in `jui.config.json`; an entry ending in `*` is a prefix. A
declaration is not looked up in the layouts, and one no step of the run names is
listed, so a stale one can be removed:

```json
{ "test": { "appOwnedIds": ["sampleToast", "sample_menu_button", "sample_day_*"] } }
```

**Contracts coverage section.** After its summary, `validate` reports
`jsonui-test contracts coverage` for the project whose config it read — one line
per platform:

```
coverage: web units 2 · statuses required 12 · row 5 · excluded 1 · uncovered 6 · not evaluated 0 → exit 1 (uncovered) · baselined 0 (matched 0 · new 6 · stale 0) — no baseline file: every entry is new
from jsonui-cli <next release>, validate fails on contracts coverage entries not in the baseline — close them (Task 6 of the define agent), or record the current ones once with `jsonui-test contracts baseline --initial` (the user's decision); see the release note
```

with any declaration errors, and what could not be measured by cause
(`n/a(unbound endpoint) 1`, …). Each line ends with how the entries compare with the
[baseline](#contracts-baseline). Its last line says where the gate stands: below the
release it names, the section **does not change the exit code**; from that release on,
validate fails — after installing the valid tests — on entries not in the baseline
(new), on baselined entries that are closed (stale), and on what can never be
baselined (declaration errors, rows or screens that could not be evaluated, HTTP with
nothing evaluated, cannot start). The summary line then says which:
`Coverage: FAILED (exit 1; web: 1 not in the baseline)`, or `Coverage: passed (exit 1)`
when everything coverage reports is baselined. It is never silent:
`coverage not run: N error(s) above …` when the run's own errors stop it,
`coverage not applicable: …` when the project declares no `mock.swagger` and no
spec has `branchContracts`, `coverage cannot start: …` when it has one of them and
coverage still cannot start, and `coverage skipped (--no-coverage-check)` when
asked.

### generate test screen (g t screen)

Generate screen test file template from a layout JSON file.

```bash
# Generate screen test template (output to tests/screens/login/login.test.json)
jsonui-test generate test screen login
jsonui-test g t screen login

# Specify output path
jsonui-test g t screen login --path tests/auth/login.test.json

# Specify platform
jsonui-test g t screen login -p ios-swiftui
```

**Options:**
- `--path`: Output file path (default: `tests/screens/<name>/<name>.test.json`)
- `-p, --platform`: Target platform (`ios`, `ios-swiftui`, `ios-uikit`, `android`, `web`, `all`)

### generate test flow (g t flow)

Generate flow test file template.

```bash
# Generate flow test template (output to tests/flows/checkout/checkout.test.json)
jsonui-test generate test flow checkout
jsonui-test g t flow checkout

# Specify output path
jsonui-test g t flow checkout --path tests/e2e/checkout.test.json

# Specify platform
jsonui-test g t flow checkout -p ios-swiftui
```

**Options:**
- `--path`: Output file path (default: `tests/flows/<name>/<name>.test.json`)
- `-p, --platform`: Target platform (`ios`, `ios-swiftui`, `ios-uikit`, `android`, `web`, `all`)

### generate description (g d)

Generate description JSON file for a specific test case.

```bash
# Generate description file for screen test case
jsonui-test generate description screen login error_case_1
jsonui-test g d screen login error_case_1
jsonui-test g desc screen login initial_display

# Generate description file for flow test case
jsonui-test g d flow checkout happy_path

# Specify output path
jsonui-test g d screen login error_case_1 --path tests/custom/description.json
```

**Options:**
- `--path`: Output file path (default: `tests/screens/<name>/descriptions/<case_name>.json` or `tests/flows/<name>/descriptions/<case_name>.json`)

**Output Structure:**
```
tests/
├── screens/
│   └── login/
│       ├── login.test.json
│       └── descriptions/
│           ├── initial_display.json
│           ├── error_case_1.json
│           └── login_success.json
└── flows/
    └── checkout/
        ├── checkout.test.json
        └── descriptions/
            └── happy_path.json
```

**Description JSON Format:**
```json
{
  "case_name": "error_case_1",
  "summary": "Verify login error handling",
  "preconditions": [],
  "test_procedure": [
    "1. Enter 'invalid' into 'email_input'",
    "2. Tap on 'login_button'"
  ],
  "expected_results": [
    "'error_label' is visible",
    "'error_label' shows 'Invalid email'"
  ],
  "notes": "",
  "created_at": "2025-01-16T12:00:00",
  "updated_at": "2025-01-16T12:00:00"
}
```

After generating, link descriptions to test cases using `descriptionFile`:

```json
{
  "cases": [
    {
      "name": "error_case_1",
      "descriptionFile": "descriptions/error_case_1.json",
      "steps": [...]
    }
  ]
}
```

### generate doc (g doc)

Generate human-readable documentation from test files.

```bash
# Generate markdown documentation
jsonui-test generate doc -f test.test.json -o docs/test.md
jsonui-test g doc -f test.test.json -o docs/test.md

# Generate HTML documentation
jsonui-test g doc -f test.test.json -o docs/test.html --format html

# Output to stdout
jsonui-test g doc -f test.test.json

# Generate schema reference document
jsonui-test g doc --schema -o docs/schema.md
```

**Options:**
- `-f, --file`: Test file to generate documentation for
- `-o, --output`: Output file path
- `--format`: Output format (`markdown`, `html`)
- `--schema`: Generate schema reference instead

### generate html (g html)

Generate HTML documentation directory with index page for all test files.

```bash
# Generate HTML for all tests in directory
jsonui-test generate html tests/
jsonui-test g html tests/

# Specify output directory
jsonui-test g html tests/ -o docs/html

# Specify custom title
jsonui-test g html tests/ -o docs/html -t "My App Tests"
```

**Options:**
- `input`: Input directory containing .test.json files (required)
- `-o, --output`: Output directory (default: `html`)
- `-t, --title`: Title for index page (default: `JsonUI Test Documentation`)

**Output Structure:**
```
html/
├── index.html          # Index with links to all tests
├── screens/
│   ├── login.html
│   └── home.html
└── flows/
    └── checkout.html
```

The index page includes:
- Summary statistics (total files, screen tests, flow tests, cases, steps)
- Links to all test documentation organized by type
- Test metadata (platform, case count, description)

### artifacts pull (a pull)

Pull test artifacts (screenshots, recordings) into the local artifacts directory.

- **iOS**: exports attachments from the newest `.xcresult` bundle (explicit path, glob, or automatic DerivedData discovery) via `xcrun xcresulttool export attachments`, organized per test into `screenshots/`, `recordings/`, and `other/` subdirectories.
- **Android**: pulls `/sdcard/Android/data/<appId>/files/jsonui-artifacts` and the uninstall-surviving mirror `/data/local/tmp/jsonui-artifacts/<appId>` (android driver ≥ 1.8.9) from the device via `adb pull`; `--clean` removes only those two. A device still running an older driver mirrors into the flat `/data/local/tmp/jsonui-artifacts`, which has no app dimension: it is read suite-by-suite (entries that look like a package name are other apps' scoped mirrors and are left alone) and is never cleaned, because on a shared device one app's `--clean` there deletes the other app's runs. adb is resolved from `test.artifacts.android.adb` (explicit path) > PATH > `$ANDROID_HOME` / `$ANDROID_SDK_ROOT` > the OS-default SDK location (`~/Library/Android/sdk` on macOS, `~/Android/Sdk` on Linux) — so it also works from environments without a login-shell PATH (e.g. an MCP daemon).

- **Web**: collects Playwright's per-test output dirs (`test-results/<spec>-<title>-<project>/` — video.webm, traces, error context) plus the web driver's `screenshotDir` PNGs. Recording and browser selection are Playwright-native — enable them in the consuming harness:

  ```ts
  // playwright.config.ts
  export default defineConfig({
    use: { video: 'on' },                       // or 'retain-on-failure'
    projects: [
      { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
      { name: 'firefox',  use: { ...devices['Desktop Firefox'] } },
      { name: 'webkit',   use: { ...devices['Desktop Safari'] } },
    ],
  });
  ```

  ```ts
  // in the test: point the driver's screenshotDir at the per-test bucket so
  // failure/action PNGs land next to the video and pull collects them together
  test('login', async ({ page }, testInfo) => {
    const runner = new JsonUITestRunner(page, { screenshotDir: testInfo.outputDir });
    ...
  });
  ```


Each pull lands in `<dir>/<platform>/<stamp>/` (iOS stamps use the xcresult mtime so re-pulls of the same run are stable) and a `<dir>/<platform>/latest` symlink points at the newest pull.

```bash
# Pull from all platforms (best effort — missing device/xcresult is skipped)
jsonui-test artifacts pull
jsonui-test a pull

# Pull only iOS from an explicit xcresult
jsonui-test a pull --platform ios --xcresult path/to/Run.xcresult

# Pull only Android from a specific device, removing device files afterwards
jsonui-test a pull --platform android --serial emulator-5554 --clean

# Machine-readable output
jsonui-test a pull --json
```

**Options:**
- `--platform`: `ios`, `android`, or `all` (default: `all`)
- `--xcresult`: Explicit `.xcresult` path or glob (overrides `test.artifacts.ios.xcresult`)
- `--serial`: adb device serial (overrides `test.artifacts.android.serial`)
- `--out`: Output directory (overrides `test.artifacts.dir`)
- `--config`: Config file (default: `jui.config.json`)
- `--clean`: Remove pulled artifact dirs from the Android device after pulling
- `--json`: Print a single JSON object: `{"outputDir": ..., "files": [...], "skipped": [...]}`

**Exit codes:**
- `0`: Pull succeeded (with `--platform all`, per-platform skips are benign)
- `1`: An explicitly requested single platform produced no files, or config error (e.g. missing `appId`)

### artifacts prune-legacy (a prune-legacy)

The one deliberate exit from the flat legacy mirror `/data/local/tmp/jsonui-artifacts`. `pull --clean` never removes it (it has no app dimension, so on a shared device the entries can belong to any app that ran with an android driver < 1.8.9), and a device still running an older driver keeps refilling it. Once every app on the device writes the scoped mirror (driver ≥ 1.8.9), a person runs this to close the migration:

```bash
jsonui-test artifacts prune-legacy                 # dry run: lists the suite dirs it would delete
jsonui-test artifacts prune-legacy --serial emulator-5554 --yes   # deletes them
```

Only suite-shaped entries are deleted. Package-shaped entries (other apps' scoped mirrors) and the root itself are never touched. The command cannot tell whether an older driver is still in use on the device — that is what the dry run and `--yes` are for.

With more than one device or emulator attached, `--serial` (or `test.artifacts.android.serial`) is required: adb refuses to pick one, the listing is never reached, and the command reports `skipped (adb: more than one device/emulator)` with exit 1. On a shared device, compare the dry-run listing between the lanes that use it before anyone passes `--yes` — a suite name alone (`Login_Smoke_Test`) does not say which app wrote it.

### artifacts status (a status)

Show the resolved artifacts configuration (artifacts dir, discovered xcresult, Android appId/serial and the resolved adb path) and every file currently under the artifacts directory.

```bash
jsonui-test artifacts status
jsonui-test a status --json
```

**Options:**
- `--config`: Config file (default: `jui.config.json`)
- `--json`: Print status as a single JSON object

### Artifacts Configuration

Configured under the `test.artifacts` block of `jui.config.json`:

```json
{
  "test": {
    "artifacts": {
      "dir": "tests/artifacts",
      "ios": { "xcresult": null },
      "android": { "appId": "com.example.app", "serial": null, "adb": null },
      "web": { "testResults": "test-results", "screenshotDir": "screenshots" }
    }
  }
}
```

- `dir`: Output root, relative to the config file's directory (default: `tests/artifacts`)
- `ios.xcresult`: Explicit `.xcresult` path or glob. When omitted, the newest `~/Library/Developer/Xcode/DerivedData/*/Logs/Test/*.xcresult` is used
- `android.appId`: Application ID (required for Android pulls)
- `android.serial`: adb device serial (optional; `--serial` overrides)

**Output structure:**
```
tests/artifacts/
├── ios/
│   ├── latest -> 20260101-120000
│   └── 20260101-120000/
│       └── LoginTests/testLogin()/
│           ├── screenshots/launch_screen.png
│           └── recordings/run_recording.mp4
└── android/
    ├── latest -> 20260101-120500
    └── 20260101-120500/
        └── shot.png
```

### mock serve --artifacts

The mock server (`jsonui-test mock serve`) accepts an `--artifacts` flag: after an `ios` or `android` run target (from `mock.runTargets`) finishes, the corresponding `artifacts pull` runs automatically. Other targets (e.g. `web`) are skipped, and pull errors never crash the server.

```bash
jsonui-test mock serve --artifacts
```

### API path scope

When one swagger is shared by several front-ends, `mock generate` only
scaffolds and checks the endpoints this project declares it consumes. It reads
the same keys the DTO codegen already filters on, so the scope is stated once:

```jsonc
{
  "api": { "schemas": {
    "include_paths": ["/api/user/*"],
    "exclude_paths": []
  }}
}
```

Endpoints outside the scope are not scaffolded and are not counted as
`[MISSING]` — another realm's endpoints are not this project's missing mocks.
A mock file that serves an out-of-scope route is reported as `[SCOPE]` (an
unused file you can delete) rather than `[ORPHAN]`, and does not fail the
check; `[ORPHAN]` keeps its meaning of "no such endpoint in the swagger at
all". Glob semantics match the codegen filter: `*` matches any characters
including `/`, patterns are case-sensitive and match the whole path.

Set `mock.includePaths` / `mock.excludePaths` to give the mocks a different
scope from the DTOs (`"includePaths": ["*"]` opts out of narrowing entirely).
With no declaration anywhere, the whole swagger is in scope, as before.

### Which mock is answering

`jsonui-test mock identity` asks the running server whose corpus it serves and
exits non-zero if it is not this project's:

```bash
jsonui-test mock identity --port 8795   # 0 = mine, 1 = another project's, 2 = nothing listening,
                                        # 3 = something answered but has no identity
```

A health check that only sees HTTP 200 cannot do this. Measured 2026-09-04: a
lane's server failed to bind because another project already held the port,
the health check passed on the control panel's 200, and five tests ran against
the other project's mocks — the failures read as regressions of the change
under test, and nothing in the results said otherwise.

Run it **after starting the server and again after the run**. The port can
change hands in between, and the second call is the only thing that says so.
Exit 3 means a server is up but predates this endpoint (it answers 401 from
the admin router) — you cannot learn whose corpus it serves, so upgrade or
stop it. `--any-project` prints the identity without failing; the endpoint itself
(`GET /__jsonui__/identity`) needs no admin token, because a caller asking
"are you mine?" does not hold the token of the server that answers when the
answer is no.

The payload also carries `swagger` (the sources this corpus was generated
from, as absolute paths) and `endpointCount`:

```json
{"pid": 40321, "projectRoot": "/…/client", "mockDir": "/…/client/tests/mocks",
 "swagger": ["/…/client/api/openapi.yaml"], "endpointCount": 37,
 "port": 8795, "startedAt": "2026-09-04T03:59:31+00:00"}
```

`swagger` is absolute because `api/openapi.yaml` is the same string in every
project and could not tell two servers apart. `endpointCount` separates "the
wrong corpus" from "an empty one": a server with 0 endpoints answers 404 to
everything, which reads downstream as a broken app rather than a mock pointed
at nothing.

### What the `--check` gates do not compare

Each `--check` compares two things, and the chain stops short of the
implementation:

| Gate | Compares |
|---|---|
| `jsonui-test validate` | mock **↔ the shape the schema declares** |
| `mock generate --check` | mock **↔ swagger** |
| `generate branch-tests --check` | the copy baked into the test **↔ the mock file** |

None of them read implementation source, and a swagger does not declare the
**text** of a body. So a green run does not mean a mock's message strings
match what the endpoint actually returns — a mock can hold wording no code
produces and pass all three.

This is not an oversight to be fixed by a fourth gate. A project that tried
one measured 88 false positives (messages raised through helpers, composed
with f-strings, or built outside the handler), and a gate that is always red
costs more than the checking is worth — it takes the credibility of the gates
next to it. Treat body text as a discipline rather than a gate: check pinned
strings against the implementation when you pin them, and re-check when the
implementation changes.

The gap is worst when the assertion does not depend on the text either — a
branch asserted by string key passes identically before and after the wording
is corrected, so no test count moves and no diff appears. Errors in an
ungated stretch do not arrive at a commit; they sit there from the start,
which is why `git diff` and range comparisons do not find them.

### contracts coverage

```
jsonui-test contracts coverage [screen] [--platform web|android|ios ...] [--json]
```

For every screen and platform, every response status the OpenAPI documents in
`mock.swagger` declare for an operation the screen's dataFlow names lands in
exactly one bucket, per (screen, view-model method, operation, platform):

- **row** — a branch serves the status in its `when` (explicitly; the route's
  default scenario is not an answer) and its `then` says more than "the op was
  called". An `alsoStatuses` copy answers too and is counted apart.
- **unit / unreachable / unexpressible** — `excludedOutcomes` with a reason.
- **not-evaluated** — the method's row for the op could not be bound.
- **uncovered** — `partial` (the method answers other statuses of the op),
  `default-only`, or `unattributed` (no method's rows reach the op, and
  `unreachedOps` does not say why).

A method's operations are the ones its rows reach — the same set every
generated branch test now bounds from the other side: a call during act to a
declared route outside that set (plus the side calls the app contracts spec's
`apiOutcomeRules` admit for the statuses the test serves, minus what the row
says `not-called`) turns the test red.

An operation is one a repositories / useCases method names as its `endpoint`
— the same set branch tests route. An endpoint listed only in
`dataFlow.apiEndpoints` is counted apart as **unbound endpoint**: a call to it
is recorded as `(unmatched)`, so no bound, reach or count sees it. Bind it to
the method that calls it.

Exit per platform, composed 2 > 1 > 3 > 0: `0` pass (`empty` when no screen
exists on the platform), `1` uncovered or a declaration error, `2` cannot
start, `3` something could not be evaluated (including an unbound endpoint)
and nothing is uncovered.

Each platform block ends with its totals — `[platform=p] total
n/a(no mock) … · n/a(not in OpenAPI) … · n/a(unbound endpoint) … ·
n/a(non-HTTP) …`, each with the number of screens it came from. The
per-screen `n/a (E)` lines are each screen's own; the one right above the
block's exit line is the last screen's, not the total. When the block is
exit 1 and something could not be evaluated as well, it also says
`uncovered is a floor:` and names what, since the statuses behind those were
never counted. The JSON carries the same: `totals.na_endpoints` and `floor`
per platform.

Each block also prints a **data** line — report only, it never moves the exit:
`[platform=p] data (report only) units N · arranged A · produced P · neither X ·
screens evaluated E of S (…) · Bool not in layout … · visibleElements not in
layout … · cells not bound …`. A unit is (screen, field, value): a field
declared `Bool` that the screen's layout binds (true and false), or a
`stateManagement.states[].values[]` whose `visibleElements` the layout all has.
ARRANGED means a row's `when` sets it (`data.X` or a seed `state.X`); PRODUCED,
that a row's `then` asserts it. The layout is the spec's `metadata.layoutFile`
only (no guessing: `layout not linked` otherwise), read by
`jui_cli.core.layout_facts` — the normalizer's includes, styles and platform
filter, and binding roots by the Ruby validator's grammar. When most of a
block's screens carry more data units than statuses, the line counts fields
instead of values (`coarse`); the values stay in `--json`
(`screens[].data`, `data_totals`, `data_coarse`).

### contracts baseline

```
jsonui-test contracts baseline [--initial]
```

When the gate starts, a project with uncovered statuses has two ways out:
close them all, or switch the check off. The baseline is the third: today's
entries recorded once, the gate holding every NEW one to the rule at once.

The file is `<spec_directory>/contracts_coverage_baseline.json`, next to the
app contracts spec; commit it. It holds the entries that keep coverage from
exit 0, sorted and without timestamps, so the same set is the same bytes:

- **uncovered** — (platform, spec, method, op, status)
- **unmeasured** — (platform, spec, op, cause), cause one of `unbound
  endpoint`, `no mock`, `not in OpenAPI`; and (platform, spec, op, status,
  cause) for `no scenario`, which is per status — another status of the same
  op losing its scenario later is a new entry, not the recorded one

With no file, the command writes nothing unless it is given `--initial`:
recording the first baseline accepts every current entry as debt, which is
the user's decision (`wrote …` with it; nothing is written when there are no
entries). With a file, it writes only what the file AND the current run hold
— **the command never adds an entry**:

```
updated docs/screens/json/contracts_coverage_baseline.json
removed 2 · kept 10 · new 1 not added (close them, or add by hand)
```

A recorded entry under what cannot be measured NOW — its op has no mock, is
not in the OpenAPI, or is an unbound endpoint; or, for one status, it has no
scenario — is not closed, only unmeasured: the command keeps it (`kept 12 (4
unmeasured now — not closed, kept)`), and the gate counts it as neither
matched nor stale (`· unmeasured now 4` on the line).

A recorded entry whose unit is not in the run at all — its screen left the
platform (`metadata.platforms`), its spec file is gone (a rename too), its
method or op is no longer declared, its status left the OpenAPI — has
**vanished**: it is not closed either. Only an entry the run measured and
found answered by a decision (a row, `alsoStatuses`, `excludedOutcomes`,
`unreachedOps`; for an unmeasured one, its op or status measured again) is
closed. A vanished entry fails the gate (`web: 2 baselined but gone from the
run (detail 2)`, `· vanished 2` on the line) and the command keeps it
(`(2 vanished — not closed, kept; remove or re-key them by hand)`):
removing or re-keying it is done by hand, where the diff shows it — the
user's decision. Dropping an endpoint, a status or a platform is not a way
out of the debt. baselined = matched + stale + unmeasured now + vanished.

Close a new entry with a row (Task 6 of the define agent). Adding it to the file by
hand also works, and the tool cannot tell it from the recorded debt — only the
commit's diff shows it. Once an entry is closed, run the command to drop it:
a closed entry left in the file is **stale** and fails the gate, because it
would silently swallow the same entry if it came back.

What the gate fails on whatever the file says is never recorded — declaration
errors, a row or a screen that could not be evaluated, HTTP with nothing
evaluated, cannot start. While any is present the command writes nothing and
exits 1, naming them: the statuses behind them were never counted, so a first
write would record a floor and a shrink would drop entries as closed that were
only unmeasured.

`contracts coverage` prints the comparison under each platform —
`[platform=web] baselined 6 (matched 6 · new 0 · stale 0)` — and `--json`
carries it as `baseline` per platform (the counts, and the entries
themselves as `new_entries` / `stale_entries` / `hidden_entries` /
`vanished_entries`) and
`baseline: {file, present}` at the top; each screen lists what could not be
measured as `unmeasured` (`{op, status?, cause}`). validate's summary names
the screens: `Coverage: FAILED (exit 1; web: 3 not in the baseline
(detail 2, other 1))`. A run on `--platform` or one screen
compares only what it measured.

### Generated branch tests: the act window

Every generated test installs the mock, builds the harness, lets the
construction settle, writes the arranged state, and only then calls
`rec.mark()` — `countFor`, `matchedCalls` and `lastBodyFor` read calls after
the mark, so what the constructor fetched is not read as the method's doing.
A hand-written test that never calls `mark()` reads every call, as before.

### A scenario's `delayMs`: the order responses arrive in

A scenario's `delayMs` delays its whole response by that many milliseconds
after the request (at most 30000) — what `mock serve` does, on all three
faces of the generated tests. So a row whose `when` picks a delayed scenario
for one of two parallel requests makes that one arrive last, and a view model
whose outcome depends on the arrival order can be driven by rows. `settle()`
waits for every delayed response before it returns, draining again after
each arrival, so `then` reads the state after they landed; past 31000 ms
(one capped delay and a margin) it fails the test by name, with how long it
waited. A screen with no `delayMs` generates what it did.

### Requests no route declares

A request during act that matches no declared route is answered 599 by the
runtime — a response no server returns — so whatever the view model did next
is made up. `rec.unmatchedCalls()` lists those requests in the window as
`METHOD path`. Until the release `UNMATCHED_GATE_FROM` names, every generated
test prints one warning per test that has any (`… reached no declared route
and was answered 599 …; from jsonui-cli <release> this fails the test`); from
that release it fails the test and names them. Unset, the warning names no
release. Clear one by declaring the route and its scenarios (a repositories /
useCases `endpoint` and a mock); a call the app's network layer makes around
every request is admitted once, with `apiOutcomeRules` (below).

Only the app's own API counts. A request to another host — an analytics SDK,
say — is the info `unmatched_foreign: N — METHOD origin/path`, never a
failure, and routes answer only the app's requests (another host's POST to a
declared path is not served). Tell the runtime which hosts are the app's: on
web, export `apiOrigins` from the screen's harness module (`export const
apiOrigins = ["https://api.example.com"]`; a relative URL is always the
app's); on iOS, give the harness `apiOrigin` (override it on
`BaseBranchHarness`, or declare it on your own `BranchHarness`). Undeclared,
the hosts cannot be told apart and every unmatched request counts as the
app's — the message says to declare them. Android needs nothing: MockWebServer
only ever sees the app's own requests.

### Side calls the screen does not declare

A rule's `sideCalls` name operations the app's network layer makes around a
call — ApiClient's logout after a 401, say. When the screen does not declare
such an operation, the generated test serves it anyway, as a **side route**:
under its operationId, with its mock's default scenario (`generate
branch-tests` prints a `side routes:` line). It is admitted only in the tests
whose served statuses the rule names — a call to it anywhere else is the
bound's red — and it is not an endpoint of the screen: `contracts coverage`
requires nothing of it. An operationId that is already the screen's name for a
different endpoint stops generation. An app without `apiOutcomeRules`
generates what it did.

### Harness conditions (`harnessConditions`)

When a view model's calls depend on something outside it — a signed-in
session, say — no mock can arrange that, and the op it gates cannot be closed
by a row. Declare the precondition once, in the app contracts spec:

```json
"harnessConditions": {
  "session": {"values": ["absent", "present"], "default": "absent",
              "reason": "whether a user is signed in; the VM reads it at construction"}
}
```

and name it in a row's `when` as `"harness.session": "present"` (not `cond`,
which names a `branchContracts.conditions` witness). Every generated test then
calls `arrangeCondition(name, value)` for **every** declared condition — the
row's value, or the default — after the mock is installed and before the
harness is built. The hook is one consumer-owned file per app in the harness
directory: `branch-conditions.ts` (web, awaited, so it may be async),
`BranchConditions.kt` (a top-level function in the harness package),
`BranchConditions.swift`. A skeleton that fails every unimplemented pair is
written once when the file is missing; `--check` reports it missing. Make each
pair produce what production would give the view model to observe; the tool
cannot see whether it does.

A row naming an undeclared condition or a value outside `values`, or any
`harness.*` key when no app contracts spec declares `harnessConditions`, is a
declaration error in `generate branch-tests` and in `contracts coverage`
(exit 1). Coverage counts such rows as ordinary rows and reports them as
`condition_rows`. An app without `harnessConditions` gets none of this: its
generated files are byte for byte what they were.

Whether a condition changes anything is a question the rows do not answer: a
row naming `harness.session: "present"` stays green if the session decides
nothing it asserts. `generate branch-tests --condition-controls` adds, after
each row that names a condition away from its default, a **control**
(`[control: session=absent instead of present]`) that runs the same act and
assertions with every condition at its default and never fails; when all of
them still hold it prints `condition_without_effect: <row> …` (info, on the
console — a JSON reporter does not show it). Off by default: it doubles those
rows.

### `seedableState` on a view model built from `init` arguments

`branchContracts.seedableState` names ViewModel-internal state a branch may
arrange; its value may be a scalar, an object or a list, and the read-back is
a partial match on every platform (the seed's keys only, nested, lists
element-wise). One consumer-side consequence, measured on a screen whose
seeded value is a `let` init argument on iOS: the harness cannot assign it,
so its `setState` **rebuilds the view model**. Any data keys the same
arrange step wrote before the seed then live on the old instance — the
harness must replay them onto the new one (or apply the seed first). This
is the harness's contract, not the runtime's: the read-back only tells you
the seed took.

On Android the runtime's `BaseBranchHarness.setState` writes each key to the
view model's field and to the `_data` class — to each only when its type
takes the value. A view model's state and the layout's data may share a name
with different types (a `List<String>` of choices and the card collection
drawing them): the key goes to the side that takes it. A key neither side
takes, when either declares that name, fails naming the key and both types.

### Legacy Syntax

For backwards compatibility, the old syntax still works:

```bash
jsonui-test generate -f test.test.json
jsonui-test generate --schema
```

## Test File Format

Test files must be valid JSON with `.test.json` extension.

### Screen Test Example

```json
{
  "type": "screen",
  "source": {
    "layout": "layouts/home.json"
  },
  "metadata": {
    "name": "home_screen_test",
    "description": "Tests for home screen"
  },
  "platform": "ios",
  "cases": [
    {
      "name": "initial_display",
      "description": "Verify initial elements",
      "descriptionFile": "descriptions/home/initial_display.json",
      "steps": [
        { "action": "waitFor", "id": "root_view", "timeout": 5000 },
        { "assert": "visible", "id": "title_label" }
      ]
    }
  ]
}
```

**Case Fields:**
- `description`: Inline description text
- `descriptionFile`: Path to external JSON file with detailed test documentation (relative to test file)

### Flow Test Example

```json
{
  "type": "flow",
  "metadata": {
    "name": "login_flow",
    "description": "User login flow test"
  },
  "steps": [
    { "action": "waitFor", "id": "login_screen" },
    { "action": "input", "id": "email_field", "value": "test@example.com" },
    { "action": "input", "id": "password_field", "value": "password123" },
    { "action": "tap", "id": "login_button" },
    { "assert": "visible", "id": "home_screen" }
  ]
}
```

## Supported Actions

| Action | Required | Optional | Description |
|--------|----------|----------|-------------|
| tap | id | text, timeout | Tap on an element |
| doubleTap | id | timeout | Double tap |
| longPress | id | duration, timeout | Long press |
| input | id, value | timeout | Input text |
| clear | id | timeout | Clear text field |
| scroll | id, direction | amount, timeout | Scroll |
| swipe | id, direction | timeout | Swipe gesture |
| waitFor | id | timeout | Wait for element |
| waitForAny | ids | timeout | Wait for any element |
| wait | ms | - | Wait duration |
| back | - | - | Navigate back |
| screenshot | name | - | Take screenshot |
| alertTap | button | timeout | Tap button in alert dialog |
| selectOption | id | value, label, index, timeout | Select option from dropdown |
| tapItem | id, index | timeout | Tap item at index in collection |
| selectTab | index | id, timeout | Select tab by index |

**Direction values:** `up`, `down`, `left`, `right`

**Platform notes:**
- `selectOption`: `index`, `value` and `label` are three ways to name ONE option, with precedence `index` → `value` → `label` (a lower one is ignored when a higher one is present — same on iOS, Android and web). Write exactly one; `validate` warns when a step carries two or more. On this action `label` is the option's visible text, **not** the step note it is everywhere else — a note written there is the option the driver selects.
- `selectTab`: For `ios-uikit`, `id` is optional (uses UITabBarController directly). For `ios-swiftui`/`android`/`web`, `id` is required (uses `{id}_tab_{index}` pattern).

## Supported Assertions

| Assert | Required | Optional | Description |
|--------|----------|----------|-------------|
| visible | id | timeout | Element is visible |
| notVisible | id | timeout | Element is not visible |
| enabled | id | timeout | Element is enabled |
| disabled | id | timeout | Element is disabled |
| text | id | equals, contains, timeout | Text matches |
| count | id, equals | timeout | Element count |

## Running Tests

```bash
# Install with dev dependencies
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- --dev

# Run tests
pytest

# Run with coverage
pytest --cov=jsonui_test_cli

# Run specific test file
pytest tests/test_validator.py -v
```

## Project Structure

```
test_tools/
├── installer/
│   ├── bootstrap.sh            # Bootstrap script for curl install
│   ├── install_jsonui_test.sh  # Main installer script
│   └── README.md               # Installer documentation
├── pyproject.toml              # Package configuration
├── README.md                   # This file
├── jsonui-test                 # CLI entry point (development)
├── jsonui_test_cli/
│   ├── __init__.py
│   ├── cli.py                  # CLI commands
│   ├── schema.py               # Action/assertion definitions
│   ├── validator.py            # Test file validator
│   └── generator.py            # Documentation generator
└── tests/
    ├── test_cli.py
    ├── test_validator.py
    └── test_generator.py
```
