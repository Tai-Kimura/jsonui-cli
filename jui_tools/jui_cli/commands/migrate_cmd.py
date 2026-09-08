"""`jui migrate-layouts` — copy existing platform Layouts/ to shared layouts_directory."""
from __future__ import annotations

import argparse
import json
import os
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

        # 🚨 THIS PLATFORM'S CONVENTION FIRST. The loop used to walk
        # `DEFAULT_LAYOUTS_DIR.values()` in dict order, which puts iOS's
        # bare `Layouts` ahead of everything — so `--source-platform
        # android` would take the iOS directory if one existed. The guess
        # ignored the very argument it was guessing for.
        #
        # 🚨 AND ON A CASE-INSENSITIVE FILESYSTEM IT COULD PICK THE
        # DESTINATION. Found 2026-09-09 by the first arm that ever DROVE
        # this command (a support lane measured 1 arm executing this module
        # against 121 for `build`): a project whose `layouts_directory` is
        # `layouts` makes `root / "Layouts"` exist on macOS, so the command
        # chose the empty destination as its source and reported
        # "Copied 0 file(s)" with exit 0. Silent, successful, and wrong.
        dest_dir_for_guard = config_mgr.layouts_directory
        own = DEFAULT_LAYOUTS_DIR.get(args.source_platform)
        ordered = dict.fromkeys(
            ([own] if own else []) + list(DEFAULT_LAYOUTS_DIR.values()))
        for candidate in ordered:
            path = root / candidate
            if not path.exists():
                continue
            # ⚠️ Never migrate a directory onto itself, compared by INODE.
            # `resolve()` does NOT fold case on macOS — it hands back the
            # spelling it was given — so `Layouts` and `layouts` compare
            # unequal as paths while naming one directory. Measured: the
            # first draft of this guard used `resolve()` and did not fire.
            # `samefile` asks the filesystem, which is the thing that knows.
            try:
                if dest_dir_for_guard.exists() and os.path.samefile(
                        path, dest_dir_for_guard):
                    continue
            except OSError:
                pass
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
