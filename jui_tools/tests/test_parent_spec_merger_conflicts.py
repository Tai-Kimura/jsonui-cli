"""Tests for ParentSpecMerger and RepositoryAggregator conflict semantics.

Conflicts are reported as a structured list but the merged/aggregated
spec keeps first-write-wins, so callers can surface conflicts as a
warning and proceed instead of aborting. This unblocks `jui generate
project` during in-progress refactors that span multiple specs.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.parent_spec_merger import ParentSpecMerger
from jui_cli.core.repository_aggregator import RepositoryAggregator
from jui_cli.core.spec_extractor import (
    MethodDef,
    MethodParam,
    RepositoryDef,
    ScreenSpec,
    UseCaseDef,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sub_spec(name: str, endpoints: list[dict]) -> dict:
    return {
        "type": "screen_sub_spec",
        "metadata": {"name": name},
        "structure": {"components": []},
        "stateManagement": {},
        "dataFlow": {
            "repositories": [],
            "useCases": [],
            "apiEndpoints": endpoints,
        },
    }


def _parent_spec(sub_files: list[str]) -> dict:
    return {
        "type": "screen_parent_spec",
        "metadata": {"name": "Chat"},
        "subSpecs": [{"file": f} for f in sub_files],
        "structure": {},
        "stateManagement": {},
        "dataFlow": {},
    }


class ParentSpecMergerConflictTests(unittest.TestCase):
    """Reproduces the kept-first-wins behaviour relied on by `jui g project`
    and `jui build` after the parent_spec merge-conflict bug fix."""

    def test_conflicting_endpoints_are_reported_and_first_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sub_a_path = base / "chat-core.spec.json"
            sub_b_path = base / "chat-recommendation.spec.json"
            parent_path = base / "chat.spec.json"

            _write_json(
                sub_a_path,
                _sub_spec(
                    "Chat - Core",
                    [
                        {
                            "method": "POST",
                            "path": "/api/chat/bar-confirm",
                            "request": {"shape": "core"},
                        }
                    ],
                ),
            )
            _write_json(
                sub_b_path,
                _sub_spec(
                    "Chat - Recommendation",
                    [
                        {
                            "method": "POST",
                            "path": "/api/chat/bar-confirm",
                            "request": {"shape": "recommendation"},
                        }
                    ],
                ),
            )
            _write_json(
                parent_path,
                _parent_spec(["chat-core.spec.json", "chat-recommendation.spec.json"]),
            )

            merger = ParentSpecMerger(spec_dir=base)
            result = merger.merge_from_file(parent_path)

            # Conflict surfaced...
            self.assertTrue(result.has_conflicts)
            self.assertEqual(len(result.conflicts), 1)
            conflict = result.conflicts[0]
            self.assertIn("apiEndpoints", conflict.path)
            self.assertIn("POST", conflict.path)
            self.assertIn("/api/chat/bar-confirm", conflict.path)

            # ...but the merged spec is usable: first-write-wins kept
            # the chat-core variant, conflict didn't drop the endpoint.
            endpoints = result.spec["dataFlow"]["apiEndpoints"]
            self.assertEqual(len(endpoints), 1)
            self.assertEqual(endpoints[0]["request"]["shape"], "core")

    def test_no_conflicts_when_endpoints_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sub_a_path = base / "core.spec.json"
            sub_b_path = base / "rec.spec.json"
            parent_path = base / "parent.spec.json"

            same_endpoint = {
                "method": "GET",
                "path": "/api/foo",
                "request": {"shape": "x"},
            }
            _write_json(sub_a_path, _sub_spec("Core", [same_endpoint]))
            _write_json(sub_b_path, _sub_spec("Rec", [same_endpoint]))
            _write_json(
                parent_path,
                _parent_spec(["core.spec.json", "rec.spec.json"]),
            )

            merger = ParentSpecMerger(spec_dir=base)
            result = merger.merge_from_file(parent_path)

            self.assertFalse(result.has_conflicts)
            endpoints = result.spec["dataFlow"]["apiEndpoints"]
            self.assertEqual(len(endpoints), 1)


def _spec_with_repo(name: str, method: MethodDef) -> ScreenSpec:
    return ScreenSpec(
        name=name,
        display_name=name,
        description="",
        repositories=[
            RepositoryDef(
                name="HistoryRepository",
                methods=[method],
                description="",
            )
        ],
    )


def _method(params_count: int) -> MethodDef:
    return MethodDef(
        name="getHistory",
        params=[MethodParam(name=f"p{i}", type="String") for i in range(params_count)],
        return_type="HistoryListResponse",
        is_async=True,
    )


class RepositoryAggregatorConflictTests(unittest.TestCase):
    """Aggregator must record signature conflicts as data instead of raising,
    so `jui generate project` can warn and continue across an in-progress
    cross-spec refactor."""

    def test_signature_conflict_is_collected_first_wins(self):
        agg = RepositoryAggregator()
        agg.add_spec("first.spec.json", _spec_with_repo("First", _method(5)))
        agg.add_spec("second.spec.json", _spec_with_repo("Second", _method(2)))

        result = agg.aggregate()
        self.assertTrue(result.has_conflicts)
        self.assertEqual(len(result.conflicts), 1)

        c = result.conflicts[0]
        self.assertEqual(c.kind, "Repository")
        self.assertEqual(c.owner, "HistoryRepository")
        self.assertEqual(c.method, "getHistory")
        self.assertIn("first.spec.json", c.existing_source)
        self.assertIn("second.spec.json", c.new_source)
        self.assertIn("kept first-write-wins", c.format())

        # First-write-wins: 5-param signature is kept.
        repo = result.repositories["HistoryRepository"]
        self.assertEqual(len(repo.methods), 1)
        self.assertEqual(len(repo.methods[0].params), 5)

    def test_no_conflict_when_signatures_match(self):
        agg = RepositoryAggregator()
        agg.add_spec("a.spec.json", _spec_with_repo("A", _method(3)))
        agg.add_spec("b.spec.json", _spec_with_repo("B", _method(3)))

        result = agg.aggregate()
        self.assertFalse(result.has_conflicts)


if __name__ == "__main__":
    unittest.main()
