"""shared/core/layout_data_fields.py answers shared/core/layout_data_fields_vectors.json.

The same vector is run by each generator's spec (sjui / kjui / rjui) on its
own expansion and extraction, so the collector validate uses agrees with what
the generators put in the Data type, platform by platform.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_test_cli import shared_core

FIELDS = shared_core.load("layout_data_fields")
VECTORS = json.loads((shared_core.shared_core_dir() / "layout_data_fields_vectors.json").read_text(encoding="utf-8"))


def _materialise(tmp_path: Path, files: dict) -> tuple[Path, Path]:
    for rel, body in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(body), encoding="utf-8")
    return tmp_path / "layouts", tmp_path / "styles"


@pytest.mark.parametrize("platform", ["ios", "android", "web"])
@pytest.mark.parametrize("vector", VECTORS["cases"], ids=[c["id"] for c in VECTORS["cases"]])
def test_the_collector_answers_the_vector(tmp_path, vector, platform):
    layouts, styles = _materialise(tmp_path, vector["files"])
    got = FIELDS.declared_data_fields(layouts / f"{vector['screen']}.json", platform,
                                      layouts_dir=layouts, styles_dir=styles)
    assert [list(f) for f in got] == vector["expected"][platform]


def test_the_vector_covers_every_platform_and_disagrees_somewhere():
    # A vector whose platforms always agree could not catch a collector that
    # ignored the platform; at least one case has to tell them apart.
    assert all(set(c["expected"]) == {"ios", "android", "web"} for c in VECTORS["cases"])
    assert any(len({json.dumps(v) for v in c["expected"].values()}) > 1 for c in VECTORS["cases"])


def test_an_unknown_platform_is_refused(tmp_path):
    layouts, styles = _materialise(tmp_path, VECTORS["cases"][0]["files"])
    with pytest.raises(ValueError):
        FIELDS.declared_data_fields(layouts / "screen.json", "flutter", layouts_dir=layouts, styles_dir=styles)
