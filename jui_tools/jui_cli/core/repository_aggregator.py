"""Aggregate Repository / UseCase definitions across multiple spec files."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .spec_extractor import ScreenSpec, RepositoryDef, UseCaseDef, MethodDef, MethodParam


@dataclass
class AggregatorConflict:
    """A method signature mismatch encountered during aggregation.

    Conflicts are accumulated rather than raised so that an in-progress
    refactor (e.g. renaming params across screens) doesn't block the
    whole project generate. The first-seen signature wins; later
    conflicting variants are dropped from the aggregated protocol.
    """
    kind: str            # "repository" | "useCase"
    owner: str           # Repository name or UseCase name
    method: str
    existing_source: str
    new_source: str
    existing_signature: str
    new_signature: str
    reason: str

    def format(self) -> str:
        return (
            f"{self.kind} method signature conflict in "
            f"'{self.owner}.{self.method}':\n"
            f"  {self.existing_source}: {self.existing_signature}\n"
            f"  {self.new_source}: {self.new_signature}\n"
            f"  → {self.reason} (kept first-write-wins)"
        )


@dataclass
class AggregatedResult:
    """Result of aggregating all specs."""
    repositories: dict[str, RepositoryDef] = field(default_factory=dict)
    use_cases: dict[str, UseCaseDef] = field(default_factory=dict)
    conflicts: list[AggregatorConflict] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


class RepositoryAggregator:
    """Aggregates Repository and UseCase definitions from multiple screen specs.

    Same-named Repositories are merged (methods combined).
    Method signature conflicts are recorded as warnings and the first-seen
    signature wins (matches `ParentSpecMerger`'s philosophy so a parent_spec
    overlap or an in-progress rename doesn't block `jui generate project`).
    """

    def __init__(self):
        self._repo_methods: dict[str, dict[str, tuple[MethodDef, str]]] = {}
        # repo_name -> {method_name: (MethodDef, source_file)}
        self._repo_descriptions: dict[str, str] = {}
        self._use_cases: dict[str, tuple[UseCaseDef, str]] = {}
        # uc_name -> (UseCaseDef, source_file)
        self._conflicts: list[AggregatorConflict] = []

    def add_spec(self, source_file: str, spec: ScreenSpec) -> None:
        """Add a spec's repositories and use cases to the aggregator."""
        for repo in spec.repositories:
            if repo.name not in self._repo_methods:
                self._repo_methods[repo.name] = {}
                self._repo_descriptions[repo.name] = repo.description

            for method in repo.methods:
                existing = self._repo_methods[repo.name].get(method.name)
                if existing is not None:
                    existing_method, existing_source = existing
                    conflict = _check_signature_conflict(existing_method, method)
                    if conflict:
                        self._conflicts.append(AggregatorConflict(
                            kind="Repository",
                            owner=repo.name,
                            method=method.name,
                            existing_source=existing_source,
                            new_source=source_file,
                            existing_signature=_format_signature(existing_method),
                            new_signature=_format_signature(method),
                            reason=conflict,
                        ))
                        continue
                    existing_method.platforms = _union_platforms(
                        existing_method.platforms, method.platforms
                    )
                else:
                    self._repo_methods[repo.name][method.name] = (method, source_file)

        for uc in spec.use_cases:
            if uc.name in self._use_cases:
                # UseCase names should be unique per spec
                existing_uc, existing_source = self._use_cases[uc.name]
                # Merge methods (same conflict check)
                for method in uc.methods:
                    existing_method = next((m for m in existing_uc.methods if m.name == method.name), None)
                    if existing_method:
                        conflict = _check_signature_conflict(existing_method, method)
                        if conflict:
                            self._conflicts.append(AggregatorConflict(
                                kind="UseCase",
                                owner=uc.name,
                                method=method.name,
                                existing_source=existing_source,
                                new_source=source_file,
                                existing_signature=_format_signature(existing_method),
                                new_signature=_format_signature(method),
                                reason=conflict,
                            ))
                            continue
                        existing_method.platforms = _union_platforms(
                            existing_method.platforms, method.platforms
                        )
                    else:
                        existing_uc.methods.append(method)
                # Merge repository dependencies
                for dep in uc.repositories:
                    if dep not in existing_uc.repositories:
                        existing_uc.repositories.append(dep)
            else:
                self._use_cases[uc.name] = (uc, source_file)

    def aggregate(self) -> AggregatedResult:
        """Build the aggregated result. Call after all specs are added."""
        result = AggregatedResult()

        for repo_name, methods in self._repo_methods.items():
            result.repositories[repo_name] = RepositoryDef(
                name=repo_name,
                methods=[m for m, _ in methods.values()],
                description=self._repo_descriptions.get(repo_name, ""),
            )

        for uc_name, (uc, _) in self._use_cases.items():
            result.use_cases[uc_name] = uc

        result.conflicts = list(self._conflicts)
        return result

    def save_cache(self, cache_path: Path, spec_files: list[Path]) -> None:
        """Save aggregation result as .jui_cache.json."""
        result = self.aggregate()
        spec_hashes = {}
        for sf in spec_files:
            if sf.exists():
                content = sf.read_bytes()
                spec_hashes[sf.name] = f"sha256:{hashlib.sha256(content).hexdigest()}"

        cache = {
            "version": "1.0",
            "spec_hashes": spec_hashes,
            "repositories": {
                name: _repo_to_dict(repo)
                for name, repo in result.repositories.items()
            },
            "use_cases": {
                name: _usecase_to_dict(uc)
                for name, uc in result.use_cases.items()
            },
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
            f.write("\n")

    @staticmethod
    def load_cache(cache_path: Path, spec_files: list[Path]) -> AggregatedResult | None:
        """Load cache if valid (all spec hashes match). Returns None if stale."""
        if not cache_path.exists():
            return None

        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)

        stored_hashes = cache.get("spec_hashes", {})
        for sf in spec_files:
            if not sf.exists():
                return None
            content = sf.read_bytes()
            current_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
            if stored_hashes.get(sf.name) != current_hash:
                return None

        # Reconstruct from cache
        result = AggregatedResult()
        for name, data in cache.get("repositories", {}).items():
            result.repositories[name] = _dict_to_repo(name, data)
        for name, data in cache.get("use_cases", {}).items():
            result.use_cases[name] = _dict_to_usecase(name, data)
        return result


def _union_platforms(a: list[str], b: list[str]) -> list[str]:
    """Union platforms lists. Empty list means 'all platforms' and is absorbing."""
    if not a or not b:
        return []  # unrestricted wins
    merged: list[str] = list(a)
    for p in b:
        if p not in merged:
            merged.append(p)
    return merged


def _check_signature_conflict(a: MethodDef, b: MethodDef) -> str | None:
    """Check if two method definitions conflict. Returns description or None."""
    # Check param count
    if len(a.params) != len(b.params):
        return f"params count mismatch ({len(a.params)} vs {len(b.params)})"

    # Check param types
    for i, (pa, pb) in enumerate(zip(a.params, b.params)):
        if pa.type != pb.type:
            return f"param[{i}] type mismatch ({pa.name}: {pa.type} vs {pb.name}: {pb.type})"

    # Check return type
    if a.return_type and b.return_type and a.return_type != b.return_type:
        return f"return type mismatch ({a.return_type} vs {b.return_type})"

    return None


def _format_signature(method: MethodDef) -> str:
    """Format method as readable signature."""
    params = ", ".join(f"{p.name}: {p.type}" for p in method.params)
    sig = f"func {method.name}({params})"
    if method.return_type:
        sig += f" -> {method.return_type}"
    return sig


def _repo_to_dict(repo: RepositoryDef) -> dict:
    return {
        "description": repo.description,
        "methods": [_method_to_dict(m) for m in repo.methods],
    }


def _usecase_to_dict(uc: UseCaseDef) -> dict:
    return {
        "description": uc.description,
        "repositories": uc.repositories,
        "methods": [_method_to_dict(m) for m in uc.methods],
    }


def _method_to_dict(m: MethodDef) -> dict:
    return {
        "name": m.name,
        "params": [{"name": p.name, "type": p.type} for p in m.params],
        "return_type": m.return_type,
        "is_async": m.is_async,
        "platforms": list(m.platforms),
    }


def _dict_to_repo(name: str, data: dict) -> RepositoryDef:
    return RepositoryDef(
        name=name,
        methods=[_dict_to_method(m) for m in data.get("methods", [])],
        description=data.get("description", ""),
    )


def _dict_to_usecase(name: str, data: dict) -> UseCaseDef:
    return UseCaseDef(
        name=name,
        methods=[_dict_to_method(m) for m in data.get("methods", [])],
        repositories=data.get("repositories", []),
        description=data.get("description", ""),
    )


def _dict_to_method(data: dict) -> MethodDef:
    return MethodDef(
        name=data["name"],
        params=[MethodParam(name=p["name"], type=p["type"]) for p in data.get("params", [])],
        return_type=data.get("return_type", ""),
        is_async=data.get("is_async", True),
        platforms=list(data.get("platforms", []) or []),
    )
