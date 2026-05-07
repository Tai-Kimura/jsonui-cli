# JsonUI Test CLI Installer

This directory contains installation scripts for JsonUI Test CLI.

## Quick Start

To install JsonUI Test CLI in your project, run this command:

```bash
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash
```

This will download and install:
- `jsonui_test_cli` - CLI tool for validating and generating documentation from JsonUI test files

## Installation Options

### Install specific version

```bash
# Install from a specific tag
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- -v v1.0.0

# Install from a specific branch
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- -v feature-branch
```

### Install in specific directory

```bash
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- -d ./my-project
```

### Install with development dependencies

```bash
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- --dev
```

### Combined options

```bash
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- -v v1.0.0 -d ./my-project --dev
```

## Manual Installation

If you prefer to download and run the installer manually:

1. Download the installer script:
```bash
curl -O https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/install_jsonui_test.sh
chmod +x install_jsonui_test.sh
```

2. Run the installer:
```bash
./install_jsonui_test.sh [OPTIONS]
```

Available options:
- `-v, --version <version>` - Specify version/branch/tag to download (default: main)
- `-d, --directory <dir>` - Installation directory (default: current directory)
- `--dev` - Install with development dependencies (pytest)
- `-h, --help` - Show help message

## What Gets Installed

The installer will:
1. Download the specified version of jsonui-test-runner
2. Extract `jsonui_test_cli` package to the current directory
3. Copy `pyproject.toml` and `jsonui-test` entry point
4. Install the Python package using pip
5. (Optional) Copy tests directory if `--dev` flag is used

## Using the Tool

After installation, you can use the `jsonui-test` command:

```bash
# Validate test files
jsonui-test validate path/to/test.test.json
jsonui-test validate tests/

# Generate documentation
jsonui-test generate -f test.test.json -o docs/test.md
jsonui-test generate -f test.test.json -o docs/test.html --format html

# Generate schema reference
jsonui-test generate --schema -o docs/schema.md

# See all available commands
jsonui-test --help
```

## Requirements

- Python 3.10 or higher
- pip
- curl
- tar

### Python Version Setup

If you don't have Python 3.10+, the bootstrap script will try to install it using mise or pyenv.

**Using mise (recommended):**
```bash
curl https://mise.run | sh
mise install python@3.11
mise use python@3.11
```

**Using pyenv:**
```bash
brew install pyenv  # macOS
pyenv install 3.11.0
pyenv local 3.11.0
```

## Troubleshooting

If you encounter issues:
1. Ensure you have Python 3.10 or higher installed
2. Check your internet connection
3. Verify the version/branch name exists
4. Check file permissions in your installation directory

For more help, visit: https://github.com/Tai-Kimura/jsonui-test-runner
