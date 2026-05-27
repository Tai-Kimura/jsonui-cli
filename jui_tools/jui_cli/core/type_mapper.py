"""Type mapping from spec types to platform-specific types.

Supports exact matches and generic patterns with ``$T`` style variables.

Examples of generic patterns in ``.jsonui-type-map.json``::

    "[$T]":        maps iOS "[Foo]" to Kotlin "List<Foo>"
    "$T?":         maps iOS "Foo?"  to TypeScript "Foo | undefined"
    "AsyncThrowingStream<$T,$E>": maps to "Flow<Foo>" on Android
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# Built-in defaults (used when no .jsonui-type-map.json is found)
_BUILTIN_TYPES = {
    "String": {"class": "String", "defaultValue": "", "web": {"class": "string"}},
    "Int": {"class": "Int", "defaultValue": 0, "web": {"class": "number"}},
    "Double": {"class": "Double", "defaultValue": 0.0, "web": {"class": "number"}},
    "Bool": {
        "class": "Bool",
        "defaultValue": False,
        "android": {"class": "Boolean"},
        "web": {"class": "boolean"},
    },
    "Void": {
        "class": "Void",
        "android": {"class": "Unit"},
        "web": {"class": "void"},
    },
    "Visibility": {"class": "String", "defaultValue": "gone"},
    "CollectionDataSource": {"class": "CollectionDataSource"},
    "callback": {
        "class": "(() -> Void)?",
        "android": {"class": "(() -> Unit)?"},
        "web": {"class": "(() => void) | undefined"},
    },
    "callback(String)": {
        "class": "((String) -> Void)?",
        "android": {"class": "((String) -> Unit)?"},
        "web": {"class": "((value: string) => void) | undefined"},
    },
    "callback(String,String)": {
        "class": "((String, String) -> Void)?",
        "android": {"class": "((String, String) -> Unit)?"},
        "web": {"class": "((oldValue: string, newValue: string) => void) | undefined"},
    },
    # Generic patterns ------------------------------------------------------
    # Swift array syntax → platform-native list types. Four shapes are
    # supported so spec authors can compose nullability freely:
    #   [$T]    — list, elements required
    #   [$T]?   — optional list, elements required
    #   [$T?]   — list, elements nullable
    #   [$T?]?  — optional list, elements nullable
    # Without the explicit nullable-element variants the pattern engine
    # would only match the elements-required forms and `[String?]` would
    # leak through to the Kotlin/TS protocols verbatim.
    "[$T]": {
        "class": "[$T]",
        "android": {"class": "List<$T>"},
        "web": {"class": "$T[]"},
    },
    "[$T]?": {
        "class": "[$T]?",
        "android": {"class": "List<$T>?"},
        "web": {"class": "$T[] | undefined"},
    },
    "[$T?]": {
        "class": "[$T?]",
        "android": {"class": "List<$T?>"},
        "web": {"class": "($T | null)[]"},
    },
    "[$T?]?": {
        "class": "[$T?]?",
        "android": {"class": "List<$T?>?"},
        "web": {"class": "($T | null)[] | undefined"},
    },
    "$T?": {
        "class": "$T?",
        "android": {"class": "$T?"},
        "web": {"class": "$T | undefined"},
    },
    "Array($T)": {
        "class": "[$T]",
        "android": {"class": "List<$T>"},
        "web": {"class": "$T[]"},
    },
    # Canonical `List(T)` alias — same shape as `Array(T)`. Spec authors
    # reach for either spelling interchangeably; without this entry the
    # iOS Swift Protocol leaks `List(Foo)` verbatim and fails to compile
    # (Swift has no `List(...)` syntax). Kotlin/TS are symmetric since
    # both generators route through this same TypeMapper.
    "List($T)": {
        "class": "[$T]",
        "android": {"class": "List<$T>"},
        "web": {"class": "$T[]"},
    },
    "AsyncThrowingStream<$T,$E>": {
        "class": "AsyncThrowingStream<$T, $E>",
        "android": {
            "class": "Flow<$T>",
            "imports": ["kotlinx.coroutines.flow.Flow"],
        },
        "web": {"class": "AsyncIterable<$T>"},
    },
    "[String: Any]": {
        "class": "[String: Any]",
        "android": {"class": "Map<String, Any>"},
        "web": {"class": "Record<string, any>"},
    },
    # Kotlin-style `Map(K, V)` / optional `Map(K, V)?` translated per-platform.
    # `$K`/`$V` bind to whatever the author writes (primitive or custom type).
    "Map($K,$V)": {
        "class": "[$K: $V]",
        "android": {"class": "Map<$K, $V>"},
        "web": {"class": "Record<$K, $V>"},
    },
    # Swift built-in types that have platform-specific Kotlin / TS equivalents.
    "Data": {
        "class": "Data",
        "android": {"class": "ByteArray"},
        "web": {"class": "Uint8Array"},
    },
    # Android-side image type. iOS/Web pass-through is a placeholder —
    # in practice a Bitmap-typed param is `platforms: ["android"]` only,
    # so the iOS/Web Protocols never see it. Carrying the Android import
    # hint here lets the generator emit `import android.graphics.Bitmap`
    # automatically without each project needing a local type-map entry.
    "Bitmap": {
        "class": "Bitmap",
        "android": {
            "class": "Bitmap",
            "imports": ["android.graphics.Bitmap"],
        },
    },
    "URL": {
        "class": "URL",
        "android": {"class": "String"},
        "web": {"class": "string"},
    },
    "Date": {
        "class": "Date",
        "android": {"class": "java.time.Instant"},
        "web": {"class": "Date"},
    },
}


_VAR_RE = re.compile(r"\$(\w+)")


class TypeMapper:
    """Maps spec types to platform-specific types using .jsonui-type-map.json."""

    def __init__(self, type_map_path: Path | None = None):
        self._types: dict[str, dict] = dict(_BUILTIN_TYPES)
        if type_map_path and type_map_path.exists():
            self._load(type_map_path)

    def _load(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._types.update(data.get("types", {}))
        # User entries shadow built-ins and any subsequently auto-registered
        # swagger schemas. We remember the user-defined keys so
        # ``register_schemas`` can skip them and report the shadowing.
        self._user_keys: set[str] = set(data.get("types") or {})

    def user_keys(self) -> set[str]:
        """Names that the user explicitly declared in ``.jsonui-type-map.json``.

        Used by ``api_model_sync`` to skip DTO emit + Domain scaffold
        patching for schemas the consumer has hand-taken-over via a
        type-map shadow entry. Returns a copy so callers can mutate
        without affecting the mapper.
        """
        return set(getattr(self, "_user_keys", set()))

    def register_schemas(self, schema_names: list[str]) -> list[str]:
        """Register swagger-derived schema names as pass-through types.

        Each registered name resolves to the same identifier on every
        platform (Domain wrapper type is identical across iOS/Android/Web —
        ``User`` is always ``User``). The point of the registration is
        :meth:`is_registered`, which ``jui verify`` uses to decide which
        type identifiers to flag as missing from ``.jsonui-type-map.json``.

        Per plan §9.2 / C5: **manual entries from
        ``.jsonui-type-map.json`` always win**. This method silently
        skips any name already present in the user map and returns the
        list of skipped (shadowed) names so the caller can surface an
        info-level log.
        """
        shadowed: list[str] = []
        user_keys = getattr(self, "_user_keys", set())
        for name in schema_names:
            if name in user_keys:
                shadowed.append(name)
                continue
            # Don't clobber an existing entry that came from a previous
            # call — registration is idempotent across multiple swagger
            # docs that mention the same schema name.
            if name in self._types and name not in user_keys:
                continue
            self._types[name] = {"class": name}
        return shadowed

    def resolve(self, spec_type: str, platform: str = "ios") -> dict[str, Any]:
        """Resolve a spec type to class name, default value, and imports.

        Resolution order:
        0. Pipe-union (``A|B|C`` = android|ios|web) → pick the right segment
           for *platform* before further resolution. Spec authors use this
           when one logical type maps to different native types per language
           (e.g. ``"ByteArray|Data"`` → Kotlin ``ByteArray``, Swift ``Data``).
        1. Exact match against a key in the type map.
        2. Generic pattern match (keys containing ``$T`` style variables).
           Longer patterns are tried first, so more specific patterns win.
        3. Pass-through — return the spec type as-is.

        Result shape::

            {"class": str, "defaultValue": Any, "imports": list[str]}
        """
        spec_type = _pick_union_segment(spec_type, platform)
        # 1. Exact match
        entry = self._types.get(spec_type)
        if entry is not None:
            return self._apply_platform(entry, platform, fallback=spec_type)

        # 2. Pattern match (longest pattern first so specific > generic)
        patterns = sorted(
            (p for p in self._types if "$" in p),
            key=len,
            reverse=True,
        )
        for pattern in patterns:
            bindings = self._match_pattern(pattern, spec_type)
            if bindings is None:
                continue
            entry = self._types[pattern]
            resolved = self._apply_platform(entry, platform, fallback=spec_type)
            resolved["class"] = self._substitute(resolved["class"], bindings, platform)
            # Collect imports from captured variable types too
            nested_imports: list[str] = []
            for value in bindings.values():
                for imp in self.resolve_imports(value, platform):
                    if imp not in resolved["imports"] and imp not in nested_imports:
                        nested_imports.append(imp)
            resolved["imports"].extend(nested_imports)
            return resolved

        # 3. Pass-through
        return {"class": spec_type, "defaultValue": None, "imports": []}

    def resolve_class(self, spec_type: str, platform: str = "ios") -> str:
        """Shorthand: get just the class name."""
        return self.resolve(spec_type, platform)["class"]

    def resolve_default(self, spec_type: str, platform: str = "ios") -> Any:
        """Shorthand: get just the default value."""
        return self.resolve(spec_type, platform)["defaultValue"]

    def resolve_imports(self, spec_type: str, platform: str = "ios") -> list[str]:
        """Shorthand: get just the list of import statements required."""
        return list(self.resolve(spec_type, platform).get("imports") or [])

    def resolve_in_string(self, source: str, platform: str = "ios") -> str:
        """Walk *source* and resolve every atomic type expression in place.

        Used for structural type strings (closures, tuples) where we want
        to translate sub-types like ``Bool``, ``Array(Foo)``, or ``[Foo]``
        without parsing the entire shape. Each PascalCase identifier (with
        optional ``(..)`` / ``<..>`` generic args and optional ``?``) and
        each ``[..]`` subscript is fed to :meth:`resolve_class`; everything
        else (commas, ``->``, whitespace, structural parens) is preserved
        verbatim.
        """
        if not source:
            return source
        out: list[str] = []
        i = 0
        n = len(source)
        while i < n:
            ch = source[i]
            if "A" <= ch <= "Z":
                j = i + 1
                while j < n and (source[j].isalnum() or source[j] == "_"):
                    j += 1
                # Allow nested-type qualifier (Parent.Child)
                while j < n and source[j] == "." and j + 1 < n and "A" <= source[j + 1] <= "Z":
                    j += 1
                    while j < n and (source[j].isalnum() or source[j] == "_"):
                        j += 1
                # Optional generic args
                if j < n and source[j] == "(":
                    close = _match_balanced(source, j, "(", ")")
                    if close != -1:
                        j = close + 1
                elif j < n and source[j] == "<":
                    close = _match_balanced(source, j, "<", ">")
                    if close != -1:
                        j = close + 1
                # Optional `?`
                if j < n and source[j] == "?":
                    j += 1
                expr = source[i:j]
                out.append(self.resolve_class(expr, platform))
                i = j
            elif ch == "[":
                close = _match_balanced(source, i, "[", "]")
                if close != -1:
                    end = close + 1
                    if end < n and source[end] == "?":
                        end += 1
                    out.append(self.resolve_class(source[i:end], platform))
                    i = end
                else:
                    out.append(ch)
                    i += 1
            else:
                out.append(ch)
                i += 1
        return "".join(out)

    def is_registered(self, spec_type: str) -> bool:
        """Return True if *spec_type* matches a type-map entry.

        Covers exact matches and generic pattern matches. Pipe-union inputs
        resolve via ``_pick_union_segment`` like ``resolve()`` does, then any
        of the segments being registered is enough.
        """
        segs = [s.strip() for s in spec_type.split("|")] if "|" in spec_type else [spec_type]
        for seg in segs:
            if not seg:
                continue
            # Strip trailing ? — nullability is handled by $T? pattern in
            # builtins, so a bare `Foo?` with Foo unregistered still counts
            # as unregistered.
            bare = seg.rstrip("?").strip()
            if bare in self._types:
                return True
            for pattern in self._types:
                if "$" not in pattern:
                    continue
                if self._match_pattern(pattern, bare) is not None:
                    return True
                if self._match_pattern(pattern, seg) is not None:
                    return True
        return False

    # --- Internal helpers --------------------------------------------------

    @staticmethod
    def _apply_platform(entry: dict, platform: str, fallback: str) -> dict[str, Any]:
        """Pick the platform-specific override or fall back to the base entry."""
        platform_key = {"ios": "ios", "android": "android", "web": "web"}.get(platform, platform)
        base_class = entry.get("class", fallback)
        base_default = entry.get("defaultValue")
        base_imports = list(entry.get("imports") or [])
        if platform_key in entry:
            override = entry[platform_key]
            if isinstance(override, dict):
                overlay_imports = list(override.get("imports") or [])
                return {
                    "class": override.get("class", base_class),
                    "defaultValue": override.get("defaultValue", base_default),
                    "imports": overlay_imports or base_imports,
                }
        return {
            "class": base_class,
            "defaultValue": base_default,
            "imports": base_imports,
        }

    @staticmethod
    def _match_pattern(pattern: str, target: str) -> dict[str, str] | None:
        """Match a pattern like ``[$T]`` against ``[Foo]``.

        Returns a ``{var_name: value}`` dict on success, ``None`` otherwise.
        The capture character class depends on how many variables the
        pattern contains:

        - Single variable (``$T`` / ``$T?`` / ``[$T]``) — allow commas so the
          variable can absorb nested generics like ``Map(String, String)``.
        - Multiple variables (``<$T,$E>`` / ``Map($K,$V)``) — disallow
          commas so the variables split correctly.

        Brackets / angle brackets / question marks are always excluded so
        structural tokens stay literal.
        """
        escaped = re.escape(pattern)
        # re.escape turns $ into \$; variable names stay intact after it.
        var_count = len(re.findall(r"\\\$\w+", escaped))
        if var_count <= 1:
            capture = r"(?P<\1>[^<>\[\]?]+)"
        else:
            capture = r"(?P<\1>[^,<>\[\]?]+)"
        regex = re.sub(r"\\\$(\w+)", capture, escaped)
        m = re.fullmatch(regex, target.strip())
        if not m:
            return None
        return {k: v.strip() for k, v in m.groupdict().items()}

    def _substitute(self, class_str: str, bindings: dict[str, str], platform: str) -> str:
        """Replace ``$T`` placeholders in *class_str* using *bindings*.

        Each captured value is recursively resolved through the type map so
        nested generics work, e.g. ``[ItemImage]`` on Kotlin becomes
        ``List<ItemImage>`` where ``ItemImage`` passes through.
        """
        def _replace(match: re.Match) -> str:
            name = match.group(1)
            value = bindings.get(name, match.group(0))
            return self.resolve_class(value, platform)

        return _VAR_RE.sub(_replace, class_str)


def _match_balanced(s: str, start: int, open_ch: str, close_ch: str) -> int:
    """Return the index of the matching ``close_ch`` for the ``open_ch`` at
    *start*, or ``-1`` if unmatched. Tracks nested pairs of the same kind."""
    depth = 1
    i = start + 1
    while i < len(s):
        if s[i] == open_ch:
            depth += 1
        elif s[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


# Pipe-union segment order. Spec authors write one type field that resolves
# to different natives per platform; this is the positional convention.
_UNION_ORDER = ("android", "ios", "web")


def _pick_union_segment(spec_type: str, platform: str) -> str:
    """Split ``"A|B|C"`` into platform-specific segments.

    Rules:
    - No ``|`` → pass-through
    - ``->`` in string → pass-through (don't touch closure types)
    - 1 segment → pass-through
    - 2 segments → ``android|ios`` (web falls back to ios)
    - 3 segments → ``android|ios|web``
    - 4+ segments → first three map to android/ios/web, rest ignored
    """
    if "|" not in spec_type or "->" in spec_type:
        return spec_type
    segs = [s.strip() for s in spec_type.split("|")]
    if len(segs) == 1:
        return segs[0]
    # Strip trailing `?` on the whole union — optional applies to any segment.
    optional = all(s.endswith("?") for s in segs)
    if optional:
        segs = [s[:-1].rstrip() for s in segs]
    layout = _UNION_ORDER[: max(2, min(len(segs), 3))]
    idx = layout.index(platform) if platform in layout else len(layout) - 1
    if idx >= len(segs):
        idx = len(segs) - 1
    result = segs[idx]
    return f"{result}?" if optional else result
