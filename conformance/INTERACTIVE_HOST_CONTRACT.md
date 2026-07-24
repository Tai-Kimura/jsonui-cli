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

Determinism rules: no randomness, no time, no network. All state values are
strings (`class: "String"`) in v2 — the most portable `defaultValue`
representation across the three runtimes. The state vocabulary is fixed:
`conformanceText`, `conformanceResult`, `conformanceVisibility` vars, the
`conformanceFire` handler (`set` kind), and the `confPush` / `confPop`
handlers (`embed` kind, Embed isolated fixtures).

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
