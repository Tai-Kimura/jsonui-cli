"""Screen test HTML generation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .styles import get_screen_styles, get_toggle_script
from .sidebar import generate_screen_sidebar, escape_html


def generate_screen_html(
    data: dict,
    file_path: Path,
    resolve_description_fn,
    format_description_html_fn,
    format_step_details_fn,
    all_tests_nav: dict | None = None,
    current_test_path: str | None = None
) -> str:
    """
    Generate HTML documentation for screen tests.

    Args:
        data: Test data dict
        file_path: Path to the test file
        resolve_description_fn: Function to resolve case description
        format_description_html_fn: Function to format description as HTML
        format_step_details_fn: Function to format step details
        all_tests_nav: Navigation data {'screens': [...], 'flows': [...]}
        current_test_path: Current test's relative HTML path

    Returns:
        Complete HTML string
    """
    metadata = data.get("metadata", {})
    name = metadata.get("name", file_path.stem)
    description = metadata.get("description", "")
    title = description or name
    cases = data.get("cases", [])

    # Pre-compute case display names for sidebar
    case_displays = []
    for case in cases:
        case_name = case.get("name", "Case")
        case_desc = resolve_description_fn(case)
        if isinstance(case_desc, dict) and case_desc.get("summary"):
            case_displays.append(case_desc["summary"])
        else:
            case_displays.append(case.get("description") or case_name)

    # Build HTML
    html_parts = _get_html_header(title)
    html_parts.extend(generate_screen_sidebar(title, case_displays, all_tests_nav, current_test_path))

    # Main content wrapper
    html_parts.append("  <main class='main-content'>")
    html_parts.append(f"    <h1>{escape_html(title)}</h1>")
    html_parts.append(f"    <p class='test-name-label'><strong>Test Name:</strong> <code>{escape_html(name)}</code></p>")

    # Test info
    html_parts.append("    <div class='info'>")
    html_parts.append(f"      <strong>Type:</strong> {data.get('type', 'unknown')}<br>")
    html_parts.append(f"      <strong>Platform:</strong> {data.get('platform', 'all')}<br>")
    if "source" in data:
        html_parts.append(f"      <strong>Layout:</strong> <code>{escape_html(data['source'].get('layout', 'N/A'))}</code><br>")
    html_parts.append(f"      <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    html_parts.append("    </div>")

    # Test cases
    if cases:
        html_parts.append("    <h2>Test Cases</h2>")

        for i, case in enumerate(cases, 1):
            case_name = case.get("name", f"Case {i}")
            case_desc = resolve_description_fn(case)
            # Use description from descriptionFile (summary) or inline description
            if isinstance(case_desc, dict) and case_desc.get("summary"):
                case_display = case_desc["summary"]
            else:
                case_display = case.get("description") or case_name
            case_id = f"case-{i}"

            html_parts.append(f"    <h3 id='{case_id}'>{i}. {escape_html(case_display)}</h3>")
            html_parts.append(f"    <p class='case-name-label'><strong>Case Name:</strong> <code>{escape_html(case_name)}</code></p>")

            # Display args if present
            case_args = case.get("args", {})
            if case_args:
                html_parts.append("    <div class='case-args'>")
                html_parts.append("      <strong>Default Args:</strong>")
                html_parts.append("      <ul>")
                for arg_key, arg_value in case_args.items():
                    html_parts.append(f"        <li><code>@{{{arg_key}}}</code> = <code>{escape_html(str(arg_value))}</code></li>")
                html_parts.append("      </ul>")
                html_parts.append("    </div>")

            html_parts.extend(format_description_html_fn(case_desc))

            steps = case.get("steps", [])
            if steps:
                html_parts.append("    <table>")
                html_parts.append("      <tr><th>#</th><th>Type</th><th>Action/Assert</th><th>Target</th><th>Details</th></tr>")

                for j, step in enumerate(steps, 1):
                    step_type = "action" if "action" in step else "assert"
                    type_label = "Action" if step_type == "action" else "Assert"
                    action_name = step.get("action") or step.get("assert", "?")
                    target = step.get("id") or ", ".join(step.get("ids", [])) or "-"
                    details = format_step_details_fn(step)
                    html_parts.append(f"      <tr><td>{j}</td><td><span class='{step_type}'>{type_label}</span></td><td><code>{action_name}</code></td><td><code>{target}</code></td><td>{details}</td></tr>")

                html_parts.append("    </table>")

    html_parts.append("  </main>")
    html_parts.append("</body>")
    html_parts.append("</html>")

    return "\n".join(html_parts)


def _get_html_header(title: str) -> list[str]:
    """Get HTML header with styles for screen test pages."""
    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        f"  <title>{escape_html(title)} - Test Documentation</title>",
        "  <meta charset='utf-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1'>",
        "  <style>",
    ]
    parts.extend(get_screen_styles())
    parts.append("  </style>")
    parts.extend(get_toggle_script())
    parts.extend([
        "</head>",
        "<body>",
    ])
    return parts
