"""Prose fields of a spec that live in a YAML texts file, as Markdown.

A spec's prose — `description`, `notes`, `intent` — is written inline as a
JSON string. That is fine for a sentence and unreadable for a page: a 27 KB
`metadata.description` is one line of `\\n` escapes, and it renders as one
paragraph. So a prose field may instead point into a YAML file:

    "intent": { "md": "user_repository.health_check.timeout" }
    "intent": { "md": "shared/network.texts.yaml#timeouts.default" }

The first form reads the spec's paired file (`foo.spec.json` ->
`foo.texts.yaml`, next to it); the second names a file relative to the spec's
directory. The key is a `.`-separated path through nested mappings, and the
value at its end is a string, rendered as Markdown. A plain string field is
untouched and stays plain text — Markdown is what a reference opts into, never
what an inline string is reinterpreted as, so no existing spec changes meaning.

Resolved ONCE, where a spec is read (`resolve_spec_texts`), into
`MarkdownText` — a `str` subclass. Every reader that treats the field as a
string keeps working on the Markdown source; only a renderer that asks
`isinstance(v, MarkdownText)` treats it as Markdown. The alternative — each
reader learning the `{"md": ...}` shape — is a change to every reader, and the
first one missed would print a dict repr into a generated test.

The YAML rules, each of which exists because the permissive reading is a
silent wrong answer:

- keys are strings: YAML 1.1 reads `yes:` / `on:` as booleans and `1:` as an
  int, and a key nobody can spell in a reference is a text nobody can reach;
- keys hold no `.`: the `.` is the path separator, so `a.b` as a key and `a`
  -> `b` as a path could not be told apart;
- a key appears once per mapping: PyYAML keeps the LAST of two, so the first
  would vanish without a word;
- a value is a string or a mapping: a list has no stable key (reordering it
  would re-point every reference), and a number or null is not prose.

Only the stdlib is imported at module level: this file is loaded by path from
tools that run without pip (see `jsonui_doc_cli/shared_core.py`). PyYAML is
imported when a reference is actually met, and its absence is an error that
says how to install it, rather than a crash or a skipped check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: The spec keys whose value may be a reference. Prose only: a reference in an
#: identifier or a type is not a text, and resolving it there would hand a
#: Markdown page to a reader that expects a name.
TEXT_KEYS = ("description", "notes", "intent")

#: The paired file's suffix, replacing the spec's `.spec.json` /
#: `.component.json` / `.json`.
TEXTS_SUFFIX = ".texts.yaml"

_REF_KEY = "md"
_INSTALL_HINT = "pip install pyyaml"


class MarkdownText(str):
    """A prose value that came from a texts file and is Markdown.

    `source` is `<file>#<key>` as written in the reference, for messages.
    """

    source: str = ""

    def __new__(cls, text: str, source: str = "") -> "MarkdownText":
        obj = super().__new__(cls, text)
        obj.source = source
        return obj


def is_markdown(value: Any) -> bool:
    return isinstance(value, MarkdownText)


def is_reference(value: Any) -> bool:
    """`{"md": ...}` — the whole shape, so a dict that merely has an `md` key
    among others is a malformed reference, reported, not a silent miss."""
    return isinstance(value, dict) and _REF_KEY in value


def paired_texts_path(spec_path: Path) -> Path:
    """`foo.spec.json` -> `foo.texts.yaml`, in the same directory."""
    name = spec_path.name
    for suffix in (".spec.json", ".component.json", ".json"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return spec_path.with_name(name + TEXTS_SUFFIX)


class _TextsFile:
    """One parsed texts file: its leaves by dotted key, or why it has none."""

    def __init__(self, path: Path):
        self.path = path
        self.leaves: dict[str, str] = {}
        self.branches: set[str] = set()
        self.errors: list[str] = []
        self.missing = False


def _yaml_loader():
    """A SafeLoader that refuses duplicate keys, or None without PyYAML."""
    try:
        import yaml
    except ImportError:
        return None, None

    class _StrictLoader(yaml.SafeLoader):
        pass

    def _mapping(loader, node, deep=False):
        seen: dict = {}
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            try:
                hash(key)
            except TypeError:
                raise yaml.constructor.ConstructorError(
                    None, None, "a key must be a plain string",
                    key_node.start_mark)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None,
                    f"duplicate key {key!r} (first at line "
                    f"{seen[key].line + 1}) — YAML would keep only the last",
                    key_node.start_mark)
            seen[key] = key_node.start_mark
        return loader.construct_mapping(node, deep=deep)

    _StrictLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
    return yaml, _StrictLoader


def _flatten(node: Any, prefix: str, out: _TextsFile) -> None:
    for key, value in node.items():
        where = f"{prefix}.{key}" if prefix else str(key)
        if not isinstance(key, str):
            # Not echoed back as `"True":` — the author wrote `yes:` (or
            # `on:`), and that spelling is gone by the time the key is here.
            out.errors.append(
                f"key {key!r} under '{prefix or '(top)'}' is a "
                f"{type(key).__name__}, not a string — YAML reads yes / no / "
                f"on / off / true / false and bare numbers as values; quote "
                f"the key if it is meant as a name")
            continue
        if "." in key:
            out.errors.append(
                f"key '{where}' contains '.', which is the path separator — "
                f"nest it as a mapping instead")
            continue
        if not key:
            out.errors.append(f"an empty key under '{prefix or '(top)'}'")
            continue
        if isinstance(value, str):
            out.leaves[where] = value
        elif isinstance(value, dict):
            out.branches.add(where)
            _flatten(value, where, out)
        else:
            shown = "empty" if value is None else f"a {type(value).__name__}"
            out.errors.append(
                f"'{where}' is {shown} — a value is a string (use `|` for "
                f"Markdown) or a mapping of more keys")


def load_texts_file(path: Path) -> _TextsFile:
    out = _TextsFile(path)
    if not path.is_file():
        out.missing = True
        return out
    yaml, loader = _yaml_loader()
    if yaml is None:
        out.errors.append(
            f"PyYAML is not installed, so {path.name} cannot be read — "
            f"{_INSTALL_HINT}")
        return out
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=loader)
    except (OSError, UnicodeDecodeError) as e:
        out.errors.append(f"cannot be read ({e})")
        return out
    except yaml.YAMLError as e:
        # `str(e)` carries PyYAML's own rendering — `in "<unicode string>",
        # line 7, column 3:` plus the source line and a caret — which names
        # no file and reads as a crash. The problem and its line are the
        # finding; the file is prefixed by the caller.
        mark = getattr(e, "problem_mark", None)
        problem = getattr(e, "problem", None)
        if mark is not None and problem:
            out.errors.append(f"line {mark.line + 1}: {problem}")
        else:
            out.errors.append(" ".join(str(e).split()))
        return out
    if data is None:
        return out
    if not isinstance(data, dict):
        out.errors.append(
            f"the top level is a {type(data).__name__}; it must be a mapping "
            f"of keys")
        return out
    _flatten(data, "", out)
    return out


class TextsResolution:
    """What `resolve_spec_texts` found: the resolved spec and its problems."""

    def __init__(self, data: Any):
        self.data = data
        self.errors: list[str] = []
        self.warnings: list[str] = []
        #: Every texts file a reference read, for callers that track inputs.
        self.files: list[Path] = []


def resolve_spec_texts(data: Any, spec_path: Path | str) -> TextsResolution:
    """Replace every `{"md": ...}` in a prose field with its `MarkdownText`.

    Returns a copy; `data` is not modified. A reference that cannot be
    resolved is left as it was and named in `errors`, so a caller that only
    renders still has something to show and a caller that validates refuses.

    A spec with no reference and no paired file costs one `is_file()` and
    returns an equal structure — the common case pays nothing else.
    """
    spec_path = Path(spec_path)
    base = spec_path.parent
    paired = paired_texts_path(spec_path)
    files: dict[Path, _TextsFile] = {}
    used: dict[Path, set[str]] = {}
    result = TextsResolution(None)

    def texts(path: Path) -> _TextsFile:
        key = path.resolve()
        if key not in files:
            loaded = load_texts_file(path)
            files[key] = loaded
            if not loaded.missing:
                result.files.append(path)
            for err in loaded.errors:
                result.errors.append(f"{_rel(path, base)}: {err}")
        return files[key]

    def resolve_ref(ref: dict, where: str) -> Any:
        extra = sorted(k for k in ref if k != _REF_KEY)
        target = ref.get(_REF_KEY)
        if extra or not isinstance(target, str) or not target.strip():
            result.errors.append(
                f"{where}: a text reference is {{\"md\": \"key\"}} or "
                f"{{\"md\": \"file.texts.yaml#key\"}}"
                + (f" — unexpected {', '.join(repr(k) for k in extra)}"
                   if extra else ""))
            return ref
        if "#" in target:
            file_part, key = target.split("#", 1)
            path = base / file_part
        else:
            file_part, key = "", target
            path = paired
        shown = f"{file_part or paired.name}#{key}"
        if not key:
            result.errors.append(f"{where}: '{target}' names no key after '#'")
            return ref
        loaded = texts(path)
        if loaded.missing:
            result.errors.append(
                f"{where}: '{shown}' — {_rel(path, base)} does not exist")
            return ref
        if key in loaded.leaves:
            used.setdefault(path.resolve(), set()).add(key)
            return MarkdownText(loaded.leaves[key], shown)
        if key in loaded.branches:
            result.errors.append(
                f"{where}: '{shown}' is a mapping, not a text — name one of "
                f"its keys")
        elif not loaded.errors:
            result.errors.append(f"{where}: '{shown}' is not defined")
        # A file with parse errors has already been reported once; a missing
        # key in it is a consequence, not a second finding.
        return ref

    def walk(node: Any, path: str, in_text: bool) -> Any:
        if isinstance(node, dict):
            if is_reference(node):
                if in_text:
                    return resolve_ref(node, path)
                result.errors.append(
                    f"{path}: a text reference is read only in "
                    f"{' / '.join(TEXT_KEYS)}")
                return node
            return {
                k: walk(v, f"{path}.{k}" if path else str(k), k in TEXT_KEYS)
                for k, v in node.items()
            }
        if isinstance(node, list):
            # `notes: [...]` — each entry is prose too. Deeper lists under a
            # text key are not prose, so the flag is not carried past one.
            return [walk(v, f"{path}[{i}]", in_text and not isinstance(v, list))
                    for i, v in enumerate(node)]
        return node

    result.data = walk(data, "", False)

    # A paired file exists for this spec alone, so a key nothing reads is
    # dead text — usually a reference renamed on one side only. A named file
    # may be shared by other specs, so one spec cannot call its keys unused.
    loaded = files.get(paired.resolve()) if paired.is_file() else None
    if loaded is None and paired.is_file():
        loaded = texts(paired)
    if loaded is not None and not loaded.errors:
        unused = sorted(set(loaded.leaves) - used.get(paired.resolve(), set()))
        if unused:
            shown = ", ".join(unused[:10]) + (" …" if len(unused) > 10 else "")
            result.warnings.append(
                f"{paired.name}: {len(unused)} key(s) no field of this spec "
                f"references: {shown}")
    return result


def _rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)
