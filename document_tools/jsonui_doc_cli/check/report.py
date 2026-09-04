"""Check-result artifact contract (doc-contract-check plan 01 §5 + review §3-2).

This is the output contract for builtin checkers AND full-checker plugins.
Invalid plugin output is an execution error (exit 2), not a mismatch.

Reports are written to:
    docs/api/.check-report.json                 (kind=api)
    docs/db/.check-report.json                  (kind=db, default database)
    docs/db/{db_name}/.check-report.json        (kind=db, named database)

Reports are local artifacts by default (NOT committed — executed_at churns).
`generate html` renders them if present; absence must never fail generation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from ..reproducible import build_local_datetime

SCHEMA_VERSION = 1

# `warning` is a mismatch the project declared as non-gating
# (CheckDecl.downgrade_to_warning): the finding keeps its expected/actual
# detail and stays visible in reports, but never sets the exit code — the
# same standing the free-text `warnings` list already had, with structure.
STATUSES = {"ok", "mismatch", "missing_in_impl", "missing_in_doc", "skipped",
            "warning"}
CONFIDENCES = {"proof", "metadata", "sampled"}
TARGET_KINDS = {"db", "api", "custom"}

REPORT_BASENAME = ".check-report.json"


class ReportValidationError(Exception):
    """The result JSON does not satisfy the contract."""


@dataclass
class ResultItem:
    target: str
    status: str
    confidence: str
    expected: str | None = None
    actual: str | None = None
    message: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "target": self.target,
            "status": self.status,
            "confidence": self.confidence,
        }
        if self.expected is not None:
            d["expected"] = self.expected
        if self.actual is not None:
            d["actual"] = self.actual
        if self.message is not None:
            d["message"] = self.message
        return d


@dataclass
class CheckReport:
    checker: str
    target_kind: str            # db | api | custom
    target_name: str            # db name / "api" / checker-defined
    target_extra: dict = field(default_factory=dict)   # e.g. {"dialect": "mysql"}
    executed_at: str = ""
    input_hashes: dict[str, str] = field(default_factory=dict)
    results: list[ResultItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: What this checker counts — "operation", "table". A count with no unit
    #: cannot be read from the output: a consumer lane had to infer it from
    #: the shape of `target` strings, which made its gate depend on this
    #: report's internal spelling.
    unit: str = ""
    #: Units on the declaring side before any exclusion, and units actually
    #: examined. `None` means the checker did not report one — never fill
    #: either in with a guess, because the whole point is telling
    #: "compared 136 of 136" apart from "compared 136 of 236".
    declared: int | None = None
    compared: int | None = None
    #: Units configuration deliberately left out.
    excluded: int = 0
    #: Provenance of the two sides. Metadata only: never compared, never
    #: consulted for staleness (`is_stale` stays one-directional by design).
    inputs: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.executed_at:
            self.executed_at = build_local_datetime().isoformat(timespec="seconds")

    @property
    def summary(self) -> dict:
        counts: dict = {s: 0 for s in
                        ("ok", "mismatch", "missing_in_impl", "missing_in_doc",
                         "skipped", "warning")}
        for r in self.results:
            counts[r.status] += 1
        if self.unit:
            counts["unit"] = self.unit
        if self.declared is not None:
            counts["declared"] = self.declared
        if self.compared is not None:
            counts["compared"] = self.compared
        if self.excluded:
            counts["excluded"] = self.excluded
        residual = self.coverage_residual
        if residual:
            # Shown, not rounded away. The arithmetic failing to close means
            # this report cannot account for some of what it declared, and a
            # denominator nobody can reconcile is worse than none — it looks
            # authoritative.
            counts["unaccounted"] = residual
        return counts

    @property
    def coverage_residual(self) -> int:
        """`declared - compared - excluded`; 0 when the arithmetic closes."""
        if self.declared is None or self.compared is None:
            return 0
        return self.declared - self.compared - self.excluded

    @property
    def compared_nothing(self) -> bool:
        """Declared units exist and not one of them was examined.

        The endpoint of partial coverage, and the case that reads exactly
        like a clean pass: every count is zero because nothing happened.
        """
        return bool(self.declared) and self.compared == 0

    @property
    def has_mismatch(self) -> bool:
        s = self.summary
        return (s["mismatch"] + s["missing_in_impl"] + s["missing_in_doc"]) > 0

    def to_dict(self) -> dict:
        d = {
            "schemaVersion": SCHEMA_VERSION,
            "checker": self.checker,
            "executed_at": self.executed_at,
            "target": {"kind": self.target_kind, "name": self.target_name,
                       **self.target_extra},
            "input_hashes": dict(self.input_hashes),
            "results": [r.to_dict() for r in self.results],
            "warnings": list(self.warnings),
            "summary": self.summary,
        }
        if self.inputs:
            d["inputs"] = dict(self.inputs)
        return d


def validate_report_dict(data: dict, source: str = "report") -> list[str]:
    """Return a list of contract violations (empty = valid).

    Used both for our own output (self-check) and for full-checker plugin
    stdout (where violations mean exit 2)."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return [f"{source}: top level must be an object"]
    if data.get("schemaVersion") != SCHEMA_VERSION:
        problems.append(
            f"{source}: schemaVersion must be {SCHEMA_VERSION} "
            f"(got {data.get('schemaVersion')!r})"
        )
    if not isinstance(data.get("checker"), str) or not data.get("checker"):
        problems.append(f"{source}: 'checker' must be a non-empty string")
    target = data.get("target")
    if not isinstance(target, dict):
        problems.append(f"{source}: 'target' must be an object")
    else:
        if target.get("kind") not in TARGET_KINDS:
            problems.append(
                f"{source}: target.kind must be one of {sorted(TARGET_KINDS)}"
            )
        if not isinstance(target.get("name"), str):
            problems.append(f"{source}: target.name must be a string")
    results = data.get("results")
    if not isinstance(results, list):
        problems.append(f"{source}: 'results' must be an array")
    else:
        for i, r in enumerate(results):
            ctx = f"{source}: results[{i}]"
            if not isinstance(r, dict):
                problems.append(f"{ctx} must be an object")
                continue
            if not isinstance(r.get("target"), str):
                problems.append(f"{ctx}.target must be a string")
            if r.get("status") not in STATUSES:
                problems.append(f"{ctx}.status must be one of {sorted(STATUSES)}")
            if r.get("confidence") not in CONFIDENCES:
                problems.append(
                    f"{ctx}.confidence must be one of {sorted(CONFIDENCES)}"
                )
    hashes = data.get("input_hashes", {})
    if not isinstance(hashes, dict):
        problems.append(f"{source}: 'input_hashes' must be an object")
    return problems


