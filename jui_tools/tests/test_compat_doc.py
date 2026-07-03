"""Tests for ``jui conformance compat-doc`` (conformance/compat_doc.py)."""

import json
from pathlib import Path

from jui_cli.conformance.compat_doc import generate_compat_doc


def _write_inputs(tmp_path: Path):
    definitions = tmp_path / "attribute_definitions.json"
    definitions.write_text(json.dumps({
        "common": {
            "width": {"type": ["string", "number"]},
            "opacity": {"type": "number", "aliases": ["alpha"]},
        },
        "Collection": {
            "onValueChange": {
                "type": ["string", "binding"],
                "platform": ["swift", "kotlin", "react"],
                "aliases": ["onValueChanged", "onPageChanged"],
            },
            "oldAttr": {"type": "string", "deprecated": True},
        },
    }))

    conf = tmp_path / "conformance"
    (conf / "results").mkdir(parents=True)
    (conf / "manifest.json").write_text(json.dumps({
        "fixtures": [
            {"id": "common/width__a", "component": "common", "attribute": "width"},
            {"id": "common/width__b", "component": "common", "attribute": "width"},
            {"id": "Collection/onValueChange__fire", "component": "Collection",
             "attribute": "onValueChange"},
        ],
    }))
    (conf / "results" / "android.results.json").write_text(json.dumps({
        "results": [
            {"id": "common/width__a", "status": "pass"},
            {"id": "common/width__b", "status": "fail"},
            {"id": "Collection/onValueChange__fire", "status": "pass"},
        ],
    }))
    return definitions, conf


def test_generates_expected_tables(tmp_path):
    definitions, conf = _write_inputs(tmp_path)
    out = tmp_path / "compat.md"
    summary = generate_compat_doc(definitions, conf, "android", out)

    text = out.read_text()
    assert "@generated" in text
    assert summary.components == 2
    assert summary.attributes == 4
    assert summary.covered == 2

    # alias + coverage rollups
    assert "| `opacity` | `alpha` |" in text
    assert "`onValueChanged`, `onPageChanged`" in text
    assert "1/2 pass (1 fail/error)" in text  # width
    assert "| `onValueChange` " in text and "✅ 1 pass" in text
    # deprecated flag + uncovered attr
    assert "| `oldAttr` |  | string | yes | — |" in text


def test_deterministic_output(tmp_path):
    definitions, conf = _write_inputs(tmp_path)
    out1 = tmp_path / "a.md"
    out2 = tmp_path / "b.md"
    generate_compat_doc(definitions, conf, "android", out1)
    generate_compat_doc(definitions, conf, "android", out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_missing_results_warns_but_writes(tmp_path):
    definitions, _ = _write_inputs(tmp_path)
    empty_conf = tmp_path / "empty"
    empty_conf.mkdir()
    out = tmp_path / "c.md"
    summary = generate_compat_doc(definitions, empty_conf, "ios", out)
    assert out.is_file()
    assert summary.warnings  # both manifest and results missing
    assert "| `width` |" in out.read_text()
