"""Apply platform-specific filtering to a resolved layout tree.

Thin wrapper around the existing ``PlatformResolver`` so the hotload
server uses the same platform-override / platform-string-filter rules
that ``jui build`` applies at build time.
"""
from __future__ import annotations

from typing import Any

from ..core.platform_resolver import PlatformResolver, VALID_PLATFORMS


def filter_for_platform(node: Any, platform: str) -> Any:
    """Return a copy of *node* with platform overrides merged and
    non-matching string-valued ``platform`` filters dropped.

    Raises ``ValueError`` if *platform* is not one of iOS / Android /
    Web. Hotload only serves iOS + Android today; Web is accepted for
    symmetry in case anyone points a web client at the server.
    """
    if platform not in VALID_PLATFORMS:
        raise ValueError(
            f"Unknown platform {platform!r}. Valid: {', '.join(VALID_PLATFORMS)}"
        )
    return PlatformResolver(platform).resolve_tree(node)
