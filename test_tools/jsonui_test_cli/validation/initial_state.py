"""`initialState`: what a test file asks to be put into a screen's Data.

Contract: jsonui-test-runner spec §10 (specs/2026-07-08-advanced-test-features.md)
and its vectors, vendored into shared/core/:

- initial_state_payload_vectors.json: which test files are validate errors and
  warnings, by code (CODE_* below);
- initial_state_coercion_vectors.json: which values a Data class accepts, and
  the reason for each one it rejects (`judge`).

What validate checks, and why each is not left to the run:

- the shape (an object with `viewModel` on a screen test or a case,
  `viewModels` of objects on a flow);
- a case-level initialState under `caseIsolation: shared` — the screen opens
  once, before the first case, so it cannot be delivered and the driver fails
  that case (`case-initial-state-needs-reopen`);
- a flow's `initialState.screen`, removed from the schema
  (`flow-initial-state-screen-removed`);
- a flow's `viewModels` keys, which are screen ids (the screen-id rules);
- each key and value against the Data the screen's layout declares, on every
  platform the file runs on, judged as the app judges it (§10.3): the app
  rejects what does not fit, and the driver then fails the file's cases;
- a flow step that references a file or case with an initialState — not
  applied inside the flow (`referenced-initial-state-ignored`, a warning).

An empty initialState is the same as none (§10.2) everywhere here.

The layout comes from the screen index the screen-id check already builds
(`screen_ids.load_screen_index`: the config the run read), and its Data from
shared/core/layout_data_fields.py, the collector held to the three
generators. When either is unavailable the values are not checked and the
file says so once (INFO): silence would read as "checked and clean".
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from .models import ValidationMessage, ValidationResult

CODE_CASE_NEEDS_REOPEN = "case-initial-state-needs-reopen"
CODE_REFERENCED_IGNORED = "referenced-initial-state-ignored"
CODE_FLOW_SCREEN_REMOVED = "flow-initial-state-screen-removed"

PLATFORMS = ("ios", "android", "web")

#: Per platform: the key a per-platform class is written under, the mode the
#: generator builds, and its modes in fallback order — TypeConverter
#: LANGUAGE / MODES of sjui, kjui and rjui, read by `extract_platform_value`.
_CLASS_KEYS = {
    "ios": ("swift", "swiftui", ("swiftui", "uikit")),
    "android": ("kotlin", "compose", ("compose", "xml")),
    "web": ("typescript", "react", ("react",)),
}


def is_empty(value) -> bool:
    """An initialState that delivers nothing: `{}`, `{"viewModel": {}}`,
    `{"viewModels": {}}`. Spec §10.2: the same as none — no payload, no
    launch, nothing for a driver to read or to ignore.

    Anything else counts as written, a malformed value included: its shape
    is the shape check's finding, not a reason to treat it as absent.
    """
    return isinstance(value, dict) and all(v == {} for v in value.values())


# ---------------------------------------------------------------- the value rules

#: Scalar classes, by lower-case spelling, to the JSON kind they accept
#: (§10.3: `Integer` is `Int`, `Number` is `Double`, `Boolean` / `bool` are
#: `Bool`, lower-case spellings are their capitalised class).
_SCALARS = {
    "string": "string", "int": "int", "integer": "int",
    "double": "number", "float": "number", "cgfloat": "number", "number": "number",
    "bool": "boolean", "boolean": "boolean", "color": "string",
}
_ELEMENT = (re.compile(r"^Array\((.+)\)$"), re.compile(r"^\[(.+)\]$"), re.compile(r"^List<(.+)>$"))
_INT_MIN, _INT_MAX = -2147483648, 2147483647


def _scalar(name: str) -> str | None:
    return _SCALARS.get(name.strip().lower())


def _shape(base: str):
    """(kind, element kind) a class takes, or None when it is unsupported."""
    scalar = _scalar(base)
    if scalar:
        return scalar, None
    for pattern in _ELEMENT:
        m = pattern.match(base)
        if m:
            inner = _scalar(m.group(1))
            return ("array", inner) if inner else None
    if base == "Array":
        return "array", None
    if base in ("Object", "Hash"):
        return "object", None
    return None


def _is_primitive(v) -> bool:
    return isinstance(v, (str, bool)) or (isinstance(v, (int, float)) and _finite(v))


def _finite(v) -> bool:
    return not isinstance(v, float) or math.isfinite(v)


def _fits(kind: str, v) -> bool:
    if kind == "string":
        return isinstance(v, str)
    if kind == "boolean":
        return isinstance(v, bool)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not _finite(v):
        return False
    if kind == "number":
        return True
    if kind == "int":
        # 2.0 is 2: JavaScript cannot tell them apart, so it is the one rule
        # all three faces can apply alike (§10.3).
        return (isinstance(v, int) or v.is_integer()) and _INT_MIN <= v <= _INT_MAX
    return False


def check_value(declared_class: str, value) -> str | None:
    """None when the class accepts the value, else the rejection reason, in
    the contract's order: unsupported type, null, then the type."""
    raw = declared_class.strip()
    optional = raw.endswith("?")
    shape = _shape(raw[:-1].strip() if optional else raw)
    if shape is None:
        return f"unsupported type {declared_class}"
    if value is None:
        return None if optional else f"null for non-optional {declared_class}"
    kind, element = shape
    if kind == "array":
        ok = isinstance(value, list) and all(
            _fits(element, v) if element else _is_primitive(v) for v in value)
    elif kind == "object":
        ok = isinstance(value, dict) and all(_is_primitive(v) for v in value.values())
    else:
        ok = _fits(kind, value)
    return None if ok else f"type mismatch: expected {declared_class}"


