# JsonUI CLI Tools

A unified repository for JsonUI CLI tools across all platforms.

## Tools

| Tool | Platform | Language | Command | Description |
|------|----------|----------|---------|-------------|
| **sjui_tools** | iOS (SwiftUI/UIKit) | Ruby | `sjui` | CLI for SwiftJsonUI development |
| **kjui_tools** | Android (Compose; XML frozen) | Ruby | `kjui` | CLI for KotlinJsonUI development. The XML (Android Views) codegen path is maintenance-frozen — new features are Compose-only |
| **rjui_tools** | Web (React/Next.js) | Ruby | `rjui` | CLI for ReactJsonUI development |
| **jui_tools** | Cross-platform | Python | `jui` | Unified cross-platform generator/verifier |
| **test_tools** | Cross-platform | Python | `jsonui-test` | Test file validation and generation |
| **document_tools** | Cross-platform | Python | `jsonui-doc` | Documentation generation |

## Installation

### Remote Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/Tai-Kimura/jsonui-cli/main/installer/bootstrap.sh | bash
```

Installs to `$HOME/.jsonui-cli` by default (where jsonui-mcp-server and the
platform tools look). The installer prints absolute `export PATH=...` lines to
add to your shell rc.

Options:
```bash
# Custom base directory (jsonui-cli/ is created inside it)
JSONUI_INSTALL_DIR=/opt curl -fsSL ... | bash

# Custom full install path
JSONUI_CLI_DIR=/opt/jsonui-cli curl -fsSL ... | bash

# Install specific tools only
JSONUI_TOOLS="sjui kjui" curl -fsSL ... | bash

# Available tools: sjui, kjui, rjui, jui, test, doc, mcp
# "all" (default) includes mcp — the Claude Code MCP server (jsonui-mcp-server),
# installed to ~/.jsonui-mcp-server and registered in ~/.claude.json (needs Node.js).
JSONUI_TOOLS="test doc" curl -fsSL ... | bash
```

### Local Install (from cloned repo)

```bash
./install.sh
```

### Individual Tool Installation

#### sjui (SwiftJsonUI)
```bash
cd sjui_tools
./bin/sjui --help
```

#### kjui (KotlinJsonUI)
```bash
cd kjui_tools
bundle install
./bin/kjui --help
```

#### rjui (ReactJsonUI)
```bash
cd rjui_tools
bundle install
./bin/rjui --help
```

#### jsonui-test (Test Tools)
```bash
cd test_tools
pip install -e .
jsonui-test --help
```

#### jsonui-doc (Document Tools)
```bash
cd document_tools
pip install -e .
jsonui-doc --help
```

## Requirements

- **Ruby** 2.7.4+ (for sjui_tools, kjui_tools, rjui_tools)
- **Python** 3.10+ (for test_tools, document_tools)
- **Node.js** 16+ (for hotloader functionality)

## Directory Structure

```
jsonui-cli/
├── sjui_tools/       # SwiftJsonUI CLI
├── kjui_tools/       # KotlinJsonUI CLI
├── rjui_tools/       # ReactJsonUI CLI
├── test_tools/       # Test file validation and generation
├── document_tools/   # Documentation generation
│   └── jsonui_doc_cli/
│       ├── test_doc/   # Test documentation
│       └── spec_doc/   # Specification documentation
├── shared/           # Shared modules
│   ├── core/         # Common definitions (attribute_definitions.json)
│   └── validation/   # Shared validation module for Python tools
├── installer/        # Bootstrap installer
├── install.sh        # Local installer
└── README.md
```

## License

MIT License
