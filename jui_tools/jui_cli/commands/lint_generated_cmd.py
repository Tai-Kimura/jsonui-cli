"""`jui lint-generated` — verify the @generated sentinel in generated outputs.

Scans known auto-generated output directories and confirms each file starts
with the @generated header and (for text files) ends with the END footer.
The sentinel is shared across jui/sjui/kjui/rjui; see
``jui_tools.jui_cli.core.generated_marker`` for the source of truth.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


CODE_EXTENSIONS = {".swift", ".kt", ".ts", ".tsx", ".js", ".jsx"}
HEAD_SCAN_LINES = 30
TAIL_SCAN_LINES = 5

# Directories we never descend into — they're either third-party
# dependencies or build artifacts and have their own `Generated/`
# conventions that jui/sjui/kjui/rjui don't own.
DEFAULT_EXCLUDED_DIR_NAMES = frozenset({
    ".git",
    ".gradle",
    ".idea",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    ".vscode",
    ".build",
    "build",
    "dist",
    "out",
    "node_modules",
    "Pods",
    "DerivedData",
    "target",
    "vendor",
    "__pycache__",
    ".venv",
    "venv",
})


def _is_excluded(path: Path, excluded_names: frozenset[str]) -> bool:
    """Return True if any ancestor of ``path`` is an excluded directory."""
    return any(part in excluded_names for part in path.parts)


def register_lint_generated_command(subparsers: argparse._SubParsersAction) -> None:
    """Register ``jui lint-generated``."""
    parser = subparsers.add_parser(
        "lint-generated",
        help="Verify @generated markers on auto-generated files",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Print the regeneration command when markers are missing",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="List every checked file, not just failures",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=5,
        help="Per-function brace-nesting bound for generated view code (default 5)",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=250,
        help="Per-function line-count bound for generated view code (default 250)",
    )
    parser.add_argument(
        "--update-size-baseline",
        action="store_true",
        help="Write the current oversized-function set to .jui-size-waivers "
             "(the ratchet baseline)",
    )
    parser.set_defaults(func=cmd_lint_generated)


def cmd_lint_generated(args: argparse.Namespace) -> int:
    from ..core.config_manager import ConfigManager
    from ..core.generated_marker import SENTINEL, END_LINE

    config_mgr = ConfigManager()
    if not config_mgr.exists():
        print("ERROR: jui.config.json not found. Run 'jui init' first.")
        return 1

    project_root = config_mgr.project_root
    targets = list(_collect_targets(config_mgr))

    if not targets:
        print("No generated files found. Did you run 'jui g project' and 'jui build'?")
        return 0

    missing_header: list[Path] = []
    missing_footer: list[Path] = []
    oversized: list[tuple[Path, str, int, int]] = []
    ok: list[Path] = []

    for kind, path in targets:
        status = _check_file(kind, path, SENTINEL, END_LINE)
        if status == "ok":
            ok.append(path)
        elif status == "missing_header":
            missing_header.append(path)
        elif status == "missing_footer":
            missing_footer.append(path)

    # Generated VIEW files carry no sentinel (they hold hand-edit markers
    # inside instead), so they get their own walk for the size gate.
    view_files = _view_targets(config_mgr)
    for path in view_files:
        oversized.extend(
            (path, name, depth, lines)
            for name, depth, lines in _oversized_functions(
                path, args.max_depth, args.max_lines
            )
        )

    total = len(targets)
    print(f"Checked {total} generated file{'s' if total != 1 else ''} "
          f"(+{len(view_files)} generated views for the size gate).")
    print(f"  OK:              {len(ok)}")
    print(f"  Missing header:  {len(missing_header)}")
    print(f"  Missing footer:  {len(missing_footer)}")
    print(f"  Oversized fns:   {len(oversized)} (depth > {args.max_depth} or lines > {args.max_lines})")

    if args.verbose:
        for p in ok:
            print(f"  [OK] {_rel(p, project_root)}")

    new_waivers: list[str] = []
    if oversized or args.update_size_baseline:
        print(
            "\nOversized generated functions (the extractors' declared "
            "waivers — the size bound is iOS-calibrated; on Android the dex "
            "method limit is a hard compile error a passing build already "
            "proves):"
        )
        for path, name, depth, lines in oversized:
            print(f"  - {_rel(path, project_root)} {name}: depth {depth} / {lines} lines")
        new_waivers = _ratchet_size_baseline(
            project_root, oversized, update=args.update_size_baseline
        )
        if new_waivers:
            print(
                "\nNEW oversized functions (not in .jui-size-waivers — the "
                "waiver set is a ratchet; investigate the regression or, if "
                "reviewed and accepted, re-run with --update-size-baseline):"
            )
            for entry in new_waivers:
                print(f"  - {entry}")

    if missing_header:
        print("\nMissing @generated sentinel:")
        for p in missing_header:
            print(f"  - {_rel(p, project_root)}")

    if missing_footer:
        print("\nMissing END AUTO-GENERATED footer:")
        for p in missing_footer:
            print(f"  - {_rel(p, project_root)}")

    if missing_header or missing_footer:
        if args.fix:
            print(
                "\nTo restore markers, regenerate from specs:\n"
                "  jui g project --force\n"
                "  jui build\n"
                "  # Then re-run 'jui lint-generated'."
            )
        return 1
    if new_waivers:
        return 1
    return 0


BASELINE_FILENAME = ".jui-size-waivers"


def _ratchet_size_baseline(project_root, oversized, update: bool) -> list[str]:
    """Compare the oversized set against the project's checked-in baseline.

    The baseline is a ratchet: entries may leave freely (the tools improved),
    but a NEW entry means the extractors regressed into shipping something
    oversized that yesterday's build bounded — that is a failure signal even
    though the standing waivers are not. Without a baseline file the check is
    purely informational, so projects opt in by committing one
    (--update-size-baseline writes it). Identity is path + function name;
    depth/line numbers wobble with content edits and deliberately don't
    participate.
    """
    baseline_path = project_root / BASELINE_FILENAME
    current = sorted({f"{_rel(path, project_root)} {name}" for path, name, _d, _l in oversized})

    if update:
        baseline_path.write_text(
            "# jui lint-generated size-waiver baseline (ratchet).\n"
            "# One entry per accepted oversized generated function.\n"
            + "".join(f"{entry}\n" for entry in current),
            encoding="utf-8",
        )
        print(f"\nBaseline written: {_rel(baseline_path, project_root)} ({len(current)} entries)")
        return []

    if not baseline_path.is_file():
        return []

    known = {
        line.strip()
        for line in baseline_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    return [entry for entry in current if entry not in known]


def _strip_code_noise(line: str) -> str:
    """Strip string literals and // comments (brace counting must not see
    either — Swift interpolations and Kotlin templates carry braces)."""
    out: list[str] = []
    in_string = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


_FUNC_RE = None


def _oversized_functions(path: Path, max_depth: int, max_lines: int):
    """Yield (name, body_depth, line_count) for generated view functions over
    the size bounds. The metric matches the codegen bounders (sjui
    SectionBounder / kjui SectionExtractor): per-function BODY brace peak,
    strings stripped — never indentation, which the generators deepen far
    past the structural level."""
    global _FUNC_RE
    import re

    if _FUNC_RE is None:
        _FUNC_RE = re.compile(
            r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*"
            r"(?:public\s+|private\s+|internal\s+|fileprivate\s+)?"
            r"(?:func|fun)\s+(?:[\w.]+\.)?(\w+)"
            r"|^\s*(?:public\s+|private\s+)?var\s+(body)\s*:\s*some\s+View\s*\{"
        )

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return

    open_funcs: list[dict] = []
    depth = 0
    for idx, raw in enumerate(lines):
        code = _strip_code_noise(raw)
        match = _FUNC_RE.match(code)
        if match:
            open_funcs.append({
                "name": match.group(1) or match.group(2),
                "start": idx,
                "base": depth,
                "peak": 0,
                "opened": False,
            })
        for ch in code:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        still_open = []
        for fn in open_funcs:
            if depth > fn["base"]:
                fn["opened"] = True
                fn["peak"] = max(fn["peak"], depth - fn["base"])
            if fn["opened"] and depth <= fn["base"]:
                body_depth = fn["peak"] - 1  # the decl's own brace
                line_count = idx - fn["start"] + 1
                if body_depth > max_depth or line_count > max_lines:
                    yield (fn["name"], body_depth, line_count)
            else:
                still_open.append(fn)
        open_funcs = still_open


def _view_targets(config_mgr) -> list[Path]:
    """Every *GeneratedView.swift / *.kt under the project's platform roots
    (build dirs excluded) — the per-function size gate's subjects."""
    roots: list[Path] = []
    config = config_mgr.load()
    platforms = config.get("platforms")
    if isinstance(platforms, dict):
        for platform in platforms.values():
            root = platform.get("root") if isinstance(platform, dict) else None
            if isinstance(root, str) and root:
                candidate = config_mgr.project_root / root
                roots.append(candidate) if candidate.is_dir() else None
    if not roots:
        roots = [config_mgr.project_root]

    out: list[Path] = []
    for root in roots:
        for pattern in ("*GeneratedView.swift", "*GeneratedView.kt"):
            for path in root.rglob(pattern):
                if _is_excluded(path, DEFAULT_EXCLUDED_DIR_NAMES):
                    continue
                out.append(path)
    return sorted(set(out))


