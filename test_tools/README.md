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
