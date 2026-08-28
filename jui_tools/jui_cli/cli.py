"""CLI entry point for jui command."""
from __future__ import annotations

import argparse
import sys

from .core.spec_extractor import CanonicalMarkError
from .version import version_label
from .commands.init_cmd import register_init_command, cmd_init
from .commands.generate_cmd import register_generate_command, cmd_generate
from .commands.build_cmd import register_build_command, cmd_build
from .commands.verify_cmd import register_verify_command, cmd_verify
from .commands.migrate_cmd import register_migrate_command, cmd_migrate_layouts
from .commands.lint_generated_cmd import register_lint_generated_command, cmd_lint_generated
from .commands.lint_strings_cmd import register_lint_strings_command, cmd_lint_strings
from .commands.ls_cmd import register_ls_command, cmd_ls
from .commands.sync_tool_cmd import register_sync_tool_command, cmd_sync_tool
from .commands.hotload_cmd import register_hotload_command, cmd_hotload
from .commands.conformance_cmd import register_conformance_command, cmd_conformance
from .commands.screens_cmd import register_screens_command, cmd_screens


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="jui",
        description="JsonUI cross-platform project tool",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version_label()}"
    )
    subparsers = parser.add_subparsers(dest="command")

    # jui init (i)
    register_init_command(subparsers)

    # jui generate (g)
    register_generate_command(subparsers)

    # jui build (b)
    register_build_command(subparsers)

    # jui verify
    register_verify_command(subparsers)

    # jui migrate-layouts
    register_migrate_command(subparsers)

    # jui lint-generated
    register_lint_generated_command(subparsers)

    # jui lint-strings
    register_lint_strings_command(subparsers)

    # jui ls (MCP discovery commands)
    register_ls_command(subparsers)

    # jui sync_tool
    register_sync_tool_command(subparsers)

    # jui hotload
    register_hotload_command(subparsers)

    # jui conformance
    register_conformance_command(subparsers)

    # jui screens — screen-identity classification (MCP consumes --json)
    register_screens_command(subparsers)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    command_map = {
        "init": cmd_init,
        "i": cmd_init,
        "generate": cmd_generate,
        "g": cmd_generate,
        "build": cmd_build,
        "b": cmd_build,
        "verify": cmd_verify,
        "migrate-layouts": cmd_migrate_layouts,
        "lint-generated": cmd_lint_generated,
        "lint-strings": cmd_lint_strings,
        "ls": cmd_ls,
        "sync_tool": cmd_sync_tool,
        "hotload": cmd_hotload,
        "conformance": cmd_conformance,
        "screens": cmd_screens,
    }

    handler = command_map.get(args.command)
    if handler:
        try:
            return handler(args)
        except CanonicalMarkError as exc:
            # Formatted, not a traceback. The message was already specific
            # enough to act on — a lane read it straight off a red run — but
            # seven frames of Python above it read as "the tool crashed", and
            # the next person to hit it looks at the tool instead of the spec.
            print(f"\nERROR: {exc}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
