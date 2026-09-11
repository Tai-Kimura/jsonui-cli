#!/bin/bash
#
# JsonUI CLI Tools Bootstrap Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-cli/main/installer/bootstrap.sh | bash
#
# Options:
#   JSONUI_INSTALL_DIR  - Base directory; jsonui-cli/ is created inside it.
#   JSONUI_CLI_DIR      - Full install path (overrides JSONUI_INSTALL_DIR).
#   JSONUI_TOOLS        - Tools to install: all, sjui, kjui, rjui, jui, test, doc, mcp (default: all)
#
# "mcp" installs the Claude Code MCP server (jsonui-mcp-server) and registers
# it in ~/.claude.json. Included in "all"; needs Node.js.
#
# Default install dir (neither var set): $HOME/.jsonui-cli — aligns with
# jsonui-mcp-server's 4-layer fallback and the platform tools' lookup.
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
            TOOLS_SOURCE="--tools"
            shift 2
            ;;
        -h|--help)
            echo "Usage: bootstrap.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -d, --dir DIR    Base directory; jsonui-cli/ is created inside it."
            echo "                   Ignored if JSONUI_CLI_DIR is set."
            echo "  -t, --tools LIST Tools to install: all, sjui, kjui, rjui, jui, test, doc, mcp (default: all)"
            echo "  -h, --help       Show this help message"
            echo ""
            echo "Default install dir (no -d / env): \$HOME/.jsonui-cli"
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
# jsonui-mcp-server is a separate repo with its own self-contained installer
# (clones itself to ~/.jsonui-mcp-server, npm build, and registers the
# `jui-tools` MCP server in ~/.claude.json). We delegate to it rather than
# duplicating that logic. Overridable for forks / pinned versions.
MCP_INSTALLER_URL="${JSONUI_MCP_INSTALLER_URL:-https://raw.githubusercontent.com/Tai-Kimura/jsonui-mcp-server/main/install.sh}"
# Resolve the install directory:
#   1. JSONUI_CLI_DIR     — full path, used verbatim.
#   2. JSONUI_INSTALL_DIR — base dir; jsonui-cli/ is created inside it.
#   3. neither            — default to $HOME/.jsonui-cli.
# The default is the home-dotted dir (NOT ./jsonui-cli in the current
# directory) so it lands where jsonui-mcp-server's 4-layer fallback and the
# platform tools look, and so a bare `curl ... | bash` from any cwd doesn't
# scatter a stray jsonui-cli/ into wherever it was run.
if [ -n "$JSONUI_CLI_DIR" ]; then
    INSTALL_DIR="$JSONUI_CLI_DIR"
elif [ -n "$JSONUI_INSTALL_DIR" ]; then
    INSTALL_DIR="$JSONUI_INSTALL_DIR/jsonui-cli"
else
    INSTALL_DIR="$HOME/.jsonui-cli"
fi
# 🚨 THE RESOLVED LIST, AND WHERE IT CAME FROM. `JSONUI_TOOLS=… curl … | bash`
# puts the variable on CURL, not on the bash that reads it — the form the README
# carried until 2026-09-10. The installer then ran with TOOLS=all and installed
# the MCP server that the caller believed they had excluded; it succeeded, so
# the output gave no sign. Printing the resolved value is what makes that
# visible, and printing WHERE it came from is what separates "I asked for all"
# from "nothing reached me". A bare `TOOLS=all` line cannot tell those apart,
# and the failure wears the face of the success.
if [ -n "${JSONUI_TOOLS:-}" ]; then
    TOOLS="$JSONUI_TOOLS"
    TOOLS_SOURCE="${TOOLS_SOURCE:-JSONUI_TOOLS}"
else
    TOOLS="all"
    TOOLS_SOURCE="default — JSONUI_TOOLS was not set in this shell"
