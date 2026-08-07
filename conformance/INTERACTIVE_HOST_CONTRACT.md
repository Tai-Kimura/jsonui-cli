# Interactive fixture host contract (conformanceState)

Contract between the generated `class: interactive` conformance fixtures and
every platform host (web today; iOS / Android in the next round). A host
that implements **the one mechanism described here** runs *all* interactive
fixtures — per-fixture host code is forbidden by design (host effort must
not scale with fixture count).

Hand-maintained. Generator side: `jui_tools/jui_cli/conformance/interactive_rules.py`.
Web reference implementation: `conformance/hosts/web/src/conformanceState.tsx`.

## What an interactive fixture looks like

Layout (`fixtures/<Section>/<attr>__<case>.layout.json`):

```json
{
  "type": "View", "id": "root", "orientation": "vertical",
  "data": [
    { "name": "conformanceResult", "class": "String", "defaultValue": "ready" }
  ],
  "child": [
    { "type": "Button", "id": "target", "text": "Sample", "onclick": "conformanceFire" },
    { "type": "Label", "id": "mirror", "text": "@{conformanceResult}" }
  ]
}
```

Manifest entry (`manifest.fixtures[]`, `class: "interactive"`):

```json
{
  "id": "common/onclick__callback_fire",
  "class": "interactive",
  "state": {
    "vars":     [ { "name": "conformanceResult", "class": "String", "defaultValue": "ready" } ],
    "handlers": [ { "name": "conformanceFire", "set": { "var": "conformanceResult", "value": "fired" } } ]
  },
  "promotedFrom": "callback"
}
```

The test JSON is a plain jsonui-test-runner screen test; the runner only
needs the actions/assertions it already has (`tap`, `input`, `longPress`,
`selectOption`, `waitFor`, `text`/`visible`/`notVisible`). **No schema
extension was needed.**

## The contract (3 requirements)

A platform host must provide, once, a generic state provider that for any
fixture:

1. **Initial values** — provision every `state.vars` entry with its
   `defaultValue` before first render. All runtimes already do this from
   the layout `data` section; use the production path:
   - iOS: `DynamicView.mergeDataDefaults` (SwiftJsonUI, SwiftUI dynamic mode)
   - Android: `DynamicView.applyDataSectionDefaults` (KotlinJsonUI dynamic)
   - web: `create<View>Data()` emitted by rjui codegen (what the web host seeds
     into React state)

2. **Handlers** — for every `state.handlers` entry, register a closure under
   `name` in the same state/data dictionary the runtime resolves `@{name}` /
   selector-format handler references from. **Any callback payload is
   ignored** — this keeps the contract identical for `() -> Void`,
   `(T) -> Void` and `(id, T) -> Void` shaped callbacks on every platform:
   - iOS: closures in the `data` dict; `DynamicEventHelper.call` /
     `callWithValue` already resolve by name and try the three signatures.
   - Android: closures in the `data` map; `ModifierBuilder.resolveEventHandler`
     resolves both `@{name}` and bare-selector strings.
   - web: `StateHost` assigns `() => setData(...)` closures into the data prop.

   A handler declares exactly one of two operation kinds:

   - `set: { var, value }` — invoking the closure sets the single variable
     `set.var` to the literal string `set.value` and triggers re-render of
     everything bound to it.
   - `embed: { id, action, screen?, params? }` — invoking the closure drives
     the private stack of the mounted isolated embed whose embedId is `id`,
     looked up through the library's `EmbedNavigatorRegistry` (iOS
     `EmbedNavigatorRegistry.shared.navigator(for:)`, Android
     `EmbedNavigatorRegistry.get`, web template v2 `getEmbedNavigator`).
     `action: "push"` pushes `screen` (with optional flat string `params`);
     `action: "pop"` pops one entry (bounded at the embed root by the
     navigator itself). No mounted embed with that id → no-op.

