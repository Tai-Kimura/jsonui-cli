#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== JsonUI CLI Tools Installer ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}!${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

# Check Ruby
if command -v ruby &> /dev/null; then
    RUBY_VERSION=$(ruby -v | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    success "Ruby $RUBY_VERSION found"
else
    error "Ruby not found. Please install Ruby 2.7.4 or later."
    exit 1
fi

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
    success "Python $PYTHON_VERSION found"
else
    warning "Python3 not found. test_tools will not be installed."
fi

# Check Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    success "Node.js $NODE_VERSION found"
else
    warning "Node.js not found. Hotloader functionality will not work."
fi

echo ""
echo "Installing tools..."
echo ""

# Copy shared modules to Python tools
copy_shared_modules() {
    local target_dir="$1"
    local pkg_name="$2"

    if [ -d "$SCRIPT_DIR/shared/validation" ] && [ -d "$target_dir/$pkg_name" ]; then
        rm -rf "$target_dir/$pkg_name/validation"
        cp -r "$SCRIPT_DIR/shared/validation" "$target_dir/$pkg_name/"
        rm -rf "$target_dir/$pkg_name/validation/__pycache__"

        if [ -f "$SCRIPT_DIR/shared/schema.py" ]; then
            cp "$SCRIPT_DIR/shared/schema.py" "$target_dir/$pkg_name/"
            # Also copy to test_doc/ for document_tools (markdown imports from ..schema)
            if [ -d "$target_dir/$pkg_name/test_doc" ]; then
                cp "$SCRIPT_DIR/shared/schema.py" "$target_dir/$pkg_name/test_doc/"
            fi
        fi
    fi
}

# Install sjui_tools
echo "--- sjui_tools ---"
if [ -d "$SCRIPT_DIR/sjui_tools" ]; then
    chmod +x "$SCRIPT_DIR/sjui_tools/bin/sjui"
    success "sjui_tools ready"
else
    error "sjui_tools not found"
fi

# Install kjui_tools
echo "--- kjui_tools ---"
if [ -d "$SCRIPT_DIR/kjui_tools" ]; then
    chmod +x "$SCRIPT_DIR/kjui_tools/bin/kjui"
    if [ -f "$SCRIPT_DIR/kjui_tools/Gemfile" ]; then
        cd "$SCRIPT_DIR/kjui_tools"
        if command -v bundle &> /dev/null; then
            bundle install --quiet
            success "kjui_tools dependencies installed"
        else
            warning "Bundler not found. Run 'gem install bundler' then 'bundle install' in kjui_tools/"
        fi
        cd "$SCRIPT_DIR"
    fi
    success "kjui_tools ready"
else
    error "kjui_tools not found"
fi

# Install rjui_tools
echo "--- rjui_tools ---"
if [ -d "$SCRIPT_DIR/rjui_tools" ]; then
    chmod +x "$SCRIPT_DIR/rjui_tools/bin/rjui"
    if [ -f "$SCRIPT_DIR/rjui_tools/Gemfile" ]; then
        cd "$SCRIPT_DIR/rjui_tools"
        if command -v bundle &> /dev/null; then
            bundle install --quiet
            success "rjui_tools dependencies installed"
        else
            warning "Bundler not found. Run 'gem install bundler' then 'bundle install' in rjui_tools/"
        fi
        cd "$SCRIPT_DIR"
    fi
    success "rjui_tools ready"
else
    error "rjui_tools not found"
fi

# Install jui_tools
echo "--- jui_tools ---"
if [ -d "$SCRIPT_DIR/jui_tools" ]; then
    if command -v python3 &> /dev/null; then
        cd "$SCRIPT_DIR/jui_tools"
        pip3 install -e . --quiet 2>/dev/null || pip3 install -e .
        cd "$SCRIPT_DIR"
        success "jui_tools installed"
    else
        warning "Skipping jui_tools (Python3 required)"
    fi
else
    error "jui_tools not found"
fi

# Install test_tools
echo "--- test_tools ---"
if [ -d "$SCRIPT_DIR/test_tools" ]; then
    if command -v python3 &> /dev/null; then
        copy_shared_modules "$SCRIPT_DIR/test_tools" "jsonui_test_cli"
        cd "$SCRIPT_DIR/test_tools"
        pip3 install -e . --quiet 2>/dev/null || pip3 install -e .
        cd "$SCRIPT_DIR"
        success "test_tools installed"
    else
        warning "Skipping test_tools (Python3 required)"
    fi
else
    error "test_tools not found"
fi

# Install document_tools
echo "--- document_tools ---"
if [ -d "$SCRIPT_DIR/document_tools" ]; then
    if command -v python3 &> /dev/null; then
        copy_shared_modules "$SCRIPT_DIR/document_tools" "jsonui_doc_cli"
        cd "$SCRIPT_DIR/document_tools"
        pip3 install -e . --quiet 2>/dev/null || pip3 install -e .
        cd "$SCRIPT_DIR"
        success "document_tools installed"
    else
        warning "Skipping document_tools (Python3 required)"
    fi
else
    error "document_tools not found"
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Add the following to your shell profile (.bashrc, .zshrc, etc.):"
echo ""
echo "  export PATH=\"$SCRIPT_DIR/sjui_tools/bin:\$PATH\""
echo "  export PATH=\"$SCRIPT_DIR/kjui_tools/bin:\$PATH\""
echo "  export PATH=\"$SCRIPT_DIR/rjui_tools/bin:\$PATH\""
echo ""
echo "Then run: source ~/.zshrc (or your shell profile)"
