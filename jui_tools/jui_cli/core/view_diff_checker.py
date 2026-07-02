"""Compare generated Layout JSON to an on-disk implementation Layout JSON.

Used by ``jui verify`` to report structural drift between the spec's
expected output and what currently exists in the repository.

The comparison recursively resolves ``cellClasses`` / ``include``
references so that cells declared in separate layout files (e.g.
``chat/message_cell.json``) are aggregated into the actual-layout view
of ids for a single screen.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class NodeDiff:
    node_id: str
    expected_type: str | None = None
    actual_type: str | None = None
    status: str = ""  # "missing", "extra", "type_mismatch"


@dataclass
class DiffResult:
    screen: str
    match: int = 0
    expected_ids: set[str] = field(default_factory=set)
    actual_ids: set[str] = field(default_factory=set)
    missing: list[NodeDiff] = field(default_factory=list)
    extra: list[NodeDiff] = field(default_factory=list)
    type_mismatch: list[NodeDiff] = field(default_factory=list)

    @property
    def total_match_pct(self) -> int:
        total = len(self.expected_ids | self.actual_ids)
        if total == 0:
            return 100
        return int(round(100 * self.match / total))

    @property
    def has_diff(self) -> bool:
        return bool(self.missing or self.extra or self.type_mismatch)


class ViewDiffChecker:
    """Structural diff between two Layout JSON trees."""

    def __init__(
        self,
        layouts_root: Path | None = None,
        normalizer: Callable[[Any], Any] | None = None,
    ):
        # Root directory used to resolve ``cellClasses`` / ``include``
        # references when comparing against an actual Layout JSON tree.
        self._layouts_root = Path(layouts_root) if layouts_root else None
        # Optional tree transform applied to BOTH sides of the comparison
        # (and to referenced layout files). Used by ``jui verify`` on
        # normalizeLayouts projects so L1 canonicalization can never
        # produce false drift between spec-generated and on-disk trees.
        self._normalizer = normalizer

    def compare(
        self,
        generated: dict[str, Any],
        actual: dict[str, Any],
        screen: str = "",
    ) -> DiffResult:
        if self._normalizer is not None:
            generated = self._normalizer(generated)
            actual = self._normalizer(actual)
        result = DiffResult(screen=screen)

        gen_index: dict[str, str] = {}
        act_index: dict[str, str] = {}
        self._flatten(generated, gen_index)
        self._flatten(actual, act_index, resolve_refs=self._layouts_root is not None)

        result.expected_ids = set(gen_index)
        result.actual_ids = set(act_index)

        for node_id in sorted(result.expected_ids & result.actual_ids):
            if gen_index[node_id] != act_index[node_id]:
                result.type_mismatch.append(
                    NodeDiff(
                        node_id=node_id,
                        expected_type=gen_index[node_id],
                        actual_type=act_index[node_id],
                        status="type_mismatch",
                    )
                )
            else:
                result.match += 1

        for node_id in sorted(result.expected_ids - result.actual_ids):
            result.missing.append(
                NodeDiff(
                    node_id=node_id,
                    expected_type=gen_index[node_id],
                    status="missing",
                )
            )

        for node_id in sorted(result.actual_ids - result.expected_ids):
            result.extra.append(
                NodeDiff(
                    node_id=node_id,
                    actual_type=act_index[node_id],
                    status="extra",
                )
            )

        return result

    # ------------------------------------------------------------------

    def _flatten(
        self,
        node: Any,
        out: dict[str, str],
        resolve_refs: bool = False,
        loaded_files: set[str] | None = None,
    ) -> None:
        if loaded_files is None:
            loaded_files = set()
        if isinstance(node, dict):
            nid = node.get("id")
            if nid:
                # Treat a missing type as the Layout JSON default (View)
                out[nid] = node.get("type") or "View"

            if resolve_refs and self._layouts_root is not None:
                cc = node.get("cellClasses")
                if isinstance(cc, list):
                    for ref in cc:
                        if isinstance(ref, str):
                            self._load_ref(ref, out, loaded_files)
                inc = node.get("include")
                if isinstance(inc, str):
                    self._load_ref(inc, out, loaded_files)

            for key in ("child", "children", "content", "headerCell"):
                if key in node:
                    self._flatten(node[key], out, resolve_refs, loaded_files)
        elif isinstance(node, list):
            for item in node:
                self._flatten(item, out, resolve_refs, loaded_files)

    def _load_ref(self, ref: str, out: dict[str, str], loaded: set[str]) -> None:
        ref = ref.strip()
        if not ref or self._layouts_root is None:
            return
        path = self._layouts_root / f"{ref}.json"
        key = str(path.resolve())
        if key in loaded or not path.exists():
            return
        loaded.add(key)
        try:
            sub = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        if self._normalizer is not None:
            sub = self._normalizer(sub)
        self._flatten(sub, out, resolve_refs=True, loaded_files=loaded)


def render_report(results: list[DiffResult], detail: bool = False) -> str:
    """Render a list of DiffResult as a markdown-ish text report."""
    lines: list[str] = []
    lines.append("# jui verify report")
    lines.append("")
    lines.append(
        "| Screen | Expected | Actual | Match | Missing | Extra | TypeMM | % |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    total_match = total_missing = total_extra = total_tm = 0
    for r in results:
        lines.append(
            f"| {r.screen} | {len(r.expected_ids)} | {len(r.actual_ids)} | "
            f"{r.match} | {len(r.missing)} | {len(r.extra)} | "
            f"{len(r.type_mismatch)} | {r.total_match_pct}% |"
        )
        total_match += r.match
        total_missing += len(r.missing)
        total_extra += len(r.extra)
        total_tm += len(r.type_mismatch)
    lines.append("")
    lines.append(
        f"**Total: match={total_match}, missing={total_missing}, "
        f"extra={total_extra}, type_mismatch={total_tm}**"
    )

    if detail:
        for r in results:
            if not r.has_diff:
                continue
            lines.append("")
            lines.append(f"## {r.screen}")
            if r.missing:
                lines.append("")
                lines.append("**Missing (in spec but not in Layout JSON):**")
                for d in r.missing:
                    lines.append(f"- {d.node_id} ({d.expected_type})")
            if r.extra:
                lines.append("")
                lines.append("**Extra (in Layout JSON but not in spec):**")
                for d in r.extra:
                    lines.append(f"- {d.node_id} ({d.actual_type})")
            if r.type_mismatch:
                lines.append("")
                lines.append("**Type mismatches:**")
                for d in r.type_mismatch:
                    lines.append(
                        f"- {d.node_id}: spec={d.expected_type} vs "
                        f"code={d.actual_type}"
                    )

    return "\n".join(lines) + "\n"
