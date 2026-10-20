"""Skill spirits' models (viz/spirits.py): what makes a model folder ok or broken, read without unpacking a .glb."""
from __future__ import annotations

import json
import struct

import pytest

from jui_cli.viz import spirits


def glb(doc: dict, binary: bytes = b"") -> bytes:
    body = json.dumps(doc).encode()
    body += b" " * (-len(body) % 4)
    out = struct.pack("<I4s", len(body), b"JSON") + body
    if binary:
        binary += b"\0" * (-len(binary) % 4)
        out += struct.pack("<I4s", len(binary), b"BIN\x00") + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(out)) + out


def png_head(w: int, h: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", w, h) + b"\x08\x06\0\0\0" + b"\0" * 4


def mesh_doc(triangles: int = 1, nodes: int = 1, **extra) -> dict:
    doc = {"asset": {"version": "2.0"}, "accessors": [{"count": triangles * 3, "type": "VEC3", "componentType": 5126}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
           "nodes": [{"name": f"n{i}", "mesh": 0} for i in range(nodes)]}
    doc.update(extra)
    return doc


def model(tmp_path, spec: dict | None = None, files: dict | None = None, name: str = "m1"):
    folder = tmp_path / name
    folder.mkdir(parents=True)
    for fname, data in (files if files is not None else {"spirit.glb": glb(mesh_doc())}).items():
        (folder / fname).write_bytes(data)
    if spec is not None:
        (folder / "spirit.json").write_text(json.dumps(spec), encoding="utf-8")
    return folder


def test_a_small_model_with_every_section_is_ok(tmp_path):
    anim = mesh_doc(animations=[{"name": "appear"}, {"name": "loop"}, {"name": "leave"}])
    folder = model(tmp_path, {
        "version": 1, "name": {"ja": "歯車", "en": "Gear"}, "skills": ["code-review"], "weight": 2,
        "spirit": {"file": "spirit.glb", "at": "back", "scale": 1.2, "opacity": 0.6, "tint": "#c8a040",
                   "clips": {"appear": "appear", "loop": "loop", "leave": "leave"},
                   "material": {"kind": "ghost", "rim": "#ffffff", "shade": "#203040", "rimK": 1.5, "pow": 2},
                   "outline": {"color": "#101010", "width": 0.02}},
        "parts": [{"file": "robot-goggles.glb", "at": "band", "offset": [0, 0.1, 0]}, {"file": "prop-wrench.glb", "at": "handR"}],
        "robot": {"hide": ["band"], "eyes": {"shape": "sharp", "color": "#ffcc00"}, "pose": "type", "tag": "auto"},
        "effects": {"afterimage": {"count": 3}, "sparks": {"color": "#ffd060", "rate": 8}},
        "bubble": {"text": {"ja": ["一行目", "二行目"], "en": "one"}, "ruby": "るび", "target": "robot", "font": "mincho",
                   "tail": "left", "showSec": 4},
        "shouts": {"texts": {"ja": ["カチ", "ゴン"]}, "everySec": 0.6, "style": {"fill": "#ffffff", "skew": -12}},
    }, {"spirit.glb": glb(anim), "robot-goggles.glb": glb(mesh_doc()), "prop-wrench.glb": glb(mesh_doc())})
    m = spirits.check_model(folder)
    assert m["problems"] == [] and m["ok"]
    assert m["files"]["spirit.glb"]["clips"] == ["appear", "loop", "leave"]
    assert m["skills"] == ["code-review"] and m["weight"] == 2


@pytest.mark.parametrize("spec, says", [
    ({"version": 1, "parts": [{"file": "robot-a.glb", "at": "shoulder"}]}, "parts[0].at: 'shoulder' is not one of"),
    ({"version": 1, "robot": {"pose": "dance"}}, "robot.pose: 'dance' is not one of"),
    ({"version": 1, "effects": {"fireworks": {}}}, "unknown effect 'fireworks'"),
    ({"version": 1, "effects": {"aura": {"colour": "#ffffff"}}}, "effects.aura: unknown key 'colour'"),
    ({"version": 1, "spirit": {"file": "spirit.glb", "tint": "gold"}}, "spirit.tint: 'gold' is not a colour"),
    ({"version": 1, "spirit": {"file": "spirit.glb", "opacity": 2}}, "spirit.opacity: 2 is not a number from 0 to 1"),
    ({"version": 1, "robot": {"hide": ["legs"]}}, "robot.hide[0]: 'legs' is not one of band, antenna, headset"),
    ({"version": 1, "bubble": {"text": "x", "target": "desk"}}, "bubble.target: 'desk' is not one of spirit, robot"),
    ({"version": 1, "bubble": {"text": ["1", "2", "3", "4", "5", "6", "7"]}}, "bubble.text: has 7 lines"),
    ({"version": 1, "bubble": {"ruby": "x"}}, "bubble: has no text"),
    ({"version": 1, "shouts": {"texts": [f"w{i}" for i in range(21)]}}, "shouts.texts: is not a list of 1 to 20"),
    ({"version": 1, "name": {"Japanese": "x"}}, "'Japanese' is not a language code"),
    ({"version": 1, "name": "x" * 201}, "name: is 201 characters"),
    ({"version": 2}, "version: 2 (1 is read)"),
    ({"name": "x"}, "has no version"),
    ({"version": 1, "colour": "#ffffff"}, "spirit.json: unknown key 'colour'"),
    ({"version": 1, "parts": [{"file": "hair.glb"}]}, "parts[0].file: 'hair.glb' is not a .glb in this folder"),
    ({"version": 1, "spirit": {"file": "spirit.glb", "clips": {"loop": "type"}}}, "spirit.glb has no clip 'type'"),
])
def test_a_mistake_in_spirit_json_breaks_the_model_and_is_named(tmp_path, spec, says):
    m = spirits.check_model(model(tmp_path, spec, {"spirit.glb": glb(mesh_doc()), "robot-a.glb": glb(mesh_doc())}))
    assert not m["ok"]
    assert any(says in p for p in m["problems"]), m["problems"]


@pytest.mark.parametrize("data, says", [
    (b"not a glb at all, just text", "no glTF magic"),
    (struct.pack("<4sII", b"glTF", 1, 20) + b"\0" * 8, "glTF version 1"),
    (glb(mesh_doc())[:-4], "its header says"),
    (glb(mesh_doc(extensionsUsed=["KHR_draco_mesh_compression"])), "uses KHR_draco_mesh_compression"),
    (glb(mesh_doc(extensionsUsed=["EXT_meshopt_compression"])), "uses EXT_meshopt_compression"),
    (glb(mesh_doc(extensionsRequired=["VENDOR_magic"])), "requires VENDOR_magic"),
    (glb(mesh_doc(buffers=[{"uri": "model.bin", "byteLength": 4}])), "buffer 0 is outside the file"),
    (glb(mesh_doc(images=[{"uri": "skin.png"}])), "image 0 is outside the file"),
    (glb(mesh_doc(images=[{"mimeType": "image/webp", "bufferView": 0}])), "image 0 is 'image/webp'"),
    (glb(mesh_doc(triangles=100_001)), "100,001 triangles (100,000 at most)"),
])
def test_a_glb_the_page_cannot_read_breaks_the_model(tmp_path, data, says):
    m = spirits.check_model(model(tmp_path, None, {"spirit.glb": data}))
    assert not m["ok"]
    assert any(p.startswith("spirit.glb: ") and says in p for p in m["problems"]), m["problems"]


def test_triangles_are_counted_per_node_that_draws_the_mesh_and_summed_over_files(tmp_path):
    assert spirits.summarize_glb(glb(mesh_doc(triangles=10, nodes=3)))["triangles"] == 30
    files = {"spirit.glb": glb(mesh_doc(triangles=60_000)), "robot-a.glb": glb(mesh_doc(triangles=50_000))}
    m = spirits.check_model(model(tmp_path, None, files))
    assert "110,000 triangles in all (100,000 at most)" in m["problems"]


def test_an_embedded_texture_is_measured_from_its_header(tmp_path):
    for side, ok in ((2048, True), (2049, False)):
        head = png_head(side, 16)
        doc = mesh_doc(images=[{"mimeType": "image/png", "bufferView": 0}],
                       bufferViews=[{"buffer": 0, "byteOffset": 0, "byteLength": len(head)}], buffers=[{"byteLength": len(head)}])
        summary = spirits.summarize_glb(glb(doc, head))
        assert summary["textures"] == [(side, 16)]
        assert (summary["problems"] == []) is ok, summary["problems"]


def test_a_file_or_folder_over_its_size_is_refused_before_it_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(spirits, "MAX_FILE_BYTES", 100)
    m = spirits.check_model(model(tmp_path, None, {"spirit.glb": glb(mesh_doc()) + b"\0" * 200}))
    assert any(p.startswith("spirit.glb: ") and "bytes (0 MB at most)" in p for p in m["problems"])


def test_a_folder_with_nothing_to_show_is_broken_and_other_files_are_notes(tmp_path):
    m = spirits.check_model(model(tmp_path, {"version": 1, "bubble": {"text": "x"}}, {"preview.png": b"x"}))
    assert any("nothing to show" in p for p in m["problems"])
    assert m["notes"] == ["preview.png: not read (a model reads spirit.json, spirit.glb, robot-*.glb and prop-*.glb)"]
    only_effects = spirits.check_model(model(tmp_path, {"version": 1, "effects": {"aura": {"color": "#ffd23a"}}}, {}, name="m2"))
    assert only_effects["ok"], only_effects["problems"]


def test_spirit_json_that_is_not_json_is_said(tmp_path):
    folder = model(tmp_path, None)
    (folder / "spirit.json").write_text("{version: 1", encoding="utf-8")
    assert spirits.check_model(folder)["problems"] == ["spirit.json: cannot be read as JSON (JSONDecodeError)"]


def test_the_scan_skips_badly_named_folders_and_the_doctor_names_a_broken_model(tmp_path, monkeypatch):
    home = tmp_path / "viz"
    monkeypatch.setenv("JUI_VIZ_HOME", str(home))
    base = home / "mine"
    model(base, {"version": 1}, name="good")
    model(base, {"version": 1, "robot": {"pose": "dance"}}, name="bad")
    model(base, {"version": 1}, name="has space")
    (home / "config.json").write_text(json.dumps({"spiritsDir": "mine"}), encoding="utf-8")
    assert spirits.own_dir() == base
    found = spirits.scan(base)
    assert [m["name"] for m in found["models"]] == ["bad", "good"] and found["skipped"] == ["has space"]
    row = spirits.doctor_check()
    assert row["name"] == "spirits" and row["ok"] is False
    assert "1 of 2 of yours ok" in row["detail"]
    assert "bad not used: spirit.json robot.pose: 'dance' is not one of" in row["detail"]
    assert "folders not read (name not A-Z a-z 0-9 _ -): has space" in row["detail"]


def test_without_spirits_dir_the_folder_is_spirits_in_the_viz_home(tmp_path, monkeypatch):
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path))
    assert spirits.own_dir() == tmp_path / "spirits"
    row = spirits.doctor_check()
    assert row["ok"] is True and "0 of 0 of yours ok" in row["detail"] and "no such folder yet" in row["detail"]


def test_the_command_checks_a_model_folder_and_exits_1_when_it_is_broken(tmp_path, capsys):
    good = model(tmp_path, {"version": 1}, name="good")
    bad = model(tmp_path, {"version": 1, "spirit": {"file": "spirit.glb", "at": "tail"}}, name="bad")
    assert spirits.main([str(good)]) == 0
    assert spirits.main([str(bad)]) == 1
    out = capsys.readouterr().out
    assert "OK  good" in out and "NG  bad" in out and "error: spirit.json spirit.at: 'tail' is not one of" in out
