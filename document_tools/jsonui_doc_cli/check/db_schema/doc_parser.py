"""Parse docs/db/{db?}/*.json (schema-only OpenAPI + x-* extensions) into
the doc-side table model the comparator consumes.

Nullability convention: a column is nullable iff the property declares
``nullable: true``. The OpenAPI ``required`` array is NOT reused as a
NOT-NULL marker for DB models (it means "always present in payloads",
which existing DB docs do not maintain consistently).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocColumn:
    name: str
    openapi_type: str            # integer / number / string / boolean / array / object
    openapi_format: str | None = None
    nullable: bool = False
    primary_key: bool = False
    unique: bool = False
    auto_increment: bool = False
    indexed: bool = False
    enum_values: list | None = None
    enum_as_int: bool = False    # x-enum-values present → stored as int code
    foreign_key: tuple[str, str] | None = None   # (table, column)
    fk_enforced: bool = True     # x-foreign-key {enforced: false} = logical
                                 # reference only — no DB constraint expected
    db_type: str | None = None   # x-db-type → exact-match comparison
    max_length: int | None = None
    external_ref: str | None = None


@dataclass
class DocIndex:
    columns: list[str]
    unique: bool = False
    name: str | None = None


@dataclass
class DocTable:
    name: str
    source_file: Path
    columns: dict[str, DocColumn] = field(default_factory=dict)
    indexes: list[DocIndex] = field(default_factory=list)


def _snake_case(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _parse_fk(raw) -> tuple[str, str] | None:
    if isinstance(raw, dict):
        table, column = raw.get("table"), raw.get("column")
        if table and column:
            return (str(table), str(column))
        return None
    if isinstance(raw, str) and raw.count(".") == 1:
        table, column = raw.split(".")
        return (table, column)
    return None


def _fk_enforced(raw) -> bool:
    """The dict form may declare {"enforced": false}: the reference is
    documentation/ERD-only and the DB is not expected to hold a constraint."""
    if isinstance(raw, dict):
        return raw.get("enforced") is not False
    return True


def _first_object_schema(schemas: dict) -> tuple[str, dict] | None:
    """Pick the table schema: first non-enum object schema in the file."""
    for name, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        if "enum" in schema:
            continue
        if schema.get("type", "object") == "object" or "properties" in schema:
            return name, schema
    return None


def parse_table_file(path: Path) -> DocTable | None:
    """Parse one docs/db table JSON. Returns None for non-swagger files."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if "openapi" not in data and "swagger" not in data:
        return None
    if data.get("paths"):
        return None  # has API paths → not a DB model file

    schemas = (data.get("components") or {}).get("schemas") or {}
    picked = _first_object_schema(schemas)
    if picked is None:
        return None
    schema_name, schema = picked

    info = data.get("info") or {}
    table_name = info.get("x-table-name") or _snake_case(schema_name)
    table = DocTable(name=str(table_name), source_file=path)

    # Enum companion schemas in the same file (for x-enum-values lookup)
    enum_schemas = {n: s for n, s in schemas.items()
                    if isinstance(s, dict) and "enum" in s}

    for prop_name, prop in (schema.get("properties") or {}).items():
        if not isinstance(prop, dict):
            continue
        resolved = prop
        # local $ref to an enum companion schema
        ref = prop.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            target = schemas.get(ref.rsplit("/", 1)[-1])
            if isinstance(target, dict):
                resolved = {**target, **{k: v for k, v in prop.items()
                                         if k != "$ref"}}
        enum_values = resolved.get("enum")
        enum_as_int = bool(resolved.get("x-enum-values"))
        if enum_values is None and ref:
            target = enum_schemas.get(ref.rsplit("/", 1)[-1])
            if target:
                enum_values = target.get("enum")
                enum_as_int = bool(target.get("x-enum-values"))

        col = DocColumn(
            name=prop_name,
            openapi_type=str(resolved.get("type", "string")),
            openapi_format=resolved.get("format"),
            nullable=bool(resolved.get("nullable", False)),
            primary_key=bool(resolved.get("x-primary-key", False)),
            unique=bool(resolved.get("x-unique", False)),
            auto_increment=bool(resolved.get("x-auto-increment", False)),
            indexed=bool(resolved.get("x-index", False)),
            enum_values=list(enum_values) if enum_values else None,
            enum_as_int=enum_as_int,
            foreign_key=_parse_fk(resolved.get("x-foreign-key")),
            fk_enforced=_fk_enforced(resolved.get("x-foreign-key")),
            db_type=resolved.get("x-db-type"),
            max_length=resolved.get("maxLength"),
            external_ref=resolved.get("x-external-ref"),
        )
        table.columns[prop_name] = col

    for idx in schema.get("x-indexes", []) or []:
        if isinstance(idx, dict) and isinstance(idx.get("columns"), list):
            table.indexes.append(DocIndex(
                columns=[str(c) for c in idx["columns"]],
                unique=bool(idx.get("unique", False)),
                name=idx.get("name"),
            ))
    return table


def parse_db_docs(db_dir: Path) -> dict[str, DocTable]:
    """Parse every table JSON directly inside db_dir (non-recursive:
    in the multi-DB layout each database directory is parsed separately)."""
    tables: dict[str, DocTable] = {}
    for f in sorted(db_dir.glob("*.json")):
        if f.name.startswith("."):
            continue
        table = parse_table_file(f)
        if table is not None:
            tables[table.name] = table
    return tables
