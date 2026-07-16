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
- **Android**: pulls `/sdcard/Android/data/<appId>/files/jsonui-artifacts` and `/data/local/tmp/jsonui-artifacts` from the device via `adb pull`. adb is resolved from `test.artifacts.android.adb` (explicit path) > PATH > `$ANDROID_HOME` / `$ANDROID_SDK_ROOT` > the OS-default SDK location (`~/Library/Android/sdk` on macOS, `~/Android/Sdk` on Linux) — so it also works from environments without a login-shell PATH (e.g. an MCP daemon).

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
      "android": { "appId": "com.example.app", "serial": null, "adb": null }
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
