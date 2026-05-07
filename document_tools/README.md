# JsonUI Document Tools

CLI tool for generating documentation from JsonUI projects.

## Installation

```bash
pip install -e .
```

## Modules

### test_doc - Test Documentation

Generate documentation from JsonUI test files (`.test.json`).

### spec_doc - Specification Documentation

Generate documentation from screen specification files (`.spec.json`) and component specification files (`.component.json`).

### figma - Figma Integration

Fetch Figma file data via API and convert to HTML documentation with sidebar navigation.

## Usage

### Initialization

#### Create Screen Specification Template

```bash
# Create a new screen specification file
jsonui-doc init spec Login
jsonui-doc init spec UserProfile -d "User Profile Screen" -o docs/specs
```

#### Create Component Specification Template

```bash
# Create a new component specification file
jsonui-doc init component UserCard -c card
jsonui-doc init component SearchBar -c input -d "Search Bar" -o docs/components
```

### Validation

#### Validate Screen Specification

```bash
jsonui-doc validate spec docs/specs/Login.spec.json
```

#### Validate Component Specification

```bash
jsonui-doc validate component docs/components/UserCard.component.json
```

### Generation

#### Generate HTML Documentation

```bash
# Generate HTML for all test files in a directory
jsonui-doc generate html tests/ -o docs/html

# With additional docs directories (API specs, etc.)
jsonui-doc generate html tests/ -o docs/html -d docs/api -d docs/db

# With Figma directory
jsonui-doc generate html tests/ -o docs/html -fig docs/figma
```

The `generate html` command auto-detects and includes:
- Test files (`.test.json`) from `screens/` and `flows/`
- Screen specs (`.spec.json`) from `specs/` directory
- Component specs (`.component.json`) from `components/` directory
- OpenAPI/Swagger files from `-d` directories
- Markdown files (`.md`) from `-d` directories
- Figma JSON files from `figma/` directory (auto-converted with sidebar navigation)

#### Generate Mermaid Diagram

```bash
# Output mermaid code to stdout
jsonui-doc generate mermaid tests/

# Generate HTML with embedded diagram
jsonui-doc generate mermaid tests/ -o flow_diagram.html
```

#### Generate Test Adapter

```bash
# Generate iOS adapter
jsonui-doc generate adapter ios -o MyApp/UITests -n MyApp

# Generate Android adapter
jsonui-doc generate adapter android -o app/src/androidTest -n MyApp

# Generate Web adapter
jsonui-doc generate adapter web -o tests/e2e -n MyApp
```

#### Generate Single File Documentation

```bash
# Generate markdown documentation
jsonui-doc generate doc -f tests/screens/login.test.json

# Generate HTML documentation
jsonui-doc generate doc -f tests/screens/login.test.json -o login.html --format html
```

#### Generate Screen Specification Documentation

```bash
# Single file
jsonui-doc generate spec docs/specs/Login.spec.json -o login.html --format html

# Batch mode (all .spec.json files in directory)
jsonui-doc generate spec docs/specs/ -o docs/html
```

#### Generate Component Documentation

```bash
# Single file
jsonui-doc generate component docs/components/UserCard.component.json -o usercard.html --format html

# Batch mode (all .component.json files in directory)
jsonui-doc generate component docs/components/ -o docs/html
```

### Figma Integration

#### Fetch Figma File

```bash
# Fetch by file key
jsonui-doc figma fetch FILE_KEY

# Fetch by URL (auto-extracts file key and node-id)
jsonui-doc figma fetch --url "https://www.figma.com/design/FILE_KEY/..."

# Interactive page selection
jsonui-doc figma fetch FILE_KEY --pages

# Fetch specific nodes
jsonui-doc figma fetch FILE_KEY --node-ids 0:1 1:2

# Custom output path and depth limit
jsonui-doc figma fetch FILE_KEY -o output.json --depth 3

# Fetch with images (fills + vector renders)
jsonui-doc figma fetch FILE_KEY --images
jsonui-doc figma fetch --url "https://www.figma.com/design/FILE_KEY/..." --images

# Throttle image downloads based on Figma plan
jsonui-doc figma fetch FILE_KEY --images --plan pro
jsonui-doc figma fetch FILE_KEY --images --plan enterprise
```

