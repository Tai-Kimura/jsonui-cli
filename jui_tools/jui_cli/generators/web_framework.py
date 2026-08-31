"""The web framework a project targets, read from its own declaration.

`rjui.config.json` already carries `web_framework`, and `rjui_tools`'
`Core::Frameworks` resolves every framework-specific string the web codegen
emits from it — router imports, router types, link wiring, the RSC
directive — so that "Emitters stay framework-neutral and ask the adapter".

The scaffold generator here was not asking. It wrote Next's router type
into every ViewModel it scaffolded, which is a second implementation of a
decision the Ruby side already owns: a project that declares a custom
adapter got a scaffold contradicting its own declaration, and the failure
reads as a mistake by whoever ran the generator rather than as a tool that
ignored the config.

This mirrors only the two fields the Python scaffold emits. The resolution
itself — absent means `next`, a string names a built-in, an object declares
a custom adapter with neutral defaults — follows
``Core::Frameworks.for`` exactly, and the parity vectors in
``test_web_framework_adapter.py`` are what keep the mirror from becoming a
second decision.
"""
from __future__ import annotations

CONFIG_KEY = "web_framework"
DEFAULT_FRAMEWORK = "next"

#: Next.js App Router — the reference adapter. Its values are the historical
#: emit, byte for byte, so a project that declares nothing sees no change.
_NEXT = {
    "router_type_import": (
        'import { AppRouterInstance } from '
        '"next/dist/shared/lib/app-router-context.shared-runtime";'
    ),
    "router_type": "AppRouterInstance",
}

#: Neutral defaults for a custom adapter: no import, untyped router. Mirrors
#: CustomAdapter::DEFAULTS for the keys read here.
_CUSTOM_DEFAULTS = {
    "router_type_import": "",
    "router_type": "any",
}

_REGISTRY = {"next": _NEXT}

#: Keys a custom adapter may declare, from CustomAdapter::ALLOWED_KEYS. The
#: full list is validated even though only two are read: a typo in a key
#: this generator ignores is still a typo the project wants to hear about,
#: and staying silent here would make the two tools disagree about whether
#: the config is valid.
_ALLOWED_KEYS = frozenset({
    "name",
    "use_client_directive",
    "link_import_line",
    "link_href_attribute",
    "router_hook_import",
    "router_hook_statement",
    "router_type_import",
    "router_type",
    "router_type_jsdoc",
})


class WebFrameworkError(ValueError):
    """The project's `web_framework` declaration cannot be resolved."""


def resolve(rjui_config: dict | None) -> dict:
    """Adapter values for *rjui_config*. Absent declaration means Next."""
    raw = (rjui_config or {}).get(CONFIG_KEY)
    if raw is None:
        return dict(_REGISTRY[DEFAULT_FRAMEWORK])
    if isinstance(raw, str):
        adapter = _REGISTRY.get(raw)
        if adapter is None:
            raise WebFrameworkError(
                f"Unknown web_framework '{raw}' in rjui.config.json "
                f"(built-in: {', '.join(sorted(_REGISTRY))}; or declare a "
                "custom adapter object)"
            )
        return dict(adapter)
    if isinstance(raw, dict):
        unknown = sorted(set(raw) - _ALLOWED_KEYS)
        if unknown:
            raise WebFrameworkError(
                f"Unknown web_framework key(s) {', '.join(unknown)} "
                f"(allowed: {', '.join(sorted(_ALLOWED_KEYS))})"
            )
        bad = sorted(k for k, v in raw.items() if not isinstance(v, str))
        if bad:
            raise WebFrameworkError(
                f"web_framework key(s) {', '.join(bad)} must be strings"
            )
        values = dict(_CUSTOM_DEFAULTS)
        values.update({k: v for k, v in raw.items() if k in values})
        return values
    raise WebFrameworkError(
        "web_framework must be a built-in name string or a custom adapter "
        f"object (got {type(raw).__name__})"
    )
