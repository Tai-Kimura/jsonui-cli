"""Which swagger endpoints this project actually consumes.

One swagger is often shared by several front-ends, each declaring the slice
it owns in ``jui.config.json``. DTO codegen already honours that declaration
(``jui build`` prints "filtered out N schema(s) not reachable from configured
paths/schemas"); the mock checker did not, so every endpoint belonging to
another realm was reported as a mock the project had failed to write.

That is not a cosmetic miscount. A gate that is red for 66 endpoints nobody
can call is a gate people stop reading, and the one real MISSING that appears
later is invisible inside it.

Glob semantics are copied from ``jui_cli.core.schema_filter`` on purpose —
the same patterns must select the same endpoints in both tools:

- ``*`` matches any string including ``/`` (no special ``**``)
- patterns are case-sensitive and match the whole path
- ``fnmatch.translate`` does the translation, for portability

(The two implementations are separate because ``jsonui-test-cli`` installs
without ``jui_tools``; the duplication is four lines and a shared test
vector beats a dependency.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import translate
from functools import lru_cache


def _patterns(raw) -> tuple:
    """Normalise a config value to a tuple of glob strings.

    Missing, ``None`` and ``[]`` all mean "no restriction on this dimension",
    and a bare string is accepted where a list is expected — mirroring how
    ``api.schemas.*`` is read on the codegen side.
    """
    if raw is None or raw == []:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, (list, tuple)):
        return tuple(p for p in raw if isinstance(p, str) and p)
    return ()


@lru_cache(maxsize=None)
def _compile(patterns) -> "re.Pattern | None":
    """Compiled matcher for a glob tuple. Cached: `covers` runs once per
    endpoint per check, and a shared swagger has hundreds of them."""
    if not patterns:
        return None
    return re.compile("|".join(translate(p) for p in patterns))


@dataclass(frozen=True)
class PathScope:
    """The set of API paths a project declares it consumes."""

    include: tuple = ()
    exclude: tuple = ()

    @classmethod
    def from_config(cls, data) -> "PathScope":
        """Resolve the scope from a whole ``jui.config.json`` document.

        ``mock.includePaths`` / ``mock.excludePaths`` win when either is set,
        so a project whose mocks legitimately cover more than its DTOs can say
        so. Otherwise ``api.schemas.include_paths`` / ``exclude_paths`` is
        reused: it already states the same thing, and asking a project to
        repeat itself is how the two drift apart.
        """
        if not isinstance(data, dict):
            return cls()
        mock = data.get("mock") if isinstance(data.get("mock"), dict) else {}
        include = _patterns(mock.get("includePaths"))
        exclude = _patterns(mock.get("excludePaths"))
        if include or exclude:
            return cls(include=include, exclude=exclude)

        api = data.get("api") if isinstance(data.get("api"), dict) else {}
        schemas = api.get("schemas") if isinstance(api.get("schemas"), dict) else {}
        return cls(
            include=_patterns(schemas.get("include_paths")),
            exclude=_patterns(schemas.get("exclude_paths")),
        )

    def is_active(self) -> bool:
        return bool(self.include or self.exclude)

    def covers(self, path) -> bool:
        """True when *path* is inside the declared scope.

        An empty scope covers everything — a project that has not declared
        one is asking for the whole swagger, which is the behaviour every
        existing project already has.
        """
        if not isinstance(path, str):
            return True
        include_re = _compile(self.include)
        exclude_re = _compile(self.exclude)
        if include_re is not None and not include_re.match(path):
            return False
        if exclude_re is not None and exclude_re.match(path):
            return False
        return True

    def describe(self) -> str:
        """One-line summary for the check output."""
        parts = []
        if self.include:
            parts.append(f"include {', '.join(self.include)}")
        if self.exclude:
            parts.append(f"exclude {', '.join(self.exclude)}")
        return "; ".join(parts) or "all paths"
