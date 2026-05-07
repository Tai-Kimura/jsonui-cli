#!/usr/bin/env bash

# JsonUI Test CLI Installer Script
# This script downloads and installs jsonui-test-cli

set -e

# Default values
GITHUB_REPO="Tai-Kimura/jsonui-test-runner"
DEFAULT_BRANCH="main"
INSTALL_DIR="."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -v, --version <version>    Specify version/branch/tag/commit to download (default: main)"
    echo "  -d, --directory <dir>      Installation directory (default: current directory)"
    echo "  --dev                      Install with development dependencies"
    echo "  -h, --help                 Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                         # Install latest from main branch"
    echo "  $0 -v v1.0.0               # Install specific version (tag)"
    echo "  $0 -v feature-branch       # Install from specific branch"
    echo "  $0 -d ./my-project         # Install in specific directory"
    echo "  $0 --dev                   # Install with dev dependencies (pytest)"
    exit 0
}

# Parse command line arguments
VERSION=""
DEV_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -d|--directory)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --dev)
            DEV_MODE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Use default branch if no version specified
if [ -z "$VERSION" ]; then
    VERSION="$DEFAULT_BRANCH"
fi

# Validate installation directory
if [ ! -d "$INSTALL_DIR" ]; then
    print_error "Installation directory does not exist: $INSTALL_DIR"
    exit 1
fi

# Change to installation directory
cd "$INSTALL_DIR"

print_info "Installing JsonUI Test CLI..."
print_info "Version: $VERSION"
print_info "Directory: $(pwd)"

# Function to compare version numbers
version_compare() {
    printf '%s\n%s' "$1" "$2" | sort -V | head -n1
}

# Check Python version
check_python() {
    MINIMUM_PYTHON_VERSION="3.10"

    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        echo ""
        echo "Please install Python 3.10 or higher"
        echo ""
        echo "Using mise (recommended):"
        echo "  mise install python@3.11"
        echo "  mise use python@3.11"
        echo ""
        echo "Or using pyenv:"
        echo "  pyenv install 3.11.0"
        echo "  pyenv local 3.11.0"
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
        print_error "Python $PYTHON_VERSION is too old. Required: $MINIMUM_PYTHON_VERSION+"
        echo ""
        echo "Using mise (recommended):"
        echo "  mise install python@3.11"
        echo "  mise use python@3.11"
        exit 1
    fi

    print_info "Python version: $PYTHON_VERSION"
}

# Check if jsonui_test_cli already exists
if [ -d "jsonui_test_cli" ]; then
    print_warning "jsonui_test_cli directory already exists."
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Installation cancelled."
        exit 0
    else
        rm -rf jsonui_test_cli
        rm -f pyproject.toml
        rm -f jsonui-test
    fi
fi

# Check Python first
check_python

# Create temporary directory for download
TEMP_DIR=$(mktemp -d)
print_info "Created temporary directory: $TEMP_DIR"

# Cleanup function
cleanup() {
    if [ -d "$TEMP_DIR" ]; then
        print_info "Cleaning up temporary files..."
        rm -rf "$TEMP_DIR"
    fi
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Download the archive
print_info "Downloading JsonUI Test CLI $VERSION..."

# Determine download URL based on VERSION format
if [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+ ]]; then
    # Tag with 'v' prefix (e.g., v1.0.0)
    DOWNLOAD_URL="https://github.com/$GITHUB_REPO/archive/refs/tags/$VERSION.tar.gz"
    print_info "Detected: tag"
elif [[ "$VERSION" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
    # Commit hash (7-40 hex characters)
    DOWNLOAD_URL="https://github.com/$GITHUB_REPO/archive/$VERSION.tar.gz"
    print_info "Detected: commit hash"
else
    # Branch name
    DOWNLOAD_URL="https://github.com/$GITHUB_REPO/archive/$VERSION.tar.gz"
    print_info "Detected: branch"
fi

if ! curl -L -f -o "$TEMP_DIR/jsonui-test-runner.tar.gz" "$DOWNLOAD_URL"; then
    print_error "Failed to download from $DOWNLOAD_URL"
    print_error "Please check if the version/branch '$VERSION' exists."
    exit 1
fi

# Extract the archive
print_info "Extracting archive..."
tar -xzf "$TEMP_DIR/jsonui-test-runner.tar.gz" -C "$TEMP_DIR"

# Find the extracted directory
EXTRACT_DIR=$(find "$TEMP_DIR" -maxdepth 1 -type d -name "jsonui-test-runner-*" | head -1)

if [ -z "$EXTRACT_DIR" ]; then
    print_error "Failed to find extracted directory"
    exit 1
fi

# Copy test_tools contents
TEST_TOOLS_PATH=""
if [ -d "$EXTRACT_DIR/test_tools" ]; then
    TEST_TOOLS_PATH="$EXTRACT_DIR/test_tools"
fi

if [ -n "$TEST_TOOLS_PATH" ]; then
    print_info "Installing jsonui_test_cli..."

    # Copy jsonui_test_cli package
    if [ -d "$TEST_TOOLS_PATH/jsonui_test_cli" ]; then
        cp -r "$TEST_TOOLS_PATH/jsonui_test_cli" .
        print_info "Copied jsonui_test_cli package"
    fi

    # Copy pyproject.toml
    if [ -f "$TEST_TOOLS_PATH/pyproject.toml" ]; then
        cp "$TEST_TOOLS_PATH/pyproject.toml" .
        print_info "Copied pyproject.toml"
    fi

    # Copy jsonui-test entry point
    if [ -f "$TEST_TOOLS_PATH/jsonui-test" ]; then
        cp "$TEST_TOOLS_PATH/jsonui-test" .
        chmod +x jsonui-test
        print_info "Copied jsonui-test entry point"
    fi

    # Copy tests if dev mode
    if [ "$DEV_MODE" = true ] && [ -d "$TEST_TOOLS_PATH/tests" ]; then
        cp -r "$TEST_TOOLS_PATH/tests" .
        print_info "Copied tests directory"
    fi

    # Create VERSION file
    echo "$VERSION" > jsonui_test_cli/VERSION
    print_info "Set version to: $VERSION"

    print_info "Installing Python package..."

    if [ "$DEV_MODE" = true ]; then
        pip3 install ".[dev]"
        print_info "Installed with development dependencies"
    else
        pip3 install .
        print_info "Installed package"
    fi

    # Clean up build artifacts
    rm -rf jsonui_test_cli.egg-info build
    rm -f pyproject.toml jsonui-test

    print_info "jsonui_test_cli installed successfully"
else
    print_error "test_tools not found in the downloaded version"
    exit 1
fi

print_info ""
print_info "Installation completed successfully!"
print_info ""
print_info "You can now use the tool:"
print_info "  jsonui-test validate <file>"
print_info "  jsonui-test generate -f <file>"
print_info ""
print_info "For help:"
print_info "  jsonui-test --help"
print_info ""
print_info "For more information, visit: https://github.com/$GITHUB_REPO"