Options:
- `--url`: Figma URL (auto-extracts file key and node-id from URL)
- `-p, --pages`: Interactive page selection mode
- `--node-ids`: Fetch specific node IDs
- `--images`: Also download images (fills and vector renders) after fetching JSON
- `--plan`: Figma plan for API rate limit throttling (`starter`/`pro`/`org`/`enterprise`, default: `starter`)
- `-t, --token`: Figma API token (default: `FIGMA_TOKEN` env var)
- `-o, --output`: Output path (default: `figma/{file_key}.json`)
- `--depth`: Limit response tree depth

#### Download Images for Existing JSON

```bash
# Download images for a previously fetched Figma JSON file
jsonui-doc figma images figma/FILE_KEY.json

# With explicit file key
jsonui-doc figma images figma/FILE_KEY.json -k FILE_KEY

# Throttle based on Figma plan
jsonui-doc figma images figma/FILE_KEY.json --plan pro
```

Options:
- `-k, --file-key`: Figma file key (default: inferred from filename)
- `--plan`: Figma plan for API rate limit throttling (`starter`/`pro`/`org`/`enterprise`, default: `starter`)
- `-t, --token`: Figma API token (default: `FIGMA_TOKEN` env var)

#### Rate Limit Throttling

The `--plan` option controls how fast image download requests are sent to avoid Figma API rate limits (HTTP 429):

| Plan | Tier 1 Limit | Request Interval |
|------|-------------|-----------------|
| `starter` (default) | 10 req/min | ~12s |
| `pro` | 15 req/min | ~8s |
| `org` | 20 req/min | ~6s |
| `enterprise` | Unlimited | No throttle |

Throttling uses 50% of each plan's limit to leave headroom and avoid 429s. If a 429 response is received, the CLI automatically waits based on the `Retry-After` header and retries.

Images are saved to `figma/images/` with a manifest file (`figma/images.json`):
```
figma/
  {file_key}.json       # Figma API JSON
  images.json           # Image manifest (imageRef/nodeId → local path)
  images/
    fills/              # IMAGE fill images (photos, backgrounds)
    renders/            # Rendered nodes (icons, vectors)
```

#### Figma HTML Conversion

Figma JSON files placed in the `figma/` directory are automatically converted to HTML with sidebar navigation when running `generate html`:

```bash
# 1. Fetch Figma data with images
jsonui-doc figma fetch FILE_KEY --images

# 2. Generate HTML (auto-includes figma/ files and images)
jsonui-doc generate html tests/ -o html/
```

The generated `html/figma/` directory contains individual screen pages with the shared sidebar navigation. If images were downloaded, they are automatically included as `<img>` tags in the generated HTML.

## Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `init spec` | `i spec` | Create screen specification template |
| `init component` | `i component` | Create component specification template |
| `validate spec` | `v spec` | Validate screen specification JSON file |
| `validate component` | `v component` | Validate component specification JSON file |
| `generate html` | `g html` | Generate HTML directory with index from test files |
| `generate mermaid` | `g mermaid` | Generate Mermaid flow diagram from test files |
| `generate adapter` | `g adapter` | Generate platform-specific test adapter |
| `generate doc` | `g doc` | Generate single file documentation from test file |
| `generate spec` | `g spec` | Generate HTML/Markdown from screen specification |
| `generate component` | `g component` | Generate HTML/Markdown from component specification |
| `figma fetch` | `f fetch` | Fetch Figma file JSON via API |
| `figma images` | `f images` | Download images for existing Figma JSON file |

## Project Structure

```
document_tools/
├── jsonui_doc_cli/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point
│   ├── validator.py        # Re-export from validation module
│   ├── test_doc/           # Test documentation generation
│   │   ├── generator.py    # HTML directory generator (auto-discovers figma/)
│   │   ├── adapter/        # Platform-specific test adapters
│   │   ├── html/           # HTML generators (screen, flow, index, sidebar, etc.)
│   │   ├── markdown/       # Markdown generators
│   │   └── mermaid/        # Mermaid diagram generators
│   ├── spec_doc/           # Specification documentation
│   │   ├── screen_spec_schema.py
│   │   ├── component_spec_schema.py
│   │   ├── validator.py
│   │   ├── html_generator.py
│   │   ├── markdown_generator.py
│   │   └── template.py     # Spec/component file templates
│   └── figma/              # Figma integration
│       ├── api_client.py   # Figma REST API client (file, nodes, images, renders)
│       ├── image_fetcher.py # Image collection, download, and manifest management
│       └── figma_to_html.py # Figma JSON to HTML converter (with sidebar and images)
├── pyproject.toml
└── README.md
```
