#!/usr/bin/env python3
"""
JsonUI Test CLI

Command-line interface for validating, generating test files,
and creating documentation from JsonUI test files.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

from . import __version__
from .validator import TestValidator
from .generator import DocumentGenerator, generate_schema_reference, generate_html_directory
from .mermaid import generate_mermaid_diagram, generate_mermaid_html
from .adapter import generate_adapter, SUPPORTED_PLATFORMS as ADAPTER_PLATFORMS


def cmd_validate(args):
    """Handle validate command."""
    validator = TestValidator()
    total_errors = 0
    total_warnings = 0
    files_checked = 0

    # Collect files
    files_to_validate = []
    for path in args.files:
        p = Path(path)
        if p.is_dir():
            # Collect test files
            files_to_validate.extend(p.rglob("*.test.json"))
            # Collect description files in descriptions folders
            for desc_dir in p.rglob("descriptions"):
                if desc_dir.is_dir():
                    files_to_validate.extend(desc_dir.glob("*.json"))
        elif p.exists():
            files_to_validate.append(p)
        else:
            print(f"Warning: Path not found: {path}", file=sys.stderr)

    if not files_to_validate:
        print("No test or description files found")
        return 1

    # Validate each file
    for file_path in sorted(files_to_validate):
        files_checked += 1
        result = validator.validate_file(file_path)

        if args.verbose or result.errors or result.warnings:
            print(f"\n{file_path}")

        if result.errors:
            for error in result.errors:
                print(error)
            total_errors += len(result.errors)

        if result.warnings and not args.quiet:
            for warning in result.warnings:
                print(warning)
            total_warnings += len(result.warnings)

        if result.is_valid and not result.warnings and args.verbose:
            print("  OK")

    # Summary
    print(f"\n{'='*50}")
    status = "PASSED" if total_errors == 0 else "FAILED"
    print(f"Result: {status}")
    print(f"Files: {files_checked}, Errors: {total_errors}, Warnings: {total_warnings}")

    return 1 if total_errors > 0 else 0


def cmd_generate_test_screen(args):
    """Handle 'generate test screen' command - create screen test file template."""
    name = args.name
    output_path = args.path

    # Determine output path if not specified
    if not output_path:
        output_path = f"tests/screens/{name.lower()}/{name.lower()}.test.json"

    # Create test template
    test_template = {
        "type": "screen",
        "metadata": {
            "name": f"{name}_test",
            "description": f"Tests for {name} screen"
        },
        "cases": [
            {
                "name": "initial_display",
                "description": "Verify initial screen state",
                "steps": [
                    {"assert": "visible", "id": "TODO_element_id"}
                ]
            }
        ]
    }

    # Add platform if specified
    if args.platform:
        test_template["platform"] = args.platform

    # Write file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(test_template, f, indent=2, ensure_ascii=False)

    print(f"Created screen test file: {output}")
    print(f"  Edit the file to add proper element IDs and test cases.")

    return 0


def cmd_generate_test_flow(args):
    """Handle 'generate test flow' command - create flow test file template."""
    name = args.name
    output_path = args.path

    # Determine output path if not specified
    if not output_path:
        output_path = f"tests/flows/{name.lower()}/{name.lower()}.test.json"

    # Create flow test template
    test_template = {
        "type": "flow",
        "metadata": {
            "name": f"{name}_flow",
            "description": f"{name} flow test"
        },
        "steps": [
            {"action": "waitFor", "id": "TODO_start_screen"},
            {"action": "tap", "id": "TODO_element_id"},
            {"assert": "visible", "id": "TODO_end_screen"}
        ]
    }

    # Add platform if specified
    if args.platform:
        test_template["platform"] = args.platform

    # Write file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(test_template, f, indent=2, ensure_ascii=False)

    print(f"Created flow test file: {output}")
    print(f"  Edit the file to add proper element IDs and test steps.")

    return 0


def cmd_generate_description(args):
    """Handle 'generate description' command - create description JSON file for a specific test case."""
    test_type = args.test_type  # "screen" or "flow"
    name = args.name
    case_name = args.case_name
    output_path = args.path

    # Determine output path if not specified
    if not output_path:
        output_path = f"tests/{test_type}s/{name.lower()}/descriptions/{case_name}.json"

    # Create description JSON
    description_data = {
        "case_name": case_name,
        "summary": "",
        "preconditions": [],
        "test_procedure": [],
        "expected_results": [],
        "notes": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    # Write file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(description_data, f, indent=2, ensure_ascii=False)

    print(f"Created description file: {output}")
    print(f"  Edit the file to add test documentation.")
    print(f"\nTo link to test file, add 'descriptionFile' to the case:")
    print(f'  "descriptionFile": "descriptions/{case_name}.json"')

    return 0


def cmd_generate_doc(args):
    """Handle 'generate doc' command - generate HTML/MD documentation."""
    generator = DocumentGenerator()

    # Determine output format
    output_format = args.format
    if args.output and not output_format:
        ext = Path(args.output).suffix.lower()
        if ext == ".html":
            output_format = "html"
        else:
            output_format = "markdown"
    elif not output_format:
        output_format = "markdown"

    # Handle schema reference
    if args.schema:
        content = generate_schema_reference(format=output_format)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Schema reference written to: {output_path}")
        else:
            print(content)
        return 0

    # Handle test file documentation
    if not args.file:
        print("Error: Either --file or --schema is required", file=sys.stderr)
        return 1

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    try:
        output_path = Path(args.output) if args.output else None
        content = generator.generate(file_path, output_path, format=output_format)

        if content:
            print(content)
        else:
            print(f"Documentation written to: {output_path}")

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate_html(args):
    """Handle 'generate html' command - generate HTML directory with index."""
    input_dir = Path(args.input)
    output_dir = Path(args.output) if args.output else Path("html")
    title = args.title or "JsonUI Test Documentation"

    # Process multiple --docs options
    docs_dirs = []
    if args.docs:
        for doc_path in args.docs:
            doc_dir = Path(doc_path)
            if not doc_dir.exists():
                print(f"Error: Docs directory not found: {doc_dir}", file=sys.stderr)
                return 1
            docs_dirs.append(doc_dir)

    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        return 1

    print(f"Generating HTML documentation...")
    print(f"  Input: {input_dir}")
    print(f"  Output: {output_dir}")
    for doc_dir in docs_dirs:
        print(f"  Docs: {doc_dir}")
    print()

    try:
        files = generate_html_directory(input_dir, output_dir, title, docs_dirs if docs_dirs else None)
        print()
        print(f"Generated {len(files)} HTML files")
        print(f"Open {output_dir}/index.html to view documentation")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate_mermaid(args):
    """Handle 'generate mermaid' command - generate Mermaid flow diagram."""
    input_dir = Path(args.input)
    output_path = Path(args.output) if args.output else None
    title = args.title or "Flow Diagram"
    screens_dir = Path(args.screens) if args.screens else None

    # Determine flows directory
    flows_dir = input_dir / "flows" if (input_dir / "flows").exists() else input_dir

    if not flows_dir.exists():
        print(f"Error: Input directory not found: {flows_dir}", file=sys.stderr)
        return 1

    # Determine screens directory
    if screens_dir is None:
        if (input_dir / "screens").exists():
            screens_dir = input_dir / "screens"
        else:
            screens_dir = flows_dir.parent / "screens"

    print(f"Generating Mermaid diagram...")
    print(f"  Flows: {flows_dir}")
    print(f"  Screens: {screens_dir}")

    try:
        if output_path:
            # Generate HTML with embedded Mermaid
            mermaid_code = generate_mermaid_html(flows_dir, output_path, title, screens_dir)
            print()
            print(f"Generated: {output_path}")
            print(f"Open in browser to view the diagram")
        else:
            # Output Mermaid code to stdout
            mermaid_code = generate_mermaid_diagram(flows_dir, screens_dir)
            print()
            print(mermaid_code)

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate_adapter(args):
    """Handle 'generate adapter' command - generate adapter files for custom actions."""
    platform = args.platform
    output_dir = Path(args.output) if args.output else Path(".")
    project_name = args.name or "MyApp"

    # Parse custom actions from JSON file if provided
    custom_actions = None
    if args.actions:
        actions_path = Path(args.actions)
        if actions_path.exists():
            with open(actions_path, 'r', encoding='utf-8') as f:
                custom_actions = json.load(f)
                if isinstance(custom_actions, dict):
                    custom_actions = custom_actions.get("actions", [])

    print(f"Generating {platform} adapter...")
    print(f"  Output: {output_dir}")
    print(f"  Project: {project_name}")
    if custom_actions:
        print(f"  Custom actions: {len(custom_actions)}")

    try:
        generated = generate_adapter(
            platform=platform,
            output_dir=output_dir,
            project_name=project_name,
            custom_actions=custom_actions
        )

        print()
        print("Generated files:")
        for name, path in generated.items():
            print(f"  {name}: {path}")

        print()
        print("Next steps:")
        if platform == "ios":
            print("  1. Add JsonUITestAdapter.swift to your UITest target")
            print("  2. Call applyJsonUIConfig() before app.launch()")
            print("  3. Implement your custom action handlers")
        elif platform == "android":
            print("  1. Add JsonUITestAdapter.kt to your androidTest directory")
            print("  2. Call JsonUITestAdapter.configure() before activity launch")
            print("  3. Implement your custom action handlers")
        elif platform == "web":
            print("  1. Import JsonUITestAdapter in your test setup")
            print("  2. Call adapter.configure() before navigation")
            print("  3. Implement your custom action handlers")

        print()
        print(f"Schema file: {generated.get('schema')}")
        print("  Use this schema in your test JSON files for validation:")
        print('  { "$schema": "./jsonui-test-custom.schema.json", ... }')

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# Legacy generate command for backwards compatibility
def cmd_generate(args):
    """Handle legacy generate command (redirects to 'generate doc')."""
    return cmd_generate_doc(args)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="jsonui-test",
        description="JsonUI Test CLI - Validate and generate test files and documentation"
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        aliases=["v"],
        help="Validate test files"
    )
    validate_parser.add_argument(
        "files",
        nargs="+",
        help="Files or directories to validate"
    )
    validate_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show all files, including valid ones"
    )
    validate_parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Hide warnings, show only errors"
    )

    # Generate command with subcommands
    generate_parser = subparsers.add_parser(
        "generate",
        aliases=["g"],
        help="Generate test files, descriptions, or documentation"
    )
    generate_subparsers = generate_parser.add_subparsers(dest="generate_type", help="Generation type")

    # Generate test subcommand with screen/flow subcommands
    gen_test_parser = generate_subparsers.add_parser(
        "test",
        aliases=["t"],
        help="Generate test file template"
    )
    gen_test_subparsers = gen_test_parser.add_subparsers(dest="test_type", help="Test type")

    # Generate test screen subcommand
    gen_test_screen_parser = gen_test_subparsers.add_parser(
        "screen",
        help="Generate screen test file template"
    )
    gen_test_screen_parser.add_argument(
        "name",
        help="Screen name (e.g., login, home)"
    )
    gen_test_screen_parser.add_argument(
        "--path",
        help="Output test file path (default: tests/screens/<name>/<name>.test.json)"
    )
    gen_test_screen_parser.add_argument(
        "-p", "--platform",
        choices=["ios", "ios-swiftui", "ios-uikit", "android", "web", "all"],
        help="Target platform"
    )

    # Generate test flow subcommand
    gen_test_flow_parser = gen_test_subparsers.add_parser(
        "flow",
        help="Generate flow test file template"
    )
    gen_test_flow_parser.add_argument(
        "name",
        help="Flow name (e.g., login, checkout)"
    )
    gen_test_flow_parser.add_argument(
        "--path",
        help="Output test file path (default: tests/flows/<name>/<name>.test.json)"
    )
    gen_test_flow_parser.add_argument(
        "-p", "--platform",
        choices=["ios", "ios-swiftui", "ios-uikit", "android", "web", "all"],
        help="Target platform"
    )

    # Generate description subcommand with screen/flow subcommands
    gen_desc_parser = generate_subparsers.add_parser(
        "description",
        aliases=["d", "desc"],
        help="Generate description JSON file for a test case"
    )
    gen_desc_subparsers = gen_desc_parser.add_subparsers(dest="test_type", help="Test type")

    # Generate description screen subcommand
    gen_desc_screen_parser = gen_desc_subparsers.add_parser(
        "screen",
        help="Generate description for screen test case"
    )
    gen_desc_screen_parser.add_argument(
        "name",
        help="Screen name (e.g., login, home)"
    )
    gen_desc_screen_parser.add_argument(
        "case_name",
        help="Test case name (e.g., initial_display, error_case_1)"
    )
    gen_desc_screen_parser.add_argument(
        "--path",
        help="Output file path (default: tests/screens/<name>/descriptions/<case_name>.json)"
    )

    # Generate description flow subcommand
    gen_desc_flow_parser = gen_desc_subparsers.add_parser(
        "flow",
        help="Generate description for flow test case"
    )
    gen_desc_flow_parser.add_argument(
        "name",
        help="Flow name (e.g., login, checkout)"
    )
    gen_desc_flow_parser.add_argument(
        "case_name",
        help="Test case name (e.g., happy_path, error_handling)"
    )
    gen_desc_flow_parser.add_argument(
        "--path",
        help="Output file path (default: tests/flows/<name>/descriptions/<case_name>.json)"
    )

    # Generate doc subcommand
    gen_doc_parser = generate_subparsers.add_parser(
        "doc",
        help="Generate HTML/Markdown documentation from test files"
    )
    gen_doc_parser.add_argument(
        "-f", "--file",
        help="Test file to generate documentation for"
    )
    gen_doc_parser.add_argument(
        "-o", "--output",
        help="Output file path"
    )
    gen_doc_parser.add_argument(
        "--format",
        choices=["markdown", "html"],
        help="Output format (default: inferred from output or markdown)"
    )
    gen_doc_parser.add_argument(
        "--schema",
        action="store_true",
        help="Generate schema reference instead of test documentation"
    )

    # Generate html subcommand
    gen_html_parser = generate_subparsers.add_parser(
        "html",
        help="Generate HTML directory with index for all test files"
    )
    gen_html_parser.add_argument(
        "input",
        help="Input directory containing .test.json files"
    )
    gen_html_parser.add_argument(
        "-o", "--output",
        help="Output directory (default: html)"
    )
    gen_html_parser.add_argument(
        "-t", "--title",
        help="Title for index page (default: JsonUI Test Documentation)"
    )
    gen_html_parser.add_argument(
        "-d", "--docs",
        action="append",
        metavar="DIR",
        help="Directory containing OpenAPI/Swagger files (can be specified multiple times, e.g., -d api -d db)"
    )

    # Generate mermaid subcommand
    gen_mermaid_parser = generate_subparsers.add_parser(
        "mermaid",
        help="Generate Mermaid flow diagram from flow tests"
    )
    gen_mermaid_parser.add_argument(
        "input",
        help="Input directory containing tests (with flows/ and screens/ subdirs)"
    )
    gen_mermaid_parser.add_argument(
        "-o", "--output",
        help="Output HTML file path (if not specified, outputs Mermaid code to stdout)"
    )
    gen_mermaid_parser.add_argument(
        "-t", "--title",
        help="Title for diagram page (default: Flow Diagram)"
    )
    gen_mermaid_parser.add_argument(
        "-s", "--screens",
        help="Path to screens directory (default: auto-detect)"
    )

    # Generate adapter subcommand
    gen_adapter_parser = generate_subparsers.add_parser(
        "adapter",
        aliases=["a"],
        help="Generate adapter files for custom actions and configurations"
    )
    gen_adapter_parser.add_argument(
        "platform",
        choices=ADAPTER_PLATFORMS,
        help="Target platform (ios, android, web)"
    )
    gen_adapter_parser.add_argument(
        "-o", "--output",
        help="Output directory (default: current directory)"
    )
    gen_adapter_parser.add_argument(
        "-n", "--name",
        help="Project name for namespacing (default: MyApp)"
    )
    gen_adapter_parser.add_argument(
        "-a", "--actions",
        help="Path to JSON file defining custom actions"
    )

    # Legacy: direct generate options (for backwards compatibility)
    generate_parser.add_argument(
        "-f", "--file",
        help="(Legacy) Test file to generate documentation for"
    )
    generate_parser.add_argument(
        "-o", "--output",
        help="(Legacy) Output file path"
    )
    generate_parser.add_argument(
        "--format",
        choices=["markdown", "html"],
        help="(Legacy) Output format"
    )
    generate_parser.add_argument(
        "--schema",
        action="store_true",
        help="(Legacy) Generate schema reference"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.command in ["validate", "v"]:
        return cmd_validate(args)
    elif args.command in ["generate", "g"]:
        # Check for subcommand
        if hasattr(args, 'generate_type') and args.generate_type:
            if args.generate_type in ["test", "t"]:
                # Check for test type subcommand
                if hasattr(args, 'test_type') and args.test_type:
                    if args.test_type == "screen":
                        return cmd_generate_test_screen(args)
                    elif args.test_type == "flow":
                        return cmd_generate_test_flow(args)
                gen_test_parser.print_help()
                return 0
            elif args.generate_type in ["description", "d", "desc"]:
                # Check for test type subcommand
                if hasattr(args, 'test_type') and args.test_type:
                    if args.test_type in ["screen", "flow"]:
                        return cmd_generate_description(args)
                gen_desc_parser.print_help()
                return 0
            elif args.generate_type == "doc":
                return cmd_generate_doc(args)
            elif args.generate_type == "html":
                return cmd_generate_html(args)
            elif args.generate_type == "mermaid":
                return cmd_generate_mermaid(args)
            elif args.generate_type in ["adapter", "a"]:
                return cmd_generate_adapter(args)
        # Legacy: if --file or --schema is used directly
        elif args.file or args.schema:
            return cmd_generate(args)
        else:
            generate_parser.print_help()
            return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
