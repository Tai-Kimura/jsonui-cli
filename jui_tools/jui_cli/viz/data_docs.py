"""The data server (requester, 10-19; 2.3.5): a JsonUI room's API and DB specifications, for its rack up close.

Found the way `jsonui-doc generate` finds them (test_doc/generator.py): ``docs/api`` and ``docs/db`` beside the specs
(here: under the room's root and under each app's config folder), every ``*.json`` under them that
``is_swagger_file`` takes (OpenAPI 3 / Swagger 2); a file with paths is an API document, one without (components only)
a schema document; ``docs/db/<name>/…`` is a database of its own. document_tools' own helpers decide (has_api_paths,
the ER diagram's Mermaid builder; is_swagger_file's rule is applied to bytes this module read itself, test-pinned to
the same answers), reached through jui's routes to document_tools (core/document_tools_import) — one copy.

Every file is opened once, one path part at a time from the room's real root with O_NOFOLLOW, and the open fd is what
is checked (a regular file, under the cap) and read (dd's review, 10-19: a symlink swapped in between a check of the
path and an open of it let a file from outside the room through, and a file over the cap).

What the room says without reading a document: ``counts`` (how many API and schema documents there are), cached by
the files' names, sizes and times, for the page to put the rack there or not. What it reads: ``read`` — only when the
rack is pressed (POST /api/data-docs), never in a snapshot or an export — with caps on the number and the size of the
files. Only files under those folders: the client never names a path, and a folder or a file whose real path leaves
the room (a symlink, ``..``) is not read.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

MAX_FILES = 200            # documents per room
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 8_000_000
KINDS = ("api", "db")

_DOC: dict = {}


def _doc():
    """document_tools' test_doc helpers (swagger, schema, erd), or None when it cannot be reached."""
    if "mods" not in _DOC:
        from ..core.document_tools_import import load_document_tools_module
        mods = {n: load_document_tools_module(f"test_doc.html.{n}")[0] for n in ("swagger", "schema", "erd")}
        _DOC["mods"] = mods if all(mods.values()) else None
    return _DOC["mods"]


def _open_inside(root: Path, rel: Path) -> int | None:
    """An fd of ``root / rel`` opened one part at a time from the room's real root, each part with O_NOFOLLOW (dd's
    review, 10-19: a check on the path and a later open of the same path could be raced by a symlink swapped in
    between). A symlink anywhere below the root, a part that is not there or the wrong kind: None."""
    flags_dir = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        fd = os.open(str(Path(root).resolve()), flags_dir)
    except OSError:
        return None
    try:
        parts = Path(rel).parts
        for k, part in enumerate(parts):
            if part in ("", ".", ".."):
                return None
            last = k == len(parts) - 1
            nxt = os.open(part, (os.O_RDONLY | os.O_NOFOLLOW) if last else flags_dir, dir_fd=fd)
            os.close(fd)
            fd = nxt
        out, fd = fd, None
        return out
    except OSError:
        return None
    finally:
        if fd is not None:
            os.close(fd)


TOO_BIG = object()   # _read_capped's answer for a file over its cap (counted as skipped)


def _read_capped(root: Path, rel: Path, cap: int):
    """The bytes of a regular file under the room, read through the fd _open_inside gave (fstat'ed: a regular file, not
    over ``cap``; then at most cap + 1 bytes read, so a file grown in the meantime is refused too). TOO_BIG for a file
    over the cap, None for anything else that is not read."""
    fd = _open_inside(root, rel)
    if fd is None:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None
        if st.st_size > cap:
            return TOO_BIG
        chunks, n = [], 0
        while n <= cap:
            b = os.read(fd, min(1 << 16, cap + 1 - n))
            if not b:
                break
            chunks.append(b)
            n += len(b)
        return TOO_BIG if n > cap else b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


def _swagger(raw: bytes | None) -> dict | None:
    """document_tools' is_swagger_file + parse_swagger_file over bytes already read (they open the path again): a
    JSON object with "openapi" or "swagger". test_viz_data_docs keeps the two answers the same."""
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) and ("openapi" in data or "swagger" in data) else None


def _inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError):
        return False


def doc_dirs(project) -> list[tuple[str, Path, Path]]:
    """(kind, folder, the root it belongs to) for each docs/api and docs/db of the room (its root, then each app's
    config folder), real folders whose real path stays inside the room."""
    roots: list[Path] = []
    for r in [Path(project.root), *(Path(s.root) for s in getattr(project, "sources", []))]:
        if r not in roots:
            roots.append(r)
    out: list[tuple[str, Path, Path]] = []
    seen: set[Path] = set()
    for r in roots:
        for kind in KINDS:
            d = r / "docs" / kind
            if not d.is_dir() or not _inside(d, Path(project.root)):
                continue
            real = d.resolve()
            if real in seen:
                continue
            seen.add(real)
            out.append((kind, d, r))
    return out


