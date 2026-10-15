# Vendored jsonui-test-runner web driver

`types.ts`, `ActionExecutor.ts`, `AssertionExecutor.ts`,
`reasonHistory.ts`, `StateProvider.ts` and `visibility.ts` are vendored
from the `jsonui-test-runner` repository (`drivers/web/src/{models/types.ts,
actions/ActionExecutor.ts, assertions/AssertionExecutor.ts,
assertions/reasonHistory.ts, runner/StateProvider.ts, visibility.ts}`) so the
conformance runner executes the exact same action/assertion semantics as
the production Playwright driver, without requiring a sibling checkout at
run time.

Re-vendored 2026-10-15 from web driver 1.14.0 (release/next 2d2c9c7): `types.ts`
now carries `caseIsolation` (the runner that reads it is not vendored; conformance
does not use it). Before that, the same day from branch feat/hidden-assertion (on the
assertion-timeout reason history): the `hidden` assertion and `when: { hidden }`
(visibility.ts isHidden), and a timed-out assertion names every reason it waited
through (reasonHistory.ts). The re-vendor before, 2026-10-14 from 6b2c118 (1.13.0): `visible` /
`notVisible` / scrollUntilVisible's stop condition mean in the viewport
(the new `visibility.ts`), scrollUntilVisible without a `container` scrolls
the target's nearest scrolling ancestor, and selectOption's selector
precedence is index → value → label. The previous re-vendor (2026-07-24,
06 variant-file track) picked up `setViewport` / `setOrientation`.

Local patches (kept intentionally minimal, re-apply when re-vendoring):

1. Import specifiers rewritten for direct execution under Node's native
   TypeScript type stripping:
   - `from '../models/types'` → `from './types.ts'`,
     `from '../runner/StateProvider'` → `from './StateProvider.ts'`,
     `from '../visibility'` → `from './visibility.ts'`, and
     `from './reasonHistory'` → `from './reasonHistory.ts'`
     (relative TS imports need explicit extensions outside a bundler).
   - Type-only imports (`Page`, `Locator` from `playwright`; `TestStep`;
     `StateProvider`) marked `import type` so the erased binding is not
     looked up at module-link time.

2. `ActionExecutor`: the `import { TestLoader } from '../runner/TestLoader'`
   dependency is dropped and its single use
   (`TestLoader.getBasePath() ?? process.cwd()` — runner-relative media
   path resolution for `addMedia`) replaced with `process.cwd()`.
   Conformance fixtures never use runner-relative media paths.

`pngjs` / `pixelmatch` (AssertionExecutor's visual-diff assert) are
declared as host devDependencies so the vendored module links even though
conformance drives its visual pipeline through `run.ts` screenshots.

The `screenshot` action is intentionally *not* routed through
`ActionExecutor` by `scripts/run.ts` — the driver writes to `<name>.png`
relative to the process cwd, while conformance artifacts must land in the
artifacts directory; `run.ts` handles that one action itself (same
Playwright `page.screenshot` call).

To re-vendor: copy the six files from the jsonui-test-runner checkout
and re-apply the patches above.
