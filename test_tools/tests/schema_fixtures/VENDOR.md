# Vendored canonical test schemas (test-only fixtures)

These are **verbatim copies** of the canonical JSON Schemas that live in the
`jsonui-test-runner` repository (`schemas/`). They are the source of truth for
test-file shape; the `jsonui_test_cli` validator re-encodes the same rules as
Python constants (`jsonui_test_cli/schema.py`, `jsonui_test_cli/report.py`).

## Why they are here

The validator (jsonui-cli) and the schemas (jsonui-test-runner) are a cross-repo
mirror. Nothing at runtime reads a schema file — validation is driven entirely by
the Python constants — so the two can silently drift apart. `test_schema_drift.py`
loads these vendored copies and asserts the constants still match the schemas,
turning drift into a CI failure.

- **Test-only.** These files are NOT packaged (`pyproject` package-data is
  `static/*` only) and NOT read at runtime. Vendoring them keeps D2 "case A"
  intact (the shipped CLI has no schema-file dependency).
- **Not the canonical copy.** Never hand-edit these to make a test pass. The
  canonical schemas live in `jsonui-test-runner/schemas/`; edit there, then
  re-vendor.

## Source provenance

- Source repo: `Tai-Kimura/jsonui-test-runner`
- Source path: `schemas/{actions,screen-test,flow-test,results,description}.schema.json`
- Vendored at commit: `322a227d05c929f98c4d2d0119b5d8f5c113df0d`

## Re-vendor procedure

When the canonical schemas change in jsonui-test-runner:

```bash
TR=/path/to/jsonui-test-runner
for s in actions screen-test flow-test results description; do
  cp "$TR/schemas/$s.schema.json" test_tools/tests/schema_fixtures/$s.schema.json
done
# update the "Vendored at commit" line above to `git -C "$TR" rev-parse HEAD`
python -m pytest test_tools/tests/test_schema_drift.py   # must pass, or a real drift exists
```

If `test_schema_drift.py` fails after re-vendoring, the canonical schema and the
validator constants genuinely disagree — fix `schema.py` / `report.py` (or the
schema) so the mirror holds, do not loosen the test.