def _files(project) -> list[tuple[str, Path, Path, Path]]:
    """(category, file, its docs folder, the file relative to the room's real root — what is opened, through
    _open_inside): the *.json under each folder, sorted, inside it, under the size cap."""
    out: list[tuple[str, Path, Path, Path]] = []
    real_root = Path(project.root).resolve()
    for kind, d, _root in doc_dirs(project):
        try:
            d_rel = d.resolve().relative_to(real_root)
        except (OSError, ValueError):
            continue
        for f in sorted(d.rglob("*.json")):
            if len(out) >= MAX_FILES:
                return out
            if not f.is_file() or not _inside(f, d):
                continue
            try:
                if f.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            rel = f.parent.relative_to(d)
            category = f"db/{rel.parts[0]}" if kind == "db" and rel.parts else kind   # generator.py's multi-DB rule
            out.append((category, f, d, d_rel / f.relative_to(d)))
    return out


def _signature(files) -> tuple:
    sig = []
    for _c, f, _d, _rel in files:
        try:
            st = f.stat()
            sig.append((str(f), st.st_size, st.st_mtime_ns))
        except OSError:
            pass
    return tuple(sig)


def counts(project, cache: dict | None = None) -> dict:
    """{"api": API documents, "db": schema documents} — 0 / 0 when there are none or document_tools is not found.
    ``cache`` (a dict the caller keeps) skips the parse while no file changed."""
    mods = _doc()
    files = _files(project)
    if mods is None or not files:
        return {"api": 0, "db": 0}
    sig = _signature(files)
    if cache is not None and cache.get("sig") == sig:
        return dict(cache["counts"])
    n, total, root = {"api": 0, "db": 0}, 0, Path(project.root)
    for _category, _f, _d, rel in files:
        raw = _read_capped(root, rel, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total)) if total < MAX_TOTAL_BYTES else None
        raw = None if raw is TOO_BIG else raw
        total += len(raw) if raw else 0
        data = _swagger(raw)
        if data is not None:
            n["api" if mods["schema"].has_api_paths(data) else "db"] += 1
    if cache is not None:
        cache.update(sig=sig, counts=dict(n))
    return n


# ---------------------------------------------------------------- what the page shows

def _s(v, n: int = 2000) -> str:
    return v[:n] if isinstance(v, str) else ""


def _column(name: str, prop: dict, required: bool) -> dict:
    """One column as schema.py's _render_property_row shows it (Field, Type, Description, Default, Key, Constraints,
    Notes), as text; test_viz_data_docs compares it with that row."""
    p = prop if isinstance(prop, dict) else {}
    type_str = str(p.get("type", "any"))
    if p.get("format"):
        type_str = f"{type_str} ({p['format']})"
    if p.get("nullable"):
        type_str += " | null"
    if p.get("x-db-type"):
        type_str += f" = {p['x-db-type']}"
    default = "-"
    if "default" in p:
        d = p["default"]
        default = "null" if d is None else str(d).lower() if isinstance(d, bool) else str(d)
    keys = []
    if p.get("x-primary-key"):
        keys.append("PRI")
    if p.get("x-unique"):
        keys.append("UNI")
    if p.get("x-foreign-key"):
        fk = p["x-foreign-key"]
        if isinstance(fk, dict):
            ref = f"{fk.get('table', '')}.{fk.get('column', '')}" + (" (logical)" if fk.get("enforced") is False else "")
        else:
            ref = str(fk)
        keys.append(f"FK {ref}")
    if p.get("x-index"):
        keys.append("IDX")
    if p.get("x-external-ref"):
        keys.append(f"EXT {p['x-external-ref']}")
    cons = []
    if required:
        cons.append("required")
    if p.get("x-auto-increment"):
        cons.append("auto_increment")
    for key, label in (("maxLength", "maxLength"), ("minLength", "minLength"), ("minimum", "min"), ("maximum", "max")):
        if key in p:
            cons.append(f"{label}: {p[key]}")
    if "pattern" in p:
        cons.append(f"pattern: {p['pattern']}")
    if "enum" in p and isinstance(p["enum"], list):
        cons.append(f"enum: [{', '.join(str(v) for v in p['enum'])}]")
    notes = p.get("x-notes")
    notes_list = [str(x) for x in notes] if isinstance(notes, list) else [str(notes)] if notes is not None else []
    return {"name": _s(name, 200), "type": _s(type_str, 300), "description": _s(p.get("description")), "default": _s(default, 300),
            "keys": [_s(k, 300) for k in keys], "constraints": [_s(c, 300) for c in cons], "notes": [_s(x, 500) for x in notes_list]}


