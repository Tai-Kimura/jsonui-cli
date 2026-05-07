"""Markdown generation for JsonUI test documentation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..schema import (
    SUPPORTED_ACTIONS,
    SUPPORTED_ASSERTIONS,
    PARAMETER_DESCRIPTIONS,
)


def generate_markdown(
    data: dict,
    file_path: Path,
    resolve_description_fn,
    format_step_details_fn
) -> str:
    """
    Generate Markdown documentation from test data.

    Args:
        data: Test data dict
        file_path: Path to the test file
        resolve_description_fn: Function to resolve case description
        format_step_details_fn: Function to format step details

    Returns:
        Markdown string
    """
    lines = []

    # Header
    metadata = data.get("metadata", {})
    title = metadata.get("name", file_path.stem)
    description = metadata.get("description", "")

    lines.append(f"# {title}")
    lines.append("")
    if description:
        lines.append(f"> {description}")
        lines.append("")

    # Test info
    lines.append("## Test Information")
    lines.append("")
    lines.append(f"- **Type:** {data.get('type', 'unknown')}")
    lines.append(f"- **Platform:** {data.get('platform', 'all')}")
    if "source" in data:
        lines.append(f"- **Layout:** `{data['source'].get('layout', 'N/A')}`")
    lines.append(f"- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Test cases
    cases = data.get("cases", [])
    if cases:
        lines.append("## Test Cases")
        lines.append("")

        for i, case in enumerate(cases, 1):
            case_name = case.get("name", f"Case {i}")
            case_desc = resolve_description_fn(case)

            lines.append(f"### {i}. {case_name}")
            lines.append("")
            lines.extend(_format_description_markdown(case_desc))

            # Steps table
            steps = case.get("steps", [])
            if steps:
                lines.append("| # | Type | Action/Assert | Target | Details |")
                lines.append("|---|------|---------------|--------|---------|")

                for j, step in enumerate(steps, 1):
                    step_type = "Action" if "action" in step else "Assert"
                    action_name = step.get("action") or step.get("assert", "?")
                    target = step.get("id") or ", ".join(step.get("ids", [])) or "-"
                    details = format_step_details_fn(step)
                    lines.append(f"| {j} | {step_type} | `{action_name}` | `{target}` | {details} |")

                lines.append("")

    # Setup/Teardown
    for section_name in ["setup", "teardown"]:
        section = data.get(section_name, [])
        if section:
            lines.append(f"## {section_name.title()}")
            lines.append("")
            for j, step in enumerate(section, 1):
                action_name = step.get("action") or step.get("assert", "?")
                target = step.get("id", "-")
                lines.append(f"{j}. `{action_name}` on `{target}`")
            lines.append("")

    return "\n".join(lines)


def _format_description_markdown(desc: dict | str) -> list[str]:
    """Format description (dict or string) for Markdown output."""
    lines = []
    if isinstance(desc, dict):
        # Description from JSON file
        if desc.get("summary"):
            lines.append(desc["summary"])
            lines.append("")
        if desc.get("preconditions"):
            lines.append("**Preconditions:**")
            for item in desc["preconditions"]:
                lines.append(f"- {item}")
            lines.append("")
        if desc.get("test_procedure"):
            lines.append("**Test Procedure:**")
            for i, item in enumerate(desc["test_procedure"], 1):
                lines.append(f"{i}. {item}")
            lines.append("")
        if desc.get("expected_results"):
            lines.append("**Expected Results:**")
            for item in desc["expected_results"]:
                lines.append(f"- {item}")
            lines.append("")
        if desc.get("notes"):
            lines.append(f"**Notes:** {desc['notes']}")
            lines.append("")
    elif desc:
        # Inline description string
        lines.append(desc)
        lines.append("")
    return lines


def generate_schema_markdown() -> str:
    """Generate Markdown schema reference."""
    lines = [
        "# JsonUI Test Schema Reference",
        "",
        "This document describes all supported actions and assertions for JsonUI test files.",
        "",
        "## Actions",
        "",
    ]

    for action, spec in SUPPORTED_ACTIONS.items():
        lines.append(f"### `{action}`")
        lines.append("")
        lines.append(spec["description"])
        lines.append("")

        if spec["required"]:
            lines.append("**Required parameters:**")
            for param in spec["required"]:
                desc = PARAMETER_DESCRIPTIONS.get(param, "")
                lines.append(f"- `{param}`: {desc}")
            lines.append("")

        if spec["optional"]:
            lines.append("**Optional parameters:**")
            for param in spec["optional"]:
                desc = PARAMETER_DESCRIPTIONS.get(param, "")
                lines.append(f"- `{param}`: {desc}")
            lines.append("")

        # Example
        example = _get_action_example(action, spec)
        lines.append("**Example:**")
        lines.append("```json")
        lines.append(json.dumps(example, indent=2))
        lines.append("```")
        lines.append("")

    lines.append("## Assertions")
    lines.append("")

    for assertion, spec in SUPPORTED_ASSERTIONS.items():
        lines.append(f"### `{assertion}`")
        lines.append("")
        lines.append(spec["description"])
        lines.append("")

        if spec["required"]:
            lines.append("**Required parameters:**")
            for param in spec["required"]:
                desc = PARAMETER_DESCRIPTIONS.get(param, "")
                lines.append(f"- `{param}`: {desc}")
            lines.append("")

        if spec["optional"]:
            lines.append("**Optional parameters:**")
            for param in spec["optional"]:
                desc = PARAMETER_DESCRIPTIONS.get(param, "")
                lines.append(f"- `{param}`: {desc}")
            lines.append("")

        # Example
        example = _get_assertion_example(assertion, spec)
        lines.append("**Example:**")
        lines.append("```json")
        lines.append(json.dumps(example, indent=2))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _get_action_example(action: str, spec: dict) -> dict:
    """Generate example for an action."""
    example = {"action": action}

    if "id" in spec["required"]:
        example["id"] = "element_id"
    if "ids" in spec["required"]:
        example["ids"] = ["element_1", "element_2"]
    if "value" in spec["required"]:
        example["value"] = "sample text"
    if "direction" in spec["required"]:
        example["direction"] = "down"
    if "ms" in spec["required"]:
        example["ms"] = 1000
    if "name" in spec["required"]:
        example["name"] = "screenshot_name"

    return example


def _get_assertion_example(assertion: str, spec: dict) -> dict:
    """Generate example for an assertion."""
    example = {"assert": assertion}

    if "id" in spec["required"]:
        example["id"] = "element_id"
    if "equals" in spec["required"]:
        example["equals"] = 5

    if assertion == "text":
        example["equals"] = "Expected text"

    return example
