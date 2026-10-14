"""The repo files the conformance checks read from beside ``conformance/``,
and the one line that says what a gate or a bake was handed.

Three readers resolve ``shared/core`` as a SIBLING of the conformance dir
(``cross_effect.contract_path``, ``report.generate_report``'s enum values,
``os_dependence.os_dependent_screenshots_for``), and each one reads a missing
file as empty, silently. Run from the repo root that is always there. Run on
a copy (``--dir`` somewhere else) it is not, and the gate's verdict changes
with no message: measured on run 38620808116, the same artifacts gave 21
unrecorded / 25 stale cross-effect findings from the repo and 16 / 55 from a
copy, and a bake from a copy would leave the availability-gated pictures in
the OS-agnostic table instead of carving them under ``hashes_by_os``.

An absent file here is never "not adopted": it is a check that went on
running with less. So a check that needs one names it and stops
(:func:`missing_for`), and every gate and bake prints what it read
(:func:`input_digest`) so two runs can be shown to have had the same inputs.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

SEMANTICS = "attribute_semantics.json"
DEFINITIONS = "attribute_definitions.json"

#: What each sibling file feeds, in the words a failure names it by.
FEEDS = {
    SEMANTICS: "the cross-effect semantics contract",
    DEFINITIONS: (
        "the uniformly-inert cross-effect check and the os-dependent "
        "baseline carve-out (hashes_by_os)"
    ),
}


def sibling(conformance_dir, name: str) -> Path:
    """``<conformance_dir>/../shared/core/<name>`` — where the readers look."""
    return Path(conformance_dir).parent / "shared" / "core" / name


def missing_for(conformance_dir, names, *, asked: str) -> list[str]:
    """A problem per *names* file absent beside *conformance_dir*.

    *asked* names what the run was asked to do (``--cross-effect``, ``a
    bake``) so the message says which request cannot be answered.
    """
    problems = []
    for name in names:
        path = sibling(conformance_dir, name)
        if not path.is_file():
            problems.append(
                f"{asked} reads {path} and it is not there — without it "
                f"{FEEDS[name]} would run on nothing and change the verdict "
                "without saying so. Run from the repo root, or put shared/core "
                "beside the --dir you pass."
            )
    return problems


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree_digest(root: Path) -> tuple[int, str]:
    """(file count, digest of sorted ``relpath\\0md5`` lines) under *root*."""
    if not root.is_dir():
        return 0, "-"
    lines = sorted(
        f"{p.relative_to(root).as_posix()}\0{_md5(p)}"
        for p in root.rglob("*")
        if p.is_file()
    )
    return len(lines), hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]


def _file(path: Path) -> str:
    return _md5(path)[:12] if path.is_file() else "MISSING"


def input_digest(
    conformance_dir,
    *,
    results_dir=None,
    platforms=None,
    artifacts_dir=None,
) -> str:
    """One line naming every input a gate or bake reads, with a digest each.

    *platforms* narrows results / codegen / artifacts to those faces (a bake
    reads one); None means every file present. Two runs that print the same
    line were handed the same inputs; a difference names the one that moved.
    """
    conformance_dir = Path(conformance_dir)
    results_dir = Path(results_dir) if results_dir else conformance_dir / "results"

    def _results(folder: Path) -> str:
        if not folder.is_dir():
            return "-"
        files = sorted(
            p for p in folder.glob("*.results.json")
            if platforms is None or p.name.split(".", 1)[0] in platforms
        )
        return ",".join(f"{p.name.split('.', 1)[0]}:{_md5(p)[:12]}" for p in files) or "-"

    if artifacts_dir is not None:
        art_root = Path(artifacts_dir)
    else:
        art_root = conformance_dir / "artifacts"
    if platforms is None or artifacts_dir is not None:
        count, digest = _tree_digest(art_root)
    else:
        count, parts = 0, []
        for face in sorted(platforms):
            n, d = _tree_digest(art_root / face)
            count += n
            parts.append(f"{face}={d}")
        digest = "+".join(parts)

    return (
        f"conformance inputs: dir={conformance_dir.resolve()}"
        f" manifest={_file(conformance_dir / 'manifest.json')}"
        f" results=[{_results(results_dir)}]"
        f" codegen=[{_results(conformance_dir / 'codegen')}]"
        f" artifacts={count} files {digest}"
        f" semantics={sibling(conformance_dir, SEMANTICS)} {_file(sibling(conformance_dir, SEMANTICS))}"
        f" definitions={sibling(conformance_dir, DEFINITIONS)} {_file(sibling(conformance_dir, DEFINITIONS))}"
    )
