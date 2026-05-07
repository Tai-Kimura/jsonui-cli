"""Flow test HTML generation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .styles import get_flow_styles, get_toggle_script
from .sidebar import generate_flow_sidebar, escape_html


def generate_flow_html(
    data: dict,
    file_path: Path,
    format_step_details_fn,
    resolve_description_for_ref_fn,
    get_ref_case_label_fn,
    format_description_html_for_ref_fn,
    render_referenced_cases_fn,
    resolve_block_description_fn=None,
    format_block_description_html_fn=None,
    all_tests_nav: dict | None = None,
    current_test_path: str | None = None
) -> str:
    """
    Generate HTML documentation for flow tests.

    Args:
        data: Test data dict
        file_path: Path to the test file
        format_step_details_fn: Function to format step details
        resolve_description_for_ref_fn: Function to resolve description for referenced case
        get_ref_case_label_fn: Function to get sidebar label for file reference
        format_description_html_for_ref_fn: Function to format description HTML for reference
        render_referenced_cases_fn: Function to render referenced cases
        resolve_block_description_fn: Function to resolve block description (optional)
        format_block_description_html_fn: Function to format block description as HTML (optional)
        all_tests_nav: Navigation data {'screens': [...], 'flows': [...]}
        current_test_path: Current test's relative HTML path

    Returns:
        Complete HTML string
    """
    metadata = data.get("metadata", {})
    name = metadata.get("name", file_path.stem)
    description = metadata.get("description", "")
    title = description or name
    steps = data.get("steps", [])
    setup_steps = data.get("setup", [])
    teardown_steps = data.get("teardown", [])
    checkpoints = data.get("checkpoints", [])

    # Build sidebar data (file references and blocks, not inline action/assert)
    # Only file references and blocks get numbered
    sidebar_steps = []
    numbered_step_num = 0
    for step in steps:
        if "file" in step:
            numbered_step_num += 1
            # File reference - get label from referenced case description
            file_ref = step.get("file", "")
            case_name = step.get("case")
            cases_list = step.get("cases")

            # Get label from referenced file's case description
            label = get_ref_case_label_fn(file_ref, case_name, cases_list)

            sidebar_steps.append({
                "num": numbered_step_num,
                "type": "file",
                "label": label,
                "detail": ""
            })
        elif "block" in step:
            numbered_step_num += 1
            # Block step - show in sidebar with description or block name
            block_name = step.get("block", "")
            block_desc = step.get("description", "")

            # Try to get description from descriptionFile if present
            if resolve_block_description_fn and "descriptionFile" in step:
                resolved_desc = resolve_block_description_fn(step)
                if isinstance(resolved_desc, dict) and resolved_desc.get("summary"):
                    block_desc = resolved_desc["summary"]

            label = block_desc or block_name
            sidebar_steps.append({
                "num": numbered_step_num,
                "type": "block",
                "label": label,
                "detail": ""
            })
        # Inline steps (action/assert) are not shown in sidebar and not numbered

    # Build HTML
    html_parts = _get_html_header(title, name)
    html_parts.extend(generate_flow_sidebar(name, sidebar_steps, checkpoints, all_tests_nav, current_test_path))

    # Main content wrapper
    html_parts.append("  <main class='main-content'>")
    html_parts.append(f"    <h1>{escape_html(title)}</h1>")
    html_parts.append(f"    <p class='test-name-label'><strong>Flow Name:</strong> <code>{escape_html(name)}</code></p>")

    # Test info
    html_parts.append("    <div class='info'>")
    html_parts.append(f"      <strong>Type:</strong> flow<br>")
    html_parts.append(f"      <strong>Platform:</strong> {data.get('platform', 'all')}<br>")
    html_parts.append(f"      <strong>Steps:</strong> {len(steps)}<br>")
    if setup_steps:
        html_parts.append(f"      <strong>Setup:</strong> {len(setup_steps)} steps<br>")
    if teardown_steps:
        html_parts.append(f"      <strong>Teardown:</strong> {len(teardown_steps)} steps<br>")
    if checkpoints:
        html_parts.append(f"      <strong>Checkpoints:</strong> {len(checkpoints)}<br>")
    html_parts.append(f"      <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    html_parts.append("    </div>")

    # Setup section
    if setup_steps:
        html_parts.append("    <h2>Setup</h2>")
        html_parts.append("    <div class='setup-teardown'>")
        for i, step in enumerate(setup_steps, 1):
            html_parts.extend(_render_flow_step(
                i, step, "setup", format_step_details_fn, render_referenced_cases_fn,
                resolve_block_description_fn, format_block_description_html_fn
            ))
        html_parts.append("    </div>")

    # Flow Steps
    html_parts.append("    <h2>Flow Steps</h2>")
    numbered_step_num = 0
    for step in steps:
        # Only file references and blocks get numbered
        if "file" in step or "block" in step:
            numbered_step_num += 1
            html_parts.extend(_render_flow_step(
                numbered_step_num, step, "step", format_step_details_fn, render_referenced_cases_fn,
                resolve_block_description_fn, format_block_description_html_fn
            ))
        else:
            # Inline action/assert - no number
            html_parts.extend(_render_flow_step(
                None, step, "step", format_step_details_fn, render_referenced_cases_fn,
                resolve_block_description_fn, format_block_description_html_fn
            ))

    # Teardown section
    if teardown_steps:
        html_parts.append("    <h2>Teardown</h2>")
        html_parts.append("    <div class='setup-teardown'>")
        for i, step in enumerate(teardown_steps, 1):
            html_parts.extend(_render_flow_step(
                i, step, "teardown", format_step_details_fn, render_referenced_cases_fn,
                resolve_block_description_fn, format_block_description_html_fn
            ))
        html_parts.append("    </div>")

    # Checkpoints section
    if checkpoints:
        html_parts.append("    <h2>Checkpoints</h2>")
        html_parts.append("    <ul class='checkpoint-list'>")
        for cp in checkpoints:
            cp_name = cp.get("name", "unnamed")
            after_step = cp.get("afterStep", 0)
            has_screenshot = cp.get("screenshot", False)
            screenshot_icon = " 📷" if has_screenshot else ""
            html_parts.append(f"      <li><strong>{escape_html(cp_name)}</strong> (after step {after_step + 1}){screenshot_icon}</li>")
        html_parts.append("    </ul>")

    html_parts.append("  </main>")
    html_parts.append("</body>")
    html_parts.append("</html>")

    return "\n".join(html_parts)


def _render_flow_step(
    num: int | None,
    step: dict,
    context: str,
    format_step_details_fn,
    render_referenced_cases_fn,
    resolve_block_description_fn=None,
    format_block_description_html_fn=None
) -> list[str]:
    """Render a single flow step as HTML.

    Args:
        num: Step number (None for inline action/assert steps that shouldn't be numbered)
    """
    parts = []
    step_id = f"{context}-{num}" if num else f"{context}-inline"

    if "file" in step:
        # File reference step
        file_ref = step.get("file", "")
        case_name = step.get("case")
        cases = step.get("cases")

        parts.append(f"    <div class='flow-step file-ref' id='{step_id}'>")
        parts.append(f"      <div class='step-header'>")
        parts.append(f"        <span class='step-number'>{num}</span>")
        parts.append(f"        <span class='step-type-badge file'>File Reference</span>")
        parts.append(f"      </div>")
        parts.append(f"      <div class='step-content'>")
        parts.append(f"        <div class='step-detail'><strong>File:</strong> <code>{escape_html(file_ref)}</code></div>")

        if case_name:
            parts.append(f"        <div class='step-detail'><strong>Case:</strong> <code>{escape_html(case_name)}</code></div>")
        elif cases:
            cases_str = ", ".join(cases)
            parts.append(f"        <div class='step-detail'><strong>Cases:</strong> <code>{escape_html(cases_str)}</code></div>")
        else:
            parts.append(f"        <div class='step-detail'><strong>Cases:</strong> <em>all cases</em></div>")

        # Display args if present
        step_args = step.get("args", {})
        if step_args:
            parts.append(f"        <div class='step-args'>")
            parts.append(f"          <strong>Args (Override):</strong>")
            parts.append(f"          <ul>")
            for arg_key, arg_value in step_args.items():
                parts.append(f"            <li><code>@{{{arg_key}}}</code> = <code>{escape_html(str(arg_value))}</code></li>")
            parts.append(f"          </ul>")
            parts.append(f"        </div>")

        # Load referenced file and show case details
        ref_cases_html = render_referenced_cases_fn(file_ref, case_name, cases)
        if ref_cases_html:
            parts.extend(ref_cases_html)

        parts.append(f"      </div>")
        parts.append(f"    </div>")

    elif "block" in step:
        # Block step - grouped inline steps with description
        block_name = step.get("block", "")
        block_steps = step.get("steps", [])

        # Resolve description
        block_desc = step.get("description", "")
        resolved_desc = None
        if resolve_block_description_fn:
            resolved_desc = resolve_block_description_fn(step)
            if isinstance(resolved_desc, dict) and resolved_desc.get("summary"):
                block_desc = resolved_desc["summary"]

        display_title = block_desc or block_name

        parts.append(f"    <div class='flow-step block-step' id='{step_id}'>")
        parts.append(f"      <div class='step-header'>")
        parts.append(f"        <span class='step-number'>{num}</span>")
        parts.append(f"        <span class='step-type-badge block'>Block</span>")
        parts.append(f"        <span class='block-title'>{escape_html(display_title)}</span>")
        parts.append(f"      </div>")
        parts.append(f"      <div class='step-content'>")
        parts.append(f"        <div class='step-detail'><strong>Block Name:</strong> <code>{escape_html(block_name)}</code></div>")

        # Render block description (similar to case description)
        if format_block_description_html_fn and resolved_desc:
            desc_html = format_block_description_html_fn(resolved_desc)
            if desc_html:
                parts.extend(desc_html)

        # Render block steps as table (same as screen test case steps)
        if block_steps:
            parts.append(f"        <div class='block-steps'>")
            parts.append(f"          <div class='block-steps-header'>Steps ({len(block_steps)})</div>")
            parts.append(f"          <table>")
            parts.append(f"            <tr><th>#</th><th>Type</th><th>Action/Assert</th><th>Target</th><th>Details</th></tr>")
            for j, inner_step in enumerate(block_steps, 1):
                step_type = "action" if "action" in inner_step else "assert"
                type_label = "Action" if step_type == "action" else "Assert"
                action_name = inner_step.get("action") or inner_step.get("assert", "?")
                target = inner_step.get("id") or ", ".join(inner_step.get("ids", [])) or "-"
                details = format_step_details_fn(inner_step)
                parts.append(f"            <tr><td>{j}</td><td><span class='{step_type}'>{type_label}</span></td><td><code>{escape_html(action_name)}</code></td><td><code>{escape_html(target)}</code></td><td>{escape_html(details) if details else ''}</td></tr>")
            parts.append(f"          </table>")
            parts.append(f"        </div>")

        parts.append(f"      </div>")
        parts.append(f"    </div>")

    elif "action" in step:
        # Inline action
        action = step.get("action", "?")
        target = step.get("id") or ", ".join(step.get("ids", [])) or "-"
        details = format_step_details_fn(step)

        parts.append(f"    <div class='flow-step inline-action' id='{step_id}'>")
        parts.append(f"      <div class='step-header'>")
        parts.append(f"        <span class='step-type-badge action'>Action</span>")
        parts.append(f"        <code class='inline-step-action'>{escape_html(action)}</code>")
        parts.append(f"        <span class='inline-step-target'>-> <code>{escape_html(target)}</code></span>")
        if details:
            parts.append(f"        <span class='inline-step-details'>({escape_html(details)})</span>")
        parts.append(f"      </div>")
        parts.append(f"    </div>")

    elif "assert" in step:
        # Inline assertion
        assertion = step.get("assert", "?")
        target = step.get("id") or ", ".join(step.get("ids", [])) or "-"
        details = format_step_details_fn(step)

        parts.append(f"    <div class='flow-step inline-assert' id='{step_id}'>")
        parts.append(f"      <div class='step-header'>")
        parts.append(f"        <span class='step-type-badge assert'>Assert</span>")
        parts.append(f"        <code class='inline-step-action'>{escape_html(assertion)}</code>")
        parts.append(f"        <span class='inline-step-target'>-> <code>{escape_html(target)}</code></span>")
        if details:
            parts.append(f"        <span class='inline-step-details'>({escape_html(details)})</span>")
        parts.append(f"      </div>")
        parts.append(f"    </div>")

    return parts


def _get_html_header(title: str, name: str) -> list[str]:
    """Get HTML header with styles for flow test pages."""
    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        f"  <title>{escape_html(title)} - Flow Test Documentation</title>",
        "  <meta charset='utf-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1'>",
        "  <style>",
    ]
    parts.extend(get_flow_styles())
    parts.append("  </style>")
    parts.extend(get_toggle_script())
    parts.extend([
        "</head>",
        "<body>",
    ])
    return parts
