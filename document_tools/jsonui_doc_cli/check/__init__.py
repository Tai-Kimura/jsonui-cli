"""Contract checking (docs ⇔ implementation) for jsonui-doc.

Modules:
- report:            result-JSON contract (schemaVersion 1), hashes, staleness
- runner:            executes declared checkers (subprocess, timeout, cwd=root)
- openapi_normalize: impl-side OpenAPI normalization (Pydantic v2 / 3.1 → comparable form)
- openapi_diff:      builtin:openapi-diff checker
- db_schema:         builtin:db-schema checker (comparator + doc parser + adapters)
"""
