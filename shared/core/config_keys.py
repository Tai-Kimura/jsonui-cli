"""Which top-level keys `jui.config.json` has meaning for.

A misspelled key does nothing and says nothing. That is how `extends` was
found to fail twice in one day: first a value that named no file, reported in
v1.7.9, and then the key itself written `extend` — which is not a broken
declaration, it is no declaration, and the tools have never had an opinion
about keys they do not recognise.

The visible effect is that the settings simply do not arrive. For `extends`
that means the naming convention is not read and parameter names come out
spelled the API document's way; for `mockDir` it would mean the contract check
does not run. In both cases the run is green and the output is exactly what a
project that never configured the thing would produce. Only A/B finds it.

The set is a declaration, not logic: each key is read by exactly one tool
(`test` by two), so nothing here can drift out of step with behaviour without
a key being added somewhere and not added here — which the corpus check below
turns into a failing test rather than a silent gap.

Keys beginning with `_` are notes. Two consumer configs already carry `_note`
and `_comment`, and a config is a reasonable place to explain itself.
"""

from __future__ import annotations

#: Read by `jui` itself (see jui_tools/jui_cli/core/config_manager.py).
_JUI = frozenset({
    "project_name", "platforms", "api", "api_directory",
    "spec_directory", "component_spec_directory", "layouts_directory",
    "styles_directory", "images_directory", "strings_file", "type_map_file",
    "document_tools_path", "lint", "verify", "test",
})

#: Read by `jsonui-doc`.
_DOC = frozenset({"checks", "databases"})

#: Read by `jsonui-test`.
_TEST = frozenset({"mock", "test"})

#: Read by shared/core, on behalf of both.
_SHARED = frozenset({"spec", "extends"})

KNOWN_TOP_LEVEL = _JUI | _DOC | _TEST | _SHARED

#: A key that begins with this is a note to a reader, not a setting.
NOTE_PREFIX = "_"


def unknown_keys(config) -> list:
    """Top-level keys no tool reads, sorted. Empty for a correct config."""
    if not isinstance(config, dict):
        return []
    return sorted(
        key for key in config
        if isinstance(key, str)
        and not key.startswith(NOTE_PREFIX)
        and key not in KNOWN_TOP_LEVEL
    )


def message(path, keys) -> str:
    listed = ", ".join(repr(k) for k in keys)
    near = _nearest(keys)
    hint = f" Did you mean {near!r}?" if near else ""
    return (
        f"{path}: no tool reads {listed}.{hint} A key nothing recognises is "
        "silently ignored, so the settings under it never arrive and the run "
        "looks like one that never configured them. Prefix a key with '_' if "
        "it is a note."
    )


def _nearest(keys):
    """The known key one edit away, when there is exactly one.

    Deliberately narrow. A suggestion that is usually wrong trains readers to
    skip the whole message, and the message is useful without it.
    """
    for key in keys:
        matches = [k for k in KNOWN_TOP_LEVEL if _one_edit_apart(key, k)]
        if len(matches) == 1:
            return matches[0]
    return None


def _one_edit_apart(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(long)):
        if long[:i] + long[i + 1:] == short:
            return True
    return False
