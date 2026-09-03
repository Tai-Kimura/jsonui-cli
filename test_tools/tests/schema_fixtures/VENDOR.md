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
- Vendored at commit: `169ad16`

## `mock.schema.json` is not here

It is the one schema the CLI **ships**: `jsonui_test_cli/static/mock.schema.json`,
placed next to the mocks by `mock generate` so the `"$schema": "./.mock.schema.json"`
line in each mock resolves in an editor. Its copy of the re-vendor step is
`cp "$TR/schemas/mock.schema.json" test_tools/jsonui_test_cli/static/mock.schema.json`,
and `test_schema_drift.py` reads it through `generate.editor_schema_text()` —
the bytes a project receives are the bytes under test.

A test-only vendored copy would make three copies of one schema with a gate
between only two of them, which is the hole this whole directory exists to
close. There are exactly two: canonical (jsonui-test-runner) and shipped.

## Re-vendor procedure

When the canonical schemas change in jsonui-test-runner:

```bash
TR=/path/to/jsonui-test-runner
for s in actions screen-test flow-test results description; do
  cp "$TR/schemas/$s.schema.json" test_tools/tests/schema_fixtures/$s.schema.json
done
cp "$TR/schemas/mock.schema.json" test_tools/jsonui_test_cli/static/mock.schema.json
# update the "Vendored at commit" line above to `git -C "$TR" rev-parse HEAD`
python -m pytest test_tools/tests/test_schema_drift.py   # must pass, or a real drift exists
```

If `test_schema_drift.py` fails after re-vendoring, the canonical schema and the
validator constants genuinely disagree — fix `schema.py` / `report.py` (or the
schema) so the mirror holds, do not loosen the test.

Then confirm the two mock-schema copies are still one file:

```bash
dev-guide/ci/check-canonical-sync.py "$TR"
```

**That line is a convenience, not the guard.** A step in a procedure runs when
somebody remembers it, and the failure this closes is precisely somebody not
remembering: `skipRequestValidation` was added to the shipped copy alone and
would have been reverted by the next `cp` with every gate green, and the two
copies then drifted a SECOND time within minutes when the same sentence was
hand-written into both and differed by one `\u2014` escape. The gate is the
`Canonical sync` step in `ci.yml`, which checks this repo out and runs the same
script on every push. Running it here just saves you a round trip.
