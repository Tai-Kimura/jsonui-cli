"""Generator for JsonUI test documentation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..validator import TestValidator, ValidationResult
from ..spec_doc import SpecValidator, generate_spec_html, generate_component_html
from ..spec_doc.rules_config import load_rules_for_path
from .html import (
    generate_screen_html,
    generate_flow_html,
    generate_index_html,
    generate_document_html,
    is_swagger_file,
    parse_swagger_file,
    generate_swagger_html,
    has_api_paths,
    generate_schema_html,
    generate_erd_html,
    generate_markdown_html,
)
from .html.sidebar import escape_html
from .markdown import generate_markdown, generate_schema_markdown
from .mermaid import generate_mermaid_html


def _validator_for(spec_file: Path) -> SpecValidator:
    """Build a :class:`SpecValidator` whose custom rules are discovered from
    *spec_file*'s own location.

    The doc generators validate many files in one run. A single reused
    validator freezes its custom rules to whatever the FIRST validated file
    resolved — ``SpecValidator`` only auto-discovers ``.jsonui-doc-rules.json``
    while its rules are still empty (``validate_file``'s lazy load). So a
    later file whose nearest config differs from the first one's is validated
    against the wrong rule set, making the pre-generate / page-generate passes
    falsely ``SKIP`` custom component types that the standalone ``validate``
    path (which loads rules per file) accepts. Constructing a fresh validator
    per file restores that per-file discovery. Bug:
    doc-pregenerate-component-validation-ignores-custom-rules.
    """
    return SpecValidator(custom_rules=load_rules_for_path(spec_file))


class DocumentGenerator:
    """Generates human-readable documentation from test files."""

    def __init__(self):
        self.validator = TestValidator()
        self._test_file_path: Path | None = None
        self._all_tests_nav: dict | None = None  # {'screens': [...], 'flows': [...]}
        self._current_test_path: str | None = None  # Current test's relative HTML path

    def _resolve_description(self, case: dict) -> dict | str:
        """
        Resolve the description for a test case.

        If descriptionFile is specified, reads and parses the JSON file.
        Otherwise, returns the inline description.

        Args:
            case: Test case dictionary

        Returns:
            Description dict (from JSON file) or string (inline description)
        """
        # Check for external description file
        if "descriptionFile" in case and self._test_file_path:
            desc_file_path = case["descriptionFile"]
            # Resolve relative to test file location
            if not Path(desc_file_path).is_absolute():
                desc_file_path = self._test_file_path.parent / desc_file_path

            desc_path = Path(desc_file_path)
            if desc_path.exists():
                try:
                    with open(desc_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    return f"[Error reading {case['descriptionFile']}: {e}]"
            else:
                return f"[Description file not found: {case['descriptionFile']}]"

        # Fall back to inline description
        return case.get("description", "")

    def _resolve_block_description(self, block_step: dict) -> dict | str:
        """
        Resolve the description for a block step.

        If descriptionFile is specified, reads and parses the JSON file.
        Otherwise, returns the inline description.

        Args:
            block_step: Block step dictionary

        Returns:
            Description dict (from JSON file) or string (inline description)
        """
        # Check for external description file
        if "descriptionFile" in block_step and self._test_file_path:
            desc_file_path = block_step["descriptionFile"]
            # Resolve relative to test file location
            if not Path(desc_file_path).is_absolute():
                desc_file_path = self._test_file_path.parent / desc_file_path

            desc_path = Path(desc_file_path)
            if desc_path.exists():
                try:
                    with open(desc_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    return f"[Error reading {block_step['descriptionFile']}: {e}]"
            else:
                return f"[Description file not found: {block_step['descriptionFile']}]"

        # Fall back to inline description
        return block_step.get("description", "")

    def generate(self, file_path: Path, output_path: Path | None = None, format: str = "markdown") -> str | None:
        """
        Generate documentation from a test file.

        Args:
            file_path: Path to the .test.json file
            output_path: Optional output path (if None, returns string)
            format: Output format ("markdown" or "html")

        Returns:
            Generated content as string if output_path is None
        """
        # Store file path for resolving relative description files
        self._test_file_path = Path(file_path).resolve()

        # First validate
        result = self.validator.validate_file(file_path)

        if not result.is_valid:
            raise ValueError(f"Validation failed for {file_path}: {result.error_count} errors")

        # Generate based on format
        if format == "markdown":
            content = self._generate_markdown(result)
        elif format == "html":
            content = self._generate_html(result)
        else:
            raise ValueError(f"Unsupported format: {format}")

        # Write or return
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return None
        else:
            return content

    def _generate_markdown(self, result: ValidationResult) -> str:
        """Generate Markdown documentation."""
        return generate_markdown(
            result.test_data,
            result.file_path,
            self._resolve_description,
            self._format_step_details
        )

    def _format_description_html(self, desc: dict | str) -> list[str]:
        """Format description (dict or string) for HTML output."""
        parts = []
        if isinstance(desc, dict):
            # Description from JSON file
            if desc.get("summary"):
                escaped = escape_html(desc["summary"])
                parts.append(f"  <p class='summary'>{escaped}</p>")
            if desc.get("preconditions"):
                parts.append("  <div class='desc-section'>")
                parts.append("    <strong>Preconditions:</strong>")
                parts.append("    <ul>")
                for item in desc["preconditions"]:
                    escaped = escape_html(item)
                    parts.append(f"      <li>{escaped}</li>")
                parts.append("    </ul>")
                parts.append("  </div>")
            if desc.get("test_procedure"):
                parts.append("  <div class='desc-section'>")
                parts.append("    <strong>Test Procedure:</strong>")
                parts.append("    <ol>")
                for item in desc["test_procedure"]:
                    escaped = escape_html(item)
                    parts.append(f"      <li>{escaped}</li>")
                parts.append("    </ol>")
                parts.append("  </div>")
            if desc.get("expected_results"):
                parts.append("  <div class='desc-section'>")
                parts.append("    <strong>Expected Results:</strong>")
                parts.append("    <ul>")
                for item in desc["expected_results"]:
                    escaped = escape_html(item)
                    parts.append(f"      <li>{escaped}</li>")
                parts.append("    </ul>")
                parts.append("  </div>")
            if desc.get("notes"):
                escaped = escape_html(desc["notes"])
                parts.append(f"  <p class='notes'><strong>Notes:</strong> {escaped}</p>")
        elif desc:
            # Inline description string
            escaped = escape_html(desc)
            parts.append(f"  <p>{escaped}</p>")
        return parts

    def _format_block_description_html(self, desc: dict | str) -> list[str]:
        """Format block description for HTML output (with block-specific indentation)."""
        parts = []
        if isinstance(desc, dict):
            if desc.get("preconditions"):
                parts.append("        <div class='ref-desc-section'>")
                parts.append("          <strong>Preconditions:</strong>")
                parts.append("          <ul>")
                for item in desc["preconditions"]:
                    parts.append(f"            <li>{escape_html(item)}</li>")
                parts.append("          </ul>")
                parts.append("        </div>")
            if desc.get("test_procedure"):
                parts.append("        <div class='ref-desc-section'>")
                parts.append("          <strong>Test Procedure:</strong>")
                parts.append("          <ol>")
                for item in desc["test_procedure"]:
                    parts.append(f"            <li>{escape_html(item)}</li>")
                parts.append("          </ol>")
                parts.append("        </div>")
            if desc.get("expected_results"):
                parts.append("        <div class='ref-desc-section'>")
                parts.append("          <strong>Expected Results:</strong>")
                parts.append("          <ul>")
                for item in desc["expected_results"]:
                    parts.append(f"            <li>{escape_html(item)}</li>")
                parts.append("          </ul>")
                parts.append("        </div>")
            if desc.get("notes"):
                parts.append(f"        <p class='ref-notes'><strong>Notes:</strong> {escape_html(desc['notes'])}</p>")
        return parts

    def _generate_html(self, result: ValidationResult) -> str:
        """Generate HTML documentation."""
        data = result.test_data
        test_type = data.get("type", "screen")

        # Route to appropriate generator based on test type
        if test_type == "flow":
            return generate_flow_html(
                data,
                result.file_path,
                self._format_step_details,
                self._resolve_description_for_ref,
                self._get_ref_case_label,
                self._format_description_html_for_ref,
                self._render_referenced_cases,
                self._resolve_block_description,
                self._format_block_description_html,
                self._all_tests_nav,
                self._current_test_path
            )
        else:
            return generate_screen_html(
                data,
                result.file_path,
                self._resolve_description,
                self._format_description_html,
                self._format_step_details,
                self._all_tests_nav,
                self._current_test_path
            )

    def _find_tests_root(self) -> Path:
        """Find the tests root directory (parent of flows/ or screens/)."""
        if not self._test_file_path:
            return Path(".")

        base_dir = self._test_file_path.parent

        # Check if we're in flows/ or screens/ directly
        if base_dir.name == "flows" or base_dir.name == "screens":
            return base_dir.parent

        # Check if we're in a subdirectory of flows/ or screens/
        if base_dir.parent.name == "flows" or base_dir.parent.name == "screens":
            return base_dir.parent.parent

        return base_dir.parent

    def _render_referenced_cases(self, file_ref: str, case_name: str | None, cases: list | None) -> list[str]:
        """
        Load referenced test file and render its cases.

        Args:
            file_ref: File reference path (e.g., "screens/login")
            case_name: Single case name if specified
            cases: List of case names if specified

        Returns:
            List of HTML strings for the referenced cases
        """
        if not self._test_file_path:
            return []

        # Find tests root directory
        base_dir = self._test_file_path.parent
        tests_root = self._find_tests_root()

        candidates = [
            # screens/{file_ref}/{file_ref}.test.json (subdirectory structure)
            tests_root / "screens" / file_ref / f"{file_ref}.test.json",
            tests_root / "screens" / file_ref / f"{file_ref}.json",
            # screens/{file_ref}.test.json (flat structure)
            tests_root / "screens" / f"{file_ref}.test.json",
            tests_root / "screens" / f"{file_ref}.json",
            # flows/{file_ref}/{file_ref}.test.json (subdirectory structure)
            tests_root / "flows" / file_ref / f"{file_ref}.test.json",
            # flows/{file_ref}.test.json (flat structure)
            tests_root / "flows" / f"{file_ref}.test.json",
            # Same directory as current test
            base_dir / f"{file_ref}.test.json",
            base_dir / f"{file_ref}.json",
            base_dir / file_ref,
        ]

        ref_file = None
        for candidate in candidates:
            if candidate.exists():
                ref_file = candidate
                break

        if not ref_file:
            return [f"        <div class='step-detail warning'><em>Referenced file not found: {escape_html(file_ref)}</em></div>"]

        try:
            with open(ref_file, 'r', encoding='utf-8') as f:
                ref_data = json.load(f)
        except Exception as e:
            return [f"        <div class='step-detail warning'><em>Error reading file: {escape_html(str(e))}</em></div>"]

        # Get cases from referenced file
        ref_cases = ref_data.get("cases", [])
        if not ref_cases:
            return []

        # Filter cases based on case_name or cases parameter
        if case_name:
            # Single case specified
            ref_cases = [c for c in ref_cases if c.get("name") == case_name]
        elif cases:
            # Multiple cases specified
            ref_cases = [c for c in ref_cases if c.get("name") in cases]
        # else: all cases

        if not ref_cases:
            return []

        parts = []
        parts.append("        <div class='referenced-cases'>")
        parts.append("          <div class='ref-cases-header'>Referenced Test Cases:</div>")

        for i, case in enumerate(ref_cases, 1):
            c_name = case.get("name", f"Case {i}")
            steps = case.get("steps", [])

            # Resolve description (same logic as screen test)
            case_desc = self._resolve_description_for_ref(case, ref_file)
            if isinstance(case_desc, dict) and case_desc.get("summary"):
                c_display = case_desc["summary"]
            else:
                c_display = case.get("description") or c_name

            parts.append(f"          <div class='ref-case'>")
            parts.append(f"            <div class='ref-case-title'>{i}. {escape_html(c_display)}</div>")
            parts.append(f"            <div class='ref-case-name'><code>{escape_html(c_name)}</code></div>")

            # Show description details (same as screen test)
            parts.extend(self._format_description_html_for_ref(case_desc))

            if steps:
                parts.append("            <table class='ref-steps-table'>")
                parts.append("              <tr><th>#</th><th>Type</th><th>Action/Assert</th><th>Target</th><th>Details</th></tr>")

                for j, step in enumerate(steps, 1):
                    step_type = "action" if "action" in step else "assert"
                    type_label = "Action" if step_type == "action" else "Assert"
                    action_name = step.get("action") or step.get("assert", "?")
                    target = step.get("id") or ", ".join(step.get("ids", [])) or "-"
                    details = self._format_step_details(step)
                    parts.append(f"              <tr><td>{j}</td><td><span class='{step_type}'>{type_label}</span></td><td><code>{action_name}</code></td><td><code>{target}</code></td><td>{details}</td></tr>")

                parts.append("            </table>")

            parts.append("          </div>")

        parts.append("        </div>")

        return parts

    def _resolve_description_for_ref(self, case: dict, ref_file: Path) -> dict | str:
        """Resolve description for a referenced test case."""
        if "descriptionFile" in case:
            desc_file_path = case["descriptionFile"]
            if not Path(desc_file_path).is_absolute():
                desc_file_path = ref_file.parent / desc_file_path

            desc_path = Path(desc_file_path)
            if desc_path.exists():
                try:
                    with open(desc_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    pass
        return case.get("description", "")

    def _get_ref_case_label(self, file_ref: str, case_name: str | None, cases_list: list | None) -> str:
        """
        Get sidebar label for a file reference step.

        Returns the case description if single case, or a summary for multiple cases.
        """
        if not self._test_file_path:
            return file_ref.split("/")[-1] if "/" in file_ref else file_ref

        # Find tests root directory and resolve file
        base_dir = self._test_file_path.parent
        tests_root = self._find_tests_root()

        candidates = [
            # screens/{file_ref}/{file_ref}.test.json (subdirectory structure)
            tests_root / "screens" / file_ref / f"{file_ref}.test.json",
            tests_root / "screens" / file_ref / f"{file_ref}.json",
            # screens/{file_ref}.test.json (flat structure)
            tests_root / "screens" / f"{file_ref}.test.json",
            tests_root / "screens" / f"{file_ref}.json",
            # flows/{file_ref}/{file_ref}.test.json (subdirectory structure)
            tests_root / "flows" / file_ref / f"{file_ref}.test.json",
            # flows/{file_ref}.test.json (flat structure)
            tests_root / "flows" / f"{file_ref}.test.json",
            # Same directory as current test
            base_dir / f"{file_ref}.test.json",
            base_dir / f"{file_ref}.json",
            base_dir / file_ref,
        ]

        ref_file = None
        for candidate in candidates:
            if candidate.exists():
                ref_file = candidate
                break

        if not ref_file:
            return file_ref.split("/")[-1] if "/" in file_ref else file_ref

        try:
            with open(ref_file, 'r', encoding='utf-8') as f:
                ref_data = json.load(f)
        except Exception:
            return file_ref.split("/")[-1] if "/" in file_ref else file_ref

        ref_cases = ref_data.get("cases", [])
        if not ref_cases:
            return file_ref.split("/")[-1] if "/" in file_ref else file_ref

        # Single case specified
        if case_name:
            for case in ref_cases:
                if case.get("name") == case_name:
                    # Try to get description
                    desc = self._resolve_description_for_ref(case, ref_file)
                    if isinstance(desc, dict) and desc.get("summary"):
                        return desc["summary"]
                    elif case.get("description"):
                        return case["description"]
                    else:
                        return case_name
            return case_name

        # Multiple cases specified
        if cases_list and len(cases_list) > 0:
            # Get the first case's description
            first_case_name = cases_list[0]
            for case in ref_cases:
                if case.get("name") == first_case_name:
                    desc = self._resolve_description_for_ref(case, ref_file)
                    if isinstance(desc, dict) and desc.get("summary"):
                        label = desc["summary"]
                    elif case.get("description"):
                        label = case["description"]
                    else:
                        label = first_case_name

                    if len(cases_list) > 1:
                        return f"{label} (+{len(cases_list) - 1})"
                    return label
            return f"{first_case_name} (+{len(cases_list) - 1})" if len(cases_list) > 1 else first_case_name

        # All cases (no case/cases specified)
        metadata = ref_data.get("metadata", {})
        screen_name = metadata.get("name", "")
        if screen_name:
            return f"{screen_name} (all cases)"
        return f"{file_ref.split('/')[-1]} (all cases)"

    def _format_description_html_for_ref(self, desc: dict | str) -> list[str]:
        """Format description for referenced case (indented for nested display)."""
        parts = []
        if isinstance(desc, dict):
            if desc.get("preconditions"):
                parts.append("            <div class='ref-desc-section'>")
                parts.append("              <strong>Preconditions:</strong>")
                parts.append("              <ul>")
                for item in desc["preconditions"]:
                    parts.append(f"                <li>{escape_html(item)}</li>")
                parts.append("              </ul>")
                parts.append("            </div>")
            if desc.get("test_procedure"):
                parts.append("            <div class='ref-desc-section'>")
                parts.append("              <strong>Test Procedure:</strong>")
                parts.append("              <ol>")
                for item in desc["test_procedure"]:
                    parts.append(f"                <li>{escape_html(item)}</li>")
                parts.append("              </ol>")
                parts.append("            </div>")
            if desc.get("expected_results"):
                parts.append("            <div class='ref-desc-section'>")
                parts.append("              <strong>Expected Results:</strong>")
                parts.append("              <ul>")
                for item in desc["expected_results"]:
                    parts.append(f"                <li>{escape_html(item)}</li>")
                parts.append("              </ul>")
                parts.append("            </div>")
            if desc.get("notes"):
                parts.append(f"            <p class='ref-notes'><strong>Notes:</strong> {escape_html(desc['notes'])}</p>")
        return parts

    def _format_step_details(self, step: dict) -> str:
        """Format step details for display."""
        details = []

        if "value" in step:
            details.append(f"value: \"{step['value']}\"")
        if "direction" in step:
            details.append(f"direction: {step['direction']}")
        if "timeout" in step:
            details.append(f"timeout: {step['timeout']}ms")
        if "ms" in step:
            details.append(f"wait: {step['ms']}ms")
        if "duration" in step:
            details.append(f"duration: {step['duration']}ms")
        if "equals" in step:
            details.append(f"equals: \"{step['equals']}\"")
        if "contains" in step:
            details.append(f"contains: \"{step['contains']}\"")
        if "name" in step and step.get("action") == "screenshot":
            details.append(f"name: \"{step['name']}\"")

        return ", ".join(details) if details else "-"


def generate_schema_reference(output_path: Path | None = None, format: str = "markdown") -> str | None:
    """
    Generate a reference document for the test schema.

    Args:
        output_path: Optional output path
        format: Output format ("markdown" or "html")

    Returns:
        Generated content as string if output_path is None
    """
    if format == "markdown":
        content = generate_schema_markdown()
    else:
        raise ValueError(f"Unsupported format: {format}")

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return None
    else:
        return content


def _resolve_layouts_dir_for_spec(
    spec_file: Path, override: Path | None = None
) -> Path | None:
    """Return the layouts directory for a given spec file.

    If *override* is given, returns it directly. Otherwise walks up
    from *spec_file* looking for ``jui.config.json`` and resolves
    ``layouts_directory`` relative to it. Returns ``None`` when no
    config is found or the setting is missing.
    """
    if override is not None:
        return override
    import json as _json
    for parent in spec_file.parents:
        config = parent / "jui.config.json"
        if not config.exists():
            continue
        try:
            data = _json.loads(config.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        rel = data.get("layouts_directory")
        if rel:
            return (parent / rel).resolve()
        return None
    return None


def generate_html_directory(
    input_dir: Path,
    output_dir: Path,
    title: str = "JsonUI Test Documentation",
    docs_dirs: list[Path] | None = None,
    figma_dir: Path | None = None,
    apps: list[dict] | None = None,
    layouts_dir: Path | None = None,
) -> list[dict]:
    """
    Generate HTML documentation for all test files in a directory.

    Creates individual HTML files for each test and an index.html with links.
    Automatically discovers and processes:
    - docs/screens/json/*.spec.json -> docs/screens/html/ and docs/screens/md/
    - docs/components/json/*.component.json -> docs/components/html/ and docs/components/md/
    - docs/api/*.json (Swagger/OpenAPI files)
    - docs/db/*.json (DB schema files)

    Args:
        input_dir: Directory containing .test.json files
        output_dir: Directory to output HTML files
        title: Title for the index page
        docs_dirs: Optional list of additional directories containing OpenAPI/Swagger files
        figma_dir: Optional directory containing Figma JSON files (overrides auto-detection)

    Returns:
        List of generated file info dicts with 'name', 'path', 'type', 'cases'
    """
    generator = DocumentGenerator()
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    # Auto-discover docs directories relative to input_dir
    # Look for standard docs structure: docs/screens/json, docs/components/json, docs/api, docs/db
    auto_docs_dirs = []
    docs_base = input_path.parent / "docs" if input_path.name == "tests" else input_path / "docs"
    if not docs_base.exists():
        docs_base = input_path.parent / "docs"

    # Add standard docs directories if they exist
    for subdir in ["api", "db"]:
        candidate = docs_base / subdir
        if candidate.exists():
            auto_docs_dirs.append(candidate)

    # Merge with explicitly provided docs_dirs
    all_docs_dirs = list(docs_dirs or []) + auto_docs_dirs
    # Remove duplicates while preserving order
    seen = set()
    unique_docs_dirs = []
    for d in all_docs_dirs:
        d_resolved = Path(d).resolve()
        if d_resolved not in seen:
            seen.add(d_resolved)
            unique_docs_dirs.append(d)

    # Pre-generate spec and component documentation (HTML and MD)
    spec_json_dir = docs_base / "screens" / "json"
    component_json_dir = docs_base / "components" / "json"

    if spec_json_dir.exists() or component_json_dir.exists():
        print("Pre-generating specification documentation...")
        _pre_generate_spec_docs(docs_base, layouts_dir=layouts_dir)

    # Collect all test files
    test_files = list(input_path.rglob("*.test.json"))

    if not test_files:
        raise ValueError(f"No .test.json files found in {input_dir}")

    generated_files = []

    # First pass: collect all file info
    file_infos = []
    for test_file in sorted(test_files):
        try:
            result = generator.validator.validate_file(test_file)
            if not result.is_valid:
                print(f"  Skipping {test_file} (validation errors)")
                continue

            test_type = result.test_data.get('type', 'unknown')
            if test_type == 'screen':
                subdir = 'screens'
            elif test_type == 'flow':
                subdir = 'flows'
            else:
                subdir = 'other'

            rel_path = test_file.relative_to(input_path)
            html_filename = rel_path.with_suffix('.html').name
            html_rel_path = Path(subdir) / html_filename

            metadata = result.test_data.get('metadata', {})
            cases = result.test_data.get('cases', [])
            steps = result.test_data.get('steps', [])
            source = result.test_data.get('source', {})

            file_infos.append({
                'test_file': test_file,
                'result': result,
                'name': metadata.get('name', test_file.stem),
                'description': metadata.get('description', ''),
                'path': html_rel_path,
                'type': test_type,
                'case_count': len(cases) if cases else 0,
                'step_count': len(steps) if steps else sum(len(c.get('steps', [])) for c in cases),
                'platform': result.test_data.get('platform', 'all'),
                'document': source.get('document'),
            })
        except Exception as e:
            print(f"  Error processing {test_file}: {e}")

    # Build documents list from file_infos that have document paths
    document_files = []
    for f in file_infos:
        if f.get('document'):
            document_files.append({
                'name': f['name'],
                'path': f['document'],  # Path to document page
            })

    # Find and process Swagger/OpenAPI files from docs_dirs
    # Group by directory name for separate categories
    api_doc_categories = {}  # category_name -> list of api_doc_files
    all_api_doc_files = []

    if unique_docs_dirs:
        for docs_dir in unique_docs_dirs:
            docs_path = Path(docs_dir)
            if not docs_path.exists():
                continue

            # Use directory name as category (e.g., "api", "db")
            category_name = docs_path.name

            used_html_paths: set[str] = set()
            for json_file in sorted(docs_path.rglob("*.json")):
                if is_swagger_file(json_file):
                    swagger_data = parse_swagger_file(json_file)
                    if swagger_data:
                        info = swagger_data.get('info', {})
                        api_name = info.get('title', json_file.stem)
                        api_desc = info.get('description', '')
                        # Track subdirectory relative to the docs_path
                        rel_parent = json_file.parent.relative_to(docs_path)
                        subdir = str(rel_parent) if str(rel_parent) != '.' else ''

                        # Multi-database layout (docs/db/{db_name}/*.json):
                        # the first-level directory under docs/db is a
                        # database name — it becomes its own category with
                        # its own output directory and per-DB ERD.
                        # Flat docs/db/*.json stays the single "db" category
                        # (existing single-DB projects are unchanged).
                        if category_name == 'db' and subdir:
                            db_name = rel_parent.parts[0]
                            category = f"db/{db_name}"
                            nav_subdir = '/'.join(rel_parent.parts[1:])
                            html_rel_path = f"db/{db_name}/{json_file.stem}.html"
                        else:
                            category = category_name
                            nav_subdir = subdir
                            html_rel_path = f"{category_name}/{json_file.stem}.html"

                        # Collision guard: two source files must never
                        # silently overwrite one output page (same stem in
                        # different subdirs used to do exactly that).
                        if html_rel_path in used_html_paths:
                            safe = nav_subdir.replace('/', '_') or 'dup'
                            html_rel_path = (
                                f"{category}/{safe}_{json_file.stem}.html"
                            )
                            print(
                                f"  Warning: output name collision for "
                                f"{json_file} — writing {html_rel_path}"
                            )
                        used_html_paths.add(html_rel_path)

                        doc_info = {
                            'name': api_name,
                            'description': api_desc[:100] + '...' if len(api_desc) > 100 else api_desc,
                            'path': html_rel_path,
                            'source_file': json_file,
                            'swagger_data': swagger_data,
                            'category': category,
                            'subdir': nav_subdir,
                        }
                        api_doc_categories.setdefault(category, []).append(doc_info)
                        all_api_doc_files.append(doc_info)

    # Discover contract-check reports (.check-report.json written by
    # `jsonui-doc check`). Pure rendering: reports are optional, and their
    # absence changes nothing (doc-contract-check plan 01 §4).
    check_report_pages = _discover_check_reports(
        unique_docs_dirs, api_doc_categories)

    # Build navigation data for sidebar
    all_tests_nav = {
        'screens': [{'name': f['name'], 'path': str(f['path'])} for f in file_infos if f['type'] == 'screen'],
        'flows': [{'name': f['name'], 'path': str(f['path'])} for f in file_infos if f['type'] == 'flow'],
        'documents': document_files,
        'api_docs': [{'name': d['name'], 'path': d['path'], 'subdir': d.get('subdir', '')} for d in all_api_doc_files],
        'api_doc_categories': {k: [{'name': d['name'], 'path': d['path'], 'subdir': d.get('subdir', '')} for d in v] for k, v in api_doc_categories.items()},
    }

    # Second pass: generate HTML with navigation
    for file_info in file_infos:
        try:
            test_file = file_info['test_file']
            result = file_info['result']
            html_rel_path = file_info['path']

            # Create subdirectory
            html_path = output_path / html_rel_path
            html_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate HTML with navigation
            generator._test_file_path = test_file.resolve()
            generator._all_tests_nav = all_tests_nav
            generator._current_test_path = str(html_rel_path)
            content = generator._generate_html(result)

            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # Add to generated files (without internal fields)
            generated_files.append({
                'name': file_info['name'],
                'description': file_info['description'],
                'path': html_rel_path,
                'type': file_info['type'],
                'case_count': file_info['case_count'],
                'step_count': file_info['step_count'],
                'platform': file_info['platform'],
                'document': file_info.get('document'),
            })

            print(f"  Generated: {html_path}")

        except Exception as e:
            print(f"  Error processing {file_info['test_file']}: {e}")

    # Generate Mermaid diagram if there are flow files
    mermaid_generated = False
    flow_files_exist = any(f['type'] == 'flow' for f in generated_files)
    if flow_files_exist:
        try:
            flows_dir = input_path / "flows" if (input_path / "flows").exists() else input_path
            screens_dir = input_path / "screens" if (input_path / "screens").exists() else flows_dir.parent / "screens"
            mermaid_output = output_path / "diagram.html"
            diagram = generate_mermaid_html(
                flows_dir, mermaid_output, "Flow Diagram", screens_dir, layouts_dir
            )
            # An empty result means no flow produced a screen — link nothing
            # rather than publishing a page the tab script cannot render.
            mermaid_generated = bool(diagram)
            if mermaid_generated:
                print(f"  Generated: {mermaid_output}")
            else:
                print("  Skipped: flow diagram has no screens")
        except Exception as e:
            print(f"  Warning: Could not generate Mermaid diagram: {e}")

    # Generate index.html
    generate_index_html(output_path, generated_files, title, mermaid_generated, document_files, api_doc_categories)

    # Generate document pages (HTML with sidebar) for each document
    _generate_document_pages(input_path, output_path, generated_files, all_tests_nav)

    # Generate Swagger/OpenAPI documentation pages
    _generate_swagger_pages(output_path, all_api_doc_files, all_tests_nav, api_doc_categories)

    # Contract-check pages (rendered only when a report artifact exists)
    _generate_check_report_pages(output_path, check_report_pages, api_doc_categories)

    # Generate screen specification HTML pages from docs directories
    spec_files_info = []
    component_files_info = []
    # Include screens/json and components/json directories for spec pages
    spec_search_dirs = list(unique_docs_dirs)
    if spec_json_dir.exists():
        spec_search_dirs.append(spec_json_dir)
    if component_json_dir.exists():
        spec_search_dirs.append(component_json_dir)
    if spec_search_dirs:
        # Two-pass approach: first collect file info, then generate with navigation
        spec_files_info, component_files_info = _generate_spec_pages(
            spec_search_dirs, output_path, collect_only=True,
            layouts_dir=layouts_dir,
        )
        # Update navigation with spec and component files
        all_tests_nav['specs'] = spec_files_info
        all_tests_nav['components'] = component_files_info
        # Generate HTML with full navigation
        _generate_spec_pages(
            spec_search_dirs, output_path, all_tests_nav=all_tests_nav,
            layouts_dir=layouts_dir,
        )

    # Generate markdown pages from docs directories
    md_files_by_dir = {}
    if unique_docs_dirs:
        # Collect markdown files first
        md_files_by_dir = _collect_markdown_files(unique_docs_dirs)
        if md_files_by_dir:
            # Add to navigation
            all_tests_nav['md_files_by_dir'] = md_files_by_dir
            # Generate HTML pages
            _generate_markdown_pages(
                unique_docs_dirs, output_path, all_tests_nav, md_files_by_dir
            )

    # Generate Figma screen pages from figma/ directory
    figma_files_info = []
    if figma_dir is None:
        figma_dir = input_path.parent / "figma" if input_path.name == "tests" else input_path / "figma"
        if not figma_dir.exists():
            figma_dir = input_path.parent / "figma"
    if figma_dir.exists():
        figma_files_info = _generate_figma_pages(figma_dir, output_path, all_tests_nav)
        if figma_files_info:
            all_tests_nav['figma_screens'] = figma_files_info

    # Process multi-app documentation if --app options provided
    apps_nav = {}  # app_name -> {specs: [...], components: [...], ...}
    if apps:
        print("Processing multi-app documentation...")
        for app_info in apps:
            app_name = app_info['name']
            app_docs_path = Path(app_info['docs_path']).resolve()
            app_nav = {}

            # Process app-specific specs (screens/json)
            app_spec_dir = app_docs_path / "screens" / "json"
            app_component_dir = app_docs_path / "components" / "json"
            app_requirements_dir = app_docs_path / "requirements" / "json"

            # Pre-generate spec docs for this app
            if app_spec_dir.exists() or app_component_dir.exists() or app_requirements_dir.exists():
                _pre_generate_spec_docs(app_docs_path, layouts_dir=layouts_dir)
                # Also pre-generate for requirements if they exist
                if app_requirements_dir.exists():
                    _pre_generate_spec_docs(app_docs_path, spec_subdir="requirements", layouts_dir=layouts_dir)

            app_spec_search_dirs = []
            if app_spec_dir.exists():
                app_spec_search_dirs.append(app_spec_dir)
            if app_component_dir.exists():
                app_spec_search_dirs.append(app_component_dir)
            if app_requirements_dir.exists():
                app_spec_search_dirs.append(app_requirements_dir)

            if app_spec_search_dirs:
                app_specs, app_components = _generate_spec_pages(
                    app_spec_search_dirs, output_path, collect_only=True,
                    path_prefix=app_name, layouts_dir=layouts_dir,
                )
                if app_specs:
                    app_nav['specs'] = app_specs
                if app_components:
                    app_nav['components'] = app_components

            # Process app-specific markdown files from all subdirectories
            # (e.g., app-config/, plans/, etc. - everything except screens/json, components/json)
            app_md_dirs = []
            if app_docs_path.exists():
                for subdir in sorted(app_docs_path.iterdir()):
                    if subdir.is_dir() and subdir.name not in ('screens', 'components', 'requirements', 'html', 'json', 'md'):
                        app_md_dirs.append(subdir)
            if app_md_dirs:
                app_md_files = _collect_markdown_files(app_md_dirs, path_prefix=app_name)
                if app_md_files:
                    app_nav['md_files_by_dir'] = app_md_files

            # Process app-specific figma
            app_figma_dir = app_docs_path.parent / "figma"
            if app_figma_dir.exists():
                app_figma = _generate_figma_pages(
                    app_figma_dir, output_path, all_tests_nav,
                    path_prefix=app_name
                )
                if app_figma:
                    app_nav['figma_screens'] = app_figma

            if app_nav:
                apps_nav[app_name] = app_nav
                print(f"  {app_name}: {sum(len(v) for v in app_nav.values())} items")

        if apps_nav:
            all_tests_nav['apps'] = apps_nav

            # Second pass: generate HTML with full navigation for app specs
            for app_info in apps:
                app_name = app_info['name']
                app_docs_path = Path(app_info['docs_path']).resolve()

                app_spec_search_dirs = []
                for subdir in ["screens/json", "components/json", "requirements/json"]:
                    candidate = app_docs_path / subdir
                    if candidate.exists():
                        app_spec_search_dirs.append(candidate)

                if app_spec_search_dirs:
                    _generate_spec_pages(
                        app_spec_search_dirs, output_path,
                        all_tests_nav=all_tests_nav,
                        path_prefix=app_name,
                        layouts_dir=layouts_dir,
                    )

                # Generate app-specific markdown pages
                app_nav_data = apps_nav.get(app_name, {})
                app_md = app_nav_data.get('md_files_by_dir')
                if app_md:
                    app_md_dirs = []
                    if app_docs_path.exists():
                        for subdir in sorted(app_docs_path.iterdir()):
                            if subdir.is_dir() and subdir.name not in ('screens', 'components', 'requirements', 'html', 'json', 'md'):
                                app_md_dirs.append(subdir)
                    if app_md_dirs:
                        _generate_markdown_pages(
                            app_md_dirs, output_path,
                            all_tests_nav=all_tests_nav,
                            md_files_by_dir=app_md
                        )

    # Re-generate index.html with updated navigation (if specs, components, markdown, figma, or apps were added)
    if spec_files_info or component_files_info or md_files_by_dir or figma_files_info or apps_nav:
        generate_index_html(output_path, generated_files, title, mermaid_generated, document_files, api_doc_categories, spec_files_info, component_files_info, md_files_by_dir, figma_files_info, apps_nav=apps_nav)

    return generated_files


def _generate_document_pages(
    input_path: Path,
    output_path: Path,
    generated_files: list[dict],
    all_tests_nav: dict
) -> None:
    """
    Generate document pages with sidebar for all documents referenced in test files.

    Embeds body content directly with Mermaid CDN support (no iframe).

    Args:
        input_path: Input directory containing test files
        output_path: Output directory for generated HTML
        generated_files: List of generated file info dicts
        all_tests_nav: Navigation data for sidebar
    """
    # Collect unique document paths
    documents_to_process: dict[str, str] = {}  # doc_path -> test_name
    for f in generated_files:
        doc_path = f.get('document')
        if doc_path:
            documents_to_process[doc_path] = f.get('name', 'Document')

    if not documents_to_process:
        return

    print("  Generating document pages...")

    for doc_path, test_name in documents_to_process.items():
        try:
            # Resolve source document path.
            #
            # 'document' is resolved from the input directory (or its
            # parent), NOT from the test file like 'source.layout' is. The
            # bases differ for a reason: this value doubles as the page's
            # path inside the generated site and as the URL the flow
            # diagram links to, so it has to be a forward path from a
            # stable root. A test-file-relative '../../..' value would
            # write the page outside the output directory.
            source_path = input_path / doc_path
            if not source_path.exists():
                # Try relative to parent
                source_path = input_path.parent / doc_path
            if not source_path.exists():
                print(
                    f"    Warning: Document not found: {doc_path}\n"
                    f"      'document' is resolved from {input_path} or {input_path.parent}, "
                    f"not from the test file (unlike 'source.layout'). "
                    f"Write it as a forward path from one of those."
                )
                continue

            # Determine output path (preserve relative structure)
            # e.g., docs/screens/login.html -> docs/screens/login.html
            rel_doc_path = Path(doc_path)
            output_doc_path = output_path / rel_doc_path
            output_doc_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate document page with embedded body content and Mermaid CDN
            html_content = generate_document_html(
                source_path=source_path,
                title=test_name,
                all_tests_nav=all_tests_nav,
                current_doc_path=doc_path
            )

            with open(output_doc_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"    Generated: {output_doc_path}")

        except Exception as e:
            print(f"    Error processing document {doc_path}: {e}")


def _generate_swagger_pages(
    output_path: Path,
    api_doc_files: list[dict],
    all_tests_nav: dict,
    api_doc_categories: dict[str, list[dict]] | None = None
) -> None:
    """
    Generate Swagger/OpenAPI documentation pages.

    Uses Redoc for files with API paths, schema HTML for schema-only files.
    Also generates ER diagram for DB schema categories.

    Args:
        output_path: Output directory for generated HTML
        api_doc_files: List of API documentation file dicts
        all_tests_nav: Navigation data for sidebar
        api_doc_categories: Dict of category name -> list of docs for sidebar
    """
    if not api_doc_files:
        return

    print("  Generating API documentation pages...")

    # Track schema-only files by category for ER diagram generation
    schema_files_by_category: dict[str, list[dict]] = {}

    for api_doc in api_doc_files:
        try:
            swagger_data = api_doc.get('swagger_data')
            if not swagger_data:
                continue

            html_rel_path = api_doc['path']
            output_doc_path = output_path / html_rel_path
            output_doc_path.parent.mkdir(parents=True, exist_ok=True)

            # Get category docs for sidebar navigation
            category = api_doc.get('category', '')
            category_docs = api_doc_categories.get(category, []) if api_doc_categories else []

            # Check if this has API paths or is schema-only
            if has_api_paths(swagger_data):
                # Use Redoc for API documentation
                html_content = generate_swagger_html(
                    swagger_data=swagger_data,
                    title=api_doc['name'],
                    all_tests_nav=all_tests_nav,
                    current_doc_path=html_rel_path
                )
            else:
                # Use schema HTML for schema-only files (e.g., DB models)
                html_content = generate_schema_html(
                    swagger_data=swagger_data,
                    title=api_doc['name'],
                    current_doc_path=html_rel_path,
                    category_docs=category_docs
                )
                # Track for ER diagram
                if category not in schema_files_by_category:
                    schema_files_by_category[category] = []
                schema_files_by_category[category].append(api_doc)

            with open(output_doc_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"    Generated: {output_doc_path}")

        except Exception as e:
            print(f"    Error processing API doc {api_doc.get('name', 'unknown')}: {e}")

    # Generate ER diagrams for each schema category
    for category, schema_files in schema_files_by_category.items():
        if not schema_files:
            continue

        try:
            category_docs = api_doc_categories.get(category, []) if api_doc_categories else []
            erd_path = f"{category}/erd.html"
            output_erd_path = output_path / erd_path
            output_erd_path.parent.mkdir(parents=True, exist_ok=True)

            erd_html = generate_erd_html(
                schema_files=schema_files,
                title=(f"{category[3:]} ER Diagram" if category.startswith('db/')
                       else f"{category.upper()} ER Diagram"),
                current_doc_path=erd_path,
                category_docs=category_docs
            )

            with open(output_erd_path, 'w', encoding='utf-8') as f:
                f.write(erd_html)

            print(f"    Generated: {output_erd_path} (ER Diagram)")

        except Exception as e:
            print(f"    Error generating ER diagram for {category}: {e}")


def _discover_check_reports(
    docs_dirs: list,
    api_doc_categories: dict[str, list[dict]],
) -> list[dict]:
    """Find .check-report.json artifacts and register their pages in the
    category navigation. Reading only — never runs checks."""
    from ..check.report import REPORT_BASENAME, is_stale, load_report

    pages: list[dict] = []
    candidates: list[tuple[str, Path, Path]] = []
    for docs_dir in docs_dirs:
        docs_path = Path(docs_dir)
        if not docs_path.is_dir():
            continue
        # input_hashes in a report are relative to the project root, which
        # for a report at <root>/docs/<kind>/ is two levels up from the
        # kind dir — derive it per candidate rather than trusting docs_base
        # (explicit -d dirs can live anywhere).
        root = docs_path.parent.parent
        if docs_path.name in ("api", "db"):
            candidates.append((docs_path.name, docs_path / REPORT_BASENAME,
                               root))
        if docs_path.name == "db":
            for sub in sorted(p for p in docs_path.iterdir() if p.is_dir()):
                candidates.append((f"db/{sub.name}", sub / REPORT_BASENAME,
                                   root))

    for category, report_path, project_root in candidates:
        if not report_path.is_file():
            continue
        try:
            report = load_report(report_path)
        except Exception as e:  # noqa: BLE001 — a broken artifact must not kill generation
            print(f"  Warning: invalid check report {report_path}: {e}")
            continue
        if report is None:
            continue
        stale = is_stale(report, project_root)
        page_path = f"{category}/contract-check.html"
        status = "✗" if report.has_mismatch else ("⚠" if stale else "✓")
        api_doc_categories.setdefault(category, []).append({
            "name": f"Contract Check {status}",
            "path": page_path,
            "subdir": "",
            "check_report": True,
        })
        pages.append({
            "category": category,
            "report": report,
            "stale": stale,
            "path": page_path,
        })
    return pages


def _generate_check_report_pages(
    output_path: Path,
    check_report_pages: list[dict],
    api_doc_categories: dict[str, list[dict]] | None = None,
) -> None:
    if not check_report_pages:
        return
    from .html.check_report_page import generate_check_report_html

    print("  Generating contract-check pages...")
    for page in check_report_pages:
        category_docs = (api_doc_categories or {}).get(page["category"], [])
        html = generate_check_report_html(
            report=page["report"],
            title=f"Contract Check — {page['category']}",
            current_doc_path=page["path"],
            category_docs=category_docs,
            stale=page["stale"],
        )
        out_file = output_path / page["path"]
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"    Generated: {out_file}")


def _generate_spec_pages(
    docs_dirs: list[Path],
    output_path: Path,
    all_tests_nav: dict | None = None,
    collect_only: bool = False,
    path_prefix: str | None = None,
    layouts_dir: Path | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Generate HTML pages from screen and component specification JSON files.

    Finds all .spec.json and .component.json files in docs_dirs and generates
    corresponding HTML files.

    Args:
        docs_dirs: List of documentation directories to search
        output_path: Output directory for generated HTML
        all_tests_nav: Navigation data for sidebar (if provided, adds sidebar to pages)
        collect_only: If True, only collect file info without generating HTML
        path_prefix: Optional prefix for output paths (e.g., app name for multi-app)

    Returns:
        Tuple of (spec_files_info, component_files_info) for navigation
    """
    spec_files_found = []
    component_files_found = []

    # Find all .spec.json and .component.json files in docs_dirs
    for docs_dir in docs_dirs:
        docs_path = Path(docs_dir)
        if not docs_path.exists():
            continue

        # Look for .spec.json files (screen specifications)
        for spec_file in docs_path.rglob("*.spec.json"):
            spec_files_found.append((spec_file, docs_path))

        # Look for .component.json files (component specifications)
        for comp_file in docs_path.rglob("*.component.json"):
            component_files_found.append((comp_file, docs_path))

    spec_files_info = []
    component_files_info = []

    # Generate screen specification pages
    if spec_files_found:
        if not collect_only:
            print("  Generating screen specification pages...")

        success_count = 0
        error_count = 0

        for spec_file, spec_docs_path in sorted(spec_files_found, key=lambda x: x[0]):
            try:
                result = _validator_for(spec_file).validate_file(spec_file)

                if not result.is_valid:
                    if not collect_only:
                        print(f"    FAILED: {spec_file.name}")
                        for error in result.errors:
                            print(f"      {error}")
                    error_count += 1
                    continue

                # Determine output path
                # e.g., docs/screens/json/login.spec.json -> specs/login.html
                # e.g., docs/screens/json/settings/profile.spec.json -> specs/settings/profile.html
                # With path_prefix: client/specs/login.html
                output_name = spec_file.stem.replace(".spec", "") + ".html"
                # Preserve subdirectory structure relative to docs_path
                rel_to_docs = spec_file.parent.relative_to(spec_docs_path)
                rel_subdir = str(rel_to_docs) if str(rel_to_docs) != '.' else ''
                specs_subdir = f"{path_prefix}/specs" if path_prefix else "specs"
                if rel_subdir:
                    current_path = f"{specs_subdir}/{rel_subdir}/{output_name}"
                else:
                    current_path = f"{specs_subdir}/{output_name}"

                # Prepare navigation info
                metadata = result.spec_data.get('metadata', {})
                spec_files_info.append({
                    'name': metadata.get('displayName', metadata.get('name', spec_file.stem)),
                    'path': current_path,
                })

                # Skip HTML generation if collect_only mode
                if collect_only:
                    success_count += 1
                    continue

                output_spec_path = output_path / current_path
                output_spec_path.parent.mkdir(parents=True, exist_ok=True)

                # Generate HTML with navigation if available
                spec_layouts_dir = _resolve_layouts_dir_for_spec(spec_file, layouts_dir)
                content = generate_spec_html(
                    result.spec_data,
                    all_tests_nav=all_tests_nav,
                    current_path=current_path,
                    layouts_dir=spec_layouts_dir,
                )

                with open(output_spec_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                print(f"    Generated: {output_spec_path}")
                success_count += 1

            except Exception as e:
                print(f"    Error processing {spec_file.name}: {e}")
                error_count += 1

        if not collect_only and (success_count > 0 or error_count > 0):
            print(f"  Spec pages: {success_count} generated, {error_count} failed")

    # Generate component specification pages
    if component_files_found:
        if not collect_only:
            print("  Generating component specification pages...")

        success_count = 0
        error_count = 0

        for comp_file, comp_docs_path in sorted(component_files_found, key=lambda x: x[0]):
            try:
                result = _validator_for(comp_file).validate_file(comp_file)

                if not result.is_valid:
                    if not collect_only:
                        print(f"    FAILED: {comp_file.name}")
                        for error in result.errors:
                            print(f"      {error}")
                    error_count += 1
                    continue

                # Determine output path
                # e.g., docs/components/json/usercard.component.json -> components/usercard.html
                # With path_prefix: client/components/usercard.html
                output_name = comp_file.stem.replace(".component", "") + ".html"
                # Preserve subdirectory structure
                rel_to_docs = comp_file.parent.relative_to(comp_docs_path)
                rel_subdir = str(rel_to_docs) if str(rel_to_docs) != '.' else ''
                comps_subdir = f"{path_prefix}/components" if path_prefix else "components"
                if rel_subdir:
                    current_path = f"{comps_subdir}/{rel_subdir}/{output_name}"
                else:
                    current_path = f"{comps_subdir}/{output_name}"

                # Add to navigation info
                metadata = result.spec_data.get('metadata', {})
                component_files_info.append({
                    'name': metadata.get('displayName', metadata.get('name', comp_file.stem)),
                    'path': current_path,
                    'category': metadata.get('category', 'other'),
                })

                # Skip HTML generation if collect_only mode
                if collect_only:
                    success_count += 1
                    continue

                output_comp_path = output_path / current_path
                output_comp_path.parent.mkdir(parents=True, exist_ok=True)

                # Generate HTML using component-specific generator (with sidebar)
                content = generate_component_html(
                    result.spec_data,
                    all_tests_nav=all_tests_nav,
                    current_path=current_path
                )

                with open(output_comp_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                print(f"    Generated: {output_comp_path}")
                success_count += 1

            except Exception as e:
                print(f"    Error processing {comp_file.name}: {e}")
                error_count += 1

        if not collect_only and (success_count > 0 or error_count > 0):
            print(f"  Component pages: {success_count} generated, {error_count} failed")

    return spec_files_info, component_files_info


def _pre_generate_spec_docs(
    docs_base: Path,
    spec_subdir: str = "screens",
    layouts_dir: Path | None = None,
) -> None:
    """
    Pre-generate HTML and Markdown documentation from spec and component JSON files.

    Processes:
    - docs/<spec_subdir>/json/*.spec.json -> docs/<spec_subdir>/html/ and docs/<spec_subdir>/md/
    - docs/components/json/*.component.json -> docs/components/html/ and docs/components/md/

    Args:
        docs_base: Base docs directory (e.g., /path/to/project/docs)
        spec_subdir: Subdirectory name for spec files (default: "screens", can be "requirements")
    """
    from ..spec_doc import generate_spec_html, generate_spec_markdown
    from ..cli import generate_component_html, generate_component_markdown

    # Process screen specifications
    spec_json_dir = docs_base / spec_subdir / "json"
    if spec_json_dir.exists():
        spec_files = list(spec_json_dir.rglob("*.spec.json"))
        if spec_files:
            print(f"  Processing {len(spec_files)} {spec_subdir} specification files...")

            html_dir = docs_base / spec_subdir / "html"
            md_dir = docs_base / spec_subdir / "md"
            html_dir.mkdir(parents=True, exist_ok=True)
            md_dir.mkdir(parents=True, exist_ok=True)

            for spec_file in sorted(spec_files):
                try:
                    result = _validator_for(spec_file).validate_file(spec_file)
                    if not result.is_valid:
                        print(f"    SKIP: {spec_file.name} (validation errors)")
                        continue

                    # Generate HTML - preserve subdirectory structure
                    rel_to_json = spec_file.parent.relative_to(spec_json_dir)
                    output_name = spec_file.stem.replace(".spec", "")
                    html_subdir = html_dir / rel_to_json
                    md_subdir = md_dir / rel_to_json
                    html_subdir.mkdir(parents=True, exist_ok=True)
                    md_subdir.mkdir(parents=True, exist_ok=True)

                    spec_layouts_dir = _resolve_layouts_dir_for_spec(spec_file, layouts_dir)
                    html_content = generate_spec_html(result.spec_data, layouts_dir=spec_layouts_dir)
                    html_path = html_subdir / f"{output_name}.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)

                    # Generate Markdown
                    md_content = generate_spec_markdown(result.spec_data, layouts_dir=spec_layouts_dir)
                    md_path = md_subdir / f"{output_name}.md"
                    with open(md_path, 'w', encoding='utf-8') as f:
                        f.write(md_content)

                    print(f"    OK: {spec_file.name} -> html, md")

                except Exception as e:
                    print(f"    ERROR: {spec_file.name}: {e}")

    # Process component specifications
    comp_json_dir = docs_base / "components" / "json"
    if comp_json_dir.exists():
        comp_files = list(comp_json_dir.glob("*.component.json"))
        if comp_files:
            print(f"  Processing {len(comp_files)} component specification files...")

            html_dir = docs_base / "components" / "html"
            md_dir = docs_base / "components" / "md"
            html_dir.mkdir(parents=True, exist_ok=True)
            md_dir.mkdir(parents=True, exist_ok=True)

            for comp_file in sorted(comp_files):
                try:
                    result = _validator_for(comp_file).validate_file(comp_file)
                    if not result.is_valid:
                        print(f"    SKIP: {comp_file.name} (validation errors)")
                        continue

                    # Generate HTML
                    html_content = generate_component_html(result.spec_data)
                    output_name = comp_file.stem.replace(".component", "")
                    html_path = html_dir / f"{output_name}.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)

                    # Generate Markdown
                    md_content = generate_component_markdown(result.spec_data)
                    md_path = md_dir / f"{output_name}.md"
                    with open(md_path, 'w', encoding='utf-8') as f:
                        f.write(md_content)

                    print(f"    OK: {comp_file.name} -> html, md")

                except Exception as e:
                    print(f"    ERROR: {comp_file.name}: {e}")


def _collect_markdown_files(
    docs_dirs: list[Path],
    path_prefix: str | None = None
) -> dict[str, list[dict]]:
    """
    Collect markdown files from docs directories, grouped by directory name.

    Files are grouped by the docs_dir name (category). Subdirectories within
    each docs_dir are tracked via the 'subdir' field for sub-grouping in the UI.

    Args:
        docs_dirs: List of documentation directories to search
        path_prefix: Optional prefix for output paths (e.g., app name for multi-app)

    Returns:
        Dict of directory name -> list of markdown file info dicts
    """
    md_files_by_dir: dict[str, list[dict]] = {}

    for docs_dir in docs_dirs:
        docs_path = Path(docs_dir)
        if not docs_path.exists():
            continue

        # Use the docs_dir name as the category
        dir_name = docs_path.name

        # Find all .md files in this directory
        for md_file in sorted(docs_path.glob("**/*.md")):
            # Get relative path from docs_dir
            rel_path = md_file.relative_to(docs_path)

            # Track subdirectory relative to docs_path for sub-grouping
            if len(rel_path.parts) > 1:
                # File is in a subdirectory - track first-level subdir
                subdir = rel_path.parts[0]
            else:
                subdir = ''

            # Create output path preserving relative structure: md/{relative_path}.html
            output_name = rel_path.with_suffix('.html')
            if path_prefix:
                html_path = f"{path_prefix}/md/{output_name}"
            else:
                html_path = f"md/{output_name}"

            file_info = {
                'name': md_file.stem,
                'path': html_path,
                'source_file': md_file,
                'dir_name': dir_name,
                'subdir': subdir,
            }

            if dir_name not in md_files_by_dir:
                md_files_by_dir[dir_name] = []
            md_files_by_dir[dir_name].append(file_info)

    return md_files_by_dir


def _generate_markdown_pages(
    docs_dirs: list[Path],
    output_path: Path,
    all_tests_nav: dict | None = None,
    md_files_by_dir: dict[str, list[dict]] | None = None
) -> dict[str, list[dict]]:
    """
    Generate HTML pages from markdown files in docs directories.

    Args:
        docs_dirs: List of documentation directories to search
        output_path: Output directory for generated HTML
        all_tests_nav: Navigation data for sidebar
        md_files_by_dir: Pre-collected markdown files (if None, will collect)

    Returns:
        Dict of directory name -> list of markdown file info dicts
    """
    if md_files_by_dir is None:
        md_files_by_dir = _collect_markdown_files(docs_dirs)

    if not md_files_by_dir:
        return {}

    print("  Generating markdown pages...")

    success_count = 0
    error_count = 0

    for dir_name, md_files in md_files_by_dir.items():
        for file_info in md_files:
            try:
                source_file = file_info['source_file']
                html_rel_path = file_info['path']

                # Read markdown content
                with open(source_file, 'r', encoding='utf-8') as f:
                    md_content = f.read()

                # Create output directory
                output_html_path = output_path / html_rel_path
                output_html_path.parent.mkdir(parents=True, exist_ok=True)

                # Generate HTML
                html_content = generate_markdown_html(
                    markdown_content=md_content,
                    title=file_info['name'],
                    all_tests_nav=all_tests_nav,
                    current_path=html_rel_path,
                    md_files_by_dir=md_files_by_dir
                )

                with open(output_html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)

                print(f"    Generated: {output_html_path}")
                success_count += 1

            except Exception as e:
                print(f"    Error processing {file_info.get('name', 'unknown')}: {e}")
                error_count += 1

    if success_count > 0 or error_count > 0:
        print(f"  Markdown pages: {success_count} generated, {error_count} failed")

    return md_files_by_dir


def _generate_figma_pages(
    figma_dir: Path,
    output_path: Path,
    all_tests_nav: dict | None = None,
    path_prefix: str | None = None
) -> list[dict]:
    """
    Generate HTML pages from Figma JSON files.

    Discovers Figma API JSON files in figma_dir and converts each screen
    to an HTML page with sidebar navigation.

    Args:
        figma_dir: Directory containing Figma JSON files
        output_path: Output directory for generated HTML
        all_tests_nav: Navigation data for sidebar

    Returns:
        List of figma screen info dicts with 'name', 'path', 'canvas'
    """
    from ..figma.figma_to_html import convert_figma_json

    figma_json_files = sorted(figma_dir.glob("*.json"))
    if not figma_json_files:
        return []

    # Filter to only Figma API response files
    # Supports both full file format (document.children) and nodes format (nodes.{id}.document)
    valid_files = []
    for json_file in figma_json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Full file format: { "document": { "children": [...] } }
            if "document" in data and "children" in data.get("document", {}):
                valid_files.append(json_file)
            # Nodes format: { "nodes": { "0:1": { "document": {...} } } }
            elif "nodes" in data and isinstance(data["nodes"], dict):
                valid_files.append(json_file)
        except Exception:
            continue

    if not valid_files:
        return []

    print("  Generating Figma screen pages...")

    all_figma_files = []
    for json_file in valid_files:
        try:
            screens = convert_figma_json(json_file, output_path, all_tests_nav)
            all_figma_files.extend(screens)
            print(f"    {json_file.name}: {len(screens)} screens")
        except Exception as e:
            print(f"    Error processing {json_file.name}: {e}")

    if all_figma_files:
        print(f"  Figma pages: {len(all_figma_files)} screens generated")

    return all_figma_files