fi
#: Every name `should_install` answers to. An unknown name must be refused
#: rather than silently matching nothing: a typo would otherwise install a
#: subset the caller never asked for, which is the same silence as above.
KNOWN_TOOLS="all sjui kjui rjui jui test doc mcp"

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

# Refuse a name nothing answers to, then say what will be installed and why.
for _t in $(echo "$TOOLS" | tr ',' ' '); do
    case " $KNOWN_TOOLS " in
        *" $_t "*) ;;
        *) error "unknown tool '$_t' in the tools list ('$TOOLS', from $TOOLS_SOURCE).
   Known: $KNOWN_TOOLS
   Nothing was installed. A name nothing matches would otherwise install a
   subset you did not ask for, silently." ;;
    esac
done
info "tools: $TOOLS  (from $TOOLS_SOURCE)"
if [ "$TOOLS" = "all" ] && [ "$TOOLS_SOURCE" != "--tools" ] && [ -z "${JSONUI_TOOLS:-}" ]; then
    echo "    all = sjui kjui rjui jui test doc mcp — INCLUDING the MCP server."
    echo "    If you meant to exclude something, the variable has to reach THIS"
    echo "    shell: 'curl … | JSONUI_TOOLS=\"…\" bash', or '--tools \"…\"'."
    echo "    'JSONUI_TOOLS=… curl … | bash' sets it on curl and never gets here."
fi

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

# Canonicalize INSTALL_DIR to an absolute path now that it exists. The
# default install dir is cwd-relative (`./jsonui-cli`), and the generated
# PATH exports below embed $INSTALL_DIR verbatim — a relative path there
# would only resolve from the directory the installer happened to run in,
# so `jui` (and the Ruby tools) would vanish from any other cwd. Resolve it
# once here so every export line is absolute.
INSTALL_DIR="$(pwd -P)"

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

# NOTE: The old copy_shared_validation() step (which injected shared/validation
# + shared/schema.py into the Python packages) was removed. test_tools
# (jsonui_test_cli) is now self-contained — it ships its own validation/ (incl.
# launch.py + mock.py) and schema.py — and document_tools (jsonui_doc_cli)
# imports the validator + schema constants from jsonui_test_cli. Injecting the
# old shared/ generation silently clobbered mock/launch/setMocks validation, so
# neither package is fed by shared/ anymore. shared/core/*.json (Ruby tools'
# copy target below) is unaffected. DO NOT reintroduce a shared/ copy here.

# Stamp the source SHA BEFORE the cleanup below deletes .git. The installed
# tree is not a git checkout, so this file is the only way `jui --version`
# and `jui sync_tool` can name the commit the toolchain came from (the
# version itself comes from the root VERSION file, which cleanup keeps).
if git rev-parse HEAD >/dev/null 2>&1; then
    git rev-parse HEAD > SOURCE_SHA
    success "Stamped SOURCE_SHA ($(cut -c1-12 SOURCE_SHA))"
else
    warning "Could not resolve git HEAD — SOURCE_SHA not stamped"
fi