def report_from_dict(data: dict, source: str = "report") -> CheckReport:
    problems = validate_report_dict(data, source)
    if problems:
        raise ReportValidationError("; ".join(problems))
    target = data["target"]
    extra = {k: v for k, v in target.items() if k not in ("kind", "name")}
    return CheckReport(
        checker=data["checker"],
        target_kind=target["kind"],
        target_name=target["name"],
        target_extra=extra,
        executed_at=data.get("executed_at", ""),
        input_hashes=dict(data.get("input_hashes", {})),
        results=[
            ResultItem(
                target=r["target"],
                status=r["status"],
                confidence=r["confidence"],
                expected=r.get("expected"),
                actual=r.get("actual"),
                message=r.get("message"),
            )
            for r in data["results"]
        ],
        warnings=list(data.get("warnings", [])),
        # Coverage lives in `summary` on the wire (that is where a reader
        # looks) but as fields here. Absent in a plugin's output means the
        # plugin does not report coverage, which stays distinguishable from
        # reporting zero.
        unit=_coverage_str(data, "unit"),
        declared=_coverage_int(data, "declared"),
        compared=_coverage_int(data, "compared"),
        excluded=_coverage_int(data, "excluded") or 0,
        inputs=dict(data.get("inputs") or {}),
    )


def _coverage_int(data: dict, key: str) -> int | None:
    value = (data.get("summary") or {}).get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _coverage_str(data: dict, key: str) -> str:
    value = (data.get("summary") or {}).get(key)
    return value if isinstance(value, str) else ""


# --------------------------------------------------------------------- #
# Hashes / staleness
# --------------------------------------------------------------------- #

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def compute_input_hashes(paths: list[Path], project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for p in sorted(paths):
        try:
            rel = str(p.resolve().relative_to(project_root.resolve()))
        except ValueError:
            rel = str(p)
        hashes[rel] = sha256_of(p)
    return hashes


def is_stale(report: CheckReport, project_root: Path) -> bool:
    """True if any hashed doc input changed (or vanished) since the check ran.

    NOTE: one-directional by design — changes on the IMPLEMENTATION side
    (real DB / real API) are undetectable here. Renderers must display
    executed_at prominently and say so (review §3-5).
    """
    for rel, expected in report.input_hashes.items():
        p = project_root / rel
        if not p.is_file():
            return True
        if sha256_of(p) != expected:
            return True
    return False


# --------------------------------------------------------------------- #
# Location / IO
# --------------------------------------------------------------------- #

def report_path_for(target_kind: str, target_name: str, project_root: Path) -> Path:
    if target_kind == "api":
        return project_root / "docs" / "api" / REPORT_BASENAME
    if target_kind == "db":
        base = project_root / "docs" / "db"
        if target_name and target_name != "default":
            return base / target_name / REPORT_BASENAME
        return base / REPORT_BASENAME
    # custom checkers: keep them under docs/ so generate html can find them
    return project_root / "docs" / f".check-report.{target_name}.json"


def save_report(report: CheckReport, project_root: Path) -> Path:
    path = report_path_for(report.target_kind, report.target_name, project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def load_report(path: Path) -> CheckReport | None:
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return report_from_dict(data, source=str(path))