def _collect_targets(config_mgr) -> list[tuple[str, Path]]:
    """Return list of (kind, path) pairs to check.

    ``kind`` is "json" for Layout JSON (embedded _generated key) or "code" for
    source-code files (leading comment banner).
    """
    targets: list[tuple[str, Path]] = []

    # Merge project-level exclusions from jui.config.json into the defaults.
    config = config_mgr.load()
    lint_cfg = config.get("lint", {}) if isinstance(config, dict) else {}
    extra_exclusions = lint_cfg.get("exclude_dir_names", []) if isinstance(lint_cfg, dict) else []
    excluded_names = DEFAULT_EXCLUDED_DIR_NAMES | frozenset(extra_exclusions)

    excluded_files: set[Path] = set()
    for entry in (lint_cfg.get("exclude_files", []) if isinstance(lint_cfg, dict) else []):
        excluded_files.add((config_mgr.project_root / entry).resolve())

    # 1. Layout JSON — only the distributed per-platform copies get the
    # @generated marker; the shared ``layouts_directory`` source is
    # hand-editable and intentionally marker-free.
    full_config = config_mgr.load()
    platforms = full_config.get("platforms", {}) if isinstance(full_config, dict) else {}
    for platform_name, pconfig in platforms.items():
        if not isinstance(pconfig, dict):
            continue
        layouts_rel = pconfig.get("layoutsDir")
        platform_root_rel = pconfig.get("root")
        if not layouts_rel or not platform_root_rel:
            continue
        platform_layouts = config_mgr.project_root / platform_root_rel / layouts_rel
        if not platform_layouts.exists():
            continue
        for jf in platform_layouts.rglob("*.json"):
            if _is_resource_or_style(jf):
                continue
            if _is_excluded(jf, excluded_names):
                continue
            if jf.resolve() in excluded_files:
                continue
            targets.append(("json", jf))

    # 2. Per-platform generated directories. We scan anything named "Generated"
    # as well as the conventional web "src/generated" tree.
    for root in _platform_roots(config_mgr):
        if root is None or not root.exists():
            continue
        for generated in root.rglob("Generated"):
            if _is_excluded(generated, excluded_names):
                continue
            if generated.is_dir():
                for tgt in _scan_code_tree(generated):
                    if _is_excluded(tgt[1], excluded_names):
                        continue
                    if tgt[1].resolve() in excluded_files:
                        continue
                    targets.append(tgt)
        for sub in (
            "src/generated/hooks",
            "src/generated/viewmodels",
            "src/generated/data",
            "src/generated/components",
        ):
            sub_path = root / sub
            if sub_path.exists() and not _is_excluded(sub_path, excluded_names):
                for tgt in _scan_code_tree(sub_path):
                    if _is_excluded(tgt[1], excluded_names):
                        continue
                    if tgt[1].resolve() in excluded_files:
                        continue
                    targets.append(tgt)

    # Deduplicate by inode so a single file reached via two casings on a
    # case-insensitive filesystem (macOS default APFS) is checked once.
    seen: set[tuple[int, int]] = set()
    unique: list[tuple[str, Path]] = []
    for kind, path in targets:
        try:
            st = path.stat()
        except OSError:
            continue
        key = (st.st_dev, st.st_ino)
        if key in seen:
            continue
        seen.add(key)
        unique.append((kind, path))
    return unique


def _platform_roots(config_mgr) -> list[Path | None]:
    return [config_mgr.ios_root, config_mgr.android_root, config_mgr.web_root]


def _scan_code_tree(directory: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for f in directory.rglob("*"):
        if f.is_file() and f.suffix in CODE_EXTENSIONS:
            out.append(("code", f))
    return out


def _is_resource_or_style(path: Path) -> bool:
    parts = set(path.parts)
    return "Resources" in parts or "Styles" in parts


def _check_file(kind: str, path: Path, sentinel: str, end_line: str) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "ok"  # Unreadable — don't flag, not our concern

    if kind == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return "ok"
        if isinstance(data, dict):
            generated = data.get("_generated")
            if isinstance(generated, dict) and generated.get("sentinel") == sentinel:
                return "ok"
        return "missing_header"

    lines = text.splitlines()
    head = "\n".join(lines[:HEAD_SCAN_LINES])
    tail = "\n".join(lines[-TAIL_SCAN_LINES:]) if lines else ""
    if sentinel not in head:
        return "missing_header"
    if end_line not in tail:
        return "missing_footer"
    return "ok"


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