# Remove unnecessary files for production
# Keep shared/core/ — jsonui-mcp-server's 4-layer fallback reads
# attribute_definitions.json and component_metadata.json from there, AND the
# Python loaders in jui_tools/document_tools/test_tools resolve every
# shared/core/*.py by walking up to this directory. Narrowing this to the two
# JSON files the MCP server names would delete those modules and turn
# `shared_core.load()` into a silent None.
info "Cleaning up development files..."
rm -rf .git
rm -rf .github
rm -rf installer
rm -f  README.md
rm -f  install.sh
rm -rf */spec
rm -rf */coverage
rm -rf */.rspec_status
rm -f  */.DS_Store
# 🔻 EVERY TOOL'S TEST TREE, AND THE PYTHON ONES NEED A LINE EACH. `rm -rf
# */spec` above is a one-level glob, so it covers all three Ruby tools at
# once; the Python tools keep their tests in `tests/`, which that glob does
# not reach, so each needs its own line. From the initial commit until
# 2026-09-11 only `test_tools` had one — `document_tools/tests` and
# `jui_tools/tests` shipped to every machine for four months, and the
# asymmetry read as deliberate because the `build` / `*.egg-info` lines below
# ARE paired. Nothing consumed them: measured across the consuming projects,
# references to the distributed test trees were zero.
#
# ⚠️ TWO COUNTS, TWO SUBJECTS. Both are right and they are not the same number:
#     199 = 83 + 116   what actually SHIPPED, measured at v1.8.70
#     200 = 83 + 117   what these rules now EXCLUDE
# The +1 is the arm below, which lives in `jui_tools/tests` and is therefore
# pruned by the rule it guards. Write which question a figure answers, or the
# pair reads as a discrepancy and someone "fixes" the correct one.
#
# 🚨 AND SAY WHICH TREE, NOT "FROM HERE". Whole-distribution totals move with
# every file added anywhere, so a figure anchored to "this commit" is stale as
# soon as the next one lands — measured: the line that used to stand here said
# `676 / 2923 from here`, written at 88df835c, and it was already 678 / 2924
# three commits later. Two figures that differ by one file read exactly like a
# discrepancy, which is the failure this whole comment is about, committed by
# the comment itself.
#
#     v1.8.70  (OLD rules)    476 excluded / 3122 delivered  (tracked 3598)
#     v1.8.71  (these rules)   678 excluded / 2924 delivered  (tracked 3602)
#     v1.8.72  (these rules)   678 excluded / 2924 delivered  (tracked 3602)
#              — same rules, same partition: measured on 58340fe8's tree by
#              materialising the archive and running the 17 rules, not predicted.
#     v1.8.73  (these rules)   679 excluded / 2924 delivered  (tracked 3603)
#              — same rules; one tracked file more (a test, pruned), measured on
#              a8d574a2's tree the same way.
#
# PINNED TO TAGS, and NOT to a SHA — a tag does not move, and naming the tip
# here would be stale the moment this file is committed, which is the bug
# being fixed. Each row closes on its own tree: excluded + delivered ==
# tracked.
#
# ⚠️ WHAT WAS WRONG WITH THE OLD LINE WAS ONLY THAT IT SAID "from here".
# Both of its pairs were correct partitions of their own trees — 676 + 2923
# really is 3599 — and a first reading of this file diagnosed the delivered
# figure as one tree's total minus another's excluded. That was false, and
# it was retracted by the reader who proposed it; the identity it rested on
# is just the partition restated. Recording it here anyway would have made
# this comment defend against a danger that never existed while leaving the
# real one — a figure anchored to a commit, in a file that outlives it.
#
# ⚠️ AND THE CONSERVATION LAW DOES NOT SETTLE IT. Two different splits of
# the same total both close: 676 + 2923 and 674 + 2925 are each 3599, and
# only one of them applies the rules below. Closing is necessary, not
# sufficient — to decide which split is right, run the rules or compare the
# delivered SET, not its size.
#
# For any other tree, derive it. The arm below builds the population from the
# repository rather than listing it, and THE RULES ARE `rm -rf` AND `rm -f`:
# README.md and install.sh are two tracked files only the second kind
# reaches, so a predicate grepping for `rm -rf` alone lands exactly two
# short. Two independent readers did.
#
# ⚠️ `jui_tools/tests/test_the_distribution_prunes_every_test_tree.py` derives
# this population from the repo rather than listing it, so a seventh tool
# added later fails there instead of shipping its tests.
rm -rf test_tools/tests
rm -rf document_tools/tests
rm -rf jui_tools/tests
rm -rf test_tools/.pytest_cache
# 🔻 THESE TWO PAIRS CANNOT CATCH WHAT `pip install -e .` MAKES. The prune
# runs here; the pip step is ~70 lines further down, so anything it creates
# arrives after this block has finished. They exist for a source tree that
# already had the artifacts — which a fresh clone never does, both being
# git-ignored. Kept as defence, named as inert.
rm -rf test_tools/build
rm -rf test_tools/*.egg-info
rm -rf document_tools/build
rm -rf document_tools/*.egg-info
success "Cleaned up (preserved shared/core/ for jsonui-mcp-server)"

# Install tools
echo ""
info "Setting up tools..."

should_install() {
    # 🚫 NOT a substring match. `grep -q jui` is true for `sjui` and `kjui`, so
    # `JSONUI_TOOLS="sjui kjui"` used to install jui_tools as well — the README
    # example for "install specific tools only" installed a tool it did not
    # name. Tokenise on both separators the docs use (space and comma) and
    # compare whole names.
    [ "$TOOLS" = "all" ] && return 0
    for _t in $(echo "$TOOLS" | tr ',' ' '); do
        [ "$_t" = "$1" ] && return 0
    done
    return 1
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

# jsonui-mcp-server (Claude Code MCP). Separate repo — delegate to its own
# self-contained installer, which clones itself to ~/.jsonui-mcp-server,
# builds, and registers the `jui-tools` MCP server in ~/.claude.json. Runs
# by default (part of "all"); opt out with JSONUI_TOOLS that omits "mcp".
# Honors JSONUI_MCP_DIR / CLAUDE_JSON / JSONUI_MCP_REPO (passed through env).
if should_install "mcp"; then
    echo ""
    if ! command -v node >/dev/null 2>&1; then
        warning "Skipping MCP server (jui-tools) — Node.js required. Install later: curl -fsSL $MCP_INSTALLER_URL | bash"
    else
        info "Installing jsonui-mcp-server (Claude Code MCP)..."
        MCP_TMP="$(mktemp)"
        if curl -fsSL "$MCP_INSTALLER_URL" -o "$MCP_TMP" && [ -s "$MCP_TMP" ]; then
            # Run in a subshell so the MCP installer's own `set -e` / `cd`
            # can't abort or relocate this bootstrap.
            if (bash "$MCP_TMP"); then
                success "jsonui-mcp-server installed + registered in ~/.claude.json (restart Claude Code to activate)"
            else
                warning "MCP server install failed — retry manually: curl -fsSL $MCP_INSTALLER_URL | bash"
            fi
        else
            warning "Could not download MCP installer ($MCP_INSTALLER_URL) — skipped"
        fi
        rm -f "$MCP_TMP"
    fi
fi

# Detect shell
SHELL_NAME=$(basename "$SHELL")
case "$SHELL_NAME" in
    zsh)  SHELL_RC="$HOME/.zshrc" ;;
    bash) SHELL_RC="$HOME/.bashrc" ;;
    *)    SHELL_RC="$HOME/.profile" ;;
esac

# Generate PATH export (absolute paths — see INSTALL_DIR canonicalization above).
#
# The Python-tool launchers (jui / jsonui-doc / jsonui-test) self-inject
# sys.path, so putting their bin dir on PATH is enough to RUN them — no pip
# console script needed, and immune to pip dropping the script into a
# scripts dir that isn't on PATH (the common `--user` / PEP 668 failure).
#
# Caveat: only the core commands are pure-stdlib. `jui hotload` additionally
# imports `watchdog` + `aiohttp`, and YAML swagger input in `jui build`
# needs `pyyaml`; the `pip install -e .` step above installs those as deps.
# If that pip step was skipped/failed, the core jui commands still work via
# PATH, but `jui hotload` needs `pip install watchdog aiohttp` and YAML
# swagger input needs `pip install pyyaml` (jui halts with that guidance).
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
echo "Note: the lines above use absolute paths and put 'jui' on PATH via its"
echo "self-contained launcher — no pip console script required for core commands."
echo -e "'jui hotload' also needs: ${BLUE}pip3 install watchdog aiohttp${NC}; YAML swagger input needs ${BLUE}pip3 install pyyaml${NC} (both installed by this script's pip step when available)."
echo ""
