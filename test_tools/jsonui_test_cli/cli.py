#!/usr/bin/env python3
"""
JsonUI Test CLI

Command-line interface for validating and generating test files.
For documentation generation, use jsonui-doc (document_tools).
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

from . import __version__
from .validator import TestValidator


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


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="jsonui-test",
        description="JsonUI Test CLI - Validate and generate test files"
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
        help="Generate test files and descriptions"
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
        else:
            generate_parser.print_help()
            return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