def _table(name: str, schema: dict) -> dict:
    s = schema if isinstance(schema, dict) else {}
    if s.get("type") == "string" and "enum" in s:   # an enum schema, as schema.py's _render_enum_schema
        return {"name": _s(name, 200), "description": _s(s.get("description")), "enum": [_s(str(v), 200) for v in s.get("enum") or []][:200], "columns": []}
    req = s.get("required") if isinstance(s.get("required"), list) else []
    props = s.get("properties") if isinstance(s.get("properties"), dict) else {}
    return {"name": _s(name, 200), "description": _s(s.get("description")),
            "columns": [_column(k, v, k in req) for k, v in list(props.items())[:300]]}


_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def _endpoints(data: dict) -> list[dict]:
    out = []
    paths = data.get("paths") if isinstance(data.get("paths"), dict) else {}
    for path, item in list(paths.items())[:500]:
        if not isinstance(item, dict):
            continue
        shared = item.get("parameters") if isinstance(item.get("parameters"), list) else []
        for m in _METHODS:
            op = item.get(m)
            if not isinstance(op, dict):
                continue
            params = [x for x in shared + (op.get("parameters") if isinstance(op.get("parameters"), list) else []) if isinstance(x, dict)]
            out.append({"method": m.upper(), "path": _s(path, 500), "summary": _s(op.get("summary"), 500), "description": _s(op.get("description")),
                        "operationId": _s(op.get("operationId"), 200), "tags": [_s(t, 100) for t in op.get("tags") or [] if isinstance(t, str)][:20],
                        "parameters": params[:100], "requestBody": op.get("requestBody") if isinstance(op.get("requestBody"), dict) else None,
                        "responses": op.get("responses") if isinstance(op.get("responses"), dict) else {}})
    return out


def read(project) -> dict:
    """The rack's documents: {"api": [document], "db": [database], "skipped": n}. A document: its file (relative to the
    room), title, version, description, endpoints and its schemas; a database: its name, its ER diagram (document_tools'
    Mermaid builder over the database's schema documents) and its tables. Raises nothing."""
    mods = _doc()
    out: dict = {"api": [], "db": [], "skipped": 0}
    if mods is None:
        out["error"] = "document_tools が見つかりません"
        return out
    total = 0
    groups: dict[str, list[dict]] = {}
    root = Path(project.root).resolve()
    for category, f, _d, rel_file in _files(project):
        raw = _read_capped(root, rel_file, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total)) if total < MAX_TOTAL_BYTES else TOO_BIG
        if raw is TOO_BIG:
            out["skipped"] += 1
            continue
        data = _swagger(raw)
        if data is None:
            continue
        total += len(raw)
        rel = rel_file.as_posix()
        info = data.get("info") if isinstance(data.get("info"), dict) else {}
        schemas = (data.get("components") or {}).get("schemas") if isinstance(data.get("components"), dict) else None
        schemas = schemas if isinstance(schemas, dict) else (data.get("definitions") if isinstance(data.get("definitions"), dict) else {})
        if mods["schema"].has_api_paths(data):
            out["api"].append({"file": rel, "title": _s(info.get("title"), 300) or f.stem, "version": _s(str(info.get("version", "")), 100),
                               "description": _s(info.get("description"), 4000), "endpoints": _endpoints(data), "schemas": schemas})
        else:
            groups.setdefault(category, []).append({"name": _s(info.get("title"), 300) or f.stem, "swagger_data": data, "file": rel})
    for category, files in groups.items():
        try:
            erd = mods["erd"]._build_mermaid_erd(files)
        except Exception:  # a schema the builder cannot read: the tables still show
            erd = ""
        tables = []
        for sf in files:
            comps = sf["swagger_data"].get("components") if isinstance(sf["swagger_data"].get("components"), dict) else {}
            for name, schema in (comps.get("schemas") or {}).items() if isinstance(comps.get("schemas"), dict) else []:
                tables.append({**_table(name, schema), "file": sf["file"]})
        out["db"].append({"name": category[3:] if category.startswith("db/") else category, "category": category,
                          "erd": erd if isinstance(erd, str) and len(erd) <= 50_000 else "", "tables": tables})
    return out


def payload(project) -> bytes:
    return json.dumps(read(project), ensure_ascii=False).encode("utf-8")