def judge(fields, values: dict) -> tuple[list, list]:
    """(applied keys, [{key, reason}]) for *values* against the declared
    *fields* [(name, class)] — what the app answers (§10.3, the coercion
    vector). Each key on its own."""
    declared = dict(fields)
    applied, rejected = [], []
    for key, value in values.items():
        if key not in declared:
            reason = "not a data field"
        else:
            reason = check_value(declared[key], value)
        if reason is None:
            applied.append(key)
        else:
            rejected.append({"key": key, "reason": reason})
    return applied, rejected


def platform_class(written, platform: str):
    """The class a platform's generator reads from a data item's `class`:
    the string, or this platform's entry of a per-platform object
    (TypeConverter.extract_platform_value). None when it gives none."""
    if isinstance(written, str):
        return written
    if not isinstance(written, dict):
        return None
    language, mode, modes = _CLASS_KEYS[platform]
    value = written.get(language)
    if isinstance(value, dict):
        for m in (mode, *modes):
            if isinstance(value.get(m), str):
                return value[m]
        return None
    return value if isinstance(value, str) else None


# ---------------------------------------------------------------- where it runs


def _platforms_of(*declared) -> list[str]:
    """The platforms a file (or a case of it) runs on: the innermost
    `platform` written, within the project's declared platforms."""
    from .step import project_platforms
    chosen = list(PLATFORMS)
    for value in declared:
        if value is None:
            continue
        if value == "all":
            chosen = list(PLATFORMS)
        elif isinstance(value, str):
            chosen = [value] if value in PLATFORMS else []
        elif isinstance(value, list):
            chosen = [p for p in PLATFORMS if p in value]
    project = project_platforms()
    if project is not None:
        declared_faces = {p for p in PLATFORMS if any(str(d).startswith(p) for d in project)}
        chosen = [p for p in chosen if p in declared_faces]
    return chosen


class _Screens:
    """The Data each screen id declares, per platform, read once per file."""

    def __init__(self, test_file_path: Path | None):
        from .screen_ids import load_screen_index
        from ..shared_core import load
        self.index = load_screen_index(test_file_path)
        self.fields_module = load("layout_data_fields")
        self._cache: dict = {}

    def why_not(self) -> str | None:
        if not self.index.available:
            return self.index.why
        if self.fields_module is None:
            return "shared/core/layout_data_fields.py is not in this tool tree"
        return None

    def fields(self, screen_id: str, platform: str):
        """([(name, class)], None), or (None, why they cannot be read)."""
        key = (screen_id, platform)
        if key not in self._cache:
            layout = self.index.layout_of(screen_id)
            if layout is None:
                self._cache[key] = (None, f"screen '{screen_id}' has no layout in this project "
                                          f"({self._whose(screen_id)})")
            else:
                try:
                    self._cache[key] = (self.fields_module.declared_data_fields(
                        layout, platform, layouts_dir=self.index.layouts_dir,
                        styles_dir=self.index.styles_dir), None)
                except (OSError, ValueError) as exc:
                    self._cache[key] = (None, f"{layout.name} could not be read ({exc})")
        return self._cache[key]

    def _whose(self, screen_id: str) -> str:
        if screen_id in self.index.collisions:
            return "several layouts share the id"
        if self.index.is_known(screen_id):
            return "declared app-owned"
        return "no layout has that basename"


