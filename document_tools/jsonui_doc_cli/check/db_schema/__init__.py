"""builtin:db-schema — real database schema ⇔ docs/db/ comparison.

Architecture (plan 02 §1): dialect differences live in the dump adapters
and the type-family table; the comparator is one pure implementation that
only ever sees the normalized schema JSON. The comparator + a project
`dump_command` work with ZERO extra dependencies; the live-connection
adapter needs the optional `sqlalchemy` extra (review §3-6).
"""

from .checker import DbSchemaError, run_db_schema_check

__all__ = ["DbSchemaError", "run_db_schema_check"]
