#!/bin/bash
#
# JsonUI CLI Tools Bootstrap Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-cli/main/installer/bootstrap.sh | bash
#
# Options:
#   JSONUI_INSTALL_DIR  - Base directory (default: current directory). jsonui-cli/ will be created inside.
#   JSONUI_CLI_DIR      - Full install path (overrides JSONUI_INSTALL_DIR). Set this to e.g.
#                         $HOME/.jsonui-cli to align with jsonui-mcp-server's 4-layer fallback.
#   JSONUI_TOOLS        - Tools to install: all, sjui, kjui, rjui, jui, test, doc (default: all)
#

set -e

# Parse arguments
while [ $# -gt 0 ]; do
    case "$1" in
        -d|--dir)
            JSONUI_INSTALL_DIR="$2"
            shift 2
            ;;
        -t|--tools)
            JSONUI_TOOLS="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: bootstrap.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -d, --dir DIR    Base directory (default: .). jsonui-cli/ will be created inside."
            echo "                   Ignored if JSONUI_CLI_DIR is set."
            echo "  -t, --tools LIST Tools to install: all, sjui, kjui, rjui, jui, test, doc (default: all)"
            echo "  -h, --help       Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  JSONUI_INSTALL_DIR  Base directory (same as --dir)."
            echo "  JSONUI_CLI_DIR      Full install path (overrides JSONUI_INSTALL_DIR and --dir)."
            echo "  JSONUI_TOOLS        Tools list (same as --tools)."
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Configuration
REPO_URL="https://github.com/Tai-Kimura/jsonui-cli.git"
BASE_DIR="${JSONUI_INSTALL_DIR:-.}"
INSTALL_DIR="${JSONUI_CLI_DIR:-$BASE_DIR/jsonui-cli}"
TOOLS="${JSONUI_TOOLS:-all}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}==>${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warning() { echo -e "${YELLOW}!${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

echo ""
echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     JsonUI CLI Tools Installer         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Check dependencies
info "Checking dependencies..."

if ! command -v git >/dev/null 2>&1; then
    error "git is required but not installed."
fi
success "git found"

if command -v ruby >/dev/null 2>&1; then
    RUBY_VERSION=$(ruby -v | grep -oE '[0-9]+\.[0-9]+' | head -1)
    success "Ruby $RUBY_VERSION found"
else
    warning "Ruby not found. sjui/kjui/rjui tools require Ruby 2.7+"
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON_VERSION=$(python3 --version | grep -oE '[0-9]+\.[0-9]+')
    success "Python $PYTHON_VERSION found"
else
    warning "Python3 not found. test_tools and document_tools require Python 3.10+"
fi

if command -v node >/dev/null 2>&1; then
    NODE_VERSION=$(node --version)
    success "Node.js $NODE_VERSION found"
else
    warning "Node.js not found. Hotloader functionality will not work."
fi

echo ""

# Clone or update repository
info "Installing to $INSTALL_DIR..."

if [ -d "$INSTALL_DIR" ]; then
    if [ -d "$INSTALL_DIR/.git" ]; then
        # Has .git directory - can update via git
        info "Updating existing installation..."
        cd "$INSTALL_DIR"
        git fetch origin
        git reset --hard origin/main
        success "Updated to latest version"
    else
        # No .git directory - remove and re-clone
        info "Re-installing (previous .git was cleaned up)..."
        rm -rf "$INSTALL_DIR"
        git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
        success "Re-cloned repository"
    fi
else
    info "Cloning repository..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
    success "Cloned repository"
fi

cd "$INSTALL_DIR"

# Copy shared attribute_definitions.json to each tool
info "Setting up shared resources..."
ATTR_DEF="shared/core/attribute_definitions.json"
if [ -f "$ATTR_DEF" ]; then
    for tool_dir in sjui_tools kjui_tools rjui_tools; do
        if [ -d "$tool_dir/lib/core" ]; then
            # Remove symlink if exists
            rm -f "$tool_dir/lib/core/attribute_definitions.json"
            # Copy the actual file
            cp "$ATTR_DEF" "$tool_dir/lib/core/attribute_definitions.json"
        fi
    done
    success "Copied attribute_definitions.json to all tools"
fi

# Copy shared validation module to Python tools
copy_shared_validation() {
    local target_dir="$1"
    local pkg_name="$2"

    if [ -d "shared/validation" ] && [ -d "$target_dir/$pkg_name" ]; then
        rm -rf "$target_dir/$pkg_name/validation"
        cp -r "shared/validation" "$target_dir/$pkg_name/"
        rm -rf "$target_dir/$pkg_name/validation/__pycache__"

        # validation module imports from ..schema
        if [ -f "shared/schema.py" ]; then
            cp "shared/schema.py" "$target_dir/$pkg_name/"
        fi
    fi
}

if [ -d "shared/validation" ]; then
    copy_shared_validation "test_tools" "jsonui_test_cli"
    copy_shared_validation "document_tools" "jsonui_doc_cli"
    success "Copied shared validation module to Python tools"
fi

# Copy schema.py to test_doc subdirectory (required for document_tools imports)
if [ -f "shared/schema.py" ] && [ -d "document_tools/jsonui_doc_cli/test_doc" ]; then
    cp "shared/schema.py" "document_tools/jsonui_doc_cli/test_doc/"
fi

# Remove unnecessary files for production
# Keep shared/core/ — jsonui-mcp-server's 4-layer fallback reads
# attribute_definitions.json and component_metadata.json from there.
info "Cleaning up development files..."
rm -rf .git
rm -rf .github
rm -rf installer
rm -rf shared/validation
rm -f  shared/schema.py
rm -f  README.md
rm -f  install.sh
rm -rf */spec
rm -rf */coverage
rm -rf */.rspec_status
rm -f  */.DS_Store
rm -rf test_tools/tests
rm -rf test_tools/.pytest_cache
rm -rf test_tools/build
rm -rf test_tools/*.egg-info
rm -rf document_tools/build
rm -rf document_tools/*.egg-info
success "Cleaned up (preserved shared/core/ for jsonui-mcp-server)"

# Install tools
echo ""
info "Setting up tools..."

should_install() {
    [ "$TOOLS" = "all" ] || echo "$TOOLS" | grep -q "$1"
}

# sjui_tools
if should_install "sjui" && [ -d "sjui_tools" ]; then
    chmod +x sjui_tools/bin/sjui
    success "sjui_tools ready"
fi

# kjui_tools
if should_install "kjui" && [ -d "kjui_tools" ]; then
    chmod +x kjui_tools/bin/kjui
    if [ -f "kjui_tools/Gemfile" ] && command -v bundle >/dev/null 2>&1; then
        cd kjui_tools && bundle install --quiet 2>/dev/null && cd ..
        success "kjui_tools dependencies installed"
    fi
    success "kjui_tools ready"
fi

# rjui_tools
if should_install "rjui" && [ -d "rjui_tools" ]; then
    chmod +x rjui_tools/bin/rjui
    if [ -f "rjui_tools/Gemfile" ] && command -v bundle >/dev/null 2>&1; then
        cd rjui_tools && bundle install --quiet 2>/dev/null && cd ..
        success "rjui_tools dependencies installed"
    fi
    success "rjui_tools ready"
fi

# Python CLI installer.
#
# `pip install -e` registers a single editable project record per package
# name. That record points at whatever directory was `pip install -e`-d
# last. So if the user has previously run pip install from another checkout
# (e.g. a dev clone or a frozen copy under a subproject), our console
# scripts (`jui`, `jsonui-doc`, `jsonui-test`) keep pointing there — and
# break the instant that other directory is moved or deleted.
#
# To make the bootstrap the source of truth, we unconditionally reinstall
# from $INSTALL_DIR/<tool> every time. We also fall back to
# `--break-system-packages` on PEP 668 systems (Homebrew Python 3.12+,
# Debian/Ubuntu) where the global site-packages is externally managed.
install_python_tool() {
    local tool_dir="$1"
    local tool_name="$2"

    if ! command -v python3 >/dev/null 2>&1; then
        warning "Skipping $tool_dir ($tool_name) — python3 required"
        return
    fi

    cd "$tool_dir"
    if pip3 install -e . --quiet 2>/dev/null; then
        :
    elif pip3 install -e . --break-system-packages --quiet 2>/dev/null; then
        :
    else
        # Show the real error on the third attempt so users can see why.
        warning "pip3 install retry (showing errors):"
        pip3 install -e . --break-system-packages
    fi
    cd ..

    # Log where pip thinks the editable is now, so installs that got
    # blocked by a pre-existing pointer (e.g. from a subproject clone)
    # are caught immediately rather than at first run.
    local pkg_map
    case "$tool_dir" in
        jui_tools)      pkg_map="jui_cli" ;;
        test_tools)     pkg_map="jsonui-test-cli" ;;
        document_tools) pkg_map="jsonui-doc-cli" ;;
        *)              pkg_map="" ;;
    esac
    if [ -n "$pkg_map" ]; then
        local loc
        loc=$(pip3 show "$pkg_map" 2>/dev/null | awk -F': ' '/Editable project location/ {print $2}')
        if [ -n "$loc" ] && [ "$loc" != "$(pwd)/$tool_dir" ]; then
            success "$tool_dir installed ($tool_name) — pip editable: $loc"
        else
            success "$tool_dir installed ($tool_name)"
        fi
    else
        success "$tool_dir installed ($tool_name)"
    fi
}

if should_install "jui"  && [ -d "jui_tools" ];      then install_python_tool jui_tools      jui; fi
if should_install "test" && [ -d "test_tools" ];     then install_python_tool test_tools     jsonui-test; fi
if should_install "doc"  && [ -d "document_tools" ]; then install_python_tool document_tools jsonui-doc; fi

# Detect shell
SHELL_NAME=$(basename "$SHELL")
case "$SHELL_NAME" in
    zsh)  SHELL_RC="$HOME/.zshrc" ;;
    bash) SHELL_RC="$HOME/.bashrc" ;;
    *)    SHELL_RC="$HOME/.profile" ;;
esac

# Generate PATH export
# Python-tool wrappers (jui / jsonui-doc / jsonui-test) self-inject sys.path,
# so PATH alone is enough — no pip install required.
PATH_EXPORTS=""
[ -x "$INSTALL_DIR/jui_tools/bin/jui" ]            && PATH_EXPORTS="$PATH_EXPORTS\nexport PATH=\"$INSTALL_DIR/jui_tools/bin:\$PATH\""
[ -x "$INSTALL_DIR/document_tools/jsonui-doc" ]    && PATH_EXPORTS="$PATH_EXPORTS\nexport PATH=\"$INSTALL_DIR/document_tools:\$PATH\""
[ -x "$INSTALL_DIR/test_tools/jsonui-test" ]       && PATH_EXPORTS="$PATH_EXPORTS\nexport PATH=\"$INSTALL_DIR/test_tools:\$PATH\""
[ -d "$INSTALL_DIR/sjui_tools/bin" ]               && PATH_EXPORTS="$PATH_EXPORTS\nexport PATH=\"$INSTALL_DIR/sjui_tools/bin:\$PATH\""
[ -d "$INSTALL_DIR/kjui_tools/bin" ]               && PATH_EXPORTS="$PATH_EXPORTS\nexport PATH=\"$INSTALL_DIR/kjui_tools/bin:\$PATH\""
[ -d "$INSTALL_DIR/rjui_tools/bin" ]               && PATH_EXPORTS="$PATH_EXPORTS\nexport PATH=\"$INSTALL_DIR/rjui_tools/bin:\$PATH\""

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "Add the following to your $SHELL_RC:"
echo ""
echo -e "${YELLOW}# JsonUI CLI Tools${NC}"
echo -e "$PATH_EXPORTS"
echo ""
echo "Then run:"
echo -e "  ${BLUE}source $SHELL_RC${NC}"
echo ""
echo "Or run this to add automatically:"
echo -e "  ${BLUE}echo -e '$PATH_EXPORTS' >> $SHELL_RC && source $SHELL_RC${NC}"
echo ""