def _check_values(values: dict, screen_id: str, platforms: list, screens: _Screens,
                  path: str, result: ValidationResult, unchecked: list) -> None:
    """Judge *values* for *screen_id* on each platform; one error per key and
    reason, naming the platforms it holds on."""
    findings: dict = {}
    for platform in platforms:
        fields, why = screens.fields(screen_id, platform)
        if fields is None:
            unchecked.append(why)
            continue
        resolved, unresolved = [], []
        for name, written in fields:
            cls = platform_class(written, platform)
            (resolved if cls is not None else unresolved).append((name, cls))
        _, rejected = judge(resolved, {k: v for k, v in values.items()
                                       if k not in dict(unresolved)})
        for r in rejected:
            findings.setdefault((r["key"], r["reason"]), []).append(platform)
        for name, _ in unresolved:
            if name in values:
                unchecked.append(f"'{name}' on {platform}: its data item gives this "
                                 "platform no class")
    for (key, reason), on in findings.items():
        where = "" if len(on) == len(platforms) else f" on {', '.join(on)}"
        result.errors.append(ValidationMessage(
            path=f"{path}.{key}",
            message=(f"initialState '{key}' for screen '{screen_id}': {reason}{where}. "
                     "The app rejects it and the driver fails the file's cases (setup). "
                     "Keys are the layout's Data names (top level, case-sensitive); "
                     "values fit the Data's class, null only for a class ending in '?'.")))


def _say_unchecked(unchecked: list, path: str, result: ValidationResult) -> None:
    if unchecked:
        reasons = list(dict.fromkeys(unchecked))
        result.infos.append(ValidationMessage(
            path=path, level="info",
            message="initialState values not checked against the screen's Data — "
                    + "; ".join(reasons)))


# ---------------------------------------------------------------- shape


def _object_error(value, path: str, what: str, result: ValidationResult) -> bool:
    if isinstance(value, dict):
        return False
    from .screen import _json_type_name
    result.errors.append(ValidationMessage(
        path=path, message=f"{what} must be an object, got: {_json_type_name(value)}"))
    return True


def _screen_shape(state, path: str, result: ValidationResult) -> dict | None:
    """The `viewModel` values of a screen test's (or case's) initialState,
    or None when its shape is wrong (reported) or it has none."""
    if _object_error(state, path, "'initialState'", result):
        return None
    for key in state:
        if key != "viewModel":
            result.errors.append(ValidationMessage(
                path=path, message=f"Unknown initialState key: {key} (only 'viewModel': "
                                   "Data name -> value for the screen under test)"))
    values = state.get("viewModel")
    if values is None:
        return None
    if _object_error(values, f"{path}.viewModel", "'initialState.viewModel'", result):
        return None
    return values


# ---------------------------------------------------------------- screen tests


def check_screen_test(data: dict, path: str, result: ValidationResult,
                      test_file_path: Path | None) -> None:
    """initialState on a screen test: the file's and each case's."""
    targets = []  # (path, values, platforms)
    if "initialState" in data:
        values = _screen_shape(data["initialState"], f"{path}.initialState", result)
        if values:
            targets.append((f"{path}.initialState.viewModel", values,
                            _platforms_of(data.get("platform"))))
    reopen = data.get("caseIsolation") == "reopen"
    cases = data.get("cases") if isinstance(data.get("cases"), list) else []
    for i, case in enumerate(cases):
        if not isinstance(case, dict) or "initialState" not in case:
            continue
        case_path = f"{path}.cases[{i}].initialState"
        values = _screen_shape(case["initialState"], case_path, result)
        if is_empty(case["initialState"]):
            continue
        if not reopen:
            name = case.get("name", f"#{i}")
            result.errors.append(ValidationMessage(
                path=case_path, kind=CODE_CASE_NEEDS_REOPEN,
                message=(f"case '{name}' has its own initialState, but the file's caseIsolation "
                         f"is {data.get('caseIsolation', 'shared (the default)')!s} — the screen "
                         "opens once, before the first case, so it cannot be delivered and the "
                         "driver fails this case (setup). Set \"caseIsolation\": \"reopen\", or "
                         f"move the values to the file's initialState ({CODE_CASE_NEEDS_REOPEN})")))
        if values:
            targets.append((f"{case_path}.viewModel", values,
                            _platforms_of(data.get("platform"), case.get("platform"))))
    if not targets:
        return
    screen_id = _screen_under_test(data)
    if screen_id is None:
        return  # no source.layout: the source check's error
    screens = _Screens(test_file_path)
    why = screens.why_not()
    if why:
        _say_unchecked([why], f"{path}.initialState", result)
        return
    unchecked: list = []
    for target_path, values, platforms in targets:
        _check_values(values, screen_id, platforms, screens, target_path, result, unchecked)
    _say_unchecked(unchecked, f"{path}.initialState", result)


