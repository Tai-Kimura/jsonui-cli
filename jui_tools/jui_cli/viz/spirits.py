"""Skill spirits (ticket 2026-10-21-jui-viz-skill-spirit): while a session uses a skill, its robot can change its look
and a "spirit" can stand behind it. Each look is a model: one folder holding .glb files and a small spirit.json.

Where models are read from:
  - the bundled ones: the package's web/spirits/<name>/ (original works only, made by tools/spirits/);
  - the person's own: ``spiritsDir`` in the viz folder's config.json (absolute, or from the viz folder), else
    ``<viz home>/spirits/``. Each sub-folder whose name matches NAME_RE is one model.

What is checked, without unpacking a model (the page reads only the models found ok here):
  - a .glb's header (magic "glTF", version 2, its length) and its JSON chunk: the extensions it uses, triangles
    (accessor counts, per node that draws the mesh), images (PNG / JPEG headers in the binary chunk) and clip names;
  - spirit.json: every key, type and range against the closed lists below. An unknown key, anchor, pose, effect or
    colour is an error, so a typo is said rather than quietly ignored.

A model with any problem is broken: it is never chosen, and ``jui viz doctor`` names the file and what is wrong.
``python -m jui_cli.viz.spirits [FOLDER ...]`` prints the same check for model folders (or a folder of models).
"""
from __future__ import annotations

import json
import re
import struct
import sys
from importlib import resources
from pathlib import Path

from . import paths

NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
PART_FILE_RE = re.compile(r"(robot|prop)-[A-Za-z0-9_-]{1,64}\.glb")
COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
LANG_RE = re.compile(r"[a-z]{2}(-[A-Za-z0-9]{2,8})?")
SKILL_RE = re.compile(r"[A-Za-z0-9_.:-]{1,128}")

SPIRIT_JSON = "spirit.json"
SPIRIT_GLB = "spirit.glb"

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_MODEL_BYTES = 50 * 1024 * 1024
MAX_MODELS = 50
MAX_TRIANGLES = 100_000
MAX_TEXTURE_PX = 2048
MAX_JSON_BYTES = 64 * 1024
MAX_TEXT_CHARS = 200
MAX_SHOUTS = 20
MAX_PARTS = 16
MAX_SKILLS = 50
MAX_BUBBLE_LINES = 6

#: where a part or the spirit is put (the page's robot: 10-robot-core.js). head is the head group's origin, so a part
#: made in the head's own coordinates goes on with no offset.
ANCHORS = ("head", "forehead", "band", "headset", "face", "handL", "handR", "back", "root")
#: what spirit.json's robot.hide may take away while the skill runs (put back after)
HIDE = ("band", "antenna", "headset")
POSES = ("type", "book", "arms-crossed", "none")
EYE_SHAPES = ("normal", "sharp", "narrow")
TAG_PLACES = ("auto", "top", "cheek")
BUBBLE_TARGETS = ("spirit", "robot")
BUBBLE_FONTS = ("gothic", "mincho")
BUBBLE_TAILS = ("left", "right")
CLIP_SLOTS = ("appear", "loop", "leave")
MATERIAL_KINDS = ("ghost", "plain")
AURA_STYLES = ("flame", "column")

#: glTF extensions the page cannot read: they need a Worker and WASM, which the viz page's CSP does not allow
REFUSED_EXTENSIONS = ("KHR_draco_mesh_compression", "KHR_texture_basisu", "EXT_meshopt_compression")
#: what the vendored GLTFLoader (three 0.160.0) reads without anything more; a required extension outside it is refused
READ_EXTENSIONS = (
    "KHR_lights_punctual", "KHR_materials_clearcoat", "KHR_materials_ior", "KHR_materials_sheen",
    "KHR_materials_specular", "KHR_materials_transmission", "KHR_materials_iridescence", "KHR_materials_anisotropy",
    "KHR_materials_unlit", "KHR_materials_volume", "KHR_texture_transform", "KHR_mesh_quantization",
    "KHR_materials_emissive_strength", "EXT_materials_bump", "EXT_mesh_gpu_instancing",
)

