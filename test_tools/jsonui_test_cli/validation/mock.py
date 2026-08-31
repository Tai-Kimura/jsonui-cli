"""Validation for *.mock.json definition files.

Handwritten (mirrors screen.py / flow.py); the CLI does not depend on jsonschema.
schemas/mock.schema.json is an editor/doc asset, not the validation mechanism.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import ValidationMessage, ValidationResult

VALID_MOCK_KEYS = ["$schema", "source", "activeScenario", "scenarios"]
VALID_SOURCE_KEYS = ["swagger", "operationId", "method", "path"]
VALID_SCENARIO_KEYS = ["status", "headers", "body", "delayMs", "contentType",
                       "bodyFile", "contractViolations"]
VALID_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


_MOCK_INDEX_CACHE: dict = {}

#: id(index) -> the directory that supplied it, for error messages.
_INDEX_SOURCE: dict = {}


@dataclass(frozen=True)
class MockSource:
    """Where this run's mocks are, and how that was decided.

    One value, resolved once, instead of two independent answers to the same
    question — a declaration read by the CLI and a walk performed by the
    validators, with the walk's bound an optional argument each caller could
    forget. Six releases went into that argument's meaning (arrival vs
    containment) and into how many places the walk should start; the hole was
    the optionality, so it is gone. Every caller now gets the same bound
    because there is nowhere to not pass it.

    `boundary` is the project root. Without it the walk runs to the filesystem
    root: on a machine where every project sits under one directory, a single
    stray `mocks/` there answers for every project below it — including the
    ones with no mocks at all.
    """

    directory: Path | None = None
    provenance: str = "none"      # "declared" | "discovered" | "none"
    boundary: Path | None = None


#: This run's resolved source. Set by the CLI before validation.
_MOCK_SOURCE = MockSource()


def set_mock_source(directory=None, boundary=None) -> None:
    """Record what this run's config says, before any file is validated.

    A declaration outranks a search: the project said where its mocks are,
    and a directory found by convention is a guess about the same question.
    Measured before this existed — one stray `*.mock.json` in an ancestor
    directory replaced the entire operationId index, and every mock reference
    in every test became "unknown mock operationId". A consumer with a correct,
    declared mockDir and 151 real mocks got 357 errors from one decoy file,
    with no way to switch it off: the reference check is not the drift gate,
    so `--no-mock-check` does not reach it.

    The boundary is recorded even when nothing is declared, which is the case
    the first version of this missed. Declaring nothing is not a reason to
    search outside your own project.
    """
    global _MOCK_SOURCE
    _MOCK_SOURCE = MockSource(
        directory=Path(directory).resolve() if directory is not None else None,
        provenance="declared" if directory is not None else "none",
        boundary=Path(boundary).resolve() if boundary is not None else None,
    )
    # A new run means the mocks on disk may have changed (validate rebuilds
    # a stale generated/ before this is called) — a cache surviving the
    # source it was read from would validate against the previous tree.
    _MOCK_INDEX_CACHE.clear()
    _GENERATED_ROUTES_CACHE.clear()


def _enclosing_project(start: Path):
    """The project a path sits in — nearest `jui.config.json`, else `.git`.

    The bound the CLI computes is better (it is the config `validate` actually
    loaded, so "this project" means the same directory the gate means), but a
    caller that never set a source used to get no bound at all, and no bound
    means the filesystem root. Deriving one here costs a caller nothing and
    leaves nowhere to forget it — which is the whole defect this file has been
    working through: the bound was an optional argument, so the walk was
    bounded exactly where someone remembered to bound it.

    A boundary definition, not a second rule for where mocks live.
    """
    for parent in [start, *start.parents]:
        if (parent / "jui.config.json").exists():
            return parent
    for parent in [start, *start.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def find_mock_dir(test_file_path):
    """Locate the mock directory for a test file, or None.

    A declared mockDir wins outright. Otherwise the convention: walk up from
    the test file for a `jui.config.json` naming one, else a `tests/mocks` or
    `mocks` directory — confined to the project.

    Confinement, not a stop marker. An earlier version broke when it reached
    the boundary directory, which silently did nothing whenever the boundary
    was not on the walk's path — and a project whose tests live in a
    different tree from its config is exactly that case. Measured: tests in a
    sibling tree, boundary never matched, the walk ran to the filesystem root
    and reported nine mock files belonging to no project at all. The bound
    has to be asked about every directory, not waited for.
    """
    if test_file_path is None:
        return None
    if _MOCK_SOURCE.directory is not None and _MOCK_SOURCE.directory.is_dir():
        return _MOCK_SOURCE.directory
    start = Path(test_file_path).resolve().parent
    # A set boundary is authoritative, including when it does not contain
    # `start`: that is the split-tree layout, where the walk from a test file
    # legitimately reaches nothing and the second start point at the project
    # root is what finds the mocks. Falling back to an intrinsic bound there
    # would turn "out of bounds" back into "unbounded" — measured, it
    # reintroduced the nine-foreign-mocks report v1.6.53 removed.
    boundary = _MOCK_SOURCE.boundary
    if boundary is None:
        boundary = _enclosing_project(start)
    if boundary is not None and boundary != start and boundary not in start.parents:
        # The walk would start outside the subtree it is confined to, so
        # every directory it could reach is out of bounds.
        return None
    mock_dir = None
    for parent in [start, *start.parents]:
        config = parent / "jui.config.json"
        if config.exists():
            try:
                with open(config, "r", encoding="utf-8") as f:
                    rel = (json.load(f).get("mock", {}) or {}).get("mockDir")
                if rel:
                    cand = (parent / rel)
                    if cand.exists():
                        mock_dir = cand
                        break
            except (OSError, json.JSONDecodeError):
                pass
        for name in ("tests/mocks", "mocks"):
            cand = parent / name
            if cand.is_dir():
                mock_dir = cand
                break
        if mock_dir:
            break
        # Inclusive: the boundary directory is searched, its parent is not.
        if boundary is not None and parent == boundary:
            break
    if mock_dir is not None and boundary is not None:
        resolved = mock_dir.resolve()
        if resolved != boundary and boundary not in resolved.parents:
            return None
    return mock_dir


#: `str(mock_dir)` -> `{route_key: set(scenario names)}` for generated/.
_GENERATED_ROUTES_CACHE: dict = {}


def _enclosing_mock_root(mock_file: Path):
    """The mock tree *mock_file* itself sits in, or None.

    Nearest ancestor that holds a `generated/` directory — the tool writes
    that tree, so its presence is what makes a directory a mock root, and
    a file with no such ancestor has no counterpart to overlay by
    definition. Used only when the run's declared mockDir does not contain
    the file; the declaration keeps answering discovery.
    """
    from ..mock.generate import GENERATED_DIR

    for parent in mock_file.parents:
        if (parent / GENERATED_DIR).is_dir():
            return parent
    return None


def _generated_scenarios_by_route(mock_dir) -> dict:
    """``route_key -> scenario-name set`` for ``<mockDir>/generated/**``.

    What the serve-side overlay merges under a hand-written file: the
    validator judges a thin overlay against the same union the server
    builds, instead of against the file alone.
    """
    from ..mock.generate import GENERATED_DIR, read_route

    key = str(Path(mock_dir).resolve())
    if key in _GENERATED_ROUTES_CACHE:
        return _GENERATED_ROUTES_CACHE[key]
    index: dict = {}
    gen_root = Path(mock_dir) / GENERATED_DIR
    if gen_root.is_dir():
        for f in gen_root.rglob("*.mock.json"):
            rk = read_route(f)
            if rk is None:
                continue
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            index[rk] = set((data.get("scenarios") or {}).keys())
    _GENERATED_ROUTES_CACHE[key] = index
    return index


def find_mock_index(test_file_path):
    """`{operationId: {scenarios}}` for the mocks of a test file, or None.

    The directory is located by `find_mock_dir` — one walk, exposed at two
    granularities, so a caller that needs the location does not grow a second
    convention for where mocks live.
    """
    mock_dir = find_mock_dir(test_file_path)
    if mock_dir is None:
        return None

    key = str(mock_dir.resolve())
    if key in _MOCK_INDEX_CACHE:
        cached = _MOCK_INDEX_CACHE[key]
        _INDEX_SOURCE[id(cached)] = key
        return cached

    index: dict[str, set] = {}
    for f in mock_dir.rglob("*.mock.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        op_id = (data.get("source", {}) or {}).get("operationId") or f.stem.replace(".mock", "")
        # UNION per operation — the view serve actually serves. A route can
        # legitimately have two files (generated counterpart + hand-written
        # overlay), and a test's scenario reference is valid iff the union
        # answers it. This used to assign (last-wins over an UNSORTED walk),
        # so once the overlay model guaranteed the counterpart exists, the
        # generated copy could shadow the very scenarios the tests drive —
        # 24 reference errors on the reporting consumer, every one naming
        # the generated side's set as "available".
        index.setdefault(op_id, set()).update(
            (data.get("scenarios", {}) or {}).keys())
    _MOCK_INDEX_CACHE[key] = index
    _INDEX_SOURCE[id(index)] = key
    return index


def validate_mock_reference(mapping, path: str, result: ValidationResult, index):
    """Validate a {operationId: scenario} map (root `mocks` or a setMocks step)."""
    if not isinstance(mapping, dict):
        result.errors.append(ValidationMessage(
            path=path, message=f"'mocks' must be an object of operationId -> scenario, got: {type(mapping).__name__}"))
        return
    for op_id, scenario in mapping.items():
        if not isinstance(scenario, str):
            result.errors.append(ValidationMessage(
                path=f"{path}.{op_id}", message=f"scenario name must be a string, got: {type(scenario).__name__}"))
            continue
        if index is None:
            continue  # no mock dir discoverable; skip existence check
        if op_id not in index:
            # The resolved directory, not the literal "tests/mocks": which
            # directory answered is the whole question when the answer is
            # wrong, and a reporting lane needed four A/B runs to find out
            # that a stray file two levels up had supplied the index.
            # With how it was chosen, too: a wrong `mockDir` and a wrong guess
            # print the same path, and they are not the same thing to fix.
            where = _INDEX_SOURCE.get(id(index), "the mock directory")
            # Derived from the directory that answered, not from the run's
            # declaration: a run may declare a mockDir that does not resolve
            # and still be answered by the convention, and then saying
            # "declared" would name the wrong thing to go and fix.
            declared = _MOCK_SOURCE.directory
            how = ""
            if declared is not None and where == str(declared):
                how = " declared by mock.mockDir"
            elif where != "the mock directory":
                how = " found by convention"
            result.errors.append(ValidationMessage(
                path=f"{path}.{op_id}",
                message=f"unknown mock operationId '{op_id}' "
                        f"(not in {where}{how})"))
        elif scenario not in index[op_id]:
            result.errors.append(ValidationMessage(
                path=f"{path}.{op_id}",
                message=f"mock '{op_id}' has no scenario '{scenario}' (available: {sorted(index[op_id])})"))


class MockValidator:
    """Validates a single mock definition file."""

    def _check_schema_ref(self, data, path: str, result: ValidationResult):
        """The `$schema` reference must be the sibling spelling, or absent.

        `mock generate` places a copy of the schema in every directory that
        holds mocks, so the reference is a sibling everywhere. A `../` form
        points at a directory that never receives one — it resolves to
        nothing and the editor silently stops checking the file, which is
        indistinguishable from a file with no problems.

        Only the spelling is checked, never whether the file is there: a
        project is free to gitignore the placed copies, and a fresh CI
        checkout would then fail on every mock it has. The spelling is the
        tool's own convention, so it is decidable without the file and
        reaches zero regardless of that choice.
        """
        if "$schema" not in data:
            return  # generated mocks carry one; omitting it by hand is fine
        from ..mock.generate import EDITOR_SCHEMA_REF
        found = data["$schema"]
        if found == EDITOR_SCHEMA_REF:
            return
        result.errors.append(ValidationMessage(
            path=f"{path}.$schema",
            message=(f"'$schema' must be '{EDITOR_SCHEMA_REF}', got: {found!r}. "
                     "The schema is placed in every directory that holds mocks, "
                     "so the reference is always a sibling; another spelling "
                     "resolves to nothing and the editor stops checking this "
                     "file without saying so.")))

    def validate(self, data, path: str, result: ValidationResult):
        if not isinstance(data, dict):
            result.errors.append(ValidationMessage(path=path, message="Mock file must be a JSON object"))
            return

        for key in data:
            if key not in VALID_MOCK_KEYS:
                result.warnings.append(ValidationMessage(
                    path=path, message=f"Unknown mock key: {key}", level="warning"))

        self._check_schema_ref(data, path, result)

        source = data.get("source")
        if not isinstance(source, dict):
            result.errors.append(ValidationMessage(path=f"{path}.source", message="'source' is required and must be an object"))
        else:
            for key in source:
                if key not in VALID_SOURCE_KEYS:
                    result.warnings.append(ValidationMessage(
                        path=f"{path}.source", message=f"Unknown source key: {key}", level="warning"))
            method = source.get("method")
            if method and method.upper() not in VALID_METHODS:
                result.errors.append(ValidationMessage(
                    path=f"{path}.source.method", message=f"Invalid method: {method}"))
            if not source.get("path"):
                result.errors.append(ValidationMessage(
                    path=f"{path}.source.path", message="'source.path' is required for routing"))

        scenarios = data.get("scenarios")
        if not isinstance(scenarios, dict) or not scenarios:
            result.errors.append(ValidationMessage(
                path=f"{path}.scenarios", message="'scenarios' is required and must be a non-empty object"))
            return

        for name, scenario in scenarios.items():
            spath = f"{path}.scenarios.{name}"
            if not isinstance(scenario, dict):
                result.errors.append(ValidationMessage(path=spath, message="scenario must be an object"))
                continue
            for key in scenario:
                if key not in VALID_SCENARIO_KEYS:
                    result.warnings.append(ValidationMessage(
                        path=spath, message=f"Unknown scenario key: {key}", level="warning"))
            status = scenario.get("status")
            if not isinstance(status, int) or not (100 <= status <= 599):
                result.errors.append(ValidationMessage(
                    path=f"{spath}.status", message=f"'status' must be an HTTP status int, got: {status!r}"))
            if "delayMs" in scenario and not isinstance(scenario["delayMs"], (int, float)):
                result.errors.append(ValidationMessage(
                    path=f"{spath}.delayMs", message="'delayMs' must be a number"))

        # A hand-written mock with a generated counterpart is a thin overlay
        # (the serve model: generated supplies the routine scenarios, the
        # hand-written file carries only what its tests drive, and an OMITTED
        # activeScenario inherits the generated side's). Judging such a file
        # alone rejected the exact shape the server documents — so the
        # membership check runs against the same merged view serve builds.
        # A file with no counterpart is the whole route and is judged alone,
        # exactly as before.
        counterpart = self._generated_counterpart(path, source)
        active = data.get("activeScenario")
        if counterpart is None:
            effective = active if active is not None else "default"
            if effective not in scenarios:
                result.errors.append(ValidationMessage(
                    path=f"{path}.activeScenario",
                    message=f"activeScenario '{effective}' is not among "
                            f"scenarios: {list(scenarios.keys())}"))
        elif active is not None and active not in (set(scenarios) | counterpart):
            result.errors.append(ValidationMessage(
                path=f"{path}.activeScenario",
                message=(
                    f"activeScenario '{active}' is not among this file's "
                    f"scenarios {sorted(scenarios)} or the generated "
                    f"mock's {sorted(counterpart)} it overlays")))

    @staticmethod
    def _generated_counterpart(path: str, source) -> set | None:
        """Scenario names of the generated mock this file overlays, or None.

        None for a generated file itself and for a route generated/ does
        not serve.

        The tree is anchored to THIS FILE, not to the run's declared
        mockDir. Those answer different questions: discovery ("where are
        this project's mocks") is the declaration's, and it stays
        authoritative there — but "what does this file overlay" is about
        one file, and a file outside the declared tree still has the
        sibling `generated/` of its own tree. Asking the declared dir
        about it found nothing and judged the overlay alone, which is the
        very error 1.7.22 removed, reappearing whenever validate is aimed
        at mocks outside the resolved config's mockDir (a monorepo
        sub-project validated while an ancestor config answers, measured).
        """
        from ..mock.generate import GENERATED_DIR, route_key

        if not isinstance(source, dict) or not source.get("path"):
            return None
        file_on_disk = Path(path)
        if not file_on_disk.exists():
            return None
        here = file_on_disk.resolve()
        mock_dir = find_mock_dir(file_on_disk)
        if mock_dir is None or Path(mock_dir).resolve() not in here.parents:
            mock_dir = _enclosing_mock_root(here)
        if mock_dir is None:
            return None
        rel_parts = here.relative_to(Path(mock_dir).resolve()).parts
        if GENERATED_DIR in rel_parts:
            return None
        rk = route_key((source.get("method") or "GET"), source["path"])
        return _generated_scenarios_by_route(mock_dir).get(rk)