def _screen_under_test(data: dict) -> str | None:
    """The screen id of `source.layout` (spec §10.1), by the canon's own
    implementation; None when there is no layout or no canon."""
    source = data.get("source")
    layout = source.get("layout") if isinstance(source, dict) else None
    if not isinstance(layout, str) or not layout.strip():
        return None
    return screen_id_for_layout(layout.strip())


def screen_id_for_layout(layout: str) -> str | None:
    from .screen_ids import _prefer_sibling_jui_cli
    _prefer_sibling_jui_cli()
    try:
        from jui_cli.core.screen_identity import screen_id_for_path
    except ImportError:
        return None
    return screen_id_for_path(layout)


# ---------------------------------------------------------------- flow tests


def check_flow_test(data: dict, path: str, result: ValidationResult,
                    test_file_path: Path | None) -> None:
    """initialState on a flow test: `viewModels` by screen id."""
    if "initialState" not in data:
        return
    state = data["initialState"]
    state_path = f"{path}.initialState"
    if _object_error(state, state_path, "'initialState'", result):
        return
    for key in state:
        if key == "screen":
            result.errors.append(ValidationMessage(
                path=f"{state_path}.screen", kind=CODE_FLOW_SCREEN_REMOVED,
                message=("initialState.screen is removed: a flow starts where the app starts, "
                         "and its values go to screens by id in initialState.viewModels. "
                         f"Delete the key ({CODE_FLOW_SCREEN_REMOVED})")))
        elif key != "viewModels":
            result.errors.append(ValidationMessage(
                path=state_path, message=f"Unknown initialState key: {key} (only 'viewModels': "
                                         "screen id -> (Data name -> value))"))
    models = state.get("viewModels")
    if models is None:
        return
    if _object_error(models, f"{state_path}.viewModels", "'initialState.viewModels'", result):
        return
    from .screen_ids import check_screen_value
    screens = _Screens(test_file_path)
    why = screens.why_not()
    platforms = _platforms_of(data.get("platform"))
    unchecked: list = []
    for screen_id, values in models.items():
        entry_path = f"{state_path}.viewModels.{screen_id}"
        if _object_error(values, entry_path, f"initialState.viewModels['{screen_id}']", result):
            continue
        message = check_screen_value(screen_id, screens.index)
        if message:
            result.errors.append(ValidationMessage(
                path=entry_path,
                message=f"initialState.viewModels keys are screen ids, as the steps' "
                        f"'screen' — {message}"))
            continue
        if values and why is None:
            _check_values(values, screen_id, platforms, screens, entry_path, result, unchecked)
    if why and any(models.values()):
        unchecked.append(why)
    _say_unchecked(unchecked, state_path, result)


def check_referenced_file(step: dict, referenced: dict, path: str,
                          result: ValidationResult) -> None:
    """A flow's file step whose file, or one of the cases it runs, has an
    initialState: not applied inside the flow (spec §10.2) — a warning."""
    if not isinstance(referenced, dict):
        return
    file_ref = step.get("file")
    hint = ("not applied inside a flow — the flow's one launch has already happened. Put the "
            "values in the flow's initialState.viewModels under the screen id, or drop them "
            f"({CODE_REFERENCED_IGNORED})")
    if "initialState" in referenced and not is_empty(referenced["initialState"]):
        result.warnings.append(ValidationMessage(
            path=path, level="warning", kind=CODE_REFERENCED_IGNORED,
            message=f"referenced file '{file_ref}' has an initialState: {hint}"))
    cases = referenced.get("cases") if isinstance(referenced.get("cases"), list) else []
    if isinstance(step.get("case"), str):
        wanted = {step["case"]}
    elif isinstance(step.get("cases"), list):
        wanted = {c for c in step["cases"] if isinstance(c, str)}
    else:
        wanted = None
    for case in cases:
        if not isinstance(case, dict) or "initialState" not in case:
            continue
        if wanted is not None and case.get("name") not in wanted:
            continue
        if is_empty(case["initialState"]):
            continue
        result.warnings.append(ValidationMessage(
            path=path, level="warning", kind=CODE_REFERENCED_IGNORED,
            message=f"case '{case.get('name')}' of referenced file '{file_ref}' has an "
                    f"initialState: {hint}"))