# A field's kind: ("num", lo, hi), ("int", lo, hi), "color", "bool", ("enum", choices), ("vec3", lo, hi)
_NUM = lambda lo, hi: ("num", lo, hi)  # noqa: E731
_INT = lambda lo, hi: ("int", lo, hi)  # noqa: E731
#: an offset (the robot's units) and a rotation (degrees, as spiritPut turns it: a quarter turn is 90)
_OFFSET = ("vec3", -10, 10)
_DEGREES = ("vec3", -360, 360)

#: the effects the page draws (spirit.json effects.<name>), with the fields each takes
EFFECTS = {
    # style: "flame" (the default: an envelope with flame points and rising tongues) or "column" (an open cylinder)
    "aura": {"color": "color", "style": ("enum", AURA_STYLES), "size": _NUM(0.3, 3), "height": _NUM(0.2, 4),
             "opacity": _NUM(0, 1), "flicker": _NUM(0, 4)},
    # the pool holds as many as rate shows (rate × 1.6 s of life): rate 40 is 64 at once
    "sparks": {"color": "color", "rate": _NUM(0, 40), "rise": _NUM(0.1, 4), "size": _NUM(0.05, 0.3)},
    # count bolts at a time, each a ribbon length tall
    "lightning": {"color": "color", "everySec": _NUM(0.3, 30), "count": _INT(1, 4), "length": _NUM(0.5, 4)},
    "afterimage": {"count": _INT(1, 4), "spreadDeg": _NUM(0, 60)},
    "glow": {"color": "color", "opacity": _NUM(0, 1), "scale": _NUM(1, 1.5)},
}

#: the page's "ghost" look for the spirit (glTF cannot carry a shader): rim light over a shade, fading downward
MATERIAL_FIELDS = {
    "kind": ("enum", MATERIAL_KINDS), "rim": "color", "shade": "color", "base": "color",
    "rimK": _NUM(0, 4), "pow": _NUM(0.5, 8), "yFade": _NUM(-4, 4), "yFadeLen": _NUM(0.05, 8),
}
OUTLINE_FIELDS = {"color": "color", "width": _NUM(0, 0.2)}
SPIRIT_FIELDS = {
    "file": "file", "at": ("enum", ANCHORS), "offset": _OFFSET, "rotate": _DEGREES, "scale": _NUM(0.1, 5),
    "opacity": _NUM(0, 1), "tint": "color", "clips": "clips", "material": "material", "outline": "outline",
}
PART_FIELDS = {"file": "file", "at": ("enum", ANCHORS), "offset": _OFFSET, "rotate": _DEGREES, "scale": _NUM(0.1, 5)}
ROBOT_FIELDS = {"hide": "hide", "eyes": "eyes", "pose": ("enum", POSES), "tag": ("enum", TAG_PLACES)}
EYES_FIELDS = {"shape": ("enum", EYE_SHAPES), "color": "color"}
BUBBLE_FIELDS = {
    "text": "lines", "ruby": "text", "showSec": _NUM(0.5, 30), "target": ("enum", BUBBLE_TARGETS),
    "font": ("enum", BUBBLE_FONTS), "tail": ("enum", BUBBLE_TAILS),
}
SHOUTS_FIELDS = {"texts": "shoutTexts", "everySec": _NUM(0.1, 10), "style": "shoutStyle"}
SHOUT_STYLE_FIELDS = {"fill": "color", "stroke": "color", "skew": _NUM(-45, 45)}
TOP_FIELDS = {
    "version": "version", "name": "text", "skills": "skills", "weight": _NUM(0, 10), "spirit": "spirit",
    "parts": "parts", "robot": "robot", "effects": "effects", "bubble": "bubble", "shouts": "shouts",
}


# ---------------------------------------------------------------- where


def bundled_dir() -> Path:
    return Path(str(resources.files("jui_cli.viz").joinpath("web", "spirits")))


