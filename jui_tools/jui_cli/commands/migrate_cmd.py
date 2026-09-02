"""`jui migrate-layouts` — copy existing platform Layouts/ to shared layouts_directory."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def register_migrate_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "migrate-layouts",
        help="Copy existing platform Layouts/ into shared layouts_directory",
    )
    parser.add_argument(
        "--from",
        dest="source_platform",
        default="ios",
        choices=["ios", "android", "web"],
        help="Platform to copy from (default: ios)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied without actually copying",
    )


def cmd_migrate_layouts(args: argparse.Namespace) -> int:
    from ..core.config_manager import ConfigManager

    config_mgr = ConfigManager()
    if not config_mgr.exists():
        print("ERROR: jui.config.json not found. Run 'jui init' first.")
        return 1

    config = config_mgr.load()
    platforms = config.get("platforms", {})
    pconfig = platforms.get(args.source_platform)
    if not pconfig:
        print(f"ERROR: Platform '{args.source_platform}' not found in config.")
        return 1

    layouts_rel = pconfig.get("layoutsDir")
    if not layouts_rel:
        # Guess based on convention
        root = config_mgr.project_root / pconfig["root"]
        # Same map init writes, so a guess here cannot point at a
        # directory the build would never distribute from.
        from ..core.config_manager import DEFAULT_LAYOUTS_DIR

        for candidate in dict.fromkeys(DEFAULT_LAYOUTS_DIR.values()):
            if (root / candidate).exists():
                layouts_rel = candidate
                break
    if not layouts_rel:
        print(f"ERROR: Cannot find Layouts directory for {args.source_platform}")
        return 1

    src_dir = config_mgr.project_root / pconfig["root"] / layouts_rel
    dest_dir = config_mgr.layouts_directory

    if not src_dir.exists():
        print(f"ERROR: Source directory not found: {src_dir}")
        return 1

    count = 0
    for src_file in sorted(src_dir.rglob("*.json")):
        rel = src_file.relative_to(src_dir)
        dest = dest_dir / rel

        if args.dry_run:
            print(f"  [DRY-RUN] {rel}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
        count += 1

    if args.dry_run:
        print(f"\nWould copy {count} file(s) from {args.source_platform} to {dest_dir.relative_to(config_mgr.project_root)}")
    else:
        print(f"\nCopied {count} file(s) → {dest_dir.relative_to(config_mgr.project_root)}")

        # Update config if layouts_directory is not set
        if "layouts_directory" not in config:
            config["layouts_directory"] = str(dest_dir.relative_to(config_mgr.project_root))
            config_mgr.save(config)
            print(f"Updated jui.config.json: layouts_directory = {config['layouts_directory']}")

    return 0
