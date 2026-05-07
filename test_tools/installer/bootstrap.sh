#!/usr/bin/env bash

# JsonUI Test CLI Bootstrap Script
# This script downloads the installer and runs it with automatic Python setup
#
# Usage examples:
#   curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- -v v1.0.0
#   curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- -d ./my-project
#   curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-test-runner/main/test_tools/installer/bootstrap.sh | bash -s -- --dev

set -e

# Configuration
GITHUB_REPO="Tai-Kimura/jsonui-test-runner"
INSTALLER_PATH="test_tools/installer/install_jsonui_test.sh"
REQUIRED_PYTHON_VERSION="3.11"
MINIMUM_PYTHON_VERSION="3.10"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to compare version numbers
version_compare() {
    printf '%s\n%s' "$1" "$2" | sort -V | head -n1
}

# Check and setup Python environment
setup_python_environment() {
    print_info "Checking Python environment..."

    # Check if mise is installed
    if command -v mise &> /dev/null; then
        print_info "Found mise"

        # Check current Python version
        if command -v python3 &> /dev/null; then
            CURRENT_PYTHON=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
                print_info "Python $CURRENT_PYTHON is compatible"
                return 0
            fi
        fi

        # Install Python if needed
        print_info "Installing Python $REQUIRED_PYTHON_VERSION with mise..."
        if mise install python@$REQUIRED_PYTHON_VERSION; then
            mise use python@$REQUIRED_PYTHON_VERSION
            print_info "Python $REQUIRED_PYTHON_VERSION installed and activated"
        fi

    # Check if pyenv is installed
    elif command -v pyenv &> /dev/null; then
        print_info "Found pyenv"
        eval "$(pyenv init -)" 2>/dev/null || true

        # Check current Python version
        if command -v python3 &> /dev/null; then
            CURRENT_PYTHON=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
                print_info "Python $CURRENT_PYTHON is compatible"
                return 0
            fi
        fi

        # Install Python if needed
        print_info "Installing Python $REQUIRED_PYTHON_VERSION with pyenv..."
        if pyenv install -s "$REQUIRED_PYTHON_VERSION"; then
            pyenv local "$REQUIRED_PYTHON_VERSION"
            print_info "Python $REQUIRED_PYTHON_VERSION installed and set as local version"
        fi

    # Check system Python
    elif command -v python3 &> /dev/null; then
        CURRENT_PYTHON=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
            print_info "System Python $CURRENT_PYTHON is compatible"
            return 0
        else
            print_warning "System Python $CURRENT_PYTHON is too old (minimum: $MINIMUM_PYTHON_VERSION)"
            print_info "Consider installing mise or pyenv for better Python version management"
            print_info "  mise: curl https://mise.run | sh"
            print_info "  pyenv: brew install pyenv (macOS)"
            return 1
        fi
    else
        print_error "Python not found!"
        print_info "Please install Python $MINIMUM_PYTHON_VERSION or later"
        print_info "Recommended: Install mise first"
        print_info "  curl https://mise.run | sh"
        return 1
    fi
}

# Parse arguments (pass them to the installer)
ARGS="$@"

# Default to main branch if no version specified
VERSION="main"

# Parse arguments to extract version
set -- "$@"
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

print_info "JsonUI Test CLI Bootstrap"
print_info "Version: $VERSION"

# Setup Python environment first
setup_python_environment

print_info "Downloading installer from branch/tag: $VERSION"

# Download the installer script
INSTALLER_URL="https://raw.githubusercontent.com/$GITHUB_REPO/$VERSION/$INSTALLER_PATH?$(date +%s)"
TEMP_INSTALLER=$(mktemp)

if ! curl -L -f -o "$TEMP_INSTALLER" "$INSTALLER_URL"; then
    print_error "Failed to download installer from $INSTALLER_URL"
    print_error "Please check if the version/branch '$VERSION' exists."
    rm -f "$TEMP_INSTALLER"
    exit 1
fi

# Make it executable
chmod +x "$TEMP_INSTALLER"

# Run the installer with all arguments
print_info "Running installer..."
"$TEMP_INSTALLER" $ARGS

# Cleanup
rm -f "$TEMP_INSTALLER"
