# Vendored jsonui-test-runner web driver

`types.ts`, `ActionExecutor.ts`, `AssertionExecutor.ts`,
`reasonHistory.ts`, `StateProvider.ts`, `StateBridge.ts` and `visibility.ts`
are vendored from the `jsonui-test-runner` repository
(`drivers/web/src/{models/types.ts, actions/ActionExecutor.ts,
assertions/AssertionExecutor.ts, assertions/reasonHistory.ts,
runner/StateProvider.ts, runner/StateBridge.ts, visibility.ts}`) so the
conformance runner executes the exact same action/assertion semantics as
the production Playwright driver, without requiring a sibling checkout at
run time.

Checked 2026-10-16 against web driver 1.15.0 (088c2d3, afterLaunch + the
payload's writtenAt): the seven vendored files are byte-for-byte what a1a7d9c
gave (the change is in InitialState.ts / JsonUITestRunner.ts, not vendored);
scripts/run.ts writes writtenAt itself.
Re-vendored 2026-10-16 from web driver feat/test-state-launch (a1a7d9c, the
1.15.0 train): `StateBridge.ts` is new (readBridge, the state-path rule) and
`StateProvider.ts` now carries `BridgeStateProvider`, the default `state`
provider reading `window.__JSONUI_STATE__[screenId]` (run.ts points it at
each fixture's staged screen id — INTERACTIVE_HOST_CONTRACT.md §6);
`AssertionExecutor.ts`'s `state` uses its pending / truncated outcomes;
`types.ts` loses `FlowInitialState.screen`. `ActionExecutor.ts`,
`reasonHistory.ts` and `visibility.ts` are unchanged from 1.14.2.
Before that, 2026-10-15 from web driver 1.14.2 (d6eb14b): a Playwright timeout is
recognised by its name (`isTimeoutError` in `visibility.ts`), so `ActionExecutor.ts`
no longer imports `errors` from playwright. Before that, the same day from web driver 1.14.1 (8641d1b): `visibility.ts` bounds every
look at an element (`probe`, `DETACHED`, `viewportState`), `AssertionExecutor.ts`
reads a detached element as absent within the assert's timeout, and
`ActionExecutor.ts` gives every locator action the step's timeout
(`actionabilityReason`). Before that, the same day from web driver 1.14.0 (release/next 2d2c9c7): `types.ts`
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
     `from '../visibility'` → `from './visibility.ts'`,
     `from './reasonHistory'` → `from './reasonHistory.ts'`, and (in
     `StateProvider.ts`) `from './StateBridge'` → `from './StateBridge.ts'`
     (relative TS imports need explicit extensions outside a bundler).
   - Type-only imports (`Page`, `Locator` from `playwright`; `TestStep`;
     `StateProvider`; `StateLookup`) marked `import type` (or an inline
     `type` specifier) so the erased binding is not looked up at
     module-link time.
   - Node's type stripping also rejects TypeScript parameter properties;
     the driver itself avoids them in the vendored files (a1a7d9c), so this
     needs no patch — keep it that way.

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

To re-vendor: copy the seven files from the jsonui-test-runner checkout
and re-apply the patches above.
