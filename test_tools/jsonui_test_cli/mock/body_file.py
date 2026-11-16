"""A scenario's `bodyFile` (ticket 2026-10-25-jsonui-test-mock-bodyfile-is-never-read).

`"bodyFile": "files/export.default.csv"` on a scenario is the response body: the file's bytes, read relative to
the mock file that declares the scenario, sent with the scenario's `contentType` — by `mock serve` and by the
three runtimes `generate branch-tests` writes. One rule here, read by the validator, the server and the
branch-test emitter, so the body one of them sends is the body each of them sends.

- `body` and `bodyFile` on one scenario: `body` is what is sent (it always was); the validator names the pair.
- The branch-test runtimes embed the body in generated source, so a file there is read as UTF-8 text (a BOM is
  kept: it is part of the bytes a CSV export sends). A file that is not UTF-8 is served by `mock serve` and
  refused by `generate branch-tests` by name.
"""

from __future__ import annotations

from pathlib import Path


def declares_body_file(scenario) -> bool:
    """A scenario whose body is a file: `bodyFile` set and no inline `body`."""
    return (isinstance(scenario, dict) and scenario.get("body") is None
            and isinstance(scenario.get("bodyFile"), str) and bool(scenario["bodyFile"].strip()))


def body_file_path(mock_file: Path, scenario) -> Path | None:
    """Where a scenario's `bodyFile` is: relative to the mock file that declares it. None without one."""
    if not declares_body_file(scenario):
        return None
    return (Path(mock_file).parent / scenario["bodyFile"]).resolve()


def body_file_problems(mock_file: Path, scenario) -> list[str]:
    """Why a scenario's `bodyFile` is not served (empty: it is, or there is none)."""
    if not isinstance(scenario, dict) or scenario.get("bodyFile") is None:
        return []
    value = scenario["bodyFile"]
    if not isinstance(value, str) or not value.strip():
        return [f"'bodyFile' must be a path to a file, relative to this mock file, got {value!r}"]
    if Path(value).is_absolute():
        return [f"'bodyFile' must be relative to this mock file, got the absolute path {value!r}"]
    if scenario.get("body") is not None:
        return ["'body' and 'bodyFile' are both set — 'body' is what is sent; remove one"]
    path = body_file_path(mock_file, scenario)
    if not path.is_file():
        return [f"'bodyFile' {value!r} is not a file (looked for {path})"]
    return []


def read_body_file(mock_file: Path, scenario) -> bytes | None:
    """The scenario's body from its `bodyFile`, as bytes; None without one or when it cannot be read."""
    path = body_file_path(mock_file, scenario)
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def read_body_file_text(mock_file: Path, scenario) -> tuple[str | None, str | None]:
    """`(text, problem)`: the `bodyFile` as UTF-8 text for a generated runtime, or why it cannot be one."""
    path = body_file_path(mock_file, scenario)
    if path is None:
        return None, None
    try:
        data = path.read_bytes()
    except OSError as e:
        return None, f"'bodyFile' {scenario['bodyFile']!r} cannot be read ({path}): {e.strerror or e}"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, (f"'bodyFile' {scenario['bodyFile']!r} is not UTF-8 text — the generated branch tests "
                      "embed the body in source; `mock serve` sends it as is")
