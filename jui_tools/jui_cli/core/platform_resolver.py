"""Resolve platform-specific overrides in Layout JSON at build time.

Each node may contain a ``platform`` key with per-platform attribute
overrides.  ``PlatformResolver`` merges the target platform's overrides
into the base attributes and removes the ``platform`` key from the
output, producing a platform-specific Layout JSON.

Example input::

    {
        "type": "View",
        "height": 200,
        "platform": {
            "ios": {"height": 220},
            "android": {"height": 180},
            "web": {"height": "100vh", "maxWidth": 1200}
        }
    }

After resolving for iOS::

    {"type": "View", "height": 220}

The ``responsive`` key (if present) is left untouched — it is resolved
at runtime by each platform's framework.
"""
from __future__ import annotations

from typing import Any

VALID_PLATFORMS = ("ios", "android", "web")

# String-valued "platform" filter — maps each target platform to language/framework
# tokens commonly seen in legacy SwiftJsonUI / KotlinJsonUI / ReactJsonUI layouts.
PLATFORM_LANG_MAP = {
    "ios": {"ios", "swift", "swiftui", "uikit"},
    "android": {"android", "kotlin", "java", "compose", "xml"},
    "web": {"web", "typescript", "javascript", "react"},
}


class PlatformResolver:
    """Resolve ``platform`` overrides for a single target platform."""

    def __init__(self, target_platform: str):
        if target_platform not in VALID_PLATFORMS:
            raise ValueError(
                f"Unknown platform {target_platform!r}. "
                f"Valid: {', '.join(VALID_PLATFORMS)}"
            )
        self._platform = target_platform
        self._valid_tokens = PLATFORM_LANG_MAP[target_platform]

    def resolve_tree(self, node: Any) -> Any:
        """Walk the JSON tree and merge platform overrides recursively.

        - Dict-valued ``platform`` (``{"ios": {...}, "android": {...}}``):
          merge the target platform's overrides into the node.
        - String-valued ``platform`` (``"swift"``, ``"android"``, etc.):
          act as a filter — if the value does not match the target
          platform, the node is dropped (returns ``None``).
        """
        if isinstance(node, dict):
            # String-valued platform filter — skip node when not a match
            p = node.get("platform")
            if isinstance(p, str):
                tokens = {t.strip().lower() for t in p.split(",") if t.strip()}
                if tokens and tokens.isdisjoint(self._valid_tokens):
                    return None

            result: dict[str, Any] = {}
            platform_overrides: dict[str, Any] = {}

            for k, v in node.items():
                if k == "platform":
                    # Dict-valued: merge target platform's overrides below.
                    if self._is_override_map(v):
                        platform_overrides = v.get(self._platform, {})
                        if not isinstance(platform_overrides, dict):
                            platform_overrides = {}
                        continue
                    # String-valued: build-time filter was consumed above;
                    # drop the key so downstream validators don't see it as
                    # an unknown attribute.
                    if isinstance(v, str):
                        continue
                resolved = self.resolve_tree(v)
                result[k] = resolved

            # Merge platform-specific overrides (override wins)
            for k, v in platform_overrides.items():
                result[k] = self.resolve_tree(v)

            return result
        elif isinstance(node, list):
            resolved_items = [self.resolve_tree(item) for item in node]
            return [item for item in resolved_items if item is not None]
        else:
            return node

    @staticmethod
    def _is_override_map(value: Any) -> bool:
        """Return True if *value* looks like a platform override dict.

        A valid override map is a dict whose keys are a subset of the
        known platform names.  A simple string like ``"swift"`` or a
        dict with non-platform keys (e.g. ``{"class": "..."}`` ) is
        NOT an override map.
        """
        if not isinstance(value, dict):
            return False
        if not value:
            return False
        return all(k in VALID_PLATFORMS for k in value)

    @staticmethod
    def has_platform_key(node: Any) -> bool:
        """Quick check: does the tree contain any ``platform`` filter/override?

        Returns True for either a dict-valued override map or a
        string-valued platform filter.
        """
        if isinstance(node, dict):
            v = node.get("platform")
            if v is not None:
                if isinstance(v, str) and v.strip():
                    return True
                if PlatformResolver._is_override_map(v):
                    return True
            return any(
                PlatformResolver.has_platform_key(child)
                for child in node.values()
            )
        elif isinstance(node, list):
            return any(PlatformResolver.has_platform_key(item) for item in node)
        return False
