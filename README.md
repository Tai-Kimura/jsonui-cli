# JsonUI CLI Tools

The monorepo for the JsonUI toolchain: platform code generators, the unified
cross-platform CLI, **the attribute SSoT that defines the JsonUI language**, and
**the conformance system that proves all three renderers implement it identically**.

## Tools

| Tool | Platform | Language | Command | Description |
|------|----------|----------|---------|-------------|
| **jui_tools** | Cross-platform | Python | `jui` | Unified generator/verifier/distributor — builds all platforms, syncs API models & ViewModel protocols, normalizes layouts, generates typed attribute code and conformance fixtures |
| **sjui_tools** | iOS (SwiftUI/UIKit) | Ruby | `sjui` | CLI for SwiftJsonUI development |
| **kjui_tools** | Android (Compose; XML frozen) | Ruby | `kjui` | CLI for KotlinJsonUI development. The XML (Android Views) codegen path is maintenance-frozen — new features are Compose-only |
| **rjui_tools** | Web (React/Next.js) | Ruby | `rjui` | CLI for ReactJsonUI development (fully static codegen — no runtime package) |
| **test_tools** | Cross-platform | Python | `jsonui-test` | Test file validation, reports (JUnit/HTML), mock server, artifacts |
| **document_tools** | Cross-platform | Python | `jsonui-doc` | Spec validation, HTML/Mermaid documentation, API contract checks |

## The attribute SSoT — `shared/core/`

`shared/core/attribute_definitions.json` is the canonical definition of the
JsonUI language: every attribute's name, type, enum values, aliases,
deprecations and platform availability. Everything else derives from it:

- the Ruby validators in all three platform tools (consumed via symlink),
- typed attribute code for Swift / Kotlin / Ruby (`jui generate attr-bindings`),
- the conformance fixture suite (`jui conformance generate`),
- the `jui-tools` MCP server and the VSCode extension (vendored snapshots).

Aliases are resolved by the normalizer, never by emitters; generated files are
marked `@generated` and never hand-edited. Changing the SSoT ripples through a
defined regeneration checklist — see [dev-guide/02-ssot-shared-core.md](dev-guide/02-ssot-shared-core.md).

## Conformance — `conformance/`

A WPT-style machine proof that the three renderers agree on the SSoT:
**717 generated fixtures** (layout + test pairs, plus a control set for
environment-noise diffing) executed on **three real hosts** — iOS Simulator
(SwiftJsonUI ConformanceHost), Android emulator (KotlinJsonUI conformance-host)
and Playwright (real rjui codegen output). Visual results are compared against
dhash baselines; `jui conformance gate` renders the report and applies the same
pass/fail judgement as CI, locally.

CI runs web conformance on every push and the mobile suite weekly
(`.github/workflows/conformance-mobile.yml`). Fixtures are never hand-written —
the generator and its classification tables are the only source. Details:
[dev-guide/08-testing-conformance.md](dev-guide/08-testing-conformance.md).

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
curl -fsSL ... | JSONUI_INSTALL_DIR=/opt bash

# Custom full install path
curl -fsSL ... | JSONUI_CLI_DIR=/opt/jsonui-cli bash

# Install specific tools only.
#
# ⚠️ THE VARIABLE GOES ON `bash`, NOT IN FRONT OF `curl`. A prefix before
# `curl` sets it for curl, and the bash on the other side of the pipe never
# sees it — the installer then runs with the default (all) and installs
# everything you meant to exclude, successfully and without a word. This file
# carried the broken form until 2026-09-10; it installed the MCP server for a
# caller who had listed six tools without it.
curl -fsSL ... | JSONUI_TOOLS="sjui kjui" bash

# Or use the flag, which has no such trap:
curl -fsSL ... -o /tmp/bootstrap.sh && bash /tmp/bootstrap.sh --tools "sjui kjui"

# Available tools: sjui, kjui, rjui, jui, test, doc, mcp
# "all" (default) includes mcp — the Claude Code MCP server (jsonui-mcp-server),
# installed to ~/.jsonui-mcp-server and registered in ~/.claude.json (needs Node.js).
# Names are matched WHOLE: "sjui" no longer also selects "jui".
# The installer prints the list it resolved and where it came from, so a
# variable that did not arrive is visible in the output rather than silent.
curl -fsSL ... | JSONUI_TOOLS="test doc" bash
```

### Local Install (from cloned repo)

```bash
./install.sh
```

### Individual Tool Installation

```bash
# Ruby tools (from their directory): bundle install, then ./bin/<tool> --help
cd kjui_tools && bundle install && ./bin/kjui --help

# Python tools (from their directory): pip install -e ., then <command> --help
cd test_tools && pip install -e . && jsonui-test --help
```

## Requirements

CI-verified versions (older ones may work but are not tested):

- **Ruby** 3.3 (sjui_tools, kjui_tools, rjui_tools)
- **Python** 3.11+ (jui_tools, test_tools, document_tools)
- **Node.js** 24 (web conformance host needs ≥ 23 for native TS type stripping;
  also used by the MCP server and the hotloader clients)

## Directory Structure

```
jsonui-cli/
├── shared/core/      # ★ Attribute SSoT (attribute_definitions.json, component_metadata.json)
├── jui_tools/        # Unified Python CLI "jui" (build/verify/generate/sync/hotload/conformance)
├── sjui_tools/       # SwiftJsonUI CLI (Ruby)
├── kjui_tools/       # KotlinJsonUI CLI (Ruby)
├── rjui_tools/       # ReactJsonUI CLI (Ruby, vendored typed attribute tables)
├── test_tools/       # jsonui-test CLI (canonical home; schemas live in jsonui-test-runner)
├── document_tools/   # jsonui-doc CLI (spec docs, API contract checks)
├── conformance/      # ★ 717 generated fixtures + baselines + results + report
├── build/            # attr-codegen output staging (swift/kotlin/ruby typed tables)
├── dev-guide/        # ★ Maintainer guide (published; start at dev-guide/README.md)
├── installer/        # bootstrap.sh (curl | bash entry point)
├── install.sh        # Local installer
└── docs/             # Local-only working notes (gitignored; see docs/README.md locally)
```

## Maintainer guide

Modifying the toolchain itself? Start at
**[dev-guide/README.md](dev-guide/README.md)** — repository map, SSoT
consumption matrix, per-platform internals, release/distribution procedures and
maintenance playbooks (in Japanese).

## License

MIT License
