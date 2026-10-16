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

   A handler declares exactly one of three operation kinds:

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
   - `count: { var }` — invoking the closure adds 1 to the variable
     `count.var` (a string holding an integer: "0" → "1" → "2") and
     re-renders. It is how a fixture tells a handler called once from one
     called twice, which `set` cannot (from jsonui-cli 1.9.6; the event x
     declared-form probes of 2026-10-03 measured one call per single action
     with it). Hosts: web (this repository's host), iOS ConformanceHost
     (SwiftJsonUI, dynamic and codegen faces — on its measurement branch at
     1.9.6, to land with the next SwiftJsonUI release); the Android host does
     not have it yet. The generator does not emit a `count` fixture yet, so
     no gate depends on it until all three hosts carry it.

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

## afterFirstDraw — one change the host makes after the first draw (2026-10-14)

Some visual fixtures photograph a REACTION to a change rather than a first
draw. A Collection's scrollTo request is the one that made this necessary: the
request is a change of the bound value, and the value a list is drawn with
scrolls nowhere (jsonui-cli 1.9.0). A static fixture therefore never asked
anything to scroll, and `scrollAnchor` top / center / bottom drew the same
picture on every face (conformance-collection-scrollanchor-family-does-not-
discriminate). Such a fixture declares the change in its manifest `state`:

```json
"state": {
  "vars": [ { "name": "scrollTarget", "class": "String", "defaultValue": "" } ],
  "handlers": [],
  "afterFirstDraw": { "name": "conformanceAfterFirstDraw",
                      "set": { "var": "scrollTarget", "value": "Gamma" } }
}
```

The generator writes it (`rules.AFTER_FIRST_DRAW`, keyed by the binding the
layout carries, so a family's shared control declares the same change). It is
the `set` operation of §2, but it is not a handler: the layout does not name
it, nothing in the layout calls it, and a host must not register it under
`name` in the data — the codegen faces have no member of that name. `class`
of every afterFirstDraw var is `String` and `value` a literal string, as with
`set`.

Every host face (iOS Dynamic and codegen, Android Dynamic and codegen, web):

1. **Fire once, itself, after the first draw.** When the fixture's first frame
   has been drawn, set `set.var` to `set.value` through the same path a `set`
   handler uses on that face (the state store / data map / generated
   ViewModel / React state), exactly once. A face that renders no `state.vars`
   for the fixture still provisions the declared var with its default before
   the first draw.
2. **Stamp it.** Record the time the change was made (`firedAtMs`) and the time
   the first frame drawn WITH the changed value was drawn (`appliedAtMs`), both
   in ms after the first draw. The stamp is what the runner waits for; a
   host that has not drawn the changed value has not applied it.
3. **The runner waits, then photographs.** Before the fixture's `screenshot`
   step the runner waits for the applied stamp (budget 10 s), then reads where
   every id is drawn every 0.25 s until the reading has stood still for 1 s
   (budget 10 s) — the shape of the iOS host's `Landing.wait`: a bounded read,
   never a fixed sleep. A change whose effect starts later than that `still`
   window would be photographed early; the series in the result says so.
4. **The result says what happened** (RESULTS_SCHEMA.md `afterFirstDraw`):
   `fired` with both times and the landing line, or `not-fired` with why.

`jui conformance gate` fails a declaring fixture whose result has no stamp or
a stamp other than `fired` (after_first_draw.py), on the dynamic faces always
and on the codegen faces with `--parity`. A fixture that does not declare
afterFirstDraw is captured exactly as before.

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
  here is carried only for data-source fidelity. A section may also carry
  `"header": {...}` and `"footer": {...}` (jsonui-cli 1.9.0): that section's
  header / footer data, its view named by the node's `sections` declaration
  as for the cells. The renderers draw a declared header or footer only when
  its section has data, so a fixture that declares one gives it data here.
  Carried by the three codegen literals and both hosts' materializers from
  jsonui-cli 1.9.0; until then only the cells were, and no fixture could
  draw a section header on iOS or Android.
- **nested** (2026-09-03) — a value inside a cell dictionary written in the
  explicit shape (`"items": {"sections": [...]}`) is itself a Collection's
  data: the iOS host materializes it into a nested `CollectionDataSource`, so
  a Collection inside a cell layout (`items: "@{items}"` in the cell file) is
  fed through the cell dictionary. That is the only channel that reaches a
  cell file — a cell is rendered from its own layout with the cell dictionary
  as its data, and the root `data` section is not visible there. Plain arrays
  inside a cell dictionary are left as they are (a string list looks the
  same). Implemented: `ConformanceStateProvider.materializeNestedCollections`.

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

## 6. testBridge — initialState delivered at launch, and `state` (2026-10-16)

jsonui-test-runner spec §10: a screen applies a UI test's initialState once,
the first time it appears after launch, and publishes its Data plus a receipt
(the state bridge). Generator side:
`jui_tools/jui_cli/conformance/test_bridge_fixtures.py` (section `TestBridge`).
The four fixtures drive no input, so the codegen faces host them too.

A fixture that carries `testBridge` in the manifest:

```json
"testBridge": {
  "data": [ { "name": "tbEmail", "class": "String", "defaultValue": "unset" }, … ],
  "initialState": { "tbEmail": "a@example.com", "tbCount": 3, "tbAgreed": true, "tbNickname": null },
  "receipt": { "applied": ["tbAgreed", "tbCount", "tbEmail", "tbNickname"], "rejected": [] },
  "remount": true
}
```

- `data` is the layout's `data` section, repeated so a host need not parse the
  layout. It is typed (Int, Bool, an optional String): these values do NOT go
  through `state.vars` (String-only, see above).
- `initialState` and `receipt` are absent on a fixture that only reads
  `state` (`initialState__bridge_follows`).

### The host's four jobs

Once, for every testBridge fixture — no per-fixture code.

1. **Deliver at launch.** For each launch, one `JSONUI_TEST_INITIAL_STATE`
   payload `{version: 1, launchId: <a UUID>, screens: {…}}` carrying every
   testBridge fixture in the batch that has an `initialState`, each under the
   screen id THIS FACE gives that fixture's screen (its bridge's id): iOS env,
   Android intent extra, web sessionStorage. One launch can carry many
   fixtures — their screen ids differ.
2. **Check the receipt.** When the fixture is on screen, read its bridge and
   wait (up to the host's screen-ready time) for `initialState` with this
   launch's `launchId`. Compare `applied` and `rejected` with
   `testBridge.receipt` as sets (a rejection is key + reason). A receipt that
   never comes, or differs, fails the fixture with what was seen.
3. **Point `state` at the screen.** Before the steps run, tell the assertion
   executor which screen `state` reads (iOS `setStateScreen`, the same idea on
   the other drivers): this face's screen id for the fixture.
4. **Remount when asked.** With `remount: true`, after the receipt check and
   before the steps, rebuild the fixture view AND its data store, so a new
   instance of the same screen appears in the same launch. The steps then
   expect the defaults: the payload is applied once per launch and screen.

### Where the bridge comes from on each face

- **Codegen** (sjui / kjui / rjui output): the generated screen view carries
  the bridge; the host passes the generated Data through as it does for any
  fixture. Its screen id is the staged layout's (iOS `fx_NNNN`).
- **Dynamic** (a host that drives the runtime's DynamicView directly): the
  host attaches the library's bridge itself — iOS
  `.jsonUITestBridge(screenId, snapshot:apply:)` — over a typed store made
  from `testBridge.data` (defaults from `defaultValue`), with `apply`
  judging each value by the library's check (iOS
  `JsonUITestValue.check(_:declaredClass:)`, the one place a value is
  judged) and `snapshot` returning the store as JSON values. The screen id
  is the host's choice; it is the key used in job 1 and job 3.

### The four fixtures

| fixture | delivers | the steps check |
|---|---|---|
| `TestBridge/initialState__applied` | String, Int, Bool, null for `String?` | the label shows the string; `state` reads all four |
| `TestBridge/initialState__rejected` | a string, an undeclared key, 1.5 for an Int | the string is in; the Int keeps 0; the receipt lists the two rejections with the spec's reasons |
| `TestBridge/initialState__not_reapplied` | a string, then `remount` | after the remount the label and `state` show the default |
| `TestBridge/initialState__bridge_follows` | nothing; afterFirstDraw sets `conformanceResult` | `state` reads the new value; the mirror label too |

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
