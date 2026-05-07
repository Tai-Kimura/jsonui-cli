"""Generator for JsonUI test documentation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .validator import TestValidator, ValidationResult
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
)
from .html.sidebar import escape_html
from .markdown import generate_markdown, generate_schema_markdown
from .mermaid import generate_mermaid_html


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


def generate_html_directory(
    input_dir: Path,
    output_dir: Path,
    title: str = "JsonUI Test Documentation",
    docs_dirs: list[Path] | None = None
) -> list[dict]:
    """
    Generate HTML documentation for all test files in a directory.

    Creates individual HTML files for each test and an index.html with links.

    Args:
        input_dir: Directory containing .test.json files
        output_dir: Directory to output HTML files
        title: Title for the index page
        docs_dirs: Optional list of directories containing OpenAPI/Swagger files

    Returns:
        List of generated file info dicts with 'name', 'path', 'type', 'cases'
    """
    generator = DocumentGenerator()
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

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

    if docs_dirs:
        for docs_dir in docs_dirs:
            docs_path = Path(docs_dir)
            if not docs_path.exists():
                continue

            # Use directory name as category (e.g., "api", "db")
            category_name = docs_path.name

            category_files = []
            for json_file in sorted(docs_path.rglob("*.json")):
                if is_swagger_file(json_file):
                    swagger_data = parse_swagger_file(json_file)
                    if swagger_data:
                        info = swagger_data.get('info', {})
                        api_name = info.get('title', json_file.stem)
                        api_desc = info.get('description', '')
                        # Output path: <category>/<filename>.html
                        html_rel_path = f"{category_name}/{json_file.stem}.html"
                        doc_info = {
                            'name': api_name,
                            'description': api_desc[:100] + '...' if len(api_desc) > 100 else api_desc,
                            'path': html_rel_path,
                            'source_file': json_file,
                            'swagger_data': swagger_data,
                            'category': category_name,
                        }
                        category_files.append(doc_info)
                        all_api_doc_files.append(doc_info)

            if category_files:
                api_doc_categories[category_name] = category_files

    # Build navigation data for sidebar
    all_tests_nav = {
        'screens': [{'name': f['name'], 'path': str(f['path'])} for f in file_infos if f['type'] == 'screen'],
        'flows': [{'name': f['name'], 'path': str(f['path'])} for f in file_infos if f['type'] == 'flow'],
        'documents': document_files,
        'api_docs': [{'name': d['name'], 'path': d['path']} for d in all_api_doc_files],
        'api_doc_categories': {k: [{'name': d['name'], 'path': d['path']} for d in v] for k, v in api_doc_categories.items()},
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
            generate_mermaid_html(flows_dir, mermaid_output, "Flow Diagram", screens_dir)
            mermaid_generated = True
            print(f"  Generated: {mermaid_output}")
        except Exception as e:
            print(f"  Warning: Could not generate Mermaid diagram: {e}")

    # Generate index.html
    generate_index_html(output_path, generated_files, title, mermaid_generated, document_files, api_doc_categories)

    # Generate document pages (HTML with sidebar) for each document
    _generate_document_pages(input_path, output_path, generated_files, all_tests_nav)

    # Generate Swagger/OpenAPI documentation pages
    _generate_swagger_pages(output_path, all_api_doc_files, all_tests_nav, api_doc_categories)

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
            # Resolve source document path
            source_path = input_path / doc_path
            if not source_path.exists():
                # Try relative to parent
                source_path = input_path.parent / doc_path
            if not source_path.exists():
                print(f"    Warning: Document not found: {doc_path}")
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
                title=f"{category.upper()} ER Diagram",
                current_doc_path=erd_path,
                category_docs=category_docs
            )

            with open(output_erd_path, 'w', encoding='utf-8') as f:
                f.write(erd_html)

            print(f"    Generated: {output_erd_path} (ER Diagram)")

        except Exception as e:
            print(f"    Error generating ER diagram for {category}: {e}")