3. **Two-way write-back** — vars bound into input components
   (`text: "@{var}"` on TextField/TextView) must update when the user (or
   the test driver's `input` action) edits the field, so mirror Labels bound
   to the same var follow:
   - iOS: provide the var as a `SwiftUI.Binding` (per `DynamicBindingHelper.string`).
   - Android: route edits through `DataBindingContext.updateValue`.
   - web: rjui emits `on<Var>Change` dispatch; the host injects the default
     write-back setter exactly like `hook_generator.rb` would (only when the
     generated data shape has the `on<Var>Change` key left undefined).

Determinism rules: no randomness, no time, no network — with the single
exception carved out in §5, whose whole purpose is to keep those three
properties while photographing a state that only exists during a request.
All state values are
strings (`class: "String"`) in v2 — the most portable `defaultValue`
representation across the three runtimes. The state vocabulary is fixed:
`conformanceText`, `conformanceResult`, `conformanceVisibility` vars, the
`conformanceFire` handler (`set` kind), and the `confPush` / `confPop`
handlers (`embed` kind, Embed isolated fixtures).

## 4. Collection data supply (F4 Phase 2 prerequisite, 2026-08-02)

Static Collection fixtures need item data to render cells, and the four
render paths consume it differently — the only declaration channel all four
share is the **layout root `data` section**, so that is the contract:

```json
"data": [
  { "name": "items", "class": "CollectionDataSource", "defaultValue": [
      { "title": "Alpha" }, { "title": "Beta" }, { "title": "Gamma" }
  ] }
]
```

`defaultValue` accepts two shapes:

- **shorthand** — a bare array of cell dictionaries: one section holding
  exactly these cells (the form the fixture generator emits);
- **explicit** — `{"sections": [{"cell": <name?>, "cells": [ {...} ]}, ...]}`
  for multi-section fixtures. The renderer takes each section's cell view
  name from the Collection node's own `sections` declaration; a `cell` name
  here is carried only for data-source fidelity.

Host obligation per path (the host plays the consumer ViewModel's role):

- **iOS dynamic**: `CollectionConverter` resolves `items: "@{prop}"` via
  `data[prop] as? CollectionDataSource` — a raw defaultValue dictionary never
  survives that cast, so the host must materialize a real
  `SwiftJsonUI.CollectionDataSource` and pass it in the external data (which
  overrides `mergeDataDefaults`). Implemented: `ConformanceHost`
  `ConformanceStateProvider.swift` requirement 4 (2026-08-02).
- **Android dynamic**: KotlinJsonUI consumes the `sections`/`cellTemplate`
  route; supply status pending the four-path unification (31 F4 Phase 2).
- **iOS / Android codegen**: generated Data classes default-initialize from
  the layout `data` declaration (array-default support unverified — 31 F4
  Phase 2 scope).

This channel is independent of the manifest `state` block (Collection
fixtures are static, not interactive); it exists for any fixture whose
layout declares a `CollectionDataSource`-classed data entry.

## 5. Deterministic network — the two reserved hosts (plan 51-H, 2026-08-07)

Two attribute states are defined by what a request is doing: `errorImage`
(the request failed) and `loadingImage` (the request has not finished). The
ERROR face was already deterministic — `conformance.invalid` can never
resolve (RFC 2606), so Android fails it synchronously in an OkHttp
application interceptor, before any resolver is asked, and the environment
gets no say in *when*. The LOADING face was not, and `rules.py` recorded it
as unphotographable "however the fixture is shaped": a still capture has no
duration, so by the time the shutter opens the request has either not
started or already failed.

**That claim is true only while the request is allowed to finish.** The move
this contract makes is to stop treating LOADING as a state of time and make
it a state of rest: a request that never completes and never fails leaves the
loading face on screen for the entire run. Everything downstream — settle
logic, capture-until-stable, baselines, control diffs — then works unchanged,
because it is photographing a resting state like every other fixture.

### The contract

1. **Two reserved host names, both under `.invalid`** so no conformance
   request can ever leave the machine:

   | host | host obligation | face under test |
   |---|---|---|
   | `conformance.invalid` | fail the request **synchronously** | ERROR |
   | `pending.invalid` | **never complete and never fail** it | LOADING |

2. **`pending.invalid` must be matched before any `.invalid` catch-all.**
   Android's existing interceptor tests `host.endsWith(".invalid")` and
   throws; that predicate swallows `pending.invalid` and silently turns every
   LOADING fixture back into an ERROR fixture.

3. **No timeout may convert the stall into a failure.** A stall that expires
   mid-suite is worse than no stall: the fixture is deterministic for the
   fixtures that run early and flips for the ones that run late. The host
   must disable — not lengthen — call/read timeouts for this host name.

4. **The stall must not cost a blocked thread per fixture where the platform
   offers a non-blocking form** (iOS `URLProtocol`, Playwright `page.route`
   both do). Where it does block (OkHttp's interceptor chain), release it at
   suite teardown so the run can exit.

5. **The loading face under test must be a static image, never a spinner.**
   Both the web and Android capture paths shoot until two consecutive frames
   are byte-identical; an animated face never converges, so they exhaust
   their retries and then photograph an arbitrary frame. This is a fixture
   rule, not a preference — it belongs to whoever shapes the fixture.

6. **A host that has not implemented the stall must fail, not pass quietly.**
   Without it the request reaches a real resolver, `pending.invalid` gets
   NXDOMAIN like any `.invalid` name, and the error face is photographed
   instead — a picture that can be baked into a baseline and stay green
   forever. The guard is the fixture's **control**:
   `NetworkImage/loadingImage__static` is today the only NetworkImage state
   fixture with `"control": null`, and it must be given one (the same
   no-`defaultImage` control its `errorImage` sibling uses).
   - stall installed → fixture paints the alt asset, control paints blank →
     **active**
   - stall missing → both paint the error face → **inert**

   An inert result cannot then hide: inert on one platform and active on the
   other is a `cross_effect` divergence row, inert on both is a
   uniformly-inert row, and as of `2bb8d07` a new unreviewed row of either
   kind exceeds the `gate_ratchet.json` unreviewed ceiling and fails the
   gate. "The host quietly didn't implement it" has no green path.

### What this contract deliberately does NOT change

- **`RESULTS_SCHEMA.md` is untouched.** No new status, no `artifacts[]`, no
  artifact kind. The capture is an ordinary PNG of a resting state and rides
  the existing `screenshot` field. (A fifth status would also have been
  quietly downgraded: `report.py:_status_of` maps anything outside
  `pass/fail/error/skipped` to `error`.)
- **No screenshot-timing change on any platform.** Once the loading face is
  a resting state, the existing settle and stability logic is already
  correct. iOS's lack of a stability loop is a separate weakness, not one
  this fixture introduces.
- **No driver release.** The fixture's test is `waitFor(root)` +
  `screenshot(name)` — vocabulary all three drivers have shipped for a long
  time. The stall lives in the three *host apps*
  (`conformance/hosts/web/scripts/run.ts`, SwiftJsonUI `ConformanceHost`,
  KotlinJsonUI `conformance-host`), and not one of them is a driver.

### Scope: two platforms, not three

`loadingImage` is declared `platform: [swift, kotlin]`; the manifest rows for
both `Image/loadingImage__static` and `NetworkImage/loadingImage__static` say
`platforms: ["ios", "android"]`. Web is out of scope — it reports `skipped`
with a `detail`, as it does today. The web mechanism is specified below
anyway so it is ready if a web-declared loading attribute ever gets a
fixture; nothing today requires it.

### Per-platform implementation

- **Android** (`conformance-host/.../ConformanceHostApp.kt`) — add the
  `pending.invalid` branch **above** the existing `.endsWith(".invalid")`
  throw, blocking on a latch that is released at teardown, and build the
  client with the timeouts zeroed. Both Coil generations already share this
  client, so both host modes inherit it.
- **iOS** (`ConformanceHost/App/`) — a `URLProtocol` subclass whose `canInit`
  matches the host name and whose `startLoading()` simply never calls its
  client back; `stopLoading()` is a no-op. Non-blocking and thread-free.
  Register it on the loader's `URLSessionConfiguration.protocolClasses`, not
  only via `URLProtocol.registerClass` — a loader with its own session will
  not see the latter.
- **Web** (`conformance/hosts/web/scripts/run.ts`) — `page.route` on the host
  name, before `page.goto`, with a handler that neither fulfills nor aborts.

## Fixture case types the host will encounter

| case | mechanism exercised | trigger |
|---|---|---|
| `binding_initial` | `@{var}` + data default renders | none (assert only) |
| `binding_twoway` | input edit -> var -> mirror Label | `input` |
| `callback_fire` | handler mutates var -> mirror Label | `tap` / `input` / `selectOption` / `longPress` / none (`onAppear`) |
| `binding_visible` / `binding_invisible` / `binding_gone` | enum sweep through a binding | none (visible / notVisible asserts) |

## Result reporting

Unchanged from RESULTS_SCHEMA.md: one entry per manifest fixture. Interactive
fixtures are ordinary pass/fail/error entries; report platform-inapplicable
or mode-inapplicable fixtures as `skipped` with a `detail`, exactly like
static fixtures. No screenshots are required for interactive fixtures.

## Notes for the iOS/Android round

- `common/onAppear` is `mode: compose`; hosts that don't render that mode
  skip it (the web host does).
- `common/onLongPress` is `platform: [swift, kotlin]` — it never ran on web;
  iOS/Android are its first real executions (driver `longPress` action).
- `selectOption` drives SelectBox fixtures; verify the platform driver
  implements it before the run (web's Playwright executor does).
- Not promoted in v2 (still skipped, revisit here): boolean two-way `bind`
  attrs (need a `checked`-style assertion in the runner vocabulary),
  Slider/Segment/TabView value callbacks (no deterministic driver action),
  TextField focus/editing callbacks (need focus-shift vocabulary).
