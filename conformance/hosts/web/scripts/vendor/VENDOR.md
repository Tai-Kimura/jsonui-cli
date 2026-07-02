# Vendored jsonui-test-runner web driver

`types.ts`, `ActionExecutor.ts` and `AssertionExecutor.ts` are vendored
verbatim from the `jsonui-test-runner` repository
(`drivers/web/src/{models/types.ts, actions/ActionExecutor.ts,
assertions/AssertionExecutor.ts}`) so the conformance runner executes the
exact same action/assertion semantics as the production Playwright driver,
without requiring a sibling checkout at run time.

Local patches (kept intentionally minimal, re-apply when re-vendoring):

1. `AssertionExecutor.assertText`: the nested-input lookup excludes
   `input[type=checkbox]` / `input[type=radio]`. Their `value` attribute is
   a form-submission token (default `"on"`), not user-visible text, so a
   composite control (`<label id=...><input type=checkbox/><span>Text</span></label>`)
   must resolve `text` to the label's textContent. Driver bug filed
   upstream (see docs/bugs report); remove this patch once fixed.

2. Import specifiers rewritten for direct execution under Node's native
   TypeScript type stripping:
   - `from '../models/types'` → `from './types.ts'` (relative TS imports
     need explicit extensions outside a bundler).
   - Type-only imports (`Page`, `Locator` from `playwright`; `TestStep`
     from `./types.ts`) marked `import type` so the erased binding is not
     looked up at module-link time.

Patch 1 is the only behavioral change (a driver bug workaround); patch 2
is syntax-only. The `screenshot` action is intentionally *not*
routed through `ActionExecutor` by `scripts/run.ts` — the driver writes to
`<name>.png` relative to the process cwd, while conformance artifacts must
land in the artifacts directory; `run.ts` handles that one action itself
(same Playwright `page.screenshot` call).

To re-vendor: copy the three files from the jsonui-test-runner checkout
and re-apply the patches above.