def own_dir() -> Path:
    """The person's models: config.json's spiritsDir (absolute, or from the viz folder), else <viz home>/spirits."""
    home = paths.viz_home()
    try:
        data = json.loads(paths.config_json().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    value = data.get("spiritsDir") if isinstance(data, dict) else None
    if isinstance(value, str) and value.strip():
        given = Path(value.strip()).expanduser()
        return given if given.is_absolute() else home / given
    return home / "spirits"


# ---------------------------------------------------------------- .glb


class GlbError(ValueError):
    pass


def read_glb(data: bytes) -> dict:
    """The parts of a .glb this module checks: {json, bin}. Raises GlbError when it is not a well-formed .glb."""
    if len(data) < 20:
        raise GlbError("too short for a .glb")
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise GlbError("not a .glb (no glTF magic)")
    if version != 2:
        raise GlbError(f"glTF version {version} (2 is read)")
    if length != len(data):
        raise GlbError(f"its header says {length} bytes, the file has {len(data)}")
    doc, binary, at = None, b"", 12
    while at < length:
        if at + 8 > length:
            raise GlbError("a chunk header runs past the end")
        size, kind = struct.unpack_from("<I4s", data, at)
        body = data[at + 8:at + 8 + size]
        if len(body) != size:
            raise GlbError("a chunk runs past the end")
        if doc is None:
            if kind != b"JSON":
                raise GlbError("the first chunk is not JSON")
            try:
                doc = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise GlbError(f"its JSON chunk cannot be read ({type(exc).__name__})") from None
            if not isinstance(doc, dict):
                raise GlbError("its JSON chunk is not an object")
        elif kind == b"BIN\x00" and not binary:
            binary = body
        at += 8 + size  # a chunk's length already counts its padding to 4 bytes
    if doc is None:
        raise GlbError("no JSON chunk")
    return {"json": doc, "bin": binary}


def _image_size(head: bytes) -> tuple[int, int] | None:
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        return struct.unpack_from(">II", head, 16)
    if head[:2] == b"\xff\xd8":
        at = 2
        while at + 9 < len(head):
            if head[at] != 0xFF:
                return None
            marker = head[at + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack_from(">HH", head, at + 5)
                return w, h
            at += 2 + struct.unpack_from(">H", head, at + 2)[0]
    return None


def _list(doc: dict, key: str) -> list:
    value = doc.get(key)
    return value if isinstance(value, list) else []


def _primitive_triangles(doc: dict, prim: dict) -> int:
    accessors = _list(doc, "accessors")
    mode = prim.get("mode", 4)
    index = prim.get("indices")
    if not isinstance(index, int):
        index = (prim.get("attributes") or {}).get("POSITION")
    if not isinstance(index, int) or not 0 <= index < len(accessors) or not isinstance(accessors[index], dict):
        return 0
    count = accessors[index].get("count")
    count = count if isinstance(count, int) and count > 0 else 0
    if mode == 4:
        return count // 3
    if mode in (5, 6):
        return max(0, count - 2)
    return 0


def summarize_glb(data: bytes) -> dict:
    """{triangles, textures: [(w, h)], clips: [names], nodes: [names], problems: [str]} for one .glb's bytes."""
    problems: list[str] = []
    try:
        glb = read_glb(data)
    except GlbError as exc:
        return {"triangles": 0, "textures": [], "clips": [], "nodes": [], "problems": [str(exc)]}
    doc, binary = glb["json"], glb["bin"]
    asset = doc.get("asset") if isinstance(doc.get("asset"), dict) else {}
    if str(asset.get("version", "")).split(".")[0] != "2":
        problems.append(f"asset.version {asset.get('version')!r} (2.x is read)")
    used = [e for e in _list(doc, "extensionsUsed") if isinstance(e, str)]
    for name in used:
        if name in REFUSED_EXTENSIONS:
            problems.append(f"uses {name} (compressed: needs a Worker and WASM, which the page cannot run)")
    for name in _list(doc, "extensionsRequired"):
        if name not in REFUSED_EXTENSIONS and name not in READ_EXTENSIONS:
            problems.append(f"requires {name}, which the page's loader does not read")
    for i, buf in enumerate(_list(doc, "buffers")):
        if isinstance(buf, dict) and "uri" in buf:
            problems.append(f"buffer {i} is outside the file (uri): everything must be in the .glb")
    meshes = _list(doc, "meshes")
    triangles = 0
    for node in _list(doc, "nodes"):
        mesh = node.get("mesh") if isinstance(node, dict) else None
        if isinstance(mesh, int) and 0 <= mesh < len(meshes) and isinstance(meshes[mesh], dict):
            for prim in _list(meshes[mesh], "primitives"):
                if isinstance(prim, dict):
                    triangles += _primitive_triangles(doc, prim)
    views = _list(doc, "bufferViews")
    textures = []
    for i, image in enumerate(_list(doc, "images")):
        if not isinstance(image, dict):
            continue
        if "uri" in image:
            problems.append(f"image {i} is outside the file (uri): embed it in the .glb")
            continue
        mime = image.get("mimeType")
        if mime not in ("image/png", "image/jpeg"):
            problems.append(f"image {i} is {mime!r} (PNG or JPEG is read)")
            continue
        view = image.get("bufferView")
        if not isinstance(view, int) or not 0 <= view < len(views) or not isinstance(views[view], dict):
            problems.append(f"image {i} has no bufferView")
            continue
        start = views[view].get("byteOffset", 0)
        size = views[view].get("byteLength", 0)
        if not isinstance(start, int) or not isinstance(size, int) or start < 0 or start + size > len(binary):
            problems.append(f"image {i}'s bufferView runs past the binary chunk")
            continue
        wh = _image_size(binary[start:start + min(size, 65536)])
        if wh is None:
            problems.append(f"image {i}: its {mime} header cannot be read")
            continue
        textures.append(wh)
        if max(wh) > MAX_TEXTURE_PX:
            problems.append(f"image {i} is {wh[0]}x{wh[1]} px (a side of {MAX_TEXTURE_PX} at most)")
    if triangles > MAX_TRIANGLES:
        problems.append(f"{triangles:,} triangles ({MAX_TRIANGLES:,} at most)")
    clips = [a.get("name") for a in _list(doc, "animations") if isinstance(a, dict) and isinstance(a.get("name"), str)]
    nodes = [n.get("name") for n in _list(doc, "nodes") if isinstance(n, dict) and isinstance(n.get("name"), str)]
    return {"triangles": triangles, "textures": textures, "clips": clips, "nodes": nodes, "problems": problems}


# ---------------------------------------------------------------- spirit.json


class _Check:
    def __init__(self, files: set[str]):
        self.files = files
        self.problems: list[str] = []

    def bad(self, where: str, text: str) -> None:
        self.problems.append(f"{SPIRIT_JSON}{' ' + where if where else ''}: {text}")

    def fields(self, where: str, value, schema: dict) -> None:
        if not isinstance(value, dict):
            self.bad(where, "is not an object")
            return
        for key, item in value.items():
            if key not in schema:
                self.bad(where, f"unknown key {key!r} (known: {', '.join(schema)})")
            else:
                self.field(f"{where}.{key}" if where else key, item, schema[key])

    def text(self, where: str, value, lines: bool = False) -> None:
        def one(w: str, v) -> None:
            if lines and isinstance(v, list):
                if not 1 <= len(v) <= MAX_BUBBLE_LINES:
                    self.bad(w, f"has {len(v)} lines (1 to {MAX_BUBBLE_LINES})")
                for i, line in enumerate(v):
                    one_line(f"{w}[{i}]", line)
            else:
                one_line(w, v)

        def one_line(w: str, v) -> None:
            if not isinstance(v, str) or not v.strip():
                self.bad(w, "is not a non-empty string")
            elif len(v) > MAX_TEXT_CHARS:
                self.bad(w, f"is {len(v)} characters ({MAX_TEXT_CHARS} at most)")

        if isinstance(value, dict):
            if not value:
                self.bad(where, "is an empty language table")
            for lang, v in value.items():
                if not LANG_RE.fullmatch(lang):
                    self.bad(where, f"{lang!r} is not a language code (ja, en, …)")
                one(f"{where}.{lang}", v)
        else:
            one(where, value)

    def field(self, where: str, value, kind) -> None:
        if isinstance(kind, tuple) and kind[0] in ("num", "int"):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            if kind[0] == "int":
                ok = ok and isinstance(value, int)
            if not ok or not kind[1] <= value <= kind[2]:
                self.bad(where, f"{value!r} is not a{'n integer' if kind[0] == 'int' else ' number'} from {kind[1]} to {kind[2]}")
        elif isinstance(kind, tuple) and kind[0] == "enum":
            if value not in kind[1]:
                self.bad(where, f"{value!r} is not one of {', '.join(kind[1])}")
        elif kind == "color":
            if not isinstance(value, str) or not COLOR_RE.fullmatch(value):
                self.bad(where, f"{value!r} is not a colour (#rrggbb)")
        elif isinstance(kind, tuple) and kind[0] == "vec3":
            if (not isinstance(value, list) or len(value) != 3
                    or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and kind[1] <= v <= kind[2] for v in value)):
                self.bad(where, f"is not three numbers from {kind[1]} to {kind[2]}")
        elif kind == "version":
            if value != 1:
                self.bad(where, f"{value!r} (1 is read)")
        elif kind == "text":
            self.text(where, value)
        elif kind == "lines":
            self.text(where, value, lines=True)
        elif kind == "skills":
            if not isinstance(value, list) or not 1 <= len(value) <= MAX_SKILLS:
                self.bad(where, f"is not a list of 1 to {MAX_SKILLS} skill names")
            else:
                for i, s in enumerate(value):
                    if not isinstance(s, str) or not SKILL_RE.fullmatch(s):
                        self.bad(f"{where}[{i}]", f"{s!r} is not a skill name")
        elif kind == "file":
            if value not in self.files:
                self.bad(where, f"{value!r} is not a .glb in this folder")
        elif kind == "clips":
            self.fields(where, value, {slot: "clipName" for slot in CLIP_SLOTS})
        elif kind == "clipName":
            if not isinstance(value, str) or not value:
                self.bad(where, "is not a clip name")
        elif kind == "material":
            self.fields(where, value, MATERIAL_FIELDS)
        elif kind == "outline":
            self.fields(where, value, OUTLINE_FIELDS)
        elif kind == "spirit":
            self.fields(where, value, SPIRIT_FIELDS)
            if isinstance(value, dict) and "file" not in value:
                self.bad(where, "has no file")
        elif kind == "parts":
            if not isinstance(value, list) or len(value) > MAX_PARTS:
                self.bad(where, f"is not a list of at most {MAX_PARTS} parts")
                return
            for i, part in enumerate(value):
                self.fields(f"{where}[{i}]", part, PART_FIELDS)
                if isinstance(part, dict):
                    f = part.get("file")
                    if "file" not in part:
                        self.bad(f"{where}[{i}]", "has no file")
                    elif isinstance(f, str) and not PART_FILE_RE.fullmatch(f):
                        self.bad(f"{where}[{i}].file", f"{f!r} is not a robot-*.glb or prop-*.glb")
        elif kind == "robot":
            self.fields(where, value, ROBOT_FIELDS)
        elif kind == "hide":
            if not isinstance(value, list):
                self.bad(where, "is not a list")
            else:
                for i, h in enumerate(value):
                    if h not in HIDE:
                        self.bad(f"{where}[{i}]", f"{h!r} is not one of {', '.join(HIDE)}")
        elif kind == "eyes":
            self.fields(where, value, EYES_FIELDS)
        elif kind == "effects":
            if not isinstance(value, dict):
                self.bad(where, "is not an object")
                return
            for name, conf in value.items():
                if name not in EFFECTS:
                    self.bad(where, f"unknown effect {name!r} (known: {', '.join(EFFECTS)})")
                else:
                    self.fields(f"{where}.{name}", conf, EFFECTS[name])
        elif kind == "bubble":
            self.fields(where, value, BUBBLE_FIELDS)
            if isinstance(value, dict) and "text" not in value:
                self.bad(where, "has no text")
        elif kind == "shouts":
            self.fields(where, value, SHOUTS_FIELDS)
            if isinstance(value, dict) and "texts" not in value:
                self.bad(where, "has no texts")
        elif kind == "shoutTexts":
            def shout_list(w: str, v) -> None:
                if not isinstance(v, list) or not 1 <= len(v) <= MAX_SHOUTS:
                    self.bad(w, f"is not a list of 1 to {MAX_SHOUTS} words")
                    return
                for i, s in enumerate(v):
                    self.text(f"{w}[{i}]", s)

            if isinstance(value, dict):
                for lang, v in value.items():
                    if not LANG_RE.fullmatch(lang):
                        self.bad(where, f"{lang!r} is not a language code (ja, en, …)")
                    shout_list(f"{where}.{lang}", v)
            else:
                shout_list(where, value)
        elif kind == "shoutStyle":
            self.fields(where, value, SHOUT_STYLE_FIELDS)


def check_spirit_json(value, files: set[str]) -> list[str]:
    """The problems in one spirit.json's parsed value; ``files`` are the .glb names in its folder."""
    check = _Check(files)
    if not isinstance(value, dict):
        return [f"{SPIRIT_JSON}: is not an object"]
    for key, item in value.items():
        if key not in TOP_FIELDS:
            check.bad("", f"unknown key {key!r} (known: {', '.join(TOP_FIELDS)})")
        else:
            check.field(key, item, TOP_FIELDS[key])
    if "version" not in value:
        check.bad("", "has no version (1)")
    return check.problems


# ---------------------------------------------------------------- one model, all models


def check_model(folder: Path) -> dict:
    """One model folder: {name, dir, ok, problems, notes, files: {name: {bytes, triangles, ...}}, skills, weight}."""
    problems: list[str] = []
    notes: list[str] = []
    files: dict[str, dict] = {}
    total = 0
    triangles = 0
    spec: dict = {}
    names = sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
    glbs = {n for n in names if n == SPIRIT_GLB or PART_FILE_RE.fullmatch(n)}
    for name in names:
        path = folder / name
        if path.is_symlink() or not path.is_file():
            notes.append(f"{name}: not read (not a plain file)")
            continue
        size = path.stat().st_size
        total += size
        if name not in glbs and name != SPIRIT_JSON:
            notes.append(f"{name}: not read (a model reads spirit.json, spirit.glb, robot-*.glb and prop-*.glb)")
            continue
        if size > MAX_FILE_BYTES:
            problems.append(f"{name}: {size:,} bytes ({MAX_FILE_BYTES // 1024 // 1024} MB at most)")
            continue
        if name in glbs:
            summary = summarize_glb(path.read_bytes())
            files[name] = {"bytes": size, **{k: summary[k] for k in ("triangles", "textures", "clips", "nodes")}}
            triangles += summary["triangles"]
            problems.extend(f"{name}: {p}" for p in summary["problems"])
    if total > MAX_MODEL_BYTES:
        problems.append(f"the folder holds {total:,} bytes ({MAX_MODEL_BYTES // 1024 // 1024} MB at most)")
    if triangles > MAX_TRIANGLES and not any("triangles" in p for p in problems):
        problems.append(f"{triangles:,} triangles in all ({MAX_TRIANGLES:,} at most)")
    json_path = folder / SPIRIT_JSON
    if SPIRIT_JSON in names and json_path.is_file() and not json_path.is_symlink():
        size = json_path.stat().st_size
        if size > MAX_JSON_BYTES:
            problems.append(f"{SPIRIT_JSON}: {size:,} bytes ({MAX_JSON_BYTES // 1024} KB at most)")
        else:
            try:
                spec = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                problems.append(f"{SPIRIT_JSON}: cannot be read as JSON ({type(exc).__name__})")
                spec = {}
            else:
                problems.extend(check_spirit_json(spec, glbs))
                if not isinstance(spec, dict):
                    spec = {}
    clips = (spec.get("spirit") or {}).get("clips") if isinstance(spec.get("spirit"), dict) else None
    spirit_file = (spec.get("spirit") or {}).get("file", SPIRIT_GLB) if isinstance(spec.get("spirit"), dict) else SPIRIT_GLB
    if isinstance(clips, dict) and spirit_file in files:
        for slot, clip in clips.items():
            if isinstance(clip, str) and clip not in files[spirit_file]["clips"]:
                problems.append(f"{SPIRIT_JSON} spirit.clips.{slot}: {spirit_file} has no clip {clip!r}"
                                f" (it has: {', '.join(files[spirit_file]['clips']) or 'none'})")
    if not glbs and not spec.get("effects"):
        problems.append("nothing to show: no spirit.glb, robot-*.glb or prop-*.glb, and no effects in spirit.json")
    skills = spec.get("skills") if isinstance(spec.get("skills"), list) else []
    weight = spec.get("weight", 1)
    return {"name": folder.name, "dir": str(folder), "ok": not problems, "problems": problems, "notes": notes,
            "files": files, "skills": [s for s in skills if isinstance(s, str)],
            "weight": weight if isinstance(weight, (int, float)) and not isinstance(weight, bool) else 1,
            "title": spec.get("name"), "spec": spec}


def scan(base: Path) -> dict:
    """Every model folder under base: {dir, models: [check_model …], skipped: [names], problems: [str]}."""
    out = {"dir": str(base), "models": [], "skipped": [], "problems": []}
    if not base.is_dir():
        return out
    folders = []
    for child in sorted(base.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name.startswith("."):
            continue
        if not NAME_RE.fullmatch(child.name):
            out["skipped"].append(child.name)
            continue
        folders.append(child)
    if len(folders) > MAX_MODELS:
        out["problems"].append(f"{len(folders)} models ({MAX_MODELS} at most): the first {MAX_MODELS} by name are read")
        folders = folders[:MAX_MODELS]
    out["models"] = [check_model(f) for f in folders]
    return out


#: The sources the page is given, in this order (a model of the person's may share a bundled one's name: both are kept).
SOURCES = ("bundled", "own")


def _scans() -> dict[str, dict]:
    return {"bundled": scan(bundled_dir()), "own": scan(own_dir())}


def listing() -> list[dict]:
    """The models the page may show, read now: only those the checks pass. Each is {id: "<source>/<name>", source, name,
    title, skills, weight, files: {file: {clips, nodes}}, spec: spirit.json as written}. A broken model is not listed
    (the doctor names it)."""
    out = []
    for source, found in _scans().items():
        for m in found["models"]:
            if not m["ok"]:
                continue
            out.append({"id": f"{source}/{m['name']}", "source": source, "name": m["name"], "title": m["title"],
                        "skills": m["skills"], "weight": m["weight"],
                        "files": {n: {"clips": f["clips"], "nodes": f["nodes"]} for n, f in m["files"].items()},
                        "spec": m["spec"]})
    return out


def model_file(model_id: str, file: str) -> tuple[int, bytes | str]:
    """(200, the bytes) of one .glb of a model the page was listed, matched by id and file name against a scan made
    now — never a path from the page; else (status, why)."""
    if not isinstance(model_id, str) or not isinstance(file, str):
        return 400, "id and file are required"
    source, _, name = model_id.partition("/")
    if source not in SOURCES or not NAME_RE.fullmatch(name):
        return 404, "no such model"
    model = next((m for m in _scans()[source]["models"] if m["name"] == name), None)
    if model is None or not model["ok"]:
        return 404, "no such model"
    if file not in model["files"]:
        return 404, "no such file in the model"
    path = Path(model["dir"]) / file
    if path.is_symlink() or not path.is_file():
        return 404, "no such file in the model"
    return 200, path.read_bytes()


def doctor_check() -> dict:
    """The doctor's row: {name, ok, detail}. ok is false while one of the person's models is broken (never chosen)."""
    bundled, own = scan(bundled_dir()), scan(own_dir())
    b_ok = sum(1 for m in bundled["models"] if m["ok"])
    mine = own["models"]
    broken = [m for m in bundled["models"] + mine if not m["ok"]]
    detail = (f"skill spirits: {b_ok} bundled; {sum(1 for m in mine if m['ok'])} of {len(mine)} of yours ok"
              f" ({own['dir']}{'' if Path(own['dir']).is_dir() else ', no such folder yet'})")
    for m in broken:
        detail += f"; {m['name']} not used: " + "; ".join(m["problems"][:3]) + (
            f" (and {len(m['problems']) - 3} more)" if len(m["problems"]) > 3 else "")
    if own["skipped"]:
        detail += f"; folders not read (name not A-Z a-z 0-9 _ -): {', '.join(own['skipped'])}"
    for p in own["problems"]:
        detail += f"; {p}"
    return {"name": "spirits", "ok": not broken, "detail": detail}


def words(value, language: str) -> str:
    """A model's words in ``language``, else ja, else the first written; a string is itself (the page's spiritWords)."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict) or not value:
        return ""
    got = value.get(language, value.get("ja", next(iter(value.values()))))
    return got if isinstance(got, str) else ""


def _report(model: dict, language: str = "en") -> list[str]:
    # spirit.json's name, in the report's language: the one place it is read (the page draws no name)
    title = words(model.get("title"), language)
    named = (f"（{title}）" if language == "ja" else f": {title}") if title else ""
    lines = [f"{'OK' if model['ok'] else 'NG'}  {model['name']}{named} ({model['dir']})"]
    for name, f in model["files"].items():
        lines.append(f"      {name}: {f['bytes']:,} bytes, {f['triangles']:,} triangles"
                     + (f", textures {', '.join(f'{w}x{h}' for w, h in f['textures'])}" if f["textures"] else "")
                     + (f", clips {', '.join(f['clips'])}" if f["clips"] else ""))
    lines += [f"      error: {p}" for p in model["problems"]]
    lines += [f"      note: {n}" for n in model["notes"]]
    return lines


def main(argv: list[str] | None = None) -> int:
    """Check model folders (a folder holding spirit.json or .glb files is one model; any other is a folder of
    models). With no folder: the bundled models and the person's own. Exit 1 when one is broken."""
    args = sys.argv[1:] if argv is None else argv
    targets = [Path(a) for a in args] or [bundled_dir(), own_dir()]
    models = []
    for t in targets:
        if t.is_dir() and any((t / n).is_file() for n in (SPIRIT_JSON, SPIRIT_GLB)) or any(
                PART_FILE_RE.fullmatch(p.name) for p in (t.iterdir() if t.is_dir() else [])):
            models.append(check_model(t))
        else:
            found = scan(t)
            if not t.is_dir():
                print(f"--  {t}: no such folder")
            for s in found["skipped"]:
                print(f"--  {t / s}: not read (name not A-Z a-z 0-9 _ -)")
            for p in found["problems"]:
                print(f"--  {t}: {p}")
            models += found["models"]
    language = _language()
    for m in models:
        print("\n".join(_report(m, language)))
    return 0 if all(m["ok"] for m in models) else 1


def _language() -> str:
    """The report's language: config.json's (and JUI_VIZ_LANGUAGE), as the view's words take it."""
    from . import i18n
    from .config import load_config

    try:
        return i18n.from_config(load_config()).language
    except Exception:   # a config the check cannot read never stops the check
        return i18n.DEFAULT_LANGUAGE


if __name__ == "__main__":
    raise SystemExit(main())
