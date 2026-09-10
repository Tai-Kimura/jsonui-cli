"""Generator for JsonUI test documentation."""

from __future__ import annotations

import json
import os
import posixpath
import re
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any

from ..validator import TestValidator, ValidationResult
from ..spec_doc import SpecValidator, generate_spec_html, generate_component_html
from ..spec_doc.rules_config import load_rules_for_path
from .html import (
    generate_screen_html,
    generate_flow_html,
    generate_unit_html,
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
from .. import run_log
from ..run_log import warn


# ── Page-level failure accounting ────────────────────────────────────────
#
# A page that fails to render used to disappear silently: the run still
# exited 0, the index and sidebar kept linking to it, and the gap surfaced
# only when a human clicked the dead link — a week later, in the report that
# prompted this (doc-html-generation-swallows-page-errors).
#
# Every `except` that abandons a WHOLE PAGE funnels through
# `record_page_failure`, which also writes a placeholder in the page's place
# so the link resolves and states what went wrong. Failures that only
# degrade part of a page (an unreadable description file rendered as an
# inline error) are deliberately not counted here — those are visible where
# they happen.
#
# Module-level state is safe: one CLI invocation renders one site, and
# `generate_html_directory` resets it on entry.
_page_failures: list[dict] = []
# Paths, not a tally: knowing which pages this run wrote is what lets the
# leftovers from previous runs be named at the end.
_pages_written: set[Path] = set()
#: Directories this run wrote OUTSIDE `-o`. `generate html` regenerates the
#: per-spec html/md in the SOURCE tree before it builds the site, for the root
#: scope and for every `--app` in the same invocation — so one run rewrites
#: every app's tree, and two lanes pointing `-o` at different directories are
#: not isolated from each other. Reported 2026-09-08, after two lanes measured
#: against that assumption for a whole release cycle; the writes were real and
#: nothing named them. Named at the end of the run now, from what was actually
#: written rather than from a rule about where it would go.
_written_outside_output: set[Path] = set()
# Set by `_report_stale_pages_outside`: the number of directories that scan
# walked. `leftoversOutside: 0` beside `…Scanned: 0` is "nothing to look at";
# beside `…Scanned: 4` it is "looked at four and found none". Without it the
# two share one symbol, and a face gating on `leftoversOutside == 0` passes
# unconditionally on a run that registered no outside directories at all
# (triage, 2026-09-10, sharpening the scoped-zero ticket).
_stale_outside_scanned: int = 0

#: Which source file each written page was rendered from, for the writers
#: that render a file already on disk (a face's markdown, a spec). The site
#: copy of a leftover is the page whose SOURCE is the leftover — not a page
#: that happens to share its name, which on one tree was another face's live
#: screen (2026-09-10).
_page_sources: dict = {}

#: Which tests name each document (resolved source path → test names), from
#: the document-page writer. A leftover that tests still name is not a page
#: to delete but a face-side inconsistency (spec renamed, tests not); the
#: report says so instead of sending the reader to delete it (triage,
#: 2026-09-10: one such orphan was named by five tests).
_document_referrers: dict = {}


#: What the last run read, for the closing line. Recorded once at the end of
#: `generate_html_directory` and phrased in ONE place, the same reason
#: `unit-stubs --check` hands its denominator over as a sentence rather than
#: as numbers for each caller to word again.
_generation_counts: dict = {}

#: What the document-slot report found, for the manifest. The printed report
#: reaches whoever is watching; its return value reached nobody — the call
#: site discarded it — and the manifest's own `summary.collisions` counts a
#: DIFFERENT quantity under the same word (keys whose spellings normalised
#: onto one entry), so one face read `collisions: 0` beside two SHARED SLOT
#: lines from the same run. Kept under its own name so the two cannot be
#: read as one number disagreeing with itself.
_document_slot_facts: dict = {}


#: Flow-test transitions absent from the specs, this run. The CLI reads it
#: back for the exit code the same way it reads `_page_failures`.
_diagram_errors: list[dict] = []


def get_diagram_errors() -> list[dict]:
    """``{owner, from, to, flow, file, reason}`` per absent transition, oldest first."""
    return list(_diagram_errors)


def reset_page_failures() -> None:
    """Start a fresh accounting run."""
    _page_failures.clear()
    _pages_written.clear()
    _written_outside_output.clear()
    global _stale_outside_scanned
    _stale_outside_scanned = 0
    _page_sources.clear()
    _document_referrers.clear()
    _generation_counts.clear()
    _document_slot_facts.clear()
    run_log.reset()
    _diagram_errors.clear()


def note_generation_counts(**counts) -> None:
    """Record what this run read, for `generation_summary_line`."""
    _generation_counts.update(counts)


def generation_summary_line() -> str:
    """`Generated N HTML files (...)` — the count WITH its denominator.

    A bare page count cannot tell an empty input, a mistyped path, a project
    that declares no contracts, and a half-updated install apart: all four
    produce a small number and exit 0. So the line carries what was read, not
    only what was written.

    `unit targets U from K spec file(s) scanned` is one clause on purpose — U
    alone is the number that was ambiguous, and K is what disambiguates it.

    ⚠️ U is a different unit from K and D, and the words say which: U counts
    TARGETS while K and D both count spec FILES. The first reader of this
    line took K for screens and D for targets and published both wrong, which
    is what these words are for. K and D are deliberately the same unit so
    that D <= K reads as true, and both are the gate's own quantities —
    `unit-stubs --check` counts the same files with the same words, so the
    site and the gate cannot drift.
    """
    n = get_pages_written()
    c = _generation_counts
    head = f"Generated {n} HTML files"
    # 🔻 THE WARNING COUNT IS THE TOOL'S, AND IT PRINTS AT ZERO. This line
    # never carried one; what a face read as "warning 5" at 1.8.63 was its own
    # grep over the log, which went to 0 when five lines were respelled — and
    # from the log alone, "0 warnings" and "the counter is gone" are the same
    # sentence. Tallied by `run_log.warn`, which every warning goes through.
    warnings = f"warnings {run_log.count()}"
    # 🔻 THE TOTAL IS THE GATE'S; THE BREAKDOWN IS THE READER'S. On any `--app`
    # run the outside-writes notice fires by design and the gate's expression
    # counts its ⚠, so N is never 0 on a multi-app face and "0 = clean" was a
    # reading nobody there could use (reported 2026-09-10). Shrinking N would
    # re-open the gap B2 closed (tally ≠ gate); dropping the ⚠ would take a
    # write into another lane's tree out of the zero-warnings gate. So N stays
    # and the same line says how many of it are structural: `N − M == 0` is
    # the clean reading.
    structural = run_log.structural()
    if structural:
        warnings += (f" ({sum(structural.values())} structural: "
                     f"{', '.join(sorted(structural))})")
    # 🔻 THE READER'S EXPRESSION ALSO MATCHES DATA. N counts what went through
    # `warn()`; the rulebook's grep counts every line it matches, and a face
    # printed a test NAME carrying "warning:" (the shared-slot listing echoes
    # names) — its log said 2 where this line said 1, and no fixture's name
    # had ever carried the token, so the B2 arm was green for the fixtures'
    # reason (2026-09-10). Bending data so the expression misses it would
    # dull the instrument; so N stays the tool's, and this clause says how
    # many more lines the gate will count that are not warnings — the
    # reader's 2 explained by the line that says 1. Only the command can see
    # its own stream (`run_log.begin` wraps it); a library call has no window
    # and adds no clause. The clause itself carries none of the gate's tokens.
    hits = run_log.data_hits()
    if hits:
        warnings += (f" / gate expression matches {run_log.count() + len(hits)} "
                     f"({len(hits)} printed data, not warnings)")
    if not c:
        return f"{head} ({warnings})"
    parts = [f"screens {c.get('screens', 0)}", f"flows {c.get('flows', 0)}"]
    if c.get("unit_scanned"):
        parts.append(
            f"unit targets {c.get('unit_targets', 0)} from "
            f"{c.get('specs_read', 0)} spec file(s) scanned, "
            f"{c.get('specs_declaring', 0)} spec file(s) declaring unitContracts"
        )
    else:
        # Not "0 read". A scan that did not happen and a scan that found
        # nothing are the two things this line exists to separate.
        parts.append("unitContracts not read")
    parts.append(warnings)
    return f"{head} ({' / '.join(parts)})"


def generation_warnings() -> list[str]:
    """Warnings about the denominator itself, in the counted spelling.

    Zero specs read is the shape a wrong path makes, and it is also the shape
    an empty project makes; the difference matters enough to say out loud,
    because everything downstream of it reports a legitimate-looking zero.
    """
    c = _generation_counts
    out: list[str] = []
    if c.get("unit_scanned") and not c.get("specs_read"):
        out.append(
            "WARNING [doc]: 0 spec file(s) scanned while looking for "
            "unitContracts "
            "— the spec directory is empty or `spec_directory` points "
            "somewhere else, so `unit targets 0` is not evidence that none "
            "are declared")
    # K counts every file looked at, unreadable ones included, while D counts
    # only files that could be read AND declare. So a spec that will not parse
    # widens K - D by one and changes nothing else: from the closing line it
    # is indistinguishable from a file that simply declares nothing. Named
    # here, with the files, because "declares nothing" and "could not be
    # asked" are the pair this whole line exists to keep apart.
    unreadable = c.get("specs_unreadable") or 0
    if unreadable:
        names = ", ".join(c.get("unreadable_files") or []) or "(not named)"
        out.append(
            f"WARNING [doc]: {unreadable} spec file(s) could not be read while "
            f"looking for unitContracts: {names}")
    return out


def get_page_failures() -> list[dict]:
    """Failures recorded since the last reset, oldest first."""
    return list(_page_failures)


def get_pages_written() -> int:
    """Distinct files reported as generated since the last reset.

    Distinct, not a tally of writes: when two sources landed on one path the
    old counter reported both, so the number agreed with a run that had in
    fact lost a page.
    """
    return len(_pages_written)


def get_written_pages() -> set[Path]:
    """Resolved paths of the pages written since the last reset."""
    return set(_pages_written)


def note_page_generated(path: Path | str, suffix: str = "", indent: str = "    ") -> None:
    """Report a successfully written page and count it."""
    _pages_written.add(Path(path).resolve())
    print(f"{indent}Generated: {path}{suffix}")


def note_page_source(path: Path | str, source: Path | str) -> None:
    """Record which file on disk a written page was rendered from."""
    try:
        _page_sources[Path(path).resolve()] = Path(source).resolve()
    except OSError:
        pass


def _validation_failure_text(result, limit: int = 5) -> str:
    """The errors themselves, not the fact that there were errors.

    `(validation errors)` sent the reader back to run the validator by hand
    to find out which ones. The placeholder page and the stderr summary both
    render this string, so the message has to carry the errors with it.
    """
    errors = list(getattr(result, "errors", []) or [])
    if not errors:
        return "the spec did not validate"
    head = "; ".join(
        f"{getattr(e, 'path', '') or '(spec)'}: {getattr(e, 'message', e)}"
        for e in errors[:limit]
    )
    if len(errors) > limit:
        head += f"; … and {len(errors) - limit} more error(s)"
    return f"{len(errors)} validation error(s) — {head}"


def record_page_failure(
    kind: str,
    name: str,
    error: BaseException | str,
    *,
    source: Path | str | None = None,
    output: Path | str | None = None,
    indent: str = "    ",
) -> None:
    """Record that one page could not be generated.

    `source` is the input file — without it the operator has to guess which
    of dozens of inputs to fix, since `name` is only the display title.
    `output`, when given, gets a placeholder page so navigation does not
    dead-end on a 404.
    """
    failure = {
        'kind': kind,
        'name': name,
        'error': str(error),
        'source': str(source) if source is not None else None,
        'output': str(output) if output is not None else None,
    }
    _page_failures.append(failure)

    where = f" [{source}]" if source else ""
    print(f"{indent}Error processing {kind} {name}{where}: {error}")

    if output is not None:
        try:
            _write_failure_placeholder(Path(output), failure)
        except Exception as placeholder_error:  # noqa: BLE001
            print(f"{indent}  (could not write placeholder: {placeholder_error})")


def _write_failure_placeholder(output_path: Path, failure: dict) -> None:
    """Write a page that says why the real page is missing."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_line = (
        f"<p><strong>Source:</strong> <code>{escape_html(failure['source'])}</code></p>"
        if failure['source'] else ""
    )
    output_path.write_text(
        "<!DOCTYPE html>\n"
        "<html lang='en'><head><meta charset='utf-8'>"
        f"<title>Generation failed — {escape_html(failure['name'])}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:48rem;margin:4rem auto;"
        "padding:0 1rem;line-height:1.6}code{background:#f1f5f9;padding:.1rem .3rem;"
        "border-radius:3px}.err{background:#fef2f2;border-left:4px solid #dc2626;"
        "padding:1rem;margin:1.5rem 0}</style></head><body>"
        f"<h1>This page could not be generated</h1>"
        f"<p><strong>{escape_html(failure['kind'])}:</strong> "
        f"{escape_html(failure['name'])}</p>"
        f"{source_line}"
        f"<div class='err'><code>{escape_html(failure['error'])}</code></div>"
        "<p>Fix the input and regenerate. This placeholder exists so the link "
        "that brought you here is not a 404 — the documentation is incomplete, "
        "not merely mis-linked.</p>"
        "</body></html>\n",
        encoding='utf-8',
    )


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


# Test trees come in two shapes. A single-app project puts the type directory
# at the top — ``tests/screens/login/…`` — while a project holding several apps
# puts the app in front of it: ``tests/user/screens/…``. The type directory is
# what tells them apart, so the segments ahead of it are the app and a type
# directory in first position means there is no app to speak of. Reading the
# group off the path keeps single-app output byte-identical and avoids asking
# the author to declare a second time what the directory layout already says.
_TEST_TYPE_DIRS = ("screens", "flows")


def _test_group(rel_path: Path) -> str:
    """Return the app a test belongs to, or '' when the project has just one.

    *rel_path* is the test file relative to the tests input directory.

    Not every app uses the type directory — ``tests/<app>/*.test.json`` is a
    real shape, and a project can hold one app in each style at once. Taking
    every segment when no type directory appears keeps those two apps
    symmetrical; splitting on the marker only when there is one is what keeps
    ``tests/screens/<area>/`` an area rather than an app.
    """
    dirs = rel_path.parts[:-1]
    for i, part in enumerate(dirs):
        if part in _TEST_TYPE_DIRS:
            return "/".join(dirs[:i])
    return "/".join(dirs)


def _diagram_owners(
    input_path: Path,
    unit_roots: list[dict] | None,
    project_root: Path | None,
    docs_base: Path,
    layouts_override: Path | None,
    root_app: str,
    flow_groups: list[str],
    test_roots: list[dict] | None = None,
) -> list[dict]:
    """One entry per app that can have a diagram — i.e. per SPEC directory.

    Ruled 2026-09-10: the diagram is drawn from specs, so its owners are the
    spec-bearing apps, not the flow-bearing ones. Three ways an owner is
    found, most explicit first:

      1. a unit root (``--config`` / ``--app`` / the walk-up): its config
         names ``spec_directory``, ``layouts_directory``, the app-owned
         screens and the transition aliases
      2. the run's own ``docs/screens/json`` when no config was found
      3. a flow group's ``docs/<app>/screens/json`` — a config-less
         multi-app tree, kept so such a tree still gets its diagrams

    Each entry: ``{name, app, spec_dir, layouts_dir, aliases, app_owned,
    app_owned_transitions, flows_dir, screens_dir, rel}``.

    ⚠️ An app's flow tests live where its config's ``test.src`` says
    (``test_roots``), which in a split tree is ``<app>/tests`` — NOT under
    the run's input directory. The first version looked only at
    ``<input>/<app>/flows`` and checked 0 of a face's 59 flow tests, which
    reads exactly like "no violations" (measured by triage 2026-09-10 on an
    isolated copy). ``<input>/<app>`` remains the fallback for the shared
    ``tests/<app>/`` shape, where no app declares ``test.src``.
    """
    from .mermaid.flow_graph import import_jui_cli_module
    project_config = import_jui_cli_module("jui_cli.core.project_config")
    screen_identity = import_jui_cli_module("jui_cli.core.screen_identity")
    roots_by_app: dict[str | None, Path] = {}
    for entry in (test_roots or []):
        if entry.get("root"):
            roots_by_app[entry.get("app")] = Path(entry["root"])

    def tests_for(app: str | None, declared_root: Path | None = None) -> tuple[Path, Path, str, Path]:
        """``(flows_dir, screens_dir, provenance)`` — provenance says which
        root the paths came from, so the log never claims to have LOOKED at
        a directory it did not (a face read `flow tests 0 in client/tests/bar`
        as "it looked there"). An app that DECLARES `test.src` is judged by
        the declared path, present or absent; the fallback under the input
        directory is only for apps that declare nothing."""
        declared = roots_by_app.get(app) or declared_root
        if declared is not None:
            if declared.is_dir():
                base, provenance = declared, "declared test root"
            else:
                return declared / "flows", declared / "screens", "absent: declared", declared
        else:
            base = input_path / app if app else input_path
            if not base.is_dir():
                return base / "flows", base / "screens", "absent: nothing declared", base
            provenance = "fallback under the input directory"
        flows = base / "flows" if (base / "flows").exists() else base
        screens = base / "screens" if (base / "screens").exists() else flows.parent / "screens"
        return flows, screens, provenance, base

    owners: list[dict] = []
    seen_specs: set[Path] = set()

    def add(name: str, app: str | None, spec_dir: Path | None, layouts: Path | None,
            config: dict | None, declared_root: Path | None = None) -> None:
        if spec_dir is None or not spec_dir.is_dir():
            return
        key = spec_dir.resolve()
        if key in seen_specs:
            return
        seen_specs.add(key)
        aliases: list = []
        app_owned: list = []
        owned_transitions: dict = {}
        if config is not None and project_config is not None and screen_identity is not None:
            aliases = screen_identity.parse_transition_aliases(
                project_config.declared_transition_aliases(config))
            declared = project_config.declared_app_owned_screens(config)
            app_owned = [e.screen_id for e in screen_identity.parse_app_owned_screens(declared)]
            owned_transitions = screen_identity.app_owned_transitions(declared)
        flows, screens, provenance, test_root = tests_for(app, declared_root)
        owners.append({
            "name": name, "app": app, "spec_dir": spec_dir, "layouts_dir": layouts,
            "aliases": aliases, "app_owned": app_owned,
            "app_owned_transitions": owned_transitions,
            "flows_dir": flows, "screens_dir": screens, "tests_provenance": provenance,
            "test_root": test_root,
            "rel": f"{app}/diagram.html" if app else "diagram.html",
        })

    for entry in normalise_unit_roots(unit_roots, project_root):
        root = Path(entry["root"])
        config = None
        if project_config is not None:
            config, _path = project_config.find_project_config(root)
        if not isinstance(config, dict):
            continue
        spec_rel = config.get("spec_directory")
        spec_dir = (root / spec_rel).resolve() if isinstance(spec_rel, str) and spec_rel else None
        layouts = layouts_override
        if layouts is None:
            layouts_rel = config.get("layouts_directory")
            if isinstance(layouts_rel, str) and layouts_rel:
                layouts = (root / layouts_rel).resolve()
        app = entry.get("app")
        src = (config.get("test") or {}).get("src") if isinstance(config.get("test"), dict) else None
        declared_root = (root / src).resolve() if isinstance(src, str) and src else None
        add(app or root_app, app, spec_dir, layouts, config, declared_root)

    def add_from_discovered_config(name: str, app: str | None, start: Path, default_spec_dir: Path) -> None:
        """A root or flow group with no unit root: derive the config the way
        the test tree does (walk-up, then the `tests/<app>` sibling) instead
        of assuming none. Without this a run that is not given unit roots
        drew from spec stems alone — no layouts in the id space, so a layout
        id and a spec file name that normalize alike were never seen as one
        screen, and the check reported a transition the spec does declare."""
        config, cfg_path = (None, None)
        if project_config is not None:
            config, cfg_path = project_config.find_project_config(start)
        if isinstance(config, dict) and cfg_path:
            root = Path(cfg_path).parent
            spec_rel = config.get("spec_directory")
            spec_dir = (root / spec_rel).resolve() if isinstance(spec_rel, str) and spec_rel else default_spec_dir
            layouts = layouts_override
            if layouts is None:
                layouts_rel = config.get("layouts_directory")
                if isinstance(layouts_rel, str) and layouts_rel:
                    layouts = (root / layouts_rel).resolve()
            src = (config.get("test") or {}).get("src") if isinstance(config.get("test"), dict) else None
            declared_root = (root / src).resolve() if isinstance(src, str) and src else None
            add(name, app, spec_dir, layouts, config, declared_root)
        else:
            add(name, app, default_spec_dir, layouts_override, None)

    if not owners:
        add_from_discovered_config(root_app, None, input_path, docs_base / "screens" / "json")
    for group in flow_groups:
        if group:
            add_from_discovered_config(group, group, input_path / group, docs_base / group / "screens" / "json")
    return owners


def generate_html_directory(
    input_dir: Path,
    output_dir: Path,
    title: str = "JsonUI Test Documentation",
    docs_dirs: list[Path] | None = None,
    figma_dir: Path | None = None,
    apps: list[dict] | None = None,
    layouts_dir: Path | None = None,
    project_root: Path | None = None,
    unit_roots: list[dict] | None = None,
    test_roots: list[dict] | None = None,
    manifest_roots: list[dict] | None = None,
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
        project_root: Directory holding jui.config.json. Required for the Unit
            Tests section — `unitContracts` are read from `spec_directory` and
            compared against the per-platform `unitTestsDir`, both declared
            there. Omitted, the section is skipped and the rest is unaffected.
        manifest_roots: Every root whose generation manifest this run
            records into, `{'app': name, 'root': dir}` each — the CLI
            resolves them (`--config`, else every app with a config, else
            the walk-up). When omitted, `project_root` alone is written,
            which is the single-tree spelling and the historical one.
        unit_roots: For a split tree, one `{'app': name, 'root': dir}` per
            place contracts are declared, because such a project keeps each
            app's spec config beside the app rather than at the repository
            root. Takes precedence over `project_root`, which stays the
            single-root spelling.

    Returns:
        List of generated file info dicts with 'name', 'path', 'type', 'cases'
    """
    generator = DocumentGenerator()
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # One run, one tally: the CLI reads these back to decide the exit code.
    reset_page_failures()
    # Captured before anything is written: pages touched after this
    # belong to this run, whatever the tally says (see _report_stale_pages).
    started_at = time.time()

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

    # The run's own tree is an app like any other; it just never had a name.
    #
    # `docs_base` is `<input>/../docs`, so a repo whose run is rooted at one
    # app's tests has docs_base == that app's docs_path. The root pass then
    # read the SAME directory as the --app pass and wrote a second copy of the
    # pages under `specs/` and `components/`, which the sidebar rendered flat,
    # at the top, under the PROJECT's name while holding ONE app's contents.
    # Comparing the resolved directories is what tells the duplicate from a
    # genuine project-level docs tree; the names cannot, because the root has
    # none. Measured 2026-09-09 on a four-app repo: 55 specs and 8 components
    # rendered twice, and `docs/html/specs/` was a second copy on disk.
    _root_app = None
    for _app_info in (apps or []):
        if Path(_app_info['docs_path']).resolve() == docs_base.resolve():
            _root_app = _app_info['name']
            break
    _root_is_duplicate = _root_app is not None
    if _root_app is None:
        # A single-app project gets a folder too — the shape must not change
        # with the number of apps, or the reader learns a different site each
        # time one is added.
        _root_app = docs_base.parent.name or title

    # Pre-generate spec and component documentation (HTML and MD)
    spec_json_dir = docs_base / "screens" / "json"
    component_json_dir = docs_base / "components" / "json"

    if spec_json_dir.exists() or component_json_dir.exists():
        print("Pre-generating specification documentation...")
        _pre_generate_spec_docs(docs_base, layouts_dir=layouts_dir)

    # Collect all test files, from the run's own tests directory and from every
    # app that declared one.
    #
    # 🚨 ONE INPUT DIRECTORY WAS SCANNED, AND `--app` BROUGHT ONLY SPECS AND
    # COMPONENTS. Measured on a consumer tree 2026-09-09, from the generated
    # site rather than from this source: the sidebar's Flow Tests (61) and
    # Screen Tests (15) were exactly the input directory's own 61 flow + 15
    # screen tests, on EVERY app's page — and the other two apps' 14 and 41
    # screen tests had no page at all. A reader on one app's page was shown
    # another app's tests because those were the only ones that existed.
    #
    # ⚠️ THE FIRST THREE DIAGNOSES OF THIS WERE WRONG, all read off the source:
    # "only one of three sidebar functions is per-app" (the renderer is one
    # function and already groups), then "the nav does not pass `group`" (it
    # does, generator.py's nav dict sets it), then "`_test_group` reads the app
    # off the path and the path has no app segment" (true, and still not the
    # defect). The counts settled it: 61 + 15 = 76 = one app's whole corpus.
    #
    # The app's root comes from its OWN declaration — `test.src` in the config
    # beside its docs — not from a path guess, for the same reason unit roots
    # do: a directory named `tests` next to `docs` is a convention, and this
    # file should not be the place that convention is enforced.
    # 🔻 THE RUN'S OWN ROOT KEEPS ITS NAME. It used to be pinned to None and
    # the matching declaration was skipped whole, so the app the run was
    # pointed at lost its name while every other app kept one — from the same
    # `test_roots` list, in the same call.
    #
    # The consequence is one section further on: `unit` resolves its roots
    # elsewhere and preserves the name, so on a real site one app's unit pages
    # sit under its own segment while its screen and flow pages sit flat, next
    # to nobody. 76 of 131 pages on one tree.
    #
    # ⚠️ MECHANISM CONFIRMED, SOLE CAUSE NOT MEASURED. That this is the only
    # reason the two sections differ is not something anyone has shown; what
    # was measured is that the names match one app's whole corpus exactly and
    # that `unit` keeps what this discarded.
    own_app = next(
        (entry.get("app") for entry in (test_roots or [])
         if Path(entry["root"]).resolve() == input_path.resolve()),
        None,
    )
    roots: list[tuple[Path, str | None]] = [(input_path, own_app)]
    for entry in (test_roots or []):
        root = Path(entry["root"])
        if root.resolve() == input_path.resolve():
            continue  # the run's own tests, already first in the list
        if root.is_dir():
            roots.append((root, entry.get("app")))

    test_files: list[tuple[Path, Path, str | None]] = []
    for root, app_name in roots:
        for f in root.rglob("*.test.json"):
            test_files.append((f, root, app_name))

    if not test_files:
        raise ValueError(f"No .test.json files found in {input_dir}")

    generated_files = []

    # First pass: collect all file info
    file_infos = []
    used_test_paths: set[Path] = set()
    for test_file, test_root, test_app in sorted(test_files, key=lambda t: t[0]):
        try:
            result = generator.validator.validate_file(test_file)
            if not result.is_valid:
                # The third site with this shape, found while measuring the
                # other two. A test file that will not validate drops its
                # page from the index and leaves last run's copy on disk,
                # and the run still exited 0. No placeholder here: the page
                # path is derived from `test_data` this file could not
                # supply, and a leftover under `-o` is named by
                # `_warn_about_leftovers`, which spec pages (written outside
                # `-o`) do not get.
                record_page_failure(
                    'test', test_file.name,
                    _validation_failure_text(result),
                    source=test_file, indent="  ")
                continue

            test_type = result.test_data.get('type', 'unknown')
            if test_type == 'screen':
                subdir = 'screens'
            elif test_type == 'flow':
                subdir = 'flows'
            else:
                subdir = 'other'

            rel_path = test_file.relative_to(test_root)
            # A file from an app root is grouped by the app that DECLARED it;
            # only the run's own tree falls back to reading the app off the
            # path. `_test_group` returning "" is correct for a single-app
            # tree and says nothing about an app whose tests live elsewhere.
            group = test_app or _test_group(rel_path)
            html_filename = rel_path.with_suffix('.html').name
            html_dir = Path(subdir) / group if group else Path(subdir)
            html_rel_path = html_dir / html_filename

            # Collision guard: only the file name survived the path above, so
            # two tests sharing one could silently overwrite each other's page
            # — a whole app's worth of documentation went missing that way.
            # Grouping separates the apps; this catches what is left, two
            # equally named tests inside one app.
            if html_rel_path in used_test_paths:
                safe = "_".join(rel_path.parts[:-1]).replace("/", "_") or "dup"
                html_rel_path = html_dir / f"{safe}_{html_filename}"
                warn(
                    f"  WARNING [doc-collision]: output name collision for {test_file} "
                    f"— writing {html_rel_path}"
                )
            used_test_paths.add(html_rel_path)

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
                'group': group,
                'type': test_type,
                'case_count': len(cases) if cases else 0,
                'step_count': len(steps) if steps else sum(len(c.get('steps', [])) for c in cases),
                'platform': result.test_data.get('platform', 'all'),
                'document': source.get('document'),
            })
        except Exception as e:
            record_page_failure('test file', test_file.name, e,
                                source=test_file, indent="  ")

    # Build documents list from file_infos that have document paths
    document_files = []
    for f in file_infos:
        if f.get('document'):
            document_files.append({
                'name': f['name'],
                # Same rule as the writer, from the same function. A page
                # moved without its links is a worse state than the one this
                # repairs: the collision was at least visible in the output.
                'path': document_output_rel_path(
                    f.get('group') or None, f['document']),
                # 🚨 WITHOUT THIS THE RENDERER HAS NOTHING TO GROUP BY. The
                # sidebar's Documents lists were rewritten to go through
                # `_render_tests_sidebar_section`, which nests by `group` — and
                # that alone changes nothing, because these entries carried
                # only name and path while `file_infos` had the group all
                # along. Two halves; either one alone is invisible.
                'group': f.get('group', ''),
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
                            warn(
                                f"  WARNING [doc-collision]: output name collision for "
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
    # Loaded HERE, above `all_tests_nav`, because every page's sidebar now
    # carries the Unit Tests section and the screen and flow pages are
    # written before any unit page exists. See `_unit_nav_entries` for why
    # the sidebar is built from the DECLARED targets rather than the written
    # ones. Pure reads — `normalise_unit_roots` and `_load_unit_contract_pages`
    # take only arguments, so nothing between here and the old position fed it.
    #
    # One entry per place unitContracts are declared. A split tree keeps each
    # app's spec config beside the app, so there is no single root to walk up
    # to — see `normalise_unit_roots`.
    unit_by_app: dict[str | None, dict] = {}
    for _entry in normalise_unit_roots(unit_roots, project_root):
        _pages = _load_unit_contract_pages(_entry["root"])
        if _pages is not None:
            unit_by_app[_entry["app"]] = _pages

    all_tests_nav = {
        'screens': [{'name': f['name'], 'path': f['path'].as_posix(), 'group': f['group']} for f in file_infos if f['type'] == 'screen'],
        'flows': [{'name': f['name'], 'path': f['path'].as_posix(), 'group': f['group']} for f in file_infos if f['type'] == 'flow'],
        'documents': document_files,
        'api_docs': [{'name': d['name'], 'path': d['path'], 'subdir': d.get('subdir', '')} for d in all_api_doc_files],
        'api_doc_categories': {k: [{'name': d['name'], 'path': d['path'], 'subdir': d.get('subdir', '')} for d in v] for k, v in api_doc_categories.items()},
    }

    # The Unit Tests section belongs to EVERY page's sidebar (user ruling
    # 2026-09-05). It used to be a local copy handed only to the unit pages,
    # deliberately, so the section would not appear on screen, flow and spec
    # pages — the reader then had no way to reach a unit page except the
    # index body, and read the site as having no hand-written tests at all.
    # That is the report this reverses.
    _unit_nav = _unit_nav_entries(unit_by_app)
    if _unit_nav:
        all_tests_nav['units'] = _unit_nav

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
            generator._current_test_path = html_rel_path.as_posix()
            content = generator._generate_html(result)

            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # Add to generated files (without internal fields)
            generated_files.append({
                'name': file_info['name'],
                'description': file_info['description'],
                'path': html_rel_path,
                'group': file_info['group'],
                'type': file_info['type'],
                'case_count': file_info['case_count'],
                'step_count': file_info['step_count'],
                'platform': file_info['platform'],
                'document': file_info.get('document'),
            })

            note_page_generated(html_path, indent="  ")

        except Exception as e:
            record_page_failure('test page', str(file_info['test_file']), e,
                                source=file_info['test_file'],
                                output=html_path, indent="  ")

    # Generate Mermaid diagrams — ONE PER APP.
    #
    # There used to be a single `diagram.html` built from the run's own flows
    # and linked at the top of the sidebar, outside every app. In a repo
    # holding several apps that diagram is one app's flow graph wearing the
    # project's name, and the other apps had no diagram at all. The flows are
    # already separated on disk (`_test_group` reads the app off the path and
    # the pages are written to `flows/<app>/`), so the split costs one call
    # per group rather than any new declaration.
    mermaid_generated = False
    app_diagrams: dict[str, str] = {}
    flow_groups = sorted({
        f.get('group', '') for f in file_infos if f['type'] == 'flow'
    })
    # Ruled 2026-09-10: drawn from the SPECS, one diagram per spec-bearing
    # app; the flow tests are checked against it. A flow group with no spec
    # directory anywhere gets a WARNING, not a diagram — its transitions
    # cannot be checked against a spec that does not exist.
    owners = _diagram_owners(
        input_path, unit_roots, project_root, docs_base, layouts_dir, _root_app, flow_groups,
        test_roots=test_roots)
    covered_groups = {o["app"] or "" for o in owners}
    for _group in flow_groups:
        if _group not in covered_groups:
            _flows, _screens = (input_path / _group if _group else input_path), None
            n_flows = len(list(_flows.rglob("*.test.json")))
            warn(f"  WARNING [doc-diagram]: no spec directory found for {_group or _root_app} "
                 f"— no diagram drawn and {n_flows} flow test file(s) not checked against a spec")
    for owner in owners:
        _owner = owner["name"]
        try:
            _out = output_path / owner["rel"]
            _out.parent.mkdir(parents=True, exist_ok=True)
            result = generate_mermaid_html(
                owner["spec_dir"], _out, "Flow Diagram", owner["screens_dir"], owner["layouts_dir"],
                flows_dir=owner["flows_dir"], aliases=owner["aliases"],
                app_owned=owner["app_owned"], app_owned_transitions=owner["app_owned_transitions"],
                site_root=output_path,
            )
            for err in result.errors:
                print(f"  ERROR [doc-diagram]: {_owner}: {err}")
                _diagram_errors.append({
                    "owner": _owner, "from": err.from_id, "to": err.to_id,
                    "flow": err.flow_name, "file": err.flow_file, "reason": err.reason,
                })
            for winner, entries in result.id_collisions:
                named = " and ".join(f"'{raw}' ({source})" for raw, source in entries)
                warn(f"  WARNING [doc-diagram]: {_owner}: ids {named} normalize to the same key; "
                     f"drawn as '{winner}' — rename the spec (or layout) so one screen has one id")
            if result.unresolved:
                listed = "; ".join(f"{u.source}: {u.raw!r}" for u in result.unresolved[:6])
                more = "" if len(result.unresolved) <= 6 else f"; +{len(result.unresolved) - 6} more"
                warn(f"  WARNING [doc-diagram]: {_owner}: {len(result.unresolved)} of "
                     f"{result.stats.get('transitions', 0)} spec destination(s) could not be "
                     f"resolved and were treated as absent: {listed}{more}")
            if result.combined:
                note_page_generated(_out, indent="  ")
                app_diagrams[_owner] = owner["rel"]
                if not owner["app"]:
                    mermaid_generated = True
                if owner["tests_provenance"] == "absent: declared":
                    flows_clause = (f"no test root for {_owner} (declared {owner['test_root']} absent), "
                                    f"nothing checked")
                elif owner["tests_provenance"] == "absent: nothing declared":
                    flows_clause = (f"no test root for {_owner} (nothing declared; {owner['test_root']} absent), "
                                    f"nothing checked")
                else:
                    flows_clause = (f"flow tests {result.stats.get('flow_tests', 0)} in "
                                    f"{owner['flows_dir']} ({owner['tests_provenance']}) checked "
                                    f"{result.stats.get('flow_edges', 0)} transition(s), absent "
                                    f"{result.stats.get('absent', 0)}")
                print(f"    diagram {_owner}: specs {result.stats.get('specs', 0)} / "
                      f"transitions {result.stats.get('transitions', 0)} / "
                      f"spec edges {result.stats.get('spec_edges', 0)} (all in the All tab) / "
                      f"none inferred from wording {result.stats.get('none_inferred', 0)} / "
                      f"{flows_clause}")
            else:
                print(f"  Skipped: flow diagram — no spec under {owner['spec_dir']} declares a "
                      f"resolvable screen transition ({_owner})")
        except Exception as e:
            warn(f"  WARNING [doc-diagram]: could not generate Mermaid diagram for "
                 f"{_owner}: {e}")

    # Generate index.html
    generate_index_html(output_path, generated_files, title, mermaid_generated, document_files, api_doc_categories)

    # Generate Swagger/OpenAPI documentation pages
    _generate_swagger_pages(output_path, all_api_doc_files, all_tests_nav, api_doc_categories)

    # Contract-check pages (rendered only when a report artifact exists)
    _generate_check_report_pages(output_path, check_report_pages, api_doc_categories)

    # Generate screen specification HTML pages from docs directories
    spec_files_info = []
    component_files_info = []
    # Loaded before the spec pages are written so each spec that declares
    # `unitContracts` can link to its target's page; the pages themselves are
    # written after, when the spec pages they link back to exist.
    # One entry per place unitContracts are declared. A split tree keeps each
    # app's spec config beside the app, so there is no single root to walk up
    # to — see `normalise_unit_roots`.
    unit_pages = unit_by_app.get(None)
    unit_pages_by_target = _unit_pages_by_target(unit_pages, None)
    # Include screens/json and components/json directories for spec pages
    spec_search_dirs = list(unique_docs_dirs)
    if spec_json_dir.exists():
        spec_search_dirs.append(spec_json_dir)
    if component_json_dir.exists():
        spec_search_dirs.append(component_json_dir)
    if spec_search_dirs and _root_is_duplicate:
        # The --app pass reads this very directory and writes the pages under
        # the app's own prefix. Running it here as well produced `specs/` and
        # `components/` as a second copy with different relative links.
        print(f"  Skipped: root specs/components are {_root_app}'s (--app covers this directory)")
        spec_search_dirs = []
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
            layouts_dir=layouts_dir, unit_pages_by_target=unit_pages_by_target,
        )

    # Unit contract pages. After the spec pages, because each target links to
    # the spec that declares it and the link is built from the pages this run
    # actually wrote.
    #
    # "After the spec pages" held for the root scope only. An app's spec
    # pages are written further down, so an app-scoped project reached here
    # with an EMPTY list and every one of its targets missed — 0 of 19 on the
    # face that reported it. The app pages are therefore COLLECTED here,
    # before the unit pages that link to them; collect_only writes nothing
    # and prints nothing, so no page moves and the write order is unchanged.
    # `_unit_spec_href` picks its own app's subset out of the combined list.
    spec_pages_all = list(spec_files_info)
    for app_info in apps or []:
        app_docs_path = Path(app_info['docs_path']).resolve()
        app_dirs = [
            app_docs_path / sub for sub in
            ("screens/json", "components/json", "requirements/json")
            if (app_docs_path / sub).exists()
        ]
        if not app_dirs:
            continue
        _app_specs, _ = _generate_spec_pages(
            app_dirs, output_path, collect_only=True,
            path_prefix=app_info['name'], layouts_dir=layouts_dir,
        )
        spec_pages_all.extend(_app_specs or [])

    unit_files_info: list[dict] = []
    unit_app_summaries: list[tuple[str, str]] = []
    unit_undeclared: dict[str, list[str]] = {}
    for _app, _pages in sorted(unit_by_app.items(), key=lambda kv: (kv[0] or "")):
        _files, _summary, _undeclared = _generate_unit_pages(
            _pages, output_path, spec_pages_all, all_tests_nav, app=_app
        )
        unit_files_info.extend(_files)
        # An app's targets are grouped under its name, the same level the
        # index already uses for a multi-app project.
        for _f in _files:
            if _app:
                _f["group"] = _app
        if _summary:
            unit_app_summaries.append((_app or "", _summary))
        for _face, _names in (_undeclared or {}).items():
            unit_undeclared.setdefault(_face, []).extend(_names)
    # ONE app's line is not the run's line. This used to keep the first
    # summary it saw, so on a multi-app site the index reported whichever app
    # sorted first — and when that app declared nothing, the page carried
    # `0 case(s) declared` four lines under `Unit Targets 5`. A denominator
    # exists to stop a zero being mistaken for "nothing to find"; picking one
    # app's zero out of several does exactly the harm it was added to prevent.
    #
    # Summed and worded by `jsonui_test_cli`, which owns the sentence for a
    # single scan too. Composing it here as well would put one fact in two
    # places, and the per-app lines below print that function's output
    # verbatim — so both halves of the page now come from one speller.
    from jsonui_test_cli.unit_contracts import aggregate_unit_totals
    _run_totals = aggregate_unit_totals(
        [(p.get("totals") or {}) for p in unit_by_app.values()])
    unit_summary = _run_totals["summary_line"] if unit_by_app else None

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
                        unit_pages_by_target=_unit_pages_by_target(
                            unit_by_app.get(app_name), app_name),
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

    # Document pages LAST of the page writers. Each one embeds the body of a
    # page from the source tree, and that body's own links have to be rewritten
    # to the pages THIS run wrote — so those pages have to exist first. It used
    # to run before the spec and component pages and could only have reapplied
    # a layout rule, which is the defect this repair removes.
    #
    # ⚠️ Their sidebar therefore carries the full navigation now (specs,
    # components, units, apps) where before it carried only what had been
    # collected by that earlier point. That is a byte change on every document
    # page, and it makes them consistent with every other page in the site.
    # The map is built from `roots`, which already pairs each declared test
    # directory with the app that declared it. Nothing new is declared here —
    # the asset existed and this call site simply was not reading it, which is
    # the same shape v1.8.63 repaired one function away.
    _generate_document_pages(
        input_path, output_path, generated_files, all_tests_nav,
        roots_by_app={app: root for root, app in roots},
    )

    # Re-generate index.html with updated navigation (if specs, components, markdown, figma, or apps were added)
    # `unit_files_info` is part of the condition rather than assumed to ride
    # along with `spec_files_info`: unitContracts are read from
    # `spec_directory` in jui.config.json, while the spec PAGES come from the
    # docs directory that was scanned. Those are usually the same tree and are
    # not required to be, and when they are not, the section would be built
    # and then never rendered.
    if (spec_files_info or component_files_info or md_files_by_dir
            or figma_files_info or apps_nav or unit_files_info):
        generate_index_html(output_path, generated_files, title, mermaid_generated, document_files, api_doc_categories, spec_files_info, component_files_info, md_files_by_dir, figma_files_info, apps_nav=apps_nav, unit_files=unit_files_info, unit_summary=unit_summary, unit_undeclared=unit_undeclared, unit_app_summaries=unit_app_summaries, root_app=_root_app, app_diagrams=app_diagrams)

    # Recorded here, once, where every number is in scope. Summed across
    # roots: a split tree reads a config per app, and the closing line names
    # the run rather than any one of them.
    note_generation_counts(
        screens=sum(1 for f in generated_files if f.get('type') == 'screen'),
        flows=sum(1 for f in generated_files if f.get('type') == 'flow'),
        unit_targets=len(unit_files_info),
        unit_scanned=bool(unit_by_app),
        specs_read=sum((p.get('totals') or {}).get('specs_scanned', 0)
                       for p in unit_by_app.values()),
        specs_declaring=sum((p.get('totals') or {}).get('specs_declaring', 0)
                            for p in unit_by_app.values()),
        specs_unreadable=_run_totals.get('specs_unreadable', 0),
        unreadable_files=sorted(_run_totals.get('unreadable_files') or []),
    )

    # Both of these were called for their printing and their results thrown
    # away. The printing reaches whoever is watching; the record reaches the
    # next question. One face shipped 64 unreachable pages that this exact
    # call had already named.
    stale = _report_stale_pages(output_path, started_at)
    outside = _report_writes_outside_output(output_path)
    stale_outside = _report_stale_pages_outside(output_path, started_at)
    _record_generation_manifest(
        output_path,
        [{"app": e.get("app"), "root": Path(e["root"]), "docs": e.get("docs")} for e in manifest_roots]
        if manifest_roots else project_root,
        stale, outside, slots=dict(_document_slot_facts), stale_outside=stale_outside)

    return generated_files


#: An `href` in an embedded body, either spelling. The generator uses BOTH
#: (nav writes `'`, the component table writes `"`), so a scan that picks one
#: silently drops the other — that is how the body links were reported as
#: "0 present" on 2026-09-08.
_BODY_HREF = re.compile(r"""(href\s*=\s*)(['"])([^'"]+)\2""", re.I)


def _app_of_embedded_page(page_path: Path, output_path: Path) -> str | None:
    """The app an embedded body belongs to: `docs/<app>/...` under the site.

    Returns None when the page is not under a `docs/<app>/` prefix, which is
    how a single-app layout reaches this — and there the basename is already
    unambiguous, so nothing is lost.
    """
    try:
        parts = page_path.resolve().relative_to(Path(output_path).resolve()).parts
    except (ValueError, OSError):
        return None
    if len(parts) >= 2 and parts[0] == "docs":
        return parts[1]
    return None


def _app_of_component_page(written_page: Path) -> str | None:
    """The app a written component page belongs to: `<app>/components/<name>`.

    Read from the segment BEFORE `components`, so it holds for both the site
    layout and any nesting above it.
    """
    parts = written_page.parts
    for i, seg in enumerate(parts):
        if seg == "components" and i >= 1:
            return parts[i - 1]
    return None


def _component_body_rewriter(page_path: Path, output_path: Path):
    """Rewrite component links in an embedded body to the pages THIS run wrote.

    The body comes from `docs/<app>/screens/html/`, where
    `../../components/html/<name>.html` is correct. Embedded at
    `<site>/docs/<app>/screens/html/`, the same href points at a directory the
    site never writes — the site's component pages are at
    `<site>/<app>/components/<name>.html`.

    Resolution is by BASENAME against the set of pages actually written, and
    only when exactly one candidate matches. Zero means the run wrote no page
    for that component and the link is left alone rather than pointed
    somewhere plausible.

    More than one used to mean the same thing, on the reasoning that "guessing
    would be worse than the dangling link, which at least fails loudly when
    someone clicks it." ⚠️ That reasoning assumed the app was unknown. It is
    not: this page sits at `docs/<app>/screens/html/`, and each app writes its
    own `<app>/components/<name>.html`. Choosing THIS page's app is not a
    guess — it is the only candidate the page could mean.

    🚨 Measured 2026-09-08 on the two-app specimen: the href was left as the
    source-tree `../../components/html/picker.html`, which resolves under the
    site to a directory the run never writes. So the branch that existed to
    avoid a wrong link was EMITTING a dangling one — while the sibling arm in
    the same file states the rule it broke ("a component with no page must
    render as text, not as a link nobody can follow"). Two rules for one
    situation, and the one that shipped was the unstated one.

    The old reason is kept where it still reaches: if the same app somehow
    offers two pages for one basename, nothing here can choose, and the link
    is left alone.
    """
    written = {
        w for w in get_written_pages()
        if "/components/" in str(w) and w.suffix == ".html"
    }
    # ⚠️ Resolved on BOTH sides. `note_page_generated` stores resolved paths,
    # and on macOS `/var` is a symlink to `/private/var` — mixing the two makes
    # relpath climb to the filesystem root and emit a link that is absolute in
    # everything but name. Caught by the arm that checks both quote spellings,
    # which printed the path.
    try:
        page_dir = page_path.parent.resolve()
    except OSError:
        page_dir = page_path.parent

    app = _app_of_embedded_page(page_path, output_path)

    def rewrite(body: str) -> str:
        def one(m):
            prefix, quote, href = m.group(1), m.group(2), m.group(3)
            if "components/" not in href or not href.endswith(".html"):
                return m.group(0)
            name = posixpath.basename(href)
            hits = [w for w in written if w.name == name]
            if len(hits) > 1 and app:
                # Narrow to THIS page's app before declining. See the docstring:
                # the app is known, so this is a selection, not a guess.
                same_app = [w for w in hits if _app_of_component_page(w) == app]
                if len(same_app) == 1:
                    hits = same_app
            if len(hits) != 1:
                return m.group(0)
            rel = os.path.relpath(hits[0], page_dir)
            return f"{prefix}{quote}{rel}{quote}"
        return _BODY_HREF.sub(one, body)

    return rewrite


def _report_writes_outside_output(output_path: Path) -> dict:
    """Name the directories this run wrote that are not under `-o`.

    From what was WRITTEN, not from a rule about where it would go — the same
    reason the unit and component links are built from the pages this run
    produced. A rule reapplied here would go stale the moment the layout
    changes, and this line exists precisely because nothing was telling the
    truth about the layout.

    Silent when there is nothing to name, so the common `generate spec` shape
    gains no line. When there IS something, the count of apps matters more
    than the paths: one run rewrites every `--app` tree, which is what broke
    two lanes' isolation without either of them being able to see it.
    """
    try:
        out = output_path.resolve()
    except OSError:
        out = output_path
    # 🔻 ONE DIRECTORY, ONE ENTRY, however it was spelled on the way in. The
    # root scope records `input_path.parent / "docs"` exactly as the run was
    # given it, and every `--app` records its docs path `.resolve()`d — so a
    # run pointed at an app that is ALSO passed as `--app` (the normal shape
    # for a face listing all of its apps) put one directory in this set twice,
    # once relative and once absolute, and the manifest said two directories
    # where there was one. Seen on a single face, because a single face spells
    # its input relatively; the others were not safe, they were not on the
    # path. Keyed by the real path here rather than normalised at each of the
    # writers, so a writer added tomorrow cannot reopen it.
    by_real: dict[Path, Path] = {}
    for d in _written_outside_output:
        try:
            real = d.resolve()
        except OSError:
            real = d
        by_real.setdefault(real, d)
    outside = sorted(
        real for real in by_real
        if not str(real).startswith(str(out) + "/")
    )
    if not outside:
        # The same shape, empty: "counted, found none" is a fact the record
        # states, never an absent key. One face read `leftovers` missing
        # beside `directories: []` and could not tell "zero" from "not
        # counted" — a file that teaches two conventions teaches neither.
        return {"directories": [], "gitTrackedDirectories": {},
                "gitModifiedDirectories": {}, "uncheckable": []}
    # Through the tally: the gate's expression counts `⚠`, so this line is a
    # warning whether or not it was written as one.
    warn(f"  ⚠️ Also written OUTSIDE {output_path} ({len(outside)} directories):",
         structural="outside-writes")
    for d in outside:
        print(f"       {d}")
    print("     Every --app passed to this run has its source tree rewritten, so "
          "two runs\n"
          "     with different -o are not isolated from each other: the last one "
          "to finish\n"
          "     leaves its version here.")

    # 🚨 THE PATHS ALONE DID NOT REACH THE PEOPLE WHO NEEDED THEM.
    #
    # Everything above was already printed on 2026-09-09 when one lane's
    # verification run, with four `--app` flags, rewrote ten files in another
    # lane's tree. The owning lane found them in `git status` and had to work
    # out who wrote them; nothing had told it, and the version that landed was
    # one it had not accepted. The help text names these paths, this notice
    # lists them, and neither of those is a message to the OWNER.
    #
    # ⚠️ So the line that matters is not "where" but "these are tracked, and
    # the tracking means someone else's next commit". A path under `.gitignore`
    # costs a regenerate; a tracked path costs a review, a revert, or a
    # silently committed artifact from a version nobody accepted.
    #
    # ⚠️ THREE STATES, NOT TWO. `git` absent, or the directory outside any
    # repository, is "cannot tell" — printed as such rather than folded into
    # "not tracked". A count of 0 from a working `git` is a fact; -1 is the
    # absence of the instrument, and they must not print the same.
    tracked, unknown = [], []
    modified: dict[Path, int] = {}
    for d in outside:
        n = _git_tracked_file_count(d)
        if n > 0:
            tracked.append((d, n))
            modified[d] = _git_modified_file_count(d)
        elif n < 0:
            unknown.append(d)
    if tracked:
        # 🔻 "WROTE INTO", THEN A MEASURED NUMBER. The first version said "this
        # run changed files another lane owns" from the tracked count alone,
        # which had never looked at a byte. On the reporting face all 38
        # tracked files came back identical and `git status` showed nothing;
        # the line sent that lane to review a change that did not exist. The
        # word "changed" is not used here at all — "differ" is, and only next
        # to the count that measured it.
        print(f"  🚨 {len(tracked)} of those are GIT-TRACKED — this run wrote into "
              f"files another lane owns:")
        for d, n in tracked:
            m = modified[d]
            state = (f"{m} now differ from the index" if m >= 0
                     else "could not tell whether any differ")
            print(f"       {d}  ({n} tracked file(s), {state})")
        differing = sum(m for m in modified.values() if m > 0)
        unmeasured = sum(1 for m in modified.values() if m < 0)
        # The owner is told in EVERY state. The write into their tree happened
        # whether or not a byte moved, and only they can say whether that was
        # acceptable; what changes with the state is what they are told. The
        # first draft said it only when files differed, and an arm written for
        # the 2026-09-09 incident — "called out by owner, not just listed" —
        # went red for the byte-identical case, which is the common one.
        if differing:
            print(f"     Tell the lane that owns them: {differing} tracked file(s) now "
                  "differ from the index and will show in\n"
                  "     their `git status` with no way to tell which run produced "
                  "them, or which version of the\n"
                  "     tools wrote them. (A change they had pending before this run "
                  "counts here too: this is a\n"
                  "     state, not an attribution.)")
        elif unmeasured:
            print("     Tell the lane that owns them: the write happened; whether any "
                  "byte moved could not be\n"
                  f"     measured here (git did not answer for {unmeasured} of the "
                  "tracked directories).")
        else:
            print("     Tell the lane that owns them: 0 tracked file(s) differ from the "
                  "index — every rewrite was\n"
                  "     byte-identical, so there is nothing to review. The write still "
                  "happened; a version that\n"
                  "     renders differently would have landed here.")
        if differing and unmeasured:
            print(f"     ⓘ {unmeasured} of the tracked directories could not be "
                  "checked for differences (git did not answer).")
    if unknown:
        print(f"  ⓘ {len(unknown)} could not be checked for tracking (no git, or "
              f"outside a repository).")
        for d in unknown:
            print(f"       {d}")
    # Returned as well as printed. The print reaches whoever is watching the
    # run; the return reaches the record. Until 2026-09-09 only the first
    # existed, and the caller discarded what its sibling returned — so the
    # stronger the message got, the more was lost when the terminal scrolled.
    return {
        "directories": [str(d) for d in outside],
        # 🚨 `gitTracked…`, not `tracked…`. The manifest already uses "tracked"
        # for a DIFFERENT quantity — `summary.tracked` and
        # `summary.trackedByDirectory` are files the MANIFEST tracks, nothing to
        # do with git. Shipping a git-sense `trackedDirectories` into the same
        # JSON put two meanings of one word in one file, and the reader who hit
        # it was reading the file, not this source. Reported by the admin face
        # the day it shipped.
        "gitTrackedDirectories": {str(d): n for d, n in tracked},
        # Per tracked directory: how many files now differ from the index, or
        # -1 when git did not answer — the same three values the printed line
        # carries, so the record cannot say "0" where the terminal said
        # "could not tell".
        "gitModifiedDirectories": {str(d): m for d, m in modified.items()},
        "uncheckable": [str(d) for d in unknown],
    }


def _record_generation_manifest(
    output_path: Path,
    project_root: Path | list | None,
    stale: list,
    outside: dict,
    slots: dict | None = None,
    stale_outside: list | None = None,
) -> None:
    """Write what this run did into `.jsonui-cli/generation-manifest.json`.

    `jui build` has recorded which version wrote each generated file since
    2026-09-03. This run did not, and the gap was not academic: answering
    "which version generated this page" for one face took four separate
    measurements — the page's own stamp (a time, no version), the bootstrap
    landing time, the shared checkout's reflog, and an enumeration of every
    generator reachable on the machine. A first sweep of that last one found
    one copy; there were five.

    THREE THINGS GO IN, because all three were being lost the same way:
    the pages written, the leftovers found, and the directories written
    outside `-o`. The middle one is why this exists — one face was shipping
    64 pages nothing linked to, and the run that detected them printed the
    list, discarded the return value, and exited 0. The third was enriched
    the same day with git-tracked counts, which raised what a scrolled
    terminal costs rather than lowering it.

    🚫 SAYS NOTHING ABOUT GATES. This writes a record and nothing else — no
    exit code, no promise about what any check will do with it. The line
    above it in this file used to carry exactly that kind of promise in
    `jui build` ("not counted toward the zero-warnings gate"), reasoning
    from a tally that did not exist; it was corrected on 2026-09-09. A new
    printer is the moment that trap gets rebuilt, so this one describes only
    what it did.

    Silent when it cannot write, in the sense of `shared_core.load`'s own
    contract — "the caller says what it is skipping". The two reasons are
    kept apart because they call for different responses: no project root is
    this run's own scope, and no `shared/core` is the tree it was installed
    into. ⚠️ The second reaches a real population: `shared/` is not part of
    the pip distribution (`include = ['jsonui_doc_cli*']`), so a face that
    installed the doc tool from a bare pip has no manifest and this notice is
    the only thing that says so.
    """
    # One root or several: a site run over N apps writes the SAME run record
    # into every app root that has a config (2026-09-10). Before that the
    # first app's manifest got everything and the others could never hold
    # `summary.run`, which the v1.8.66 notice had told them to read.
    if isinstance(project_root, list):
        targets = [{"app": e.get("app"), "root": Path(e["root"]), "docs": e.get("docs")}
                   for e in project_root]
    elif project_root is not None:
        targets = [{"app": None, "root": Path(project_root)}]
    else:
        targets = []
    if not targets:
        print("  ⓘ NOTE: no project root for this run, so nothing was recorded "
              "in .jsonui-cli/generation-manifest.json — not a statement that "
              "there was nothing to record.")
        return
    from .. import shared_core
    manifest = shared_core.load("generation_manifest")
    if manifest is None:
        print("  ⓘ NOTE: shared/core/generation_manifest.py is not in this tree, "
              "so this run recorded nothing about itself. Pages, leftovers and "
              "writes outside -o all went to this output and nowhere else.")
        return

    from ..reproducible import build_datetime_utc
    # One stamp for every target, so the copies of one run agree to the
    # second — a reader compares them across faces. Through `reproducible`,
    # like every other stamp this package writes.
    recorded_at = build_datetime_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    for target in targets:
        _record_into(target, targets, manifest, stale, outside, slots, recorded_at,
                     stale_outside or [])


def _git_toplevel(root: Path) -> "Path | None":
    """The repository that holds `root`, or None when there is none to ask."""
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        return Path(out.stdout.strip()).resolve()
    except OSError:
        return None


def _relative_to_root(directories: list, root: Path) -> list:
    """Each directory relative to `root`, with `../` where that is what the
    layout is. None only when no relative form exists at all (another drive).

    ⚠️ Until 1.8.68 this returned None for anything outside the REPOSITORY
    holding `root`, on the reasoning that a sub-repository is its own
    repository and that is what its face commits. Measured on the face that
    asked for the key: its manifest root is a submodule and its `--app` docs
    live in the parent repository, so every entry came back None and the
    ticket's own problem — a tracked manifest full of machine-specific
    absolute paths — was not solved for the face that reported it. The
    relative form is never WORSE than the absolute one for that purpose:
    `../docs/<face>/screens/html` survives a clone at another path, an
    absolute path does not. So it is emitted, and whether it leaves the
    repository is said in its own key rather than by erasing the value.
    (2026-09-10, filed after 1.8.68 shipped; see
    `directoriesRelative-is-null-for-every-submodule-face-…`.)"""
    base = str(Path(root).resolve())
    out: list = []
    for d in directories:
        try:
            out.append(os.path.relpath(str(Path(d).resolve()), base))
        except (OSError, ValueError):
            # No relative form exists (a different drive on Windows). Not the
            # same as "outside the repository", which now has its own key.
            out.append(None)
    return out


def _outside_repo_flags(directories: list, root: Path) -> list:
    """For each directory, whether it lies outside the repository holding
    `root` — index-aligned with `directories` and `directoriesRelative`.

    This carries what the None used to carry, without destroying the path.
    A face that clones only its own sub-repository cannot reach a `true`
    entry from that clone; a face whose tree is one repository sees all
    `false`. A sub-repository is its own repository here."""
    top = _git_toplevel(root) or Path(root).resolve()
    flags: list = []
    for d in directories:
        try:
            Path(d).resolve().relative_to(top)
            flags.append(False)
        except (OSError, ValueError):
            flags.append(True)
    return flags


def _under_any(p, scopes: list) -> bool:
    try:
        real = Path(p).resolve()
    except OSError:
        return False
    for sc in scopes:
        try:
            real.relative_to(Path(sc).resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


def _scope_outside(outside: dict, scopes: list) -> dict:
    """The outside-writes record restricted to the face's own directories.

    `scopes` is the face's config root plus its `--app` directory: a split
    tree keeps the docs OUTSIDE the root (one face's docs sit under the
    parent repository's docs/), and those docs are exactly what the run
    writes. Scoped to the root alone, both faces of such a tree would have
    read an empty list — an absence wearing the face of zero. Lists keep the
    entries under any scope, dicts keep the keys under any scope, and the
    block names its scopes.
    """
    roots = []
    for sc in scopes:
        try:
            roots.append(Path(sc).resolve())
        except OSError:
            roots.append(Path(sc))

    def under(p) -> bool:
        try:
            real = Path(p).resolve()
        except OSError:
            return False
        for r in roots:
            try:
                real.relative_to(r)
                return True
            except ValueError:
                continue
        return False
    scoped: dict = {}
    for key, value in outside.items():
        if isinstance(value, list):
            scoped[key] = [d for d in value if under(d)]
        elif isinstance(value, dict):
            scoped[key] = {d: n for d, n in value.items() if under(d)}
        else:
            scoped[key] = value
    scoped["scope"] = [str(r) for r in roots]
    # The run also wrote outside this scope — another face's tree, or a tree
    # in another repository. Counted, not listed: the fact survives in every
    # block (one run rewrites several lanes' trees, which is what broke two
    # lanes' isolation), while the paths, which are another face's and
    # machine-specific, stay in that face's own block and in the run's log.
    scoped["elsewhere"] = sum(1 for d in (outside.get("directories") or []) if not under(d))
    return scoped


def _record_into(target: dict, targets: list, manifest, stale: list, outside: dict,
                 slots: dict | None, recorded_at: str, stale_outside: list) -> None:
    """Write this run's record into ONE root's manifest; see the caller."""
    root = Path(target["root"]).resolve()
    scopes = [root] + ([Path(target["docs"])] if target.get("docs") else [])

    def _key(p) -> str | None:
        try:
            return str(Path(p).resolve().relative_to(root))
        except ValueError:
            # Written outside the project being recorded. Counted by the
            # outside-writes block instead of silently filed under a key
            # that would resolve to a different tree on the next run.
            return None

    written = sorted(k for k in (_key(p) for p in get_written_pages()) if k)
    facts = {}
    # Explicit zero, like `outsideOutput.directories: []`: the run counted and
    # found none. A missing key means the record predates the key.
    facts["leftovers"] = len(stale)
    facts["leftoverPaths"] = [str(p) for p in stale[:20]]
    if len(stale) > 20:
        facts["leftoverPathsNote"] = f"first 20 of {len(stale)}"
    # Leftovers in the directories this run wrote OUTSIDE -o — a renamed spec's
    # old pages — under this face's scope, like outsideOutput. A face whose
    # docs tree another face shares counts the same file too: each block is
    # that face's view, and the paths say which file it is.
    mine = [(p, copies) for p, copies in stale_outside if _under_any(p, scopes)]
    facts["leftoversOutside"] = len(mine)
    # The scan looked at every directory the run wrote outside -o; this block
    # only lists the ones under THIS face's scope. Counted, not listed, like
    # `outsideOutput.elsewhere` — otherwise a scoped 0 reads as "the scan
    # found nothing" when the scan found several and filed them elsewhere.
    # Measured on a single-root run where the console said 3 pages and the
    # manifest said 0, which is exactly what the one-convention-for-zero
    # ruling (1.8.68) says a 0 must never mean. The console's count is
    # `leftoversOutside + leftoversOutsideElsewhere`.
    facts["leftoversOutsideElsewhere"] = len(stale_outside) - len(mine)
    # …and how many directories the scan walked to get there. A zero with a
    # zero denominator is not the same answer as a zero with a denominator.
    facts["leftoversOutsideScanned"] = _stale_outside_scanned
    facts["leftoverOutsidePaths"] = [str(p) for p, _c in mine[:20]]
    facts["leftoverOutsideSiteCopies"] = [str(c) for _p, copies in mine[:20] for c in copies]
    facts["leftoverOutsideReferencedBy"] = {
        str(p): len(_document_referrers.get(Path(p).resolve(), [])) for p, _c in mine[:20]}
    if len(mine) > 20:
        facts["leftoverOutsidePathsNote"] = f"first 20 of {len(mine)}"
    if outside:
        # Several roots: each face's block names writes into ITS tree, with
        # an explicit empty list when there were none — one face's block used
        # to carry four faces' directories, and the other three had no block
        # at all. One root: the run-level record, unchanged.
        # Always scoped and always named, one root or many: a block without
        # `scope` read as "unrestricted" beside blocks that had it (measured on
        # one face's single-root run next to a four-root run, same version).
        block = _scope_outside(outside, scopes)
        # The same directories relative to THIS manifest's root, beside the
        # absolute ones. The manifest is a tracked file on some faces, and
        # an absolute path makes it machine-specific: a clone at another
        # path rewrites every line on its first run. Relative to the root —
        # `../docs/<face>/…` on a split tree, which is not a defect but the
        # record's point — the list is byte-identical across clones. A
        # directory outside this repository has no such form and is None.
        block["directoriesRelative"] = _relative_to_root(block.get("directories") or [], root)
        # Index-aligned with the two lists above: whether that directory is
        # outside the repository holding this root. The relative form is still
        # given for those — it is what a face with the whole tree checked out
        # follows — but a face that clones only its sub-repository cannot.
        block["directoriesOutsideRepo"] = _outside_repo_flags(
            block.get("directories") or [], root)
        # The scope is absolute too; the same block must not hold one key
        # with a relative twin and another without. The root itself is `.`.
        block["scopeRelative"] = _relative_to_root(block["scope"], root)
        block["scopeOutsideRepo"] = _outside_repo_flags(block["scope"], root)
        facts["outsideOutput"] = block
    if slots:
        # Its own key, not `collisions`: that word already belongs to the
        # manifest's count of keys whose spellings normalised onto one entry,
        # and one face read the two as a single number disagreeing with the
        # SHARED SLOT lines on its terminal.
        facts["documentSlots"] = dict(slots)
    # Which apps this run covered — the same record lands in each of their
    # manifests, and a reader of one should know the others hold the same
    # run. Always written: `[]` is "no --app", an absent key would not be.
    facts["apps"] = [t["app"] for t in targets if t.get("app")]
    facts["recordedAt"] = recorded_at
    try:
        from .. import __version__ as version
    except ImportError:
        version = "unknown"
    # Whether the record this run just wrote is visible to anyone else.
    # ⚠️ NOT a reason to make it tracked — `.jsonui-cli/` is the face's call,
    # and it is genuinely split: measured 2026-09-09, one of three faces on
    # this machine does not track it. The tool reports the condition and
    # leaves the choice where it belongs.
    target = manifest.manifest_path(root)
    existed = target.is_file()
    tracked = _git_tracks_file(target, root)
    facts["manifestIsGitTracked"] = tracked
    # Untracked because the face said so (an ignore rule), or just untracked.
    ignored = _git_ignores_file(target, root) if tracked is False else False
    facts["manifestIsGitIgnored"] = ignored
    try:
        manifest.save(
            root, version, written,
            generated_by="jsonui-doc generate html",
            run_facts=facts,
        )
    except OSError as exc:
        print(f"  ⓘ NOTE: could not write the generation manifest ({exc}). "
              f"The pages were written; the record of them was not.")
        return
    if len(targets) > 1:
        # Named per root, and whether this run CREATED the file: a root that
        # never had a manifest (a sub-repository a face ignores by default,
        # say) now gets one, and the face should see that in the log rather
        # than in a status line it did not expect.
        print(f"  Manifest {'created' if not existed else 'updated'}: {target}")
    # Three states, like the outside-writes block above and for the same
    # reason: "not tracked" is an answer, and "cannot tell" is the absence of
    # the instrument. Folding them together would tell a face with no git
    # that its record is private, which is a different claim.
    if tracked is False:
        # Two kinds of "not tracked", and they call for different readers.
        # An ignore rule the face wrote is a decision already taken: say
        # where the record lives and stop. A plain untracked file may be an
        # accident: ask. One wording for both made the deliberate case a
        # line printed every run that never changed anyone's action, and a
        # reader who learns to skip it skips the other one too (reported
        # 2026-09-10; one face holds both kinds in a single run).
        if ignored:
            print(f"  ⓘ NOTE: {target} is ignored by this repository's .gitignore, so this "
                  f"record lives outside `git status` and any diff by that rule. It is "
                  f"readable in place; nothing to decide here.")
        else:
            print(f"  ⓘ NOTE: {target} is NOT git-tracked here, so this record "
                  f"will not appear in `git status` or a diff. It is still "
                  f"readable in place — but it cannot serve as evidence to anyone "
                  f"who is looking for a change rather than reading the file.")
    elif tracked is None:
        print(f"  ⓘ NOTE: could not tell whether {target} is git-tracked (no "
              f"git, or outside a repository) — not a statement that it is "
              f"untracked.")


def _git_ignores_file(path: Path, cwd: Path) -> "bool | None":
    """True when an ignore rule of the repository covers `path`, False when
    none does, None when git did not answer. Run from `cwd` (the root), like
    `_git_tracks_file`, and for the same reason: the file need not exist yet."""
    try:
        out = subprocess.run(["git", "-C", str(cwd), "check-ignore", "-q", "--", str(path)],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode == 0:
        return True
    if out.returncode == 1:
        return False
    return None  # 128: not a repository, or git refused


def _git_tracks_file(path: Path, cwd: Path) -> bool | None:
    """True/False/None — tracked, not tracked, or the question was not answered.

    ⚠️ None IS NOT False, for the reason `_git_tracked_file_count` gives about
    its own -1: a machine without git would otherwise be told every record it
    writes is invisible, which is a claim about the repository rather than
    about the instrument.

    ⚠️ Runs from *cwd* (the project root), NOT from the file's own directory.
    The first draft used `path.parent`, which does not exist yet on the run
    that creates the manifest — git then failed for a reason that has nothing
    to do with tracking, and the helper reported the confident `False`. A
    directory that is not there is exactly the case this three-valued answer
    exists to keep apart from "not tracked".
    """
    if not cwd.is_dir():
        return None
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), "ls-files", "--error-unmatch", str(path)],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if r.returncode == 0:
        return True
    # git ran. Only a pathspec that did not match is a fact about the file;
    # anything else (no repository, a broken index) is the absence of an
    # answer and must not print as "your record is private".
    stderr = (r.stderr or "").lower()
    if "did not match any file" in stderr or "did not match" in stderr:
        return False
    return None


def _git_tracked_file_count(directory: Path) -> int:
    """Tracked files under *directory*: a count, or -1 when git cannot say.

    ⚠️ -1 IS NOT 0. No git on PATH, or a directory outside any repository,
    means the question was not answered; 0 means it was answered and nothing
    there is tracked. Folding them together would report "not tracked" for
    every machine without git, which is the shape that makes a missing
    instrument look like a clean result.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(directory), "ls-files", "--", str(directory)],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return -1
    if r.returncode != 0:
        return -1
    return sum(1 for line in r.stdout.splitlines() if line.strip())


def _git_modified_file_count(directory: Path) -> int:
    """Tracked files under *directory* that now differ from the index: a count,
    or -1 when git cannot say.

    The companion of `_git_tracked_file_count`, added because the line using
    that count said "this run CHANGED files" without ever having looked at a
    byte. Tracked-and-rewritten-identical is the common case — 38 of 38 on
    the reporting face — and it is exactly the case where the owning lane has
    nothing to do; "changed" sent them looking for a diff that was not there.

    ⚠️ A STATE, NOT A CAUSE. `git status` says a file differs now, not which
    run made it so; a modification the owner had pending before this run
    counts too. So the printed line says "now differ", never "this run
    changed", and keeps the tracked count beside it — a directory where the
    two are equal has had every tracked file touched, which is the shape of a
    regeneration, while a single difference is more likely the owner's own.

    ⚠️ -1 IS NOT 0, for the reason the companion gives about its own -1.
    `--untracked-files=no` because a new, untracked file is not a change to
    anything the owner committed; it is reported through the tracked count's
    complement, not here.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(directory), "status", "--porcelain",
             "--untracked-files=no", "--", str(directory)],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return -1
    if r.returncode != 0:
        return -1
    return sum(1 for line in r.stdout.splitlines() if line.strip())


def _is_leftover(p: Path, written: set, cutoff: "float | None") -> bool:
    """Not written by this run AND untouched since it started — see the
    docstring of _report_stale_pages for why both conditions are needed."""
    try:
        if p.resolve() in written:
            return False
    except OSError:
        return False
    if cutoff is None:
        return True
    try:
        return p.stat().st_mtime < cutoff
    except OSError:
        return False


def _site_copies_of(orphan: Path, output_path: Path, written: set) -> list:
    """Pages this run rendered under `-o` FROM the orphan — a stale markdown
    file re-rendered into the site every run. Identified by source, never by
    name: on a tree where two faces share a screen name, the name matched the
    other face's live page and named it as a copy (triage, 2026-09-10)."""
    try:
        src = orphan.resolve()
        out = output_path.resolve()
    except OSError:
        return []
    hits = []
    for page, source in _page_sources.items():
        if source != src or page not in written:
            continue
        try:
            page.relative_to(out)
        except ValueError:
            continue
        hits.append(page)
    return sorted(hits)


def _report_stale_pages_outside(output_path: Path, started_at: "float | None" = None,
                                limit: int = 20) -> list:
    """The same question for every directory this run wrote OUTSIDE `-o`.

    `_report_stale_pages` scans the output tree, and only that: a face's own
    docs directory (`--app`), which the run rewrites in place, was never
    scanned, so a spec renamed on one face left its old pages — html and md —
    behind with nothing naming them, while the site carried both names.
    Reported 2026-09-10 by the lane that regenerates four faces at once.
    The directories come from the outside-writes ledger, so the scan covers
    exactly what the run touched and nothing the operator keeps elsewhere.
    Returns `(orphan, [site copies])` pairs.
    """
    try:
        out = output_path.resolve()
    except OSError:
        out = output_path
    written = get_written_pages()
    cutoff = (started_at - 1) if started_at is not None else None
    seen: set = set()
    stale: list = []
    global _stale_outside_scanned
    for d in sorted(_written_outside_output, key=str):
        try:
            real = d.resolve()
        except OSError:
            continue
        if str(real).startswith(str(out) + "/") or real in seen or not real.is_dir():
            continue
        seen.add(real)
        for pattern in ("*.html", "*.md"):
            stale.extend(p for p in real.rglob(pattern) if _is_leftover(p, written, cutoff))
    stale = sorted(set(stale))
    # How many directories this scan actually walked. Recorded HERE, by the
    # scan, rather than re-derived at the recording site: the same rule
    # written in two places drifts, and the number's whole job is to say
    # whether the zero beside it was measured.
    _stale_outside_scanned = len(seen)
    if not stale:
        return []
    pairs = [(p, _site_copies_of(p, output_path, written)) for p in stale]
    by_dir: dict = {}
    for p, copies in pairs:
        by_dir.setdefault(p.parent, []).append((p, copies))
    print()
    warn(f"  WARNING [doc-stale]: {len(stale)} page(s) outside {output_path} were not written "
         "by this run — leftovers from a deleted or renamed source, in the directories "
         "this run wrote:")
    shown = 0
    for d in sorted(by_dir, key=str):
        print(f"       {d}: {len(by_dir[d])}")
        for p, copies in by_dir[d]:
            if shown < limit:
                refs = _document_referrers.get(p.resolve(), [])
                line = f"         {p.name}"
                if copies:
                    line += f"  (also copied into the site: {', '.join(str(c) for c in copies)})"
                if refs:
                    # Not a page to delete: tests still resolve their `source.document`
                    # to it. The inconsistency is on the face (spec renamed, tests not).
                    named = ', '.join(refs[:3]) + (f', … +{len(refs) - 3}' if len(refs) > 3 else '')
                    line += (f"  (no spec writes it, but {len(refs)} test(s) still name it as "
                             f"source.document — update those before deleting: {named})")
                print(line)
                shown += 1
    if len(stale) > limit:
        print(f"       … {len(stale) - limit} more")
    return pairs


def _report_stale_pages(output_path: Path, started_at: float | None = None,
                        limit: int = 20) -> list[Path]:
    """Name the pages sitting in the output directory that this run did not write.

    Generation writes over the previous run rather than replacing it, so a
    page whose source was deleted or renamed stays behind and nothing links
    to it. That is untidy on its own, but the real cost is that it makes the
    page count agree: a reporting project counted one page per test and
    concluded nothing was missing, when in fact one page was a leftover and
    one real page had been overwritten by a same-named test in another app.

    A warning rather than a deletion — `-o` may hold files the operator put
    there, and this reports what it sees instead of acting on it.

    Membership of the written set is not enough on its own. Not every writer
    reports through `note_page_generated` — the Figma pages did not, and the
    first version of this check called twelve pages leftovers while the same
    run was writing them. So the run's start time is the second condition:
    a page touched since then was produced by this run whether or not the
    tally knows about it, and only an untouched one can be a leftover. That
    holds for a writer nobody has noticed yet, which the tally cannot.
    """
    if not output_path.exists():
        return []
    written = get_written_pages()
    # Filesystem timestamps are coarser than the call that captured the
    # start, so a page written in the same instant must not look older.
    cutoff = (started_at - 1) if started_at is not None else None
    stale = sorted(p for p in output_path.rglob("*.html") if _is_leftover(p, written, cutoff))
    if not stale:
        return []
    print()
    warn(f"  WARNING [doc-stale]: {len(stale)} page(s) in {output_path} were not written "
          "by this run — leftovers from a deleted or renamed source:")
    for p in stale[:limit]:
        print(f"    {p.relative_to(output_path)}")
    if len(stale) > limit:
        print(f"    … and {len(stale) - limit} more")
    # The count of these ships on the closing line (`warnings N`), tallied by
    # `run_log.warn` — not as a grep recipe printed here. The recipe that used
    # to follow matched its own text (`warning \[` is in the expression), so a
    # reader who ran it over this log counted one warning that was the
    # instruction to count. The reader's expression is the gate's business; the
    # number is this tool's.
    return stale


def document_output_rel_path(owner: str | None, doc_path: str) -> str:
    """Where a declared document's page is written, relative to the site root.

    The declaring app's name goes in front. Two apps naming the same relative
    path used to land on one file and the last writer kept it — silently, with
    a successful run and no warning.

    🔻 EVERY declared page moves, not only the ones that collide today. The
    ruling was that a page's location must follow its own declaration and
    nothing else: under 'separate them only when they clash', a path depends on
    what OTHER apps happen to declare, so an app adding a name tomorrow moves a
    neighbour's URL that nobody touched. One move now beats a move whenever
    somebody else writes something.

    🚫 NO SEGMENT WITHOUT A NAME. A run with nothing declared has no app to
    name, and inventing one — 'default', the directory's name — would put every
    such site's pages somewhere new for no gain. The absent segment is the
    honest rendering of an absent declaration.

    🚫 AND NO SECOND COPY OF A NAME THE PATH ALREADY CARRIES. v1.8.64 prepended
    unconditionally and produced `user/docs/user/screens/html/mypage.html` on a
    face whose declarations are already app-scoped — measured by that face 10
    minutes after the release, along with 30 pages left at their old URLs. The
    convention `docs/<app>/…` is declared one function away in this same file
    (`_app_of_embedded_page`), so the information needed to not do that was
    already here.

    ⚠️ THIS IS NOT "separate them only when they clash". The test is whether
    THIS path already names THIS owner — a property of the one declaration, not
    of what other apps declared. So the ruling's reason survives: a page's
    location still depends on nothing but its own declaration, and an app added
    tomorrow still moves nobody's URL.
    """
    if not owner:
        return doc_path
    if _path_already_names_app(owner, doc_path):
        return doc_path
    return f"{owner}/{doc_path}"


def _path_already_names_app(owner: str, doc_path: str) -> bool:
    """Does `doc_path` already carry `owner` as its app segment?

    Two shapes, both unambiguous:

        <owner>/…            the segment is already in front
        docs/<owner>/…       the convention `_app_of_embedded_page` reads

    🚫 WHAT THIS DELIBERATELY DOES NOT DO: search for the name anywhere in the
    path. `docs/screens/user/x.html` is not app-scoping — `user` there is a
    directory that happens to share the name — and treating it as one would
    make two apps whose paths differ only in a middle segment collide again,
    which is the defect this whole function exists to stop. A face using some
    third convention gets the segment prepended; that is the honest answer for
    a shape nothing here can recognise, and it is the safe direction (a
    redundant segment separates; a missing one collides).
    """
    parts = PurePosixPath(doc_path).parts
    if not parts:
        return False
    if parts[0] == owner:
        return True
    return len(parts) >= 2 and parts[0] == "docs" and parts[1] == owner


def _report_document_slot_collisions(
    declarations: list[tuple[str | None, str, str]],
) -> int:
    """Say how many declared documents land on one output file, and which tests.

    Takes the DECLARATIONS, not a dictionary of them. The first version took a
    dict keyed by (owner, path) and counted its entries, which is the same
    mistake one level up: three tests in ONE app declaring one path arrived as
    a single entry, and the report said "1 declaration, 0 shared". A counter
    built on top of a structure that already deduplicates counts the
    survivors, and the survivors are exactly what a collision report is
    supposed to look past.

    🔻 THE SLOT IS THE FILE, AND THE FILE IS `document_output_rel_path`. Until
    the app segment landed, the slot was the declared path alone, so two apps
    naming one path collided. Since then each app's page is written under its
    own segment — two apps naming one path are two files — and a report still
    keyed on the bare path announced SHARED SLOT for pairs that share nothing,
    while the manifest beside it said `collisions: 0`, because THAT counter
    means manifest keys whose spellings normalised onto one entry. Same word,
    two quantities, one reader. The key here is the function that decides
    where the page goes, so the report and the writer cannot disagree about
    what "the same file" means.

    ⚠️ THE SHARED KEY IS STILL NOT THE APP. Two tests in one app declaring one
    path land on one file today exactly as before — measured on a consumer
    tree: 201 declarations over 30 paths, 29 shared, ALL inside a single app.
    The segment separates apps; it does nothing within one.

    🔻 "N TEST(S) RESOLVE TO THIS PAGE", NOT "KEPT / OVERWRITTEN". The page is
    generated from the document alone: same owner, same path, same source,
    same bytes, whichever declaration is processed last. Nothing any test said
    is lost. The old line named a winner and losers, and the faces went
    looking for the overwritten content and found identical files. What IS
    true, and what a person has to act on, is that several tests name one
    page — so all of them are listed, none as a loser.

    🔻 THE COUNT IS PRINTED EVEN WHEN IT IS ZERO. "No shared slots" and
    "nobody checked" produce the same silence otherwise, and this whole family
    of defects has been silence.

    Returns the number of shared files; the full facts go to
    `_document_slot_facts` for the manifest, because the printed report
    reaches whoever is watching and the record reaches the next question.
    """
    by_file: dict[str, list[tuple[str | None, str]]] = {}
    for owner, doc_path, test_name in declarations:
        out_rel = document_output_rel_path(owner, doc_path)
        by_file.setdefault(out_rel, []).append((owner, test_name))

    shared = {p: v for p, v in by_file.items() if len(v) > 1}
    print(f"  Document slots: {len(by_file)} path(s) from {len(declarations)} "
          f"declaration(s); {len(shared)} shared by more than one test.")
    for out_rel, claimants in sorted(shared.items()):
        print(f"    SHARED SLOT {out_rel}")
        print(f"      {len(claimants)} test(s) resolve to this page — same source, "
              f"same bytes, nothing lost:")
        for owner, name in claimants:
            print(f"        {name} ({owner or 'the run itself'})")
    _document_slot_facts.clear()
    _document_slot_facts.update({
        "paths": len(by_file),
        "declarations": len(declarations),
        "sharedPaths": len(shared),
        "sharedPathKeys": sorted(shared)[:20],
    })
    if len(shared) > 20:
        _document_slot_facts["sharedPathKeysNote"] = f"first 20 of {len(shared)}"
    return len(shared)


def _generate_document_pages(
    input_path: Path,
    output_path: Path,
    generated_files: list[dict],
    all_tests_nav: dict,
    roots_by_app: dict[str | None, Path] | None = None,
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
    # Keyed by (owner, path). Keying by the path alone dropped one of two
    # apps that declared the same relative path — before any resolution ran,
    # so nothing downstream could know it had happened.
    #
    # 🚫 THIS DOES NOT YET PRODUCE TWO PAGES. The output path is still built
    # from the relative path alone, so two entries still write to one file and
    # the last one still wins it on disk. What changed is that the run now
    # KNOWS, and says so. The page count is unchanged and the ruling that
    # changes it — every page under its declaring app's segment — is waiting
    # on a question this function cannot answer: the app the run itself was
    # pointed at arrives with no name, because the name is discarded where the
    # roots are built.
    #
    # Reporting it before fixing it is the point. A collision that is silent
    # is indistinguishable from no collision, and the count below is what
    # makes "we looked and there were none" a different statement from "we
    # never looked".
    declarations: list[tuple[str | None, str, str]] = [
        (f.get('group') or None, f['document'], f.get('name', 'Document'))
        for f in generated_files if f.get('document')
    ]
    _report_document_slot_collisions(declarations)

    # One slot is one page, so the processing map necessarily deduplicates.
    # The report above runs on the declarations, BEFORE this, for that exact
    # reason: counting here would count what survived.
    documents_to_process: dict[tuple[str | None, str], str] = {
        (owner, doc_path): test_name
        for owner, doc_path, test_name in declarations
    }
    # Every test that names a document, kept beside the deduplicated map: the
    # leftover report needs the count the map throws away.
    referrers_by_key: dict = {}
    for owner, doc_path, test_name in declarations:
        referrers_by_key.setdefault((owner, doc_path), []).append(test_name)

    if not documents_to_process:
        return

    print("  Generating document pages...")

    for (owner, doc_path), test_name in documents_to_process.items():
        # Bound before the try so the failure record can name them even when
        # the exception fires before they are assigned.
        source_path = None
        out_rel = document_output_rel_path(owner, doc_path)
        output_doc_path = output_path / Path(out_rel)
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
            # 🔻 The base is the root of the app that DECLARED the test, not
            # the directory this run happened to be pointed at. They are the
            # same thing for a single-app run and differ for every other one:
            # a path that exists only under its own app was reported as
            # missing, because the run's input was a different app's tree.
            # ⚠️ NO `input_path` FALLBACK IN THE LIST, deliberately. The map
            # already holds it: `roots` starts with `(input_path, None)`, so
            # the run's own tests — whose group is None — resolve through the
            # same lookup as everyone else. A mutation dropping `input_path`
            # from a two-entry list left every arm green, which is what a
            # redundant element does; arming it would have defended code that
            # cannot fail. The `or input_path` below is the real fallback, for
            # a caller that passes no map at all.
            owner_root = (roots_by_app or {}).get(owner) or input_path
            bases: list[Path] = [owner_root, owner_root.parent]

            source_path = next(
                (b / doc_path for b in bases if (b / doc_path).exists()), None)
            if source_path is None:
                # Name every base that was tried. "Not found" with one path in
                # it sends the reader to fix a file that is in the right place.
                tried = ", ".join(str(b) for b in bases)
                warn(
                    f"    WARNING [doc-missing]: document not found: {doc_path}\n"
                    f"      'document' is resolved from the declaring app's test root "
                    f"(and its parent), not from the test file (unlike 'source.layout'). "
                    f"Owner: {owner or '(the run itself)'}. Tried: {tried}."
                )
                continue

            # Determine output path (preserve relative structure)
            # e.g., docs/screens/login.html -> docs/screens/login.html
            rel_doc_path = Path(out_rel)
            output_doc_path = output_path / rel_doc_path
            output_doc_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate document page with embedded body content and Mermaid CDN
            html_content = generate_document_html(
                source_path=source_path,
                # 🚫 NOT `title=test_name`. `generate_document_html` already
                # takes the page's own <title> when this is None, and passing
                # a test name overrode it with whichever declaration happened
                # to win the slot. On one tree that put a test's name —
                # "…Tier 5 - Responsive Runtime Conditions" — on a page whose
                # own title says what the screen is.
                #
                # ⚠️ The nav label follows this too (the same value reaches
                # the sidebar), so twelve links that used to carry twelve
                # different test names now carry one page's title twelve
                # times. That is more honest and less readable, and the nav
                # side is a separate item on the same ticket: one page should
                # appear once.
                title=None,
                all_tests_nav=all_tests_nav,
                current_doc_path=doc_path,
                body_link_rewriter=_component_body_rewriter(
                    output_doc_path, output_path),
            )

            with open(output_doc_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            note_page_generated(output_doc_path)
            note_page_source(output_doc_path, source_path)
            _document_referrers[Path(source_path).resolve()] = list(referrers_by_key.get((owner, doc_path), []))

        except Exception as e:
            record_page_failure('document', str(doc_path), e,
                                source=source_path,
                                output=output_doc_path)


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

            note_page_generated(output_doc_path)

        except Exception as e:
            rel = api_doc.get('path')
            record_page_failure(
                'API doc',
                api_doc.get('name', 'unknown'),
                e,
                source=api_doc.get('source_file'),
                output=(output_path / rel) if rel else None,
            )

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

            note_page_generated(output_erd_path, suffix=" (ER Diagram)")

        except Exception as e:
            record_page_failure(
                'ER diagram',
                category,
                e,
                output=output_path / f"{category}/erd.html",
            )


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
            warn(f"  WARNING [doc-report]: invalid check report {report_path}: {e}")
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
        note_page_generated(out_file)


def _generate_spec_pages(
    docs_dirs: list[Path],
    output_path: Path,
    all_tests_nav: dict | None = None,
    collect_only: bool = False,
    path_prefix: str | None = None,
    layouts_dir: Path | None = None,
    unit_pages_by_target: dict[str, str] | None = None,
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
    #: component spec FILE -> the page this run wrote for it. Only successful
    #: writes land here, so a component whose page failed cannot be linked to.
    component_pages_by_file: dict[str, str] = {}

    # Component pages FIRST. The screen pages link to them, and the link
    # is built from the pages this run wrote — so they have to exist by
    # then. The screen loop used to run first and the link was a second,
    # hard-coded spelling of the layout rule; it pointed at a directory
    # this generator never writes. Same ordering defect, and same repair,
    # as the unit back-links: emit the link from what was produced, not
    # by reapplying a rule to a name.
    # Generate component specification pages
    if component_files_found:
        if not collect_only:
            print("  Generating component specification pages...")

        success_count = 0
        error_count = 0

        for comp_file, comp_docs_path in sorted(component_files_found, key=lambda x: x[0]):
            # Same shape, same reason as the screen loop above.
            output_comp_path = None
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
                # With path_prefix: <app>/components/usercard.html
                current_path = _component_page_rel(comp_file, comp_docs_path, path_prefix)

                # Add to navigation info
                metadata = result.spec_data.get('metadata', {})
                component_files_info.append({
                    'name': metadata.get('displayName', metadata.get('name', comp_file.stem)),
                    'path': current_path,
                    'category': metadata.get('category', 'other'),
                })

                # Skip HTML generation if collect_only mode
                if collect_only:
                    component_pages_by_file[comp_file.name] = current_path
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

                note_page_generated(output_comp_path)
                component_pages_by_file[comp_file.name] = current_path
                success_count += 1

            except Exception as e:
                record_page_failure('component spec', comp_file.name, e,
                                    source=comp_file, output=output_comp_path)
                error_count += 1

        if not collect_only and (success_count > 0 or error_count > 0):
            print(f"  Component pages: {success_count} generated, {error_count} failed")


    # Generate screen specification pages
    if spec_files_found:
        if not collect_only:
            print("  Generating screen specification pages...")

        success_count = 0
        error_count = 0

        for spec_file, spec_docs_path in sorted(spec_files_found, key=lambda x: x[0]):
            # Reset per ITERATION, not once before the loop. The handler below
            # reads this, and it is assigned after the `collect_only` return —
            # so on the collect pass it was never assigned at all and one bad
            # spec raised UnboundLocalError out of the whole run, losing the
            # real error. Initialising once outside the loop would fix that
            # crash and leave the worse half: a later iteration failing before
            # the assignment would still hold the PREVIOUS spec's path, and
            # `record_page_failure` writes a placeholder there — one spec's
            # error silently overwriting another spec's page.
            output_spec_path = None
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
                # Read off THIS file's own declaration; a target with no page
                # is not linked, so a link cannot dangle. Depth-aware: a
                # nested spec page sits further from unit/.
                up = "../" * len(Path(current_path).parts[:-1])
                # Same shape as unit_links, same reason: the emitter is given
                # the pages this run writes rather than a rule to reapply.
                component_links = {
                    name: f"{up}{rel}"
                    for name, rel in component_pages_by_file.items()
                }
                unit_links = [
                    {"target": t, "href": f"{up}{(unit_pages_by_target or {})[t]}"}
                    for t in _declared_targets(result.spec_data)
                    if t in (unit_pages_by_target or {})
                ]
                content = generate_spec_html(
                    result.spec_data,
                    all_tests_nav=all_tests_nav,
                    current_path=current_path,
                    layouts_dir=spec_layouts_dir,
                    unit_links=unit_links,
                    component_links=component_links,
                )

                with open(output_spec_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                note_page_generated(output_spec_path)
                note_page_source(output_spec_path, spec_file)
                success_count += 1

            except Exception as e:
                record_page_failure('screen spec', spec_file.name, e,
                                    source=spec_file, output=output_spec_path)
                error_count += 1

        if not collect_only and (success_count > 0 or error_count > 0):
            print(f"  Spec pages: {success_count} generated, {error_count} failed")

    return spec_files_info, component_files_info


def _unit_spec_href(
    spec_files_info: list[dict], app: str | None = None,
) -> tuple[Any, list[str]]:
    """``(href_fn, misses)`` mapping a declaring spec to its generated page.

    The link is built from the pages this run actually WROTE rather than by
    reapplying the spec -> URL rule to `unit_contract_pages()`'s paths. The
    two are rooted differently — `spec_files` is relative to
    `spec_directory` in jui.config.json, while the pages are written relative
    to the docs directory that was scanned — and when those roots differ,
    recomputing the rule produces a link that resolves to nothing. Matching
    on what exists cannot drift from what exists.

    THE PAGES MUST BE THIS APP'S. A unit page for app `admin` is written at
    `admin/unit/`, so a href of `../<root-relative path>` resolves inside
    `admin/`, not at the root — the decision is taken against one tree while
    the resolution happens in another. Where the two trees share a name it is
    right by coincidence; where only the root has the name it emits a link
    that dangles. Measured on two faces: one app-scoped project linked 0 of
    19 (the root list is empty before the app pages are collected), and
    another linked 8 of 25 — all 8 being names both trees happened to carry.

    Unresolved links are COLLECTED, not swallowed, and each miss carries the
    REASON: a target whose spec page was not generated renders its screen as
    plain text, and the caller says how many did that and why. A silently
    missing href looks identical to a screen that simply has no page, and
    "could not be linked" with no reason makes every reader trace the run to
    find out which of three unrelated repairs applies.
    """
    # Where this app's unit pages are written. The href is relative to it,
    # so an app's page never reaches out of its own subtree.
    unit_dir = f"{app}/unit" if app else "unit"

    # 'specs/settings/profile.html' -> 'settings/profile'
    #
    # The caller appends each app's pages AFTER the root scope's, so where
    # both scopes carry a name the app's page wins by overwriting. A filter
    # on the app's prefix was tried here and removed: with the href computed
    # relatively it changed no outcome, and an unexercised guard reads as a
    # rule the code does not actually enforce. The precedence is pinned by an
    # arm instead.
    by_key: dict[str, str] = {}
    for info in spec_files_info or []:
        path = str(info.get("path") or "")
        if not path.endswith(".html"):
            continue
        parts = path[: -len(".html")].split("/")
        if "specs" in parts:
            parts = parts[parts.index("specs") + 1:]
        if parts:
            by_key["/".join(parts)] = path
    misses: list[str] = []
    scope_has_no_pages = not by_key

    def href(screen: str, spec_file: str | None) -> str | None:
        key = None
        if spec_file and spec_file.endswith(".spec.json"):
            key = spec_file[: -len(".spec.json")]
        target = by_key.get(key) if key else None
        if target is None:
            target = by_key.get(str(screen))
        if target is None:
            # The reason, not only the name: these are repaired in three
            # different places, and without it the reader has to trace the
            # run to tell them apart.
            if scope_has_no_pages:
                why = "no spec page was written for this scope"
            elif not spec_file:
                why = "the contract names no spec file"
            else:
                why = "no spec page of this name in this scope"
            misses.append(f"{spec_file or screen} ({why})")
            return None
        return posixpath.relpath(target, unit_dir)

    return href, misses


def _component_page_rel(comp_file, comp_docs_path, path_prefix: str | None) -> str:
    """Where a component's page is written, relative to the output root.

    The ONE place that knows this. The spec page's link to a component used to
    be a second, hard-coded spelling of it — `../../components/html/<name>` —
    which is right for `generate spec` (screens/html/ beside components/html/)
    and wrong for the site, whose pages are `<app>/specs/` and
    `<app>/components/`. Reported 2026-09-08: the site's only dangling link,
    and it survived because the check counted links rather than resolving
    them. Two spellings of one rule diverge the moment one layout changes;
    🚨 CORRECTED 2026-09-08: this sentence used to end "both callers now read
    this" — TWO. There are FOUR production call sites, and they are NAMED here
    rather than described by a command:

        cli.py                — `generate spec`, batch
        cli.py                — `generate spec`, single file
        test_doc/generator.py — the site's spec pages
        test_doc/generator.py — `_pre_generate_spec_docs`, into the source tree

    ⚠️ Named, because two attempts to give a counting command both failed. A
    bare `grep -c` over the repo answers 25 (the definition, nineteen test
    references, the four above, and the comment quoting the pattern). Adding
    narrowings to that comment made the comment match its own example, and it
    answered 5. **An expression written where it can match itself is not a
    count** — so the population is listed, and a reader can check the list
    against the code instead of trusting an incantation.

    Three of the four were
    wired; the fourth (`_pre_generate_spec_docs`, pre-generation into the
    source tree) passed no `component_links` at all and fell back to the
    legacy template. It stayed invisible because that template is CORRECT at
    depth 0, and the face that first exercised the path had no nested spec —
    a face with one measured 18 pages resolving and its single nested page
    dangling.

    📌 Making one place authoritative and counting the places that must read
    it are different acts, and only the first leaves a trace in the code.
    Before trusting a sentence like this one, run the count.
    """
    from pathlib import Path as _P
    output_name = _P(comp_file).stem.replace(".component", "") + ".html"
    rel_to_docs = _P(comp_file).parent.relative_to(comp_docs_path)
    rel_subdir = str(rel_to_docs) if str(rel_to_docs) != "." else ""
    base = f"{path_prefix}/components" if path_prefix else "components"
    return f"{base}/{rel_subdir}/{output_name}" if rel_subdir else f"{base}/{output_name}"


def _unit_page_rel(target_name: str, app: str | None = None) -> str:
    """Where a target's page is written, relative to the output root.

    App-scoped when the project holds several, the same split the spec pages
    use — two apps may own a target of the same name, and one `unit/` would
    make the second overwrite the first.
    """
    stem = str(target_name).replace("/", "_")
    return f"{app}/unit/{stem}.html" if app else f"unit/{stem}.html"


def _load_unit_contract_pages(project_root: Path) -> dict | None:
    """The unit contract judgment, or None when it cannot be evaluated.

    Read BEFORE the spec pages are written, because each spec that declares
    `unitContracts` links to its target's page and needs the target's name to
    do it. The pages themselves are written afterwards, when the spec pages
    they link back to exist.

    A config that cannot be used is a WARNING, not a note. The common shape is
    a config carrying only `checks` — legitimate for `jsonui-doc check`, and
    with no `spec_directory` it cannot enumerate anything — and the result is
    an exit 0 whose Unit section is simply absent. That is indistinguishable
    from a project which declares no contracts unless it is said in the
    spelling the zero-warnings gate counts.
    """
    from jsonui_test_cli.unit_contracts import unit_contract_pages

    try:
        return unit_contract_pages(project_root)
    except Exception as exc:  # noqa: BLE001
        # Not a page failure — nothing has been promised in the index yet.
        # Say so and carry on: the rest of the site is still worth writing.
        warn(f"  WARNING [doc]: unit contracts not read from {project_root} ({exc})")
        return None


def normalise_unit_roots(
    unit_roots: list[dict] | None, project_root: Path | None
) -> list[dict]:
    """The places to read unitContracts from, as ``{app, root}`` entries.

    A split tree keeps its spec config beside each app rather than at the
    repository root, and the root often holds a config of its own carrying
    only `checks`. A single walk-up from the tests directory stops at that
    one, so the apps' contracts were unreachable however the command was
    invoked. Hence a list: the caller resolves one root per app, and `app`
    names the sub-directory its pages belong under.

    `project_root` remains the single-root spelling, and normalises to one
    unnamed entry, so a single-tree project produces exactly the paths and
    output it produced before.
    """
    if unit_roots:
        return [{"app": e.get("app"), "root": Path(e["root"])} for e in unit_roots]
    if project_root is not None:
        return [{"app": None, "root": Path(project_root)}]
    return []


def _unit_pages_by_target(pages: dict | None, app: str | None = None) -> dict[str, str]:
    """``target -> its page``, so a spec links only to a page that exists."""
    return {str(t.get("target")): _unit_page_rel(str(t.get("target")), app)
            for t in (pages or {}).get("targets") or [] if t.get("target")}


def _declared_targets(spec_data: dict) -> list[str]:
    """Target names a spec's OWN file declares, in order.

    This is the only exact answer available, and both earlier attempts at it
    were one-to-many. Keying by SCREEN fails because a split screen's cases
    are read through the merged parent, so every target under it is recorded
    against the parent's screen name. Keying by the declaring SPEC PATH fails
    for the same reason — `UnitCase.spec_file` is the parent's path for every
    sub-spec, measured — and keying by DIRECTORY fails whenever one directory
    holds two targets, which is the shape that shipped a page linking nine
    specs to one arbitrary target.

    A file's own `unitContracts` block, however, names its own target, and a
    sub-spec carries its block in its own file. So the page being rendered
    reads its own declaration and needs no map.
    """
    raw = spec_data.get("unitContracts")
    if raw is None:
        return []
    blocks = [raw] if isinstance(raw, dict) else raw
    if not isinstance(blocks, list):
        return []
    out: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        target = str(block.get("target") or "").strip()
        if target and target not in out:
            out.append(target)
    return out


def _unit_nav_entries(unit_by_app: dict) -> list[dict]:
    """The Unit Tests sidebar list: one entry per DECLARED target.

    Declared, not written, and the ordering forces it: a screen or flow page
    is rendered long before any unit page exists, and a unit page's own
    sidebar needs the screen and flow lists — so no single pass can build
    both sidebars out of pages that already exist. The circularity is the
    reason, not an oversight.

    A target that then fails to write is not a dead link: `record_page_failure`
    puts a placeholder at the same path precisely so navigation does not
    dead-end on a 404, and the run prints the failure.

    `path` and `group` come from `_unit_page_rel` and the app key — the same
    two facts `_generate_unit_pages` builds its own entries from, so the
    sidebar href and the file that gets written cannot drift apart.
    """
    entries: list[dict] = []
    for app, pages in sorted(unit_by_app.items(), key=lambda kv: (kv[0] or "")):
        for target in (pages.get("targets") or []):
            name = str(target.get("target") or "Unit")
            entries.append({
                "name": name,
                "path": _unit_page_rel(name, app),
                "group": app or "",
            })
    return entries


def _generate_unit_pages(
    pages: dict,
    output_path: Path,
    spec_files_info: list[dict],
    all_tests_nav: dict | None = None,
    app: str | None = None,
) -> tuple[list[dict], str | None, dict[str, list[str]]]:
    """Write one page per ``unitContracts.target``.

    Returns ``(nav entries, the denominator line, undeclared by face)``.

    The judgment comes from `jsonui_test_cli.unit_contracts`, the same
    function `jsonui-test generate unit-stubs --check` calls, so a case
    cannot read as implemented on the site and missing at the gate.
    """
    targets = pages.get("targets") or []
    if not targets:
        return [], pages.get("totals", {}).get("summary_line"), pages.get("undeclared") or {}

    href_fn, misses = _unit_spec_href(spec_files_info, app)
    platforms = pages.get("platforms") or []
    # Per page, not one fixed directory: an app-scoped target lives under
    # `<app>/unit/`, and creating only `unit/` made the write fail — which
    # then wrote a failure PLACEHOLDER at the app path, so the file existed
    # and the page looked generated.
    def _ensure(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    # Built before any page is rendered so each page's sidebar can list its
    # siblings, and so the nav carrying them can be a LOCAL copy. Adding
    # 'units' to the shared `all_tests_nav` would put the section into every
    # screen, flow and spec page's sidebar too — output those pages did not
    # have before, on every project that declares a unitContract.
    entries: list[dict] = []
    for target in targets:
        name = str(target.get("target") or "Unit")
        faces = target.get("faces") or {}
        summary_bits = []
        for face in platforms:
            entry = faces.get(face) or {}
            declared = len(entry.get("declared") or [])
            if declared:
                summary_bits.append(
                    f"{face} {len(entry.get('implemented') or [])}/{declared}"
                )
        entries.append({
            "name": name,
            "path": _unit_page_rel(name, app),
            "platform": ", ".join(platforms) or "all",
            "description": ", ".join(target.get("screens") or []),
            "group": "",
            "case_count": len(target.get("cases") or []),
            "faces_summary": " / ".join(summary_bits) or "no face declares it",
        })
    # The shared nav already carries every declared target, grouped by app
    # (`_unit_nav_entries`). Overriding it here with this app's own entries
    # is what made a unit page show a FLAT list while every other page showed
    # the app subgroups — two spellings of the same section, differing only
    # on the pages the section is about.
    unit_nav = dict(all_tests_nav or {})
    if not unit_nav.get("units"):
        unit_nav["units"] = entries

    written: list[dict] = []
    for target, meta in zip(targets, entries):
        name = meta["name"]
        rel = meta["path"]
        faces = target.get("faces") or {}
        content = generate_unit_html(
            target, platforms,
            spec_href_fn=href_fn,
            all_tests_nav=unit_nav,
            current_path=rel,
            unscannable=pages.get("unscannable") or {},
            undiscoverable=pages.get("undiscoverable") or {},
        )
        try:
            _ensure(output_path / rel).write_text(content, encoding="utf-8")
        except OSError as exc:
            record_page_failure("unit contract", name, exc,
                                source=", ".join(target.get("screens") or []),
                                output=output_path / rel)
            continue
        # The same counter every other page increments. `Generated N HTML
        # files` exists to answer "did everything come out?", so a page that
        # is written and not counted makes the printed denominator smaller
        # than the tree — which is the defect that counter was added to fix.
        note_page_generated(output_path / rel)
        written.append(meta)

    entries = written
    if misses:
        print(
            f"  Unit contracts: {len(misses)} target(s) could not be linked to a "
            f"spec page ({', '.join(sorted(set(misses))[:5])})"
        )
    return entries, pages.get("totals", {}).get("summary_line"), pages.get("undeclared") or {}


def _write_stamped(path: Path, content: str, command: str) -> None:
    """Write *content* to *path* carrying the same producer mark `cli.py` writes.

    🚨 TWO GENERATORS WRITE THESE FILES AND ONLY ONE OF THEM STAMPED.
    `jsonui-doc generate spec` / `generate component` mark what they write, so
    a later reader can ask "is this my own output?". This function's callers
    write the SAME files from `generate html`, and had never stamped — so any
    `generate html` run silently stripped the marks the other command had put
    there. Measured on a consumer face 2026-09-09: five html and one md lost
    theirs, and four newly written md files carried none. `generator.py`
    contained `stamp_producer` zero times, in v1.8.58 where the mark shipped
    and ever since; `cli.py` contained it five times.

    ⚠️ It is not a regression of the release that exposed it. It is the state
    since the mark was introduced, first seen the day a `generate html` run
    reached a tree whose component pages had been marked.

    ⚠️ THE MARK MUST BE THE SAME FAMILY, not a new one naming this path. The
    check reads the FIRST mark it finds and compares by family, so a second
    spelling would make every page this writes read as another producer's —
    exactly the false collision v1.8.59 removed.

    ⚠️ One place, not four call sites. The four sites here are the ones that
    exist today; a fix applied per-site reaches only the ones someone
    remembered, which is the argument the driver's own dispatch-level retry
    makes about itself.
    """
    try:
        from ..cli import stamp_producer
        content = stamp_producer(content, command, path.suffix)
    except Exception:
        # Never fail a page for the mark: an unmarked file is a file the
        # check cannot speak about, which is a state its reader already
        # handles. A crashed write is not.
        pass
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


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

    # Where each component's page WILL be written by the component loop below.
    #
    # ⚠️ Derived from the component JSON files, not from pages on disk. The
    # spec loop runs BEFORE the component loop in this same function, so
    # asking the disk here answers from the PREVIOUS run — or from nothing on
    # a first generation. The layout is this function's own, two lines down,
    # so it is known without looking.
    #
    # Reported 2026-09-08 by a face with a nested spec: this call site passed
    # no `component_links` at all, so `generate_spec_html` fell to its legacy
    # `../../components/html/<name>` template — correct only for a page
    # sitting directly in `screens/html/`, and one `../` short for anything in
    # a subdirectory. The face measured 18 top-level pages resolving and its
    # single nested page dangling.
    #
    # 🚨 The v1.8.53 fix that made these links resolve reached THREE of the
    # four `generate_spec_html` call sites. `_component_page_rel`'s docstring
    # says "both callers now read this" — it counted two. Wiring one place and
    # counting the places that need it are different acts.
    _component_json_dir = docs_base / "components" / "json"
    _component_html_dir = docs_base / "components" / "html"
    _component_pages: dict[str, Path] = {}
    if _component_json_dir.is_dir():
        for _cf in sorted(_component_json_dir.glob("*.component.json")):
            _component_pages[_cf.name] = (
                _component_html_dir / f"{_cf.stem.replace('.component', '')}.html")

    # Process screen specifications
    spec_json_dir = docs_base / spec_subdir / "json"
    if spec_json_dir.exists():
        # A component spec filed under the SCREENS json directory reaches
        # neither loop: this one globs `*.spec.json`, and the component loop
        # below reads `<docs>/components/json` only. So the file produces no
        # page, no link and — before this — no line of output at all. A face
        # was found holding ten of them; it had no way to notice, because
        # "wrote nothing" and "there was nothing to write" print the same.
        # Reported 2026-09-10 while measuring the leaf directories.
        _misfiled = sorted(spec_json_dir.rglob("*.component.json"))
        if _misfiled:
            print()
            warn(f"  WARNING [doc]: {len(_misfiled)} component spec(s) under "
                 f"{spec_json_dir} produce no page — this directory is read for "
                 f"*.spec.json, and component specs are read from "
                 f"{docs_base / 'components' / 'json'}:")
            for _m in _misfiled[:20]:
                print(f"       {_m.name}")
            if len(_misfiled) > 20:
                print(f"       … and {len(_misfiled) - 20} more")
            print("     Move them there, or rename them to *.spec.json if they "
                  "are screens. Nothing is deleted by this warning.")
        spec_files = list(spec_json_dir.rglob("*.spec.json"))
        if spec_files:
            print(f"  Processing {len(spec_files)} {spec_subdir} specification files...")

            html_dir = docs_base / spec_subdir / "html"
            md_dir = docs_base / spec_subdir / "md"
            html_dir.mkdir(parents=True, exist_ok=True)
            md_dir.mkdir(parents=True, exist_ok=True)
            _written_outside_output.update({html_dir, md_dir})

            for spec_file in sorted(spec_files):
                try:
                    # Preserve subdirectory structure. Computed BEFORE the
                    # validity check so an invalid spec can still name the
                    # page it owns: without the path there is nowhere to put
                    # the placeholder, and the stale page from the last run
                    # stays where it is, presented as current.
                    rel_to_json = spec_file.parent.relative_to(spec_json_dir)
                    output_name = spec_file.stem.replace(".spec", "")
                    html_subdir = html_dir / rel_to_json
                    md_subdir = md_dir / rel_to_json
                    html_subdir.mkdir(parents=True, exist_ok=True)
                    md_subdir.mkdir(parents=True, exist_ok=True)

                    result = _validator_for(spec_file).validate_file(spec_file)
                    if not result.is_valid:
                        record_page_failure(
                            'screen spec', spec_file.name,
                            _validation_failure_text(result),
                            source=spec_file,
                            output=html_subdir / f"{output_name}.html")
                        continue

                    spec_layouts_dir = _resolve_layouts_dir_for_spec(spec_file, layouts_dir)
                    html_content = generate_spec_html(
                        result.spec_data,
                        layouts_dir=spec_layouts_dir,
                        # Computed from THIS page's directory, so a nested
                        # spec gets the `../` it actually needs instead of the
                        # two the old template assumed.
                        component_links={
                            name: os.path.relpath(target, html_subdir)
                            for name, target in _component_pages.items()
                        })
                    html_path = html_subdir / f"{output_name}.html"
                    _write_stamped(html_path, html_content, 'spec')

                    # Generate Markdown
                    md_content = generate_spec_markdown(result.spec_data, layouts_dir=spec_layouts_dir)
                    md_path = md_subdir / f"{output_name}.md"
                    _write_stamped(md_path, md_content, 'spec')

                    print(f"    OK: {spec_file.name} -> html, md")

                except Exception as e:
                    record_page_failure('screen spec', spec_file.name, e,
                                        source=spec_file)

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
            _written_outside_output.update({html_dir, md_dir})

            for comp_file in sorted(comp_files):
                try:
                    output_name = comp_file.stem.replace(".component", "")
                    result = _validator_for(comp_file).validate_file(comp_file)
                    if not result.is_valid:
                        record_page_failure(
                            'component spec', comp_file.name,
                            _validation_failure_text(result),
                            source=comp_file,
                            output=html_dir / f"{output_name}.html")
                        continue

                    # Generate HTML
                    html_content = generate_component_html(result.spec_data)
                    html_path = html_dir / f"{output_name}.html"
                    _write_stamped(html_path, html_content, 'component')

                    # Generate Markdown
                    md_content = generate_component_markdown(result.spec_data)
                    md_path = md_dir / f"{output_name}.md"
                    _write_stamped(md_path, md_content, 'component')

                    print(f"    OK: {comp_file.name} -> html, md")

                except Exception as e:
                    record_page_failure('component spec', comp_file.name, e,
                                        source=comp_file)


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

                note_page_generated(output_html_path)
                note_page_source(output_html_path, source_file)
                success_count += 1

            except Exception as e:
                record_page_failure(
                    'page', file_info.get('name', 'unknown'), e,
                    source=file_info.get('source_file') or file_info.get('path'),
                    output=output_html_path)
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
            record_page_failure('figma file', json_file.name, e, source=json_file)

    # Register what was written. The converter reports its own progress, so
    # these are recorded quietly — but they have to be recorded: the page
    # tally and the leftover check both read this set, and for a while the
    # Figma pages were in neither while sitting in the output directory.
    for screen in all_figma_files:
        rel = screen.get('path')
        if rel:
            _pages_written.add((output_path / rel).resolve())

    if all_figma_files:
        print(f"  Figma pages: {len(all_figma_files)} screens generated")

    return all_figma_files
